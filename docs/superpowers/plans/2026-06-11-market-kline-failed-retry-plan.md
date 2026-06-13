# 数据采集失败任务重试 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `数据采集` 页面增加失败补齐任务明细与单任务同步重试能力，帮助运维人员在 UI 中直接定位和恢复失败任务。

**Architecture:** 复用现有 `GET /api/market/kline-status` 聚合接口返回失败任务明细，并新增一个受控的 `POST /api/market/kline-backfill/retry` 写接口，仅允许对单个 `failed` 任务执行一小轮同步补齐。前端保持现有页面布局，只在底部补充失败任务表、周期筛选和单行重试交互。

**Tech Stack:** FastAPI, Pydantic, MySQL store abstraction, React, TypeScript, existing CSS, pytest

---

### Task 1: 扩展后端模型以承载失败任务与重试结果

**Files:**
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: 写失败测试，锁定 `kline-status` 返回失败任务明细**

```python
def test_market_kline_status_includes_failed_tasks():
    headers = auth_headers("kline-failed-list@example.com")
    now_iso = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    store.upsert_market_kline_backfill_task(
        MarketKlineBackfillTask(
            id="mkbf-BNBUSDT-1H",
            symbol="BNBUSDT",
            period="1H",
            targetStart=datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
            targetEnd=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
            nextStart=datetime(2026, 6, 1, 6, 0, 0, tzinfo=timezone.utc).isoformat(),
            status="failed",
            pagesFetched=2,
            storedCandles=10,
            lastError="network timeout",
            createdAt=now_iso,
            updatedAt=now_iso,
        )
    )

    response = client.get("/api/market/kline-status", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body["failedTasks"]) == 1
    assert body["failedTasks"][0]["symbol"] == "BNBUSDT"
    assert body["failedTasks"][0]["period"] == "1H"
    assert body["failedTasks"][0]["lastError"] == "network timeout"
```

- [ ] **Step 2: 运行测试并确认先红**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "includes_failed_tasks" -q`
Expected: FAIL，报错提示响应中不存在 `failedTasks`

- [ ] **Step 3: 在模型中新增失败任务与重试响应类型**

```python
class MarketKlineFailedTask(BaseModel):
    symbol: str
    period: Period
    lastError: str = ""
    updatedAt: str
    pagesFetched: int
    storedCandles: int
    nextStart: str


class RetryMarketKlineBackfillRequest(BaseModel):
    symbol: str = Field(min_length=1)
    period: Period


class RetryMarketKlineBackfillResponse(BaseModel):
    symbol: str
    period: Period
    status: MarketKlineBackfillTaskStatus
    statusLabel: str
    storedCandles: int
    pagesFetched: int
    message: str
    updatedAt: str
```

- [ ] **Step 4: 把失败任务字段挂到状态响应模型**

```python
class MarketKlineStatusResponse(BaseModel):
    updatedAt: str
    overallStatus: Literal["running", "waiting", "completed", "warning"]
    overallStatusLabel: str
    activePhase: str
    cards: list[MarketKlineTaskCard]
    periodProgress: list[MarketKlinePeriodProgress]
    coverage: list[MarketKlineCoverage]
    runningTasks: list[MarketKlineRunningTask]
    failedTasks: list[MarketKlineFailedTask] = Field(default_factory=list)
    recentTasks: list[MarketKlineRecentTask]
    risks: list[str]
```

- [ ] **Step 5: 运行测试并确认转绿**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "includes_failed_tasks" -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/models.py backend/tests/test_api.py
git commit -m "test: add models for failed kline retry status"
```

### Task 2: 先用测试锁定重试接口的规则与互斥约束

**Files:**
- Modify: `backend/tests/test_api.py`
- Reference: `backend/app/store.py`
- Reference: `backend/app/routers/market.py`

- [ ] **Step 1: 写失败测试，锁定只有 failed 任务可以重试**

