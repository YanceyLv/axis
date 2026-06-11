import { ChevronLeft, ChevronRight, Eye, RotateCcw } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatDateTime, formatPrice } from "../data-format";
import type { Period, Signal } from "../types";

interface SignalsProps {
  signals: Signal[];
  onOpenSignal: (id: string) => void;
}

type SignalTab = "all" | "trend" | "watch";
type PeriodFilter = Period | "all";
type SignalTypeFilter = "all" | "trend" | "watch" | "momentum" | "other";
type TimeFilter = "all" | "today" | "7d" | "30d" | "custom";

const periods: Period[] = ["5M", "15M", "1H", "4H", "1D"];
const pageSizeOptions = [10, 20, 50];

export function Signals({ signals, onOpenSignal }: SignalsProps) {
  const [tab, setTab] = useState<SignalTab>("all");
  const [keyword, setKeyword] = useState("");
  const [periodFilter, setPeriodFilter] = useState<PeriodFilter>("all");
  const [strategyFilter, setStrategyFilter] = useState("all");
  const [signalTypeFilter, setSignalTypeFilter] = useState<SignalTypeFilter>("all");
  const [timeFilter, setTimeFilter] = useState<TimeFilter>("all");
  const [customStart, setCustomStart] = useState("");
  const [customEnd, setCustomEnd] = useState("");
  const [minimumScore, setMinimumScore] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);

  const strategyOptions = useMemo(() => {
    const names = new Set<string>();
    signals.forEach((signal) => {
      if (signal.strategyName) names.add(signal.strategyName);
    });
    return Array.from(names).sort((a, b) => a.localeCompare(b));
  }, [signals]);

  const filteredSignals = useMemo(() => {
    const normalizedKeyword = keyword.trim().toLowerCase();
    const timeRange = resolveTimeRange(timeFilter, customStart, customEnd);

    return signals.filter((signal) => {
      const signalType = normalizeSignalType(signal.signalType);
      if (tab === "trend" && signalType !== "trend") return false;
      if (tab === "watch" && signalType !== "watch") return false;
      if (signalTypeFilter !== "all" && signalType !== signalTypeFilter) return false;
      if (strategyFilter !== "all" && signal.strategyName !== strategyFilter) return false;
      if (periodFilter !== "all" && signal.period !== periodFilter) return false;
      if (signal.score < minimumScore) return false;
      if (!isSignalInTimeRange(signal.triggeredAt, timeRange)) return false;
      if (!normalizedKeyword) return true;

      const searchableText = [
        signal.symbol,
        signal.strategyName,
        signal.signalType,
        signal.summary,
        signal.period
      ].join(" ").toLowerCase();
      return searchableText.includes(normalizedKeyword);
    });
  }, [customEnd, customStart, keyword, minimumScore, periodFilter, signalTypeFilter, signals, strategyFilter, tab, timeFilter]);

  const totalPages = Math.max(1, Math.ceil(filteredSignals.length / pageSize));
  const safePage = Math.min(page, totalPages);
  const pagedSignals = filteredSignals.slice((safePage - 1) * pageSize, safePage * pageSize);

  useEffect(() => {
    setPage(1);
  }, [customEnd, customStart, keyword, minimumScore, pageSize, periodFilter, signalTypeFilter, strategyFilter, tab, timeFilter]);

  function resetFilters() {
    setTab("all");
    setKeyword("");
    setPeriodFilter("all");
    setStrategyFilter("all");
    setSignalTypeFilter("all");
    setTimeFilter("all");
    setCustomStart("");
    setCustomEnd("");
    setMinimumScore(0);
    setPage(1);
  }

  return (
    <section className="page signals-page">
      <header className="page-header">
        <div>
          <h1>信号中心</h1>
          <p>查看策略发现和观察池触发的市场信号。</p>
        </div>
      </header>

      <div className="toolbar">
        <div className="tabs" role="tablist" aria-label="信号类型快捷筛选">
          <button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")} type="button">全部</button>
          <button className={tab === "trend" ? "active" : ""} onClick={() => setTab("trend")} type="button">策略发现</button>
          <button className={tab === "watch" ? "active" : ""} onClick={() => setTab("watch")} type="button">观察池</button>
        </div>
        <span className="muted">共 {filteredSignals.length} 条信号</span>
      </div>

      <section className="signal-filter-panel">
        <div className="signal-filter-grid">
          <input
            aria-label="搜索信号"
            placeholder="搜索币种/策略"
            value={keyword}
            onChange={(event) => setKeyword(event.target.value)}
          />
          <select aria-label="按时间筛选信号" value={timeFilter} onChange={(event) => setTimeFilter(event.target.value as TimeFilter)}>
            <option value="all">全部时间</option>
            <option value="today">今天</option>
            <option value="7d">最近 7 天</option>
            <option value="30d">最近 30 天</option>
            <option value="custom">自定义时间</option>
          </select>
          {timeFilter === "custom" ? (
            <>
              <input aria-label="开始日期" type="date" value={customStart} onChange={(event) => setCustomStart(event.target.value)} />
              <input aria-label="结束日期" type="date" value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} />
            </>
          ) : null}
          <select aria-label="按策略筛选信号" value={strategyFilter} onChange={(event) => setStrategyFilter(event.target.value)}>
            <option value="all">全部策略</option>
            {strategyOptions.map((strategyName) => (
              <option key={strategyName} value={strategyName}>{strategyName}</option>
            ))}
          </select>
          <select aria-label="按信号类型筛选" value={signalTypeFilter} onChange={(event) => setSignalTypeFilter(event.target.value as SignalTypeFilter)}>
            <option value="all">全部信号类型</option>
            <option value="trend">策略发现</option>
            <option value="watch">观察池</option>
            <option value="momentum">动量信号</option>
            <option value="other">其他类型</option>
          </select>
          <select aria-label="按周期筛选信号" value={periodFilter} onChange={(event) => setPeriodFilter(event.target.value as PeriodFilter)}>
            <option value="all">全部周期</option>
            {periods.map((period) => (
              <option key={period} value={period}>{period}</option>
            ))}
          </select>
          <label className="score-filter signal-score-filter">
            <span>最低评分</span>
            <input
              aria-label="最低信号评分"
              min="0"
              max="100"
              step="1"
              type="number"
              value={minimumScore}
              onChange={(event) => setMinimumScore(Number(event.target.value) || 0)}
            />
          </label>
          <button className="secondary compact" onClick={resetFilters} type="button"><RotateCcw size={14} />重置</button>
        </div>
      </section>

      <section className="panel table-panel signal-table-panel">
        <table className="table">
          <thead>
            <tr>
              <th>币种</th>
              <th>周期</th>
              <th>策略</th>
              <th>类型</th>
              <th>价格</th>
              <th>评分</th>
              <th>后续表现</th>
              <th>触发时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {pagedSignals.map((signal) => (
              <tr key={signal.id}>
                <td><strong>{signal.symbol}</strong></td>
                <td>{signal.period}</td>
                <td>{signal.strategyName}</td>
                <td><span className="chip">{signalTypeLabel(signal.signalType)}</span></td>
                <td>{formatPrice(signal.price)}</td>
                <td>{signal.score}</td>
                <td>{performanceLabel(signal)}</td>
                <td>{formatDateTime(signal.triggeredAt)}</td>
                <td>
                  <button className="secondary compact" onClick={() => onOpenSignal(signal.id)} type="button">
                    <Eye size={15} aria-hidden="true" />
                    查看
                  </button>
                </td>
              </tr>
            ))}
            {!pagedSignals.length ? (
              <tr>
                <td className="empty-table-cell" colSpan={9}>没有符合筛选条件的信号</td>
              </tr>
            ) : null}
          </tbody>
        </table>
        <SignalPagination
          page={safePage}
          pageSize={pageSize}
          total={filteredSignals.length}
          totalPages={totalPages}
          onPageChange={setPage}
          onPageSizeChange={setPageSize}
        />
      </section>
    </section>
  );
}

