# Signal Discovery System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a frontend/backend separated MVP for a USDT perpetual futures signal discovery system with nine high-fidelity screens and mock FastAPI data.

**Architecture:** The workspace contains a Vite React frontend and a FastAPI backend. The backend owns all mock business data and exposes REST endpoints under `/api`; the frontend consumes those endpoints through a typed API client and renders the dashboard, strategies, signals, watchlist, and knowledge flows.

**Tech Stack:** React, TypeScript, Vite, lucide-react, FastAPI, Pydantic, pytest, FastAPI TestClient.

---

## File Structure

```text
D:\Axis
  backend\
    requirements.txt
    app\
      __init__.py
      main.py
      models.py
      mock_data.py
      store.py
      routers\
        __init__.py
        dashboard.py
        strategies.py
        signals.py
        watchlist.py
        knowledge.py
    tests\
      test_api.py
  frontend\
    package.json
    index.html
    tsconfig.json
    vite.config.ts
    src\
      main.tsx
      App.tsx
      api.ts
      types.ts
      data-format.ts
      styles.css
      components\
        AppShell.tsx
        Charts.tsx
        Modal.tsx
        StrengthGrade.tsx
      pages\
        Dashboard.tsx
        Strategies.tsx
        Signals.tsx
        SignalDetail.tsx
        Watchlist.tsx
        WatchDetail.tsx
        KnowledgeCase.tsx
```

## Task 1: Backend Scaffold And Health

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/tests/test_api.py`

- [ ] **Step 1: Create backend dependencies**

`backend/requirements.txt`:

```text
fastapi==0.115.6
uvicorn[standard]==0.34.0
pydantic==2.10.4
pytest==8.3.4
httpx==0.28.1
```

- [ ] **Step 2: Write the failing health test**

`backend/tests/test_api.py`:

```python
from fastapi.testclient import TestClient

from app.main import app


client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 3: Run the test and verify it fails before implementation**

Run:

```powershell
cd D:\Axis\backend
python -m pytest tests/test_api.py -v
```

Expected: FAIL if `app.main` or `/api/health` does not exist.

- [ ] **Step 4: Implement FastAPI app**

`backend/app/__init__.py`:

```python
```

`backend/app/routers/__init__.py`:

```python
```

`backend/app/main.py`:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="TrendAI Signal Discovery API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run the test and verify it passes**

Run:

```powershell
cd D:\Axis\backend
python -m pytest tests/test_api.py -v
```

Expected: `1 passed`.

## Task 2: Backend Models And Mock Store

**Files:**
- Create: `backend/app/models.py`
- Create: `backend/app/mock_data.py`
- Create: `backend/app/store.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Add model and store tests**

Append to `backend/tests/test_api.py`:

```python
from app.store import store


def test_mock_store_has_core_entities():
    assert len(store.strategies) >= 4
    assert len(store.signals) >= 5
    assert len(store.watchlist) >= 4
    assert len(store.knowledge_cases) >= 1
    assert store.signals[0].candles
```

- [ ] **Step 2: Run tests and verify store import fails**

Run:

```powershell
cd D:\Axis\backend
python -m pytest tests/test_api.py::test_mock_store_has_core_entities -v
```

Expected: FAIL because `app.store` does not exist.

- [ ] **Step 3: Create Pydantic models**

`backend/app/models.py`:

```python
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Period = Literal["1H", "4H", "1D"]
StrengthGrade = Literal["S", "A", "B", "C"]
WatchStatus = Literal["pending", "matched", "unmatched"]


class Candle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    ma5: float
    ma20: float
    ma60: float


class Strategy(BaseModel):
    id: str
    name: str
    source: Literal["preset", "ai"]
    period: Period
    enabled: bool
    conditions: list[str]
    description: str
    score: int = Field(ge=0, le=100)
    todaySignalCount: int
    lastTriggeredAt: str | None
    createdAt: str


class GeneratedStrategy(BaseModel):
    name: str
    period: Period
    description: str
    conditions: list[str]
    signalType: str
    strengthGrade: StrengthGrade
    score: int = Field(ge=0, le=100)


class GenerateStrategyRequest(BaseModel):
    period: Period
    conditions: list[str] = Field(min_length=1)


class CreateStrategyRequest(BaseModel):
    name: str
    period: Period
    description: str
    conditions: list[str] = Field(min_length=1)
    signalType: str = "趋势启动"
    score: int = Field(default=88, ge=0, le=100)


class ToggleEnabledRequest(BaseModel):
    enabled: bool


class Signal(BaseModel):
    id: str
    symbol: str
    period: Period
    strategyId: str
    strategyName: str
    signalType: str
    score: int = Field(ge=0, le=100)
    triggeredAt: str
    price: float
    summary: str
    analysis: list[str]
    strengthGrade: StrengthGrade
    candles: list[Candle]


class WatchCondition(BaseModel):
    id: str
    type: str
    period: Period
    expression: str
    status: WatchStatus
    lastTriggeredAt: str | None


class WatchItem(BaseModel):
    id: str
    symbol: str
    currentPrice: float
    change24h: float
    conditions: list[WatchCondition]
    lastTriggeredAt: str | None
    createdAt: str