```python
def test_retry_market_kline_backfill_rejects_non_failed_task():
    headers = auth_headers("kline-retry-invalid@example.com")
    now_iso = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    store.upsert_market_kline_backfill_task(
        MarketKlineBackfillTask(
            id="mkbf-BTCUSDT-5M",
            symbol="BTCUSDT",
            period="5M",
            targetStart=datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
            targetEnd=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
            nextStart=datetime(2026, 6, 1, 6, 0, 0, tzinfo=timezone.utc).isoformat(),
            status="running",
            createdAt=now_iso,
            updatedAt=now_iso,
        )
    )

    response = client.post(
        "/api/market/kline-backfill/retry",
        headers=headers,
        json={"symbol": "BTCUSDT", "period": "5M"},
    )

    assert response.status_code == 409
    assert "仅允许重试失败任务" in response.json()["detail"]
```

- [ ] **Step 2: 写失败测试，锁定清理互斥时禁止重试**

```python
def test_retry_market_kline_backfill_rejects_while_cleanup_running():
    headers = auth_headers("kline-retry-cleanup@example.com")
    now_iso = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    store.upsert_market_kline_backfill_task(
        MarketKlineBackfillTask(
            id="mkbf-ETHUSDT-1D",
            symbol="ETHUSDT",
            period="1D",
            targetStart=datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
            targetEnd=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
            nextStart=datetime(2026, 6, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
            status="failed",
            lastError="network timeout",
            createdAt=now_iso,
            updatedAt=now_iso,
        )
    )
    store_module._market_kline_cleanup_state["cleaning"] = True

    response = client.post(
        "/api/market/kline-backfill/retry",
        headers=headers,
        json={"symbol": "ETHUSDT", "period": "1D"},
    )

    assert response.status_code == 409
    assert "当前正在清理 K 线" in response.json()["detail"]
```

- [ ] **Step 3: 写失败测试，锁定重试成功后的返回结构**

```python
def test_retry_market_kline_backfill_runs_single_failed_task(monkeypatch):
    headers = auth_headers("kline-retry-success@example.com")
    now_iso = datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat()
    original = MarketKlineBackfillTask(
        id="mkbf-SOLUSDT-5M",
        symbol="SOLUSDT",
        period="5M",
        targetStart=datetime(2026, 5, 1, 0, 0, 0, tzinfo=timezone.utc).isoformat(),
        targetEnd=datetime(2026, 6, 1, 12, 0, 0, tzinfo=timezone.utc).isoformat(),
        nextStart=datetime(2026, 6, 1, 6, 0, 0, tzinfo=timezone.utc).isoformat(),
        status="failed",
        pagesFetched=1,
        storedCandles=10,
        lastError="network timeout",
        createdAt=now_iso,
        updatedAt=now_iso,
    )
    store.upsert_market_kline_backfill_task(original)

    def fake_retry(task):
        return task.model_copy(
            update={
                "status": "completed",
                "pagesFetched": 2,
                "storedCandles": 25,
                "lastError": "",
                "updatedAt": _now_iso(),
            }
        )

    monkeypatch.setattr(store, "retry_market_kline_backfill_task", fake_retry)

    response = client.post(
        "/api/market/kline-backfill/retry",
        headers=headers,
        json={"symbol": "SOLUSDT", "period": "5M"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "SOLUSDT"
    assert body["period"] == "5M"
    assert body["status"] == "completed"
    assert body["pagesFetched"] == 2
    assert body["storedCandles"] == 25
```

- [ ] **Step 4: 运行测试并确认先红**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "retry_market_kline_backfill" -q`
Expected: FAIL，报错提示路由不存在或 store 方法不存在

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_api.py
git commit -m "test: define market kline retry API behavior"
```

### Task 3: 实现后端状态聚合中的失败任务明细

**Files:**
- Modify: `backend/app/store.py`
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: 在 `market_kline_status()` 中加入失败任务列表聚合**

