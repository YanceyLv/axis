import os
import inspect
import time
from datetime import datetime, timedelta, timezone

from pathlib import Path

env_path = Path(__file__).resolve().parents[1] / ".env"
if env_path.exists():
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))

os.environ["MYSQL_DATABASE"] = "axis_test"
os.environ["ALLOW_MYSQL_RESET"] = "1"

import pytest
from fastapi.testclient import TestClient

from app.main import app
import app.store as store_module
from app.models import (
    AppSettingsUpdate,
    Candle,
    CreateStrategyRequest,
    KnowledgeCase,
    LlmSettingsUpdate,
    MarketKlineBackfillTask,
    MarketKlineCoverage,
    PushoverSettingsUpdate,
    Signal,
    StrategyScanHistory,
    WatchCondition,
    WatchItem,
)
from app.store import MySQLStore, _normalize_generated_strategy, store


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    store.reset()
    store_module._run_job_state = None
    store_module._market_kline_collection_state["collecting"] = False
    store_module._market_kline_collection_state["lastCollectedBoundaries"] = {}
    store_module._market_kline_collection_state["lastSkippedPairs"] = 0
    if hasattr(store_module, "_market_kline_backfill_state"):
        store_module._market_kline_backfill_state["backfilling"] = False
    if hasattr(store_module, "_market_kline_cleanup_state"):
        store_module._market_kline_cleanup_state["cleaning"] = False
        store_module._market_kline_cleanup_state["lastCleanupDate"] = None


def auth_headers(email: str = "authed@example.com") -> dict[str, str]:
    response = client.post(
        "/api/auth/register",
        json={"email": email, "password": "StrongPass123"},
    )
    token = response.json()["token"]
    return {"Authorization": f"Bearer {token}"}


def sample_candles(seed: float = 1.0, count: int = 24) -> list[Candle]:
    return [
        Candle(
            time=f"2026-05-31T{i:02d}:00:00+08:00",
            open=seed + i * 0.01,
            high=seed + i * 0.01 + 0.02,
            low=seed + i * 0.01 - 0.02,
            close=seed + i * 0.01 + 0.01,
            volume=1000 + i * 10,
            ma5=seed + i * 0.01,
            ma20=seed + i * 0.01 - 0.01,
            ma60=seed + i * 0.01 - 0.02,
        )
        for i in range(count)
    ]


def market_candles(seed: float = 1.0, count: int = 240, start: datetime | None = None, step_minutes: int = 60) -> list[Candle]:
    start_time = start or datetime(2026, 5, 20, 0, 0, 0, tzinfo=timezone.utc)
    return [
        Candle(
            time=(start_time + i * timedelta(minutes=step_minutes)).isoformat(),
            open=seed + i * 0.01,
            high=seed + i * 0.01 + 0.02,
            low=seed + i * 0.01 - 0.02,
            close=seed + i * 0.01 + 0.01,
            volume=1000 + i * 10,
            ma5=seed + i * 0.01,
            ma20=seed + i * 0.01 - 0.01,
            ma60=seed + i * 0.01 - 0.02,
        )
        for i in range(count)
    ]


def trend_candles(
    start_price: float,
    step: float,
    count: int = 40,
    volume: float = 1000,
    volume_step: float = 0,
    start: datetime | None = None,
    step_minutes: int = 60,
) -> list[Candle]:
    start_time = start or datetime(2026, 5, 20, 0, 0, 0, tzinfo=timezone.utc)
    candles: list[Candle] = []
    price = start_price
    for index in range(count):
        close = price + step
        high = max(price, close) + abs(step) * 0.5 + 0.01
        low = min(price, close) - abs(step) * 0.5 - 0.01
        candles.append(
            Candle(
                time=(start_time + index * timedelta(minutes=step_minutes)).isoformat(),
                open=price,
                high=high,
                low=low,
                close=close,
                volume=volume + index * volume_step,
                ma5=close,
                ma20=close,
                ma60=close,
            )
        )
        price = close
    return candles


def seed_market_candles(symbol: str, period: str = "1H", seed: float = 1.0, count: int = 240) -> None:
    store.upsert_market_candles(symbol, period, market_candles(seed, count=count))


def mysql_test_store(database_suffix: str) -> MySQLStore:
    test_store = MySQLStore(database=f"axis_test_{database_suffix}")
    test_store.reset()
    return test_store


def insert_sample_signal(signal_id: str = "sig-sample", symbol: str = "ALLUSDT", period: str = "1H") -> Signal:
    signal = Signal(
        id=signal_id,
        symbol=symbol,
        period=period,
        strategyId="seed-strategy",
        strategyName="测试行情种子",
        signalType="seed",
        score=80,
        triggeredAt="2026-05-31T10:00:00+08:00",
        price=1.23,
        summary="用于测试的行情 K 线。",
        analysis=["测试行情"],
        strengthGrade="A",
        candles=sample_candles(1.0),
    )
    store._upsert("signals", signal, store._next_front_order("signals"))
    return signal


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_and_login_with_email():
    register_response = client.post(
        "/api/auth/register",
        json={"email": "trader@example.com", "password": "StrongPass123"},
    )
    assert register_response.status_code == 200
    registered = register_response.json()
    assert registered["user"]["email"] == "trader@example.com"
    assert registered["token"]

    login_response = client.post(
        "/api/auth/login",
        json={"email": "trader@example.com", "password": "StrongPass123"},
    )
    assert login_response.status_code == 200
    logged_in = login_response.json()
    assert logged_in["user"]["email"] == "trader@example.com"
    assert logged_in["token"]


def test_register_rejects_duplicate_email():
    payload = {"email": "duplicate@example.com", "password": "StrongPass123"}
    assert client.post("/api/auth/register", json=payload).status_code == 200

    duplicate_response = client.post("/api/auth/register", json=payload)

    assert duplicate_response.status_code == 409
    assert duplicate_response.json()["code"] == "EMAIL_ALREADY_REGISTERED"


def test_login_rejects_wrong_password():
    client.post(
        "/api/auth/register",
        json={"email": "wrong-password@example.com", "password": "StrongPass123"},
    )

    response = client.post(
        "/api/auth/login",
        json={"email": "wrong-password@example.com", "password": "bad-password"},
    )

    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_CREDENTIALS"


def test_dashboard_requires_authentication():
    response = client.get("/api/dashboard/summary")

    assert response.status_code == 401
    assert response.json()["code"] == "AUTH_REQUIRED"


def test_settings_can_save_llm_api_and_pushover_without_returning_secrets():
    headers = auth_headers("settings@example.com")

    default_response = client.get("/api/settings", headers=headers)
    assert default_response.status_code == 200
    assert default_response.json()["llm"]["apiKeySet"] is False
    assert default_response.json()["pushover"]["enabled"] is False

    save_response = client.put(
        "/api/settings",
        headers=headers,
        json={
            "llm": {
                "provider": "openai",
                "baseUrl": "https://api.openai.com/v1",
                "model": "gpt-4.1",
                "apiKey": "llm-key",
            },
            "pushover": {
                "enabled": True,
                "userKey": "pushover-user",
                "appToken": "pushover-token",
            },
        },
    )

    assert save_response.status_code == 200
    body = save_response.json()
    assert body["llm"]["provider"] == "openai"
    assert body["llm"]["baseUrl"] == "https://api.openai.com/v1"
    assert body["llm"]["model"] == "gpt-4.1"
    assert body["llm"]["apiKeySet"] is True
    assert body["pushover"]["enabled"] is True
    assert body["pushover"]["userKeySet"] is True
    assert body["pushover"]["appTokenSet"] is True
    assert "llm-key" not in str(body)
    assert "pushover-token" not in str(body)


def test_new_coin_listing_scan_persists_and_deduplicates(monkeypatch):
    headers = auth_headers("new-coins@example.com")

    monkeypatch.setattr(
        store_module,
        "fetch_binance_new_listing_announcements",
        lambda: [
            {
                "id": "binance-listing-abc",
                "symbol": "ABC",
                "tradingPairs": ["ABCUSDT"],
                "title": "Binance Will List Alpha Beta Coin (ABC)",
                "url": "https://www.binance.com/en/support/announcement/binance-listing-abc",
                "announcedAt": "2026-06-05T10:00:00+00:00",
                "listedAt": None,
                "status": "upcoming",
                "source": "binance",
            }
        ],
    )

    first_scan = client.post("/api/new-coins/scan", headers=headers)
    second_scan = client.post("/api/new-coins/scan", headers=headers)
    list_response = client.get("/api/new-coins", headers=headers)

    assert first_scan.status_code == 200
    assert first_scan.json()["fetched"] == 1
    assert first_scan.json()["created"] == 1
    assert second_scan.status_code == 200
    assert second_scan.json()["created"] == 0
    assert list_response.status_code == 200
    listings = list_response.json()
    assert len(listings) == 1
    assert listings[0]["symbol"] == "ABC"
    assert listings[0]["tradingPairs"] == ["ABCUSDT"]
    assert listings[0]["notifiedAt"] is None