class CreateWatchItemRequest(BaseModel):
    symbol: str
    conditions: list[WatchCondition]


class KnowledgeCase(BaseModel):
    id: str
    title: str
    symbol: str
    strategyId: str
    strategyName: str
    score: int
    createdAt: str
    summary: str
    reasons: list[str]
    lessons: list[str]
    candles: list[Candle]


class DashboardSummary(BaseModel):
    todaySignals: int
    enabledStrategies: int
    watchSymbols: int
    observationAlerts: int
    runningStrategies: int
    signalTrend: list[dict[str, int | str]]
    latestSignals: list[Signal]
    recentStrategies: list[Strategy]
    recentWatchlist: list[WatchItem]
```

- [ ] **Step 4: Create mock data helpers and store**

`backend/app/mock_data.py`:

```python
from datetime import datetime, timedelta

from app.models import Candle, KnowledgeCase, Signal, Strategy, WatchCondition, WatchItem


def make_candles(seed: float) -> list[Candle]:
    base = datetime(2026, 5, 24, 10, 0)
    rows: list[Candle] = []
    price = seed
    for index in range(34):
        drift = (index % 6 - 2) * seed * 0.006
        close = max(seed * 0.55, price + drift + seed * 0.01)
        high = max(price, close) + seed * 0.018
        low = min(price, close) - seed * 0.014
        volume = 1200 + index * 77 + (index % 5) * 180
        ma5 = close * (0.985 + (index % 3) * 0.004)
        ma20 = close * 0.96
        ma60 = close * 0.91
        rows.append(
            Candle(
                time=(base + timedelta(hours=index)).strftime("%m-%d %H:%M"),
                open=round(price, 6),
                high=round(high, 6),
                low=round(low, 6),
                close=round(close, 6),
                volume=round(volume, 2),
                ma5=round(ma5, 6),
                ma20=round(ma20, 6),
                ma60=round(ma60, 6),
            )
        )
        price = close
    return rows


def build_initial_data():
    strategies = [
        Strategy(id="st-trend-1", name="趋势启动1号", source="preset", period="1H", enabled=True, conditions=["前低长期横盘震荡", "最近10天振幅小于30%", "价格站上MA20"], description="捕捉低位横盘后的趋势启动。", score=92, todaySignalCount=5, lastTriggeredAt="2026-05-29 10:28", createdAt="2026-05-20 09:00"),
        Strategy(id="st-volume-1", name="放量突破回踩", source="preset", period="4H", enabled=True, conditions=["突破近48小时高点", "成交量大于过去24小时均值3倍"], description="寻找放量突破后的回踩确认。", score=88, todaySignalCount=2, lastTriggeredAt="2026-05-29 09:56", createdAt="2026-05-21 10:00"),
        Strategy(id="st-watch-1", name="观察池条件", source="preset", period="1H", enabled=True, conditions=["观察价格触发", "MA20趋势保持"], description="观察池条件命中信号。", score=85, todaySignalCount=1, lastTriggeredAt="2026-05-29 09:41", createdAt="2026-05-22 11:00"),
        Strategy(id="st-ai-1", name="小币多头拐点", source="ai", period="1H", enabled=False, conditions=["1小时成交量放大", "价格收复MA20", "回撤不破前低"], description="AI生成的小周期趋势修复策略。", score=80, todaySignalCount=0, lastTriggeredAt=None, createdAt="2026-05-28 15:00"),
    ]
    all_candles = make_candles(0.21)
    sol_candles = make_candles(166.0)
    signals = [
        Signal(id="sig-1", symbol="ALLUSDT", period="1H", strategyId="st-trend-1", strategyName="趋势启动1号", signalType="趋势信号", score=92, triggeredAt="2026-05-29 10:28", price=0.2563, summary="低位横盘后放量站上均线，趋势启动概率提高。", analysis=["过去10天振幅低于30%", "最近10根K线多数收盘价位于EMA20上方", "1小时成交量突破过去24小时均值3倍"], strengthGrade="A", candles=all_candles),
        Signal(id="sig-2", symbol="WIFUSDT", period="1H", strategyId="st-trend-1", strategyName="趋势启动1号", signalType="趋势信号", score=88, triggeredAt="2026-05-29 10:17", price=1.265, summary="价格重回短均线，观察二次确认。", analysis=["MA5向上穿越MA20", "回踩未破前低", "量能温和放大"], strengthGrade="A", candles=make_candles(1.02)),
        Signal(id="sig-3", symbol="PEPEUSDT", period="4H", strategyId="st-volume-1", strategyName="放量突破回踩", signalType="突破信号", score=86, triggeredAt="2026-05-29 09:56", price=0.00001234, summary="放量突破后回踩结构保持。", analysis=["突破48小时高点", "回踩未跌回箱体", "资金流入保持"], strengthGrade="B", candles=make_candles(0.0000108)),
        Signal(id="sig-4", symbol="SOLUSDT", period="4H", strategyId="st-volume-1", strategyName="放量突破回踩", signalType="突破信号", score=83, triggeredAt="2026-05-29 09:33", price=170.25, summary="强势币种突破后进入确认区。", analysis=["24小时涨幅领先", "高点附近成交活跃", "均线多头排列"], strengthGrade="B", candles=sol_candles),
        Signal(id="sig-5", symbol="VOXELUSDT", period="1H", strategyId="st-watch-1", strategyName="观察池条件", signalType="观察信号", score=78, triggeredAt="2026-05-29 09:12", price=0.1287, summary="观察池价格条件命中。", analysis=["价格突破观察位", "短周期量能增强", "仍需确认站稳"], strengthGrade="C", candles=make_candles(0.11)),
    ]
    watchlist = [
        WatchItem(id="watch-1", symbol="ALLUSDT", currentPrice=0.2563, change24h=18.35, conditions=[WatchCondition(id="wc-1", type="price", period="1H", expression="价格 > 0.3000", status="pending", lastTriggeredAt=None), WatchCondition(id="wc-2", type="ma", period="1H", expression="价格 < MA20", status="unmatched", lastTriggeredAt="2026-05-29 09:41")], lastTriggeredAt="2026-05-29 10:28", createdAt="2026-05-29 10:10"),
        WatchItem(id="watch-2", symbol="SOLUSDT", currentPrice=170.25, change24h=6.72, conditions=[WatchCondition(id="wc-3", type="breakout", period="4H", expression="突破48小时高点", status="matched", lastTriggeredAt="2026-05-29 09:56")], lastTriggeredAt="2026-05-29 09:56", createdAt="2026-05-28 18:00"),
        WatchItem(id="watch-3", symbol="VOXELUSDT", currentPrice=0.1287, change24h=9.21, conditions=[WatchCondition(id="wc-4", type="volume", period="1H", expression="成交量 > 24H均量3倍", status="matched", lastTriggeredAt="2026-05-29 09:12")], lastTriggeredAt="2026-05-29 09:12", createdAt="2026-05-27 12:00"),
        WatchItem(id="watch-4", symbol="DOGEUSDT", currentPrice=0.11234, change24h=-1.25, conditions=[WatchCondition(id="wc-5", type="price", period="1H", expression="价格站回MA20", status="pending", lastTriggeredAt=None)], lastTriggeredAt=None, createdAt="2026-05-26 15:00"),
    ]
    cases = [
        KnowledgeCase(id="case-1", title="ALLUSDT 趋势启动成功案例", symbol="ALLUSDT", strategyId="st-trend-1", strategyName="趋势启动1号", score=91, createdAt="2026-05-29 10:15", summary="长期低位震荡后放量站上均线，随后形成趋势延续。", reasons=["横盘收敛降低假突破概率", "放量突破说明主动买盘增强", "回踩不破MA20提高确认度"], lessons=["低位横盘后的首次放量更值得关注", "信号出现后应等待回踩确认", "若跌回箱体需及时撤销观察"], candles=all_candles),
    ]
    return strategies, signals, watchlist, cases
