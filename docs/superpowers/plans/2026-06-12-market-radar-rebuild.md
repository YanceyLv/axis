# Market Radar Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the market radar calculation and presentation logic so every displayed metric is explainable, recommendations only include tradable strong setups, and the page always reads cached snapshots instead of recalculating on request.

**Architecture:** Keep the existing snapshot-based backend architecture and rebuild the snapshot payload generation around a tradable symbol universe filtered by real Binance `24H` turnover. Replace the single mixed recommendation pool with three explicit categories (`short_start`, `short_follow`, `trend_72h`), then minimally adapt the frontend types and page rendering to present the new fields without changing routes or page ownership.

**Tech Stack:** FastAPI, Pydantic, Python store layer, frontend React + TypeScript, existing Vite build, existing source-level and pytest regression tests.

---

### Task 1: Lock the new market radar contract with failing backend tests

**Files:**
- Modify: `backend/tests/test_api.py`
- Check: `backend/app/models.py`
- Check: `backend/app/store.py`

- [ ] **Step 1: Write the failing tests for tradable-pool filtering and category outputs**

```python
def test_market_radar_excludes_symbols_below_min_24h_quote_volume(monkeypatch):
    headers = auth_headers("market-radar-volume-filter@example.com")
    base_time = datetime(2026, 6, 12, 0, 0, 0, tzinfo=timezone.utc)
    store.upsert_market_candles(
        "STRONGUSDT",
        "1H",
        trend_candles(10.0, 0.6, count=90, volume=1200, volume_step=120, start=base_time),
    )
    store.upsert_market_candles(
        "THINUSDT",
        "1H",
        trend_candles(3.0, 0.8, count=90, volume=200, volume_step=50, start=base_time),
    )

    monkeypatch.setattr(
        store,
        "_fetch_market_radar_ticker_24h",
        lambda: {
            "STRONGUSDT": {"quoteVolume": 18_000_000},
            "THINUSDT": {"quoteVolume": 8_000_000},
        },
    )

    snapshot = store.refresh_market_radar_snapshot("1H", base_time)

    symbols = {
        item.symbol
        for section in snapshot.sections
        for item in section.items
    }
    assert "STRONGUSDT" in symbols
    assert "THINUSDT" not in symbols


def test_market_radar_splits_results_into_three_explicit_sections(monkeypatch):
    headers = auth_headers("market-radar-sections@example.com")
    base_time = datetime(2026, 6, 12, 0, 0, 0, tzinfo=timezone.utc)
    seed_market_radar_fixture(store, base_time)
    monkeypatch.setattr(store, "_fetch_market_radar_ticker_24h", seeded_24h_tickers)

    snapshot = store.refresh_market_radar_snapshot("1H", base_time)

    keys = [section.key for section in snapshot.sections]
    assert keys == ["short_start", "short_follow", "trend_72h"]
    assert snapshot.opportunityGroups["short_start"] >= 1
    assert snapshot.opportunityGroups["short_follow"] >= 1
    assert snapshot.opportunityGroups["trend_72h"] >= 1
```

- [ ] **Step 2: Run the focused backend tests to verify they fail on the current contract**

Run: `D:\Axis\backend\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_radar_volume_filter or market_radar_sections" -q`

Expected: FAIL because the current snapshot does not fetch Binance `24H` turnover, has no `sections` field, and still returns one mixed `recommendations` list.

- [ ] **Step 3: Add failing tests for weak-chop exclusion and snapshot-read behavior**

```python
def test_market_radar_does_not_recommend_weak_chop_symbols(monkeypatch):
    base_time = datetime(2026, 6, 12, 0, 0, 0, tzinfo=timezone.utc)
    store.upsert_market_candles(
        "CHOPUSDT",
        "1H",
        flat_then_wiggle_candles(5.0, count=90, start=base_time),
    )
    monkeypatch.setattr(
        store,
        "_fetch_market_radar_ticker_24h",
        lambda: {"CHOPUSDT": {"quoteVolume": 22_000_000}},
    )

    snapshot = store.refresh_market_radar_snapshot("1H", base_time)

    symbols = {
        item.symbol
        for section in snapshot.sections
        for item in section.items
    }
    assert "CHOPUSDT" not in symbols


def test_market_radar_endpoint_reads_cached_snapshot_sections(monkeypatch):
    headers = auth_headers("market-radar-cached-sections@example.com")
    base_time = datetime(2026, 6, 12, 0, 0, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(store, "_fetch_market_radar_ticker_24h", seeded_24h_tickers)
    snapshot = store.refresh_market_radar_snapshot("1H", base_time)

    def fail_compute(*args, **kwargs):
        raise AssertionError("endpoint must read cached snapshot only")

    monkeypatch.setattr(store, "_build_market_radar", fail_compute)

    response = client.get("/api/market/radar", headers=headers)

    assert response.status_code == 200
    assert response.json()["updatedAt"] == snapshot.updatedAt
```