def test_new_coin_listing_scan_sends_pushover_for_new_items(monkeypatch):
    headers = auth_headers("new-coin-push@example.com")
    calls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout=8):
        calls.append((request, timeout))
        return FakeResponse()

    client.put(
        "/api/settings",
        json={
            "llm": {"provider": "openai", "baseUrl": "", "model": "", "apiKey": ""},
            "pushover": {"enabled": True, "userKey": "pushover-user", "appToken": "pushover-token"},
        },
        headers=headers,
    )
    monkeypatch.setattr(store_module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(
        store_module,
        "fetch_binance_new_listing_announcements",
        lambda: [
            {
                "id": "binance-listing-xyz",
                "symbol": "XYZ",
                "tradingPairs": ["XYZUSDT"],
                "title": "Binance Will List Xylophone Yield Zone (XYZ)",
                "url": "https://www.binance.com/en/support/announcement/binance-listing-xyz",
                "announcedAt": "2026-06-05T11:00:00+00:00",
                "listedAt": None,
                "status": "upcoming",
                "source": "binance",
            }
        ],
    )

    first_scan = client.post("/api/new-coins/scan", headers=headers)
    second_scan = client.post("/api/new-coins/scan", headers=headers)

    assert first_scan.status_code == 200
    assert first_scan.json()["created"] == 1
    assert second_scan.status_code == 200
    assert second_scan.json()["created"] == 0
    assert len(calls) == 1
    sent_body = calls[0][0].data.decode("utf-8")
    assert "XYZ" in sent_body


def test_store_starts_without_mock_entities():
    assert store.strategies == []
    assert store.signals == []
    assert store.watchlist == []
    assert store.knowledge_cases == []


def test_dashboard_summary():
    response = client.get("/api/dashboard/summary", headers=auth_headers())
    assert response.status_code == 200
    body = response.json()
    assert body["todaySignals"] == 0
    assert body["latestSignals"] == []


def test_strategy_generation_and_save():
    headers = auth_headers()
    generate_response = client.post(
        "/api/strategies/generate",
        json={"period": "1H", "conditions": ["近10天振幅小于30%", "价格站上MA20"]},
        headers=headers,
    )
    assert generate_response.status_code == 200
    generated = generate_response.json()
    assert generated["strengthGrade"] == "A"
    assert generated["summary"]
    assert generated["tags"]
    assert generated["structuredConditions"][0]["title"]
    assert generated["structuredConditions"][0]["parameters"]
    assert generated["riskAdvice"]["stopLoss"]
    assert generated["nextStep"]
    assert generated["pythonCode"]
    assert generated["aiAnalysis"]
    assert generated["triggerFlow"]
    assert generated["historyStats"]["winRate"] >= 0
    assert generated["generationSource"] in ["llm", "fallback"]

    save_response = client.post("/api/strategies", json=generated, headers=headers)
    assert save_response.status_code == 200
    saved = save_response.json()
    assert saved["source"] == "ai"
    assert saved["runtime"]["language"] == "python"
    assert saved["runtime"]["entrypoint"] == "check_signal"
    assert saved["runtime"]["code"] == generated["pythonCode"]
    assert saved["runtime"]["structuredConditions"] == generated["structuredConditions"]
    assert saved["runtime"]["aiAnalysis"] == generated["aiAnalysis"]
    assert saved["schedule"]["enabled"] is True
    assert saved["schedule"]["intervalSeconds"] == 300


def test_llm_strategy_generation_tolerates_null_optional_metrics():
    generated = _normalize_generated_strategy(
        {
            "name": "LLM 生成策略",
            "period": "1H",
            "description": "模型返回的策略",
            "conditions": ["价格站上 MA20"],
            "signalType": "趋势启动类信号",
            "strengthGrade": "A",
            "score": 91,
            "summary": "模型返回的总结",
            "historyStats": {
                "winRate": None,
                "profitLossRatio": None,
                "averageHoldingHours": None,
            },
        },
        "1H",
        ["价格站上 MA20"],
        {"provider": "custom", "model": "gpt-5.4", "baseUrl": "https://pinduyun.net/v1"},
    )

    assert generated.generationSource == "llm"
    assert generated.historyStats.winRate is None
    assert generated.historyStats.profitLossRatio is None
    assert generated.historyStats.averageHoldingHours is None


def test_llm_strategy_generation_is_cached_for_same_period_and_conditions(monkeypatch):
    cache_store = mysql_test_store("cache")
    cache_store.update_settings(
        AppSettingsUpdate(
            llm=LlmSettingsUpdate(
                provider="custom",
                baseUrl="https://example.com/v1",
                model="test-model",
                apiKey="secret",
            ),
            pushover=PushoverSettingsUpdate(),
        )
    )
    calls = {"count": 0}

    def fake_llm_call(prompt, llm_settings):
        calls["count"] += 1
        return {
            "name": f"LLM 策略 {calls['count']}",
            "period": "1H",
            "description": "模型生成内容",
            "conditions": ["价格站上 MA20"],
            "signalType": "趋势启动类信号",
            "strengthGrade": "A",
            "score": 91,
            "summary": "模型生成总结",
        }, ""

    monkeypatch.setattr(store_module, "_call_llm_for_strategy", fake_llm_call)

    first = cache_store.generate_strategy("1H", ["价格站上 MA20"])
    second = cache_store.generate_strategy("1H", ["价格站上 MA20"])
    third = cache_store.generate_strategy("1H", ["价格站上 MA20"], force_refresh=True)

    assert calls["count"] == 2
    assert first.name == "LLM 策略 1"
    assert first.generationCached is False
    assert second.name == "LLM 策略 1"
    assert second.generationCached is True
    assert third.name == "LLM 策略 2"
    assert third.generationCached is False


def test_strategy_generation_from_code_preserves_pasted_code(monkeypatch):
    code_store = mysql_test_store("code_import")
    code_store.update_settings(
        AppSettingsUpdate(
            llm=LlmSettingsUpdate(
                provider="custom",
                baseUrl="https://example.com/v1",
                model="test-model",
                apiKey="secret",
            ),
            pushover=PushoverSettingsUpdate(),
        )
    )
    pasted_code = "def check_signal(candles):\n    return len(candles) > 1"

    def fake_llm_call(prompt, llm_settings):
        return {
            "name": "代码解析策略",
            "period": "1H",
            "description": "由代码解析",
            "conditions": ["代码条件"],
            "signalType": "代码信号",
            "strengthGrade": "B",
            "score": 76,
            "pythonCode": "def check_signal(candles):\n    return False",
            "structuredConditions": [
                {"title": "代码条件", "description": "读取粘贴代码得到的条件", "parameters": ["根数：2"]}
            ],
        }, ""

    monkeypatch.setattr(store_module, "_call_llm_for_strategy", fake_llm_call)

    generated = code_store.generate_strategy_from_code("1H", pasted_code)

    assert generated.name == "代码解析策略"
    assert generated.pythonCode == pasted_code
    assert generated.structuredConditions[0].title == "代码条件"


def test_placeholder_python_code_cache_is_ignored(monkeypatch):
    cache_store = mysql_test_store("cache_placeholder")
    cache_store.update_settings(
        AppSettingsUpdate(
            llm=LlmSettingsUpdate(
                provider="custom",
                baseUrl="https://example.com/v1",
                model="test-model",
                apiKey="secret",
            ),
            pushover=PushoverSettingsUpdate(),
        )
    )
    calls = {"count": 0}

    def fake_llm_call(prompt, llm_settings):
        calls["count"] += 1
        code = "def check_signal(candles):\n    return True" if calls["count"] == 1 else (
            "def check_signal(candles):\n"
            "    if len(candles) < 24:\n"
            "        return False\n"
            "    recent = candles[-10:]\n"
            "    volumes = [c['volume'] for c in candles[-24:]]\n"
            "    above_ma20 = sum(1 for c in recent if c['close'] > c['ma20']) >= 8\n"
            "    compressed = max(c['high'] for c in recent) / min(c['low'] for c in recent) < 1.30\n"
            "    avg_volume = sum(volumes[:-1]) / len(volumes[:-1])\n"
            "    volume_breakout = volumes[-1] > avg_volume * 3\n"
            "    return above_ma20 and compressed and volume_breakout\n"
        )
        return {
            "name": f"LLM 策略 {calls['count']}",
            "period": "1H",
            "description": "模型生成内容",
            "conditions": ["价格站上 MA20"],
            "signalType": "趋势启动类信号",
            "strengthGrade": "A",
            "score": 91,
            "summary": "模型生成总结",
            "pythonCode": code,
        }, ""

    monkeypatch.setattr(store_module, "_call_llm_for_strategy", fake_llm_call)

    first = cache_store.generate_strategy("1H", ["价格站上 MA20"])
    second = cache_store.generate_strategy("1H", ["价格站上 MA20"])
    third = cache_store.generate_strategy("1H", ["价格站上 MA20"])

    assert first.pythonCode.strip().endswith("return True")
    assert second.name == "LLM 策略 2"
    assert second.generationCached is False
    assert third.name == "LLM 策略 2"
    assert third.generationCached is True


def test_mysql_store_persists_created_strategy():
    database = "axis_test_persist_strategy"
    first_store = mysql_test_store("persist_strategy")
    first_store.create_strategy(
        CreateStrategyRequest(
            name="持久化策略",
            period="1H",
            description="验证数据库重开后数据仍然存在。",
            conditions=["价格站上 MA20"],
        )
    )

    second_store = MySQLStore(database=database)
    assert second_store.strategies[0].name == "持久化策略"


def test_mysql_store_persists_strategy_scan_history():
    database = "axis_test_persist_history"
    first_store = mysql_test_store("persist_history")
    first_store.save_strategy_scan_history(
        StrategyScanHistory(
            id="run-history-persisted",
            strategyName="持久化扫描策略",
            period="1H",
            status="completed",
            startedAt="2026-06-01T00:00:00+00:00",
            finishedAt="2026-06-01T00:01:00+00:00",
            elapsedSeconds=60,
            strategiesChecked=1,
            totalSymbols=528,
            scannedSymbols=528,
            signalsCreated=3,
            errorsCount=0,
            skippedSymbols=2,
        )
    )

    second_store = MySQLStore(database=database)
    history = second_store.get_strategy_run_history()

    assert history[0].id == "run-history-persisted"
    assert history[0].strategyName == "持久化扫描策略"
    assert history[0].signalsCreated == 3


def test_mysql_reset_is_blocked_by_default(monkeypatch):
    monkeypatch.delenv("ALLOW_MYSQL_RESET", raising=False)
    mysql_store = object.__new__(MySQLStore)
    mysql_store.database = "axis"

    with pytest.raises(RuntimeError, match="Refusing to reset MySQL database"):
        mysql_store.reset()


def test_run_saved_strategy_creates_signal_from_python_runtime(monkeypatch):
    headers = auth_headers("runner@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ALLUSDT"])
    seed_market_candles("ALLUSDT", "1H", seed=1.0)
    save_response = client.post(
        "/api/strategies",
        json={
            "name": "运行测试策略",
            "period": "1H",
            "description": "用于验证保存后的 Python 策略可以执行。",
            "conditions": ["始终命中"],
            "signalType": "趋势信号",
            "score": 92,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return len(candles) > 0",
            "structuredConditions": [
                {"title": "测试条件", "description": "有 K 线即可命中", "parameters": ["根数：1根"]}
            ],
            "aiAnalysis": ["测试 runner 写入信号"],
        },
        headers=headers,
    )
    assert save_response.status_code == 200
    strategy_id = save_response.json()["id"]

    run_response = client.post("/api/strategies/run-once", headers=headers)

    assert run_response.status_code == 200
    body = run_response.json()
    assert body["strategiesChecked"] >= 1
    assert body["signalsCreated"] >= 1
    assert any(item["strategyId"] == strategy_id for item in body["createdSignals"])

    updated_strategy = next(strategy for strategy in client.get("/api/strategies", headers=headers).json() if strategy["id"] == strategy_id)
    assert updated_strategy["todaySignalCount"] >= 1
    assert updated_strategy["lastTriggeredAt"]
    assert updated_strategy["schedule"]["lastRunAt"]
    assert updated_strategy["schedule"]["lastStatus"] == "success"


