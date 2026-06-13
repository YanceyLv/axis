import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";

const pageSource = readFileSync(new URL("./pages/SignalDetail.tsx", import.meta.url), "utf8");
const styleSource = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

test("signal detail kline chart keeps a bounded page height", () => {
  assert.equal(pageSource.includes("signal-chart-panel"), true);
  assert.equal(styleSource.includes(".signal-chart-panel .market-chart-shell"), true);
  assert.equal(styleSource.includes("height: min(520px, calc(100vh - 260px));"), true);
  assert.equal(styleSource.includes("min-height: 360px;"), true);
});

test("signal detail ai review uses structured readable sections", () => {
  assert.equal(pageSource.includes('className="panel ai-review-panel"'), true);
  assert.equal(pageSource.includes('className="ai-review-metrics"'), true);
  assert.equal(pageSource.includes('className="ai-review-summary"'), true);
  assert.equal(pageSource.includes('className="ai-review-analysis"'), true);
  assert.equal(pageSource.includes('className="ai-review-suggestions"'), true);
  assert.equal(pageSource.includes("formatReviewAnalysis(signal.performance.reviewAnalysis)"), true);
  assert.equal(pageSource.includes('<p className="muted">{signal.performance.reviewAnalysis}</p>'), false);
  assert.equal(styleSource.includes(".ai-review-panel"), true);
  assert.equal(styleSource.includes(".ai-review-metrics"), true);
  assert.equal(styleSource.includes(".ai-review-suggestions"), true);
});