- [ ] **Step 4: Run the expanded market radar backend slice**

Run: `D:\Axis\backend\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_radar" -q`

Expected: FAIL with missing fields / wrong recommendation behavior until the backend contract is rebuilt.

- [ ] **Step 5: Commit the red tests**

```bash
git add backend/tests/test_api.py
git commit -m "test: lock market radar rebuild contract"
```

### Task 2: Rebuild backend snapshot generation around tradable-pool analysis

**Files:**
- Modify: `backend/app/store.py`
- Modify: `backend/app/models.py`
- Check: `backend/app/routers/market.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: Add explicit response models for sections, items, and explainable metrics**

```python
class MarketRadarSectionItem(BaseModel):
    symbol: str
    category: Literal["short_start", "short_follow", "trend_72h"]
    score: int
    periodLabel: str
    movePrimary: str
    moveSecondary: str
    quoteVolume24h: float
    volumeRatio: float
    pullbackFromHighPct: float
    reason: str
    riskNote: str


class MarketRadarSection(BaseModel):
    key: Literal["short_start", "short_follow", "trend_72h"]
    title: str
    description: str
    items: list[MarketRadarSectionItem]


class MarketRadarResponse(BaseModel):
    updatedAt: str
    environment: MarketRadarEnvironment
    metrics: MarketRadarMetrics
    opportunityGroups: dict[str, int]
    sections: list[MarketRadarSection]
```

- [ ] **Step 2: Introduce a dedicated `24H` turnover fetch and tradable-pool builder in the store**

```python
def _fetch_market_radar_ticker_24h(self) -> dict[str, dict[str, float]]:
    rows = self.binance_client.ticker_24hr()
    return {
        row["symbol"].upper(): {
            "quoteVolume": float(row.get("quoteVolume") or 0.0),
            "volume": float(row.get("volume") or 0.0),
        }
        for row in rows
        if row.get("symbol")
    }


def _market_radar_tradable_pool(
    self,
    period: str,
    ticker_24h: dict[str, dict[str, float]],
    limit: int = 90,
) -> dict[str, list[Candle]]:
    snapshots = self._market_radar_snapshots(period, limit=limit)
    return {
        symbol: candles
        for symbol, candles in snapshots.items()
        if ticker_24h.get(symbol, {}).get("quoteVolume", 0.0) >= 10_000_000
    }
```

- [ ] **Step 3: Replace the old mixed analyzer with explicit per-symbol feature extraction**

```python
def _analyze_market_radar_symbol(
    symbol: str,
    candles: list[Candle],
    ticker_24h: dict[str, float],
) -> dict[str, Any] | None:
    ordered = sorted(candles, key=lambda candle: _parse_datetime(candle.time) or _MIN_UTC)
    if len(ordered) < 72:
        return None

    latest = ordered[-1]
    close_3h = ordered[-4].close
    close_6h = ordered[-7].close
    close_12h = ordered[-13].close
    close_24h = ordered[-25].close
    close_72h = ordered[-73].close

    return {
        "symbol": symbol,
        "quote_volume_24h": round(ticker_24h["quoteVolume"], 2),
        "change_3h": _pct_change(latest.close, close_3h),
        "change_6h": _pct_change(latest.close, close_6h),
        "change_12h": _pct_change(latest.close, close_12h),
        "change_24h": _pct_change(latest.close, close_24h),
        "change_72h": _pct_change(latest.close, close_72h),
        "volume_ratio_3h": _window_volume_ratio(ordered, recent_hours=3, previous_hours=9),
        "pullback_6h": _pullback_from_high(ordered[-6:]),
        "pullback_12h": _pullback_from_high(ordered[-12:]),
        "pullback_72h": _pullback_from_high(ordered[-72:]),
        "above_ma20": latest.ma20 > 0 and latest.close >= latest.ma20,
    }