def test_kline_collection_scheduler_tick_fetches_native_periods_for_all_symbols(monkeypatch):
    calls = []

    def fake_fetch(symbol: str, period: str, limit: int = 240):
        calls.append((symbol, period, limit))
        step_minutes = 5 if period == "5M" else 1440
        return market_candles(2.0, count=limit, step_minutes=step_minutes)

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ETHUSDT", "SOLUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles", fake_fetch)

    result = store_module.run_market_kline_collection_scheduler_tick(
        store,
        datetime(2026, 6, 1, 10, 15, 30, tzinfo=timezone.utc),
    )

    assert result["symbols"] == 2
    assert result["periods"] == ["5M", "1D"]
    assert result["storedCandles"] == 2 * 2 * store_module.INCREMENTAL_KLINE_LIMIT
    assert calls == [
        (symbol, period, store_module.INCREMENTAL_KLINE_LIMIT)
        for period in ["5M", "1D"]
        for symbol in ["ETHUSDT", "SOLUSDT"]
    ]
    assert len(store.latest_market_candles("ETHUSDT", "5M")) == store_module.INCREMENTAL_KLINE_LIMIT
    assert len(store.latest_market_candles("SOLUSDT", "1D")) == store_module.INCREMENTAL_KLINE_LIMIT
    assert len(store.latest_market_candles("ETHUSDT", "15M")) >= 1


def test_market_kline_backfill_scheduler_advances_limited_tasks(monkeypatch):
    calls = []

    def fake_range(symbol: str, period: str, start_time: datetime, end_time: datetime, limit: int = 500):
        calls.append((symbol, period, start_time.isoformat(), end_time.isoformat(), limit))
        return market_candles(5.0, count=3, start=start_time, step_minutes=60)

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ETHUSDT", "SOLUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles_range", fake_range)

    result = store_module.run_market_kline_backfill_scheduler_tick(
        store,
        datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        max_pairs=2,
        max_pages_per_pair=1,
    )

    assert result["processedPairs"] == 2
    assert result["storedCandles"] == 6
    assert len(calls) == 2
    assert all(call[4] == store_module.BACKFILL_PAGE_LIMIT for call in calls)
    tasks = store.market_kline_backfill_tasks
    assert len(tasks) == 4
    running_tasks = [task for task in tasks if task.status == "running"]
    assert len(running_tasks) == 2
    assert [task.storedCandles for task in running_tasks] == [3, 3]


def test_market_kline_backfill_uses_accelerated_defaults():
    signature = inspect.signature(store_module.start_market_kline_backfill_scheduler)

    assert store_module.BACKFILL_PAGE_LIMIT == 1500
    assert store_module.BACKFILL_MAX_PAIRS_PER_TICK == 20
    assert store_module.BACKFILL_MAX_PAGES_PER_PAIR == 2
    assert store_module.BACKFILL_REQUEST_SLEEP_SECONDS == 0
    assert signature.parameters["check_interval_seconds"].default == 10


def test_market_kline_retention_uses_short_intraday_and_long_daily_windows():
    cutoffs = store_module._market_kline_retention_cutoffs(datetime(2026, 6, 11, 12, 0, 0, tzinfo=timezone.utc))

    assert cutoffs["5M"] == datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    assert cutoffs["15M"] == datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    assert cutoffs["1H"] == datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    assert cutoffs["4H"] == datetime(2026, 5, 12, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    assert cutoffs["1D"] == datetime(2025, 6, 11, 12, 0, 0, tzinfo=timezone.utc).isoformat()


def test_market_kline_backfill_prioritizes_major_symbols(monkeypatch):
    calls = []

    def fake_range(symbol: str, period: str, start_time: datetime, end_time: datetime, limit: int = 500):
        calls.append((symbol, period))
        return []

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["0GUSDT", "BTCUSDT", "ETHUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles_range", fake_range)

    result = store_module.run_market_kline_backfill_scheduler_tick(
        store,
        datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        max_pairs=3,
        max_pages_per_pair=1,
    )

    assert result["processedPairs"] == 3
    assert calls == [("BTCUSDT", "5M"), ("BTCUSDT", "1D"), ("ETHUSDT", "5M")]


def test_market_kline_backfill_prioritizes_signal_symbols(monkeypatch):
    calls = []
    insert_sample_signal("sig-backfill-priority", "ZKUSDT", "1H")

    def fake_range(symbol: str, period: str, start_time: datetime, end_time: datetime, limit: int = 500):
        calls.append((symbol, period))
        return []

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["0GUSDT", "ZKUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles_range", fake_range)

    result = store_module.run_market_kline_backfill_scheduler_tick(
        store,
        datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        max_pairs=2,
        max_pages_per_pair=1,
    )

    assert result["processedPairs"] == 2
    assert calls == [("ZKUSDT", "5M"), ("ZKUSDT", "1D")]


def test_market_kline_collection_collects_completed_pairs_while_backfill_tasks_are_unfinished(monkeypatch):
    calls = []
    created_at = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()
    for symbol, status, next_start in [
        ("BTCUSDT", "pending", datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc)),
        ("ETHUSDT", "completed", datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)),
    ]:
        for period in ["5M", "1D"]:
            store.upsert_market_kline_backfill_task(
                MarketKlineBackfillTask(
                    id=f"mkbf-{symbol}-{period}",
                    symbol=symbol,
                    period=period,
                    targetStart=datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
                    targetEnd=datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
                    nextStart=next_start.isoformat(),
                    status=status,
                    createdAt=created_at,
                    updatedAt=created_at,
                )
            )

    def fake_fetch(symbol: str, period: str, limit: int = 5):
        calls.append((symbol, period, limit))
        return market_candles(8.0, count=limit)

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["BTCUSDT", "ETHUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles", fake_fetch)

    result = store_module.run_market_kline_collection_scheduler_tick(
        store,
        datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert result["symbols"] == 2
    assert result["storedCandles"] == 2 * store_module.INCREMENTAL_KLINE_LIMIT
    assert result["skippedPairs"] == 2
    assert calls == [
        ("ETHUSDT", period, store_module.INCREMENTAL_KLINE_LIMIT)
        for period in ["5M", "1D"]
    ]


def test_upserting_5m_candles_refreshes_derived_kline_cache():
    start = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    candles = market_candles(10.0, count=12, start=start, step_minutes=5)

    store.upsert_market_candles("ETHUSDT", "5M", candles)

    fifteen = store.latest_market_candles("ETHUSDT", "15M", 10)
    hourly = store.latest_market_candles("ETHUSDT", "1H", 10)
    four_hour = store.latest_market_candles("ETHUSDT", "4H", 10)

    assert [item.time for item in fifteen] == [
        datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        datetime(2026, 6, 1, 0, 15, 0, tzinfo=timezone.utc).isoformat(),
        datetime(2026, 6, 1, 0, 30, 0, tzinfo=timezone.utc).isoformat(),
        datetime(2026, 6, 1, 0, 45, 0, tzinfo=timezone.utc).isoformat(),
    ]
    assert fifteen[0].open == candles[0].open
    assert fifteen[0].high == max(candle.high for candle in candles[:3])
    assert fifteen[0].low == min(candle.low for candle in candles[:3])
    assert fifteen[0].close == candles[2].close
    assert fifteen[0].volume == sum(candle.volume for candle in candles[:3])
    assert len(hourly) == 1
    assert hourly[0].open == candles[0].open
    assert hourly[0].close == candles[-1].close
    assert len(four_hour) == 0


def test_market_kline_backfill_starts_after_existing_latest_candle(monkeypatch):
    calls = []
    store.upsert_market_candles(
        "ETHUSDT",
        "5M",
        [
                *market_candles(
                    6.0,
                    count=1,
                    start=datetime(2026, 3, 12, 12, 0, 0, tzinfo=timezone.utc),
                    step_minutes=5,
                ),
                *market_candles(
                    6.3,
                    count=1,
                    start=datetime(2026, 6, 9, 10, 0, 0, tzinfo=timezone.utc),
                    step_minutes=5,
                ),
        ],
    )

    def fake_range(symbol: str, period: str, start_time: datetime, end_time: datetime, limit: int = 500):
        calls.append((symbol, period, start_time, end_time, limit))
        return []

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ETHUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles_range", fake_range)

    store_module.run_market_kline_backfill_scheduler_tick(
        store,
        datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc),
        max_pairs=5,
        max_pages_per_pair=1,
    )

    five_minute_call = next(call for call in calls if call[1] == "5M")
    assert five_minute_call[2] == datetime(2026, 6, 9, 10, 5, 0, tzinfo=timezone.utc)


