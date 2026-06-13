import { Activity, BarChart3, Eye, LineChart, RefreshCw, ShieldAlert, TrendingUp } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { api } from "../api";
import { MarketKlineChart } from "../components/MarketKlineChart";
import { Modal } from "../components/Modal";
import type {
  Candle,
  CreateWatchItemPayload,
  MarketRadarResponse,
  MarketRadarSection,
  MarketRadarSectionItem,
  Period
} from "../types";

interface MarketRadarProps {
  radar: MarketRadarResponse | null;
  loading: boolean;
  onRefresh: () => Promise<void>;
  onCreateWatchItem: (payload: CreateWatchItemPayload) => Promise<void>;
}

const chartPeriods: Period[] = ["5M", "15M", "1H", "4H", "1D"];
type KlineCacheEntry = { candles: Candle[]; complete: boolean };

export function MarketRadar({ radar, loading, onRefresh, onCreateWatchItem }: MarketRadarProps) {
  const [selectedKlineItem, setSelectedKlineItem] = useState<MarketRadarSectionItem | null>(null);
  const [klinePeriod, setKlinePeriod] = useState<Period>("1H");
  const [klineCandles, setKlineCandles] = useState<Candle[]>([]);
  const [klineLoading, setKlineLoading] = useState(false);
  const [klineHydrating, setKlineHydrating] = useState(false);
  const [klineError, setKlineError] = useState("");
  const [activeSectionKey, setActiveSectionKey] = useState<MarketRadarSection["key"] | "">("");
  const klineCacheRef = useRef(new Map<string, KlineCacheEntry>());
  const activeChartKeyRef = useRef<string>("");
  const activeKlineRequestRef = useRef(0);

  useEffect(() => {
    if (!radar?.sections.length) {
      setActiveSectionKey("");
      return;
    }

    const hasCurrent = radar.sections.some((section) => section.key === activeSectionKey);
    if (hasCurrent) return;

    const preferred = radar.sections.find((section) => section.items.length > 0) ?? radar.sections[0];
    setActiveSectionKey(preferred.key);
  }, [activeSectionKey, radar]);

  const activeSection = useMemo(() => {
    if (!radar?.sections.length) return null;
    return (
      radar.sections.find((section) => section.key === activeSectionKey) ??
      radar.sections.find((section) => section.items.length > 0) ??
      radar.sections[0]
    );
  }, [activeSectionKey, radar]);

  useEffect(() => {
    if (!selectedKlineItem) return;

    let cancelled = false;
    const requestId = activeKlineRequestRef.current + 1;
    activeKlineRequestRef.current = requestId;
    const cacheKey = `${selectedKlineItem.symbol}:${klinePeriod}`;
    const cacheEntry = klineCacheRef.current.get(cacheKey);
    const cachedCandles = cacheEntry?.candles;
    const hasCompleteCache = Boolean(cacheEntry?.complete);
    const currentChartKey = activeChartKeyRef.current;
    const isSwitchingPeriod = currentChartKey !== cacheKey;

    setKlineLoading((!cachedCandles?.length && !klineCandles.length) || isSwitchingPeriod);
    setKlineHydrating(Boolean(cachedCandles?.length) && !hasCompleteCache);
    setKlineError("");

    if (cachedCandles?.length) {
      setKlineCandles(cachedCandles);
      activeChartKeyRef.current = cacheKey;
      if (hasCompleteCache) {
        setKlineLoading(false);
        return () => {
          cancelled = true;
        };
      }
    }

    const isStaleRequest = () => cancelled || activeKlineRequestRef.current !== requestId;
    const previewLimit = previewLimitForPeriod(klinePeriod);

    const previewPromise = cachedCandles?.length
      ? Promise.resolve(cachedCandles)
      : api.marketKlines(selectedKlineItem.symbol, klinePeriod, previewLimit);

    previewPromise
      .then((candles) => {
        if (isStaleRequest()) return null;
        if (candles.length) {
          klineCacheRef.current.set(cacheKey, { candles, complete: false });
          setKlineCandles(candles);
          activeChartKeyRef.current = cacheKey;
        }
        setKlineLoading(false);
        setKlineHydrating(true);
        return api.marketKlines(selectedKlineItem.symbol, klinePeriod);
      })
      .then((candles) => {
        if (isStaleRequest() || !candles) return;
        klineCacheRef.current.set(cacheKey, { candles, complete: true });
        setKlineCandles(candles);
        activeChartKeyRef.current = cacheKey;
      })
      .catch((error) => {
        if (isStaleRequest()) return;
        setKlineError(error instanceof Error ? error.message : "K 线加载失败");
      })
      .finally(() => {
        if (!isStaleRequest()) {
          setKlineLoading(false);
          setKlineHydrating(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [klineCandles.length, klinePeriod, selectedKlineItem]);

  async function addToWatch(item: MarketRadarSectionItem) {
    await onCreateWatchItem({
      symbol: item.symbol,
      conditions: [
        {
          id: `radar-${item.category}-${item.symbol}-${Date.now()}`,
          type: "market-radar",
          period: normalizePeriod(item.periodLabel),
          expression: `${sectionLabel(item.category)} ${item.movePrimary} / ${item.moveSecondary} | ${item.reason}`,
          status: "pending",
          lastTriggeredAt: null
        }
      ]
    });
  }

  function openKlinePreview(item: MarketRadarSectionItem) {
    const initialPeriod = normalizePeriod(item.periodLabel);
    const previewCacheKey = `${item.symbol}:${initialPeriod}`;
    if (item.previewCandles.length) {
      klineCacheRef.current.set(previewCacheKey, { candles: item.previewCandles, complete: false });
      setKlineCandles(item.previewCandles);
      activeChartKeyRef.current = previewCacheKey;
    }
    setSelectedKlineItem(item);
    setKlinePeriod(initialPeriod);
    setKlineError("");
  }

  function closeKlinePreview() {
    setSelectedKlineItem(null);
    setKlineCandles([]);
    setKlineHydrating(false);
    setKlineError("");
    activeChartKeyRef.current = "";
    activeKlineRequestRef.current += 1;
  }

  return (
    <section className="page market-radar-page">
      <header className="page-header">
        <div>
          <h1>市场雷达</h1>
          <p>先判断市场环境，再只看当前有结构、有成交额、也有执行价值的交易对。</p>
        </div>
        <div className="toolbar-actions">
          <span className="header-meta">更新于 {radar ? formatTime(radar.updatedAt) : "--"}</span>
          <button className="secondary compact" type="button" onClick={() => void onRefresh()} disabled={loading}>
            <RefreshCw size={15} aria-hidden="true" />
            刷新
          </button>
        </div>
      </header>

      {!radar ? (
        <div className="panel empty-state">{loading ? "正在加载市场雷达..." : "暂无市场雷达数据"}</div>
      ) : (
        <>
          <section className="market-radar-environment">
            <div className={`panel radar-score-card ${radar.environment.status}`}>
              <span>市场环境评分</span>
              <strong>{radar.environment.score}</strong>
              <b>{radar.environment.label}</b>
              <p>{radar.environment.summary}</p>
            </div>

            <div className="radar-metrics-grid">
              <MetricCard icon={TrendingUp} label="上涨占比" value={`${radar.metrics.risingRatio}%`} />
              <MetricCard icon={BarChart3} label="主流币状态" value={radar.metrics.majorTrend} />
              <MetricCard icon={Activity} label="放量占比" value={`${radar.metrics.volumeExpansionRatio}%`} />
              <MetricCard icon={ShieldAlert} label="平均波动" value={`${radar.metrics.averageVolatility}%`} />
            </div>

            <div className="panel radar-notes-panel">
              <div className="panel-title">
                <h2>市场结论</h2>
              </div>
              <ul>
                {radar.environment.notes.map((note) => (
                  <li key={note}>{note}</li>
                ))}
              </ul>
            </div>
          </section>

          <section className="market-radar-content">
            <div className="panel radar-tabs-card">
              <div className="panel-title radar-tabs-header">
                <div className="radar-tabs" role="tablist" aria-label="市场雷达机会分组">
                  {radar.sections.map((section) => (
                    <button
                      key={section.key}
                      type="button"
                      role="tab"
                      className={`radar-tab ${activeSection?.key === section.key ? "active" : ""}`}
                      aria-selected={activeSection?.key === section.key}
                      onClick={() => setActiveSectionKey(section.key)}
                    >
                      {section.title} ({radar.opportunityGroups[section.key] ?? section.items.length})
                    </button>
                  ))}
                </div>
                <span className="muted radar-active-summary">分析 {radar.metrics.symbolsAnalyzed} 个交易对</span>
              </div>

              {activeSection ? (
                <>
                  <div className="radar-section-description">
                    <strong>{activeSection.title}</strong>
                    <p>{activeSection.description}</p>
                  </div>

                  {activeSection.items.length === 0 ? (
                    <div className="compact-empty">当前没有满足该分组条件的交易对。</div>
                  ) : (
                    <table className="table radar-section-table">
                      <thead>
                        <tr>
                          <th>交易对</th>
                          <th>评分</th>
                          <th>核心信号</th>
                          <th>24H 成交额</th>
                          <th>量比</th>
                          <th>距离高点回撤</th>
                          <th>周期</th>
                          <th>操作</th>
                        </tr>
                      </thead>
                      <tbody>
                        {activeSection.items.map((item) => (
                          <tr key={`${activeSection.key}-${item.symbol}`}>
                            <td>
                              <strong>{item.symbol}</strong>
                              <p className="table-note">{item.reason}</p>
                              <p className="table-note subtle">{item.riskNote}</p>
                            </td>
                            <td>
                              <div className="radar-score-line">
                                <span style={{ width: `${item.score}%` }} />
                              </div>
                              <strong>{item.score}</strong>
                            </td>
                            <td>
                              <div className="radar-move-cell">
                                <strong>{item.movePrimary}</strong>
                                <span>{item.moveSecondary}</span>
                              </div>
                            </td>
                            <td>{formatQuoteVolume(item.quoteVolume24h)}</td>
                            <td>{item.volumeRatio.toFixed(2)}</td>
                            <td>{formatPercent(item.pullbackFromHighPct)}</td>
                            <td>{item.periodLabel}</td>
                            <td className="radar-actions-cell">
                              <button className="secondary compact" type="button" onClick={() => openKlinePreview(item)}>
                                <LineChart size={14} aria-hidden="true" />
                                查看 K 线
                              </button>
                              <button className="secondary compact" type="button" onClick={() => void addToWatch(item)}>
                                <Eye size={14} aria-hidden="true" />
                                加入观察
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </>
              ) : (
                <div className="compact-empty">当前暂无可展示的市场雷达分组。</div>
              )}
            </div>
          </section>
        </>
      )}

      {selectedKlineItem ? (
        <Modal title={`${selectedKlineItem.symbol} K 线预览`} onClose={closeKlinePreview} className="radar-kline-modal">
          <div className="modal-body">
            <div className="radar-kline-summary">
              <span>{sectionLabel(selectedKlineItem.category)}</span>
              <span>{selectedKlineItem.reason}</span>
            </div>

            <MarketKlineChart
              candles={klineCandles}
              loading={klineLoading}
              chartHeaderExtra={
                <div className="period-switcher" role="tablist" aria-label="市场雷达 K 线周期">
                  {chartPeriods.map((period) => (
                    <button
                      className={klinePeriod === period ? "active" : ""}
                      key={period}
                      onClick={() => setKlinePeriod(period)}
                      type="button"
                    >
                      {period}
                    </button>
                  ))}
                </div>
              }
            />
            {klineError ? <div className="inline-error">{klineError}</div> : null}
            {klineHydrating ? <div className="inline-hint">已先显示最近一段 K 线，正在后台补全完整历史…</div> : null}

            <div className="radar-kline-footer">
              <span>推荐周期：{selectedKlineItem.periodLabel}</span>
              <span>核心信号：{selectedKlineItem.movePrimary} / {selectedKlineItem.moveSecondary}</span>
              <span>24H 成交额：{formatQuoteVolume(selectedKlineItem.quoteVolume24h)}</span>
              <span>量比：{selectedKlineItem.volumeRatio.toFixed(2)}</span>
              <span>风险提示：{selectedKlineItem.riskNote}</span>
            </div>
          </div>
        </Modal>
      ) : null}
    </section>
  );
}

function previewLimitForPeriod(period: Period) {
  if (period === "5M" || period === "15M") return 480;
  if (period === "1H") return 320;
  if (period === "4H") return 220;
  return 180;
}

function MetricCard({ icon: Icon, label, value }: { icon: typeof TrendingUp; label: string; value: string }) {
  return (
    <div className="panel radar-metric-card">
      <Icon size={18} aria-hidden="true" />
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function normalizePeriod(value: string): Period {
  if (value === "5M" || value === "15M" || value === "1H" || value === "4H" || value === "1D") {
    return value;
  }
  return "1H";
}

function sectionLabel(key: MarketRadarSection["key"]) {
  if (key === "short_start") return "短线启动";
  if (key === "short_follow") return "短线延续";
  return "72H 强趋势";
}

function formatQuoteVolume(value: number) {
  if (value >= 100_000_000) return `${(value / 100_000_000).toFixed(2)} 亿 USDT`;
  if (value >= 10_000) return `${(value / 10_000).toFixed(2)} 万 USDT`;
  return `${value.toFixed(2)} USDT`;
}

function formatPercent(value: number) {
  return `${value.toFixed(2)}%`;
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}