```

- [ ] **Step 4: Build three category selectors and a new explainable environment summary**

```python
def _select_short_start(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        item
        for item in items
        if item["change_3h"] > 0
        and item["change_6h"] > 0
        and item["volume_ratio_3h"] >= 1.2
        and item["pullback_6h"] <= 1.8
    ]
    return sorted(candidates, key=_short_start_score, reverse=True)[:8]


def _select_short_follow(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = [
        item
        for item in items
        if item["change_6h"] > 0
        and item["change_12h"] > 0
        and item["above_ma20"]
        and item["pullback_12h"] <= 2.5
    ]
    return sorted(candidates, key=_short_follow_score, reverse=True)[:8]


def _select_trend_72h(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ranked = sorted(items, key=lambda item: item["change_72h"], reverse=True)
    top_cutoff = max(1, math.ceil(len(ranked) * 0.1))
    candidates = [
        item
        for item in ranked[:top_cutoff]
        if item["change_24h"] > 0 and item["pullback_72h"] <= 4.0
    ]
    return sorted(candidates, key=_trend_72h_score, reverse=True)[:8]
```

- [ ] **Step 5: Rewire snapshot refresh to use tradable-pool analysis and preserve cached-read behavior**

```python
def refresh_market_radar_snapshot(self, period: str = "1H", now: datetime | None = None) -> MarketRadarResponse:
    normalized_period = normalize_period(period)
    ticker_24h = self._fetch_market_radar_ticker_24h()
    snapshots = self._market_radar_tradable_pool(normalized_period, ticker_24h, limit=90)
    snapshot = _build_market_radar(snapshots, ticker_24h, now)
    self._upsert_market_radar_snapshot(normalized_period, snapshot)
    return snapshot


def market_radar(self) -> MarketRadarResponse:
    return self.market_radar_snapshot("1H") or _empty_market_radar_response()
```

- [ ] **Step 6: Run the targeted backend tests until they pass**

Run: `D:\Axis\backend\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_radar" -q`

Expected: PASS with the new `sections` contract, low-turnover exclusion, weak-chop exclusion, and cached snapshot read behavior.

- [ ] **Step 7: Run the full backend regression suite**

Run: `D:\Axis\backend\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`

Expected: PASS with no regressions outside the market radar contract.

- [ ] **Step 8: Commit the backend implementation**

```bash
git add backend/app/models.py backend/app/store.py backend/tests/test_api.py
git commit -m "feat: rebuild market radar backend logic"
```

### Task 3: Adapt frontend types and market radar page to the new snapshot shape

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/pages/MarketRadar.tsx`
- Modify: `frontend/src/market-radar-page.test.mjs`
- Check: `frontend/src/api.ts`
- Check: `frontend/src/App.tsx`

- [ ] **Step 1: Update frontend types to reflect sections and explainable fields**

```ts
export interface MarketRadarSectionItem {
  symbol: string;
  category: "short_start" | "short_follow" | "trend_72h";
  score: number;
  periodLabel: string;
  movePrimary: string;
  moveSecondary: string;
  quoteVolume24h: number;
  volumeRatio: number;
  pullbackFromHighPct: number;
  reason: string;
  riskNote: string;
}

export interface MarketRadarSection {
  key: "short_start" | "short_follow" | "trend_72h";
  title: string;
  description: string;
  items: MarketRadarSectionItem[];
}

export interface MarketRadarResponse {
  updatedAt: string;
  environment: MarketRadarEnvironment;
  metrics: MarketRadarMetrics;
  opportunityGroups: Record<MarketRadarSection["key"], number>;
  sections: MarketRadarSection[];
}
```

- [ ] **Step 2: Replace the single mixed recommendation table with three explicit section blocks**

```tsx
const sections = radar?.sections ?? [];

{sections.map((section) => (
  <section key={section.key} className="card radar-section-card">
    <div className="section-heading">
      <div>
        <h3>{section.title}</h3>
        <p>{section.description}</p>
      </div>
      <span className="section-count">{section.items.length} 个</span>
    </div>
    {section.items.length ? (
      <table className="table radar-table">
        <thead>
          <tr>
            <th>交易对</th>
            <th>核心涨幅</th>
            <th>24H 成交额</th>
            <th>量比</th>
            <th>距阶段高点回撤</th>
            <th>入选理由</th>
            <th>操作</th>
          </tr>
        </thead>
      </table>
    ) : (
      <div className="empty-state">当前没有符合条件的{section.title}标的。</div>
    )}
  </section>
))}
```

- [ ] **Step 3: Preserve the existing K-line preview and watchlist actions against section items**

```tsx
async function addToWatch(item: MarketRadarSectionItem) {
  const payload: CreateWatchItemPayload = {
    symbol: item.symbol,
    source: "market-radar",
    note: `${item.reason}｜24H成交额 ${formatTurnover(item.quoteVolume24h)}`,
  };
  await onCreateWatchItem(payload);
}

function openKlinePreview(item: MarketRadarSectionItem) {
  setSelectedKlineItem(item);
  setKlinePeriod("1H");
}
```

- [ ] **Step 4: Update the source-level page test to lock the new fields and sections**

```js
test("market radar page renders three explainable sections", () => {
  assert.equal(pageSource.includes("24H 成交额"), true);
  assert.equal(pageSource.includes("距阶段高点回撤"), true);
  assert.equal(pageSource.includes("short_start"), true);
  assert.equal(pageSource.includes("short_follow"), true);
  assert.equal(pageSource.includes("trend_72h"), true);
});
```

- [ ] **Step 5: Run the focused frontend source tests**

Run: `node --test src/market-radar-page.test.mjs src/app-shell-layout.test.mjs src/market-data-status.test.mjs`

Expected: PASS with the new section-based rendering and no regressions in existing page guards.

- [ ] **Step 6: Commit the frontend contract update**

```bash
git add frontend/src/types.ts frontend/src/pages/MarketRadar.tsx frontend/src/market-radar-page.test.mjs
git commit -m "feat: present market radar sections"
```

### Task 4: Verify end-to-end outputs and update project progress

**Files:**
- Modify: `PROJECT_PROGRESS.md`
- Check: `docs/superpowers/specs/2026-06-12-market-radar-rebuild-design.md`
- Check: `docs/superpowers/plans/2026-06-12-market-radar-rebuild.md`
- Check: `frontend/src/styles.css` if page structure needs small support styles

- [ ] **Step 1: Run the frontend production build against the final contract**

Run: `npm.cmd run build`

Expected: PASS. Existing Vite chunk warning may remain; record it if unchanged instead of expanding scope.

- [ ] **Step 2: If section layout needs minimal support styles, add only scoped market radar selectors**

```css
.radar-section-card {
  display: grid;
  gap: 16px;
}

.section-heading {
  display: flex;
  justify-content: space-between;
  align-items: start;
  gap: 12px;
}

.section-count {
  color: var(--muted-foreground);
  font-size: 13px;
}
```

- [ ] **Step 3: Append the completed task record to `PROJECT_PROGRESS.md`**

```md
## 2026-06-12 Task 18 市场雷达数据逻辑重构
### 当前状态
- 已将市场雷达改为“可交易池过滤 + 三类机会分层 + 只读缓存快照”。
### 实施计划
- [x] 锁定后端回归测试
- [x] 重构市场雷达快照生成逻辑
- [x] 前端按三类列表展示 explainable 字段
- [x] 完成后端测试与前端构建验证
### 修改记录
- ...
### 验证结果
- ...
### 下一步任务清单
- ...
### 风险点
- ...
```

- [ ] **Step 4: Run the final verification bundle**

Run: `D:\Axis\backend\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`

Expected: PASS

Run: `node --test src/market-radar-page.test.mjs src/app-shell-layout.test.mjs src/market-data-status.test.mjs`

Expected: PASS

Run: `npm.cmd run build`

Expected: PASS

- [ ] **Step 5: Commit the progress update and verification record**

```bash
git add PROJECT_PROGRESS.md docs/superpowers/plans/2026-06-12-market-radar-rebuild.md frontend/src/styles.css
git commit -m "docs: record market radar rebuild progress"
```

