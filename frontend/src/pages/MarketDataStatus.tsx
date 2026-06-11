import { AlertTriangle, Clock3, RefreshCw, ShieldCheck, ToggleLeft, ToggleRight } from "lucide-react";
import type { MarketKlineStatusResponse, MarketKlineTaskCard, Period } from "../types";

interface MarketDataStatusProps {
  status: MarketKlineStatusResponse | null;
  loading: boolean;
  autoRefresh: boolean;
  onRefresh: () => Promise<void>;
  onToggleAutoRefresh: () => void;
}

const statusClass: Record<MarketKlineTaskCard["status"], string> = {
  running: "running",
  waiting: "waiting",
  completed: "completed",
  warning: "warning"
};

const nativePeriods = new Set<Period>(["5M", "1D"]);

export function MarketDataStatus({
  status,
  loading,
  autoRefresh,
  onRefresh,
  onToggleAutoRefresh
}: MarketDataStatusProps) {
  return (
    <section className="page market-data-page">
      <header className="page-header compact-header">
        <div>
          <h1>数据采集</h1>
          <p>K线历史补齐、增量更新、数据清理的后台任务状态。</p>
        </div>
        <div className="toolbar-actions">
          <span className="header-meta">最后刷新：{status ? formatTime(status.updatedAt) : "--"}</span>
          <button className="secondary compact" type="button" onClick={() => void onRefresh()} disabled={loading}>
            <RefreshCw size={15} aria-hidden="true" />
            刷新
          </button>
          <button className={`secondary compact auto-refresh${autoRefresh ? " active" : ""}`} type="button" onClick={onToggleAutoRefresh}>
            {autoRefresh ? <ToggleRight size={16} aria-hidden="true" /> : <ToggleLeft size={16} aria-hidden="true" />}
            自动刷新
          </button>
        </div>
      </header>

      {!status ? (
        <div className="panel empty-state">{loading ? "正在加载数据采集状态..." : "暂无数据采集状态"}</div>
      ) : (
        <>
          <section className="data-status-summary">
            <div className={`panel data-overall-card ${status.overallStatus}`}>
              <div>
                <span>当前阶段</span>
                <strong>{status.activePhase}</strong>
              </div>
              <b>{status.overallStatusLabel}</b>
            </div>
            {status.cards.map((card) => (
              <TaskCard card={card} key={card.name} />
            ))}
          </section>

          <section className="panel table-panel data-coverage-panel">
            <div className="panel-title">
              <h2>K线数据覆盖</h2>
              <span className="muted">按周期统计数据库已存在数据</span>
            </div>
            <div className="data-note-strip">
              5M/1D 为原生采集；15M/1H/4H 由 5M 完整 K 线自动聚合缓存，不再单独请求 Binance。
            </div>
            <table className="table data-table">
              <thead>
                <tr>
                  <th>周期</th>
                  <th>来源</th>
                  <th>K线数量</th>
                  <th>交易对</th>
                  <th>目标窗口</th>
                  <th>最早时间</th>
                  <th>最新时间</th>
                  <th>状态</th>
                </tr>
              </thead>
              <tbody>
                {status.coverage.map((item) => (
                  <tr key={item.period}>
                    <td><strong>{item.period}</strong></td>
                    <td><span className={`source-pill ${periodSourceClass(item.period)}`}>{periodSourceLabel(item.period)}</span></td>
                    <td>{formatNumber(item.rows)}</td>
                    <td>{item.symbols}</td>
                    <td>{item.targetWindow}</td>
                    <td>{formatTime(item.earliestOpenTime)}</td>
                    <td>{formatTime(item.latestOpenTime)}</td>
                    <td><span className={`status-pill ${item.status}`}>{item.statusLabel}</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          <section className="data-status-grid">
            <div className="panel table-panel">
              <div className="panel-title">
                <h2>历史补齐进度</h2>
                <span className="muted">仅 5M/1D 有原生补齐任务，派生周期随 5M 写入刷新</span>
              </div>
              <table className="table data-table">
                <thead>
                  <tr>
                    <th>周期</th>
                    <th>类型</th>
                    <th>总数</th>
                    <th>已完成</th>
                    <th>运行中</th>
                    <th>待处理</th>
                    <th>失败</th>
                    <th>完成率</th>
                  </tr>
                </thead>
                <tbody>
                  {status.periodProgress.map((item) => {
                    const isNative = isNativePeriod(item.period);
                    return (
                      <tr key={item.period}>
                        <td><strong>{item.period}</strong></td>
                        <td><span className={`source-pill ${periodSourceClass(item.period)}`}>{periodSourceLabel(item.period)}</span></td>
                        <td>{isNative ? item.total : "--"}</td>
                        <td>{isNative ? item.completed : "--"}</td>
                        <td>{isNative ? item.running : "--"}</td>
                        <td>{isNative ? item.pending : "--"}</td>
                        <td>{isNative ? item.failed : "--"}</td>
                        <td>
                          {isNative ? (
                            <div className="progress-cell">
                              <span><i style={{ width: `${Math.min(100, item.progressPercent)}%` }} /></span>
                              <b>{item.progressPercent}%</b>
                            </div>
                          ) : (
                            <span className="derived-progress-note">随 5M 生成</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div className="panel table-panel">
              <div className="panel-title">
                <h2>当前运行任务</h2>
                <span className="muted">仅显示 5M/1D 原生补齐任务，最多 8 个</span>
              </div>
              {status.runningTasks.length === 0 ? (
                <div className="compact-empty">当前没有正在执行的补齐子任务。</div>
              ) : (
                <table className="table data-table">
                  <thead>
                    <tr>
                      <th>交易对</th>
                      <th>周期</th>
                      <th>页数</th>
                      <th>已写入</th>
                      <th>当前补到</th>
                    </tr>
                  </thead>
                  <tbody>
                    {status.runningTasks.map((task) => (
                      <tr key={`${task.symbol}-${task.period}`}>
                        <td><strong>{task.symbol}</strong></td>
                        <td>{task.period}</td>
                        <td>{task.pagesFetched}</td>
                        <td>{formatNumber(task.storedCandles)}</td>
                        <td>{formatTime(task.nextStart)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          </section>

          <section className="data-status-grid bottom-grid">
            <div className="panel table-panel">
              <div className="panel-title">
                <h2>最近任务记录</h2>
                <span className="muted">补齐、增量、清理</span>
              </div>
              <table className="table data-table">
                <thead>
                  <tr>
                    <th>类型</th>
                    <th>状态</th>
                    <th>目标</th>
                    <th>数量</th>
                    <th>时间</th>
                    <th>说明</th>
                  </tr>
                </thead>
                <tbody>
                  {status.recentTasks.map((item, index) => (
                    <tr key={`${item.type}-${item.target}-${index}`}>
                      <td>{typeLabel(item.type)}</td>
                      <td><span className="status-pill normal">{item.status}</span></td>
                      <td>{item.target}</td>
                      <td>{item.amount}</td>
                      <td>{formatTime(item.updatedAt)}</td>
                      <td>{item.note}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <aside className="panel risk-panel">
              <div className="panel-title">
                <h2>异常与风险</h2>
              </div>
              <ul>
                {status.risks.map((risk) => (
                  <li key={risk}>
                    <AlertTriangle size={15} aria-hidden="true" />
                    <span>{risk}</span>
                  </li>
                ))}
                <li>
                  <AlertTriangle size={15} aria-hidden="true" />
                  <span>派生周期只在 5M 完整桶齐全后生成，未闭合的 15M/1H/4H 不会提前写入。</span>
                </li>
              </ul>
            </aside>
          </section>
        </>
      )}
    </section>
  );
}

function TaskCard({ card }: { card: MarketKlineTaskCard }) {
  return (
    <article className={`panel data-task-card ${statusClass[card.status]}`}>
      <div className="task-card-head">
        <div>
          <span>{card.phase}</span>
          <h2>{card.name}</h2>
        </div>
        <b>{card.statusLabel}</b>
      </div>
      {card.progressCurrent !== null && card.progressTotal !== null && card.progressPercent !== null ? (
        <div className="task-progress">
          <div>
            <strong>{card.progressCurrent} / {card.progressTotal}</strong>
            <span>{card.progressPercent}%</span>
          </div>
          <span><i style={{ width: `${Math.min(100, card.progressPercent)}%` }} /></span>
        </div>
      ) : (
        <div className="task-icon-line">
          {card.status === "warning" ? <AlertTriangle size={18} /> : card.status === "completed" ? <ShieldCheck size={18} /> : <Clock3 size={18} />}
          <span>{card.lastRunAt ? `最近执行：${formatTime(card.lastRunAt)}` : "等待下一次执行"}</span>
        </div>
      )}
      <div className="task-metrics">
        <span>{card.primaryMetric}</span>
        <span>{card.secondaryMetric}</span>
      </div>
      {card.lastError ? <p className="task-error">{card.lastError}</p> : null}
    </article>
  );
}

function formatTime(value: string | null | undefined) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", { hour12: false });
}

function formatNumber(value: number) {
  return value.toLocaleString("zh-CN");
}

function isNativePeriod(period: Period) {
  return nativePeriods.has(period);
}

function periodSourceLabel(period: Period) {
  return isNativePeriod(period) ? "原生采集" : "派生缓存";
}

function periodSourceClass(period: Period) {
  return isNativePeriod(period) ? "native" : "derived";
}

function typeLabel(type: "backfill" | "incremental" | "cleanup") {
  if (type === "backfill") return "历史补齐";
  if (type === "incremental") return "增量更新";
  return "数据清理";
}
