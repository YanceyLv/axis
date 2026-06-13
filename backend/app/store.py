import os
import base64
import hashlib
import hmac
import inspect
import json
import logging
import re
import threading
import time
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol, TypeVar
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
    MarketKlineBackfillTask,
    MarketKlineBackfillRetryResponse,
    MarketKlineCoverage,
    MarketKlineFailedTask,
    MarketKlinePeriodProgress,
    MarketKlineRecentTask,
    MarketKlineRunningTask,
    MarketKlineStatusResponse,
    MarketKlineTaskCard,
    MarketRadarEnvironment,
    MarketRadarMetrics,
    MarketRadarSection,
    MarketRadarSectionItem,
    MarketRadarResponse,
    NewCoinListing,
    NewCoinScanResult,
    NewCoinSchedulerStatus,
    Signal,
    SignalPerformance,
    StrategyLesson,
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


ENV_PATH = Path(__file__).resolve().parents[1] / ".env"
CLOSED_KLINE_LIMIT = 240
INCREMENTAL_KLINE_LIMIT = 5
BACKFILL_PAGE_LIMIT = 1500
BACKFILL_MAX_PAIRS_PER_TICK = 20
BACKFILL_MAX_PAGES_PER_PAIR = 2
BACKFILL_REQUEST_SLEEP_SECONDS = 0
MARKET_KLINE_CLEANUP_BATCH_SIZE = 10000
MARKET_KLINE_COLLECTION_PERIODS = ("5M", "15M", "1H", "4H", "1D")
MARKET_KLINE_NATIVE_PERIODS = ("5M", "1D")
MARKET_KLINE_DERIVED_PERIODS = ("15M", "1H", "4H")
MARKET_KLINE_PRIORITY_SYMBOLS = ("BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT")
SCHEDULER_BOUNDARY_GRACE_SECONDS = 180
ModelT = TypeVar("ModelT", bound=BaseModel)
ENTITY_TABLES = (
    "strategies",
    "signals",
    "watch_items",
    "knowledge_cases",
    "strategy_scan_history",
    "signal_performance",
    "strategy_lessons",
    "market_kline_backfill_tasks",
)
USER_TABLE = "users"
SETTINGS_TABLE = "settings"
STRATEGY_GENERATION_CACHE_TABLE = "strategy_generation_cache"
MARKET_KLINE_TABLE = "market_klines"
MARKET_KLINE_COVERAGE_TABLE = "market_kline_coverage_snapshots"
MARKET_RADAR_SNAPSHOT_TABLE = "market_radar_snapshots"
MARKET_RADAR_SNAPSHOT_MAX_AGE_SECONDS = 600
NEW_COIN_LISTINGS_TABLE = "new_coin_listings"
SETTINGS_ID = "global"
logger = logging.getLogger("axis.strategy_generation")
new_coin_logger = logging.getLogger("axis.new_coin_detection")


