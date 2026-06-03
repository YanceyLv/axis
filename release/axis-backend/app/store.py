import os
import base64
import hashlib
import hmac
import json
import logging
import sqlite3
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Protocol, TypeVar
from uuid import uuid4

from pydantic import BaseModel

from app.models import (
    CreateStrategyRequest,
    CreateWatchItemRequest,
    GeneratedStrategy,
    GeneratedStrategyCondition,
    GeneratedStrategyHistoryStats,
    GeneratedStrategyRiskAdvice,
    AuthUser,
    AppSettingsResponse,
    AppSettingsUpdate,
    Candle,
    LlmSettingsResponse,
    PushoverSettingsResponse,
    KnowledgeCase,
    MarketKline,
    Signal,
    Strategy,
    StrategyScanHistory,
    StrategyRunError,
    StrategyRunProgress,
    StrategyRunResult,
    StrategyRuntime,
    StrategySchedule,
    UpdateStrategyRequest,
    WatchItem,
)


DEFAULT_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "axis.sqlite3"
ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
CLOSED_KLINE_LIMIT = 240
SCHEDULER_BOUNDARY_GRACE_SECONDS = 180
ModelT = TypeVar("ModelT", bound=BaseModel)
ENTITY_TABLES = ("strategies", "signals", "watch_items", "knowledge_cases", "strategy_scan_history")
USER_TABLE = "users"
SETTINGS_TABLE = "settings"
STRATEGY_GENERATION_CACHE_TABLE = "strategy_generation_cache"
MARKET_KLINE_TABLE = "market_klines"
SETTINGS_ID = "global"
logger = logging.getLogger("axis.strategy_generation")


class Store(Protocol):
    def reset(self) -> None: ...

    @property
    def strategies(self) -> list[Strategy]: ...

    @property
    def signals(self) -> list[Signal]: ...

    @property
    def watchlist(self) -> list[WatchItem]: ...

    @property
    def knowledge_cases(self) -> list[KnowledgeCase]: ...

    def generate_strategy(self, period: str, conditions: list[str], force_refresh: bool = False) -> GeneratedStrategy: ...

    def generate_strategy_from_code(self, period: str, python_code: str) -> GeneratedStrategy: ...

    def create_strategy(self, payload: CreateStrategyRequest) -> Strategy: ...

    def update_strategy(self, strategy_id: str, payload: UpdateStrategyRequest) -> Strategy | None: ...

    def delete_strategy(self, strategy_id: str) -> bool | None: ...

    def set_strategy_enabled(self, strategy_id: str, enabled: bool) -> Strategy | None: ...

    def set_strategy_schedule_enabled(self, strategy_id: str, enabled: bool) -> Strategy | None: ...

    def run_strategies_once(self) -> StrategyRunResult: ...

    def get_strategy_run_history(self, limit: int = 8) -> list[StrategyScanHistory]: ...

    def save_strategy_scan_history(self, item: StrategyScanHistory) -> None: ...

    def upsert_market_candles(self, symbol: str, period: str, candles: list[Candle]) -> None: ...

    def market_candles_for_signal(self, signal: Signal, limit: int = CLOSED_KLINE_LIMIT) -> list[Candle]: ...

    def create_watch_item(self, payload: CreateWatchItemRequest) -> WatchItem: ...

    def create_user(self, email: str, password: str) -> tuple[AuthUser, str]: ...

    def authenticate_user(self, email: str, password: str) -> tuple[AuthUser, str] | None: ...

    def user_for_token(self, token: str) -> AuthUser | None: ...

    def get_settings(self) -> AppSettingsResponse: ...

    def update_settings(self, payload: AppSettingsUpdate) -> AppSettingsResponse: ...


