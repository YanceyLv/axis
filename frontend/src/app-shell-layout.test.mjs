import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";

const shellSource = readFileSync(new URL("./components/AppShell.tsx", import.meta.url), "utf8");
const styleSource = readFileSync(new URL("./styles.css", import.meta.url), "utf8");

test("app shell keeps sidebar outside the content scroll container", () => {
  assert.equal(shellSource.includes('<aside className="sidebar"'), true);
  assert.equal(shellSource.includes('<main className="main">'), true);
  assert.equal(styleSource.includes(".shell {"), true);
  assert.equal(styleSource.includes("height: 100vh;"), true);
  assert.equal(styleSource.includes(".main {"), true);
  assert.equal(styleSource.includes("overflow-y: auto;"), true);
  assert.equal(styleSource.includes(".sidebar {"), true);
  assert.equal(styleSource.includes("height: 100vh;"), true);
});

test("app shell uses the approved navigation order", () => {
  const dashboardIndex = shellSource.indexOf('{ key: "dashboard", label: "首页", icon: Home }');
  const radarIndex = shellSource.indexOf('{ key: "market-radar", label: "市场雷达", icon: Radar }');
  const dataIndex = shellSource.indexOf('{ key: "market-data", label: "数据采集", icon: Database }');
  const strategiesIndex = shellSource.indexOf('{ key: "strategies", label: "策略中心", icon: Sparkles }');
  const signalsIndex = shellSource.indexOf('{ key: "signals", label: "信号中心", icon: BellRing }');
  const newCoinsIndex = shellSource.indexOf('{ key: "new-coins", label: "新币监测", icon: Rocket }');
  const watchlistIndex = shellSource.indexOf('{ key: "watchlist", label: "观察池", icon: Eye }');
  const knowledgeIndex = shellSource.indexOf('{ key: "knowledge", label: "知识库", icon: BookOpen }');

  assert.equal(dashboardIndex < radarIndex, true);
  assert.equal(radarIndex < dataIndex, true);
  assert.equal(dataIndex < strategiesIndex, true);
  assert.equal(strategiesIndex < signalsIndex, true);
  assert.equal(signalsIndex < newCoinsIndex, true);
  assert.equal(newCoinsIndex < watchlistIndex, true);
  assert.equal(watchlistIndex < knowledgeIndex, true);
});