```python
failed_tasks = [
    MarketKlineFailedTask(
        symbol=task.symbol,
        period=task.period,
        lastError=task.lastError,
        updatedAt=task.updatedAt,
        pagesFetched=task.pagesFetched,
        storedCandles=task.storedCandles,
        nextStart=task.nextStart,
    )
    for task in sorted(
        [task for task in tasks if task.status == "failed"],
        key=lambda item: (item.updatedAt, item.symbol, item.period),
        reverse=True,
    )
]
```

- [ ] **Step 2: 把 `failedTasks` 放进返回体**

```python
return MarketKlineStatusResponse(
    updatedAt=updated_at,
    overallStatus=overall_status,
    overallStatusLabel=overall_label,
    activePhase=active_phase,
    cards=cards,
    periodProgress=period_progress,
    coverage=coverage,
    runningTasks=running_tasks,
    failedTasks=failed_tasks,
    recentTasks=recent_tasks,
    risks=risks,
)
```

- [ ] **Step 3: 运行状态聚合相关测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_kline_status and failed_tasks" -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/store.py backend/app/models.py backend/tests/test_api.py
git commit -m "feat: expose failed kline backfill tasks in status response"
```

### Task 4: 实现后端单任务同步重试逻辑

**Files:**
- Modify: `backend/app/store.py`
- Modify: `backend/app/models.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: 在 store 协议和实现中声明重试方法**

```python
class Store(Protocol):
    def retry_market_kline_backfill_task(self, symbol: str, period: str) -> RetryMarketKlineBackfillResponse: ...
```

- [ ] **Step 2: 添加任务定位与互斥辅助逻辑**

```python
def _find_market_kline_backfill_task(
    tasks: list[MarketKlineBackfillTask],
    symbol: str,
    period: str,
) -> MarketKlineBackfillTask | None:
    normalized_symbol = symbol.upper()
    normalized_period = str(period).upper()
    for task in tasks:
        if task.symbol == normalized_symbol and task.period == normalized_period:
            return task
    return None
```

- [ ] **Step 3: 以最小实现补上重试主逻辑**

```python
def retry_market_kline_backfill_task(self, symbol: str, period: str) -> RetryMarketKlineBackfillResponse:
    with _market_kline_cleanup_lock:
        if _market_kline_cleanup_state.get("cleaning"):
            raise ValueError("当前正在清理 K 线，请稍后再试。")

    task = _find_market_kline_backfill_task(self.market_kline_backfill_tasks, symbol, period)
    if task is None:
        raise LookupError("未找到对应的补齐任务。")
    if task.status != "failed":
        raise RuntimeError("仅允许重试失败任务。")

    running = task.model_copy(update={"status": "running", "lastError": "", "updatedAt": _now_iso()})
    self.upsert_market_kline_backfill_task(running)
    try:
        refreshed, _ = _advance_market_kline_backfill_task(self, running, max_pages=1)
    except Exception as exc:
        failed = running.model_copy(update={"status": "failed", "lastError": str(exc), "updatedAt": _now_iso()})
        self.upsert_market_kline_backfill_task(failed)
        raise

    if refreshed.status == "completed":
        label = "补齐完成"
    elif refreshed.status == "running":
        refreshed = refreshed.model_copy(update={"status": "pending", "updatedAt": _now_iso()})
        self.upsert_market_kline_backfill_task(refreshed)
        label = "已执行一轮，等待后续补齐"
    else:
        label = "已重试"

    return RetryMarketKlineBackfillResponse(
        symbol=refreshed.symbol,
        period=refreshed.period,
        status=refreshed.status,
        statusLabel=label,
        storedCandles=refreshed.storedCandles,
        pagesFetched=refreshed.pagesFetched,
        message=label,
        updatedAt=refreshed.updatedAt,
    )
```

- [ ] **Step 4: 根据测试修正异常分支，确保失败后仍保持 `failed`**

```python
except Exception as exc:
    failed = running.model_copy(
        update={
            "status": "failed",
            "lastError": str(exc),
            "updatedAt": _now_iso(),
        }
    )
    self.upsert_market_kline_backfill_task(failed)
    raise RuntimeError(f"重试失败：{exc}") from exc
```