```

`backend/app/store.py`:

```python
from uuid import uuid4

from app.mock_data import build_initial_data
from app.models import CreateStrategyRequest, CreateWatchItemRequest, GeneratedStrategy, Strategy, WatchItem


class MockStore:
    def __init__(self) -> None:
        self.strategies, self.signals, self.watchlist, self.knowledge_cases = build_initial_data()

    def generate_strategy(self, period: str, conditions: list[str]) -> GeneratedStrategy:
        return GeneratedStrategy(
            name="AI 趋势启动观察",
            period=period,
            description="根据输入条件生成的趋势启动策略，用于捕捉低位横盘后的放量突破。",
            conditions=conditions,
            signalType="趋势信号",
            strengthGrade="A",
            score=89,
        )

    def create_strategy(self, payload: CreateStrategyRequest) -> Strategy:
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
            createdAt="2026-05-31 13:30",
        )
        self.strategies.insert(0, strategy)
        return strategy

    def create_watch_item(self, payload: CreateWatchItemRequest) -> WatchItem:
        item = WatchItem(
            id=f"watch-{uuid4().hex[:8]}",
            symbol=payload.symbol,
            currentPrice=0.0,
            change24h=0.0,
            conditions=payload.conditions,
            lastTriggeredAt=None,
            createdAt="2026-05-31 13:30",
        )
        self.watchlist.insert(0, item)
        return item


store = MockStore()
```

- [ ] **Step 5: Run tests and verify they pass**

Run:

```powershell
cd D:\Axis\backend
python -m pytest tests/test_api.py -v
```

Expected: health and store tests pass.

## Task 3: Backend REST Routers

**Files:**
- Create: `backend/app/routers/dashboard.py`
- Create: `backend/app/routers/strategies.py`
- Create: `backend/app/routers/signals.py`
- Create: `backend/app/routers/watchlist.py`
- Create: `backend/app/routers/knowledge.py`
- Modify: `backend/app/main.py`
- Modify: `backend/tests/test_api.py`

- [ ] **Step 1: Add API endpoint tests**

Append to `backend/tests/test_api.py`:

```python
def test_dashboard_summary():
    response = client.get("/api/dashboard/summary")
    assert response.status_code == 200
    body = response.json()
    assert body["todaySignals"] >= 5
    assert body["latestSignals"][0]["symbol"]