def test_market_kline_backfill_reopens_completed_task_when_target_end_moves(monkeypatch):
    calls = []
    now_iso = datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc).isoformat()
    store.upsert_market_kline_backfill_task(
        MarketKlineBackfillTask(
            id="mkbf-ETHUSDT-1H",
            symbol="ETHUSDT",
            period="1H",
            targetStart=datetime(2026, 3, 3, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
            targetEnd=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc).isoformat(),
            nextStart=datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc).isoformat(),
            status="completed",
            createdAt=now_iso,
            updatedAt=now_iso,
        )
    )

    def fake_range(symbol: str, period: str, start_time: datetime, end_time: datetime, limit: int = 500):
        calls.append((symbol, period, start_time, end_time, limit))
        return []

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ETHUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles_range", fake_range)

    store_module.run_market_kline_backfill_scheduler_tick(
        store,
        datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
        max_pairs=5,
        max_pages_per_pair=1,
    )

    one_hour_call = next(call for call in calls if call[1] == "1H")
    assert one_hour_call[2] == datetime(2026, 6, 1, 10, 0, 0, tzinfo=timezone.utc)
    assert one_hour_call[3] == datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc)


def test_market_kline_status_summarizes_collection_jobs():
    headers = auth_headers("kline-status@example.com")
    now_iso = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    for symbol, period, status, stored in [
        ("BTCUSDT", "5M", "completed", 12),
        ("ETHUSDT", "5M", "running", 6),
        ("SOLUSDT", "15M", "pending", 0),
        ("BNBUSDT", "1H", "failed", 0),
    ]:
        store.upsert_market_kline_backfill_task(
            MarketKlineBackfillTask(
                id=f"mkbf-{symbol}-{period}",
                symbol=symbol,
                period=period,
                targetStart=datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
                targetEnd=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
                nextStart=datetime(2026, 6, 1, 6, 0, 0, tzinfo=timezone.utc).isoformat(),
                status=status,
                pagesFetched=2,
                storedCandles=stored,
                lastError="network timeout" if status == "failed" else "",
                createdAt=now_iso,
                updatedAt=now_iso,
            )
        )
    store.upsert_market_candles(
        "BTCUSDT",
        "5M",
        market_candles(10.0, count=2, start=datetime(2026, 6, 1, 11, 50, 0, tzinfo=timezone.utc), step_minutes=5),
    )
    store_module._market_kline_collection_state["lastTriggeredAt"] = now_iso
    store_module._market_kline_collection_state["lastStoredCandles"] = 5
    store_module._market_kline_collection_state["lastSkippedPairs"] = 3
    store_module._market_kline_cleanup_state["lastCleanupDate"] = "2026-06-01"
    store_module._market_kline_cleanup_state["lastDeletedCandles"] = 7

    response = client.get("/api/market/kline-status", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["overallStatus"] == "warning"
    assert body["activePhase"] == "历史补齐"
    assert body["cards"][0]["name"] == "K线历史补齐"
    assert body["cards"][0]["progressCurrent"] == 1
    assert body["cards"][0]["progressTotal"] == 4
    assert body["cards"][1]["primaryMetric"] == "写入 5 根"
    assert body["cards"][1]["secondaryMetric"] == "跳过 3 个组合"
    five_minute = next(item for item in body["periodProgress"] if item["period"] == "5M")
    assert five_minute["completed"] == 1
    assert five_minute["running"] == 1
    assert len(body["runningTasks"]) == 1
    assert body["runningTasks"][0]["symbol"] == "ETHUSDT"
    coverage = next(item for item in body["coverage"] if item["period"] == "5M")
    assert coverage["rows"] == 2
    assert coverage["symbols"] == 1
    assert any("失败任务 1 个" in risk for risk in body["risks"])


def test_market_kline_status_reads_persisted_coverage_snapshot(monkeypatch):
    headers = auth_headers("kline-status-snapshot@example.com")
    store.refresh_market_kline_coverage_snapshot("5M", datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc))

    def fail_full_scan(*args, **kwargs):
        raise AssertionError("status endpoint must not scan market_klines for coverage")

    monkeypatch.setattr(store, "_scan_market_kline_coverage", fail_full_scan)

    response = client.get("/api/market/kline-status", headers=headers)

    assert response.status_code == 200
    coverage = next(item for item in response.json()["coverage"] if item["period"] == "5M")
    assert coverage["rows"] == 0
    assert coverage["symbols"] == 0
    assert coverage["status"] == "empty"


def test_upsert_market_candles_refreshes_coverage_snapshot():
    store.upsert_market_candles(
        "FASTUSDT",
        "1D",
        market_candles(10.0, count=2, start=datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc), step_minutes=1440),
    )

    snapshot = store.market_kline_coverage_snapshot()
    one_day = next(item for item in snapshot if item.period == "1D")

    assert one_day.rows == 2
    assert one_day.symbols == 1
    assert one_day.earliestOpenTime == datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat()
    assert one_day.latestOpenTime == datetime(2026, 6, 2, 0, 0, 0, tzinfo=timezone.utc).isoformat()


def test_coverage_snapshot_scheduler_refreshes_one_missing_period(monkeypatch):
    refreshed: list[str] = []

    def fake_refresh(period: str, now: datetime | None = None):
        refreshed.append(period)
        return MarketKlineCoverage(
            period=period,
            rows=0,
            symbols=0,
            targetWindow="30天",
            status="empty",
            statusLabel="暂无数据",
        )

    monkeypatch.setattr(store, "refresh_market_kline_coverage_snapshot", fake_refresh)

    result = store_module.run_market_kline_coverage_snapshot_scheduler_tick(store)

    assert result == "5M"
    assert refreshed == ["5M"]


def test_upsert_market_candles_does_not_prune_old_klines():
    old_candles = market_candles(
        7.0,
        count=2,
        start=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        step_minutes=60,
    )

    store.upsert_market_candles("OLDUSDT", "1H", old_candles)

    assert len(store.latest_market_candles("OLDUSDT", "1H")) == 2


def test_market_kline_cleanup_scheduler_runs_once_per_day():
    old_candles = market_candles(
        8.0,
        count=3,
        start=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        step_minutes=60,
    )
    store.upsert_market_candles("CLEANUSDT", "1H", old_candles)

    first = store_module.run_market_kline_cleanup_scheduler_tick(
        store,
        datetime(2026, 6, 10, 2, 0, 0, tzinfo=timezone.utc),
        batch_size=10,
    )
    second = store_module.run_market_kline_cleanup_scheduler_tick(
        store,
        datetime(2026, 6, 10, 12, 0, 0, tzinfo=timezone.utc),
        batch_size=10,
    )

    assert first["deletedCandles"] == 3
    assert first["periods"]["1H"] == 3
    assert second["deletedCandles"] == 0
    assert second["skipped"] == "already_ran_today"


def test_market_kline_cleanup_scheduler_deletes_in_batches():
    old_candles = market_candles(
        9.0,
        count=5,
        start=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
        step_minutes=60,
    )
    store.upsert_market_candles("BATCHCLEANUSDT", "1H", old_candles)

    result = store_module.run_market_kline_cleanup_scheduler_tick(
        store,
        datetime(2026, 6, 11, 2, 0, 0, tzinfo=timezone.utc),
        batch_size=2,
    )

    assert result["deletedCandles"] == 2
    assert len(store.latest_market_candles("BATCHCLEANUSDT", "1H")) == 3