- [ ] **Step 5: 运行重试后端测试并确认转绿**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "retry_market_kline_backfill" -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/store.py backend/app/models.py backend/tests/test_api.py
git commit -m "feat: add synchronous retry for failed kline backfill task"
```

### Task 5: 暴露 FastAPI 路由并转换为明确的 HTTP 错误

**Files:**
- Modify: `backend/app/routers/market.py`
- Modify: `backend/tests/test_api.py`
- Test: `backend/tests/test_api.py`

- [ ] **Step 1: 在路由文件中引入请求/响应模型与 `HTTPException`**

```python
from fastapi import APIRouter, HTTPException

from app.models import (
    Candle,
    MarketKlineStatusResponse,
    MarketRadarResponse,
    Period,
    RetryMarketKlineBackfillRequest,
    RetryMarketKlineBackfillResponse,
)
```

- [ ] **Step 2: 新增重试路由**

```python
@router.post("/kline-backfill/retry", response_model=RetryMarketKlineBackfillResponse)
def retry_market_kline_backfill(payload: RetryMarketKlineBackfillRequest) -> RetryMarketKlineBackfillResponse:
    try:
        return store.retry_market_kline_backfill_task(payload.symbol, payload.period)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
```

- [ ] **Step 3: 运行 API 层测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "retry_market_kline_backfill or market_kline_status_includes_failed_tasks" -q`
Expected: PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/market.py backend/tests/test_api.py
git commit -m "feat: add market kline backfill retry route"
```

### Task 6: 先用前端测试锁定失败任务展示与重试交互

**Files:**
- Modify: `frontend/src/pages/MarketDataStatus.tsx`
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Create or Modify: `frontend/src/market-data-status.test.mjs`

- [ ] **Step 1: 写前端测试，锁定失败任务表展示**

```javascript
test("renders failed backfill tasks and filters by period", async () => {
  const status = {
    updatedAt: "2026-06-11T08:00:00+00:00",
    overallStatus: "warning",
    overallStatusLabel: "有异常",
    activePhase: "历史补齐",
    cards: [],
    periodProgress: [],
    coverage: [],
    runningTasks: [],
    failedTasks: [
      {
        symbol: "BNBUSDT",
        period: "1H",
        lastError: "network timeout",
        updatedAt: "2026-06-11T08:00:00+00:00",
        pagesFetched: 2,
        storedCandles: 10,
        nextStart: "2026-06-11T07:00:00+00:00",
      }
    ],
    recentTasks: [],
    risks: [],
  };

  render(
    <MarketDataStatus
      status={status}
      loading={false}
      autoRefresh={false}
      onRefresh={async () => {}}
      onToggleAutoRefresh={() => {}}
      onRetryFailedTask={async () => {}}
    />
  );

  assert.match(document.body.textContent ?? "", /失败任务/);
  assert.match(document.body.textContent ?? "", /BNBUSDT/);
  assert.match(document.body.textContent ?? "", /network timeout/);
});
```

- [ ] **Step 2: 写前端测试，锁定点击重试会传入 `symbol + period`**

```javascript
test("retries a failed task and refreshes status", async () => {
  const calls = [];
  let refreshCount = 0;

  render(
    <MarketDataStatus
      status={mockStatusWithFailedTask}
      loading={false}
      autoRefresh={false}
      onRefresh={async () => {
        refreshCount += 1;
      }}
      onToggleAutoRefresh={() => {}}
      onRetryFailedTask={async (symbol, period) => {
        calls.push([symbol, period]);
      }}
    />
  );

  document.querySelector("button[data-retry-task='BNBUSDT-1H']").click();
  await Promise.resolve();

  assert.deepEqual(calls, [["BNBUSDT", "1H"]]);
  assert.equal(refreshCount, 1);
});
```

- [ ] **Step 3: 运行测试并确认先红**

Run: `node --test src/market-data-status.test.mjs`
Expected: FAIL，提示组件缺少 `failedTasks` 展示或没有 `onRetryFailedTask` 行为

- [ ] **Step 4: Commit**

```bash
git add frontend/src/market-data-status.test.mjs
git commit -m "test: define failed market data retry UI behavior"
```

### Task 7: 实现前端类型、API 与页面交互

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`
- Modify: `frontend/src/pages/MarketDataStatus.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/styles.css`
- Test: `frontend/src/market-data-status.test.mjs`