def test_strategy_generation_and_save():
    generate_response = client.post(
        "/api/strategies/generate",
        json={"period": "1H", "conditions": ["近10天振幅小于30%", "价格站上MA20"]},
    )
    assert generate_response.status_code == 200
    generated = generate_response.json()
    assert generated["strengthGrade"] == "A"

    save_response = client.post("/api/strategies", json=generated)
    assert save_response.status_code == 200
    assert save_response.json()["source"] == "ai"


def test_toggle_strategy_enabled():
    response = client.patch("/api/strategies/st-trend-1/enabled", json={"enabled": False})
    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_signal_detail_and_watchlist_creation():
    signal_response = client.get("/api/signals/sig-1")
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
    )
    assert watch_response.status_code == 200
    assert watch_response.json()["symbol"] == "ALLUSDT"


def test_knowledge_case_detail():
    response = client.get("/api/knowledge/case-1")
    assert response.status_code == 200
    assert response.json()["strategyName"] == "趋势启动1号"
```

- [ ] **Step 2: Run tests and verify endpoint failures**

Run:

```powershell
cd D:\Axis\backend
python -m pytest tests/test_api.py -v
```

Expected: endpoint tests fail with `404`.

- [ ] **Step 3: Create routers**

`backend/app/routers/dashboard.py`:

```python
from fastapi import APIRouter

from app.models import DashboardSummary
from app.store import store

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def summary() -> DashboardSummary:
    enabled_count = sum(1 for strategy in store.strategies if strategy.enabled)
    return DashboardSummary(
        todaySignals=len(store.signals),
        enabledStrategies=enabled_count,
        watchSymbols=len(store.watchlist),
        observationAlerts=sum(1 for item in store.watchlist for condition in item.conditions if condition.status == "matched"),
        runningStrategies=enabled_count,
        signalTrend=[
            {"date": "05-23", "count": 10},
            {"date": "05-24", "count": 16},
            {"date": "05-25", "count": 14},
            {"date": "05-26", "count": 21},
            {"date": "05-27", "count": 23},
            {"date": "05-28", "count": 20},
            {"date": "05-29", "count": len(store.signals)},
        ],
        latestSignals=store.signals[:5],
        recentStrategies=store.strategies[:3],
        recentWatchlist=store.watchlist[:3],
    )
```

`backend/app/routers/strategies.py`:

```python
from fastapi import APIRouter, HTTPException

from app.models import CreateStrategyRequest, GenerateStrategyRequest, GeneratedStrategy, Strategy, ToggleEnabledRequest
from app.store import store

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("", response_model=list[Strategy])
def list_strategies() -> list[Strategy]:
    return store.strategies


@router.post("/generate", response_model=GeneratedStrategy)
def generate_strategy(payload: GenerateStrategyRequest) -> GeneratedStrategy:
    return store.generate_strategy(payload.period, payload.conditions)


@router.post("", response_model=Strategy)
def create_strategy(payload: CreateStrategyRequest) -> Strategy:
    return store.create_strategy(payload)


@router.patch("/{strategy_id}/enabled", response_model=Strategy)
def toggle_strategy(strategy_id: str, payload: ToggleEnabledRequest) -> Strategy:
    for strategy in store.strategies:
        if strategy.id == strategy_id:
            strategy.enabled = payload.enabled
            return strategy
    raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Strategy not found", "details": strategy_id})
```

`backend/app/routers/signals.py`:

```python
from fastapi import APIRouter, HTTPException

from app.models import Signal
from app.store import store

router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("", response_model=list[Signal])
def list_signals() -> list[Signal]:
    return store.signals


@router.get("/{signal_id}", response_model=Signal)
def get_signal(signal_id: str) -> Signal:
    for signal in store.signals:
        if signal.id == signal_id:
            return signal
    raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Signal not found", "details": signal_id})
```

`backend/app/routers/watchlist.py`:

```python
from fastapi import APIRouter, HTTPException

from app.models import CreateWatchItemRequest, WatchItem
from app.store import store

router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchItem])
def list_watchlist() -> list[WatchItem]:
    return store.watchlist


@router.get("/{watch_item_id}", response_model=WatchItem)
def get_watch_item(watch_item_id: str) -> WatchItem:
    for item in store.watchlist:
        if item.id == watch_item_id:
            return item
    raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Watch item not found", "details": watch_item_id})


@router.post("", response_model=WatchItem)
def create_watch_item(payload: CreateWatchItemRequest) -> WatchItem:
    return store.create_watch_item(payload)
```

`backend/app/routers/knowledge.py`:

```python
from fastapi import APIRouter, HTTPException

from app.models import KnowledgeCase
from app.store import store

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


@router.get("/{case_id}", response_model=KnowledgeCase)
def get_case(case_id: str) -> KnowledgeCase:
    for case in store.knowledge_cases:
        if case.id == case_id:
            return case
    raise HTTPException(status_code=404, detail={"code": "not_found", "message": "Knowledge case not found", "details": case_id})