def test_market_kline_jobs_skip_while_cleanup_is_running(monkeypatch):
    headers = auth_headers("cleanup-busy@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["CLEANBUSYUSDT"])
    seed_market_candles("CLEANBUSYUSDT", "1H", seed=4.2)
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "K线清理中跳过策略",
            "period": "1H",
            "description": "K线清理未完成时不应启动扫描。",
            "conditions": ["始终命中"],
            "signalType": "趋势信号",
            "score": 89,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return True",
            "structuredConditions": [
                {"title": "测试条件", "description": "始终命中", "parameters": ["根数: 240根"]}
            ],
            "aiAnalysis": ["测试K线清理锁"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    store_module._market_kline_cleanup_state["cleaning"] = True

    try:
        collection = store_module.run_market_kline_collection_scheduler_tick(
            store,
            datetime(2026, 6, 1, 11, 0, 30, tzinfo=timezone.utc),
        )
        backfill = store_module.run_market_kline_backfill_scheduler_tick(
            store,
            datetime(2026, 6, 1, 11, 0, 30, tzinfo=timezone.utc),
        )
        triggered = store_module.run_strategy_scheduler_tick(
            store,
            datetime(2026, 6, 1, 11, 0, 30, tzinfo=timezone.utc),
        )
    finally:
        store_module._market_kline_cleanup_state["cleaning"] = False

    assert collection["skipped"] == "cleanup_running"
    assert backfill["skipped"] == "cleanup_running"
    assert triggered == 0


def test_scheduler_tick_skips_due_strategy_while_kline_backfill_is_running(monkeypatch):
    headers = auth_headers("scheduler-backfill-busy@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["BACKFILLUSDT"])
    seed_market_candles("BACKFILLUSDT", "1H", seed=4.2)
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "K线补齐中跳过策略",
            "period": "1H",
            "description": "历史补齐未完成时不应启动扫描。",
            "conditions": ["始终命中"],
            "signalType": "趋势信号",
            "score": 89,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return True",
            "structuredConditions": [
                {"title": "测试条件", "description": "始终命中", "parameters": ["根数: 240根"]}
            ],
            "aiAnalysis": ["测试K线历史补齐锁"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    store_module._market_kline_backfill_state["backfilling"] = True

    try:
        triggered = store_module.run_strategy_scheduler_tick(store, datetime(2026, 6, 1, 11, 0, 30, tzinfo=timezone.utc))
    finally:
        store_module._market_kline_backfill_state["backfilling"] = False

    assert triggered == 0
    assert client.get("/api/strategies/run-status", headers=headers).json()["jobId"] == ""


def test_market_klines_endpoint_returns_all_stored_candles_for_symbol_and_period():
    headers = auth_headers("market-klines@example.com")
    eth_15m = market_candles(10.0, count=12, step_minutes=15)
    eth_1h = market_candles(20.0, count=5, step_minutes=60)
    sol_15m = market_candles(30.0, count=7, step_minutes=15)
    store.upsert_market_candles("ETHUSDT", "15M", eth_15m)
    store.upsert_market_candles("ETHUSDT", "1H", eth_1h)
    store.upsert_market_candles("SOLUSDT", "15M", sol_15m)

    response = client.get("/api/market/klines/ethusdt?period=15M", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert [item["time"] for item in body] == [candle.time for candle in eth_15m]
    assert body[0]["close"] == eth_15m[0].close
    assert len(body) == 12


def test_market_radar_endpoint_scores_environment_and_recommends_symbols():
    headers = auth_headers("market-radar@example.com")
    base_time = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    store.upsert_market_candles(
        "BTCUSDT",
        "1H",
        trend_candles(100.0, 0.45, count=40, volume=1200, volume_step=12, start=base_time),
    )
    store.upsert_market_candles(
        "ETHUSDT",
        "1H",
        trend_candles(50.0, 0.25, count=40, volume=900, volume_step=9, start=base_time),
    )
    store.upsert_market_candles(
        "SOLUSDT",
        "1H",
        trend_candles(20.0, 0.35, count=40, volume=800, volume_step=80, start=base_time),
    )
    store.upsert_market_candles(
        "LINKUSDT",
        "1H",
        trend_candles(15.0, 0.12, count=40, volume=700, volume_step=12, start=base_time),
    )
    store.upsert_market_candles(
        "DOGEUSDT",
        "1H",
        trend_candles(8.0, -0.08, count=40, volume=650, volume_step=0, start=base_time),
    )

    response = client.get("/api/market/radar", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["environment"]["score"] >= 60
    assert body["environment"]["status"] in {"tradable", "watch_only"}
    assert body["metrics"]["symbolsAnalyzed"] == 5
    assert body["metrics"]["risingRatio"] > 50
    assert body["recommendations"][0]["symbol"] == "SOLUSDT"
    assert body["recommendations"][0]["score"] >= body["recommendations"][1]["score"]
    assert body["recommendations"][0]["riskLevel"] in {"low", "medium", "high"}
    assert body["opportunityGroups"]["breakout"] >= 1
    assert body["updatedAt"]


def test_run_strategy_uses_cached_market_candles_for_all_tradable_symbols(monkeypatch):
    headers = auth_headers("market-runner@example.com")

    def fail_fetch(symbol: str, period: str, limit: int = 240):
        raise AssertionError("strategy scan must read cached K-lines instead of fetching Binance data")

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ETHUSDT", "SOLUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles", fail_fetch)
    seed_market_candles("ETHUSDT", "1H", seed=2.0, count=24)
    seed_market_candles("SOLUSDT", "1H", seed=2.5, count=24)
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "行情扫描策略",
            "period": "1H",
            "description": "从观察池拉取真实行情后执行",
            "conditions": ["始终命中"],
            "signalType": "趋势信号",
            "score": 91,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return len(candles) >= 24",
            "structuredConditions": [
                {"title": "测试条件", "description": "需要真实 K 线", "parameters": ["根数：24根"]}
            ],
            "aiAnalysis": ["使用行情 provider 扫描"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    run_response = client.post("/api/strategies/run-once", headers=headers)

    assert run_response.status_code == 200
    body = run_response.json()
    assert body["symbolsChecked"] == 2
    assert body["signalsCreated"] == 2
    assert {item["symbol"] for item in body["createdSignals"]} == {"ETHUSDT", "SOLUSDT"}


def test_run_strategy_reuses_cached_candles_for_same_period_strategies(monkeypatch):
    headers = auth_headers("grouped-scan@example.com")
    read_calls = []
    original_latest = store.latest_market_candles

    def tracking_latest(symbol: str, period: str, limit: int = store_module.CLOSED_KLINE_LIMIT):
        read_calls.append((symbol, period, limit))
        return original_latest(symbol, period, limit)

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ETHUSDT", "SOLUSDT"])
    monkeypatch.setattr(store, "latest_market_candles", tracking_latest)
    seed_market_candles("ETHUSDT", "1H", seed=2.0, count=80)
    seed_market_candles("SOLUSDT", "1H", seed=2.5, count=80)

    for name, required in [("24根策略", 24), ("80根策略", 80)]:
        response = client.post(
            "/api/strategies",
            json={
                "name": name,
                "period": "1H",
                "description": f"需要 {required} 根 K 线。",
                "conditions": [f"至少 {required} 根 K 线"],
                "signalType": "趋势信号",
                "score": 88,
                "strengthGrade": "A",
                "pythonCode": f"def check_signal(candles):\n    return len(candles) >= {required}",
                "structuredConditions": [
                    {"title": "测试条件", "description": "需要足够 K 线", "parameters": [f"根数: {required}根"]}
                ],
                "aiAnalysis": ["测试同周期复用K线"],
            },
            headers=headers,
        )
        assert response.status_code == 200

    run_response = client.post("/api/strategies/run-once", headers=headers)

    assert run_response.status_code == 200
    body = run_response.json()
    assert body["symbolsChecked"] == 4
    assert body["signalsCreated"] == 4
    assert read_calls == [("ETHUSDT", "1H", 80), ("SOLUSDT", "1H", 80)]


def test_async_strategy_run_reuses_cached_candles_for_same_period_strategies(monkeypatch):
    headers = auth_headers("grouped-async-scan@example.com")
    read_calls = []
    original_latest = store.latest_market_candles

    def tracking_latest(symbol: str, period: str, limit: int = store_module.CLOSED_KLINE_LIMIT):
        read_calls.append((symbol, period, limit))
        return original_latest(symbol, period, limit)

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ETHUSDT", "SOLUSDT"])
    monkeypatch.setattr(store, "latest_market_candles", tracking_latest)
    seed_market_candles("ETHUSDT", "1H", seed=2.0, count=80)
    seed_market_candles("SOLUSDT", "1H", seed=2.5, count=80)

    for name, required in [("异步24根策略", 24), ("异步80根策略", 80)]:
        response = client.post(
            "/api/strategies",
            json={
                "name": name,
                "period": "1H",
                "description": f"需要 {required} 根 K 线。",
                "conditions": [f"至少 {required} 根 K 线"],
                "signalType": "趋势信号",
                "score": 88,
                "strengthGrade": "A",
                "pythonCode": f"def check_signal(candles):\n    return len(candles) >= {required}",
                "structuredConditions": [
                    {"title": "测试条件", "description": "需要足够 K 线", "parameters": [f"根数: {required}根"]}
                ],
                "aiAnalysis": ["测试异步同周期复用K线"],
            },
            headers=headers,
        )
        assert response.status_code == 200

    status = client.post("/api/strategies/run", headers=headers).json()
    for _ in range(30):
        if not status["running"]:
            break
        time.sleep(0.05)
        status = client.get("/api/strategies/run-status", headers=headers).json()

    assert status["scannedSymbols"] == 4
    assert status["signalsCreated"] == 4
    assert read_calls == [("ETHUSDT", "1H", 80), ("SOLUSDT", "1H", 80)]


def test_strategy_run_skips_when_cached_candles_do_not_meet_strategy_requirement(monkeypatch):
    headers = auth_headers("strategy-required-bars@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["SHORTUSDT"])
    seed_market_candles("SHORTUSDT", "1H", seed=2.8, count=24)

    create_response = client.post(
        "/api/strategies",
        json={
            "name": "80 根K线策略",
            "period": "1H",
            "description": "需要 80 根 K 线。",
            "conditions": ["至少 80 根 K 线"],
            "signalType": "趋势信号",
            "score": 88,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return len(candles) >= 80",
            "structuredConditions": [
                {"title": "测试条件", "description": "需要足够 K 线", "parameters": ["根数: 80根"]}
            ],
            "aiAnalysis": ["测试策略所需根数"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    status = client.post("/api/strategies/run", headers=headers).json()
    for _ in range(30):
        if not status["running"]:
            break
        time.sleep(0.05)
        status = client.get("/api/strategies/run-status", headers=headers).json()

    assert status["signalsCreated"] == 0
    assert status["skippedSymbols"] == 1
    assert status["skipped"][0]["message"] == "需要 80 根完整K线，实际 24 根"


def test_strategy_run_sends_pushover_for_created_signal(monkeypatch):
    headers = auth_headers("pushover-signal@example.com")
    calls = []

    class FakeResponse:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(request, timeout=8):
        calls.append((request, timeout))
        return FakeResponse()

    client.put(
        "/api/settings",
        json={
            "llm": {"provider": "openai", "baseUrl": "", "model": "", "apiKey": ""},
            "pushover": {"enabled": True, "userKey": "user-key", "appToken": "app-token"},
        },
        headers=headers,
    )
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["PUSHUSDT"])
    seed_market_candles("PUSHUSDT", "1H", seed=2.2)
    monkeypatch.setattr(store_module.urllib.request, "urlopen", fake_urlopen)

    create_response = client.post(
        "/api/strategies",
        json={
            "name": "push strategy",
            "period": "1H",
            "description": "push signal",
            "conditions": ["always"],
            "signalType": "trend",
            "score": 91,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return True",
            "structuredConditions": [
                {"title": "always", "description": "always", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["push test"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    run_response = client.post("/api/strategies/run-once", headers=headers)

    assert run_response.status_code == 200
    assert run_response.json()["signalsCreated"] == 1
    assert len(calls) == 1
    request, timeout = calls[0]
    assert timeout == 8
    assert request.full_url == "https://api.pushover.net/1/messages.json"
    assert b"PUSHUSDT" in request.data


def test_strategy_run_skips_per_strategy_symbol_blacklist(monkeypatch):
    headers = auth_headers("strategy-blacklist@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ETHUSDT", "ZKUSDT"])
    seed_market_candles("ETHUSDT", "1H", seed=2.5)
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "blacklist strategy",
            "period": "1H",
            "description": "skip symbols from blacklist",
            "conditions": ["always true"],
            "signalType": "trend",
            "score": 88,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return True",
            "structuredConditions": [
                {"title": "always", "description": "always true", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["blacklist test"],
            "symbolBlacklist": ["zkusdt", "ZKUSDT"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200
    assert create_response.json()["symbolBlacklist"] == ["ZKUSDT"]

    run_response = client.post("/api/strategies/run", headers=headers)
    assert run_response.status_code == 200

    status = run_response.json()
    for _ in range(30):
        if not status["running"]:
            break
        time.sleep(0.05)
        status = client.get("/api/strategies/run-status", headers=headers).json()

    assert status["running"] is False
    assert status["scannedSymbols"] == 2
    assert status["signalsCreated"] == 1
    assert status["skippedSymbols"] == 1
    assert status["skipped"][0]["symbol"] == "ZKUSDT"


def test_strategy_run_skips_symbols_with_insufficient_closed_klines(monkeypatch):
    headers = auth_headers("thin-history@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["NEWUSDT"])
    seed_market_candles("NEWUSDT", "1H", seed=3.0, count=24)
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "K 线不足跳过策略",
            "period": "1H",
            "description": "历史 K 线不足时应跳过，不计入错误。",
            "conditions": ["始终命中"],
            "signalType": "趋势信号",
            "score": 90,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return True",
            "structuredConditions": [
                {"title": "测试条件", "description": "需要足够 K 线", "parameters": ["根数: 240根"]}
            ],
            "aiAnalysis": ["测试跳过逻辑"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    run_response = client.post("/api/strategies/run", headers=headers)
    assert run_response.status_code == 200

    status = run_response.json()
    for _ in range(30):
        if not status["running"]:
            break
        time.sleep(0.05)
        status = client.get("/api/strategies/run-status", headers=headers).json()

    assert status["running"] is False
    assert status["scannedSymbols"] == 1
    assert status["signalsCreated"] == 0
    assert status["errorsCount"] == 0
    assert status["skippedSymbols"] == 1
    assert status["skipped"][0]["symbol"] == "NEWUSDT"
    assert status["skipped"][0]["errorType"] == "K线不足"


def test_fetch_market_candles_uses_only_closed_klines(monkeypatch):
    captured = {}
    rows = [
        [1_800_000_000_000 + i * 3_600_000, "1", "2", "0.5", str(1 + i / 100), "100"]
        for i in range(241)
    ]

    def fake_read(url: str, timeout: int):
        captured["url"] = url
        return store_module.json.dumps(rows)

    monkeypatch.setattr(store_module, "_read_url_with_retry", fake_read)

    candles = store_module.fetch_market_candles("ethusdt", "1H")

    assert "limit=241" in captured["url"]
    assert len(candles) == 240
    assert candles[-1].close == 1 + 239 / 100


def test_fetch_market_candles_supports_short_intervals(monkeypatch):
    captured_urls = []
    rows = [
        [1_800_000_000_000 + i * 300_000, "1", "2", "0.5", str(1 + i / 100), "100"]
        for i in range(241)
    ]

    def fake_read(url: str, timeout: int):
        captured_urls.append(url)
        return store_module.json.dumps(rows)

    monkeypatch.setattr(store_module, "_read_url_with_retry", fake_read)

    assert len(store_module.fetch_market_candles("ethusdt", "5M")) == 240
    assert len(store_module.fetch_market_candles("ethusdt", "15M")) == 240
    assert "interval=5m" in captured_urls[0]
    assert "interval=15m" in captured_urls[1]


def test_latest_period_boundary_supports_short_intervals():
    now = datetime(2026, 6, 1, 10, 17, 42, tzinfo=timezone.utc)

    assert store_module._latest_period_boundary("5M", now) == datetime(2026, 6, 1, 10, 15, tzinfo=timezone.utc)
    assert store_module._latest_period_boundary("15M", now) == datetime(2026, 6, 1, 10, 15, tzinfo=timezone.utc)
    assert store_module._latest_period_boundary("1H", now) == datetime(2026, 6, 1, 10, 0, tzinfo=timezone.utc)


def test_market_kline_retention_cutoffs_match_required_windows():
    now = datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc)
    cutoffs = store_module._market_kline_retention_cutoffs(now)

    assert set(cutoffs) == {"5M", "15M", "1H", "4H", "1D"}
    assert cutoffs["5M"] == "2026-05-02T00:00:00+00:00"
    assert cutoffs["15M"] == "2026-05-02T00:00:00+00:00"
    assert cutoffs["1H"] == "2026-05-02T00:00:00+00:00"
    assert cutoffs["4H"] == "2026-05-02T00:00:00+00:00"
    assert cutoffs["1D"] == "2025-06-01T00:00:00+00:00"


def test_delete_old_signals_removes_only_items_older_than_retention_window():
    old_signal = insert_sample_signal("sig-old-retention", "OLDUSDT")
    recent_signal = insert_sample_signal("sig-recent-retention", "RECENTUSDT")
    invalid_timestamp_signal = insert_sample_signal("sig-invalid-retention", "INVALIDUSDT")

    store._upsert(
        "signals",
        old_signal.model_copy(update={"triggeredAt": "2026-04-30T12:00:00+00:00"}),
        store._order_for_id("signals", old_signal.id),
    )
    store._upsert(
        "signals",
        recent_signal.model_copy(update={"triggeredAt": "2026-05-15T12:00:00+00:00"}),
        store._order_for_id("signals", recent_signal.id),
    )
    store._upsert(
        "signals",
        invalid_timestamp_signal.model_copy(update={"triggeredAt": "not-a-date"}),
        store._order_for_id("signals", invalid_timestamp_signal.id),
    )

    deleted = store.delete_old_signals(datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc), retention_days=30)

    assert deleted == 1
    remaining_ids = {signal.id for signal in store.signals}
    assert old_signal.id not in remaining_ids
    assert recent_signal.id in remaining_ids
    assert invalid_timestamp_signal.id in remaining_ids


def test_signal_cleanup_scheduler_tick_runs_once_per_day():
    old_signal = insert_sample_signal("sig-old-scheduler", "SCHEDOLDUSDT")
    store._upsert(
        "signals",
        old_signal.model_copy(update={"triggeredAt": "2026-04-30T12:00:00+00:00"}),
        store._order_for_id("signals", old_signal.id),
    )

    first = store_module.run_signal_cleanup_scheduler_tick(
        store,
        datetime(2026, 6, 1, 1, 0, 0, tzinfo=timezone.utc),
    )
    second = store_module.run_signal_cleanup_scheduler_tick(
        store,
        datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc),
    )

    assert first == 1
    assert second == 0


def test_signal_performance_scheduler_completes_tracking_and_saves_ai_lesson(monkeypatch):
    headers = auth_headers("signal-review@example.com")
    signal = insert_sample_signal("sig-performance-review", "REVIEWUSDT", "1H")
    signal = signal.model_copy(
        update={
            "strategyId": "seed-strategy",
            "strategyName": "AI复盘策略",
            "triggeredAt": "2026-05-31T10:00:00+00:00",
            "price": 100.0,
        }
    )
    store._upsert("signals", signal, store._order_for_id("signals", signal.id))
    store.upsert_market_candles(
        "REVIEWUSDT",
        "1H",
        [
            Candle(
                time=(datetime(2026, 5, 31, 11, 0, 0, tzinfo=timezone.utc) + i * timedelta(hours=1)).isoformat(),
                open=100 + i,
                high=102 + i,
                low=99 - i * 0.1,
                close=101 + i,
                volume=1000 + i * 20,
                ma5=100 + i,
                ma20=99 + i,
                ma60=98 + i,
            )
            for i in range(25)
        ],
    )

    def fake_review(*_args, **_kwargs):
        return {
            "result": "effective",
            "summary": "24小时内延续上涨，信号有效。",
            "analysis": "触发后价格逐步抬高，最大浮盈明显高于最大回撤。",
            "failureReason": "",
            "effectivePattern": "突破后持续站稳并放量。",
            "improvementIdeas": ["继续保留趋势确认条件", "观察回撤是否扩大"],
            "suggestedRuleChanges": [{"type": "keep_condition", "description": "保留 MA20 上方确认"}],
            "confidence": 0.82,
        }

    monkeypatch.setattr(store_module, "_call_llm_for_signal_review", fake_review, raising=False)

    result = store_module.run_signal_performance_scheduler_tick(
        store,
        datetime(2026, 6, 1, 11, 30, 0, tzinfo=timezone.utc),
    )

    performance = store.performance_for_signal(signal.id)
    lessons = store.lessons_for_strategy(signal.strategyId)
    detail = client.get(f"/api/signals/{signal.id}", headers=headers).json()

    assert result["tracked"] == 1
    assert result["reviewed"] == 1
    assert result["lessonsCreated"] == 1
    assert performance is not None
    assert performance.status == "completed"
    assert performance.reviewStatus == "generated"
    assert performance.reviewResult == "effective"
    assert performance.change1hPct == pytest.approx(1.0)
    assert performance.change4hPct == pytest.approx(4.0)
    assert performance.change24hPct == pytest.approx(24.0)
    assert performance.maxGainPct == pytest.approx(25.0)
    assert performance.maxDrawdownPct == pytest.approx(-3.3)
    assert lessons[0].signalId == signal.id
    assert lessons[0].result == "effective"
    assert lessons[0].confidence == pytest.approx(0.82)
    assert detail["performance"]["reviewSummary"] == "24小时内延续上涨，信号有效。"


def test_scheduler_tick_starts_due_strategy_run(monkeypatch):
    headers = auth_headers("scheduler@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["DUEUSDT"])
    seed_market_candles("DUEUSDT", "1H", seed=4.0)
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "定时扫描策略",
            "period": "1H",
            "description": "到点后自动运行。",
            "conditions": ["始终命中"],
            "signalType": "趋势信号",
            "score": 89,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return True",
            "structuredConditions": [
                {"title": "测试条件", "description": "始终命中", "parameters": ["根数: 240根"]}
            ],
            "aiAnalysis": ["测试定时调度"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    triggered = store_module.run_strategy_scheduler_tick(store, datetime(2026, 6, 1, 11, 0, 30, tzinfo=timezone.utc))
    assert triggered == 1

    status = client.get("/api/strategies/run-status", headers=headers).json()
    for _ in range(30):
        if not status["running"]:
            break
        time.sleep(0.05)
        status = client.get("/api/strategies/run-status", headers=headers).json()

    assert status["triggerSource"] == "scheduled"
    assert status["signalsCreated"] == 1
    assert client.get("/api/strategies/scheduler-status", headers=headers).json()["lastTriggeredAt"]


def test_scheduler_tick_skips_due_strategy_while_kline_collection_is_running(monkeypatch):
    headers = auth_headers("scheduler-kline-busy@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["BUSYUSDT"])
    seed_market_candles("BUSYUSDT", "1H", seed=4.2)
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "K线采集中跳过策略",
            "period": "1H",
            "description": "K线采集未完成时不应启动扫描。",
            "conditions": ["始终命中"],
            "signalType": "趋势信号",
            "score": 89,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return True",
            "structuredConditions": [
                {"title": "测试条件", "description": "始终命中", "parameters": ["根数: 240根"]}
            ],
            "aiAnalysis": ["测试K线采集锁"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    store_module._market_kline_collection_state["collecting"] = True

    try:
        triggered = store_module.run_strategy_scheduler_tick(store, datetime(2026, 6, 1, 11, 0, 30, tzinfo=timezone.utc))
    finally:
        store_module._market_kline_collection_state["collecting"] = False

    assert triggered == 0
    assert client.get("/api/strategies/run-status", headers=headers).json()["jobId"] == ""


def test_manual_strategy_run_returns_not_running_while_kline_collection_is_running():
    headers = auth_headers("manual-kline-busy@example.com")
    store_module._market_kline_collection_state["collecting"] = True

    try:
        response = client.post("/api/strategies/run", headers=headers)
    finally:
        store_module._market_kline_collection_state["collecting"] = False

    assert response.status_code == 200
    body = response.json()
    assert body["running"] is False
    assert body["errorsCount"] == 1
    assert body["errors"][0]["errorType"] == "K线更新中"


def test_scheduler_uses_period_boundary_instead_of_last_run_interval(monkeypatch):
    headers = auth_headers("scheduler-boundary@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["BOUNDARYUSDT"])
    seed_market_candles("BOUNDARYUSDT", "1H", seed=4.5)
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "整点扫描策略",
            "period": "1H",
            "description": "应按整点边界触发。",
            "conditions": ["始终命中"],
            "signalType": "趋势信号",
            "score": 89,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return True",
            "structuredConditions": [
                {"title": "测试条件", "description": "始终命中", "parameters": ["根数: 240根"]}
            ],
            "aiAnalysis": ["测试整点调度"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200
    strategy_id = create_response.json()["id"]
    original = next(strategy for strategy in store.strategies if strategy.id == strategy_id)
    store._upsert(
        "strategies",
        original.model_copy(
            update={
                "schedule": original.schedule.model_copy(
                    update={"lastRunAt": "2026-06-01T10:09:00+00:00"}
                )
            }
        ),
        store._order_for_id("strategies", strategy_id),
    )

    assert store_module.run_strategy_scheduler_tick(store, datetime(2026, 6, 1, 10, 59, 45, tzinfo=timezone.utc)) == 0
    assert store_module.run_strategy_scheduler_tick(store, datetime(2026, 6, 1, 11, 0, 30, tzinfo=timezone.utc)) == 1
    status = client.get("/api/strategies/run-status", headers=headers).json()
    for _ in range(30):
        if not status["running"]:
            break
        time.sleep(0.05)
        status = client.get("/api/strategies/run-status", headers=headers).json()


def test_strategy_run_history_lists_recent_completed_scans(monkeypatch):
    headers = auth_headers("history@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["HISTORYUSDT"])
    seed_market_candles("HISTORYUSDT", "1H", seed=5.0)
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "最近扫描记录策略",
            "period": "1H",
            "description": "扫描结束后应进入最近扫描列表。",
            "conditions": ["始终命中"],
            "signalType": "趋势信号",
            "score": 88,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return True",
            "structuredConditions": [
                {"title": "测试条件", "description": "始终命中", "parameters": ["根数: 240根"]}
            ],
            "aiAnalysis": ["测试扫描历史"],
        },
        headers=headers,
    )
    assert create_response.status_code == 200

    status = client.post("/api/strategies/run", headers=headers).json()
    for _ in range(30):
        if not status["running"]:
            break
        time.sleep(0.05)
        status = client.get("/api/strategies/run-status", headers=headers).json()

    history_response = client.get("/api/strategies/run-history", headers=headers)

    assert history_response.status_code == 200
    history = history_response.json()
    assert history[0]["strategyName"] == "最近扫描记录策略"
    assert history[0]["period"] == "1H"
    assert history[0]["status"] == "completed"
    assert history[0]["signalsCreated"] == 1
    assert history[0]["errorsCount"] == 0


def test_toggle_strategy_enabled():
    created = store.create_strategy(
        CreateStrategyRequest(
            name="可切换策略",
            period="1H",
            description="用于测试启停。",
            conditions=["价格站上 MA20"],
        )
    )
    response = client.patch(
        f"/api/strategies/{created.id}/enabled",
        json={"enabled": False},
        headers=auth_headers(),
    )
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_toggle_strategy_schedule_enabled():
    headers = auth_headers("schedule-toggle@example.com")
    created = store.create_strategy(
        CreateStrategyRequest(
            name="可切换定时策略",
            period="1H",
            description="用于测试定时任务开关。",
            conditions=["价格站上 MA20"],
            pythonCode="def check_signal(candles):\n    return False",
        )
    )

    response = client.patch(
        f"/api/strategies/{created.id}/schedule-enabled",
        json={"enabled": False},
        headers=headers,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is True
    assert body["schedule"]["enabled"] is False


def test_update_strategy_persists_editable_runtime_fields():
    headers = auth_headers("edit-strategy@example.com")
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "待编辑策略",
            "period": "1H",
            "description": "初始描述",
            "conditions": ["初始条件"],
            "signalType": "趋势信号",
            "score": 80,
            "pythonCode": "def check_signal(candles):\n    return False",
            "structuredConditions": [
                {"title": "初始条件", "description": "初始描述", "parameters": ["根数：10根"]}
            ],
            "aiAnalysis": ["初始分析"],
            "intervalSeconds": 300,
        },
        headers=headers,
    )
    strategy_id = create_response.json()["id"]
    client.patch(f"/api/strategies/{strategy_id}/enabled", json={"enabled": False}, headers=headers)

    update_response = client.put(
        f"/api/strategies/{strategy_id}",
        json={
            "name": "已编辑策略",
            "period": "4H",
            "description": "编辑后的描述",
            "conditions": ["编辑后的条件"],
            "signalType": "观察信号",
            "score": 91,
            "pythonCode": "def check_signal(candles):\n    return len(candles) >= 20",
            "structuredConditions": [
                {"title": "编辑条件", "description": "编辑描述", "parameters": ["根数：20根"]}
            ],
            "aiAnalysis": ["编辑后的分析"],
            "scheduleEnabled": False,
            "intervalSeconds": 600,
        },
        headers=headers,
    )

    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "已编辑策略"
    assert updated["period"] == "4H"
    assert updated["conditions"] == ["编辑后的条件"]
    assert updated["runtime"]["code"].endswith("len(candles) >= 20")
    assert updated["runtime"]["structuredConditions"][0]["title"] == "编辑条件"
    assert updated["runtime"]["aiAnalysis"] == ["编辑后的分析"]
    assert updated["schedule"]["enabled"] is False
    assert updated["schedule"]["intervalSeconds"] == 600


def test_update_strategy_rejects_enabled_strategy():
    headers = auth_headers("running-strategy-edit@example.com")
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "running strategy",
            "period": "1H",
            "description": "running",
            "conditions": ["always"],
            "signalType": "trend",
            "score": 80,
            "pythonCode": "def check_signal(candles):\n    return False",
            "structuredConditions": [
                {"title": "always", "description": "always", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["running edit test"],
        },
        headers=headers,
    )
    strategy_id = create_response.json()["id"]

    update_response = client.put(
        f"/api/strategies/{strategy_id}",
        json={
            "name": "updated running strategy",
            "period": "1H",
            "description": "updated",
            "conditions": ["always"],
            "signalType": "trend",
            "score": 80,
            "pythonCode": "def check_signal(candles):\n    return False",
            "structuredConditions": [
                {"title": "always", "description": "always", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["running edit test"],
            "scheduleEnabled": True,
            "intervalSeconds": 3600,
            "enabled": True,
        },
        headers=headers,
    )

    assert update_response.status_code == 400
    assert update_response.json()["code"] == "STRATEGY_VALIDATION_FAILED"


def test_delete_strategy_removes_paused_strategy():
    headers = auth_headers("delete-paused-strategy@example.com")
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "delete paused strategy",
            "period": "1H",
            "description": "delete test",
            "conditions": ["always false"],
            "signalType": "trend",
            "score": 80,
            "pythonCode": "def check_signal(candles):\n    return False",
            "structuredConditions": [
                {"title": "always false", "description": "always false", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["delete test"],
        },
        headers=headers,
    )
    strategy_id = create_response.json()["id"]
    client.patch(f"/api/strategies/{strategy_id}/enabled", json={"enabled": False}, headers=headers)

    delete_response = client.delete(f"/api/strategies/{strategy_id}", headers=headers)

    assert delete_response.status_code == 204
    strategies = client.get("/api/strategies", headers=headers).json()
    assert all(strategy["id"] != strategy_id for strategy in strategies)


def test_delete_strategy_rejects_enabled_strategy():
    headers = auth_headers("delete-enabled-strategy@example.com")
    create_response = client.post(
        "/api/strategies",
        json={
            "name": "delete enabled strategy",
            "period": "1H",
            "description": "delete enabled test",
            "conditions": ["always false"],
            "signalType": "trend",
            "score": 80,
            "pythonCode": "def check_signal(candles):\n    return False",
            "structuredConditions": [
                {"title": "always false", "description": "always false", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["delete enabled test"],
        },
        headers=headers,
    )
    strategy_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/strategies/{strategy_id}", headers=headers)

    assert delete_response.status_code == 400
    assert delete_response.json()["code"] == "STRATEGY_DELETE_FAILED"


def test_delete_strategy_returns_404_for_missing_strategy():
    headers = auth_headers("delete-missing-strategy@example.com")

    delete_response = client.delete("/api/strategies/st-missing", headers=headers)

    assert delete_response.status_code == 404
    assert delete_response.json()["code"] == "STRATEGY_NOT_FOUND"


def test_save_strategy_rejects_code_that_does_not_return_bool():
    headers = auth_headers("non-bool-strategy@example.com")
    response = client.post(
        "/api/strategies",
        json={
            "name": "non bool strategy",
            "period": "1H",
            "description": "invalid return type",
            "conditions": ["always"],
            "signalType": "trend",
            "score": 88,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return 'yes'",
            "structuredConditions": [
                {"title": "always", "description": "always", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["validation test"],
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "STRATEGY_VALIDATION_FAILED"
    assert "bool" in response.json()["message"]


def test_save_strategy_allows_safe_type_annotations():
    headers = auth_headers("typed-strategy@example.com")
    response = client.post(
        "/api/strategies",
        json={
            "name": "typed strategy",
            "period": "1H",
            "description": "uses annotations",
            "conditions": ["always"],
            "signalType": "trend",
            "score": 88,
            "strengthGrade": "A",
            "pythonCode": (
                "def get_value(candle: dict[str, Any] | Any, key: str):\n"
                "    return candle.get(key) if isinstance(candle, dict) else getattr(candle, key, None)\n\n"
                "def check_signal(candles: list[dict[str, Any]]) -> bool:\n"
                "    return len(candles) >= 20 and isinstance(get_value(candles[-1], 'close'), float)\n"
            ),
            "structuredConditions": [
                {"title": "always", "description": "always", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["validation test"],
        },
        headers=headers,
    )

    assert response.status_code == 200


def test_save_strategy_allows_index_argument_signature():
    headers = auth_headers("indexed-strategy@example.com")
    response = client.post(
        "/api/strategies",
        json={
            "name": "indexed strategy",
            "period": "1H",
            "description": "uses check_signal(candles, index)",
            "conditions": ["uses latest index"],
            "signalType": "trend",
            "score": 88,
            "strengthGrade": "A",
            "pythonCode": (
                "def check_signal(candles, index):\n"
                "    return index == len(candles) - 1 and candles[index]['close'] > 0\n"
            ),
            "structuredConditions": [
                {"title": "latest index", "description": "uses latest index", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["validation test"],
        },
        headers=headers,
    )

    assert response.status_code == 200


def test_save_strategy_allows_dataframe_style_code():
    headers = auth_headers("dataframe-strategy@example.com")
    response = client.post(
        "/api/strategies",
        json={
            "name": "dataframe strategy",
            "period": "1H",
            "description": "uses pandas dataframe style access",
            "conditions": ["uses dataframe rolling ma"],
            "signalType": "trend",
            "score": 88,
            "strengthGrade": "A",
            "pythonCode": (
                "def check_signal(candles, index: int) -> bool:\n"
                "    if index < 80:\n"
                "        return False\n"
                "    candles = candles.copy()\n"
                "    candles['ma20'] = candles['close'].rolling(20).mean()\n"
                "    candles['ma60'] = candles['close'].rolling(60).mean()\n"
                "    current = candles.iloc[index]\n"
                "    recent = candles.iloc[index - 30:index]\n"
                "    return bool(current['ma20'] > current['ma60'] and (recent['close'] > recent['ma20']).mean() >= 0)\n"
            ),
            "structuredConditions": [
                {"title": "dataframe", "description": "uses dataframe", "parameters": ["bars: 80"]}
            ],
            "aiAnalysis": ["validation test"],
        },
        headers=headers,
    )

    assert response.status_code == 200


def test_save_strategy_rejects_code_that_crashes_during_scan_validation():
    headers = auth_headers("crashing-strategy@example.com")
    response = client.post(
        "/api/strategies",
        json={
            "name": "crashing strategy",
            "period": "1H",
            "description": "runtime error",
            "conditions": ["always"],
            "signalType": "trend",
            "score": 88,
            "strengthGrade": "A",
            "pythonCode": "def check_signal(candles):\n    return 1 / 0 == 0",
            "structuredConditions": [
                {"title": "always", "description": "always", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["validation test"],
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "STRATEGY_VALIDATION_FAILED"
    assert "division by zero" in response.json()["message"]


def test_save_strategy_reports_runtime_error_line_number():
    headers = auth_headers("line-number-strategy@example.com")
    response = client.post(
        "/api/strategies",
        json={
            "name": "line number strategy",
            "period": "1H",
            "description": "runtime error with source line",
            "conditions": ["always"],
            "signalType": "trend",
            "score": 88,
            "strengthGrade": "A",
            "pythonCode": (
                "def check_signal(candles, index):\n"
                "    latest = candles[index]\n"
                "    values = [1, 2, 3]\n"
                "    return values['close'] > 0\n"
            ),
            "structuredConditions": [
                {"title": "always", "description": "always", "parameters": ["bars: 240"]}
            ],
            "aiAnalysis": ["validation test"],
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "STRATEGY_VALIDATION_FAILED"
    assert "第 4 行" in response.json()["message"]
    assert "list indices must be integers" in response.json()["message"]


def test_save_strategy_rejects_breakout_code_without_price_breakout_check():
    headers = auth_headers("breakout-validator@example.com")
    response = client.post(
        "/api/strategies",
        json={
            "name": "缺少价格突破校验策略",
            "period": "1H",
            "description": "放量突破但代码没有检查价格突破前高。",
            "conditions": ["最近1小时放量突破，成交量大于过去24小时均量3倍"],
            "signalType": "趋势信号",
            "score": 88,
            "strengthGrade": "A",
            "pythonCode": (
                "def check_signal(candles):\n"
                "    if len(candles) < 25:\n"
                "        return False\n"
                "    avg = sum(c['volume'] for c in candles[-25:-1]) / 24\n"
                "    return candles[-1]['volume'] > avg * 3\n"
            ),
            "structuredConditions": [
                {"title": "放量突破", "description": "最新1小时放量突破", "parameters": ["均量周期: 24根", "放量倍数: 3倍"]}
            ],
            "aiAnalysis": ["测试保存校验"],
        },
        headers=headers,
    )

    assert response.status_code == 400
    assert response.json()["code"] == "STRATEGY_VALIDATION_FAILED"
    assert "价格未突破" in response.json()["message"]


def test_signal_detail_and_watchlist_creation():
    headers = auth_headers()
    insert_sample_signal("sig-detail-seed", "ALLUSDT", "1H")
    signal_response = client.get("/api/signals/sig-detail-seed", headers=headers)
    assert signal_response.status_code == 200
    assert signal_response.json()["symbol"] == "ALLUSDT"

    watch_response = client.post(
        "/api/watchlist",
        json={
            "symbol": "ALLUSDT",
            "conditions": [
                {
                    "id": "new-condition",
                    "type": "price",
                    "period": "1H",
                    "expression": "价格 > 0.3000",
                    "status": "pending",
                    "lastTriggeredAt": None,
                }
            ],
        },
        headers=headers,
    )
    assert watch_response.status_code == 200
    watch_body = watch_response.json()
    assert watch_body["symbol"] == "ALLUSDT"
    assert watch_body["currentPrice"] > 0
    assert watch_body["change24h"] != 0


def test_missing_signal_uses_top_level_error_envelope():
    response = client.get("/api/signals/missing", headers=auth_headers())

    assert response.status_code == 404
    assert response.json() == {
        "code": "SIGNAL_NOT_FOUND",
        "message": "Signal not found",
        "details": {"signalId": "missing"},
    }


def test_watchlist_creation_requires_conditions():
    response = client.post(
        "/api/watchlist",
        json={"symbol": "ALLUSDT", "conditions": []},
        headers=auth_headers(),
    )
    assert response.status_code == 422


def test_knowledge_case_detail():
    case = KnowledgeCase(
        id="case-test",
        title="测试案例",
        symbol="ALLUSDT",
        strategyId="st-test",
        strategyName="测试策略",
        score=90,
        createdAt="2026-05-31T10:00:00+08:00",
        summary="测试案例详情。",
        reasons=["命中条件"],
        lessons=["先验证再启用"],
        candles=sample_candles(1.0),
    )
    store._upsert("knowledge_cases", case, store._next_front_order("knowledge_cases"))

    response = client.get("/api/knowledge/case-test", headers=auth_headers())
    assert response.status_code == 200
    assert response.json()["strategyName"] == "测试策略"
