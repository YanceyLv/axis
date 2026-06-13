import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";

const pageSource = readFileSync(new URL("./pages/MarketDataStatus.tsx", import.meta.url), "utf8");
const appSource = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const styleSource = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

test("market data status page keeps row retry loading recoverable", () => {
  assert.equal(pageSource.includes("failedTasks"), true);
  assert.equal(pageSource.includes("const failedTasks = status?.failedTasks ?? [];"), true);
  assert.equal(pageSource.includes('if (failedTaskMinPeriod === "ALL") return failedTasks;'), true);
  assert.equal(pageSource.includes("return failedTasks.filter((task) => periodOrder[task.period] >= minOrder);"), true);
  assert.equal(pageSource.includes("failedTaskMinPeriod"), true);
  assert.equal(pageSource.includes("retryingTaskKeys"), true);
  assert.equal(pageSource.includes("setRetryingTaskKeys((current) => current.filter((item) => item !== taskKey))"), true);
  assert.equal(pageSource.includes("void handleRetry(task).catch(() => undefined)"), true);
  assert.equal(pageSource.includes("disabled={retrying}"), true);
});

test("market data status retry distinguishes refresh failure after success", () => {
  assert.equal(appSource.includes("marketKlineBackfillRetry"), true);
  assert.equal(appSource.includes("handleRetryFailedMarketTask"), true);
  assert.equal(appSource.includes("normalizeMarketKlineStatus"), true);
  assert.equal(appSource.includes("failedTasks: Array.isArray(status.failedTasks) ? status.failedTasks : [],"), true);
  assert.equal(appSource.includes("setMarketKlineStatusLoading(true);"), true);
  assert.equal(appSource.includes("setMarketKlineStatus(normalizeMarketKlineStatus(await api.marketKlineStatus()));"), true);
  assert.equal(appSource.includes("await api.marketKlineBackfillRetry(symbol, period);"), true);
  assert.equal(appSource.includes("catch (err)"), true);
  assert.equal(appSource.includes("onRetryFailedTask={handleRetryFailedMarketTask}"), true);
});

test("market data status panel headers keep consistent inner spacing", () => {
  assert.equal(styleSource.includes(".market-data-page .table-panel > .panel-title"), true);
  assert.equal(styleSource.includes("padding: 16px 18px 14px;"), true);
  assert.equal(styleSource.includes(".market-data-page .table-panel > .compact-empty"), true);
  assert.equal(styleSource.includes("padding: 22px 18px 26px;"), true);
  assert.equal(styleSource.includes(".market-data-page .risk-panel"), true);
});

test("market data status hides backfill progress when completed and idle", () => {
  assert.equal(pageSource.includes("const showBackfillProgress ="), true);
  assert.equal(pageSource.includes("status.periodProgress.some("), true);
  assert.equal(pageSource.includes("item.failed > 0 || item.running > 0 || item.pending > 0 || item.completed < item.total"), true);
  assert.equal(pageSource.includes("status.runningTasks.length > 0"), true);
  assert.equal(pageSource.includes("{showBackfillProgress ? ("), true);
  assert.equal(pageSource.includes('data-status-grid${showBackfillProgress ? "" : " single-panel"}'), true);
});

test("market data status hides idle running and failed sections when empty", () => {
  assert.equal(pageSource.includes("const showRunningTasks = status?.runningTasks.length"), true);
  assert.equal(pageSource.includes("const showFailedTasks = filteredFailedTasks.length > 0;"), true);
  assert.equal(pageSource.includes("{showRunningTasks ? ("), true);
  assert.equal(pageSource.includes('{showFailedTasks ? ('), true);
});