```

- [ ] **Step 4: Register routers**

Replace `backend/app/main.py` with:

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import dashboard, knowledge, signals, strategies, watchlist

app = FastAPI(title="TrendAI Signal Discovery API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(strategies.router)
app.include_router(signals.router)
app.include_router(watchlist.router)
app.include_router(knowledge.router)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
```

- [ ] **Step 5: Run backend tests**

Run:

```powershell
cd D:\Axis\backend
python -m pytest tests/test_api.py -v
```

Expected: all backend tests pass.

## Task 4: Frontend Scaffold And API Client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/index.html`
- Create: `frontend/tsconfig.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/types.ts`
- Create: `frontend/src/api.ts`
- Create: `frontend/src/data-format.ts`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/styles.css`

- [ ] **Step 1: Create package and config files**

`frontend/package.json`:

```json
{
  "scripts": {
    "dev": "vite --host 127.0.0.1",
    "build": "tsc && vite build",
    "preview": "vite preview --host 127.0.0.1"
  },
  "dependencies": {
    "@vitejs/plugin-react": "^4.3.4",
    "vite": "^6.0.7",
    "typescript": "^5.7.2",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "lucide-react": "^0.468.0"
  },
  "devDependencies": {}
}
```

`frontend/index.html`:

```html
<div id="root"></div>
<script type="module" src="/src/main.tsx"></script>
```

`frontend/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2020",
    "useDefineForClassFields": true,
    "lib": ["DOM", "DOM.Iterable", "ES2020"],
    "allowJs": false,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "allowSyntheticDefaultImports": true,
    "strict": true,
    "forceConsistentCasingInFileNames": true,
    "module": "ESNext",
    "moduleResolution": "Node",
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx"
  },
  "include": ["src"],
  "references": []
}
```

`frontend/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": "http://127.0.0.1:8000"
    }
  }
});
```

- [ ] **Step 2: Create shared frontend types**

`frontend/src/types.ts`:

```ts
export type Period = "1H" | "4H" | "1D";
export type StrengthGrade = "S" | "A" | "B" | "C";
export type WatchStatus = "pending" | "matched" | "unmatched";

export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma5: number;
  ma20: number;
  ma60: number;
}

export interface Strategy {
  id: string;
  name: string;
  source: "preset" | "ai";
  period: Period;
  enabled: boolean;
  conditions: string[];
  description: string;
  score: number;
  todaySignalCount: number;
  lastTriggeredAt: string | null;
  createdAt: string;
}

export interface GeneratedStrategy {
  name: string;
  period: Period;
  description: string;
  conditions: string[];
  signalType: string;
  strengthGrade: StrengthGrade;
  score: number;
}

export interface Signal {
  id: string;
  symbol: string;
  period: Period;
  strategyId: string;
  strategyName: string;
  signalType: string;
  score: number;
  triggeredAt: string;
  price: number;
  summary: string;
  analysis: string[];
  strengthGrade: StrengthGrade;
  candles: Candle[];
}

export interface WatchCondition {
  id: string;
  type: string;
  period: Period;
  expression: string;
  status: WatchStatus;
  lastTriggeredAt: string | null;
}

export interface WatchItem {
  id: string;
  symbol: string;
  currentPrice: number;
  change24h: number;
  conditions: WatchCondition[];
  lastTriggeredAt: string | null;
  createdAt: string;
}

export interface KnowledgeCase {
  id: string;
  title: string;
  symbol: string;
  strategyId: string;
  strategyName: string;
  score: number;
  createdAt: string;
  summary: string;
  reasons: string[];
  lessons: string[];
  candles: Candle[];
}

export interface DashboardSummary {
  todaySignals: number;
  enabledStrategies: number;
  watchSymbols: number;
  observationAlerts: number;
  runningStrategies: number;
  signalTrend: Array<{ date: string; count: number }>;
  latestSignals: Signal[];
  recentStrategies: Strategy[];
  recentWatchlist: WatchItem[];
}
```

- [ ] **Step 3: Create API client and formatting helpers**

`frontend/src/api.ts`:

```ts
import type { DashboardSummary, GeneratedStrategy, KnowledgeCase, Period, Signal, Strategy, WatchCondition, WatchItem } from "./types";

const jsonHeaders = { "Content-Type": "application/json" };

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    throw new Error(`API ${response.status}: ${url}`);
  }
  return response.json() as Promise<T>;
}

export const api = {
  dashboard: () => request<DashboardSummary>("/api/dashboard/summary"),
  strategies: () => request<Strategy[]>("/api/strategies"),
  generateStrategy: (period: Period, conditions: string[]) =>
    request<GeneratedStrategy>("/api/strategies/generate", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ period, conditions })
    }),
  createStrategy: (payload: GeneratedStrategy) =>
    request<Strategy>("/api/strategies", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(payload)
    }),
  setStrategyEnabled: (id: string, enabled: boolean) =>
    request<Strategy>(`/api/strategies/${id}/enabled`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify({ enabled })
    }),
  signals: () => request<Signal[]>("/api/signals"),
  signal: (id: string) => request<Signal>(`/api/signals/${id}`),
  watchlist: () => request<WatchItem[]>("/api/watchlist"),
  watchItem: (id: string) => request<WatchItem>(`/api/watchlist/${id}`),
  createWatchItem: (symbol: string, conditions: WatchCondition[]) =>
    request<WatchItem>("/api/watchlist", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ symbol, conditions })
    }),
  knowledgeCase: (id: string) => request<KnowledgeCase>(`/api/knowledge/${id}`)
};
```

`frontend/src/data-format.ts`:

```ts
export function formatPrice(value: number): string {
  if (value < 0.001) return value.toFixed(8);
  if (value < 1) return value.toFixed(4);
  return value.toFixed(3);
}