function SignalPagination({ page, pageSize, total, totalPages, onPageChange, onPageSizeChange }: { page: number; pageSize: number; total: number; totalPages: number; onPageChange: (page: number) => void; onPageSizeChange: (pageSize: number) => void }) {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(total, page * pageSize);
  return <footer className="table-pagination">
    <span>显示 {start}-{end} / 共 {total} 条</span>
    <div>
      <button className="icon-button" disabled={page <= 1} onClick={() => onPageChange(page - 1)} type="button" aria-label="上一页"><ChevronLeft size={17} /></button>
      <strong>{page} / {totalPages}</strong>
      <button className="icon-button" disabled={page >= totalPages} onClick={() => onPageChange(page + 1)} type="button" aria-label="下一页"><ChevronRight size={17} /></button>
      <select aria-label="每页条数" value={pageSize} onChange={(event) => onPageSizeChange(Number(event.target.value))}>
        {pageSizeOptions.map((option) => <option key={option} value={option}>{option} 条/页</option>)}
      </select>
    </div>
  </footer>;
}

function resolveTimeRange(timeFilter: TimeFilter, customStart: string, customEnd: string): { start: Date | null; end: Date | null } {
  const now = new Date();
  if (timeFilter === "today") {
    const start = new Date(now);
    start.setHours(0, 0, 0, 0);
    return { start, end: now };
  }
  if (timeFilter === "7d" || timeFilter === "30d") {
    const days = timeFilter === "7d" ? 7 : 30;
    const start = new Date(now);
    start.setDate(start.getDate() - days);
    return { start, end: now };
  }
  if (timeFilter === "custom") {
    const start = customStart ? new Date(`${customStart}T00:00:00`) : null;
    const end = customEnd ? new Date(`${customEnd}T23:59:59`) : null;
    return { start, end };
  }
  return { start: null, end: null };
}