class SQLiteStore:
    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = Path(db_path or os.getenv("SIGNAL_DB_PATH", DEFAULT_DB_PATH))
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def reset(self) -> None:
        with self._connect() as connection:
            for table in ENTITY_TABLES:
                connection.execute(f"DELETE FROM {table}")
            connection.execute(f"DELETE FROM {MARKET_KLINE_TABLE}")
            connection.execute(f"DELETE FROM {USER_TABLE}")
            connection.execute(f"DELETE FROM {SETTINGS_TABLE}")
            connection.execute(f"DELETE FROM {STRATEGY_GENERATION_CACHE_TABLE}")

    @property
    def strategies(self) -> list[Strategy]:
        return self._list("strategies", Strategy)

    @property
    def signals(self) -> list[Signal]:
        return self._list("signals", Signal)

    @property
    def watchlist(self) -> list[WatchItem]:
        return self._list("watch_items", WatchItem)

    @property
    def knowledge_cases(self) -> list[KnowledgeCase]:
        return self._list("knowledge_cases", KnowledgeCase)

    def generate_strategy(self, period: str, conditions: list[str], force_refresh: bool = False) -> GeneratedStrategy:
        cache_key = _strategy_generation_cache_key(period, conditions)
        if not force_refresh:
            cached = self._get_strategy_generation_cache(cache_key)
            if cached is not None and not _has_placeholder_python_code(cached.pythonCode):
                return cached.model_copy(update={"generationCached": True})

        generated = _generate_strategy_preview(period, conditions, self._get_raw_settings())
        if generated.generationSource == "llm":
            self._upsert_strategy_generation_cache(cache_key, generated)
        return generated

    def generate_strategy_from_code(self, period: str, python_code: str) -> GeneratedStrategy:
        return _generate_strategy_from_code_preview(period, python_code, self._get_raw_settings())

    def create_strategy(self, payload: CreateStrategyRequest) -> Strategy:
        _validate_strategy_payload(payload)
        strategy = Strategy(
            id=f"st-{uuid4().hex[:8]}",
            name=payload.name,
            source="ai",
            period=payload.period,
            enabled=True,
            conditions=payload.conditions,
            description=payload.description,
            score=payload.score,
            todaySignalCount=0,
            lastTriggeredAt=None,
            createdAt=_now_iso(),
            symbolBlacklist=_normalize_symbol_blacklist(payload.symbolBlacklist),
            runtime=StrategyRuntime(
                code=payload.pythonCode,
                structuredConditions=payload.structuredConditions,
                aiAnalysis=payload.aiAnalysis,
            ),
            schedule=StrategySchedule(
                enabled=payload.scheduleEnabled,
                intervalSeconds=payload.intervalSeconds,
            ),
        )
        self._upsert("strategies", strategy, self._next_front_order("strategies"))
        return strategy

    def set_strategy_enabled(self, strategy_id: str, enabled: bool) -> Strategy | None:
        strategy = self._get("strategies", strategy_id, Strategy)
        if strategy is None:
            return None

        updated = strategy.model_copy(update={"enabled": enabled})
        self._upsert("strategies", updated, self._order_for_id("strategies", strategy_id))
        return updated

    def set_strategy_schedule_enabled(self, strategy_id: str, enabled: bool) -> Strategy | None:
        strategy = self._get("strategies", strategy_id, Strategy)
        if strategy is None:
            return None

        updated = strategy.model_copy(update={"schedule": strategy.schedule.model_copy(update={"enabled": enabled})})
        self._upsert("strategies", updated, self._order_for_id("strategies", strategy_id))
        return updated

    def update_strategy(self, strategy_id: str, payload: UpdateStrategyRequest) -> Strategy | None:
        strategy = self._get("strategies", strategy_id, Strategy)
        if strategy is None:
            return None
        if strategy.enabled:
            raise ValueError("运行中的策略不能编辑，请先暂停策略")
        _validate_strategy_payload(payload)

        updated = strategy.model_copy(
            update={
                "name": payload.name,
                "period": payload.period,
                "enabled": payload.enabled,
                "conditions": payload.conditions,
                "description": payload.description,
                "score": payload.score,
                "symbolBlacklist": _normalize_symbol_blacklist(payload.symbolBlacklist),
                "runtime": StrategyRuntime(
                    code=payload.pythonCode,
                    structuredConditions=payload.structuredConditions,
                    aiAnalysis=payload.aiAnalysis,
                ),
                "schedule": strategy.schedule.model_copy(
                    update={
                        "enabled": payload.scheduleEnabled,
                        "intervalSeconds": payload.intervalSeconds,
                    }
                ),
            }
        )
        self._upsert("strategies", updated, self._order_for_id("strategies", strategy_id))
        return updated

    def delete_strategy(self, strategy_id: str) -> bool | None:
        strategy = self._get("strategies", strategy_id, Strategy)
        if strategy is None:
            return None
        if strategy.enabled:
            raise ValueError("运行中的策略不能删除，请先暂停策略")

        self._delete("strategies", strategy_id)
        return True

    def run_strategies_once(self) -> StrategyRunResult:
        return _run_strategies_once(self)

    def get_strategy_run_history(self, limit: int = 8) -> list[StrategyScanHistory]:
        return self._list("strategy_scan_history", StrategyScanHistory)[:limit]

    def save_strategy_scan_history(self, item: StrategyScanHistory) -> None:
        self._upsert("strategy_scan_history", item, self._next_front_order("strategy_scan_history"))

    def create_watch_item(self, payload: CreateWatchItemRequest) -> WatchItem:
        current_price, change_24h = self._market_data_for_symbol(payload.symbol)
        watch_item = WatchItem(
            id=f"watch-{uuid4().hex[:8]}",
            symbol=payload.symbol,
            currentPrice=current_price,
            change24h=change_24h,
            conditions=payload.conditions,
            lastTriggeredAt=None,
            createdAt=_now_iso(),
        )
        self._upsert("watch_items", watch_item, self._next_front_order("watch_items"))
        return watch_item

    def create_user(self, email: str, password: str) -> tuple[AuthUser, str]:
        normalized_email = _normalize_email(email)
        user = AuthUser(id=f"user-{uuid4().hex[:12]}", email=normalized_email, createdAt=_now_iso())
        password_hash = _hash_password(password)
        token = _make_token()
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {USER_TABLE} (id, email, password_hash, token, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user.id, user.email, password_hash, token, user.createdAt, user.createdAt),
            )
        return user, token

    def authenticate_user(self, email: str, password: str) -> tuple[AuthUser, str] | None:
        normalized_email = _normalize_email(email)
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT id, email, password_hash, token, created_at FROM {USER_TABLE} WHERE email = ?",
                (normalized_email,),
            ).fetchone()

        if row is None or not _verify_password(password, row[2]):
            return None

        return AuthUser(id=row[0], email=row[1], createdAt=row[4]), row[3]

    def user_for_token(self, token: str) -> AuthUser | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT id, email, created_at FROM {USER_TABLE} WHERE token = ?",
                (token,),
            ).fetchone()

        return AuthUser(id=row[0], email=row[1], createdAt=row[2]) if row else None

    def get_settings(self) -> AppSettingsResponse:
        stored = self._get_raw_settings()
        return _settings_response(stored)

    def update_settings(self, payload: AppSettingsUpdate) -> AppSettingsResponse:
        current = self._get_raw_settings()
        raw_settings = _merge_settings(current, payload)
        now = _now_iso()
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {SETTINGS_TABLE} (id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (SETTINGS_ID, _json_dumps(raw_settings), now, now),
            )
        return _settings_response(raw_settings)

    def _init_schema(self) -> None:
        with self._connect() as connection:
            for table in ENTITY_TABLES:
                connection.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table} (
                        id TEXT PRIMARY KEY,
                        sort_order INTEGER NOT NULL,
                        payload TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        updated_at TEXT NOT NULL
                    )
                    """
                )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {USER_TABLE} (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    token TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {SETTINGS_TABLE} (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {STRATEGY_GENERATION_CACHE_TABLE} (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {MARKET_KLINE_TABLE} (
                    id TEXT PRIMARY KEY,
                    symbol TEXT NOT NULL,
                    period TEXT NOT NULL,
                    open_time TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            connection.execute(
                f"CREATE INDEX IF NOT EXISTS idx_market_klines_lookup ON {MARKET_KLINE_TABLE} (symbol, period, open_time)"
            )

    def _is_empty(self) -> bool:
        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) FROM strategies").fetchone()
        return int(row[0]) == 0

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def _insert_many(self, connection: sqlite3.Connection, table: str, items: list[BaseModel]) -> None:
        now = _now_iso()
        connection.executemany(
            f"""
            INSERT INTO {table} (id, sort_order, payload, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (getattr(item, "id"), index, item.model_dump_json(), now, now)
                for index, item in enumerate(items)
            ],
        )

    def _list(self, table: str, model: type[ModelT]) -> list[ModelT]:
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT payload FROM {table} ORDER BY sort_order ASC, created_at ASC"
            ).fetchall()

        return [model.model_validate_json(row[0]) for row in rows]

    def _get(self, table: str, item_id: str, model: type[ModelT]) -> ModelT | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT payload FROM {table} WHERE id = ?",
                (item_id,),
            ).fetchone()

        return model.model_validate_json(row[0]) if row else None

    def _upsert(self, table: str, item: BaseModel, sort_order: int) -> None:
        now = _now_iso()
        item_id = getattr(item, "id")
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {table} (id, sort_order, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    sort_order = excluded.sort_order,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (item_id, sort_order, item.model_dump_json(), now, now),
            )

    def _delete(self, table: str, item_id: str) -> None:
        with self._connect() as connection:
            connection.execute(f"DELETE FROM {table} WHERE id = ?", (item_id,))

    def _next_front_order(self, table: str) -> int:
        with self._connect() as connection:
            row = connection.execute(f"SELECT MIN(sort_order) FROM {table}").fetchone()

        current = row[0]
        return -1 if current is None else int(current) - 1

    def _order_for_id(self, table: str, item_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT sort_order FROM {table} WHERE id = ?",
                (item_id,),
            ).fetchone()

        return int(row[0]) if row else self._next_front_order(table)

    def _market_data_for_symbol(self, symbol: str) -> tuple[float, float]:
        normalized_symbol = symbol.upper()
        latest_signal = max(
            (signal for signal in self.signals if signal.symbol.upper() == normalized_symbol),
            key=lambda signal: signal.triggeredAt,
            default=None,
        )
        existing_watch_item = next(
            (item for item in self.watchlist if item.symbol.upper() == normalized_symbol),
            None,
        )

        current_price = latest_signal.price if latest_signal else None
        change_24h = _change_from_candles(latest_signal.candles) if latest_signal else None

        if existing_watch_item:
            if current_price is None:
                current_price = existing_watch_item.currentPrice
            if change_24h is None:
                change_24h = existing_watch_item.change24h

        return current_price or 0, change_24h or 0

    def _get_raw_settings(self) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT payload FROM {SETTINGS_TABLE} WHERE id = ?",
                (SETTINGS_ID,),
            ).fetchone()

        return _json_loads(row[0]) if row else {}

    def _get_strategy_generation_cache(self, cache_key: str) -> GeneratedStrategy | None:
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT payload FROM {STRATEGY_GENERATION_CACHE_TABLE} WHERE id = ?",
                (cache_key,),
            ).fetchone()

        return GeneratedStrategy.model_validate_json(row[0]) if row else None

    def _upsert_strategy_generation_cache(self, cache_key: str, generated: GeneratedStrategy) -> None:
        now = _now_iso()
        payload = generated.model_copy(update={"generationCached": False}).model_dump_json()
        with self._connect() as connection:
            connection.execute(
                f"""
                INSERT INTO {STRATEGY_GENERATION_CACHE_TABLE} (id, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (cache_key, payload, now, now),
            )

    def upsert_market_candles(self, symbol: str, period: str, candles: list[Candle]) -> None:
        if not candles:
            return
        normalized_symbol = symbol.upper()
        normalized_period = str(period).upper()
        now = _now_iso()
        rows = []
        for candle in candles:
            item_id = _market_kline_id(normalized_symbol, normalized_period, candle.time)
            rows.append(
                (
                    item_id,
                    normalized_symbol,
                    normalized_period,
                    candle.time,
                    MarketKline(
                        id=item_id,
                        symbol=normalized_symbol,
                        period=normalized_period,  # type: ignore[arg-type]
                        openTime=candle.time,
                        candle=candle,
                        createdAt=now,
                        updatedAt=now,
                    ).model_dump_json(),
                    now,
                    now,
                )
            )
        with self._connect() as connection:
            connection.executemany(
                f"""
                INSERT INTO {MARKET_KLINE_TABLE} (id, symbol, period, open_time, payload, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                rows,
            )
            _prune_market_klines_sqlite(connection)

    def market_candles_for_signal(self, signal: Signal, limit: int = CLOSED_KLINE_LIMIT) -> list[Candle]:
        with self._connect() as connection:
            rows = connection.execute(
                f"""
                SELECT payload FROM {MARKET_KLINE_TABLE}
                WHERE symbol = ? AND period = ? AND open_time <= ?
                ORDER BY open_time DESC
                LIMIT ?
                """,
                (signal.symbol.upper(), signal.period, signal.triggeredAt, limit),
            ).fetchall()

        candles = [MarketKline.model_validate_json(row[0]).candle for row in reversed(rows)]
        return candles or signal.candles


class MySQLStore:
    def __init__(
        self,
        host: str | None = None,
        port: int | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str | None = None,
    ) -> None:
        self.host = host or os.getenv("MYSQL_HOST", "127.0.0.1")
        self.port = port or int(os.getenv("MYSQL_PORT", "3306"))
        self.user = user or os.getenv("MYSQL_USER", "root")
        self.password = password if password is not None else os.getenv("MYSQL_PASSWORD", "")
        self.database = database or os.getenv("MYSQL_DATABASE", "axis")
        self._ensure_database()
        self._init_schema()

    def reset(self) -> None:
        _assert_mysql_reset_allowed(self.database)
        with self._connect() as connection:
            cursor = connection.cursor()
            for table in ENTITY_TABLES:
                cursor.execute(f"DELETE FROM {table}")
            cursor.execute(f"DELETE FROM `{MARKET_KLINE_TABLE}`")
            cursor.execute(f"DELETE FROM `{USER_TABLE}`")
            cursor.execute(f"DELETE FROM `{SETTINGS_TABLE}`")
            cursor.execute(f"DELETE FROM `{STRATEGY_GENERATION_CACHE_TABLE}`")
            connection.commit()

    @property
    def strategies(self) -> list[Strategy]:
        return self._list("strategies", Strategy)

    @property
    def signals(self) -> list[Signal]:
        return self._list("signals", Signal)

    @property
    def watchlist(self) -> list[WatchItem]:
        return self._list("watch_items", WatchItem)

    @property
    def knowledge_cases(self) -> list[KnowledgeCase]:
        return self._list("knowledge_cases", KnowledgeCase)

    def generate_strategy(self, period: str, conditions: list[str], force_refresh: bool = False) -> GeneratedStrategy:
        cache_key = _strategy_generation_cache_key(period, conditions)
        if not force_refresh:
            cached = self._get_strategy_generation_cache(cache_key)
            if cached is not None and not _has_placeholder_python_code(cached.pythonCode):
                return cached.model_copy(update={"generationCached": True})

        generated = _generate_strategy_preview(period, conditions, self._get_raw_settings())
        if generated.generationSource == "llm":
            self._upsert_strategy_generation_cache(cache_key, generated)
        return generated

    def generate_strategy_from_code(self, period: str, python_code: str) -> GeneratedStrategy:
        return _generate_strategy_from_code_preview(period, python_code, self._get_raw_settings())

    def create_strategy(self, payload: CreateStrategyRequest) -> Strategy:
        _validate_strategy_payload(payload)
        strategy = Strategy(
            id=f"st-{uuid4().hex[:8]}",
            name=payload.name,
            source="ai",
            period=payload.period,
            enabled=True,
            conditions=payload.conditions,
            description=payload.description,
            score=payload.score,
            todaySignalCount=0,
            lastTriggeredAt=None,
            createdAt=_now_iso(),
            symbolBlacklist=_normalize_symbol_blacklist(payload.symbolBlacklist),
            runtime=StrategyRuntime(
                code=payload.pythonCode,
                structuredConditions=payload.structuredConditions,
                aiAnalysis=payload.aiAnalysis,
            ),
            schedule=StrategySchedule(
                enabled=payload.scheduleEnabled,
                intervalSeconds=payload.intervalSeconds,
            ),
        )
        self._upsert("strategies", strategy, self._next_front_order("strategies"))
        return strategy

    def set_strategy_enabled(self, strategy_id: str, enabled: bool) -> Strategy | None:
        strategy = self._get("strategies", strategy_id, Strategy)
        if strategy is None:
            return None

        updated = strategy.model_copy(update={"enabled": enabled})
        self._upsert("strategies", updated, self._order_for_id("strategies", strategy_id))
        return updated

    def set_strategy_schedule_enabled(self, strategy_id: str, enabled: bool) -> Strategy | None:
        strategy = self._get("strategies", strategy_id, Strategy)
        if strategy is None:
            return None

        updated = strategy.model_copy(update={"schedule": strategy.schedule.model_copy(update={"enabled": enabled})})
        self._upsert("strategies", updated, self._order_for_id("strategies", strategy_id))
        return updated

    def update_strategy(self, strategy_id: str, payload: UpdateStrategyRequest) -> Strategy | None:
        strategy = self._get("strategies", strategy_id, Strategy)
        if strategy is None:
            return None
        if strategy.enabled:
            raise ValueError("运行中的策略不能编辑，请先暂停策略")
        _validate_strategy_payload(payload)

        updated = strategy.model_copy(
            update={
                "name": payload.name,
                "period": payload.period,
                "enabled": payload.enabled,
                "conditions": payload.conditions,
                "description": payload.description,
                "score": payload.score,
                "symbolBlacklist": _normalize_symbol_blacklist(payload.symbolBlacklist),
                "runtime": StrategyRuntime(
                    code=payload.pythonCode,
                    structuredConditions=payload.structuredConditions,
                    aiAnalysis=payload.aiAnalysis,
                ),
                "schedule": strategy.schedule.model_copy(
                    update={
                        "enabled": payload.scheduleEnabled,
                        "intervalSeconds": payload.intervalSeconds,
                    }
                ),
            }
        )
        self._upsert("strategies", updated, self._order_for_id("strategies", strategy_id))
        return updated

    def delete_strategy(self, strategy_id: str) -> bool | None:
        strategy = self._get("strategies", strategy_id, Strategy)
        if strategy is None:
            return None
        if strategy.enabled:
            raise ValueError("运行中的策略不能删除，请先暂停策略")

        self._delete("strategies", strategy_id)
        return True

    def run_strategies_once(self) -> StrategyRunResult:
        return _run_strategies_once(self)

    def get_strategy_run_history(self, limit: int = 8) -> list[StrategyScanHistory]:
        return self._list("strategy_scan_history", StrategyScanHistory)[:limit]

    def save_strategy_scan_history(self, item: StrategyScanHistory) -> None:
        self._upsert("strategy_scan_history", item, self._next_front_order("strategy_scan_history"))

    def create_watch_item(self, payload: CreateWatchItemRequest) -> WatchItem:
        current_price, change_24h = self._market_data_for_symbol(payload.symbol)
        watch_item = WatchItem(
            id=f"watch-{uuid4().hex[:8]}",
            symbol=payload.symbol,
            currentPrice=current_price,
            change24h=change_24h,
            conditions=payload.conditions,
            lastTriggeredAt=None,
            createdAt=_now_iso(),
        )
        self._upsert("watch_items", watch_item, self._next_front_order("watch_items"))
        return watch_item

    def create_user(self, email: str, password: str) -> tuple[AuthUser, str]:
        normalized_email = _normalize_email(email)
        user = AuthUser(id=f"user-{uuid4().hex[:12]}", email=normalized_email, createdAt=_now_iso())
        password_hash = _hash_password(password)
        token = _make_token()
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                INSERT INTO `{USER_TABLE}` (id, email, password_hash, token, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user.id, user.email, password_hash, token, user.createdAt, user.createdAt),
            )
            connection.commit()
        return user, token

    def authenticate_user(self, email: str, password: str) -> tuple[AuthUser, str] | None:
        normalized_email = _normalize_email(email)
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT id, email, password_hash, token, created_at FROM `{USER_TABLE}` WHERE email = %s",
                (normalized_email,),
            )
            row = cursor.fetchone()

        if row is None or not _verify_password(password, row[2]):
            return None

        return AuthUser(id=row[0], email=row[1], createdAt=row[4]), row[3]

    def user_for_token(self, token: str) -> AuthUser | None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT id, email, created_at FROM `{USER_TABLE}` WHERE token = %s",
                (token,),
            )
            row = cursor.fetchone()

        return AuthUser(id=row[0], email=row[1], createdAt=row[2]) if row else None

    def get_settings(self) -> AppSettingsResponse:
        stored = self._get_raw_settings()
        return _settings_response(stored)

    def update_settings(self, payload: AppSettingsUpdate) -> AppSettingsResponse:
        current = self._get_raw_settings()
        raw_settings = _merge_settings(current, payload)
        now = _now_iso()
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                INSERT INTO `{SETTINGS_TABLE}` (id, payload, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    payload = VALUES(payload),
                    updated_at = VALUES(updated_at)
                """,
                (SETTINGS_ID, _json_dumps(raw_settings), now, now),
            )
            connection.commit()
        return _settings_response(raw_settings)

    def _ensure_database(self) -> None:
        mysql_connector = _mysql_connector()
        connection = mysql_connector.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            charset="utf8mb4",
            use_unicode=True,
        )
        try:
            cursor = connection.cursor()
            cursor.execute(
                f"CREATE DATABASE IF NOT EXISTS `{self.database}` "
                "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
            )
            connection.commit()
        finally:
            connection.close()

    def _init_schema(self) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            for table in ENTITY_TABLES:
                cursor.execute(
                    f"""
                    CREATE TABLE IF NOT EXISTS `{table}` (
                        id VARCHAR(96) PRIMARY KEY,
                        sort_order INT NOT NULL,
                        payload JSON NOT NULL,
                        created_at VARCHAR(40) NOT NULL,
                        updated_at VARCHAR(40) NOT NULL,
                        INDEX idx_{table}_sort_order (sort_order),
                        INDEX idx_{table}_created_at (created_at)
                    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                    """
                )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{USER_TABLE}` (
                    id VARCHAR(96) PRIMARY KEY,
                    email VARCHAR(255) NOT NULL UNIQUE,
                    password_hash VARCHAR(255) NOT NULL,
                    token VARCHAR(96) NOT NULL,
                    created_at VARCHAR(40) NOT NULL,
                    updated_at VARCHAR(40) NOT NULL,
                    INDEX idx_users_email (email)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{SETTINGS_TABLE}` (
                    id VARCHAR(64) PRIMARY KEY,
                    payload JSON NOT NULL,
                    created_at VARCHAR(40) NOT NULL,
                    updated_at VARCHAR(40) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{STRATEGY_GENERATION_CACHE_TABLE}` (
                    id VARCHAR(96) PRIMARY KEY,
                    payload JSON NOT NULL,
                    created_at VARCHAR(40) NOT NULL,
                    updated_at VARCHAR(40) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{MARKET_KLINE_TABLE}` (
                    id VARCHAR(128) PRIMARY KEY,
                    symbol VARCHAR(32) NOT NULL,
                    period VARCHAR(8) NOT NULL,
                    open_time VARCHAR(40) NOT NULL,
                    payload JSON NOT NULL,
                    created_at VARCHAR(40) NOT NULL,
                    updated_at VARCHAR(40) NOT NULL,
                    INDEX idx_market_klines_lookup (symbol, period, open_time),
                    INDEX idx_market_klines_open_time (open_time)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            connection.commit()

    def _is_empty(self) -> bool:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT COUNT(*) FROM strategies")
            row = cursor.fetchone()
        return int(row[0]) == 0

    def _connect(self):
        mysql_connector = _mysql_connector()
        return mysql_connector.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            use_unicode=True,
        )

    def _insert_many(self, cursor: Any, table: str, items: list[BaseModel]) -> None:
        now = _now_iso()
        cursor.executemany(
            f"""
            INSERT INTO `{table}` (id, sort_order, payload, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s)
            """,
            [
                (getattr(item, "id"), index, item.model_dump_json(), now, now)
                for index, item in enumerate(items)
            ],
        )

    def _list(self, table: str, model: type[ModelT]) -> list[ModelT]:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT payload FROM `{table}` ORDER BY sort_order ASC, created_at ASC")
            rows = cursor.fetchall()

        return [model.model_validate_json(_payload_text(row[0])) for row in rows]

    def _get(self, table: str, item_id: str, model: type[ModelT]) -> ModelT | None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT payload FROM `{table}` WHERE id = %s", (item_id,))
            row = cursor.fetchone()

        return model.model_validate_json(_payload_text(row[0])) if row else None

    def _upsert(self, table: str, item: BaseModel, sort_order: int) -> None:
        now = _now_iso()
        item_id = getattr(item, "id")
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                INSERT INTO `{table}` (id, sort_order, payload, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    sort_order = VALUES(sort_order),
                    payload = VALUES(payload),
                    updated_at = VALUES(updated_at)
                """,
                (item_id, sort_order, item.model_dump_json(), now, now),
            )
            connection.commit()

    def _delete(self, table: str, item_id: str) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"DELETE FROM `{table}` WHERE id = %s", (item_id,))
            connection.commit()

    def _next_front_order(self, table: str) -> int:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT MIN(sort_order) FROM `{table}`")
            row = cursor.fetchone()

        current = row[0]
        return -1 if current is None else int(current) - 1

    def _order_for_id(self, table: str, item_id: str) -> int:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT sort_order FROM `{table}` WHERE id = %s", (item_id,))
            row = cursor.fetchone()

        return int(row[0]) if row else self._next_front_order(table)

    def _market_data_for_symbol(self, symbol: str) -> tuple[float, float]:
        normalized_symbol = symbol.upper()
        latest_signal = max(
            (signal for signal in self.signals if signal.symbol.upper() == normalized_symbol),
            key=lambda signal: signal.triggeredAt,
            default=None,
        )
        existing_watch_item = next(
            (item for item in self.watchlist if item.symbol.upper() == normalized_symbol),
            None,
        )

        current_price = latest_signal.price if latest_signal else None
        change_24h = _change_from_candles(latest_signal.candles) if latest_signal else None

        if existing_watch_item:
            if current_price is None:
                current_price = existing_watch_item.currentPrice
            if change_24h is None:
                change_24h = existing_watch_item.change24h

        return current_price or 0, change_24h or 0

    def _get_raw_settings(self) -> dict[str, Any]:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT payload FROM `{SETTINGS_TABLE}` WHERE id = %s", (SETTINGS_ID,))
            row = cursor.fetchone()

        return _json_loads(_payload_text(row[0])) if row else {}

    def _get_strategy_generation_cache(self, cache_key: str) -> GeneratedStrategy | None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT payload FROM `{STRATEGY_GENERATION_CACHE_TABLE}` WHERE id = %s",
                (cache_key,),
            )
            row = cursor.fetchone()

        return GeneratedStrategy.model_validate_json(_payload_text(row[0])) if row else None

    def _upsert_strategy_generation_cache(self, cache_key: str, generated: GeneratedStrategy) -> None:
        now = _now_iso()
        payload = generated.model_copy(update={"generationCached": False}).model_dump_json()
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                INSERT INTO `{STRATEGY_GENERATION_CACHE_TABLE}` (id, payload, created_at, updated_at)
                VALUES (%s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    payload = VALUES(payload),
                    updated_at = VALUES(updated_at)
                """,
                (cache_key, payload, now, now),
            )
            connection.commit()

    def upsert_market_candles(self, symbol: str, period: str, candles: list[Candle]) -> None:
        if not candles:
            return
        normalized_symbol = symbol.upper()
        normalized_period = str(period).upper()
        now = _now_iso()
        rows = []
        for candle in candles:
            item_id = _market_kline_id(normalized_symbol, normalized_period, candle.time)
            rows.append(
                (
                    item_id,
                    normalized_symbol,
                    normalized_period,
                    candle.time,
                    MarketKline(
                        id=item_id,
                        symbol=normalized_symbol,
                        period=normalized_period,  # type: ignore[arg-type]
                        openTime=candle.time,
                        candle=candle,
                        createdAt=now,
                        updatedAt=now,
                    ).model_dump_json(),
                    now,
                    now,
                )
            )
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.executemany(
                f"""
                INSERT INTO `{MARKET_KLINE_TABLE}` (id, symbol, period, open_time, payload, created_at, updated_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    payload = VALUES(payload),
                    updated_at = VALUES(updated_at)
                """,
                rows,
            )
            _prune_market_klines_mysql(cursor)
            connection.commit()

    def market_candles_for_signal(self, signal: Signal, limit: int = CLOSED_KLINE_LIMIT) -> list[Candle]:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT payload FROM `{MARKET_KLINE_TABLE}`
                WHERE symbol = %s AND period = %s AND open_time <= %s
                ORDER BY open_time DESC
                LIMIT %s
                """,
                (signal.symbol.upper(), signal.period, signal.triggeredAt, limit),
            )
            rows = cursor.fetchall()

        candles = [MarketKline.model_validate_json(_payload_text(row[0])).candle for row in reversed(rows)]
        return candles or signal.candles


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _market_kline_id(symbol: str, period: str, open_time: str) -> str:
    raw = f"{symbol.upper()}:{period.upper()}:{open_time}"
    return f"mk-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:40]}"


def _store_market_candles(store_instance: Any, symbol: str, period: str, candles: list[Candle]) -> None:
    try:
        store_instance.upsert_market_candles(symbol, period, candles)
    except Exception:
        # K-line cache should never interrupt strategy scanning.
        return


def _send_signal_pushover_if_configured(store_instance: Any, signal: Signal) -> str | None:
    try:
        raw_settings = store_instance._get_raw_settings()
    except Exception as exc:
        return f"读取推送配置失败：{exc}"

    pushover = raw_settings.get("pushover") if isinstance(raw_settings.get("pushover"), dict) else {}
    if not pushover.get("enabled"):
        return None

    user_key = str(pushover.get("userKey") or "").strip()
    app_token = str(pushover.get("appToken") or "").strip()
    if not user_key or not app_token:
        return "Pushover 已启用但 User Key 或 Application Token 未配置"

    message = "\n".join(
        [
            f"币种：{signal.symbol}",
            f"周期：{signal.period}",
            f"策略：{signal.strategyName}",
            f"价格：{signal.price}",
            f"评分：{signal.score}",
        ]
    )
    payload = urllib.parse.urlencode(
        {
            "token": app_token,
            "user": user_key,
            "title": f"TrendAI 信号：{signal.symbol} {signal.period}",
            "message": message,
            "priority": "0",
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        "https://api.pushover.net/1/messages.json",
        data=payload,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status >= 400:
                return f"HTTP {response.status}"
            return None
    except Exception as exc:
        return str(exc)


def _market_kline_retention_cutoffs() -> dict[str, str]:
    now = datetime.now(timezone.utc)
    return {
        "1H": (now - timedelta(days=35)).isoformat(),
        "4H": (now - timedelta(days=120)).isoformat(),
        "1D": (now - timedelta(days=400)).isoformat(),
    }


def _prune_market_klines_sqlite(connection: sqlite3.Connection) -> None:
    for period, cutoff in _market_kline_retention_cutoffs().items():
        connection.execute(
            f"DELETE FROM {MARKET_KLINE_TABLE} WHERE period = ? AND open_time < ?",
            (period, cutoff),
        )


def _prune_market_klines_mysql(cursor: Any) -> None:
    for period, cutoff in _market_kline_retention_cutoffs().items():
        cursor.execute(
            f"DELETE FROM `{MARKET_KLINE_TABLE}` WHERE period = %s AND open_time < %s",
            (period, cutoff),
        )


def _generate_strategy_preview(period: str, conditions: list[str], raw_settings: dict[str, Any]) -> GeneratedStrategy:
    cleaned_conditions = [condition.strip() for condition in conditions if condition.strip()]
    prompt = _build_strategy_prompt(period, cleaned_conditions)
    llm_settings = _llm_settings_from_raw(raw_settings)

    generated, error = _call_llm_for_strategy(prompt, llm_settings) if llm_settings else (None, "LLM API is not configured")
    if generated is not None:
        return _normalize_generated_strategy(generated, period, cleaned_conditions, llm_settings)

    logger.warning("Strategy generation fell back without LLM result: period=%s error=%s", period, error)
    return _fallback_generated_strategy(period, cleaned_conditions, llm_settings, error)


def _generate_strategy_from_code_preview(period: str, python_code: str, raw_settings: dict[str, Any]) -> GeneratedStrategy:
    original_code = python_code.strip()
    source_conditions = _fallback_conditions_from_code(original_code)
    llm_settings = _llm_settings_from_raw(raw_settings)
    prompt = _build_strategy_from_code_prompt(period, original_code)

    generated, error = _call_llm_for_strategy(prompt, llm_settings) if llm_settings else (None, "LLM API is not configured")
    if generated is not None:
        return _normalize_generated_strategy(generated, period, source_conditions, llm_settings).model_copy(
            update={"pythonCode": original_code}
        )

    logger.warning("Strategy code import fell back without LLM result: period=%s error=%s", period, error)
    return _fallback_generated_strategy(period, source_conditions, llm_settings, error).model_copy(
        update={
            "name": f"{period} 粘贴代码导入策略",
            "description": "根据粘贴的 Python 代码导入，AI 未能生成完整结构化信息。",
            "summary": "该策略代码会原样保存；保存时只校验代码能否执行扫描，不会自动改写策略代码。",
            "pythonCode": original_code,
        }
    )


def _llm_settings_from_raw(raw_settings: dict[str, Any]) -> dict[str, Any]:
    llm_settings = raw_settings.get("llm") if isinstance(raw_settings.get("llm"), dict) else {}
    if not llm_settings and isinstance(raw_settings.get("api"), dict):
        llm_settings = raw_settings["api"]
    return llm_settings

def _strategy_generation_cache_key(period: str, conditions: list[str]) -> str:
    normalized = {
        "period": period,
        "conditions": [condition.strip() for condition in conditions if condition.strip()],
    }
    payload = json.dumps(normalized, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _has_placeholder_python_code(python_code: str) -> bool:
    compact = "".join((python_code or "").split()).lower()
    return (
        len(python_code.strip()) < 220
        or "defcheck_signal" not in compact
        or compact in {"defcheck_signal(candles):returntrue", "defcheck_signal(candles):returnfalse"}
        or "returntrue" in compact and len(python_code.strip().splitlines()) <= 3
    )


def _run_strategies_once(store_instance: Any) -> StrategyRunResult:
    created_signals: list[Signal] = []
    errors: list[str] = []
    strategies_checked = 0
    symbols_checked = 0
    market_snapshots = _latest_signal_by_symbol_and_period(store_instance.signals)

    for strategy in store_instance.strategies:
        if not strategy.enabled or not strategy.schedule.enabled or not strategy.runtime.code.strip():
            continue

        strategies_checked += 1
        strategy_created = 0
        run_at = _now_iso()
        strategy_errors: list[str] = []
        symbol_blacklist = set(_normalize_symbol_blacklist(strategy.symbolBlacklist))

        for symbol, source_signal in _scan_items_for_strategy(strategy.period, market_snapshots):
            if symbol.upper() in symbol_blacklist:
                continue
            symbols_checked += 1
            candles = source_signal.candles if source_signal is not None else []
            price = source_signal.price if source_signal is not None else 0
            try:
                candles = fetch_market_candles(symbol, strategy.period)
                _store_market_candles(store_instance, symbol, strategy.period, candles)
                if len(candles) < CLOSED_KLINE_LIMIT:
                    continue
                if candles:
                    price = candles[-1].close
                matched = _execute_strategy_code(strategy.runtime.code, candles)
            except Exception as exc:
                message = f"{strategy.name} / {symbol}: {exc}"
                errors.append(message)
                strategy_errors.append(message)
                continue

            if not matched:
                continue

            signal = Signal(
                id=f"sig-{uuid4().hex[:10]}",
                symbol=symbol,
                period=strategy.period,
                strategyId=strategy.id,
                strategyName=strategy.name,
                signalType="trend",
                score=strategy.score,
                triggeredAt=run_at,
                price=candles[-1].close if candles else price,
                summary=f"{symbol} 命中策略：{strategy.name}",
                analysis=strategy.runtime.aiAnalysis or strategy.conditions,
                strengthGrade="A",
                candles=candles,
            )
            _store_upsert_front(store_instance, "signals", signal)
            push_error = _send_signal_pushover_if_configured(store_instance, signal)
            if push_error:
                message = f"{strategy.name} / {symbol}: Pushover push failed: {push_error}"
                errors.append(message)
                strategy_errors.append(message)
            created_signals.append(signal)
            strategy_created += 1

        updated = strategy.model_copy(
            update={
                "todaySignalCount": strategy.todaySignalCount + strategy_created,
                "lastTriggeredAt": run_at if strategy_created else strategy.lastTriggeredAt,
                "schedule": strategy.schedule.model_copy(
                    update={
                        "lastRunAt": run_at,
                        "lastStatus": "error" if strategy_errors else "success",
                        "lastError": "\n".join(strategy_errors[:3]),
                    }
                ),
            }
        )
        store_instance._upsert("strategies", updated, store_instance._order_for_id("strategies", strategy.id))

    return StrategyRunResult(
        strategiesChecked=strategies_checked,
        symbolsChecked=symbols_checked,
        signalsCreated=len(created_signals),
        errors=errors,
        createdSignals=created_signals,
    )


def _latest_signal_by_symbol_and_period(signals: list[Signal]) -> dict[tuple[str, str], Signal]:
    latest: dict[tuple[str, str], Signal] = {}
    for signal in signals:
        key = (signal.symbol.upper(), signal.period)
        existing = latest.get(key)
        if existing is None or signal.triggeredAt > existing.triggeredAt:
            latest[key] = signal
    return latest


def _scan_items_for_strategy(
    period: str,
    market_snapshots: dict[tuple[str, str], Signal],
) -> list[tuple[str, Signal | None]]:
    symbols = fetch_tradable_symbols()
    if not symbols:
        symbols = sorted(symbol for (symbol, signal_period) in market_snapshots if signal_period == period)
    return [(symbol, market_snapshots.get((symbol, period))) for symbol in symbols]


def fetch_tradable_symbols() -> list[str]:
    url = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    raw_payload = _read_url_with_retry(url, timeout=10)
    payload = json.loads(raw_payload)
    symbols = payload.get("symbols", []) if isinstance(payload, dict) else []
    return sorted({
        item["symbol"].upper()
        for item in symbols
        if isinstance(item, dict)
        and item.get("status") == "TRADING"
        and item.get("contractType") == "PERPETUAL"
        and item.get("quoteAsset") == "USDT"
        and isinstance(item.get("symbol"), str)
    })


_run_job_lock = threading.Lock()
_run_job_state: dict[str, Any] | None = None
_run_history: list[StrategyScanHistory] = []


def start_strategy_run_job(
    store_instance: Any,
    selected_strategies: list[Strategy] | None = None,
    trigger_source: str = "manual",
) -> StrategyRunProgress:
    global _run_job_state
    with _run_job_lock:
        if _run_job_state and _run_job_state.get("running"):
            return _strategy_run_progress_from_state(_run_job_state)

        strategies = selected_strategies if selected_strategies is not None else [
            strategy
            for strategy in store_instance.strategies
            if _strategy_can_be_scheduled(strategy)
        ]
        _run_job_state = {
            "jobId": f"run-{uuid4().hex[:10]}",
            "running": True,
            "cancelRequested": False,
            "triggerSource": trigger_source,
            "startedAt": _now_iso(),
            "finishedAt": None,
            "currentStrategyName": "",
            "currentPeriod": None,
            "currentSymbol": "",
            "strategiesTotal": len(strategies),
            "strategiesChecked": 0,
            "totalSymbols": 0,
            "scannedSymbols": 0,
            "pendingSymbols": 0,
            "signalsCreated": 0,
            "skippedSymbols": 0,
            "errorsCount": 0,
            "elapsedSeconds": 0,
            "estimatedRemainingSeconds": 0,
            "scanSpeedPerSecond": 0,
            "errors": [],
            "skipped": [],
            "createdSignals": [],
            "_startedMonotonic": time.monotonic(),
        }
        thread = threading.Thread(target=_run_strategy_job_worker, args=(store_instance, strategies), daemon=True)
        thread.start()
        return _strategy_run_progress_from_state(_run_job_state)


def get_strategy_run_job() -> StrategyRunProgress:
    with _run_job_lock:
        if _run_job_state is None:
            return StrategyRunProgress(jobId="", running=False)
        _update_run_timing(_run_job_state)
        return _strategy_run_progress_from_state(_run_job_state)


def get_strategy_run_history(store_instance: Any, limit: int = 8) -> list[StrategyScanHistory]:
    if hasattr(store_instance, "get_strategy_run_history"):
        return store_instance.get_strategy_run_history(limit)
    with _run_job_lock:
        return list(_run_history[:limit])


def cancel_strategy_run_job() -> StrategyRunProgress:
    with _run_job_lock:
        if _run_job_state is not None and _run_job_state.get("running"):
            _run_job_state["cancelRequested"] = True
        return _strategy_run_progress_from_state(_run_job_state or {"jobId": "", "running": False})


def _run_strategy_job_worker(store_instance: Any, strategies: list[Strategy]) -> None:
    global _run_job_state
    try:
        market_snapshots = _latest_signal_by_symbol_and_period(store_instance.signals)
        symbols = fetch_tradable_symbols()
        if not symbols:
            symbols = sorted({symbol for (symbol, _period) in market_snapshots})
        _merge_run_state(totalSymbols=len(symbols) * len(strategies), pendingSymbols=len(symbols) * len(strategies))

        for strategy in strategies:
            if _is_run_cancel_requested():
                break
            strategy_created = 0
            strategy_errors: list[str] = []
            run_at = _now_iso()
            _merge_run_state(
                currentStrategyName=strategy.name,
                currentPeriod=strategy.period,
                strategiesChecked=(_run_job_state or {}).get("strategiesChecked", 0) + 1,
            )

            symbol_blacklist = set(_normalize_symbol_blacklist(strategy.symbolBlacklist))

            for symbol in symbols:
                if _is_run_cancel_requested():
                    break
                _merge_run_state(currentSymbol=symbol)
                if symbol.upper() in symbol_blacklist:
                    _append_run_skip(symbol, "币种黑名单", f"{symbol} 已加入该策略黑名单，跳过本次扫描")
                    _increment_scanned()
                    continue
                candles: list[Candle] = []
                price = 0.0
                try:
                    candles = fetch_market_candles(symbol, strategy.period)
                    _store_market_candles(store_instance, symbol, strategy.period, candles)
                    if len(candles) < CLOSED_KLINE_LIMIT:
                        _append_run_skip(symbol, "K线不足", f"需要 {CLOSED_KLINE_LIMIT} 根完整K线，实际 {len(candles)} 根")
                        _increment_scanned()
                        continue
                    if candles:
                        price = candles[-1].close
                except Exception as exc:
                    _append_run_error(symbol, "数据获取失败", str(exc))
                    strategy_errors.append(f"{strategy.name} / {symbol}: {exc}")
                    _increment_scanned()
                    continue

                try:
                    matched = _execute_strategy_code(strategy.runtime.code, candles)
                except Exception as exc:
                    _append_run_error(symbol, "计算异常", str(exc))
                    strategy_errors.append(f"{strategy.name} / {symbol}: {exc}")
                    _increment_scanned()
                    continue

                if matched:
                    signal = Signal(
                        id=f"sig-{uuid4().hex[:10]}",
                        symbol=symbol,
                        period=strategy.period,
                        strategyId=strategy.id,
                        strategyName=strategy.name,
                        signalType="strategy",
                        score=strategy.score,
                        triggeredAt=run_at,
                        price=candles[-1].close if candles else price,
                        summary=f"{symbol} 命中策略：{strategy.name}",
                        analysis=strategy.runtime.aiAnalysis or strategy.conditions,
                        strengthGrade="A",
                        candles=candles,
                    )
                    _store_upsert_front(store_instance, "signals", signal)
                    push_error = _send_signal_pushover_if_configured(store_instance, signal)
                    if push_error:
                        _append_run_error(symbol, "Pushover推送失败", push_error)
                        strategy_errors.append(f"{strategy.name} / {symbol}: Pushover push failed: {push_error}")
                    strategy_created += 1
                    with _run_job_lock:
                        if _run_job_state is not None:
                            _run_job_state["signalsCreated"] += 1
                            _run_job_state["createdSignals"].append(signal)
                _increment_scanned()

            updated = strategy.model_copy(
                update={
                    "todaySignalCount": strategy.todaySignalCount + strategy_created,
                    "lastTriggeredAt": run_at if strategy_created else strategy.lastTriggeredAt,
                    "schedule": strategy.schedule.model_copy(
                        update={
                            "lastRunAt": run_at,
                            "lastStatus": "error" if strategy_errors else "success",
                            "lastError": "\n".join(strategy_errors[:3]),
                        }
                    ),
                }
            )
            store_instance._upsert("strategies", updated, store_instance._order_for_id("strategies", strategy.id))
    finally:
        _merge_run_state(running=False, finishedAt=_now_iso(), currentSymbol="")
        _append_run_history(store_instance)


def _append_run_error(symbol: str, error_type: str, message: str) -> None:
    with _run_job_lock:
        if _run_job_state is None:
            return
        _run_job_state["errorsCount"] += 1
        _run_job_state["errors"].append(
            StrategyRunError(
                time=datetime.now().strftime("%H:%M:%S"),
                symbol=symbol,
                errorType=error_type,
                message=message,
            )
        )


def _append_run_skip(symbol: str, skip_type: str, message: str) -> None:
    with _run_job_lock:
        if _run_job_state is None:
            return
        _run_job_state["skippedSymbols"] += 1
        _run_job_state["skipped"].append(
            StrategyRunError(
                time=datetime.now().strftime("%H:%M:%S"),
                symbol=symbol,
                errorType=skip_type,
                message=message,
                impact="不参与本次判断",
            )
        )


def _increment_scanned() -> None:
    with _run_job_lock:
        if _run_job_state is None:
            return
        _run_job_state["scannedSymbols"] += 1
        _run_job_state["pendingSymbols"] = max(0, _run_job_state["totalSymbols"] - _run_job_state["scannedSymbols"])
        _update_run_timing(_run_job_state)


def _merge_run_state(**updates: Any) -> None:
    with _run_job_lock:
        if _run_job_state is None:
            return
        _run_job_state.update(updates)
        _update_run_timing(_run_job_state)


def _is_run_cancel_requested() -> bool:
    with _run_job_lock:
        return bool(_run_job_state and _run_job_state.get("cancelRequested"))


def _update_run_timing(state: dict[str, Any]) -> None:
    started = state.get("_startedMonotonic")
    if not started:
        return
    elapsed = max(0.0, time.monotonic() - started)
    scanned = int(state.get("scannedSymbols") or 0)
    total = int(state.get("totalSymbols") or 0)
    speed = scanned / elapsed if elapsed > 0 else 0
    state["elapsedSeconds"] = round(elapsed, 2)
    state["scanSpeedPerSecond"] = round(speed, 2)
    state["estimatedRemainingSeconds"] = round((total - scanned) / speed, 2) if speed > 0 and total > scanned else 0


def _strategy_run_progress_from_state(state: dict[str, Any]) -> StrategyRunProgress:
    payload = {key: value for key, value in state.items() if not key.startswith("_")}
    return StrategyRunProgress(**payload)


def _append_run_history(store_instance: Any) -> None:
    with _run_job_lock:
        if _run_job_state is None or not _run_job_state.get("jobId"):
            return
        status = "cancelled" if _run_job_state.get("cancelRequested") else "completed"
        item = StrategyScanHistory(
            id=str(_run_job_state["jobId"]),
            strategyName=str(_run_job_state.get("currentStrategyName") or "全策略扫描"),
            period=_run_job_state.get("currentPeriod"),
            triggerSource=_run_job_state.get("triggerSource") or "manual",
            status=status,
            startedAt=_run_job_state.get("startedAt"),
            finishedAt=_run_job_state.get("finishedAt"),
            elapsedSeconds=float(_run_job_state.get("elapsedSeconds") or 0),
            strategiesChecked=int(_run_job_state.get("strategiesChecked") or 0),
            totalSymbols=int(_run_job_state.get("totalSymbols") or 0),
            scannedSymbols=int(_run_job_state.get("scannedSymbols") or 0),
            signalsCreated=int(_run_job_state.get("signalsCreated") or 0),
            errorsCount=int(_run_job_state.get("errorsCount") or 0),
            skippedSymbols=int(_run_job_state.get("skippedSymbols") or 0),
        )
        if not _run_history or _run_history[0].id != item.id:
            _run_history.insert(0, item)
            del _run_history[12:]
    if hasattr(store_instance, "save_strategy_scan_history"):
        store_instance.save_strategy_scan_history(item)


def _strategy_can_be_scheduled(strategy: Strategy) -> bool:
    return bool(strategy.enabled and strategy.schedule.enabled and strategy.runtime.code.strip())


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _latest_period_boundary(period: str, now: datetime) -> datetime:
    normalized = _as_utc(now).replace(second=0, microsecond=0)
    if period == "4H":
        return normalized.replace(hour=(normalized.hour // 4) * 4, minute=0)
    if period == "1D":
        return normalized.replace(hour=0, minute=0)
    return normalized.replace(minute=0)


def _strategy_is_due(strategy: Strategy, now: datetime) -> bool:
    if not _strategy_can_be_scheduled(strategy):
        return False
    now_utc = _as_utc(now)
    boundary = _latest_period_boundary(strategy.period, now_utc)
    if now_utc - boundary > timedelta(seconds=SCHEDULER_BOUNDARY_GRACE_SECONDS):
        return False
    last_run = _parse_datetime(strategy.schedule.lastRunAt)
    if last_run is None:
        return True
    return _as_utc(last_run) < boundary


_scheduler_lock = threading.Lock()
_scheduler_stop_event: threading.Event | None = None
_scheduler_thread: threading.Thread | None = None
_scheduler_state: dict[str, Any] = {
    "running": False,
    "checkIntervalSeconds": 15,
    "lastCheckedAt": None,
    "lastTriggeredAt": None,
    "dueStrategies": 0,
    "lastError": "",
}


def run_strategy_scheduler_tick(store_instance: Any, now: datetime | None = None) -> int:
    check_time = now or datetime.now(timezone.utc)
    with _run_job_lock:
        run_busy = bool(_run_job_state and _run_job_state.get("running"))
    due_strategies = [
        strategy
        for strategy in store_instance.strategies
        if _strategy_is_due(strategy, check_time)
    ]
    with _scheduler_lock:
        _scheduler_state["lastCheckedAt"] = _now_iso()
        _scheduler_state["dueStrategies"] = len(due_strategies)
        _scheduler_state["lastError"] = ""

    if run_busy or not due_strategies:
        return 0

    start_strategy_run_job(store_instance, due_strategies, "scheduled")
    with _scheduler_lock:
        _scheduler_state["lastTriggeredAt"] = _now_iso()
    return len(due_strategies)


def start_strategy_scheduler(store_instance: Any, check_interval_seconds: int = 15) -> None:
    global _scheduler_stop_event, _scheduler_thread
    with _scheduler_lock:
        if _scheduler_thread is not None and _scheduler_thread.is_alive():
            return
        _scheduler_stop_event = threading.Event()
        _scheduler_state.update(
            {
                "running": True,
                "checkIntervalSeconds": check_interval_seconds,
                "lastError": "",
            }
        )
        _scheduler_thread = threading.Thread(
            target=_strategy_scheduler_loop,
            args=(store_instance, check_interval_seconds, _scheduler_stop_event),
            daemon=True,
        )
        _scheduler_thread.start()


def stop_strategy_scheduler() -> None:
    global _scheduler_stop_event, _scheduler_thread
    with _scheduler_lock:
        stop_event = _scheduler_stop_event
        thread = _scheduler_thread
        _scheduler_stop_event = None
        _scheduler_thread = None
        _scheduler_state["running"] = False
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


def get_strategy_scheduler_status() -> "StrategySchedulerStatus":
    from app.models import StrategySchedulerStatus

    with _scheduler_lock:
        return StrategySchedulerStatus(**_scheduler_state)


def _strategy_scheduler_loop(store_instance: Any, check_interval_seconds: int, stop_event: threading.Event) -> None:
    while not stop_event.wait(check_interval_seconds):
        try:
            run_strategy_scheduler_tick(store_instance)
        except Exception as exc:
            with _scheduler_lock:
                _scheduler_state["lastCheckedAt"] = _now_iso()
                _scheduler_state["lastError"] = str(exc)


def _normalize_symbol_blacklist(symbols: list[str] | None) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for symbol in symbols or []:
        value = str(symbol).strip().upper()
        if not value or value in seen:
            continue
        normalized.append(value)
        seen.add(value)
    return normalized


def fetch_market_candles(symbol: str, period: str, limit: int = CLOSED_KLINE_LIMIT) -> list[Candle]:
    interval_map = {"1H": "1h", "4H": "4h", "1D": "1d"}
    interval = interval_map.get(period)
    if interval is None:
        raise ValueError(f"Unsupported period: {period}")

    query = urllib.parse.urlencode({
        "symbol": symbol.upper(),
        "interval": interval,
        "limit": str(limit + 1),
    })
    url = f"https://fapi.binance.com/fapi/v1/klines?{query}"
    raw_payload = _read_url_with_retry(url, timeout=8)
    rows = json.loads(raw_payload)
    if not isinstance(rows, list):
        raise ValueError("Invalid Binance kline response")

    closed_rows = rows[:-1]
    candles = [
        Candle(
            time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc).isoformat(),
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
            ma5=0,
            ma20=0,
            ma60=0,
        )
        for row in closed_rows[-limit:]
        if isinstance(row, list) and len(row) >= 6
    ]
    _populate_moving_averages(candles)
    return candles


def _read_url_with_retry(url: str, timeout: int) -> str:
    last_error: Exception | None = None
    for attempt in range(2):
        try:
            with urllib.request.urlopen(url, timeout=timeout) as response:
                return response.read().decode("utf-8")
        except Exception as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.25)
                continue
    assert last_error is not None
    raise last_error


def _populate_moving_averages(candles: list[Candle]) -> None:
    closes = [candle.close for candle in candles]
    for index, candle in enumerate(candles):
        candle.ma5 = _rolling_average(closes, index, 5)
        candle.ma20 = _rolling_average(closes, index, 20)
        candle.ma60 = _rolling_average(closes, index, 60)


def _rolling_average(values: list[float], index: int, window: int) -> float:
    start = max(0, index - window + 1)
    subset = values[start:index + 1]
    return sum(subset) / len(subset)


def _execute_strategy_code(code: str, candles: list[Any], strict_return: bool = False) -> bool:
    namespace: dict[str, Any] = {
        "__builtins__": {
            "abs": abs,
            "all": all,
            "any": any,
            "bool": bool,
            "dict": dict,
            "enumerate": enumerate,
            "float": float,
            "getattr": getattr,
            "int": int,
            "isinstance": isinstance,
            "len": len,
            "list": list,
            "max": max,
            "min": min,
            "range": range,
            "round": round,
            "set": set,
            "slice": slice,
            "sorted": sorted,
            "str": str,
            "sum": sum,
            "tuple": tuple,
            "zip": zip,
        }
    }
    namespace.update({"Any": Any})
    exec(compile(code, "<strategy-runtime>", "exec"), namespace, namespace)
    check_signal = namespace.get("check_signal")
    if not callable(check_signal):
        raise ValueError("策略代码缺少 check_signal(candles) 函数")

    candle_payload = [candle.model_dump() if isinstance(candle, BaseModel) else candle for candle in candles]
    result = check_signal(candle_payload)
    if strict_return and not isinstance(result, bool):
        raise ValueError("check_signal(candles) 必须返回 bool 类型 True 或 False")
    return bool(result)


def _validate_strategy_payload(payload: CreateStrategyRequest | UpdateStrategyRequest) -> None:
    code = (payload.pythonCode or "").strip()
    if not code:
        return
    try:
        _execute_strategy_code(code, _strategy_validation_candles(price_breakout=True), strict_return=True)
    except Exception as exc:
        raise ValueError(f"策略代码无法执行：{exc}") from exc

    if _payload_requires_price_breakout(payload):
        matched_without_price_breakout = _execute_strategy_code(
            code,
            _strategy_validation_candles(price_breakout=False),
            strict_return=True,
        )
        if matched_without_price_breakout:
            raise ValueError("策略包含突破条件，但代码在价格未突破前高时仍会命中，请加入价格突破判断。")


def _payload_requires_price_breakout(payload: CreateStrategyRequest | UpdateStrategyRequest) -> bool:
    text = " ".join(payload.conditions)
    return "突破" in text or "前高" in text


def _strategy_validation_candles(price_breakout: bool) -> list[Candle]:
    candles: list[Candle] = []
    for index in range(CLOSED_KLINE_LIMIT):
        close = 1.08 + (index % 8) * 0.002
        high = close + 0.01
        if 191 <= index <= 238:
            high = 1.20
        if index == CLOSED_KLINE_LIMIT - 1:
            close = 1.23 if price_breakout else 1.15
            high = close + 0.01
        candles.append(
            Candle(
                time=f"2026-06-01T{index % 24:02d}:00:00+00:00",
                open=close - 0.003,
                high=high,
                low=1.00,
                close=close,
                volume=5000 if index == CLOSED_KLINE_LIMIT - 1 else 1000,
                ma5=1.03,
                ma20=1.03,
                ma60=1.02,
            )
        )
    return candles


def _store_upsert_front(store_instance: Any, table: str, item: BaseModel) -> None:
    store_instance._upsert(table, item, store_instance._next_front_order(table))


def _build_strategy_prompt(period: str, conditions: list[str]) -> str:
    condition_lines = "\n".join(f"{index + 1}. {condition}" for index, condition in enumerate(conditions))
    return f"""
你是 TrendAI 的加密货币量化策略生成助手。请根据用户输入的自然语言条件，生成一个用于“AI 生成策略”弹框预览的交易策略。

页面预览需要这些内容：
1. 策略总结：说明策略识别什么行情、为什么这些条件会形成信号、符合条件后可能出现什么机会。
2. 基础评分：给出 S/A/B/C 等级、0-100 分、信号类型，用于保存策略元数据。
3. 结构化条件：把用户的自然语言条件拆成可读的策略规则，每条包含标题、解释、可编辑参数标签。
4. Python 代码：生成可读、可执行、非占位的策略检查函数。
5. AI 分析：返回完整中文分析正文，不包含 Python 代码，不要写 Markdown 代码块。

生成要求：
- 只返回 JSON，不要 Markdown，不要代码块。
- 不要编造具体币种或实时价格。
- 语言使用简洁中文，适合直接展示在产品 UI。
- conditions 必须保留或等价改写用户输入的条件。
- structuredConditions 的数量应与用户输入条件数量一致。
- pythonCode 必须是完整 Python 代码字符串，不能是伪代码，不能只写 pass，不能只写 return True/False。
- pythonCode 必须包含 def check_signal(candles): 函数，返回 bool，并用 candles 的 high/low/close/volume/ma20 字段或 dict key 计算条件。
- pythonCode 必须包含：数据长度校验、近10根 K 线站上 MA20 比例、近10天/近10根区间振幅、最近一根成交量与过去24根均量倍数比较。
- pythonCode 可以包含小的辅助函数，例如 get_value、average，但不能依赖第三方库。
- aiAnalysis 是字符串数组，每一项是一段完整分析，内容可以包括策略逻辑、参数含义、适用场景、验证建议，但不要包含代码。
- 不要返回或编造历史胜率、盈亏比、平均持仓、风险等级、预期持仓周期、适用市场、触发流程等未经回测验证的数据。

用户选择周期：{period}
用户输入条件：
{condition_lines}

JSON 格式：
{{
  "name": "策略名称",
  "period": "{period}",
  "description": "一句话策略描述",
  "conditions": ["用于保存策略的条件1"],
  "signalType": "趋势启动类信号",
  "strengthGrade": "A",
  "score": 88,
  "summary": "两到三句话策略总结",
  "tags": ["趋势启动", "多头排列", "放量突破"],
  "structuredConditions": [
    {{"title": "箱体震荡", "description": "过去10天最高价/最低价比值 < 1.30，即振幅小于30%", "parameters": ["天数：10", "振幅：30%"]}}
  ],
  "pythonCode": "def get_value(candle, key):\\n    return candle.get(key) if isinstance(candle, dict) else getattr(candle, key)\\n\\ndef check_signal(candles):\\n    if len(candles) < 24:\\n        return False\\n    recent_10 = candles[-10:]\\n    recent_24 = candles[-24:]\\n    lows = [get_value(c, 'low') for c in recent_10]\\n    highs = [get_value(c, 'high') for c in recent_10]\\n    closes = [get_value(c, 'close') for c in recent_10]\\n    ma20_values = [get_value(c, 'ma20') for c in recent_10]\\n    volumes_24 = [get_value(c, 'volume') for c in recent_24]\\n    if any(v is None for v in lows + highs + closes + ma20_values + volumes_24):\\n        return False\\n    range_compressed = (max(highs) / min(lows)) < 1.30 if min(lows) > 0 else False\\n    above_ma20_count = sum(1 for close, ma20 in zip(closes, ma20_values) if close > ma20)\\n    trend_confirmed = above_ma20_count >= 8\\n    avg_volume_24 = sum(volumes_24[:-1]) / max(len(volumes_24[:-1]), 1)\\n    volume_breakout = volumes_24[-1] > avg_volume_24 * 3 if avg_volume_24 > 0 else False\\n    return range_compressed and trend_confirmed and volume_breakout",
  "aiAnalysis": ["该策略先过滤震荡蓄势结构，再等待趋势确认。箱体收敛用于减少无趋势噪音，均线条件用于确认价格处于偏强结构，放量突破用于判断资金是否正在推动价格离开整理区。", "参数需要结合具体标的的波动率验证。保存策略后建议先做历史回放和小样本观察，再决定是否启用实时信号检测。"]
}}
""".strip()


def _build_strategy_from_code_prompt(period: str, python_code: str) -> str:
    return f"""
You are a quantitative strategy product assistant. The user pasted Python strategy code.
Read the code and return ONLY a JSON object that describes the strategy for a UI preview.

Hard rules:
- Do not rewrite, optimize, repair, shorten, or reformat the pasted Python code.
- You may include a pythonCode field, but it will be ignored by the system.
- Focus on extracting metadata: name, description, conditions, structuredConditions, summary, tags, signalType, score, strengthGrade, aiAnalysis.
- conditions should be human-readable Chinese descriptions of what the code checks.
- structuredConditions should contain editable labels and parameters inferred from the code.
- If the code is unclear, say so in aiAnalysis instead of inventing backtest data.
- Do not invent win rate, profit/loss ratio, expected holding period, risk level, markets, or trigger flow unless they are explicit in the code.
- Return valid JSON only. No Markdown.

Selected period: {period}

Pasted Python code:
{python_code}

Expected JSON shape:
{{
  "name": "策略名称",
  "period": "{period}",
  "description": "一句话策略描述",
  "conditions": ["条件说明"],
  "signalType": "策略信号类型",
  "strengthGrade": "A",
  "score": 80,
  "summary": "两到三句策略总结",
  "tags": ["代码导入", "趋势", "量价"],
  "structuredConditions": [
    {{"title": "条件标题", "description": "条件解释", "parameters": ["参数：值"]}}
  ],
  "aiAnalysis": ["完整中文分析，说明代码逻辑、适用场景和需要验证的风险点"]
}}
""".strip()


def _fallback_conditions_from_code(python_code: str) -> list[str]:
    compact = python_code.lower()
    conditions: list[str] = []
    if "volume" in compact:
        conditions.append("成交量条件由粘贴代码计算")
    if "ma20" in compact or "ma" in compact:
        conditions.append("均线或趋势条件由粘贴代码计算")
    if "high" in compact and "low" in compact:
        conditions.append("价格区间或突破条件由粘贴代码计算")
    if not conditions:
        conditions.append("由粘贴代码的 check_signal(candles) 函数判断")
    return conditions


def _call_llm_for_strategy(prompt: str, llm_settings: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    base_url = str(llm_settings.get("baseUrl") or "").strip().rstrip("/")
    model = str(llm_settings.get("model") or "").strip()
    api_key = str(llm_settings.get("apiKey") or "").strip()
    if not base_url or not model or not api_key:
        return None, "大模型 API 配置不完整"

    try:
        import httpx

        response = httpx.post(
            f"{base_url}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": "你是严谨的量化策略产品助手，只输出可解析 JSON。"},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=90,
        )
        response.raise_for_status()
        content = response.json()["choices"][0]["message"]["content"]
        return _json_loads(_strip_json_fence(str(content))), ""
    except Exception as exc:
        return None, str(exc)


def _strip_json_fence(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


def _normalize_generated_strategy(
    payload: dict[str, Any],
    period: str,
    source_conditions: list[str],
    llm_settings: dict[str, Any],
) -> GeneratedStrategy:
    fallback = _fallback_generated_strategy(period, source_conditions)
    merged = fallback.model_dump()
    nested_fields = {"riskAdvice", "historyStats", "structuredConditions"}
    merged.update(
        {
            key: value
            for key, value in payload.items()
            if key not in nested_fields and value not in (None, "", [])
        }
    )
    merged["period"] = period
    merged["conditions"] = _string_list(merged.get("conditions")) or source_conditions
    merged["tags"] = _string_list(merged.get("tags")) or fallback.tags
    merged["riskAdvice"] = _merge_object_defaults(merged["riskAdvice"], payload.get("riskAdvice"))
    merged["historyStats"] = _merge_object_allow_null(merged["historyStats"], payload.get("historyStats"))
    merged["structuredConditions"] = _normalize_generated_conditions(
        payload.get("structuredConditions"),
        fallback.structuredConditions,
    )
    merged["generationSource"] = "llm"
    merged["generationProvider"] = str(llm_settings.get("provider") or "")
    merged["generationModel"] = str(llm_settings.get("model") or "")
    merged["generationBaseUrl"] = str(llm_settings.get("baseUrl") or "")
    merged["generationError"] = ""
    return GeneratedStrategy.model_validate(merged)


def _fallback_generated_strategy(
    period: str,
    conditions: list[str],
    llm_settings: dict[str, Any] | None = None,
    error: str = "",
) -> GeneratedStrategy:
    structured = [
        GeneratedStrategyCondition(
            title=_condition_title(condition, index),
            description=_condition_description(condition),
            parameters=_condition_parameters(condition, index),
        )
        for index, condition in enumerate(conditions)
    ]
    tags = _strategy_tags(conditions)
    signal_type = "趋势启动类信号" if any(_contains_any(condition, ["突破", "放量", "站上"]) for condition in conditions) else "条件共振类信号"
    description = "该策略用于识别整理后价格转强、量价条件共振的交易机会。"
    summary = (
        "该策略用于识别长期横盘整理后，价格站上关键均线并出现放量突破的趋势启动信号。"
        "符合条件的标的可能进入一波强势上涨行情。"
    )
    return GeneratedStrategy(
        name=f"{period} AI 趋势启动策略",
        period=period,
        description=description,
        conditions=conditions,
        signalType=signal_type,
        strengthGrade="A",
        score=88,
        summary=summary,
        tags=tags,
        structuredConditions=structured,
        riskAdvice=GeneratedStrategyRiskAdvice(stopLoss="跌回关键突破位下方", stopLossBuffer="3%"),
        nextStep="点击保存策略后，系统将为您创建策略文件并进入回测验证，验证通过后可启用实时信号检测。",
        signalDirection="做多",
        expectedHoldingPeriod="1~3天",
        riskLevel="中等",
        applicableMarkets=["现货", "合约", "主流币/山寨币"],
        triggerFlow=["前置条件满足", "趋势条件满足", "触发条件满足", "生成做多信号"],
        pythonCode=_fallback_python_code(conditions),
        aiAnalysis=[
            "该策略先识别横盘收敛和趋势线上方运行状态，避免在无方向波动中频繁触发。",
            "放量突破作为最后确认条件，用于判断资金是否参与并提高信号连续性。",
            "建议结合实际盘口流动性和回测结果调整阈值，不直接作为自动交易依据。",
        ],
        historyStats=GeneratedStrategyHistoryStats(winRate=68, profitLossRatio=2.18, averageHoldingHours=28),
        generationSource="fallback",
        generationProvider=str((llm_settings or {}).get("provider") or ""),
        generationModel=str((llm_settings or {}).get("model") or ""),
        generationBaseUrl=str((llm_settings or {}).get("baseUrl") or ""),
        generationError=error,
    )


def _merge_object_defaults(defaults: dict[str, Any], value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return defaults

    merged = dict(defaults)
    for key, item in value.items():
        if item not in (None, "", []):
            merged[key] = item
    return merged


def _merge_object_allow_null(defaults: dict[str, Any], value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return defaults

    merged = dict(defaults)
    for key, item in value.items():
        if item not in ("", []):
            merged[key] = item
    return merged


def _normalize_generated_conditions(
    value: Any,
    fallback_conditions: list[GeneratedStrategyCondition],
) -> list[dict[str, Any]]:
    fallback = [condition.model_dump() for condition in fallback_conditions]
    if not isinstance(value, list):
        return fallback

    normalized: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        fallback_item = fallback[index] if index < len(fallback) else {
            "title": "策略条件",
            "description": "",
            "parameters": [],
        }
        normalized.append(
            {
                "title": str(item.get("title") or fallback_item["title"]),
                "description": str(item.get("description") or fallback_item["description"]),
                "parameters": _string_list(item.get("parameters")) or fallback_item["parameters"],
            }
        )

    return normalized or fallback


def _fallback_python_code(conditions: list[str]) -> str:
    condition_comments = "\n".join(f"    # {index + 1}. {condition}" for index, condition in enumerate(conditions))
    return (
        "def get_value(candle, key):\n"
        "    if isinstance(candle, dict):\n"
        "        return candle.get(key)\n"
        "    return getattr(candle, key, None)\n\n"
        "def average(values):\n"
        "    valid = [value for value in values if value is not None]\n"
        "    return sum(valid) / len(valid) if valid else 0\n\n"
        "def check_signal(candles):\n"
        "    \"\"\"Return True when the generated TrendAI strategy is triggered.\"\"\"\n"
        f"{condition_comments}\n"
        "    if candles is None or len(candles) < 240:\n"
        "        return False\n"
        "    range_window = candles[-240:]\n"
        "    recent = candles[-10:]\n"
        "    volume_window = candles[-25:]\n"
        "    breakout_window = candles[-49:-1]\n"
        "    close_above_ma20 = sum(1 for c in recent if get_value(c, 'close') > get_value(c, 'ma20')) >= 8\n"
        "    volume_breakout = get_value(candles[-1], 'volume') > average([get_value(c, 'volume') for c in volume_window[:-1]]) * 3\n"
        "    range_compressed = max(get_value(c, 'high') for c in range_window) / min(get_value(c, 'low') for c in range_window) < 1.30\n"
        "    price_breakout = get_value(candles[-1], 'close') > max(get_value(c, 'high') for c in breakout_window)\n"
        "    return range_compressed and close_above_ma20 and volume_breakout and price_breakout\n"
    )


def _condition_title(condition: str, index: int) -> str:
    if _contains_any(condition, ["箱体", "振幅", "震荡", "横盘"]):
        return "箱体震荡"
    if _contains_any(condition, ["MA", "均线", "站上"]):
        return "多头排列"
    if _contains_any(condition, ["放量", "成交量", "量能"]):
        return "放量突破"
    return ["趋势条件", "结构条件", "确认条件"][index % 3]


def _condition_description(condition: str) -> str:
    if _contains_any(condition, ["振幅", "箱体", "震荡"]):
        return f"{condition}，用于过滤波动收敛后的蓄势结构"
    if _contains_any(condition, ["MA", "均线", "站上"]):
        return f"{condition}，用于确认价格已经回到中短期趋势线上方"
    if _contains_any(condition, ["放量", "成交量", "量能"]):
        return f"{condition}，用于确认突破时有资金参与"
    return condition


def _condition_parameters(condition: str, index: int) -> list[str]:
    if _contains_any(condition, ["振幅", "10天", "10 天"]):
        return ["天数：10", "振幅：30%"]
    if _contains_any(condition, ["MA20", "均线"]):
        return ["周期：MA20", "根数：10", "比例：80%"]
    if _contains_any(condition, ["放量", "成交量", "24"]):
        return ["突破周期：48", "均量周期：24", "倍数：3倍"]
    return [f"条件：{index + 1}"]


def _strategy_tags(conditions: list[str]) -> list[str]:
    tags: list[str] = []
    for condition in conditions:
        if _contains_any(condition, ["突破", "站上"]):
            tags.append("趋势启动")
        if _contains_any(condition, ["MA", "均线"]):
            tags.append("多头排列")
        if _contains_any(condition, ["放量", "成交量"]):
            tags.append("放量突破")
        if _contains_any(condition, ["震荡", "箱体", "振幅"]):
            tags.append("箱体整理")
    deduped = list(dict.fromkeys(tags))
    return (deduped or ["条件共振", "趋势观察"])[:4]


def _contains_any(value: str, keywords: list[str]) -> bool:
    normalized = value.lower()
    return any(keyword.lower() in normalized for keyword in keywords)


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _change_from_candles(candles) -> float | None:
    if len(candles) < 2 or candles[0].close == 0:
        return None
    return round(((candles[-1].close - candles[0].close) / candles[0].close) * 100, 2)


def _payload_text(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


def _json_dumps(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: str) -> dict[str, Any]:
    loaded = json.loads(value)
    return loaded if isinstance(loaded, dict) else {}


def _merge_settings(current: dict[str, Any], payload: AppSettingsUpdate) -> dict[str, Any]:
    llm_current = current.get("llm") if isinstance(current.get("llm"), dict) else {}
    if not llm_current and isinstance(current.get("api"), dict):
        llm_current = current["api"]
    pushover_current = current.get("pushover") if isinstance(current.get("pushover"), dict) else {}

    next_llm = {
        "provider": payload.llm.provider.strip() or "openai",
        "baseUrl": payload.llm.baseUrl.strip(),
        "model": payload.llm.model.strip(),
        "apiKey": payload.llm.apiKey or llm_current.get("apiKey", ""),
    }
    next_pushover = {
        "enabled": payload.pushover.enabled,
        "userKey": payload.pushover.userKey or pushover_current.get("userKey", ""),
        "appToken": payload.pushover.appToken or pushover_current.get("appToken", ""),
    }
    return {"llm": next_llm, "pushover": next_pushover}


def _settings_response(raw_settings: dict[str, Any]) -> AppSettingsResponse:
    llm = raw_settings.get("llm") if isinstance(raw_settings.get("llm"), dict) else {}
    if not llm and isinstance(raw_settings.get("api"), dict):
        llm = raw_settings["api"]
    pushover = raw_settings.get("pushover") if isinstance(raw_settings.get("pushover"), dict) else {}
    return AppSettingsResponse(
        llm=LlmSettingsResponse(
            provider=str(llm.get("provider") or "openai"),
            baseUrl=str(llm.get("baseUrl") or ""),
            model=str(llm.get("model") or ""),
            apiKeySet=bool(llm.get("apiKey")),
        ),
        pushover=PushoverSettingsResponse(
            enabled=bool(pushover.get("enabled")),
            userKeySet=bool(pushover.get("userKey")),
            appTokenSet=bool(pushover.get("appToken")),
        ),
    )


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 120_000)
    return "pbkdf2_sha256$120000$" + _b64(salt) + "$" + _b64(digest)


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        salt = _b64decode(salt_text)
        expected = _b64decode(digest_text)
    except (ValueError, TypeError):
        return False

    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations)
    return hmac.compare_digest(actual, expected)


def _make_token() -> str:
    return _b64(os.urandom(32))


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _mysql_connector():
    try:
        import mysql.connector
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "MySQL driver is not installed. Run `uv pip install -r requirements.txt` "
            "or install mysql-connector-python."
        ) from exc

    return mysql.connector


def _load_env_file() -> None:
    if not ENV_PATH.exists():
        return

    for raw_line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def _assert_mysql_reset_allowed(database: str) -> None:
    allow_reset = os.getenv("ALLOW_MYSQL_RESET", "").strip().lower()
    if allow_reset not in {"1", "true", "yes"}:
        raise RuntimeError(
            f"Refusing to reset MySQL database `{database}`. "
            "Set ALLOW_MYSQL_RESET=1 only for an intentional local reset."
        )


def create_store() -> Store:
    _load_env_file()
    driver = os.getenv("SIGNAL_DB_DRIVER", "sqlite").lower()
    if driver == "mysql":
        return MySQLStore()
    if driver == "sqlite":
        return SQLiteStore()
    raise RuntimeError(f"Unsupported SIGNAL_DB_DRIVER: {driver}")


store = create_store()