export function formatPercent(value: number): string {
  return `${value > 0 ? "+" : ""}${value.toFixed(2)}%`;
}
```

- [ ] **Step 4: Create minimal app entry**

`frontend/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
```

`frontend/src/App.tsx`:

```tsx
export default function App() {
  return <div className="app">TrendAI Signal Discovery</div>;
}
```

`frontend/src/styles.css`:

```css
:root {
  font-family: Inter, "Microsoft YaHei", system-ui, sans-serif;
  color: #182033;
  background: #f3f6fb;
}

* {
  box-sizing: border-box;
}

body {
  margin: 0;
}

.app {
  min-height: 100vh;
}
```

- [ ] **Step 5: Install dependencies and build**

Run:

```powershell
cd D:\Axis\frontend
cmd /c npm install --cache .npm-cache
cmd /c npm run build
```

Expected: Vite build succeeds.

## Task 5: Frontend Shell And Reusable UI

**Files:**
- Create: `frontend/src/components/AppShell.tsx`
- Create: `frontend/src/components/Charts.tsx`
- Create: `frontend/src/components/Modal.tsx`
- Create: `frontend/src/components/StrengthGrade.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Create reusable components**

`frontend/src/components/AppShell.tsx`:

```tsx
import { BarChart3, BellRing, BookOpen, Eye, Home, Settings, Sparkles } from "lucide-react";
import type { ReactNode } from "react";

export type ViewKey = "dashboard" | "strategies" | "signals" | "signal-detail" | "watchlist" | "watch-detail" | "knowledge";

const navItems = [
  { key: "dashboard" as const, label: "首页", icon: Home },
  { key: "strategies" as const, label: "策略中心", icon: BarChart3 },
  { key: "signals" as const, label: "信号中心", icon: BellRing },
  { key: "watchlist" as const, label: "观察池", icon: Eye },
  { key: "knowledge" as const, label: "知识库", icon: BookOpen },
];

export function AppShell({ activeView, onNavigate, children }: { activeView: ViewKey; onNavigate: (view: ViewKey) => void; children: ReactNode }) {
  return (
    <div className="shell">
      <aside className="sidebar">
        <div className="brand"><Sparkles size={18} /> TrendAI</div>
        <nav>
          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <button key={item.key} className={activeView === item.key ? "nav-item active" : "nav-item"} onClick={() => onNavigate(item.key)}>
                <Icon size={16} /> {item.label}
              </button>
            );
          })}
        </nav>
        <button className="nav-item"><Settings size={16} /> 设置</button>
      </aside>
      <main className="main">{children}</main>
    </div>
  );
}
```

`frontend/src/components/Charts.tsx`:

```tsx
import type { Candle } from "../types";

export function SparkLine({ values }: { values: number[] }) {
  const max = Math.max(...values);
  const min = Math.min(...values);
  const points = values.map((value, index) => `${(index / Math.max(values.length - 1, 1)) * 100},${36 - ((value - min) / Math.max(max - min, 1)) * 28}`).join(" ");
  return <svg className="sparkline" viewBox="0 0 100 40"><polyline points={points} /></svg>;
}

export function KlineChart({ candles }: { candles: Candle[] }) {
  const max = Math.max(...candles.map((c) => c.high));
  const min = Math.min(...candles.map((c) => c.low));
  const scaleY = (value: number) => 160 - ((value - min) / Math.max(max - min, 0.000001)) * 130;
  return (
    <svg className="kline" viewBox="0 0 720 230">
      <g className="grid">{[40, 80, 120, 160].map((y) => <line key={y} x1="0" x2="720" y1={y} y2={y} />)}</g>
      {candles.map((candle, index) => {
        const x = 14 + index * 20;
        const up = candle.close >= candle.open;
        const bodyTop = scaleY(Math.max(candle.open, candle.close));
        const bodyHeight = Math.max(Math.abs(scaleY(candle.open) - scaleY(candle.close)), 3);
        return (
          <g key={`${candle.time}-${index}`} className={up ? "candle up" : "candle down"}>
            <line x1={x} x2={x} y1={scaleY(candle.high)} y2={scaleY(candle.low)} />
            <rect x={x - 5} y={bodyTop} width="10" height={bodyHeight} rx="1" />
            <rect x={x - 5} y={185 - Math.min(candle.volume / 90, 42)} width="10" height={Math.min(candle.volume / 90, 42)} rx="1" className="volume" />
          </g>
        );
      })}
    </svg>
  );
}
```

`frontend/src/components/Modal.tsx`:

