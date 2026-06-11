import { Activity, AlertTriangle, BarChart3, Eye, RefreshCw, ShieldAlert, TrendingUp } from "lucide-react";
import type { CreateWatchItemPayload, MarketRadarRecommendation, MarketRadarResponse } from "../types";

interface MarketRadarProps {
  radar: MarketRadarResponse | null;
  loading: boolean;
  onRefresh: () => Promise<void>;
  onCreateWatchItem: (payload: CreateWatchItemPayload) => Promise<void>;
}

const categoryLabels: Record<MarketRadarRecommendation["category"], string> = {
  breakout: "顺势突破",
  pullback: "回调企稳",
  volume_start: "放量启动",
  watch: "强势观察"
};

const riskLabels: Record<MarketRadarRecommendation["riskLevel"], string> = {
  low: "低",
  medium: "中",
  high: "高"
};

export function MarketRadar({ radar, loading, onRefresh, onCreateWatchItem }: MarketRadarProps) {
  const recommendations = radar?.recommendations ?? [];
  const focusItems = recommendations.slice(0, 3);

  async function addToWatch(item: MarketRadarRecommendation) {
    await onCreateWatchItem({
      symbol: item.symbol,
      conditions: [
        {
          id: `radar-${item.symbol}-${Date.now()}`,
          type: "market-radar",
          period: item.period,
          expression: `${categoryLabels[item.category]}：评分 ${item.score}，${item.reason}`,
          status: "pending",
          lastTriggeredAt: null
        }
      ]
    });
  }

  return (
    <section className="page market-radar-page">
      <header className="page-header">
        <div>
          <h1>市场雷达</h1>
          <p>先判断市场是否配合，再筛选值得盯的短线交易对。</p>
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
              <MetricCard icon={ShieldAlert} label="波动风险" value={`${radar.metrics.averageVolatility}%`} />
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
            <div className="panel table-panel radar-table-panel">
              <div className="panel-title radar-table-title">
                <h2>推荐交易对</h2>
                <span className="muted">分析 {radar.metrics.symbolsAnalyzed} 个交易对</span>
              </div>
              <table className="table">
                <thead>
                  <tr>
                    <th>交易对</th>
                    <th>类型</th>
                    <th>评分</th>
                    <th>周期</th>
                    <th>趋势</th>
                    <th>量能</th>
                    <th>风险</th>
                    <th>操作</th>
                  </tr>
                </thead>
                <tbody>
                  {recommendations.map((item) => (
                    <tr key={item.symbol}>
                      <td>
                        <strong>{item.symbol}</strong>
                        <p className="table-note">{item.reason}</p>
                      </td>
                      <td><span className="chip">{categoryLabels[item.category]}</span></td>
                      <td>
                        <div className="radar-score-line">
                          <span style={{ width: `${item.score}%` }} />
                        </div>
                        <strong>{item.score}</strong>
                      </td>
                      <td>{item.period}</td>
                      <td>{item.trend}</td>
                      <td>{item.volume}</td>
                      <td><span className={`risk-badge ${item.riskLevel}`}>{riskLabels[item.riskLevel]}</span></td>
                      <td>
                        <button className="secondary compact" type="button" onClick={() => void addToWatch(item)}>
                          <Eye size={14} aria-hidden="true" />
                          加入观察
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <aside className="panel radar-groups-panel">
              <div className="panel-title">
                <h2>机会分布</h2>
              </div>
              {Object.entries(radar.opportunityGroups).map(([key, value]) => (
                <div className="radar-group-row" key={key}>
                  <span>{categoryLabels[key as MarketRadarRecommendation["category"]]}</span>
                  <strong>{value}</strong>
                </div>
              ))}
            </aside>
          </section>

          <section className="radar-focus-grid">
            {focusItems.map((item) => (
              <article className="panel radar-focus-card" key={item.symbol}>
                <div>
                  <strong>{item.symbol}</strong>
                  <span className="chip">{categoryLabels[item.category]}</span>
                </div>
                <MiniBars score={item.score} />
                <p>{item.reason}</p>
                <small><AlertTriangle size={13} aria-hidden="true" /> {item.riskNote}</small>
                <button className="secondary compact" type="button" onClick={() => void addToWatch(item)}>
                  加入观察
                </button>
              </article>
            ))}
          </section>
        </>
      )}
    </section>
  );
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

function MiniBars({ score }: { score: number }) {
  return (
    <div className="radar-mini-bars" aria-hidden="true">
      {Array.from({ length: 18 }).map((_, index) => (
        <span key={index} style={{ height: `${18 + ((index * 7 + score) % 28)}px` }} />
      ))}
    </div>
  );
}

function formatTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}
