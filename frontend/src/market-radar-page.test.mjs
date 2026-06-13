import { readFileSync } from "node:fs";
import assert from "node:assert/strict";
import { test } from "node:test";

const pageSource = readFileSync(new URL("./pages/MarketRadar.tsx", import.meta.url), "utf8");
const chartSource = readFileSync(new URL("./components/MarketKlineChart.tsx", import.meta.url), "utf8");
const styleSource = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
const typesSource = readFileSync(new URL("./types.ts", import.meta.url), "utf8");
const appSource = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");

test("market radar types use sections contract instead of recommendations", () => {
  assert.equal(typesSource.includes('export type MarketRadarSectionKey = "short_start" | "short_follow" | "trend_72h";'), true);
  assert.equal(typesSource.includes("export interface MarketRadarSectionItem {"), true);
  assert.equal(typesSource.includes("previewCandles: Candle[];"), true);
  assert.equal(typesSource.includes("export interface MarketRadarSection {"), true);
  assert.equal(typesSource.includes("sections: MarketRadarSection[];"), true);
  assert.equal(typesSource.includes("recommendations: MarketRadarRecommendation[];"), false);
});

test("market radar page renders a single tabbed list and key trading fields", () => {
  assert.equal(pageSource.includes('const [activeSectionKey, setActiveSectionKey] = useState<MarketRadarSection["key"] | "">("");'), true);
  assert.equal(pageSource.includes("const activeSection = useMemo(() => {"), true);
  assert.equal(pageSource.includes('className="panel radar-tabs-card"'), true);
  assert.equal(pageSource.includes('className="radar-tabs"'), true);
  assert.equal(pageSource.includes('{section.title} ({radar.opportunityGroups[section.key] ?? section.items.length})'), true);
  assert.equal(pageSource.includes("radar-groups-panel"), false);
  assert.equal(pageSource.includes("item.quoteVolume24h"), true);
  assert.equal(pageSource.includes("item.pullbackFromHighPct"), true);
  assert.equal(pageSource.includes("item.movePrimary"), true);
  assert.equal(pageSource.includes("item.moveSecondary"), true);
  assert.equal(pageSource.includes("formatQuoteVolume(item.quoteVolume24h)"), true);
});

test("market radar page keeps kline preview and watch actions", () => {
  assert.equal(pageSource.includes("const previewLimit = previewLimitForPeriod(klinePeriod);"), true);
  assert.equal(pageSource.includes("api.marketKlines(selectedKlineItem.symbol, klinePeriod, previewLimit)"), true);
  assert.equal(pageSource.includes("api.marketKlines(selectedKlineItem.symbol, klinePeriod)"), true);
  assert.equal(pageSource.includes("klineCacheRef.current.get(cacheKey)"), true);
  assert.equal(pageSource.includes("type KlineCacheEntry = { candles: Candle[]; complete: boolean };"), true);
  assert.equal(pageSource.includes("activeKlineRequestRef"), true);
  assert.equal(pageSource.includes("openKlinePreview(item)"), true);
  assert.equal(pageSource.includes("void addToWatch(item)"), true);
  assert.equal(pageSource.includes("title={`${selectedKlineItem.symbol} K 线预览`}"), true);
  assert.equal(pageSource.includes('className="period-switcher" role="tablist"'), true);
  assert.equal(chartSource.includes("chartHeaderExtra?: ReactNode;"), true);
});

test("market radar page does not blank the chart before preview data returns", () => {
  const openPreviewBlock = pageSource.slice(
    pageSource.indexOf("function openKlinePreview"),
    pageSource.indexOf("function closeKlinePreview")
  );
  assert.equal(openPreviewBlock.includes("setKlineCandles([]);"), false);
  assert.equal(openPreviewBlock.includes("item.previewCandles.length"), true);
  assert.equal(openPreviewBlock.includes("setKlineCandles(item.previewCandles);"), true);
  assert.equal(pageSource.includes("setKlineLoading((!cachedCandles?.length && !klineCandles.length) || isSwitchingPeriod);"), true);
});

test("market radar page shows explicit loading when switching chart period", () => {
  assert.equal(pageSource.includes("const isSwitchingPeriod = currentChartKey !== cacheKey;"), true);
  assert.equal(pageSource.includes("const isStaleRequest = () => cancelled || activeKlineRequestRef.current !== requestId;"), true);
  assert.equal(pageSource.includes("klineCacheRef.current.set(cacheKey, { candles, complete: true });"), true);
});

test("market radar styles include tabbed list layout refinements", () => {
  assert.equal(styleSource.includes(".market-radar-content {\n  display: block;"), true);
  assert.equal(styleSource.includes(".radar-tabs-card"), true);
  assert.equal(styleSource.includes(".radar-tabs"), true);
  assert.equal(styleSource.includes(".radar-tab"), true);
  assert.equal(styleSource.includes(".radar-tab.active"), true);
  assert.equal(styleSource.includes(".radar-active-summary"), true);
  assert.equal(styleSource.includes(".radar-section-description"), true);
  assert.equal(styleSource.includes(".radar-groups-panel"), false);
  assert.equal(styleSource.includes(".radar-move-cell"), true);
  assert.equal(styleSource.includes(".modal.radar-kline-modal"), true);
  assert.equal(styleSource.includes("width: min(1680px, calc(100vw - 16px));"), true);
  assert.equal(styleSource.includes("max-width: calc(100vw - 16px);"), true);
  assert.equal(styleSource.includes("height: calc(100vh - 16px);"), true);
  assert.equal(styleSource.includes(".radar-kline-modal .modal-header"), true);
  assert.equal(styleSource.includes("gap: 10px;"), true);
  assert.equal(styleSource.includes("padding: 8px 14px 16px;"), true);
  assert.equal(styleSource.includes(".radar-kline-modal .market-chart-header"), true);
  assert.equal(styleSource.includes("min-height: 54px;"), true);
});

test("market radar page auto refreshes cached snapshot every three minutes on radar view", () => {
  assert.equal(appSource.includes("if (!auth || view !== \"market-radar\") return;"), true);
  assert.equal(appSource.includes("}, 180000);"), true);
  assert.equal(appSource.includes("void handleRefreshMarketRadar();"), true);
});