```tsx
import type { ReactNode } from "react";
import { X } from "lucide-react";

export function Modal({ title, onClose, children }: { title: string; onClose: () => void; children: ReactNode }) {
  return (
    <div className="modal-backdrop">
      <section className="modal">
        <header className="modal-header">
          <h2>{title}</h2>
          <button className="icon-button" onClick={onClose} aria-label="关闭"><X size={18} /></button>
        </header>
        {children}
      </section>
    </div>
  );
}
```

`frontend/src/components/StrengthGrade.tsx`:

```tsx
import type { StrengthGrade as Grade } from "../types";

export function StrengthGrade({ grade, score }: { grade: Grade; score: number }) {
  return (
    <div className="strength">
      <div className="grade">{grade}<span>级</span></div>
      <p>信号强度 {score}</p>
      <div className="strength-track"><span style={{ width: `${score}%` }} /></div>
    </div>
  );
}
```

- [ ] **Step 2: Wire shell with a minimal loading view**

Replace `frontend/src/App.tsx` with:

```tsx
import { useState } from "react";
import { AppShell, type ViewKey } from "./components/AppShell";

export default function App() {
  const [view, setView] = useState<ViewKey>("dashboard");
  return (
    <AppShell activeView={view} onNavigate={setView}>
      <section className="page"><h1>TrendAI</h1><p>信号发现系统正在加载。</p></section>
    </AppShell>
  );
}
```

- [ ] **Step 3: Add layout and component styles**

Append to `frontend/src/styles.css` the complete UI foundation:

```css
button, input, select { font: inherit; }
button { cursor: pointer; }
.shell { display: grid; grid-template-columns: 180px 1fr; min-height: 100vh; }
.sidebar { background: #ffffff; border-right: 1px solid #e3e8f2; padding: 18px 14px; display: flex; flex-direction: column; gap: 20px; }
.brand { display: flex; align-items: center; gap: 8px; font-weight: 800; color: #2732d9; }
nav { display: grid; gap: 8px; }
.nav-item { display: flex; align-items: center; gap: 9px; border: 0; background: transparent; color: #536078; padding: 10px 12px; border-radius: 8px; text-align: left; }
.nav-item.active, .nav-item:hover { background: #eef0ff; color: #2732d9; }
.main { padding: 22px; overflow: auto; }
.page { max-width: 1260px; margin: 0 auto; }
.page-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.page-header h1 { margin: 0; font-size: 22px; }
.muted { color: #7b8498; }
.grid { display: grid; gap: 14px; }
.kpis { grid-template-columns: repeat(5, minmax(140px, 1fr)); }
.card, .panel { background: #fff; border: 1px solid #e4e9f4; border-radius: 8px; box-shadow: 0 8px 28px rgba(40, 48, 70, 0.05); }
.card { padding: 16px; }
.panel { padding: 18px; }
.card-title { color: #7a8498; font-size: 13px; margin-bottom: 8px; }
.metric { font-size: 28px; color: #3036e8; font-weight: 800; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 13px 12px; border-bottom: 1px solid #edf1f7; font-size: 14px; }
.table th { color: #7a8498; font-weight: 600; background: #fbfcff; }
.primary { border: 0; background: #3938e8; color: white; border-radius: 7px; padding: 10px 14px; display: inline-flex; align-items: center; gap: 8px; }
.secondary { border: 1px solid #d8def0; background: white; color: #364057; border-radius: 7px; padding: 9px 13px; }
.chip { display: inline-flex; align-items: center; gap: 5px; padding: 5px 9px; border-radius: 999px; background: #eef7ff; color: #2465d8; font-size: 12px; }
.status-on { color: #16a56a; font-weight: 700; }
.status-off { color: #9aa4b6; font-weight: 700; }
.positive { color: #10a66a; font-weight: 700; }
.negative { color: #e84c5a; font-weight: 700; }
.sparkline { width: 100%; height: 58px; }
.sparkline polyline { fill: none; stroke: #3438e8; stroke-width: 4; stroke-linecap: round; stroke-linejoin: round; }
.kline { width: 100%; height: 300px; background: #fbfcff; border-radius: 8px; }
.grid line { stroke: #e8edf5; }
.candle line { stroke-width: 1.5; }
.candle rect { opacity: 0.95; }
.candle.up line, .candle.up rect { stroke: #10b981; fill: #10b981; }
.candle.down line, .candle.down rect { stroke: #ef4444; fill: #ef4444; }
.candle .volume { opacity: 0.35; stroke: none; }
.modal-backdrop { position: fixed; inset: 0; background: rgba(21, 28, 45, 0.28); display: grid; place-items: center; padding: 24px; z-index: 20; }
.modal { width: min(920px, 100%); max-height: 88vh; overflow: auto; background: white; border-radius: 10px; border: 1px solid #e4e9f4; box-shadow: 0 20px 70px rgba(20, 25, 45, 0.22); padding: 22px; }
.modal-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 18px; }
.modal-header h2 { margin: 0; font-size: 20px; }
.icon-button { border: 0; background: transparent; padding: 7px; border-radius: 6px; }
.strength { background: #f8fafc; border: 1px solid #e6ecf5; border-radius: 8px; padding: 18px; text-align: center; }
.grade { color: #13a05f; font-size: 34px; font-weight: 900; }
.grade span { font-size: 15px; margin-left: 2px; }
.strength-track { height: 8px; border-radius: 99px; background: #dde4ee; overflow: hidden; }
.strength-track span { display: block; height: 100%; background: #1fb36f; }
@media (max-width: 900px) { .shell { grid-template-columns: 1fr; } .sidebar { position: sticky; top: 0; z-index: 10; flex-direction: row; overflow-x: auto; } nav { display: flex; } .kpis { grid-template-columns: repeat(2, 1fr); } }
```