class MarketKlineBackfillRetryError(Exception):
    def __init__(self, status_code: int, code: str, message: str, details: dict[str, str]) -> None:
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details


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

    def delete_old_signals(self, now: datetime | None = None, retention_days: int = 30) -> int: ...

    def upsert_market_candles(self, symbol: str, period: str, candles: list[Candle]) -> None: ...

    def delete_old_market_klines(
        self,
        now: datetime | None = None,
        batch_size: int = MARKET_KLINE_CLEANUP_BATCH_SIZE,
    ) -> dict[str, int]: ...

    def latest_market_candles(self, symbol: str, period: str, limit: int = CLOSED_KLINE_LIMIT) -> list[Candle]: ...

    def market_candles_for_symbol_period(self, symbol: str, period: str, limit: int | None = None) -> list[Candle]: ...

    def market_kline_status(self) -> MarketKlineStatusResponse: ...

    def retry_market_kline_backfill_task(self, symbol: str, period: str) -> MarketKlineBackfillRetryResponse: ...

    def market_kline_coverage_snapshot(self) -> list[MarketKlineCoverage]: ...

    def refresh_market_kline_coverage_snapshot(
        self, period: str, now: datetime | None = None
    ) -> MarketKlineCoverage: ...

    def market_radar_snapshot(self, period: str = "1H") -> MarketRadarResponse | None: ...

    def refresh_market_radar_snapshot(self, period: str = "1H", now: datetime | None = None) -> MarketRadarResponse: ...

    def market_radar(self) -> MarketRadarResponse: ...

    def market_candles_for_signal(self, signal: Signal, limit: int = CLOSED_KLINE_LIMIT) -> list[Candle]: ...

    @property
    def market_kline_backfill_tasks(self) -> list[MarketKlineBackfillTask]: ...

    def upsert_market_kline_backfill_task(self, task: MarketKlineBackfillTask) -> None: ...

    def market_kline_time_range(self, symbol: str, period: str) -> tuple[datetime | None, datetime | None]: ...

    def performance_for_signal(self, signal_id: str) -> SignalPerformance | None: ...

    def upsert_signal_performance(self, performance: SignalPerformance) -> None: ...

    def lessons_for_strategy(self, strategy_id: str, limit: int = 10) -> list[StrategyLesson]: ...

    def create_strategy_lesson(self, lesson: StrategyLesson) -> StrategyLesson: ...

    @property
    def new_coin_listings(self) -> list[NewCoinListing]: ...

    def scan_new_coin_listings(self) -> NewCoinScanResult: ...

    def create_watch_item(self, payload: CreateWatchItemRequest) -> WatchItem: ...

    def delete_watch_item(self, watch_item_id: str) -> bool | None: ...

    def create_user(self, email: str, password: str) -> tuple[AuthUser, str]: ...

    def authenticate_user(self, email: str, password: str) -> tuple[AuthUser, str] | None: ...

    def user_for_token(self, token: str) -> AuthUser | None: ...

    def get_settings(self) -> AppSettingsResponse: ...

    def update_settings(self, payload: AppSettingsUpdate) -> AppSettingsResponse: ...



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
            cursor.execute(f"DELETE FROM `{MARKET_KLINE_COVERAGE_TABLE}`")
            cursor.execute(f"DELETE FROM `{MARKET_RADAR_SNAPSHOT_TABLE}`")
            cursor.execute(f"DELETE FROM `{USER_TABLE}`")
            cursor.execute(f"DELETE FROM `{SETTINGS_TABLE}`")
            cursor.execute(f"DELETE FROM `{STRATEGY_GENERATION_CACHE_TABLE}`")
            cursor.execute(f"DELETE FROM `{NEW_COIN_LISTINGS_TABLE}`")
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

    @property
    def new_coin_listings(self) -> list[NewCoinListing]:
        return self._list(NEW_COIN_LISTINGS_TABLE, NewCoinListing)

    @property
    def market_kline_backfill_tasks(self) -> list[MarketKlineBackfillTask]:
        return self._list("market_kline_backfill_tasks", MarketKlineBackfillTask)

    def market_kline_coverage_snapshot(self) -> list[MarketKlineCoverage]:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(f"SELECT payload FROM `{MARKET_KLINE_COVERAGE_TABLE}`")
            rows = cursor.fetchall()
        return [MarketKlineCoverage.model_validate_json(_payload_text(row[0])) for row in rows]

    def market_radar_snapshot(self, period: str = "1H") -> MarketRadarResponse | None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"SELECT payload FROM `{MARKET_RADAR_SNAPSHOT_TABLE}` WHERE period = %s",
                (str(period).upper(),),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return _load_market_radar_snapshot_payload(_payload_text(row[0]))

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

    def scan_new_coin_listings(self) -> NewCoinScanResult:
        return _scan_new_coin_listings(self)

    def get_strategy_run_history(self, limit: int = 8) -> list[StrategyScanHistory]:
        return self._list("strategy_scan_history", StrategyScanHistory)[:limit]

    def save_strategy_scan_history(self, item: StrategyScanHistory) -> None:
        self._upsert("strategy_scan_history", item, self._next_front_order("strategy_scan_history"))

    def delete_old_signals(self, now: datetime | None = None, retention_days: int = 30) -> int:
        cutoff = _as_utc(now or datetime.now(timezone.utc)) - timedelta(days=retention_days)
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute("SELECT id, payload, created_at FROM `signals`")
            rows = cursor.fetchall()
            old_signal_ids = [
                row[0]
                for row in rows
                if _signal_row_is_older_than_cutoff(_payload_text(row[1]), row[2], cutoff)
            ]
            if old_signal_ids:
                cursor.executemany("DELETE FROM `signals` WHERE id = %s", [(signal_id,) for signal_id in old_signal_ids])
                connection.commit()
        return len(old_signal_ids)

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

    def delete_watch_item(self, watch_item_id: str) -> bool | None:
        watch_item = self._get("watch_items", watch_item_id, WatchItem)
        if watch_item is None:
            return None

        self._delete("watch_items", watch_item_id)
        return True

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
            _ensure_mysql_index(
                cursor,
                MARKET_KLINE_TABLE,
                "idx_market_klines_period_open_time",
                f"CREATE INDEX idx_market_klines_period_open_time ON `{MARKET_KLINE_TABLE}` (period, open_time)",
            )
            _ensure_mysql_index(
                cursor,
                MARKET_KLINE_TABLE,
                "idx_market_klines_period_symbol",
                f"CREATE INDEX idx_market_klines_period_symbol ON `{MARKET_KLINE_TABLE}` (period, symbol)",
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{MARKET_KLINE_COVERAGE_TABLE}` (
                    period VARCHAR(8) PRIMARY KEY,
                    payload JSON NOT NULL,
                    updated_at VARCHAR(40) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{MARKET_RADAR_SNAPSHOT_TABLE}` (
                    period VARCHAR(8) PRIMARY KEY,
                    payload JSON NOT NULL,
                    updated_at VARCHAR(40) NOT NULL
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
                """
            )
            cursor.execute(
                f"""
                CREATE TABLE IF NOT EXISTS `{NEW_COIN_LISTINGS_TABLE}` (
                    id VARCHAR(128) PRIMARY KEY,
                    sort_order INT NOT NULL,
                    payload JSON NOT NULL,
                    created_at VARCHAR(40) NOT NULL,
                    updated_at VARCHAR(40) NOT NULL,
                    INDEX idx_new_coin_listings_sort_order (sort_order),
                    INDEX idx_new_coin_listings_created_at (created_at)
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
        ids = [_market_kline_id(normalized_symbol, normalized_period, candle.time) for candle in candles]
        existing_ids: set[str] = set()
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT 1 FROM `{MARKET_KLINE_TABLE}`
                WHERE symbol = %s AND period = %s
                LIMIT 1
                """,
                (normalized_symbol, normalized_period),
            )
            symbol_exists = cursor.fetchone() is not None
            for chunk in _chunks(ids, 500):
                placeholders = ",".join(["%s"] * len(chunk))
                cursor.execute(f"SELECT id FROM `{MARKET_KLINE_TABLE}` WHERE id IN ({placeholders})", tuple(chunk))
                existing_ids.update(str(row[0]) for row in cursor.fetchall())
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
            connection.commit()
        self._apply_market_kline_coverage_delta(
            normalized_period,
            len(set(ids) - existing_ids),
            0 if symbol_exists else 1,
            [candle.time for candle in candles],
        )
        if normalized_period == "5M":
            self._refresh_derived_market_klines(normalized_symbol, candles)

    def _refresh_derived_market_klines(self, symbol: str, source_candles: list[Candle]) -> None:
        source_times = [_parse_datetime(candle.time) for candle in source_candles]
        parsed_times = [_as_utc(value) for value in source_times if value is not None]
        if not parsed_times:
            return

        window_start = _floor_datetime_to_period(min(parsed_times), "4H")
        window_end = _floor_datetime_to_period(max(parsed_times), "4H") + timedelta(seconds=_period_seconds("4H"))
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT payload FROM `{MARKET_KLINE_TABLE}`
                WHERE symbol = %s AND period = %s AND open_time >= %s AND open_time < %s
                ORDER BY open_time ASC
                """,
                (symbol.upper(), "5M", window_start.isoformat(), window_end.isoformat()),
            )
            rows = cursor.fetchall()

        five_minute_candles = [MarketKline.model_validate_json(_payload_text(row[0])).candle for row in rows]
        for derived_period in MARKET_KLINE_DERIVED_PERIODS:
            derived_candles = _aggregate_market_candles(five_minute_candles, derived_period)
            if derived_candles:
                self.upsert_market_candles(symbol, derived_period, derived_candles)

    def refresh_market_kline_coverage_snapshot(
        self, period: str, now: datetime | None = None
    ) -> MarketKlineCoverage:
        snapshot = self._scan_market_kline_coverage(str(period).upper(), now)
        self._upsert_market_kline_coverage_snapshot(snapshot)
        return snapshot

    def _scan_market_kline_coverage(self, period: str, now: datetime | None = None) -> MarketKlineCoverage:
        normalized_period = str(period).upper()
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT COUNT(*) AS rows_count, COUNT(DISTINCT symbol) AS symbols_count,
                       MIN(open_time) AS earliest_open, MAX(open_time) AS latest_open
                FROM `{MARKET_KLINE_TABLE}`
                WHERE period = %s
                """,
                (normalized_period,),
            )
            row = cursor.fetchone()
        rows_count, symbols_count, earliest_open, latest_open = row if row else (0, 0, None, None)
        row_count = int(rows_count or 0)
        return MarketKlineCoverage(
            period=normalized_period,  # type: ignore[arg-type]
            rows=row_count,
            symbols=int(symbols_count or 0),
            targetWindow=_market_kline_target_window_label(normalized_period),
            earliestOpenTime=str(earliest_open) if earliest_open else _market_kline_retention_cutoffs(now).get(normalized_period),
            latestOpenTime=str(latest_open) if latest_open else None,
            status="normal" if row_count > 0 else "empty",
            statusLabel="正常" if row_count > 0 else "暂无数据",
        )

    def _upsert_market_kline_coverage_snapshot(self, snapshot: MarketKlineCoverage) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                INSERT INTO `{MARKET_KLINE_COVERAGE_TABLE}` (period, payload, updated_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    payload = VALUES(payload),
                    updated_at = VALUES(updated_at)
                """,
                (snapshot.period, snapshot.model_dump_json(), _now_iso()),
            )
            connection.commit()

    def _apply_market_kline_coverage_delta(
        self,
        period: str,
        rows_delta: int,
        symbols_delta: int,
        open_times: list[str],
    ) -> None:
        normalized_period = str(period).upper()
        existing = {item.period: item for item in self.market_kline_coverage_snapshot()}.get(normalized_period)
        parsed_times = []
        for item in open_times:
            parsed = _parse_datetime(item)
            if parsed is not None:
                parsed_times.append(_as_utc(parsed))
        earliest = min(parsed_times).isoformat() if parsed_times else existing.earliestOpenTime if existing else None
        latest = max(parsed_times).isoformat() if parsed_times else existing.latestOpenTime if existing else None
        if existing:
            if existing.earliestOpenTime and earliest:
                existing_earliest = _as_utc(_parse_datetime(existing.earliestOpenTime))
                new_earliest = _as_utc(_parse_datetime(earliest))
                if existing_earliest is not None and new_earliest is not None:
                    earliest = min(existing_earliest, new_earliest).isoformat()
            if existing.latestOpenTime and latest:
                existing_latest = _as_utc(_parse_datetime(existing.latestOpenTime))
                new_latest = _as_utc(_parse_datetime(latest))
                if existing_latest is not None and new_latest is not None:
                    latest = max(existing_latest, new_latest).isoformat()
        row_count = max(0, (existing.rows if existing else 0) + max(0, rows_delta))
        symbol_count = max(0, (existing.symbols if existing else 0) + max(0, symbols_delta))
        snapshot = MarketKlineCoverage(
            period=normalized_period,  # type: ignore[arg-type]
            rows=row_count,
            symbols=symbol_count,
            targetWindow=_market_kline_target_window_label(normalized_period),
            earliestOpenTime=earliest,
            latestOpenTime=latest,
            status="normal" if row_count > 0 else "empty",
            statusLabel="正常" if row_count > 0 else "暂无数据",
        )
        self._upsert_market_kline_coverage_snapshot(snapshot)

    def delete_old_market_klines(
        self,
        now: datetime | None = None,
        batch_size: int = MARKET_KLINE_CLEANUP_BATCH_SIZE,
    ) -> dict[str, int]:
        limit = max(1, int(batch_size))
        deleted: dict[str, int] = {}
        with self._connect() as connection:
            cursor = connection.cursor()
            for period, cutoff in _market_kline_retention_cutoffs(now).items():
                cursor.execute(
                    f"""
                    DELETE FROM `{MARKET_KLINE_TABLE}`
                    WHERE period = %s AND open_time < %s
                    ORDER BY open_time ASC
                    LIMIT %s
                    """,
                    (period, cutoff, limit),
                )
                deleted[period] = int(cursor.rowcount or 0)
            connection.commit()
        for period, deleted_count in deleted.items():
            if deleted_count > 0:
                self.refresh_market_kline_coverage_snapshot(period, now)
        return deleted

    def latest_market_candles(self, symbol: str, period: str, limit: int = CLOSED_KLINE_LIMIT) -> list[Candle]:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT payload FROM `{MARKET_KLINE_TABLE}`
                WHERE symbol = %s AND period = %s
                ORDER BY open_time DESC
                LIMIT %s
                """,
                (symbol.upper(), str(period).upper(), limit),
            )
            rows = cursor.fetchall()

        return [MarketKline.model_validate_json(_payload_text(row[0])).candle for row in reversed(rows)]

    def market_candles_for_symbol_period(self, symbol: str, period: str, limit: int | None = None) -> list[Candle]:
        normalized_symbol = symbol.upper()
        normalized_period = str(period).upper()
        with self._connect() as connection:
            cursor = connection.cursor()
            if limit is not None and limit > 0:
                cursor.execute(
                    f"""
                    SELECT payload FROM `{MARKET_KLINE_TABLE}`
                    WHERE symbol = %s AND period = %s
                    ORDER BY open_time DESC
                    LIMIT %s
                    """,
                    (normalized_symbol, normalized_period, int(limit)),
                )
            else:
                cursor.execute(
                    f"""
                    SELECT payload FROM `{MARKET_KLINE_TABLE}`
                    WHERE symbol = %s AND period = %s
                    ORDER BY open_time ASC
                    """,
                    (normalized_symbol, normalized_period),
                )
            rows = cursor.fetchall()

        candles = [MarketKline.model_validate_json(_payload_text(row[0])).candle for row in rows]
        ordered = list(reversed(candles)) if limit is not None and limit > 0 else candles
        if normalized_period in MARKET_KLINE_DERIVED_PERIODS:
            ordered = self._with_live_derived_market_candle(normalized_symbol, normalized_period, ordered)
        if limit is not None and limit > 0:
            return ordered[-int(limit):]
        return ordered

    def _with_live_derived_market_candle(self, symbol: str, period: str, candles: list[Candle]) -> list[Candle]:
        expected_count = _period_seconds(period) // _period_seconds("5M")
        if expected_count <= 1:
            return candles

        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT payload FROM `{MARKET_KLINE_TABLE}`
                WHERE symbol = %s AND period = %s
                ORDER BY open_time DESC
                LIMIT %s
                """,
                (symbol, "5M", int(expected_count)),
            )
            rows = cursor.fetchall()

        recent_five_minute = [
            MarketKline.model_validate_json(_payload_text(row[0])).candle
            for row in reversed(rows)
        ]
        if not recent_five_minute:
            return candles

        latest_time = _parse_datetime(recent_five_minute[-1].time)
        if latest_time is None:
            return candles

        bucket_start = _floor_datetime_to_period(latest_time, period)
        bucket_candles = [
            candle
            for candle in recent_five_minute
            if (_parse_datetime(candle.time) or datetime.min.replace(tzinfo=timezone.utc)) >= bucket_start
        ]
        if not bucket_candles:
            return candles

        live_candle = Candle(
            time=bucket_start.isoformat(),
            open=bucket_candles[0].open,
            high=max(candle.high for candle in bucket_candles),
            low=min(candle.low for candle in bucket_candles),
            close=bucket_candles[-1].close,
            volume=sum(candle.volume for candle in bucket_candles),
            ma5=0,
            ma20=0,
            ma60=0,
        )

        merged = list(candles)
        if merged:
            latest_stored_time = _parse_datetime(merged[-1].time)
            if latest_stored_time is not None and _floor_datetime_to_period(latest_stored_time, period) == bucket_start:
                merged[-1] = live_candle
            elif latest_stored_time is None or bucket_start > latest_stored_time:
                merged.append(live_candle)
        else:
            merged.append(live_candle)

        _populate_moving_averages(merged)
        return merged

    def market_kline_status(self) -> MarketKlineStatusResponse:
        now = datetime.now(timezone.utc)
        updated_at = _now_iso()
        tasks = self.market_kline_backfill_tasks
        status_counts = Counter(task.status for task in tasks)
        total_tasks = len(tasks)
        completed_tasks = status_counts.get("completed", 0)
        failed_tasks = status_counts.get("failed", 0)
        running_tasks_count = status_counts.get("running", 0)
        pending_tasks = status_counts.get("pending", 0)
        progress_percent = round((completed_tasks / total_tasks) * 100, 1) if total_tasks else 100.0
        stored_total = sum(task.storedCandles for task in tasks)

        with _market_kline_backfill_lock:
            backfill_state = dict(_market_kline_backfill_state)
        with _market_kline_collection_lock:
            collection_state = dict(_market_kline_collection_state)
        with _market_kline_cleanup_lock:
            cleanup_state = dict(_market_kline_cleanup_state)

        period_progress = _market_kline_period_progress(tasks)
        coverage = self._market_kline_coverage(now)
        running_tasks = [
            MarketKlineRunningTask(
                symbol=task.symbol,
                period=task.period,
                pagesFetched=task.pagesFetched,
                storedCandles=task.storedCandles,
                nextStart=task.nextStart,
                targetEnd=task.targetEnd,
                updatedAt=task.updatedAt,
                lastError=task.lastError,
            )
            for task in sorted(
                [task for task in tasks if task.status == "running"],
                key=lambda item: (item.updatedAt, item.symbol, item.period),
                reverse=True,
            )[:8]
        ]
        failed_task_items = [
            MarketKlineFailedTask(
                symbol=task.symbol,
                period=task.period,
                pagesFetched=task.pagesFetched,
                storedCandles=task.storedCandles,
                nextStart=task.nextStart,
                targetEnd=task.targetEnd,
                updatedAt=task.updatedAt,
                lastError=task.lastError,
            )
            for task in sorted(
                [task for task in tasks if task.status == "failed"],
                key=lambda item: (item.updatedAt, item.symbol, item.period),
                reverse=True,
            )[:8]
        ]
        recent_tasks = _market_kline_recent_tasks(tasks, collection_state, cleanup_state)
        risks = _market_kline_status_risks(
            failed_tasks,
            pending_tasks,
            running_tasks_count,
            collection_state,
            cleanup_state,
        )

        backfill_running = bool(backfill_state.get("backfilling")) or running_tasks_count > 0 or pending_tasks > 0
        collection_running = bool(collection_state.get("collecting"))
        cleanup_running = bool(cleanup_state.get("cleaning"))
        if failed_tasks:
            overall_status: Literal["running", "waiting", "completed", "warning"] = "warning"
            overall_label = "有异常"
        elif cleanup_running or collection_running or backfill_running:
            overall_status = "running"
            overall_label = "运行中"
        elif total_tasks and completed_tasks == total_tasks:
            overall_status = "completed"
            overall_label = "已完成"
        else:
            overall_status = "waiting"
            overall_label = "等待中"

        if cleanup_running:
            active_phase = "数据清理"
        elif collection_running:
            active_phase = "增量更新"
        elif backfill_running:
            active_phase = "历史补齐"
        else:
            active_phase = "空闲"

        cards = [
            MarketKlineTaskCard(
                name="K线历史补齐",
                status="warning" if failed_tasks else ("running" if backfill_running else "completed"),
                statusLabel="有异常" if failed_tasks else ("运行中" if backfill_running else "已完成"),
                phase="历史窗口补齐",
                progressCurrent=completed_tasks,
                progressTotal=total_tasks,
                progressPercent=progress_percent,
                primaryMetric=f"已写入 {stored_total:,} 根",
                secondaryMetric=f"当前 {running_tasks_count} 个任务 / 失败 {failed_tasks}",
                lastRunAt=backfill_state.get("lastTriggeredAt"),
                lastError=str(backfill_state.get("lastError") or ""),
            ),
            MarketKlineTaskCard(
                name="K线增量更新",
                status="running" if collection_running else ("warning" if collection_state.get("lastError") else "completed"),
                statusLabel="运行中" if collection_running else ("有异常" if collection_state.get("lastError") else "最近完成"),
                phase="周期追新",
                primaryMetric=f"写入 {int(collection_state.get('lastStoredCandles') or 0):,} 根",
                secondaryMetric=f"跳过 {int(collection_state.get('lastSkippedPairs') or 0):,} 个组合",
                lastRunAt=collection_state.get("lastTriggeredAt"),
                lastError=str(collection_state.get("lastError") or ""),
            ),
            MarketKlineTaskCard(
                name="K线数据清理",
                status="running" if cleanup_running else ("warning" if cleanup_state.get("lastError") else "waiting"),
                statusLabel="清理中" if cleanup_running else ("有异常" if cleanup_state.get("lastError") else "等待中"),
                phase="保留窗口清理",
                primaryMetric=f"删除 {int(cleanup_state.get('lastDeletedCandles') or 0):,} 根",
                secondaryMetric=f"最近日期 {cleanup_state.get('lastCleanupDate') or '--'}",
                lastRunAt=cleanup_state.get("lastTriggeredAt"),
                lastError=str(cleanup_state.get("lastError") or ""),
            ),
        ]

        return MarketKlineStatusResponse(
            updatedAt=updated_at,
            overallStatus=overall_status,
            overallStatusLabel=overall_label,
            activePhase=active_phase,
            cards=cards,
            periodProgress=period_progress,
            coverage=coverage,
            runningTasks=running_tasks,
            failedTasks=failed_task_items,
            recentTasks=recent_tasks,
            risks=risks,
        )

    def retry_market_kline_backfill_task(self, symbol: str, period: str) -> MarketKlineBackfillRetryResponse:
        symbol_key = str(symbol).upper()
        period_key = str(period).upper()
        with _market_kline_cleanup_lock:
            if _market_kline_cleanup_state.get("cleaning"):
                raise MarketKlineBackfillRetryError(
                    status_code=409,
                    code="MARKET_KLINE_CLEANUP_RUNNING",
                    message="Market kline cleanup is running",
                    details={"symbol": symbol_key, "period": period_key},
                )
            _begin_market_kline_backfill_execution(symbol_key, period_key)

        task = next(
            (
                item
                for item in self.market_kline_backfill_tasks
                if item.symbol.upper() == symbol_key and item.period.upper() == period_key
            ),
            None,
        )
        if task is None:
            _finish_market_kline_backfill_execution()
            raise MarketKlineBackfillRetryError(
                status_code=404,
                code="MARKET_KLINE_BACKFILL_TASK_NOT_FOUND",
                message="Market kline backfill task not found",
                details={"symbol": symbol_key, "period": period_key},
            )
        if task.status != "failed":
            _finish_market_kline_backfill_execution()
            raise MarketKlineBackfillRetryError(
                status_code=409,
                code="MARKET_KLINE_BACKFILL_TASK_NOT_RETRYABLE",
                message="Market kline backfill task is not retryable",
                details={"symbol": symbol_key, "period": period_key, "status": task.status},
            )

        claimed_task = _claim_market_kline_backfill_task(
            self,
            task.id,
            expected_statuses={"failed"},
        )
        if claimed_task is None:
            _finish_market_kline_backfill_execution()
            latest_task = next(
                (
                    item
                    for item in self.market_kline_backfill_tasks
                    if item.symbol.upper() == symbol_key and item.period.upper() == period_key
                ),
                None,
            )
            status = latest_task.status if latest_task is not None else "missing"
            raise MarketKlineBackfillRetryError(
                status_code=409,
                code="MARKET_KLINE_BACKFILL_TASK_NOT_RETRYABLE",
                message="Market kline backfill task is not retryable",
                details={"symbol": symbol_key, "period": period_key, "status": status},
            )

        try:
            updated_task, task_stored = _advance_market_kline_backfill_task(
                self,
                claimed_task,
                max_pages=1,
            )
            self.upsert_market_kline_backfill_task(updated_task)
            with _market_kline_backfill_lock:
                _market_kline_backfill_state["lastTriggeredAt"] = _now_iso()
                _market_kline_backfill_state["storedCandles"] = task_stored
                _market_kline_backfill_state["completedPairs"] = sum(
                    1 for item in self.market_kline_backfill_tasks if item.status == "completed"
                )
                _market_kline_backfill_state["totalPairs"] = len(self.market_kline_backfill_tasks)
            return MarketKlineBackfillRetryResponse(
                symbol=updated_task.symbol,
                period=updated_task.period,
                status=updated_task.status,
                statusLabel=_market_kline_backfill_task_status_label(updated_task.status),
                storedCandles=updated_task.storedCandles,
                pagesFetched=updated_task.pagesFetched,
                message="已在当前请求内同步执行一轮历史补齐",
                updatedAt=updated_task.updatedAt,
            )
        except Exception as exc:
            failed_task = claimed_task.model_copy(
                update={"status": "failed", "lastError": str(exc), "updatedAt": _now_iso()}
            )
            self.upsert_market_kline_backfill_task(failed_task)
            with _market_kline_backfill_lock:
                _market_kline_backfill_state["lastError"] = str(exc)
            raise MarketKlineBackfillRetryError(
                status_code=500,
                code="MARKET_KLINE_BACKFILL_RETRY_FAILED",
                message=f"Market kline backfill retry failed: {exc}",
                details={"symbol": symbol_key, "period": period_key},
            ) from exc
        finally:
            _release_market_kline_backfill_task_claim(task.id)
            _finish_market_kline_backfill_execution()

    def _market_kline_coverage(self, now: datetime) -> list[MarketKlineCoverage]:
        snapshots = {item.period: item for item in self.market_kline_coverage_snapshot()}
        cutoffs = _market_kline_retention_cutoffs(now)
        coverage: list[MarketKlineCoverage] = []
        for period in MARKET_KLINE_COLLECTION_PERIODS:
            item = snapshots.get(period)
            if item is not None:
                coverage.append(item.model_copy(update={"targetWindow": _market_kline_target_window_label(period)}))
                continue
            coverage.append(
                MarketKlineCoverage(
                    period=period,  # type: ignore[arg-type]
                    rows=0,
                    symbols=0,
                    targetWindow=_market_kline_target_window_label(period),
                    earliestOpenTime=cutoffs.get(period),
                    latestOpenTime=None,
                    status="empty",
                    statusLabel="暂无快照",
                )
            )
        return coverage

    def refresh_market_radar_snapshot(self, period: str = "1H", now: datetime | None = None) -> MarketRadarResponse:
        normalized_period = str(period).upper()
        ticker_24h = self._fetch_market_radar_ticker_24h()
        snapshots = self._market_radar_snapshots(normalized_period, limit=90)
        snapshot = _build_market_radar(snapshots, ticker_24h, now)
        self._upsert_market_radar_snapshot(normalized_period, snapshot)
        return snapshot

    def market_radar(self) -> MarketRadarResponse:
        snapshot = self.market_radar_snapshot("1H")
        if snapshot is None:
            return _empty_market_radar_response()
        return snapshot

    def _market_radar_snapshots(self, period: str, limit: int = 90) -> dict[str, list[Candle]]:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT symbol, payload FROM (
                    SELECT
                        symbol,
                        payload,
                        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY open_time DESC) AS row_num
                    FROM `{MARKET_KLINE_TABLE}`
                    WHERE period = %s
                ) ranked
                WHERE row_num <= %s
                ORDER BY symbol ASC, row_num DESC
                """,
                (str(period).upper(), limit),
            )
            rows = cursor.fetchall()

        snapshots: dict[str, list[Candle]] = {}
        for symbol, payload in rows:
            snapshots.setdefault(str(symbol).upper(), []).append(MarketKline.model_validate_json(_payload_text(payload)).candle)
        return {symbol: candles for symbol, candles in snapshots.items() if len(candles) >= 73}

    def _fetch_market_radar_ticker_24h(self) -> dict[str, dict[str, float]]:
        try:
            payload = json.loads(_read_url_with_retry("https://fapi.binance.com/fapi/v1/ticker/24hr", timeout=8))
        except Exception as exc:
            logging.getLogger(__name__).warning("market radar ticker 24h fetch failed: %s", exc)
            return {}
        if not isinstance(payload, list):
            return {}
        tickers: dict[str, dict[str, float]] = {}
        for row in payload:
            if not isinstance(row, dict):
                continue
            symbol = str(row.get("symbol") or "").upper()
            if not symbol:
                continue
            try:
                tickers[symbol] = {
                    "quoteVolume": float(row.get("quoteVolume") or 0.0),
                    "volume": float(row.get("volume") or 0.0),
                }
            except (TypeError, ValueError):
                continue
        return tickers

    def _upsert_market_radar_snapshot(self, period: str, snapshot: MarketRadarResponse) -> None:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                INSERT INTO `{MARKET_RADAR_SNAPSHOT_TABLE}` (period, payload, updated_at)
                VALUES (%s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    payload = VALUES(payload),
                    updated_at = VALUES(updated_at)
                """,
                (str(period).upper(), snapshot.model_dump_json(), _now_iso()),
            )
            connection.commit()

    def upsert_market_kline_backfill_task(self, task: MarketKlineBackfillTask) -> None:
        self._upsert("market_kline_backfill_tasks", task, self._order_for_id("market_kline_backfill_tasks", task.id))

    def market_kline_time_range(self, symbol: str, period: str) -> tuple[datetime | None, datetime | None]:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT MIN(open_time), MAX(open_time)
                FROM `{MARKET_KLINE_TABLE}`
                WHERE symbol = %s AND period = %s
                """,
                (symbol.upper(), str(period).upper()),
            )
            row = cursor.fetchone()
        earliest = _parse_datetime(str(row[0])) if row and row[0] else None
        latest = _parse_datetime(str(row[1])) if row and row[1] else None
        return earliest, latest

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

    def market_candles_after_signal(self, signal: Signal, period: str = "1H", limit: int = 48) -> list[Candle]:
        with self._connect() as connection:
            cursor = connection.cursor()
            cursor.execute(
                f"""
                SELECT payload FROM `{MARKET_KLINE_TABLE}`
                WHERE symbol = %s AND period = %s AND open_time > %s
                ORDER BY open_time ASC
                LIMIT %s
                """,
                (signal.symbol.upper(), str(period).upper(), signal.triggeredAt, limit),
            )
            rows = cursor.fetchall()

        return [MarketKline.model_validate_json(_payload_text(row[0])).candle for row in rows]

    def performance_for_signal(self, signal_id: str) -> SignalPerformance | None:
        return self._get("signal_performance", _signal_performance_id(signal_id), SignalPerformance)

    def upsert_signal_performance(self, performance: SignalPerformance) -> None:
        self._upsert("signal_performance", performance, self._order_for_id("signal_performance", performance.id))

    def lessons_for_strategy(self, strategy_id: str, limit: int = 10) -> list[StrategyLesson]:
        lessons = [
            lesson
            for lesson in self._list("strategy_lessons", StrategyLesson)
            if lesson.strategyId == strategy_id
        ]
        return lessons[:limit]

    def create_strategy_lesson(self, lesson: StrategyLesson) -> StrategyLesson:
        self._upsert("strategy_lessons", lesson, self._next_front_order("strategy_lessons"))
        return lesson


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _market_kline_id(symbol: str, period: str, open_time: str) -> str:
    raw = f"{symbol.upper()}:{period.upper()}:{open_time}"
    return f"mk-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:40]}"


def _market_kline_backfill_task_status_label(status: str) -> str:
    labels = {
        "pending": "等待中",
        "running": "运行中",
        "completed": "已完成",
        "failed": "失败",
    }
    return labels.get(status, status)


def _empty_market_radar_response(now: datetime | None = None) -> MarketRadarResponse:
    return MarketRadarResponse(
        updatedAt=_as_utc(now or datetime.now(timezone.utc)).isoformat(),
        environment=MarketRadarEnvironment(
            score=0,
            status="avoid",
            label="数据不足",
            summary="当前市场雷达快照尚未生成，或可用于分析的 1H K 线不足。",
            notes=["等待市场雷达快照刷新完成后再查看市场雷达。"],
        ),
        metrics=MarketRadarMetrics(
            symbolsAnalyzed=0,
            risingRatio=0,
            volumeExpansionRatio=0,
            strongTrendRatio=0,
            averageVolatility=0,
            majorTrend="数据不足",
        ),
        opportunityGroups={"breakout": 0, "pullback": 0, "volume_start": 0, "watch": 0},
        recommendations=[],
    )


def _build_market_radar(snapshots: dict[str, list[Candle]], now: datetime | None = None) -> MarketRadarResponse:
    analyses = [
        analysis
        for symbol, candles in snapshots.items()
        if (analysis := _analyze_market_radar_symbol(symbol, candles)) is not None
    ]
    if not analyses:
        return _empty_market_radar_response(now)
    if not analyses:
        return MarketRadarResponse(
            updatedAt=_now_iso(),
            environment=MarketRadarEnvironment(
                score=0,
                status="avoid",
                label="数据不足",
                summary="当前数据库中可用于市场雷达分析的 K 线不足。",
                notes=["等待 K 线补齐或增量采集完成后再查看市场雷达。"],
            ),
            metrics=MarketRadarMetrics(
                symbolsAnalyzed=0,
                risingRatio=0,
                volumeExpansionRatio=0,
                strongTrendRatio=0,
                averageVolatility=0,
                majorTrend="数据不足",
            ),
            opportunityGroups={"breakout": 0, "pullback": 0, "volume_start": 0, "watch": 0},
            recommendations=[],
        )

    total = len(analyses)
    rising_ratio = _round_pct(sum(1 for item in analyses if item["change_pct"] > 0) / total * 100)
    volume_expansion_ratio = _round_pct(sum(1 for item in analyses if item["volume_ratio"] >= 1.25) / total * 100)
    strong_trend_ratio = _round_pct(sum(1 for item in analyses if item["trend_score"] >= 65) / total * 100)
    average_volatility = _round_pct(sum(item["volatility_pct"] for item in analyses) / total)
    major_trend_score = _major_symbol_trend_score(analyses)
    market_score = int(
        max(
            0,
            min(
                100,
                rising_ratio * 0.32
                + volume_expansion_ratio * 0.22
                + strong_trend_ratio * 0.26
                + major_trend_score * 0.2
                - max(0, average_volatility - 8) * 2,
            ),
        )
    )
    if market_score >= 70:
        status = "tradable"
        label = "适合轻仓短线"
    elif market_score >= 50:
        status = "watch_only"
        label = "只适合观察"
    else:
        status = "avoid"
        label = "不适合主动短线"

    notes = _market_radar_notes(status, rising_ratio, volume_expansion_ratio, average_volatility)
    recommendations = [
        _market_radar_recommendation(item)
        for item in sorted(analyses, key=lambda row: row["score"], reverse=True)
        if item["score"] >= 45
    ][:12]
    groups = {"breakout": 0, "pullback": 0, "volume_start": 0, "watch": 0}
    for recommendation in recommendations:
        groups[recommendation.category] = groups.get(recommendation.category, 0) + 1

    return MarketRadarResponse(
        updatedAt=_as_utc(now or datetime.now(timezone.utc)).isoformat(),
        environment=MarketRadarEnvironment(
            score=market_score,
            status=status,  # type: ignore[arg-type]
            label=label,
            summary=notes[0],
            notes=notes,
        ),
        metrics=MarketRadarMetrics(
            symbolsAnalyzed=total,
            risingRatio=rising_ratio,
            volumeExpansionRatio=volume_expansion_ratio,
            strongTrendRatio=strong_trend_ratio,
            averageVolatility=average_volatility,
            majorTrend=_major_trend_label(major_trend_score),
        ),
        opportunityGroups=groups,
        recommendations=recommendations,
    )


def _analyze_market_radar_symbol(symbol: str, candles: list[Candle]) -> dict[str, Any] | None:
    ordered = sorted(candles, key=lambda candle: _parse_datetime(candle.time) or datetime.min.replace(tzinfo=timezone.utc))
    if len(ordered) < 20:
        return None
    first = ordered[-20]
    latest = ordered[-1]
    if first.close <= 0 or latest.close <= 0:
        return None
    recent = ordered[-8:]
    previous = ordered[-20:-8]
    recent_volume = sum(candle.volume for candle in recent) / max(1, len(recent))
    previous_volume = sum(candle.volume for candle in previous) / max(1, len(previous))
    volume_ratio = recent_volume / previous_volume if previous_volume > 0 else 1
    change_pct = (latest.close - first.close) / first.close * 100
    recent_high = max(candle.high for candle in recent)
    recent_low = min(candle.low for candle in recent)
    volatility_pct = (recent_high - recent_low) / latest.close * 100
    above_ma20 = latest.ma20 > 0 and latest.close >= latest.ma20
    trend_score = max(0, min(100, change_pct * 8 + (20 if above_ma20 else 0) + min(volume_ratio, 2.5) * 18))
    score = max(0, min(100, trend_score * 0.45 + min(volume_ratio, 2.5) * 26 + max(0, 20 - volatility_pct) * 0.7))
    return {
        "symbol": symbol,
        "score": int(round(score)),
        "trend_score": trend_score,
        "change_pct": _round_pct(change_pct),
        "volume_ratio": round(volume_ratio, 2),
        "volatility_pct": _round_pct(volatility_pct),
        "above_ma20": above_ma20,
    }


def _market_radar_recommendation(item: dict[str, Any]) -> Any:
    category = _market_radar_category(item)
    risk_level = _market_radar_risk_level(item)
    return MarketRadarRecommendation(
        symbol=item["symbol"],
        category=category,  # type: ignore[arg-type]
        score=item["score"],
        period="1H",
        trend=_trend_label(item["trend_score"]),
        volume=_volume_label(item["volume_ratio"]),
        riskLevel=risk_level,  # type: ignore[arg-type]
        changePct=item["change_pct"],
        volumeRatio=item["volume_ratio"],
        volatilityPct=item["volatility_pct"],
        reason=_market_radar_reason(category, item),
        riskNote=_market_radar_risk_note(risk_level, item),
    )


def _market_radar_category(item: dict[str, Any]) -> str:
    if item["change_pct"] >= 8 and item["volume_ratio"] >= 1.25:
        return "breakout"
    if item["change_pct"] >= 3 and item["volume_ratio"] >= 1.4:
        return "volume_start"
    if item["change_pct"] >= 1 and item["volatility_pct"] <= 10:
        return "pullback"
    return "watch"


def _market_radar_risk_level(item: dict[str, Any]) -> str:
    if item["volatility_pct"] >= 16 or item["change_pct"] >= 18:
        return "high"
    if item["volatility_pct"] >= 9 or item["change_pct"] >= 10:
        return "medium"
    return "low"


def _market_radar_reason(category: str, item: dict[str, Any]) -> str:
    reasons = {
        "breakout": "趋势延续并伴随量能放大，适合作为顺势突破观察。",
        "volume_start": "近期量能明显抬升，价格开始脱离低位。",
        "pullback": "趋势保持向上且波动可控，适合等待回踩确认。",
        "watch": "强度尚可，但主动性不足，适合作为观察候选。",
    }
    return f"{reasons[category]} 近20根涨幅 {item['change_pct']}%，量能倍率 {item['volume_ratio']}。"


def _market_radar_risk_note(risk_level: str, item: dict[str, Any]) -> str:
    if risk_level == "high":
        return "波动或涨幅偏高，避免追高，等待回踩后再评估。"
    if risk_level == "medium":
        return "短线波动正常但已有一定涨幅，需控制仓位。"
    return "波动相对温和，仍需等待周期收线确认。"


def _market_radar_notes(status: str, rising_ratio: float, volume_ratio: float, volatility: float) -> list[str]:
    if status == "tradable":
        first = "市场环境允许轻仓短线，优先关注顺势和放量确认。"
    elif status == "watch_only":
        first = "市场环境不够强，只适合观察强势币，不适合频繁出手。"
    else:
        first = "市场环境不适合主动短线，等待方向和量能重新确认。"
    return [
        first,
        f"上涨交易对占比 {rising_ratio}%，放量交易对占比 {volume_ratio}%。",
        f"平均短线波动 {volatility}%，波动过高时需要降低追单频率。",
    ]


def _major_symbol_trend_score(analyses: list[dict[str, Any]]) -> float:
    majors = [item for item in analyses if item["symbol"] in {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"}]
    if not majors:
        return 50
    return sum(1 for item in majors if item["change_pct"] > 0) / len(majors) * 100


def _major_trend_label(score: float) -> str:
    if score >= 70:
        return "主流币偏多"
    if score >= 40:
        return "主流币分化"
    return "主流币偏弱"


def _trend_label(score: float) -> str:
    if score >= 75:
        return "强"
    if score >= 50:
        return "稳"
    return "弱"


def _volume_label(ratio: float) -> str:
    if ratio >= 1.5:
        return "放量"
    if ratio >= 1.15:
        return "温和"
    return "普通"


def _round_pct(value: float) -> float:
    return round(value, 2)


def _load_market_radar_snapshot_payload(payload_text: str) -> MarketRadarResponse | None:
    try:
        raw = json.loads(payload_text)
    except Exception:
        raw = None
    if isinstance(raw, dict) and "recommendations" in raw and "sections" not in raw:
        return _legacy_market_radar_snapshot(raw)
    try:
        return MarketRadarResponse.model_validate_json(payload_text)
    except Exception:
        if not isinstance(raw, dict):
            return None
        updated_at = _parse_datetime(str(raw.get("updatedAt") or "")) if raw.get("updatedAt") else None
        return _empty_market_radar_response(updated_at)


def _empty_market_radar_response(now: datetime | None = None) -> MarketRadarResponse:
    return MarketRadarResponse(
        updatedAt=_as_utc(now or datetime.now(timezone.utc)).isoformat(),
        environment=MarketRadarEnvironment(
            score=0,
            status="avoid",
            label="数据不足",
            summary="当前市场雷达快照尚未就绪，或可用于分析的 1H K 线不足。",
            notes=["等待下一轮市场雷达快照刷新完成后再查看市场雷达。"],
        ),
        metrics=MarketRadarMetrics(
            symbolsAnalyzed=0,
            risingRatio=0,
            volumeExpansionRatio=0,
            strongTrendRatio=0,
            averageVolatility=0,
            majorTrend="数据不足",
        ),
        opportunityGroups={"short_start": 0, "short_follow": 0, "trend_72h": 0},
        sections=[],
    )


def _market_radar_snapshot_is_stale(snapshot: MarketRadarResponse, now: datetime | None = None) -> bool:
    updated_at = _parse_datetime(snapshot.updatedAt)
    if updated_at is None:
        return True
    age_seconds = (_as_utc(now or datetime.now(timezone.utc)) - _as_utc(updated_at)).total_seconds()
    return age_seconds > MARKET_RADAR_SNAPSHOT_MAX_AGE_SECONDS


def _build_market_radar(
    snapshots: dict[str, list[Candle]],
    ticker_24h: dict[str, dict[str, float]],
    now: datetime | None = None,
) -> MarketRadarResponse:
    analyses: list[dict[str, Any]] = []
    for symbol, candles in snapshots.items():
        quote_volume = float(ticker_24h.get(symbol, {}).get("quoteVolume") or 0.0)
        if quote_volume < 10_000_000:
            continue
        analysis = _analyze_market_radar_symbol(symbol, candles, quote_volume)
        if analysis is not None:
            analyses.append(analysis)
    if not analyses:
        return _empty_market_radar_response(now)

    _attach_relative_ranks(analyses, "change_72h", "rank_72h")
    short_start_items = _select_short_start(analyses)
    short_follow_items = _select_short_follow(analyses)
    trend_72h_items = _select_trend_72h(analyses)
    selected_symbols = {item["symbol"] for item in short_start_items}
    short_follow_items = [item for item in short_follow_items if item["symbol"] not in selected_symbols]
    selected_symbols.update(item["symbol"] for item in short_follow_items)
    trend_72h_items = [item for item in trend_72h_items if item["symbol"] not in selected_symbols]
    strong_symbols = {item["symbol"] for item in short_start_items + short_follow_items + trend_72h_items}
    total = len(analyses)

    rising_ratio = _round_pct(sum(1 for item in analyses if item["change_6h"] > 0) / total * 100)
    volume_expansion_ratio = _round_pct(sum(1 for item in analyses if item["volume_ratio_3h"] >= 1.15) / total * 100)
    strong_trend_ratio = _round_pct(len(strong_symbols) / total * 100)
    average_volatility = _round_pct(sum(item["volatility_6h"] for item in analyses) / total)
    major_trend_score = _major_symbol_trend_score(analyses)
    market_score = int(
        max(
            0,
            min(
                100,
                rising_ratio * 0.22
                + volume_expansion_ratio * 0.2
                + strong_trend_ratio * 0.4
                + major_trend_score * 0.18,
            ),
        )
    )
    if market_score >= 65:
        status = "tradable"
        label = "适合轻仓短线"
    elif market_score >= 40:
        status = "watch_only"
        label = "只适合观察"
    else:
        status = "avoid"
        label = "不适合主动短线"

    notes = _market_radar_notes(status, rising_ratio, volume_expansion_ratio, strong_trend_ratio)
    sections = [
        _market_radar_section(
            "short_start",
            "短线启动",
            "关注最近几小时刚开始放量走强、且价格贴近阶段高点的交易对。",
            short_start_items,
        ),
        _market_radar_section(
            "short_follow",
            "短线延续",
            "关注已经拉出一段、当前仍维持强势结构的交易对。",
            short_follow_items,
        ),
        _market_radar_section(
            "trend_72h",
            "72H 强趋势",
            "关注最近三天在可交易池里相对最强、且回撤受控的交易对。",
            trend_72h_items,
        ),
    ]
    return MarketRadarResponse(
        updatedAt=_as_utc(now or datetime.now(timezone.utc)).isoformat(),
        environment=MarketRadarEnvironment(
            score=market_score,
            status=status,  # type: ignore[arg-type]
            label=label,
            summary=notes[0],
            notes=notes,
        ),
        metrics=MarketRadarMetrics(
            symbolsAnalyzed=total,
            risingRatio=rising_ratio,
            volumeExpansionRatio=volume_expansion_ratio,
            strongTrendRatio=strong_trend_ratio,
            averageVolatility=average_volatility,
            majorTrend=_major_trend_label(major_trend_score),
        ),
        opportunityGroups={
            "short_start": len(short_start_items),
            "short_follow": len(short_follow_items),
            "trend_72h": len(trend_72h_items),
        },
        sections=sections,
    )


def _analyze_market_radar_symbol(symbol: str, candles: list[Candle], quote_volume_24h: float) -> dict[str, Any] | None:
    ordered = sorted(candles, key=lambda candle: _parse_datetime(candle.time) or datetime.min.replace(tzinfo=timezone.utc))
    if len(ordered) < 73:
        return None
    latest = ordered[-1]
    if latest.close <= 0:
        return None
    latest_close = latest.close
    return {
        "symbol": symbol,
        "quote_volume_24h": round(quote_volume_24h, 2),
        "preview_candles": ordered[-60:],
        "change_3h": _pct_change(latest_close, ordered[-4].close),
        "change_6h": _pct_change(latest_close, ordered[-7].close),
        "change_12h": _pct_change(latest_close, ordered[-13].close),
        "change_24h": _pct_change(latest_close, ordered[-25].close),
        "change_72h": _pct_change(latest_close, ordered[-73].close),
        "volume_ratio_3h": _volume_ratio_lookback(ordered, 3, 9),
        "pullback_6h": _pullback_from_high_lookback(ordered[-6:], latest_close),
        "pullback_12h": _pullback_from_high_lookback(ordered[-12:], latest_close),
        "pullback_24h": _pullback_from_high_lookback(ordered[-24:], latest_close),
        "pullback_72h": _pullback_from_high_lookback(ordered[-72:], latest_close),
        "volatility_6h": _volatility_pct_lookback(ordered[-6:], latest_close),
        "above_ma20": latest.ma20 > 0 and latest.close >= latest.ma20,
        "above_ma60": latest.ma60 > 0 and latest.close >= latest.ma60,
    }


def _attach_relative_ranks(items: list[dict[str, Any]], field_name: str, target_name: str) -> None:
    ordered = sorted(items, key=lambda item: item[field_name], reverse=True)
    total = len(ordered)
    for index, item in enumerate(ordered, start=1):
        item[target_name] = index
        item[f"{target_name}_pct"] = index / total * 100


def _select_short_start(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        item
        for item in items
        if item["change_3h"] >= 1.5
        and item["change_6h"] >= 3.5
        and item["change_24h"] >= 6.0
        and item["volume_ratio_3h"] >= 1.15
        and item["pullback_6h"] <= 1.2
        and item["pullback_24h"] <= 2.4
        and item["above_ma20"]
        and item["above_ma60"]
    ]
    for item in candidates:
        item["score"] = int(
            round(
                min(
                    100.0,
                    item["change_3h"] * 12
                    + item["change_6h"] * 10
                    + item["change_24h"] * 3
                    + item["volume_ratio_3h"] * 14
                    + max(0.0, 6 - item["pullback_24h"]) * 4,
                )
            )
        )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:8]


def _select_short_follow(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        item
        for item in items
        if item["change_6h"] >= 2.4
        and item["change_12h"] >= 5.0
        and item["change_24h"] >= 9.0
        and item["above_ma20"]
        and item["above_ma60"]
        and item["pullback_12h"] <= 1.8
        and item["pullback_24h"] <= 3.2
        and item["volume_ratio_3h"] >= 1.0
    ]
    for item in candidates:
        item["score"] = int(
            round(
                min(
                    100.0,
                    item["change_6h"] * 7
                    + item["change_12h"] * 8
                    + item["change_24h"] * 4
                    + item["volume_ratio_3h"] * 10
                    + max(0.0, 5 - item["pullback_24h"]) * 4,
                )
            )
        )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:8]


def _select_trend_72h(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total = len(items)
    top_cutoff = max(1, int(total * 0.1 + 0.999))
    candidates = [
        item
        for item in items
        if item.get("rank_72h", total + 1) <= top_cutoff
        and item["change_24h"] >= 8.0
        and item["pullback_24h"] <= 3.0
        and item["pullback_72h"] <= 4.0
        and item["above_ma20"]
        and item["above_ma60"]
        and item["quote_volume_24h"] >= 20_000_000
    ]
    for item in candidates:
        rank_bonus = max(0, 12 - int(item.get("rank_72h", total)))
        item["score"] = int(
            round(
                min(
                    100.0,
                    item["change_24h"] * 4
                    + item["change_72h"] * 3.2
                    + item["quote_volume_24h"] / 50_000_000
                    + max(0.0, 5 - item["pullback_24h"]) * 4
                    + rank_bonus * 3,
                )
            )
        )
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[:8]


def _market_radar_section(
    key: Literal["short_start", "short_follow", "trend_72h"],
    title: str,
    description: str,
    items: list[dict[str, Any]],
) -> MarketRadarSection:
    return MarketRadarSection(
        key=key,
        title=title,
        description=description,
        items=[_market_radar_section_item(key, item) for item in items],
    )


def _market_radar_section_item(
    key: Literal["short_start", "short_follow", "trend_72h"],
    item: dict[str, Any],
) -> MarketRadarSectionItem:
    move_primary, move_secondary = _market_radar_move_labels(key, item)
    return MarketRadarSectionItem(
        symbol=item["symbol"],
        category=key,
        score=item["score"],
        periodLabel="1H",
        previewCandles=list(item.get("preview_candles") or []),
        movePrimary=move_primary,
        moveSecondary=move_secondary,
        quoteVolume24h=item["quote_volume_24h"],
        volumeRatio=round(item["volume_ratio_3h"], 2),
        pullbackFromHighPct=_round_pct(_pullback_for_key(key, item)),
        reason=_market_radar_reason_v2(key, item),
        riskNote=_market_radar_risk_note_v2(key, item),
    )


def _market_radar_move_labels(
    key: Literal["short_start", "short_follow", "trend_72h"],
    item: dict[str, Any],
) -> tuple[str, str]:
    if key == "short_start":
        return (f"3H {_signed_pct(item['change_3h'])}", f"6H {_signed_pct(item['change_6h'])}")
    if key == "short_follow":
        return (f"6H {_signed_pct(item['change_6h'])}", f"12H {_signed_pct(item['change_12h'])}")
    return (f"24H {_signed_pct(item['change_24h'])}", f"72H {_signed_pct(item['change_72h'])}")


def _pullback_for_key(key: str, item: dict[str, Any]) -> float:
    if key == "short_start":
        return item["pullback_6h"]
    if key == "short_follow":
        return item["pullback_12h"]
    return item["pullback_72h"]


def _market_radar_reason_v2(key: str, item: dict[str, Any]) -> str:
    if key == "short_start":
        return f"近6小时启动走强，量比 {round(item['volume_ratio_3h'], 2)}，距6H高点回撤 {_round_pct(item['pullback_6h'])}% 。"
    if key == "short_follow":
        return f"近12小时保持延续上涨，仍在 MA20 上方，距12H高点回撤 {_round_pct(item['pullback_12h'])}% 。"
    return f"72H 强度位于可交易池前列，24H 成交额 {_format_quote_volume(item['quote_volume_24h'])}，距72H高点回撤 {_round_pct(item['pullback_72h'])}% 。"


def _market_radar_risk_note_v2(key: str, item: dict[str, Any]) -> str:
    pullback = _pullback_for_key(key, item)
    if pullback <= 1.2:
        return "当前离阶段高点较近，适合等回踩确认，避免直接追高。"
    if pullback <= 3:
        return "结构仍完整，但已有一定回撤，关注下一次放量确认。"
    return "回撤已经扩大，虽然仍在候选内，但需要更严格控制仓位。"


def _market_radar_notes(status: str, rising_ratio: float, volume_ratio: float, strong_ratio: float) -> list[str]:
    if status == "tradable":
        first = "市场里有一定数量的短线强势标的，可以轻仓跟踪最强一批。"
    elif status == "watch_only":
        first = "市场有局部机会，但强势结构还不够普遍，更适合观察后再出手。"
    else:
        first = "市场里可执行的短线强势结构不多，当前更适合等待。"
    return [
        first,
        f"最近 6H 仍在上涨的可交易对占比 {rising_ratio}%，放量占比 {volume_ratio}%。",
        f"进入三类强势列表的交易对占比 {strong_ratio}%，优先看最强的一小批。",
    ]


def _major_symbol_trend_score(analyses: list[dict[str, Any]]) -> float:
    majors = [item for item in analyses if item["symbol"] in {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT"}]
    if not majors:
        return 50
    return sum(1 for item in majors if item["change_24h"] > 0 and item["change_6h"] > 0) / len(majors) * 100


def _major_trend_label(score: float) -> str:
    if score >= 70:
        return "主流币偏强"
    if score >= 40:
        return "主流币分化"
    return "主流币偏弱"


def _pct_change(current_close: float, previous_close: float) -> float:
    if previous_close <= 0:
        return 0.0
    return _round_pct((current_close - previous_close) / previous_close * 100)


def _volume_ratio_lookback(candles: list[Candle], recent_count: int, previous_count: int) -> float:
    recent = candles[-recent_count:]
    previous = candles[-(recent_count + previous_count):-recent_count]
    if not recent or not previous:
        return 0.0
    previous_average = sum(candle.volume for candle in previous) / len(previous)
    if previous_average <= 0:
        return 0.0
    recent_average = sum(candle.volume for candle in recent) / len(recent)
    return round(recent_average / previous_average, 2)


def _pullback_from_high_lookback(candles: list[Candle], latest_close: float) -> float:
    if not candles or latest_close <= 0:
        return 0.0
    high = max(candle.high for candle in candles)
    return _round_pct(max(0.0, (high - latest_close) / latest_close * 100))


def _volatility_pct_lookback(candles: list[Candle], latest_close: float) -> float:
    if not candles or latest_close <= 0:
        return 0.0
    high = max(candle.high for candle in candles)
    low = min(candle.low for candle in candles)
    return _round_pct((high - low) / latest_close * 100)


def _signed_pct(value: float) -> str:
    return f"{value:+.2f}%"


def _format_quote_volume(value: float) -> str:
    if value >= 100_000_000:
        return f"{value / 100_000_000:.2f} 亿 USDT"
    if value >= 10_000:
        return f"{value / 10_000:.2f} 万 USDT"
    return f"{value:.2f} USDT"


def _legacy_market_radar_snapshot(raw: dict[str, Any]) -> MarketRadarResponse:
    updated_at = _parse_datetime(str(raw.get("updatedAt") or "")) if raw.get("updatedAt") else None
    recommendations = raw.get("recommendations") if isinstance(raw.get("recommendations"), list) else []
    grouped_items = {"short_start": [], "short_follow": [], "trend_72h": []}
    legacy_category_map = {
        "breakout": "short_start",
        "volume_start": "short_start",
        "pullback": "short_follow",
        "watch": "short_follow",
    }
    for item in recommendations:
        symbol = str(item.get("symbol") or "")
        if not symbol:
            continue
        section_key = legacy_category_map.get(str(item.get("category") or ""), "short_follow")
        grouped_items[section_key].append(
            MarketRadarSectionItem(
                symbol=symbol,
                category=section_key,  # type: ignore[arg-type]
                score=int(item.get("score") or 0),
                periodLabel=str(item.get("period") or "1H"),
                previewCandles=[
                    Candle.model_validate(candle)
                    for candle in item.get("previewCandles") or []
                    if isinstance(candle, dict)
                ],
                movePrimary=f"24H {_signed_pct(float(item.get('changePct') or 0.0))}",
                moveSecondary=f"量比 {float(item.get('volumeRatio') or 0.0):.2f}",
                quoteVolume24h=0.0,
                volumeRatio=round(float(item.get("volumeRatio") or 0.0), 2),
                pullbackFromHighPct=0.0,
                reason=str(item.get("reason") or "兼容旧版快照推荐。"),
                riskNote=str(item.get("riskNote") or ""),
            )
        )
    sections = [
        MarketRadarSection(key="short_start", title="短线启动", description="由旧版快照兼容转换，等待新快照刷新。", items=grouped_items["short_start"]),
        MarketRadarSection(key="short_follow", title="短线延续", description="由旧版快照兼容转换，等待新快照刷新。", items=grouped_items["short_follow"]),
        MarketRadarSection(key="trend_72h", title="72H 强趋势", description="由旧版快照兼容转换，等待新快照刷新。", items=[]),
    ]
    environment_raw = raw.get("environment") if isinstance(raw.get("environment"), dict) else {}
    metrics_raw = raw.get("metrics") if isinstance(raw.get("metrics"), dict) else {}
    return MarketRadarResponse(
        updatedAt=_as_utc(updated_at or datetime.now(timezone.utc)).isoformat(),
        environment=MarketRadarEnvironment(
            score=int(environment_raw.get("score") or 0),
            status=str(environment_raw.get("status") or "watch_only"),  # type: ignore[arg-type]
            label=str(environment_raw.get("label") or "兼容旧快照"),
            summary=str(environment_raw.get("summary") or "旧版快照已兼容读取，等待新快照刷新。"),
            notes=[str(note) for note in environment_raw.get("notes") or ["旧版快照已兼容读取，等待新快照刷新。"]],
        ),
        metrics=MarketRadarMetrics(
            symbolsAnalyzed=int(metrics_raw.get("symbolsAnalyzed") or len(recommendations)),
            risingRatio=float(metrics_raw.get("risingRatio") or 0),
            volumeExpansionRatio=float(metrics_raw.get("volumeExpansionRatio") or 0),
            strongTrendRatio=float(metrics_raw.get("strongTrendRatio") or 0),
            averageVolatility=float(metrics_raw.get("averageVolatility") or 0),
            majorTrend=str(metrics_raw.get("majorTrend") or "数据不足"),
        ),
        opportunityGroups={
            "short_start": len(grouped_items["short_start"]),
            "short_follow": len(grouped_items["short_follow"]),
            "trend_72h": 0,
        },
        sections=sections,
    )


def _signal_performance_id(signal_id: str) -> str:
    return f"perf-{signal_id}"


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


def _scan_new_coin_listings(store_instance: Any) -> NewCoinScanResult:
    errors: list[str] = []
    try:
        fetched_items = fetch_binance_new_listing_announcements()
    except Exception as exc:
        new_coin_logger.warning("New coin scan failed: %s", exc)
        return NewCoinScanResult(errors=[str(exc)])

    created = 0
    updated = 0
    notified = 0
    saved_items: list[NewCoinListing] = []
    now = _now_iso()

    for raw_item in fetched_items:
        try:
            listing = _normalize_new_coin_listing(raw_item, now)
            existing = store_instance._get(NEW_COIN_LISTINGS_TABLE, listing.id, NewCoinListing)
            if existing is None:
                _store_upsert_front(store_instance, NEW_COIN_LISTINGS_TABLE, listing)
                created += 1
                if _new_coin_pushover_enabled(store_instance):
                    push_error = _send_new_coin_pushover_if_configured(store_instance, listing)
                    if push_error:
                        errors.append(f"{listing.symbol}: Pushover push failed: {push_error}")
                    else:
                        notified_listing = listing.model_copy(update={"notifiedAt": _now_iso(), "updatedAt": _now_iso()})
                        store_instance._upsert(
                            NEW_COIN_LISTINGS_TABLE,
                            notified_listing,
                            store_instance._order_for_id(NEW_COIN_LISTINGS_TABLE, listing.id),
                        )
                        listing = notified_listing
                        notified += 1
            else:
                listing = listing.model_copy(update={"createdAt": existing.createdAt, "notifiedAt": existing.notifiedAt})
                if listing.model_dump(exclude={"updatedAt"}) != existing.model_dump(exclude={"updatedAt"}):
                    store_instance._upsert(
                        NEW_COIN_LISTINGS_TABLE,
                        listing,
                        store_instance._order_for_id(NEW_COIN_LISTINGS_TABLE, listing.id),
                    )
                    updated += 1
                else:
                    listing = existing
            saved_items.append(listing)
        except Exception as exc:
            errors.append(str(exc))

    return NewCoinScanResult(
        fetched=len(fetched_items),
        created=created,
        updated=updated,
        notified=notified,
        errors=errors,
        listings=saved_items,
    )


def _normalize_new_coin_listing(raw_item: dict[str, Any], now: str) -> NewCoinListing:
    symbol = str(raw_item.get("symbol") or "").strip().upper()
    title = str(raw_item.get("title") or "").strip()
    if not symbol:
        symbol = _extract_listing_symbols(title)[0] if _extract_listing_symbols(title) else ""
    if not symbol:
        raise ValueError(f"Unable to parse listing symbol from: {title}")

    item_id = str(raw_item.get("id") or "").strip()
    if not item_id:
        item_id = _new_coin_listing_id("binance", title, str(raw_item.get("announcedAt") or ""))

    status = str(raw_item.get("status") or "discovered").strip().lower()
    if status not in {"discovered", "upcoming", "listed"}:
        status = "discovered"

    return NewCoinListing(
        id=item_id,
        symbol=symbol,
        tradingPairs=_normalize_trading_pairs(raw_item.get("tradingPairs"), symbol),
        title=title or symbol,
        url=str(raw_item.get("url") or "").strip(),
        announcedAt=str(raw_item.get("announcedAt") or "").strip() or None,
        listedAt=str(raw_item.get("listedAt") or "").strip() or None,
        status=status,  # type: ignore[arg-type]
        source="binance",
        notifiedAt=str(raw_item.get("notifiedAt") or "").strip() or None,
        createdAt=str(raw_item.get("createdAt") or "").strip() or now,
        updatedAt=now,
    )


def _new_coin_listing_id(source: str, title: str, announced_at: str) -> str:
    raw = f"{source}:{title}:{announced_at}"
    return f"newcoin-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:32]}"


def _normalize_trading_pairs(value: Any, symbol: str) -> list[str]:
    raw_items = value if isinstance(value, list) else []
    pairs: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        pair = str(item).strip().upper().replace("/", "")
        if not pair or pair in seen:
            continue
        pairs.append(pair)
        seen.add(pair)
    if pairs:
        return pairs
    return [f"{symbol}USDT"] if symbol else []


def fetch_binance_new_listing_announcements(limit: int = 20) -> list[dict[str, Any]]:
    urls = [
        (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
            f"?type=1&catalogId=48&pageNo=1&pageSize={limit}"
        ),
        (
            "https://www.binance.com/bapi/composite/v1/public/cms/article/catalog/list/query"
            f"?catalogId=48&pageNo=1&pageSize={limit}"
        ),
    ]
    last_error: Exception | None = None
    for url in urls:
        try:
            raw_payload = _read_url_with_retry(url, timeout=10)
            payload = json.loads(raw_payload)
            return _parse_binance_listing_payload(payload)
        except Exception as exc:
            last_error = exc
    assert last_error is not None
    raise last_error


def _parse_binance_listing_payload(payload: Any) -> list[dict[str, Any]]:
    articles = _collect_binance_articles(payload)
    listings: list[dict[str, Any]] = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        title = str(article.get("title") or "").strip()
        if not _looks_like_new_listing_title(title):
            continue
        symbols = _extract_listing_symbols(title)
        if not symbols:
            continue
        article_id = str(article.get("id") or article.get("code") or article.get("slug") or title)
        article_code = str(article.get("code") or article.get("slug") or article_id)
        announced_at = _binance_article_time(article)
        url = _binance_article_url(article_code)
        pairs = _extract_trading_pairs(title, symbols)
        for symbol in symbols:
            listings.append(
                {
                    "id": f"binance-{article_id}-{symbol}".replace(" ", "-"),
                    "symbol": symbol,
                    "tradingPairs": [pair for pair in pairs if pair.startswith(symbol)] or [f"{symbol}USDT"],
                    "title": title,
                    "url": url,
                    "announcedAt": announced_at,
                    "listedAt": None,
                    "status": "upcoming" if "will" in title.lower() or "即将" in title else "discovered",
                    "source": "binance",
                }
            )
    return listings


def _collect_binance_articles(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if not isinstance(value, dict):
        return []
    articles: list[dict[str, Any]] = []
    for key in ("articles", "catalogs", "data"):
        child = value.get(key)
        if key == "articles" and isinstance(child, list):
            articles.extend(item for item in child if isinstance(item, dict))
        elif isinstance(child, (dict, list)):
            articles.extend(_collect_binance_articles(child))
    return articles


def _looks_like_new_listing_title(title: str) -> bool:
    normalized = title.lower()
    positive = [
        "binance will list",
        "binance lists",
        "will launch",
        "new listing",
        "上线",
        "上市",
        "新增",
    ]
    negative = ["delist", "remove", "suspend", "redenomination", "airdrop"]
    return any(word in normalized for word in positive) and not any(word in normalized for word in negative)


def _extract_listing_symbols(title: str) -> list[str]:
    candidates: list[str] = []
    for group in re.findall(r"\(([A-Z0-9,\s/]+)\)", title):
        for token in re.split(r"[,/\s]+", group):
            if _is_listing_symbol_token(token):
                candidates.append(token.upper())
    for pair in re.findall(r"\b([A-Z0-9]{2,15})(?:USDT|FDUSD|USDC|BTC|BNB)\b", title):
        if _is_listing_symbol_token(pair):
            candidates.append(pair.upper())
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        deduped.append(candidate)
        seen.add(candidate)
    return deduped[:8]


def _is_listing_symbol_token(token: str) -> bool:
    value = str(token or "").strip().upper()
    return (
        2 <= len(value) <= 12
        and value.isalnum()
        and value not in {"USDT", "USDC", "FDUSD", "BTC", "ETH", "BNB", "USD", "EUR", "TRY"}
    )


def _extract_trading_pairs(title: str, symbols: list[str]) -> list[str]:
    pairs = [match.upper().replace("/", "") for match in re.findall(r"\b[A-Z0-9]{2,15}(?:USDT|FDUSD|USDC|BTC|BNB)\b", title)]
    if pairs:
        return pairs
    return [f"{symbol}USDT" for symbol in symbols]


def _binance_article_time(article: dict[str, Any]) -> str | None:
    for key in ("releaseDate", "publishDate", "publishedAt", "createdAt"):
        value = article.get(key)
        if value in (None, ""):
            continue
        try:
            if isinstance(value, (int, float)):
                timestamp = float(value)
                if timestamp > 10_000_000_000:
                    timestamp /= 1000
                return datetime.fromtimestamp(timestamp, tz=timezone.utc).isoformat()
            return str(value)
        except Exception:
            continue
    return None


def _binance_article_url(article_code: str) -> str:
    code = str(article_code or "").strip()
    if code.startswith("http"):
        return code
    return f"https://www.binance.com/en/support/announcement/{code}" if code else "https://www.binance.com/en/support/announcement"


def _new_coin_pushover_enabled(store_instance: Any) -> bool:
    try:
        raw_settings = store_instance._get_raw_settings()
    except Exception:
        return False
    pushover = raw_settings.get("pushover") if isinstance(raw_settings.get("pushover"), dict) else {}
    return bool(pushover.get("enabled") and pushover.get("userKey") and pushover.get("appToken"))


def _send_new_coin_pushover_if_configured(store_instance: Any, listing: NewCoinListing) -> str | None:
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
            f"币种：{listing.symbol}",
            f"交易对：{', '.join(listing.tradingPairs) or '-'}",
            f"状态：{_new_coin_status_label(listing.status)}",
            f"公告：{listing.title}",
            f"链接：{listing.url}",
        ]
    )
    payload = urllib.parse.urlencode(
        {
            "token": app_token,
            "user": user_key,
            "title": f"TrendAI 新币提醒：{listing.symbol}",
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


def _new_coin_status_label(status: str) -> str:
    labels = {"discovered": "已发现", "upcoming": "即将上线", "listed": "已上线"}
    return labels.get(status, status)


def _market_kline_retention_cutoffs(now: datetime | None = None) -> dict[str, str]:
    current = _as_utc(now or datetime.now(timezone.utc))
    return {
        "5M": (current - timedelta(days=30)).isoformat(),
        "15M": (current - timedelta(days=30)).isoformat(),
        "1H": (current - timedelta(days=30)).isoformat(),
        "4H": (current - timedelta(days=30)).isoformat(),
        "1D": (current - timedelta(days=365)).isoformat(),
    }


def _market_kline_target_window_label(period: str) -> str:
    return "365天" if str(period).upper() == "1D" else "30天"


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[index:index + size] for index in range(0, len(items), size)]


def _ensure_mysql_index(cursor: Any, table: str, index_name: str, create_sql: str) -> None:
    cursor.execute(
        """
        SELECT COUNT(*)
        FROM information_schema.statistics
        WHERE table_schema = DATABASE()
          AND table_name = %s
          AND index_name = %s
        """,
        (table, index_name),
    )
    row = cursor.fetchone()
    if not row or int(row[0] or 0) == 0:
        cursor.execute(create_sql)



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
    strategies = [
        strategy
        for strategy in store_instance.strategies
        if strategy.enabled and strategy.schedule.enabled and strategy.runtime.code.strip()
    ]
    strategy_created_counts: dict[str, int] = {strategy.id: 0 for strategy in strategies}
    strategy_errors_by_id: dict[str, list[str]] = {strategy.id: [] for strategy in strategies}

    for period, period_strategies in _strategies_by_period(strategies).items():
        max_required_candles = max(_strategy_required_candle_count(strategy) for strategy in period_strategies)
        for symbol, source_signal in _scan_items_for_strategy(period, market_snapshots):
            cached_candles = store_instance.latest_market_candles(symbol, period, max_required_candles)
            price = source_signal.price if source_signal is not None else 0
            if cached_candles:
                price = cached_candles[-1].close

            for strategy in period_strategies:
                symbol_blacklist = set(_normalize_symbol_blacklist(strategy.symbolBlacklist))
                if symbol.upper() in symbol_blacklist:
                    continue
                symbols_checked += 1
                required_candles = _strategy_required_candle_count(strategy)
                if len(cached_candles) < required_candles:
                    continue
                candles = cached_candles[-required_candles:]
                try:
                    matched = _execute_strategy_code(strategy.runtime.code, candles)
                except Exception as exc:
                    message = f"{strategy.name} / {symbol}: {exc}"
                    errors.append(message)
                    strategy_errors_by_id[strategy.id].append(message)
                    continue

                if not matched:
                    continue

                run_at = _now_iso()
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
                    strategy_errors_by_id[strategy.id].append(message)
                created_signals.append(signal)
                strategy_created_counts[strategy.id] += 1

    for strategy in strategies:
        strategies_checked += 1
        strategy_created = strategy_created_counts[strategy.id]
        strategy_errors = strategy_errors_by_id[strategy.id]
        updated = strategy.model_copy(
            update={
                "todaySignalCount": strategy.todaySignalCount + strategy_created,
                "lastTriggeredAt": _now_iso() if strategy_created else strategy.lastTriggeredAt,
                "schedule": strategy.schedule.model_copy(
                    update={
                        "lastRunAt": _now_iso(),
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


def _strategies_by_period(strategies: list[Strategy]) -> dict[str, list[Strategy]]:
    grouped: dict[str, list[Strategy]] = {}
    for strategy in strategies:
        grouped.setdefault(strategy.period, []).append(strategy)
    return grouped


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


def _strategy_required_candle_count(strategy: Strategy) -> int:
    candidates: list[int] = []
    structured_conditions = strategy.runtime.structuredConditions if strategy.runtime else []
    for condition in structured_conditions:
        candidates.extend(_extract_candle_count_candidates(condition.title))
        candidates.extend(_extract_candle_count_candidates(condition.description))
        for parameter in condition.parameters:
            candidates.extend(_extract_candle_count_candidates(parameter))
    for condition in strategy.conditions:
        candidates.extend(_extract_candle_count_candidates(condition))
    if strategy.runtime and strategy.runtime.code:
        candidates.extend(_extract_candle_count_candidates(strategy.runtime.code))
    return max(1, max(candidates)) if candidates else CLOSED_KLINE_LIMIT


def _extract_candle_count_candidates(text: str) -> list[int]:
    if not text:
        return []
    candidates: list[int] = []
    patterns = [
        r"len\s*\(\s*candles\s*\)\s*[<>]=?\s*(\d+)",
        r"candles\s*\[\s*-\s*(\d+)\s*:",
        r"candles\s*\[\s*-\s*(\d+)\s*\]",
        r"(?:根数|bars?|bar_count|kline_count)\s*[：:=]?\s*(\d+)",
        r"(\d+)\s*(?:根|bars?)",
    ]
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            try:
                candidates.append(int(match.group(1)))
            except (TypeError, ValueError):
                continue
    return candidates


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
    if _market_kline_collection_is_collecting() or _market_kline_backfill_is_backfilling() or _market_kline_cleanup_is_cleaning():
        return _strategy_run_progress_from_state(
            {
                "jobId": "",
                "running": False,
                "triggerSource": trigger_source,
                "errorsCount": 1,
                "errors": [
                    StrategyRunError(
                        time=datetime.now().strftime("%H:%M:%S"),
                        symbol="ALL",
                        errorType="K线更新中",
                        message="K线数据正在更新，请稍后再试",
                        impact="本次扫描未启动",
                    )
                ],
            }
        )
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

        strategy_created_counts: dict[str, int] = {strategy.id: 0 for strategy in strategies}
        strategy_errors_by_id: dict[str, list[str]] = {strategy.id: [] for strategy in strategies}
        for strategy in strategies:
            _merge_run_state(
                strategiesChecked=(_run_job_state or {}).get("strategiesChecked", 0) + 1,
            )

        for period, period_strategies in _strategies_by_period(strategies).items():
            if _is_run_cancel_requested():
                break
            max_required_candles = max(_strategy_required_candle_count(strategy) for strategy in period_strategies)
            for symbol in symbols:
                if _is_run_cancel_requested():
                    break
                _merge_run_state(currentPeriod=period, currentSymbol=symbol)
                try:
                    cached_candles = store_instance.latest_market_candles(symbol, period, max_required_candles)
                except Exception as exc:
                    for strategy in period_strategies:
                        _merge_run_state(currentStrategyName=strategy.name)
                        _append_run_error(symbol, "数据获取失败", str(exc))
                        strategy_errors_by_id[strategy.id].append(f"{strategy.name} / {symbol}: {exc}")
                        _increment_scanned()
                    continue

                price = cached_candles[-1].close if cached_candles else 0.0
                for strategy in period_strategies:
                    _merge_run_state(currentStrategyName=strategy.name)
                    symbol_blacklist = set(_normalize_symbol_blacklist(strategy.symbolBlacklist))
                    if symbol.upper() in symbol_blacklist:
                        _append_run_skip(symbol, "币种黑名单", f"{symbol} 已加入该策略黑名单，跳过本次扫描")
                        _increment_scanned()
                        continue
                    required_candles = _strategy_required_candle_count(strategy)
                    if len(cached_candles) < required_candles:
                        _append_run_skip(symbol, "K线不足", f"需要 {required_candles} 根完整K线，实际 {len(cached_candles)} 根")
                        _increment_scanned()
                        continue
                    candles = cached_candles[-required_candles:]

                    try:
                        matched = _execute_strategy_code(strategy.runtime.code, candles)
                    except Exception as exc:
                        _append_run_error(symbol, "计算异常", str(exc))
                        strategy_errors_by_id[strategy.id].append(f"{strategy.name} / {symbol}: {exc}")
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
                            triggeredAt=_now_iso(),
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
                            strategy_errors_by_id[strategy.id].append(f"{strategy.name} / {symbol}: Pushover push failed: {push_error}")
                        strategy_created_counts[strategy.id] += 1
                        with _run_job_lock:
                            if _run_job_state is not None:
                                _run_job_state["signalsCreated"] += 1
                                _run_job_state["createdSignals"].append(signal)
                    _increment_scanned()

        for strategy in strategies:
            strategy_created = strategy_created_counts[strategy.id]
            strategy_errors = strategy_errors_by_id[strategy.id]
            updated = strategy.model_copy(
                update={
                    "todaySignalCount": strategy.todaySignalCount + strategy_created,
                    "lastTriggeredAt": _now_iso() if strategy_created else strategy.lastTriggeredAt,
                    "schedule": strategy.schedule.model_copy(
                        update={
                            "lastRunAt": _now_iso(),
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


def _signal_row_is_older_than_cutoff(payload_text: str, created_at: str, cutoff: datetime) -> bool:
    payload = _json_loads(_payload_text(payload_text))
    signal_time = _parse_datetime(str(payload.get("triggeredAt") or ""))
    if signal_time is None:
        signal_time = _parse_datetime(str(created_at or ""))
    return signal_time is not None and _as_utc(signal_time) < _as_utc(cutoff)


def _latest_period_boundary(period: str, now: datetime) -> datetime:
    normalized = _as_utc(now).replace(second=0, microsecond=0)
    if period == "5M":
        return normalized.replace(minute=(normalized.minute // 5) * 5)
    if period == "15M":
        return normalized.replace(minute=(normalized.minute // 15) * 15)
    if period == "4H":
        return normalized.replace(hour=(normalized.hour // 4) * 4, minute=0)
    if period == "1D":
        return normalized.replace(hour=0, minute=0)
    return normalized.replace(minute=0)


def _first_expected_market_kline_time(start: datetime, period: str) -> datetime:
    normalized_start = _as_utc(start).replace(second=0, microsecond=0)
    floored = _floor_datetime_to_period(normalized_start, period)
    if floored < normalized_start:
        return floored + timedelta(seconds=_period_seconds(period))
    return floored


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

    if (
        run_busy
        or not due_strategies
        or _market_kline_collection_is_collecting()
        or _market_kline_backfill_is_backfilling()
        or _market_kline_cleanup_is_cleaning()
    ):
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


_new_coin_scheduler_lock = threading.Lock()
_new_coin_scheduler_stop_event: threading.Event | None = None
_new_coin_scheduler_thread: threading.Thread | None = None
_new_coin_scheduler_state: dict[str, Any] = {
    "running": False,
    "checkIntervalSeconds": 180,
    "lastCheckedAt": None,
    "lastTriggeredAt": None,
    "lastError": "",
}


def run_new_coin_scheduler_tick(store_instance: Any) -> NewCoinScanResult:
    with _new_coin_scheduler_lock:
        _new_coin_scheduler_state["lastCheckedAt"] = _now_iso()
        _new_coin_scheduler_state["lastError"] = ""
    result = store_instance.scan_new_coin_listings()
    with _new_coin_scheduler_lock:
        _new_coin_scheduler_state["lastTriggeredAt"] = _now_iso()
        if result.errors:
            _new_coin_scheduler_state["lastError"] = "\n".join(result.errors[:3])
    return result


def start_new_coin_scheduler(store_instance: Any, check_interval_seconds: int = 180) -> None:
    global _new_coin_scheduler_stop_event, _new_coin_scheduler_thread
    with _new_coin_scheduler_lock:
        if _new_coin_scheduler_thread is not None and _new_coin_scheduler_thread.is_alive():
            return
        _new_coin_scheduler_stop_event = threading.Event()
        _new_coin_scheduler_state.update(
            {
                "running": True,
                "checkIntervalSeconds": check_interval_seconds,
                "lastError": "",
            }
        )
        _new_coin_scheduler_thread = threading.Thread(
            target=_new_coin_scheduler_loop,
            args=(store_instance, check_interval_seconds, _new_coin_scheduler_stop_event),
            daemon=True,
        )
        _new_coin_scheduler_thread.start()


def stop_new_coin_scheduler() -> None:
    global _new_coin_scheduler_stop_event, _new_coin_scheduler_thread
    with _new_coin_scheduler_lock:
        stop_event = _new_coin_scheduler_stop_event
        thread = _new_coin_scheduler_thread
        _new_coin_scheduler_stop_event = None
        _new_coin_scheduler_thread = None
        _new_coin_scheduler_state["running"] = False
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


def get_new_coin_scheduler_status() -> NewCoinSchedulerStatus:
    with _new_coin_scheduler_lock:
        return NewCoinSchedulerStatus(**_new_coin_scheduler_state)


def _new_coin_scheduler_loop(store_instance: Any, check_interval_seconds: int, stop_event: threading.Event) -> None:
    while not stop_event.wait(check_interval_seconds):
        try:
            run_new_coin_scheduler_tick(store_instance)
        except Exception as exc:
            with _new_coin_scheduler_lock:
                _new_coin_scheduler_state["lastCheckedAt"] = _now_iso()
                _new_coin_scheduler_state["lastError"] = str(exc)


_signal_cleanup_scheduler_lock = threading.Lock()
_signal_cleanup_scheduler_stop_event: threading.Event | None = None
_signal_cleanup_scheduler_thread: threading.Thread | None = None
_signal_cleanup_scheduler_state: dict[str, Any] = {
    "running": False,
    "checkIntervalSeconds": 3600,
    "lastCheckedAt": None,
    "lastTriggeredAt": None,
    "lastCleanupDate": None,
    "lastDeleted": 0,
    "lastError": "",
}


def run_signal_cleanup_scheduler_tick(
    store_instance: Any,
    now: datetime | None = None,
    retention_days: int = 30,
) -> int:
    check_time = _as_utc(now or datetime.now(timezone.utc))
    cleanup_date = check_time.date().isoformat()
    with _signal_cleanup_scheduler_lock:
        _signal_cleanup_scheduler_state["lastCheckedAt"] = _now_iso()
        _signal_cleanup_scheduler_state["lastError"] = ""
        if _signal_cleanup_scheduler_state.get("lastCleanupDate") == cleanup_date:
            return 0

    deleted = store_instance.delete_old_signals(check_time, retention_days=retention_days)
    with _signal_cleanup_scheduler_lock:
        _signal_cleanup_scheduler_state["lastTriggeredAt"] = _now_iso()
        _signal_cleanup_scheduler_state["lastCleanupDate"] = cleanup_date
        _signal_cleanup_scheduler_state["lastDeleted"] = deleted
    return deleted


def start_signal_cleanup_scheduler(store_instance: Any, check_interval_seconds: int = 3600) -> None:
    global _signal_cleanup_scheduler_stop_event, _signal_cleanup_scheduler_thread
    with _signal_cleanup_scheduler_lock:
        if _signal_cleanup_scheduler_thread is not None and _signal_cleanup_scheduler_thread.is_alive():
            return
        _signal_cleanup_scheduler_stop_event = threading.Event()
        _signal_cleanup_scheduler_state.update(
            {
                "running": True,
                "checkIntervalSeconds": check_interval_seconds,
                "lastError": "",
            }
        )
        _signal_cleanup_scheduler_thread = threading.Thread(
            target=_signal_cleanup_scheduler_loop,
            args=(store_instance, check_interval_seconds, _signal_cleanup_scheduler_stop_event),
            daemon=True,
        )
        _signal_cleanup_scheduler_thread.start()


def stop_signal_cleanup_scheduler() -> None:
    global _signal_cleanup_scheduler_stop_event, _signal_cleanup_scheduler_thread
    with _signal_cleanup_scheduler_lock:
        stop_event = _signal_cleanup_scheduler_stop_event
        thread = _signal_cleanup_scheduler_thread
        _signal_cleanup_scheduler_stop_event = None
        _signal_cleanup_scheduler_thread = None
        _signal_cleanup_scheduler_state["running"] = False
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


def _signal_cleanup_scheduler_loop(store_instance: Any, check_interval_seconds: int, stop_event: threading.Event) -> None:
    while not stop_event.wait(check_interval_seconds):
        try:
            run_signal_cleanup_scheduler_tick(store_instance)
        except Exception as exc:
            with _signal_cleanup_scheduler_lock:
                _signal_cleanup_scheduler_state["lastCheckedAt"] = _now_iso()
                _signal_cleanup_scheduler_state["lastError"] = str(exc)


_signal_performance_scheduler_lock = threading.Lock()
_signal_performance_scheduler_stop_event: threading.Event | None = None
_signal_performance_scheduler_thread: threading.Thread | None = None
_signal_performance_scheduler_state: dict[str, Any] = {
    "running": False,
    "checkIntervalSeconds": 300,
    "lastCheckedAt": None,
    "lastTriggeredAt": None,
    "lastTracked": 0,
    "lastReviewed": 0,
    "lastLessonsCreated": 0,
    "lastError": "",
}


def run_signal_performance_scheduler_tick(
    store_instance: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    check_time = _as_utc(now or datetime.now(timezone.utc))
    with _signal_performance_scheduler_lock:
        _signal_performance_scheduler_state["lastCheckedAt"] = _now_iso()
        _signal_performance_scheduler_state["lastError"] = ""

    if _market_kline_collection_is_collecting() or _market_kline_cleanup_is_cleaning():
        return {"tracked": 0, "reviewed": 0, "lessonsCreated": 0, "skipped": "kline_busy", "errors": []}

    tracked = 0
    reviewed = 0
    lessons_created = 0
    errors: list[str] = []
    raw_settings = store_instance._get_raw_settings() if hasattr(store_instance, "_get_raw_settings") else {}

    for signal in store_instance.signals:
        try:
            performance = _calculate_signal_performance(store_instance, signal, check_time)
            if performance is None:
                continue
            store_instance.upsert_signal_performance(performance)
            tracked += 1
            if performance.status == "completed" and performance.reviewStatus == "pending":
                reviewed_performance, lesson = _generate_signal_review(store_instance, signal, performance, raw_settings)
                store_instance.upsert_signal_performance(reviewed_performance)
                reviewed += 1
                if lesson is not None:
                    store_instance.create_strategy_lesson(lesson)
                    lessons_created += 1
        except Exception as exc:
            errors.append(f"{signal.id}: {exc}")

    with _signal_performance_scheduler_lock:
        _signal_performance_scheduler_state["lastTriggeredAt"] = _now_iso()
        _signal_performance_scheduler_state["lastTracked"] = tracked
        _signal_performance_scheduler_state["lastReviewed"] = reviewed
        _signal_performance_scheduler_state["lastLessonsCreated"] = lessons_created
        _signal_performance_scheduler_state["lastError"] = "\n".join(errors[:3])

    return {"tracked": tracked, "reviewed": reviewed, "lessonsCreated": lessons_created, "errors": errors}


def start_signal_performance_scheduler(store_instance: Any, check_interval_seconds: int = 300) -> None:
    global _signal_performance_scheduler_stop_event, _signal_performance_scheduler_thread
    with _signal_performance_scheduler_lock:
        if _signal_performance_scheduler_thread is not None and _signal_performance_scheduler_thread.is_alive():
            return
        _signal_performance_scheduler_stop_event = threading.Event()
        _signal_performance_scheduler_state.update(
            {
                "running": True,
                "checkIntervalSeconds": check_interval_seconds,
                "lastError": "",
            }
        )
        _signal_performance_scheduler_thread = threading.Thread(
            target=_signal_performance_scheduler_loop,
            args=(store_instance, check_interval_seconds, _signal_performance_scheduler_stop_event),
            daemon=True,
        )
        _signal_performance_scheduler_thread.start()


def stop_signal_performance_scheduler() -> None:
    global _signal_performance_scheduler_stop_event, _signal_performance_scheduler_thread
    with _signal_performance_scheduler_lock:
        stop_event = _signal_performance_scheduler_stop_event
        thread = _signal_performance_scheduler_thread
        _signal_performance_scheduler_stop_event = None
        _signal_performance_scheduler_thread = None
        _signal_performance_scheduler_state["running"] = False
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


def _signal_performance_scheduler_loop(store_instance: Any, check_interval_seconds: int, stop_event: threading.Event) -> None:
    while not stop_event.wait(check_interval_seconds):
        try:
            run_signal_performance_scheduler_tick(store_instance)
        except Exception as exc:
            with _signal_performance_scheduler_lock:
                _signal_performance_scheduler_state["lastCheckedAt"] = _now_iso()
                _signal_performance_scheduler_state["lastError"] = str(exc)


def _calculate_signal_performance(store_instance: Any, signal: Signal, now: datetime) -> SignalPerformance | None:
    if signal.price <= 0:
        return None
    triggered_at = _parse_datetime(signal.triggeredAt)
    if triggered_at is None:
        return None
    triggered_at_utc = _as_utc(triggered_at)
    if _as_utc(now) <= triggered_at_utc:
        return None

    existing = store_instance.performance_for_signal(signal.id)
    candles = store_instance.market_candles_after_signal(signal, "1H", 48)
    now_iso = _now_iso()
    base = existing or SignalPerformance(
        id=_signal_performance_id(signal.id),
        signalId=signal.id,
        symbol=signal.symbol,
        period=signal.period,
        strategyId=signal.strategyId,
        strategyName=signal.strategyName,
        entryPrice=signal.price,
        createdAt=now_iso,
        updatedAt=now_iso,
    )
    if not candles:
        return base.model_copy(update={"status": "tracking", "updatedAt": now_iso})

    elapsed_hours = (_as_utc(now) - triggered_at_utc).total_seconds() / 3600
    status = "completed" if elapsed_hours >= 24 and len(candles) >= 24 else "tracking"
    window = candles[:24] if len(candles) >= 24 else candles
    updates: dict[str, Any] = {
        "status": status,
        "bestPrice": max(candle.high for candle in window),
        "worstPrice": min(candle.low for candle in window),
        "evaluatedUntil": window[-1].time,
        "updatedAt": now_iso,
    }
    updates["maxGainPct"] = _pct(updates["bestPrice"], signal.price)
    updates["maxDrawdownPct"] = _pct(updates["worstPrice"], signal.price)
    if len(candles) >= 1:
        updates["change1hPct"] = _pct(candles[0].close, signal.price)
    if len(candles) >= 4:
        updates["change4hPct"] = _pct(candles[3].close, signal.price)
    if len(candles) >= 24:
        updates["change24hPct"] = _pct(candles[23].close, signal.price)
    return base.model_copy(update=updates)


def _pct(value: float, base: float) -> float:
    return round((value - base) / base * 100, 6)


def _generate_signal_review(
    store_instance: Any,
    signal: Signal,
    performance: SignalPerformance,
    raw_settings: dict[str, Any],
) -> tuple[SignalPerformance, StrategyLesson | None]:
    review_response = _call_llm_for_signal_review(signal, performance, store_instance.lessons_for_strategy(signal.strategyId), raw_settings)
    if isinstance(review_response, tuple):
        review_payload, error = review_response
    else:
        review_payload, error = review_response, ""
    if review_payload is None:
        return performance.model_copy(
            update={
                "reviewStatus": "failed",
                "reviewSummary": error,
                "reviewGeneratedAt": _now_iso(),
                "reviewSource": "llm",
                "updatedAt": _now_iso(),
            }
        ), None

    result = _normalize_review_result(str(review_payload.get("result") or "weak"))
    suggestions = [
        str(item).strip()
        for item in review_payload.get("improvementIdeas", [])
        if str(item).strip()
    ]
    suggested_rule_changes = [
        item
        for item in review_payload.get("suggestedRuleChanges", [])
        if isinstance(item, dict)
    ]
    now_iso = _now_iso()
    updated_performance = performance.model_copy(
        update={
            "reviewStatus": "generated",
            "reviewResult": result,
            "reviewSummary": str(review_payload.get("summary") or ""),
            "reviewAnalysis": str(review_payload.get("analysis") or ""),
            "reviewSuggestions": suggestions,
            "reviewGeneratedAt": now_iso,
            "reviewSource": "llm",
            "updatedAt": now_iso,
        }
    )
    lesson = StrategyLesson(
        id=f"lesson-{uuid4().hex[:10]}",
        strategyId=signal.strategyId,
        signalId=signal.id,
        result=result,
        failureReason=str(review_payload.get("failureReason") or ""),
        effectivePattern=str(review_payload.get("effectivePattern") or ""),
        improvementIdeas=suggestions,
        suggestedRuleChanges=[
            {str(key): str(value) for key, value in item.items()}
            for item in suggested_rule_changes
        ],
        confidence=max(0, min(1, float(review_payload.get("confidence") or 0))),
        createdAt=now_iso,
    )
    return updated_performance, lesson


def _normalize_review_result(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"effective", "weak", "failed", "insufficient_data"}:
        return normalized
    return "weak"


def _call_llm_for_signal_review(
    signal: Signal,
    performance: SignalPerformance,
    lessons: list[StrategyLesson],
    raw_settings: dict[str, Any],
) -> tuple[dict[str, Any] | None, str]:
    llm_settings = _llm_settings_from_raw(raw_settings)
    prompt = _build_signal_review_prompt(signal, performance, lessons)
    return _call_llm_for_strategy(prompt, llm_settings)


def _build_signal_review_prompt(signal: Signal, performance: SignalPerformance, lessons: list[StrategyLesson]) -> str:
    lesson_summary = [
        {
            "result": lesson.result,
            "failureReason": lesson.failureReason,
            "effectivePattern": lesson.effectivePattern,
            "improvementIdeas": lesson.improvementIdeas,
            "confidence": lesson.confidence,
        }
        for lesson in lessons[:8]
    ]
    payload = {
        "signal": signal.model_dump(exclude={"candles", "performance"}),
        "performance": performance.model_dump(exclude={"reviewAnalysis", "reviewSummary", "reviewSuggestions"}),
        "recentStrategyLessons": lesson_summary,
    }
    return (
        "你是量化策略复盘助手。请基于真实信号后续表现和同策略历史经验输出严格 JSON，"
        "不要编造没有数据支持的结论。JSON 字段必须包含 result, summary, analysis, "
        "failureReason, effectivePattern, improvementIdeas, suggestedRuleChanges, confidence。\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def _market_kline_period_progress(tasks: list[MarketKlineBackfillTask]) -> list[MarketKlinePeriodProgress]:
    progress: list[MarketKlinePeriodProgress] = []
    for period in MARKET_KLINE_COLLECTION_PERIODS:
        period_tasks = [task for task in tasks if task.period == period]
        counts = Counter(task.status for task in period_tasks)
        total = len(period_tasks)
        completed = counts.get("completed", 0)
        progress.append(
            MarketKlinePeriodProgress(
                period=period,  # type: ignore[arg-type]
                total=total,
                completed=completed,
                running=counts.get("running", 0),
                pending=counts.get("pending", 0),
                failed=counts.get("failed", 0),
                progressPercent=round((completed / total) * 100, 1) if total else 100.0,
            )
        )
    return progress


def _market_kline_recent_tasks(
    tasks: list[MarketKlineBackfillTask],
    collection_state: dict[str, Any],
    cleanup_state: dict[str, Any],
) -> list[MarketKlineRecentTask]:
    recent: list[MarketKlineRecentTask] = []
    for task in sorted(tasks, key=lambda item: (item.updatedAt, item.symbol, item.period), reverse=True):
        if task.status not in {"completed", "failed"}:
            continue
        recent.append(
            MarketKlineRecentTask(
                type="backfill",
                status="完成" if task.status == "completed" else "失败",
                target=f"{task.symbol} {task.period}",
                amount=f"{task.storedCandles:,} 根",
                updatedAt=task.updatedAt,
                note=task.lastError or ("已补齐窗口" if task.status == "completed" else "等待重试"),
            )
        )
        if len(recent) >= 6:
            break

    if collection_state.get("lastTriggeredAt"):
        recent.append(
            MarketKlineRecentTask(
                type="incremental",
                status="完成" if not collection_state.get("lastError") else "异常",
                target="增量更新",
                amount=f"{int(collection_state.get('lastStoredCandles') or 0):,} 根",
                updatedAt=collection_state.get("lastTriggeredAt"),
                note=f"跳过 {int(collection_state.get('lastSkippedPairs') or 0):,} 个组合",
            )
        )
    if cleanup_state.get("lastTriggeredAt") or cleanup_state.get("lastCleanupDate"):
        recent.append(
            MarketKlineRecentTask(
                type="cleanup",
                status="完成" if not cleanup_state.get("lastError") else "异常",
                target="数据清理",
                amount=f"删除 {int(cleanup_state.get('lastDeletedCandles') or 0):,} 根",
                updatedAt=cleanup_state.get("lastTriggeredAt"),
                note=f"清理日期 {cleanup_state.get('lastCleanupDate') or '--'}",
            )
        )
    return recent[:8]


def _market_kline_status_risks(
    failed_tasks: int,
    pending_tasks: int,
    running_tasks: int,
    collection_state: dict[str, Any],
    cleanup_state: dict[str, Any],
) -> list[str]:
    risks: list[str] = []
    if failed_tasks:
        risks.append(f"失败任务 {failed_tasks} 个，需要查看错误原因并等待重试。")
    if pending_tasks or running_tasks:
        risks.append("历史补齐运行中，策略扫描可能等待 K 线写入窗口。")
    if collection_state.get("lastError"):
        risks.append(f"增量更新最近错误：{collection_state['lastError']}")
    if cleanup_state.get("lastError"):
        risks.append(f"数据清理最近错误：{cleanup_state['lastError']}")
    if not risks:
        risks.append("当前无明显异常。")
    return risks


_market_radar_snapshot_lock = threading.Lock()
_market_radar_snapshot_stop_event: threading.Event | None = None
_market_radar_snapshot_thread: threading.Thread | None = None
_market_radar_snapshot_state: dict[str, Any] = {
    "running": False,
    "refreshing": False,
    "checkIntervalSeconds": 300,
    "lastCheckedAt": None,
    "lastTriggeredAt": None,
    "lastRefreshedPeriod": None,
    "lastError": "",
}


def run_market_radar_snapshot_scheduler_tick(
    store_instance: Any,
    check_time: datetime | None = None,
) -> str | None:
    now = check_time or datetime.now(timezone.utc)
    with _market_radar_snapshot_lock:
        if _market_radar_snapshot_state.get("refreshing"):
            return None
        _market_radar_snapshot_state["lastCheckedAt"] = _now_iso()
        _market_radar_snapshot_state["lastError"] = ""
        _market_radar_snapshot_state["refreshing"] = True
    try:
        period = "1H"
        store_instance.refresh_market_radar_snapshot(period, now)
        with _market_radar_snapshot_lock:
            _market_radar_snapshot_state["lastTriggeredAt"] = _now_iso()
            _market_radar_snapshot_state["lastRefreshedPeriod"] = period
        return period
    except Exception as exc:
        with _market_radar_snapshot_lock:
            _market_radar_snapshot_state["lastError"] = str(exc)
        return None
    finally:
        with _market_radar_snapshot_lock:
            _market_radar_snapshot_state["refreshing"] = False


def start_market_radar_snapshot_scheduler(store_instance: Any, check_interval_seconds: int = 300) -> None:
    global _market_radar_snapshot_stop_event, _market_radar_snapshot_thread
    with _market_radar_snapshot_lock:
        if _market_radar_snapshot_thread is not None and _market_radar_snapshot_thread.is_alive():
            return
        _market_radar_snapshot_stop_event = threading.Event()
        _market_radar_snapshot_state.update(
            {
                "running": True,
                "checkIntervalSeconds": check_interval_seconds,
                "lastError": "",
            }
        )
        _market_radar_snapshot_thread = threading.Thread(
            target=_market_radar_snapshot_loop,
            args=(store_instance, check_interval_seconds, _market_radar_snapshot_stop_event),
            daemon=True,
        )
        _market_radar_snapshot_thread.start()


def stop_market_radar_snapshot_scheduler() -> None:
    global _market_radar_snapshot_stop_event, _market_radar_snapshot_thread
    with _market_radar_snapshot_lock:
        stop_event = _market_radar_snapshot_stop_event
        thread = _market_radar_snapshot_thread
        _market_radar_snapshot_stop_event = None
        _market_radar_snapshot_thread = None
        _market_radar_snapshot_state["running"] = False
        _market_radar_snapshot_state["refreshing"] = False
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


def _market_radar_snapshot_loop(
    store_instance: Any,
    check_interval_seconds: int,
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        run_market_radar_snapshot_scheduler_tick(store_instance)
        if stop_event.wait(check_interval_seconds):
            break


_market_kline_coverage_snapshot_lock = threading.Lock()
_market_kline_coverage_snapshot_stop_event: threading.Event | None = None
_market_kline_coverage_snapshot_thread: threading.Thread | None = None
_market_kline_coverage_snapshot_state: dict[str, Any] = {
    "running": False,
    "refreshing": False,
    "checkIntervalSeconds": 300,
    "lastCheckedAt": None,
    "lastTriggeredAt": None,
    "lastRefreshedPeriod": None,
    "lastError": "",
}


def run_market_kline_coverage_snapshot_scheduler_tick(
    store_instance: Any,
    check_time: datetime | None = None,
) -> str | None:
    now = check_time or datetime.now(timezone.utc)
    with _market_kline_coverage_snapshot_lock:
        if _market_kline_coverage_snapshot_state.get("refreshing"):
            return None
        _market_kline_coverage_snapshot_state["lastCheckedAt"] = _now_iso()
        _market_kline_coverage_snapshot_state["lastError"] = ""

    snapshots = {item.period for item in store_instance.market_kline_coverage_snapshot()}
    period = next((item for item in MARKET_KLINE_COLLECTION_PERIODS if item not in snapshots), None)
    if period is None:
        return None

    with _market_kline_coverage_snapshot_lock:
        _market_kline_coverage_snapshot_state["refreshing"] = True
    try:
        store_instance.refresh_market_kline_coverage_snapshot(period, now)
        with _market_kline_coverage_snapshot_lock:
            _market_kline_coverage_snapshot_state["lastTriggeredAt"] = _now_iso()
            _market_kline_coverage_snapshot_state["lastRefreshedPeriod"] = period
        return period
    except Exception as exc:
        with _market_kline_coverage_snapshot_lock:
            _market_kline_coverage_snapshot_state["lastError"] = str(exc)
        return None
    finally:
        with _market_kline_coverage_snapshot_lock:
            _market_kline_coverage_snapshot_state["refreshing"] = False


def start_market_kline_coverage_snapshot_scheduler(store_instance: Any, check_interval_seconds: int = 300) -> None:
    global _market_kline_coverage_snapshot_stop_event, _market_kline_coverage_snapshot_thread
    with _market_kline_coverage_snapshot_lock:
        if _market_kline_coverage_snapshot_thread is not None and _market_kline_coverage_snapshot_thread.is_alive():
            return
        _market_kline_coverage_snapshot_stop_event = threading.Event()
        _market_kline_coverage_snapshot_state.update(
            {
                "running": True,
                "checkIntervalSeconds": check_interval_seconds,
                "lastError": "",
            }
        )
        _market_kline_coverage_snapshot_thread = threading.Thread(
            target=_market_kline_coverage_snapshot_loop,
            args=(store_instance, check_interval_seconds, _market_kline_coverage_snapshot_stop_event),
            daemon=True,
        )
        _market_kline_coverage_snapshot_thread.start()


def stop_market_kline_coverage_snapshot_scheduler() -> None:
    global _market_kline_coverage_snapshot_stop_event, _market_kline_coverage_snapshot_thread
    with _market_kline_coverage_snapshot_lock:
        stop_event = _market_kline_coverage_snapshot_stop_event
        thread = _market_kline_coverage_snapshot_thread
        _market_kline_coverage_snapshot_stop_event = None
        _market_kline_coverage_snapshot_thread = None
        _market_kline_coverage_snapshot_state["running"] = False
        _market_kline_coverage_snapshot_state["refreshing"] = False
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


def _market_kline_coverage_snapshot_loop(
    store_instance: Any,
    check_interval_seconds: int,
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        run_market_kline_coverage_snapshot_scheduler_tick(store_instance)
        if stop_event.wait(check_interval_seconds):
            break


_market_kline_cleanup_lock = threading.Lock()
_market_kline_cleanup_stop_event: threading.Event | None = None
_market_kline_cleanup_thread: threading.Thread | None = None
_market_kline_cleanup_state: dict[str, Any] = {
    "running": False,
    "cleaning": False,
    "checkIntervalSeconds": 3600,
    "lastCheckedAt": None,
    "lastTriggeredAt": None,
    "lastCleanupDate": None,
    "lastDeletedCandles": 0,
    "lastDeletedByPeriod": {},
    "lastError": "",
}


def _market_kline_cleanup_is_cleaning() -> bool:
    with _market_kline_cleanup_lock:
        return bool(_market_kline_cleanup_state.get("cleaning"))


def _try_begin_market_kline_cleanup_run(cleanup_date: str) -> dict[str, Any] | None:
    with _market_kline_cleanup_lock:
        _market_kline_cleanup_state["lastCheckedAt"] = _now_iso()
        _market_kline_cleanup_state["lastError"] = ""
        if _market_kline_cleanup_state.get("lastCleanupDate") == cleanup_date:
            return {"deletedCandles": 0, "periods": {}, "skipped": "already_ran_today"}
        if _market_kline_cleanup_state.get("cleaning"):
            return {"deletedCandles": 0, "periods": {}, "skipped": "cleanup_running"}
        with _market_kline_collection_lock:
            if _market_kline_collection_state.get("collecting"):
                return {"deletedCandles": 0, "periods": {}, "skipped": "kline_busy"}
        with _market_kline_backfill_lock:
            if int(_market_kline_backfill_state.get("activeExecutions") or 0) > 0:
                return {"deletedCandles": 0, "periods": {}, "skipped": "kline_busy"}
        _market_kline_cleanup_state["cleaning"] = True
        return None


def run_market_kline_cleanup_scheduler_tick(
    store_instance: Any,
    now: datetime | None = None,
    batch_size: int = MARKET_KLINE_CLEANUP_BATCH_SIZE,
) -> dict[str, Any]:
    check_time = _as_utc(now or datetime.now(timezone.utc))
    cleanup_date = check_time.date().isoformat()
    early_result = _try_begin_market_kline_cleanup_run(cleanup_date)
    if early_result is not None:
        return early_result

    try:
        deleted_by_period = store_instance.delete_old_market_klines(check_time, batch_size)
        deleted_total = sum(deleted_by_period.values())
        with _market_kline_cleanup_lock:
            _market_kline_cleanup_state["lastTriggeredAt"] = _now_iso()
            _market_kline_cleanup_state["lastCleanupDate"] = cleanup_date
            _market_kline_cleanup_state["lastDeletedCandles"] = deleted_total
            _market_kline_cleanup_state["lastDeletedByPeriod"] = deleted_by_period
        return {"deletedCandles": deleted_total, "periods": deleted_by_period}
    except Exception as exc:
        with _market_kline_cleanup_lock:
            _market_kline_cleanup_state["lastError"] = str(exc)
        raise
    finally:
        with _market_kline_cleanup_lock:
            _market_kline_cleanup_state["cleaning"] = False


def start_market_kline_cleanup_scheduler(store_instance: Any, check_interval_seconds: int = 3600) -> None:
    global _market_kline_cleanup_stop_event, _market_kline_cleanup_thread
    with _market_kline_cleanup_lock:
        if _market_kline_cleanup_thread is not None and _market_kline_cleanup_thread.is_alive():
            return
        _market_kline_cleanup_stop_event = threading.Event()
        _market_kline_cleanup_state.update({"running": True, "checkIntervalSeconds": check_interval_seconds, "lastError": ""})
        _market_kline_cleanup_thread = threading.Thread(
            target=_market_kline_cleanup_loop,
            args=(store_instance, check_interval_seconds, _market_kline_cleanup_stop_event),
            daemon=True,
        )
        _market_kline_cleanup_thread.start()


def stop_market_kline_cleanup_scheduler() -> None:
    global _market_kline_cleanup_stop_event, _market_kline_cleanup_thread
    with _market_kline_cleanup_lock:
        stop_event = _market_kline_cleanup_stop_event
        thread = _market_kline_cleanup_thread
        _market_kline_cleanup_stop_event = None
        _market_kline_cleanup_thread = None
        _market_kline_cleanup_state["running"] = False
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


def _market_kline_cleanup_loop(store_instance: Any, check_interval_seconds: int, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            run_market_kline_cleanup_scheduler_tick(store_instance)
        except Exception as exc:
            with _market_kline_cleanup_lock:
                _market_kline_cleanup_state["lastCheckedAt"] = _now_iso()
                _market_kline_cleanup_state["lastError"] = str(exc)
        if stop_event.wait(check_interval_seconds):
            break


_market_kline_backfill_lock = threading.Lock()
_market_kline_backfill_stop_event: threading.Event | None = None
_market_kline_backfill_thread: threading.Thread | None = None
_market_kline_backfill_state: dict[str, Any] = {
    "running": False,
    "backfilling": False,
    "activeExecutions": 0,
    "checkIntervalSeconds": 30,
    "lastCheckedAt": None,
    "lastTriggeredAt": None,
    "currentSymbol": "",
    "currentPeriod": "",
    "completedPairs": 0,
    "totalPairs": 0,
    "storedCandles": 0,
    "lastError": "",
    "activeTaskIds": set(),
}


def _market_kline_backfill_is_backfilling() -> bool:
    with _market_kline_backfill_lock:
        return bool(_market_kline_backfill_state.get("backfilling")) or int(_market_kline_backfill_state.get("activeExecutions") or 0) > 0


def _begin_market_kline_backfill_execution(symbol: str, period: str) -> None:
    with _market_kline_backfill_lock:
        active_executions = int(_market_kline_backfill_state.get("activeExecutions") or 0) + 1
        _market_kline_backfill_state["activeExecutions"] = active_executions
        _market_kline_backfill_state["backfilling"] = active_executions > 0
        _market_kline_backfill_state["currentSymbol"] = symbol
        _market_kline_backfill_state["currentPeriod"] = period
        _market_kline_backfill_state["lastError"] = ""


def _finish_market_kline_backfill_execution() -> None:
    with _market_kline_backfill_lock:
        active_executions = max(0, int(_market_kline_backfill_state.get("activeExecutions") or 0) - 1)
        _market_kline_backfill_state["activeExecutions"] = active_executions
        _market_kline_backfill_state["backfilling"] = active_executions > 0
        if active_executions == 0:
            _market_kline_backfill_state["currentSymbol"] = ""
            _market_kline_backfill_state["currentPeriod"] = ""


def _market_kline_backfill_has_unfinished_tasks(store_instance: Any) -> bool:
    try:
        return any(task.status in {"pending", "running", "failed"} for task in store_instance.market_kline_backfill_tasks)
    except Exception:
        return False


def run_market_kline_backfill_scheduler_tick(
    store_instance: Any,
    now: datetime | None = None,
    max_pairs: int = BACKFILL_MAX_PAIRS_PER_TICK,
    max_pages_per_pair: int = BACKFILL_MAX_PAGES_PER_PAIR,
) -> dict[str, Any]:
    check_time = _as_utc(now or datetime.now(timezone.utc))
    with _market_kline_backfill_lock:
        _market_kline_backfill_state["lastCheckedAt"] = _now_iso()
        _market_kline_backfill_state["lastError"] = ""

    if _market_kline_cleanup_is_cleaning():
        return {"processedPairs": 0, "storedCandles": 0, "errors": [], "skipped": "cleanup_running"}

    if _market_kline_collection_is_collecting():
        return {"processedPairs": 0, "storedCandles": 0, "errors": [], "skipped": "incremental_collecting"}

    symbols = fetch_tradable_symbols()
    tasks = _ensure_market_kline_backfill_tasks(store_instance, symbols, check_time)
    candidate_tasks = _refresh_market_kline_backfill_candidate_tasks(
        store_instance,
        tasks,
        check_time,
        max_candidates=max(max_pairs * 2, max_pairs),
    )
    pending_tasks = [task for task in candidate_tasks if task.status in {"pending", "running", "failed"}][:max_pairs]
    errors: list[str] = []
    stored_candles = 0
    processed_pairs = 0

    with _market_kline_backfill_lock:
        _market_kline_backfill_state["backfilling"] = int(_market_kline_backfill_state.get("activeExecutions") or 0) > 0 or bool(pending_tasks)
        _market_kline_backfill_state["totalPairs"] = len(tasks)
        _market_kline_backfill_state["completedPairs"] = sum(1 for task in tasks if task.status == "completed")

    try:
        if pending_tasks:
            _begin_market_kline_backfill_execution("", "")
        for task in pending_tasks:
            claimed_task = _claim_market_kline_backfill_task(
                store_instance,
                task.id,
                expected_statuses={"pending", "running", "failed"},
            )
            if claimed_task is None:
                continue
            processed_pairs += 1
            with _market_kline_backfill_lock:
                _market_kline_backfill_state["currentSymbol"] = claimed_task.symbol
                _market_kline_backfill_state["currentPeriod"] = claimed_task.period
            try:
                updated_task, task_stored = _advance_market_kline_backfill_task(
                    store_instance,
                    claimed_task,
                    max_pages=max_pages_per_pair,
                )
                stored_candles += task_stored
                store_instance.upsert_market_kline_backfill_task(updated_task)
            except Exception as exc:
                errors.append(f"{claimed_task.symbol} / {claimed_task.period}: {exc}")
                failed = claimed_task.model_copy(
                    update={"status": "failed", "lastError": str(exc), "updatedAt": _now_iso()}
                )
                store_instance.upsert_market_kline_backfill_task(failed)
            finally:
                _release_market_kline_backfill_task_claim(claimed_task.id)

        refreshed_tasks = store_instance.market_kline_backfill_tasks
        with _market_kline_backfill_lock:
            _market_kline_backfill_state["lastTriggeredAt"] = _now_iso()
            _market_kline_backfill_state["completedPairs"] = sum(1 for task in refreshed_tasks if task.status == "completed")
            _market_kline_backfill_state["totalPairs"] = len(refreshed_tasks)
            _market_kline_backfill_state["storedCandles"] = stored_candles
            _market_kline_backfill_state["lastError"] = "\n".join(errors[:3])
    finally:
        if pending_tasks:
            _finish_market_kline_backfill_execution()

    return {"processedPairs": processed_pairs, "storedCandles": stored_candles, "errors": errors}


def start_market_kline_backfill_scheduler(store_instance: Any, check_interval_seconds: int = 10) -> None:
    global _market_kline_backfill_stop_event, _market_kline_backfill_thread
    with _market_kline_backfill_lock:
        if _market_kline_backfill_thread is not None and _market_kline_backfill_thread.is_alive():
            return
        _market_kline_backfill_stop_event = threading.Event()
        _market_kline_backfill_state.update({"running": True, "checkIntervalSeconds": check_interval_seconds, "lastError": ""})
        _market_kline_backfill_thread = threading.Thread(
            target=_market_kline_backfill_loop,
            args=(store_instance, check_interval_seconds, _market_kline_backfill_stop_event),
            daemon=True,
        )
        _market_kline_backfill_thread.start()


def stop_market_kline_backfill_scheduler() -> None:
    global _market_kline_backfill_stop_event, _market_kline_backfill_thread
    with _market_kline_backfill_lock:
        stop_event = _market_kline_backfill_stop_event
        thread = _market_kline_backfill_thread
        _market_kline_backfill_stop_event = None
        _market_kline_backfill_thread = None
        _market_kline_backfill_state["running"] = False
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


def _market_kline_backfill_loop(store_instance: Any, check_interval_seconds: int, stop_event: threading.Event) -> None:
    while not stop_event.wait(check_interval_seconds):
        try:
            run_market_kline_backfill_scheduler_tick(store_instance)
        except Exception as exc:
            with _market_kline_backfill_lock:
                _market_kline_backfill_state["lastCheckedAt"] = _now_iso()
                _market_kline_backfill_state["lastError"] = str(exc)


def _ensure_market_kline_backfill_tasks(store_instance: Any, symbols: list[str], now: datetime) -> list[MarketKlineBackfillTask]:
    existing = {task.id: task for task in store_instance.market_kline_backfill_tasks}
    for symbol in symbols:
        normalized_symbol = symbol.upper()
        for period in MARKET_KLINE_NATIVE_PERIODS:
            target_start = _market_kline_target_start(period, now)
            target_end = _latest_period_boundary(period, now)
            task_id = _market_kline_backfill_task_id(normalized_symbol, period)
            if task_id in existing:
                continue
            missing_window = _market_kline_first_missing_window(
                store_instance,
                normalized_symbol,
                period,
                target_start,
                target_end,
            )
            if missing_window is not None:
                task_target_start, task_target_end = missing_window
                next_start = task_target_start
                status = "pending"
            else:
                task_target_start = target_start
                task_target_end = target_end
                next_start = _market_kline_initial_backfill_start(
                    store_instance,
                    normalized_symbol,
                    period,
                    target_start,
                    target_end,
                )
                status = "completed" if next_start >= target_end else "pending"
            task = MarketKlineBackfillTask(
                id=task_id,
                symbol=normalized_symbol,
                period=period,  # type: ignore[arg-type]
                targetStart=task_target_start.isoformat(),
                targetEnd=task_target_end.isoformat(),
                nextStart=next_start.isoformat(),
                status=status,  # type: ignore[arg-type]
                createdAt=_now_iso(),
                updatedAt=_now_iso(),
            )
            store_instance.upsert_market_kline_backfill_task(task)
    period_order = {period: index for index, period in enumerate(MARKET_KLINE_NATIVE_PERIODS)}
    priority_symbols = _market_kline_backfill_priority_symbols(store_instance)
    return sorted(
        store_instance.market_kline_backfill_tasks,
        key=lambda task: (
            1 if task.status == "completed" else 0,
            _market_kline_backfill_symbol_priority(task.symbol, priority_symbols),
            task.symbol,
            period_order.get(task.period, 999),
        ),
    )


def _refresh_market_kline_backfill_candidate_tasks(
    store_instance: Any,
    tasks: list[MarketKlineBackfillTask],
    now: datetime,
    max_candidates: int,
) -> list[MarketKlineBackfillTask]:
    refreshed_by_id: dict[str, MarketKlineBackfillTask] = {}
    for task in tasks[:max_candidates]:
        target_start = _market_kline_target_start(task.period, now)
        target_end = _latest_period_boundary(task.period, now)
        refreshed = _refresh_market_kline_backfill_task_window(store_instance, task, target_start, target_end)
        refreshed_by_id[task.id] = refreshed
        if refreshed != task:
            store_instance.upsert_market_kline_backfill_task(refreshed)
    if not refreshed_by_id:
        return tasks
    return [refreshed_by_id.get(task.id, task) for task in tasks]


def _claim_market_kline_backfill_task(
    store_instance: Any,
    task_id: str,
    expected_statuses: set[str],
) -> MarketKlineBackfillTask | None:
    with _market_kline_backfill_lock:
        active_task_ids = set(_market_kline_backfill_state.get("activeTaskIds") or set())
        if task_id in active_task_ids:
            return None
        latest_task = next((item for item in store_instance.market_kline_backfill_tasks if item.id == task_id), None)
        if latest_task is None or latest_task.status not in expected_statuses:
            return None
        active_task_ids.add(task_id)
        _market_kline_backfill_state["activeTaskIds"] = active_task_ids
        claimed_task = latest_task.model_copy(update={"status": "running", "updatedAt": _now_iso()})
        try:
            store_instance.upsert_market_kline_backfill_task(claimed_task)
        except Exception:
            active_task_ids.discard(task_id)
            _market_kline_backfill_state["activeTaskIds"] = active_task_ids
            raise
        return claimed_task


def _release_market_kline_backfill_task_claim(task_id: str) -> None:
    with _market_kline_backfill_lock:
        active_task_ids = set(_market_kline_backfill_state.get("activeTaskIds") or set())
        active_task_ids.discard(task_id)
        _market_kline_backfill_state["activeTaskIds"] = active_task_ids


def _market_kline_backfill_priority_symbols(store_instance: Any) -> set[str]:
    symbols = {symbol.upper() for symbol in MARKET_KLINE_PRIORITY_SYMBOLS}
    for item in getattr(store_instance, "watchlist", []) or []:
        symbol = getattr(item, "symbol", "")
        if symbol:
            symbols.add(str(symbol).upper())
    for signal in getattr(store_instance, "signals", []) or []:
        symbol = getattr(signal, "symbol", "")
        if symbol:
            symbols.add(str(symbol).upper())
    return symbols


def _market_kline_backfill_symbol_priority(symbol: str, priority_symbols: set[str]) -> int:
    normalized = symbol.upper()
    if normalized in priority_symbols:
        return 0
    return 10


def _refresh_market_kline_backfill_task_window(
    store_instance: Any,
    task: MarketKlineBackfillTask,
    target_start: datetime,
    target_end: datetime,
) -> MarketKlineBackfillTask:
    current_target_end = _parse_datetime(task.targetEnd)
    current_next_start = _parse_datetime(task.nextStart)
    missing_window = _market_kline_first_missing_window(
        store_instance,
        task.symbol,
        task.period,
        target_start,
        target_end,
        allow_full_window_when_empty=False,
    )
    if missing_window is not None:
        gap_start, gap_end = missing_window
        update: dict[str, Any] = {
            "targetStart": gap_start.isoformat(),
            "targetEnd": gap_end.isoformat(),
            "nextStart": gap_start.isoformat(),
        }
        if task.status == "completed":
            update["status"] = "pending"
        if (
            task.targetStart == update["targetStart"]
            and task.targetEnd == update["targetEnd"]
            and task.nextStart == update["nextStart"]
            and "status" not in update
        ):
            return task
        update["updatedAt"] = _now_iso()
        return task.model_copy(update=update)

    if current_target_end is None or current_next_start is None:
        return task.model_copy(
            update={
                "targetStart": target_start.isoformat(),
                "targetEnd": target_end.isoformat(),
                "nextStart": target_start.isoformat(),
                "status": "pending",
                "updatedAt": _now_iso(),
            }
        )

    next_start = max(_as_utc(current_next_start), target_start)
    update: dict[str, Any] = {}
    if task.targetStart != target_start.isoformat():
        update["targetStart"] = target_start.isoformat()
    if _as_utc(current_target_end) < target_end:
        update["targetEnd"] = target_end.isoformat()
        if task.status == "completed":
            update["nextStart"] = min(max(_as_utc(current_target_end), target_start), target_end).isoformat()
            update["status"] = "running"
    elif next_start != _as_utc(current_next_start):
        update["nextStart"] = min(next_start, target_end).isoformat()
        if task.status != "completed":
            update["status"] = "pending"

    if not update:
        return task
    update["updatedAt"] = _now_iso()
    return task.model_copy(update=update)


def _market_kline_initial_backfill_start(
    store_instance: Any,
    symbol: str,
    period: str,
    target_start: datetime,
    target_end: datetime,
) -> datetime:
    earliest, latest = store_instance.market_kline_time_range(symbol, period)
    if earliest is None or latest is None:
        return target_start
    earliest_utc = _as_utc(earliest)
    latest_utc = _as_utc(latest)
    if earliest_utc > target_start:
        return target_start
    return min(latest_utc + timedelta(seconds=_period_seconds(period)), target_end)


def _market_kline_first_missing_window(
    store_instance: Any,
    symbol: str,
    period: str,
    target_start: datetime,
    target_end: datetime,
    *,
    allow_full_window_when_empty: bool = True,
) -> tuple[datetime, datetime] | None:
    normalized_start = _first_expected_market_kline_time(target_start, period)
    normalized_end = _as_utc(target_end)
    if normalized_start >= normalized_end:
        return None

    with store_instance._connect() as connection:
        cursor = connection.cursor()
        cursor.execute(
            f"""
            SELECT open_time FROM `{MARKET_KLINE_TABLE}`
            WHERE symbol = %s AND period = %s AND open_time >= %s AND open_time < %s
            ORDER BY open_time ASC
            """,
            (symbol.upper(), str(period).upper(), normalized_start.isoformat(), normalized_end.isoformat()),
        )
        rows = cursor.fetchall()

    expected_step = timedelta(seconds=_period_seconds(period))
    last_seen_time: datetime | None = None
    for row in rows:
        parsed_time = _parse_datetime(str(row[0] or ""))
        if parsed_time is None:
            continue
        open_time = _as_utc(parsed_time)
        if open_time < normalized_start:
            continue
        if last_seen_time is not None:
            expected_next_time = last_seen_time + expected_step
            if open_time > expected_next_time:
                return expected_next_time, min(open_time, normalized_end)
        last_seen_time = open_time

    if last_seen_time is None:
        if not allow_full_window_when_empty:
            return None
        return normalized_start, normalized_end

    trailing_start = last_seen_time + expected_step
    if trailing_start < normalized_end:
        return trailing_start, normalized_end
    return None


def _advance_market_kline_backfill_task(
    store_instance: Any,
    task: MarketKlineBackfillTask,
    max_pages: int,
) -> tuple[MarketKlineBackfillTask, int]:
    next_start = _parse_datetime(task.nextStart)
    target_end = _parse_datetime(task.targetEnd)
    if next_start is None or target_end is None:
        raise ValueError("Backfill task time range is invalid")
    current_start = _as_utc(next_start)
    target_end = _as_utc(target_end)
    if current_start >= target_end:
        return task.model_copy(update={"status": "completed", "updatedAt": _now_iso()}), 0

    stored_candles = 0
    pages_fetched = task.pagesFetched
    for page_index in range(max_pages):
        candles = fetch_market_candles_range(task.symbol, task.period, current_start, target_end, BACKFILL_PAGE_LIMIT)
        if not candles:
            current_start = target_end
            break
        store_instance.upsert_market_candles(task.symbol, task.period, candles)
        stored_candles += len(candles)
        pages_fetched += 1
        last_time = _parse_datetime(candles[-1].time)
        current_start = (_as_utc(last_time) + timedelta(seconds=_period_seconds(task.period))) if last_time else target_end
        if current_start >= target_end:
            break
        if page_index < max_pages - 1 and BACKFILL_REQUEST_SLEEP_SECONDS > 0:
            time.sleep(BACKFILL_REQUEST_SLEEP_SECONDS)

    status = "completed" if current_start >= target_end else "running"
    return task.model_copy(
        update={
            "status": status,
            "nextStart": min(current_start, target_end).isoformat(),
            "pagesFetched": pages_fetched,
            "storedCandles": task.storedCandles + stored_candles,
            "lastError": "",
            "updatedAt": _now_iso(),
        }
    ), stored_candles


def _market_kline_target_start(period: str, now: datetime) -> datetime:
    cutoff = _market_kline_retention_cutoffs(now)[str(period).upper()]
    parsed = _parse_datetime(cutoff)
    if parsed is None:
        raise ValueError(f"Invalid market kline retention cutoff for {period}: {cutoff}")
    return _as_utc(parsed)


def _market_kline_backfill_task_id(symbol: str, period: str) -> str:
    return f"mkbf-{symbol.upper()}-{str(period).upper()}"


_market_kline_collection_lock = threading.Lock()
_market_kline_collection_stop_event: threading.Event | None = None
_market_kline_collection_thread: threading.Thread | None = None
_market_kline_collection_state: dict[str, Any] = {
    "running": False,
    "collecting": False,
    "checkIntervalSeconds": 60,
    "lastCheckedAt": None,
    "lastTriggeredAt": None,
    "lastCollectedBoundaries": {},
    "lastStoredCandles": 0,
    "lastSkippedPairs": 0,
    "lastError": "",
}


def _market_kline_collection_is_collecting() -> bool:
    with _market_kline_collection_lock:
        return bool(_market_kline_collection_state.get("collecting"))


def run_market_kline_collection_scheduler_tick(
    store_instance: Any,
    now: datetime | None = None,
) -> dict[str, Any]:
    check_time = _as_utc(now or datetime.now(timezone.utc))
    due_periods = _market_kline_collection_due_periods(check_time)
    with _market_kline_collection_lock:
        _market_kline_collection_state["lastCheckedAt"] = _now_iso()
        _market_kline_collection_state["lastError"] = ""

    if not due_periods:
        return {"periods": [], "symbols": 0, "storedCandles": 0, "errors": []}

    if _market_kline_cleanup_is_cleaning():
        return {"periods": [], "symbols": 0, "storedCandles": 0, "errors": [], "skipped": "cleanup_running"}

    if _market_kline_backfill_is_backfilling():
        return {"periods": [], "symbols": 0, "storedCandles": 0, "errors": [], "skipped": "backfill_running"}

    with _market_kline_collection_lock:
        _market_kline_collection_state["collecting"] = True

    try:
        symbols = fetch_tradable_symbols()
        errors: list[str] = []
        stored_candles = 0
        skipped_pairs = 0
        completed_boundaries: dict[str, str] = {}
        backfill_status_by_pair = {
            (task.symbol.upper(), task.period.upper()): task.status for task in store_instance.market_kline_backfill_tasks
        }

        for period in due_periods:
            boundary = _latest_period_boundary(period, check_time).isoformat()
            for symbol in symbols:
                status = backfill_status_by_pair.get((symbol.upper(), period.upper()))
                if status is not None and status != "completed":
                    skipped_pairs += 1
                    continue
                try:
                    candles = fetch_market_candles(symbol, period, limit=INCREMENTAL_KLINE_LIMIT)
                    store_instance.upsert_market_candles(symbol, period, candles)
                    stored_candles += len(candles)
                except Exception as exc:
                    errors.append(f"{period} / {symbol}: {exc}")
            completed_boundaries[period] = boundary

        with _market_kline_collection_lock:
            collected = dict(_market_kline_collection_state.get("lastCollectedBoundaries") or {})
            collected.update(completed_boundaries)
            _market_kline_collection_state["lastCollectedBoundaries"] = collected
            _market_kline_collection_state["lastTriggeredAt"] = _now_iso()
            _market_kline_collection_state["lastStoredCandles"] = stored_candles
            _market_kline_collection_state["lastSkippedPairs"] = skipped_pairs
            if errors:
                _market_kline_collection_state["lastError"] = "\n".join(errors[:3])
    finally:
        with _market_kline_collection_lock:
            _market_kline_collection_state["collecting"] = False

    return {
        "periods": due_periods,
        "symbols": len(symbols),
        "storedCandles": stored_candles,
        "skippedPairs": skipped_pairs,
        "errors": errors,
    }


def _market_kline_collection_due_periods(now: datetime) -> list[str]:
    with _market_kline_collection_lock:
        collected = dict(_market_kline_collection_state.get("lastCollectedBoundaries") or {})
    due_periods: list[str] = []
    for period in MARKET_KLINE_NATIVE_PERIODS:
        boundary = _latest_period_boundary(period, now).isoformat()
        if collected.get(period) != boundary:
            due_periods.append(period)
    return due_periods


def start_market_kline_collection_scheduler(store_instance: Any, check_interval_seconds: int = 60) -> None:
    global _market_kline_collection_stop_event, _market_kline_collection_thread
    with _market_kline_collection_lock:
        if _market_kline_collection_thread is not None and _market_kline_collection_thread.is_alive():
            return
        _market_kline_collection_stop_event = threading.Event()
        _market_kline_collection_state.update(
            {
                "running": True,
                "checkIntervalSeconds": check_interval_seconds,
                "lastError": "",
            }
        )
        _market_kline_collection_thread = threading.Thread(
            target=_market_kline_collection_loop,
            args=(store_instance, check_interval_seconds, _market_kline_collection_stop_event),
            daemon=True,
        )
        _market_kline_collection_thread.start()


def stop_market_kline_collection_scheduler() -> None:
    global _market_kline_collection_stop_event, _market_kline_collection_thread
    with _market_kline_collection_lock:
        stop_event = _market_kline_collection_stop_event
        thread = _market_kline_collection_thread
        _market_kline_collection_stop_event = None
        _market_kline_collection_thread = None
        _market_kline_collection_state["running"] = False
    if stop_event is not None:
        stop_event.set()
    if thread is not None and thread.is_alive():
        thread.join(timeout=2)


def _market_kline_collection_loop(store_instance: Any, check_interval_seconds: int, stop_event: threading.Event) -> None:
    while not stop_event.is_set():
        try:
            run_market_kline_collection_scheduler_tick(store_instance)
        except Exception as exc:
            with _market_kline_collection_lock:
                _market_kline_collection_state["lastCheckedAt"] = _now_iso()
                _market_kline_collection_state["lastError"] = str(exc)
        if stop_event.wait(check_interval_seconds):
            break


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
    normalized_period = str(period).upper()
    interval = _binance_interval(normalized_period)

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


def fetch_market_candles_range(
    symbol: str,
    period: str,
    start_time: datetime,
    end_time: datetime,
    limit: int = BACKFILL_PAGE_LIMIT,
) -> list[Candle]:
    normalized_period = str(period).upper()
    interval = _binance_interval(normalized_period)
    start_utc = _as_utc(start_time)
    end_utc = _as_utc(end_time)
    if start_utc >= end_utc:
        return []

    query = urllib.parse.urlencode({
        "symbol": symbol.upper(),
        "interval": interval,
        "startTime": str(int(start_utc.timestamp() * 1000)),
        "endTime": str(int(end_utc.timestamp() * 1000)),
        "limit": str(min(max(1, limit), 1500)),
    })
    url = f"https://fapi.binance.com/fapi/v1/klines?{query}"
    raw_payload = _read_url_with_retry(url, timeout=10)
    rows = json.loads(raw_payload)
    if not isinstance(rows, list):
        raise ValueError("Invalid Binance kline response")

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
        for row in rows
        if isinstance(row, list)
        and len(row) >= 6
        and start_utc <= datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc) < end_utc
    ]
    _populate_moving_averages(candles)
    return candles


def _binance_interval(period: str) -> str:
    interval_map = {"5M": "5m", "15M": "15m", "1H": "1h", "4H": "4h", "1D": "1d"}
    interval = interval_map.get(str(period).upper())
    if interval is None:
        raise ValueError(f"Unsupported period: {period}")
    return interval


def _period_seconds(period: str) -> int:
    return {"5M": 300, "15M": 900, "1H": 3600, "4H": 14400, "1D": 86400}[str(period).upper()]


def _floor_datetime_to_period(value: datetime, period: str) -> datetime:
    utc_value = _as_utc(value)
    seconds = _period_seconds(period)
    floored_timestamp = int(utc_value.timestamp()) // seconds * seconds
    return datetime.fromtimestamp(floored_timestamp, tz=timezone.utc)


def _aggregate_market_candles(source_candles: list[Candle], period: str) -> list[Candle]:
    normalized_period = str(period).upper()
    expected_count = _period_seconds(normalized_period) // _period_seconds("5M")
    if expected_count <= 1:
        return []

    grouped: dict[str, list[Candle]] = {}
    for candle in source_candles:
        candle_time = _parse_datetime(candle.time)
        if candle_time is None:
            continue
        bucket_start = _floor_datetime_to_period(candle_time, normalized_period).isoformat()
        grouped.setdefault(bucket_start, []).append(candle)

    aggregated: list[Candle] = []
    for bucket_start, bucket_candles in sorted(grouped.items()):
        ordered = sorted(bucket_candles, key=lambda item: item.time)
        if len(ordered) != expected_count:
            continue
        aggregated.append(
            Candle(
                time=bucket_start,
                open=ordered[0].open,
                high=max(candle.high for candle in ordered),
                low=min(candle.low for candle in ordered),
                close=ordered[-1].close,
                volume=sum(candle.volume for candle in ordered),
                ma5=0,
                ma20=0,
                ma60=0,
            )
        )
    _populate_moving_averages(aggregated)
    return aggregated


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
    try:
        exec(compile(code, "<strategy-runtime>", "exec"), namespace, namespace)
    except Exception as exc:
        raise ValueError(_format_strategy_exception(exc)) from exc
    check_signal = namespace.get("check_signal")
    if not callable(check_signal):
        raise ValueError("策略代码缺少 check_signal(candles) 函数")

    candle_payload = [candle.model_dump() if isinstance(candle, BaseModel) else candle for candle in candles]
    if _strategy_uses_dataframe_style(code):
        candle_payload = _strategy_dataframe_payload(candle_payload)
    try:
        result = _call_check_signal(check_signal, candle_payload)
    except Exception as exc:
        raise ValueError(_format_strategy_exception(exc)) from exc
    if strict_return and not isinstance(result, bool):
        raise ValueError("check_signal(candles) 必须返回 bool 类型 True 或 False")
    return bool(result)


def _strategy_uses_dataframe_style(code: str) -> bool:
    return bool(
        re.search(r"\bcandles\s*\[\s*['\"]", code)
        or ".iloc" in code
        or ".loc" in code
        or ".rolling(" in code
        or ".between(" in code
    )


def _strategy_dataframe_payload(candle_payload: list[Any]) -> Any:
    try:
        import pandas as pd
    except ImportError as exc:
        raise ValueError("策略代码使用了 DataFrame 写法，但后端未安装 pandas，请执行 pip install -r backend/requirements.txt") from exc

    return pd.DataFrame(candle_payload)


def _call_check_signal(check_signal: Any, candle_payload: list[Any]) -> Any:
    try:
        signature = inspect.signature(check_signal)
        required_positionals = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)
            and parameter.default is parameter.empty
        ]
    except (TypeError, ValueError):
        required_positionals = []

    if len(required_positionals) >= 2:
        return check_signal(candle_payload, max(0, len(candle_payload) - 1))
    return check_signal(candle_payload)


def _format_strategy_exception(exc: Exception) -> str:
    if isinstance(exc, SyntaxError) and exc.lineno is not None:
        return f"第 {exc.lineno} 行：{exc.msg}"

    line_number: int | None = None
    traceback = exc.__traceback__
    while traceback is not None:
        if traceback.tb_frame.f_code.co_filename == "<strategy-runtime>":
            line_number = traceback.tb_lineno
        traceback = traceback.tb_next

    if line_number is not None:
        return f"第 {line_number} 行：{exc}"
    return str(exc)


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
        if response.status_code >= 400:
            return None, f"LLM HTTP {response.status_code}: {_response_excerpt(response.text)}"

        try:
            response_payload = response.json()
        except Exception as exc:
            return None, f"LLM response is not JSON: {exc}; body={_response_excerpt(response.text)}"

        content = response_payload.get("choices", [{}])[0].get("message", {}).get("content")
        if not str(content or "").strip():
            return None, f"LLM message content is empty; body={_response_excerpt(json.dumps(response_payload, ensure_ascii=False))}"

        try:
            return _json_loads(_strip_json_fence(str(content))), ""
        except Exception as exc:
            return None, f"LLM message content is not valid strategy JSON: {exc}; content={_response_excerpt(str(content))}"
    except Exception as exc:
        return None, str(exc)


def _response_excerpt(value: str, limit: int = 300) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit] + ("..." if len(text) > limit else "")


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
    return MySQLStore()


store = create_store()
