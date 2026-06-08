import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

test_db_path = Path(tempfile.gettempdir()) / f"axis-api-test-{os.getpid()}.sqlite3"
if test_db_path.exists():
    test_db_path.unlink()

os.environ["SIGNAL_DB_DRIVER"] = "sqlite"
os.environ["SIGNAL_DB_PATH"] = str(test_db_path)

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
    PushoverSettingsUpdate,
    Signal,
    StrategyScanHistory,
    WatchCondition,
    WatchItem,
)
from app.store import MySQLStore, SQLiteStore, _normalize_generated_strategy, store


client = TestClient(app)


@pytest.fixture(autouse=True)
def reset_store():
    store.reset()


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


def test_llm_strategy_generation_is_cached_for_same_period_and_conditions(tmp_path, monkeypatch):
    db_path = tmp_path / "axis-cache-test.sqlite3"
    cache_store = SQLiteStore(db_path)
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


def test_strategy_generation_from_code_preserves_pasted_code(tmp_path, monkeypatch):
    db_path = tmp_path / "axis-code-import-test.sqlite3"
    code_store = SQLiteStore(db_path)
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


def test_placeholder_python_code_cache_is_ignored(tmp_path, monkeypatch):
    db_path = tmp_path / "axis-cache-placeholder-test.sqlite3"
    cache_store = SQLiteStore(db_path)
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


def test_sqlite_store_persists_created_strategy(tmp_path):
    db_path = tmp_path / "axis-test.sqlite3"
    first_store = SQLiteStore(db_path)
    first_store.create_strategy(
        CreateStrategyRequest(
            name="持久化策略",
            period="1H",
            description="验证数据库重开后数据仍然存在。",
            conditions=["价格站上 MA20"],
        )
    )

    second_store = SQLiteStore(db_path)
    assert second_store.strategies[0].name == "持久化策略"


def test_sqlite_store_persists_strategy_scan_history(tmp_path):
    db_path = tmp_path / "axis-history-test.sqlite3"
    first_store = SQLiteStore(db_path)
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

    second_store = SQLiteStore(db_path)
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
    monkeypatch.setattr(store_module, "fetch_market_candles", lambda symbol, period, limit=240: sample_candles(1.0, count=240))
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


def test_run_strategy_fetches_market_candles_for_all_tradable_symbols(monkeypatch):
    headers = auth_headers("market-runner@example.com")
    calls = []

    def fake_fetch(symbol: str, period: str, limit: int = 240):
        calls.append((symbol, period, limit))
        return sample_candles(2.0, count=240)

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ETHUSDT", "SOLUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles", fake_fetch)
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
    assert calls == [("ETHUSDT", "1H", 240), ("SOLUSDT", "1H", 240)]
    assert body["symbolsChecked"] == 2
    assert body["signalsCreated"] == 2
    assert {item["symbol"] for item in body["createdSignals"]} == {"ETHUSDT", "SOLUSDT"}


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
    monkeypatch.setattr(store_module, "fetch_market_candles", lambda symbol, period, limit=240: sample_candles(2.2, count=240))
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
    calls = []

    def fake_fetch(symbol: str, period: str, limit: int = 240):
        calls.append((symbol, period, limit))
        return sample_candles(2.5, count=240)

    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["ETHUSDT", "ZKUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles", fake_fetch)
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
    assert calls == [("ETHUSDT", "1H", 240)]
    assert status["scannedSymbols"] == 2
    assert status["signalsCreated"] == 1
    assert status["skippedSymbols"] == 1
    assert status["skipped"][0]["symbol"] == "ZKUSDT"


def test_strategy_run_skips_symbols_with_insufficient_closed_klines(monkeypatch):
    headers = auth_headers("thin-history@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["NEWUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles", lambda symbol, period, limit=240: sample_candles(3.0, count=24))
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


def test_scheduler_tick_starts_due_strategy_run(monkeypatch):
    headers = auth_headers("scheduler@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["DUEUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles", lambda symbol, period, limit=240: sample_candles(4.0, count=240))
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


def test_scheduler_uses_period_boundary_instead_of_last_run_interval(monkeypatch):
    headers = auth_headers("scheduler-boundary@example.com")
    monkeypatch.setattr(store_module, "fetch_tradable_symbols", lambda: ["BOUNDARYUSDT"])
    monkeypatch.setattr(store_module, "fetch_market_candles", lambda symbol, period, limit=240: sample_candles(4.5, count=240))
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
    monkeypatch.setattr(store_module, "fetch_market_candles", lambda symbol, period, limit=240: sample_candles(5.0, count=240))
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