- [ ] **Step 4: Build frontend**

Run:

```powershell
cd D:\Axis\frontend
cmd /c npm run build
```

Expected: build succeeds.

## Task 6: Frontend Pages And Product Flow

**Files:**
- Create all files under `frontend/src/pages`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`

- [ ] **Step 1: Create page components**

Create these pages with props that receive data and navigation callbacks:

- `Dashboard.tsx`: render KPI cards, signal trend, latest signals, recent strategies, recent watchlist.
- `Strategies.tsx`: render strategy table, enabled toggle, and AI generation modal flow.
- `Signals.tsx`: render signal table and call `onOpenSignal(id)`.
- `SignalDetail.tsx`: render selected signal, K-line chart, analysis, strength grade, and add-to-watch action.
- `Watchlist.tsx`: render watchlist table and add watch modal.
- `WatchDetail.tsx`: render selected watch item with condition statuses.
- `KnowledgeCase.tsx`: render case summary, reasons, lessons, and K-line chart.

Use the existing components from Task 5. Keep each page under 220 lines by moving repeated charts and grades into shared components.

- [ ] **Step 2: Create application orchestration**

Replace `frontend/src/App.tsx` with a stateful component that:

- loads dashboard, strategies, signals, watchlist, and knowledge case on mount,
- tracks `view`, `selectedSignalId`, and `selectedWatchId`,
- calls `api.createStrategy` after AI generation confirmation,
- calls `api.setStrategyEnabled` for toggles,
- calls `api.createWatchItem` from signal detail and add watch modal,
- refreshes relevant lists after mutations.

Use this state shape:

```tsx
const [view, setView] = useState<ViewKey>("dashboard");
const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
const [strategies, setStrategies] = useState<Strategy[]>([]);
const [signals, setSignals] = useState<Signal[]>([]);
const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
const [knowledgeCase, setKnowledgeCase] = useState<KnowledgeCase | null>(null);
const [selectedSignalId, setSelectedSignalId] = useState("sig-1");
const [selectedWatchId, setSelectedWatchId] = useState("watch-1");
const [error, setError] = useState<string | null>(null);
```

- [ ] **Step 3: Add page-specific styles**

Append styles for:

- `.split-layout`
- `.toolbar`
- `.tabs`
- `.form-grid`
- `.condition-list`
- `.detail-layout`
- `.analysis-list`
- `.watch-condition`
- `.case-layout`

Use restrained white panels, blue action buttons, green/red market states, and stable table spacing consistent with the reference screens.

- [ ] **Step 4: Build frontend**

Run:

```powershell
cd D:\Axis\frontend
cmd /c npm run build
```

Expected: build succeeds.

## Task 7: End-To-End Local Verification

**Files:**
- No new files required.

- [ ] **Step 1: Run backend tests**

Run:

```powershell
cd D:\Axis\backend
python -m pytest tests/test_api.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend build**

Run:

```powershell
cd D:\Axis\frontend
cmd /c npm run build
```

Expected: build succeeds.

- [ ] **Step 3: Start backend**

Run:

```powershell
cd D:\Axis\backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Expected: FastAPI starts on `http://127.0.0.1:8000`.

- [ ] **Step 4: Start frontend**

Run:

```powershell
cd D:\Axis\frontend
cmd /c npm run dev
```

Expected: Vite starts on `http://127.0.0.1:5173`.

- [ ] **Step 5: Browser verification**

Open `http://127.0.0.1:5173` and verify:

- dashboard loads without console errors,
- AI strategy modal generates and saves a strategy,
- saved strategy appears in the strategy table,
- signal list opens signal detail,
- signal detail can create a watch item,
- watchlist and watch detail render,
- knowledge case renders.

## Self-Review

Spec coverage:

- Dashboard, strategy list, AI strategy generation, signal list/detail, watchlist list/detail, add watch, and knowledge case are covered by Tasks 3, 5, and 6.
- FastAPI backend, Pydantic models, mock store, and REST API boundaries are covered by Tasks 1 through 3.
- Build and API verification are covered by Tasks 4 through 7.

Red-flag scan:

- The plan contains no unfinished implementation markers or unspecified tasks.

Type consistency:

- Backend and frontend both use `Period`, `StrengthGrade`, `Strategy`, `Signal`, `WatchItem`, `WatchCondition`, `KnowledgeCase`, and `DashboardSummary` with matching field names.

Git note:

- `D:\Axis` is not currently a git repository. Commit steps are intentionally omitted until a repository is initialized.