- [ ] **Step 1: 补充 TypeScript 类型**

```typescript
export interface MarketKlineFailedTask {
  symbol: string;
  period: Period;
  lastError: string;
  updatedAt: string;
  pagesFetched: number;
  storedCandles: number;
  nextStart: string;
}

export interface RetryMarketKlineBackfillResponse {
  symbol: string;
  period: Period;
  status: "pending" | "running" | "completed" | "failed";
  statusLabel: string;
  storedCandles: number;
  pagesFetched: number;
  message: string;
  updatedAt: string;
}
```

- [ ] **Step 2: 扩展状态响应与 API 方法**

```typescript
export interface MarketKlineStatusResponse {
  updatedAt: string;
  overallStatus: "running" | "waiting" | "completed" | "warning";
  overallStatusLabel: string;
  activePhase: string;
  cards: MarketKlineTaskCard[];
  periodProgress: MarketKlinePeriodProgress[];
  coverage: MarketKlineCoverage[];
  runningTasks: MarketKlineRunningTask[];
  failedTasks: MarketKlineFailedTask[];
  recentTasks: MarketKlineRecentTask[];
  risks: string[];
}

marketKlineBackfillRetry: (symbol: string, period: Period) =>
  request<RetryMarketKlineBackfillResponse>("/api/market/kline-backfill/retry", {
    method: "POST",
    body: JSON.stringify({ symbol, period }),
  }),
```

- [ ] **Step 3: 给页面组件增加重试回调与本地筛选状态**

```typescript
interface MarketDataStatusProps {
  status: MarketKlineStatusResponse | null;
  loading: boolean;
  autoRefresh: boolean;
  onRefresh: () => Promise<void>;
  onToggleAutoRefresh: () => void;
  onRetryFailedTask: (symbol: string, period: Period) => Promise<void>;
}

const [failedPeriodFilter, setFailedPeriodFilter] = useState<"ALL" | Period>("ALL");
const [retryingTaskId, setRetryingTaskId] = useState("");
```

- [ ] **Step 4: 实现失败任务表格与单行重试按钮**

```tsx
<section className="panel table-panel">
  <div className="panel-title">
    <h2>失败任务</h2>
    <span className="muted">仅支持逐条受控重试</span>
  </div>
  <div className="toolbar-inline">
    <label>
      <span>周期筛选</span>
      <select value={failedPeriodFilter} onChange={(event) => setFailedPeriodFilter(event.target.value as "ALL" | Period)}>
        <option value="ALL">全部</option>
        <option value="5M">5M</option>
        <option value="1D">1D</option>
      </select>
    </label>
  </div>
  {filteredFailedTasks.length === 0 ? (
    <div className="compact-empty">当前没有失败补齐任务。</div>
  ) : (
    <table className="table data-table">
      <thead>
        <tr>
          <th>交易对</th>
          <th>周期</th>
          <th>最近错误</th>
          <th>更新时间</th>
          <th>页数</th>
          <th>已写入</th>
          <th>下次起点</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {filteredFailedTasks.map((task) => {
          const taskId = `${task.symbol}-${task.period}`;
          return (
            <tr key={taskId}>
              <td><strong>{task.symbol}</strong></td>
              <td>{task.period}</td>
              <td title={task.lastError}>{task.lastError || "--"}</td>
              <td>{formatTime(task.updatedAt)}</td>
              <td>{task.pagesFetched}</td>
              <td>{formatNumber(task.storedCandles)}</td>
              <td>{formatTime(task.nextStart)}</td>
              <td>
                <button
                  data-retry-task={taskId}
                  className="secondary compact"
                  type="button"
                  disabled={retryingTaskId === taskId}
                  onClick={async () => {
                    setRetryingTaskId(taskId);
                    try {
                      await onRetryFailedTask(task.symbol, task.period);
                      await onRefresh();
                    } finally {
                      setRetryingTaskId("");
                    }
                  }}
                >
                  {retryingTaskId === taskId ? "重试中..." : "立即重试"}
                </button>
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  )}
</section>
```

