import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";

const apiSource = readFileSync(new URL("./api.ts", import.meta.url), "utf8");
const appSource = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const watchlistSource = readFileSync(new URL("./pages/Watchlist.tsx", import.meta.url), "utf8");
const styleSource = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

test("watchlist api exposes delete watch item endpoint", () => {
  assert.equal(apiSource.includes("deleteWatchItem"), true);
  assert.equal(apiSource.includes('method: "DELETE"'), true);
  assert.equal(apiSource.includes("/api/watchlist/${encodeURIComponent(id)}"), true);
});

test("app wires watch item deletion with confirmation and refresh", () => {
  assert.equal(appSource.includes("deletingWatchId"), true);
  assert.equal(appSource.includes("handleDeleteWatchItem"), true);
  assert.equal(appSource.includes("window.confirm"), true);
  assert.equal(appSource.includes("api.deleteWatchItem(item.id)"), true);
  assert.equal(appSource.includes("await refreshDashboardAndWatchlist()"), true);
  assert.equal(appSource.includes("onDeleteWatch={handleDeleteWatchItem}"), true);
});

test("watchlist table renders a row delete action", () => {
  assert.equal(watchlistSource.includes("onDeleteWatch"), true);
  assert.equal(watchlistSource.includes("deletingWatchId"), true);
  assert.equal(watchlistSource.includes('className="table-actions"'), true);
  assert.equal(watchlistSource.includes('className="icon-button danger compact"'), true);
  assert.equal(watchlistSource.includes("<Trash2"), true);
});

test("watchlist table styles prefer content-driven widths", () => {
  assert.equal(styleSource.includes(".watchlist-table-panel .table {\n  table-layout: auto;"), true);
  assert.equal(styleSource.includes(".watchlist-table-panel .table th:nth-child(2),"), true);
  assert.equal(styleSource.includes("width: 1%;"), true);
  assert.equal(styleSource.includes(".watchlist-table-panel .table td:last-child {\n  white-space: nowrap;"), true);
});