function isSignalInTimeRange(triggeredAt: string, range: { start: Date | null; end: Date | null }): boolean {
  const value = new Date(triggeredAt);
  if (Number.isNaN(value.getTime())) return false;
  if (range.start && value < range.start) return false;
  if (range.end && value > range.end) return false;
  return true;
}

function normalizeSignalType(signalType: string): SignalTypeFilter {
  const value = signalType.trim().toLowerCase();
  if (value === "trend" || value === "strategy" || value.includes("趋势") || value.includes("策略")) return "trend";
  if (value === "watch" || value.includes("观察")) return "watch";
  if (value === "momentum" || value.includes("动量") || value.includes("突破")) return "momentum";
  return "other";
}

function signalTypeLabel(signalType: string): string {
  const normalized = normalizeSignalType(signalType);
  if (normalized === "trend") return "策略发现";
  if (normalized === "watch") return "观察池";
  if (normalized === "momentum") return "动量信号";
  return signalType || "其他类型";
}

function performanceLabel(signal: Signal): string {
  const performance = signal.performance;
  if (!performance) return "待追踪";
  if (performance.status === "tracking") return "追踪中";
  if (performance.status === "insufficient_data") return "数据不足";
  const result = performance.reviewResult ? reviewResultLabel(performance.reviewResult) : "待复盘";
  const change = formatPercent(performance.change24hPct);
  return `${result} / 24h ${change}`;
}

function reviewResultLabel(result: NonNullable<Signal["performance"]>["reviewResult"]): string {
  if (result === "effective") return "有效";
  if (result === "weak") return "偏弱";
  if (result === "failed") return "失败";
  if (result === "insufficient_data") return "数据不足";
  return "待复盘";
}

function formatPercent(value: number | null): string {
  if (value === null) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}