- [ ] **Step 5: 在页面容器中实现重试回调**

```typescript
async function retryMarketKlineTask(symbol: string, period: Period) {
  const result = await api.marketKlineBackfillRetry(symbol, period);
  setToast({ type: "success", message: `${result.symbol} ${result.period}：${result.message}` });
}
```

- [ ] **Step 6: 补充最小样式**

```css
.toolbar-inline {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 12px;
}

.toolbar-inline label {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}
```

- [ ] **Step 7: 运行前端测试与构建验证**

Run: `node --test src/market-data-status.test.mjs`
Expected: PASS

Run: `npm.cmd run build`
Expected: 通过

- [ ] **Step 8: Commit**

```bash
git add frontend/src/types.ts frontend/src/api.ts frontend/src/pages/MarketDataStatus.tsx frontend/src/App.tsx frontend/src/styles.css frontend/src/market-data-status.test.mjs
git commit -m "feat: add failed task retry controls to market data page"
```

### Task 8: 运行后端回归并更新项目进度

**Files:**
- Modify: `PROJECT_PROGRESS.md`
- Test: `backend/tests/test_api.py`
- Test: `frontend/src/market-data-status.test.mjs`

- [ ] **Step 1: 运行后端针对性测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_kline_status or retry_market_kline_backfill or market_kline_backfill" -q`
Expected: PASS

- [ ] **Step 2: 运行完整后端测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`
Expected: PASS

- [ ] **Step 3: 更新 `PROJECT_PROGRESS.md`**

```md
## 2026-06-11 数据采集失败任务重试
### 当前任务
- 已为“数据采集”页面新增失败任务明细与单任务同步重试能力。

### 实施计划
- [x] 扩展 `kline-status` 返回失败任务明细。
- [x] 新增失败任务同步重试接口。
- [x] 新增前端失败任务表、周期筛选和单行重试。
- [x] 运行后端测试、前端测试和构建验证。

### 修改记录
- 修改 `backend/app/models.py`：新增失败任务明细与重试请求/响应模型。
- 修改 `backend/app/store.py`：新增失败任务聚合与单任务同步重试逻辑。
- 修改 `backend/app/routers/market.py`：新增 `/api/market/kline-backfill/retry`。
- 修改 `backend/tests/test_api.py`：新增失败任务展示与重试测试。
- 修改 `frontend/src/types.ts`、`frontend/src/api.ts`：新增失败任务类型与重试 API。
- 修改 `frontend/src/pages/MarketDataStatus.tsx`、`frontend/src/styles.css`：新增失败任务表与重试交互。

### 验证结果
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -k "market_kline_status or retry_market_kline_backfill or market_kline_backfill" -q`，结果：通过。
- 已执行：`.\.venv\Scripts\python.exe -m pytest tests\test_api.py -q`，结果：通过。
- 已执行：`node --test src/market-data-status.test.mjs`，结果：通过。
- 已执行：`npm.cmd run build`，结果：通过。

### 下一步任务清单
- 重启后端服务后，在真实环境观察失败任务重试的接口耗时与 Binance 错误率。
- 观察用户连续重试时是否需要加入更明显的冷却提示。
- 后续如失败任务较多，可再评估分页或搜索能力。

### 风险点
- 同步重试接口会直接触发外部请求与数据库写入，耗时高于普通状态接口。
- 当前仅支持单任务单轮重试，未提供批量恢复能力。
```

- [ ] **Step 4: 运行进度更新后的最终验证**

Run: `npm.cmd run build`
Expected: 通过

- [ ] **Step 5: Commit**

```bash
git add PROJECT_PROGRESS.md
git commit -m "docs: update progress for market kline failed retry"
```
