import { ArrowUpRight, RefreshCw } from "lucide-react";
import { SparkLine } from "../components/Charts";
import { formatPercent, formatPrice, formatTimeOnly } from "../data-format";
import type { DashboardSummary, Signal, Strategy, WatchItem } from "../types";

interface DashboardProps {
  dashboard: DashboardSummary;
  onOpenSignal: (id: string) => void;
  onOpenWatch: (id: string) => void;
}

const kpiLabels = [
  ["今日信号", "todaySignals"],
  ["启用策略", "enabledStrategies"],
  ["观察币种", "watchSymbols"],
  ["观察提醒", "observationAlerts"],
  ["运行策略", "runningStrategies"]
] as const;

export function Dashboard({ dashboard, onOpenSignal, onOpenWatch }: DashboardProps) {
  return (
    <section className="page dashboard-page">
      <header className="page-header">
        <div>
          <h1>早上好，Trader</h1>
          <p>市场永远在变化，机会留给盯得住的人。</p>
        </div>
        <div className="header-meta">
          <span>更新时间：2026-05-31 13:30:00</span>
          <RefreshCw size={15} aria-hidden="true" />
        </div>
      </header>

      <div className="kpis">
        {kpiLabels.map(([label, key]) => (
          <article className="card kpi-card" key={key}>
            <span>{label}</span>
            <strong>{dashboard[key]}</strong>
          </article>
        ))}
      </div>

      <div className="dashboard-workspace">
        <section className="panel table-panel latest-panel">
          <div className="panel-title">
            <h2>今日最新信号</h2>
            <span className="muted">{dashboard.latestSignals.length} 条</span>
          </div>
          <SignalRows signals={dashboard.latestSignals} onOpenSignal={onOpenSignal} />
        </section>

        <section className="panel trend-panel">
          <div className="panel-title">
            <h2>信号趋势</h2>
            <span className="muted">近 7 日</span>
          </div>
          <SparkLine values={dashboard.signalTrend.map((item) => item.count)} />
          <div className="trend-labels">
            {dashboard.signalTrend.map((item) => (
              <span key={item.date}>{item.date}</span>
            ))}
          </div>
        </section>
      </div>

      <div className="split-layout">
        <section className="panel">
          <div className="panel-title">
            <h2>近期策略</h2>
            <span className="muted">按创建时间</span>
          </div>
          <StrategyRows strategies={dashboard.recentStrategies} />
        </section>

        <section className="panel">
          <div className="panel-title">
            <h2>近期观察</h2>
            <span className="muted">观察池</span>
          </div>
          <WatchRows items={dashboard.recentWatchlist} onOpenWatch={onOpenWatch} />
        </section>
      </div>
    </section>
  );
}

function SignalRows({
  signals,
  onOpenSignal
}: {
  signals: Signal[];
  onOpenSignal: (id: string) => void;
}) {
  return (
    <table className="table">
      <thead>
        <tr>
          <th>时间</th>
          <th>币种</th>
          <th>策略</th>
          <th>类型</th>
          <th>价格</th>
          <th>评分</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        {signals.map((signal) => (
          <tr key={signal.id}>
            <td>{formatSignalTime(signal.triggeredAt)}</td>
            <td><strong>{signal.symbol}</strong></td>
            <td>{strategyDisplayName(signal.strategyName)}</td>
            <td><span className="chip">{signalTypeLabel(signal.signalType)}</span></td>
            <td>{formatPrice(signal.price)}</td>
            <td><span className="row-value">{signal.score}<ArrowUpRight size={14} aria-hidden="true" /></span></td>
            <td>
              <button className="secondary compact" onClick={() => onOpenSignal(signal.id)} type="button">
                查看
              </button>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function formatSignalTime(value: string): string {
  return formatTimeOnly(value);
}

function signalTypeLabel(signalType: string): string {
  const value = signalType.toLowerCase();
  if (value === "trend" || value.includes("趋势")) return "趋势信号";
  if (value === "momentum" || value.includes("动量")) return "动量突破";
  if (value === "watch" || value.includes("观察")) return "观察信号";
  return signalType;
}

function strategyDisplayName(name: string): string {
  const labels: Record<string, string> = {
    "MEME 1H Volume Momentum": "MEME 1H 动量突破",
    "SOLUSDT Daily Trend Continuation": "SOLUSDT 日线趋势延续",
    "ALLUSDT Volume Breakout Case": "ALLUSDT 放量突破案例"
  };

  return labels[name] ?? name;
}

function StrategyRows({ strategies }: { strategies: Strategy[] }) {
  return (
    <div className="compact-list">
      {strategies.map((strategy) => (
        <div className="list-row static" key={strategy.id}>
          <span>
            <strong>{strategyDisplayName(strategy.name)}</strong>
            <small>{strategy.period} / {strategy.source === "ai" ? "AI" : "预设"}</small>
          </span>
          <span className={strategy.enabled ? "status-on" : "status-off"}>
            {strategy.enabled ? "运行中" : "已暂停"}
          </span>
        </div>
      ))}
    </div>
  );
}

function WatchRows({
  items,
  onOpenWatch
}: {
  items: WatchItem[];
  onOpenWatch: (id: string) => void;
}) {
  return (
    <div className="compact-list">
      {items.map((item) => (
        <button className="list-row" key={item.id} onClick={() => onOpenWatch(item.id)} type="button">
          <span>
            <strong>{item.symbol}</strong>
            <small>{formatPrice(item.currentPrice)}</small>
          </span>
          <span className={item.change24h >= 0 ? "positive" : "negative"}>{formatPercent(item.change24h)}</span>
        </button>
      ))}
    </div>
  );
}
