import { ChevronDown, ChevronRight, Plus } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "../api";
import { MarketKlineChart } from "../components/MarketKlineChart";
import { StrengthGrade } from "../components/StrengthGrade";
import { formatDateTime, formatPrice } from "../data-format";
import type { Candle, Period, Signal } from "../types";

interface SignalDetailProps {
  signal: Signal | null;
  isAddingToWatch: boolean;
  onBack: () => void;
  onAddToWatch: (signal: Signal) => Promise<void>;
}

export function SignalDetail({ signal, isAddingToWatch, onBack, onAddToWatch }: SignalDetailProps) {
  const [chartPeriod, setChartPeriod] = useState<Period>(signal?.period ?? "1H");
  const [chartCandles, setChartCandles] = useState<Candle[]>(signal?.candles ?? []);
  const [chartLoading, setChartLoading] = useState(false);
  const [chartError, setChartError] = useState("");
  const [strategyInfoOpen, setStrategyInfoOpen] = useState(false);

  useEffect(() => {
    if (!signal) return;
    setChartPeriod(signal.period);
    setChartCandles(signal.candles);
    setChartError("");
  }, [signal?.id]);

  useEffect(() => {
    if (!signal) return;
    let cancelled = false;
    setChartLoading(true);
    setChartError("");
    api.marketKlines(signal.symbol, chartPeriod)
      .then((candles) => {
        if (cancelled) return;
        setChartCandles(candles);
      })
      .catch((error) => {
        if (cancelled) return;
        setChartError(error instanceof Error ? error.message : "K线加载失败");
        setChartCandles(signal.candles);
      })
      .finally(() => {
        if (!cancelled) setChartLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [chartPeriod, signal]);

  if (!signal) {
    return (
      <section className="page">
        <button className="secondary compact" onClick={onBack} type="button">返回</button>
        <div className="panel empty-state">未找到信号。</div>
      </section>
    );
  }

  const reviewAnalysis = signal.performance ? formatReviewAnalysis(signal.performance.reviewAnalysis) : "";

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{signal.symbol} 信号详情</h1>
          <p>{signal.summary}</p>
          <div className="signal-detail-meta">
            <span>{signal.period}</span>
            <span>{signal.strategyName}</span>
            <span>{signal.signalType}</span>
            <span>触发价 {formatPrice(signal.price)}</span>
            <span>{formatDateTime(signal.triggeredAt)}</span>
            <StrengthGrade grade={signal.strengthGrade} score={signal.score} />
          </div>
        </div>
        <div className="toolbar-actions">
          <button className="secondary" onClick={onBack} type="button">返回</button>
          <button
            className="primary"
            disabled={isAddingToWatch}
            onClick={() => void onAddToWatch(signal)}
            type="button"
          >
            <Plus size={17} aria-hidden="true" />
            {isAddingToWatch ? "加入中..." : "加入观察"}
          </button>
        </div>
      </header>

      <section className="panel chart-panel signal-chart-panel">
        <div className="panel-title">
          <div>
            <h2>K线走势</h2>
            <span className="muted">{signal.symbol} / 数据库已存K线</span>
          </div>
          <div className="period-switcher" role="tablist" aria-label="K线周期">
            {periods.map((period) => (
              <button
                className={chartPeriod === period ? "active" : ""}
                key={period}
                onClick={() => setChartPeriod(period)}
                type="button"
              >
                {period}
              </button>
            ))}
          </div>
        </div>
        <MarketKlineChart candles={chartCandles} signalTime={signal.triggeredAt} loading={chartLoading} />
        {chartError ? (
          <div className="inline-error">{chartError}，已显示信号保存时的 K 线。</div>
        ) : null}
      </section>

      <section className="panel">
        <div className="panel-title">
          <h2>后续表现</h2>
          <span className="muted">{signal.performance ? performanceStatusLabel(signal.performance.status) : "待追踪"}</span>
        </div>
        {signal.performance ? (
          <div className="performance-grid">
            <div className="stat-block">
              <span>1h</span>
              <strong>{formatPercent(signal.performance.change1hPct)}</strong>
            </div>
            <div className="stat-block">
              <span>4h</span>
              <strong>{formatPercent(signal.performance.change4hPct)}</strong>
            </div>
            <div className="stat-block">
              <span>24h</span>
              <strong>{formatPercent(signal.performance.change24hPct)}</strong>
            </div>
            <div className="stat-block">
              <span>最大浮盈</span>
              <strong>{formatPercent(signal.performance.maxGainPct)}</strong>
            </div>
            <div className="stat-block">
              <span>最大回撤</span>
              <strong>{formatPercent(signal.performance.maxDrawdownPct)}</strong>
            </div>
            <div className="stat-block">
              <span>评估到</span>
              <strong>{signal.performance.evaluatedUntil ? formatDateTime(signal.performance.evaluatedUntil) : "--"}</strong>
            </div>
          </div>
        ) : (
          <p className="muted">后台会在 K 线数据更新后开始追踪该信号。</p>
        )}
      </section>

      {signal.performance?.reviewStatus === "generated" ? (
        <section className="panel ai-review-panel">
          <div className="panel-title">
            <h2>AI 复盘</h2>
            <span className="chip">{reviewResultLabel(signal.performance.reviewResult)}</span>
          </div>
          <div className="ai-review-metrics">
            <ReviewMetric label="1H 表现" value={formatPercent(signal.performance.change1hPct)} />
            <ReviewMetric label="4H 表现" value={formatPercent(signal.performance.change4hPct)} />
            <ReviewMetric label="24H 表现" value={formatPercent(signal.performance.change24hPct)} />
            <ReviewMetric label="最大回撤" value={formatPercent(signal.performance.maxDrawdownPct)} />
          </div>
          <article className="ai-review-summary">
            <span>主结论</span>
            <p>{signal.performance.reviewSummary}</p>
          </article>
          {reviewAnalysis ? (
            <article className="ai-review-analysis">
              <span>复盘判断</span>
              <p>{reviewAnalysis}</p>
            </article>
          ) : null}
          {signal.performance.reviewSuggestions.length ? (
            <div className="ai-review-suggestions">
              <span>操作建议</span>
              <ol>
              {signal.performance.reviewSuggestions.map((item) => (
                <li key={item}>{item}</li>
              ))}
              </ol>
            </div>
          ) : null}
        </section>
      ) : null}

      <section className="panel strategy-note-panel">
        <button className="strategy-note-toggle" onClick={() => setStrategyInfoOpen((value) => !value)} type="button">
          {strategyInfoOpen ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
          <span>策略说明</span>
        </button>
        {strategyInfoOpen ? (
          <ul className="analysis-list compact">
            {signal.analysis.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        ) : null}
      </section>
    </section>
  );
}

const periods: Period[] = ["5M", "15M", "1H", "4H", "1D"];

function ReviewMetric({ label, value }: { label: string; value: string }) {
  const directionClass = value.startsWith("+") ? "positive" : value.startsWith("-") ? "negative" : "";
  return (
    <div className="ai-review-metric">
      <span>{label}</span>
      <strong className={directionClass}>{value}</strong>
    </div>
  );
}

function performanceStatusLabel(status: NonNullable<Signal["performance"]>["status"]): string {
  if (status === "completed") return "追踪完成";
  if (status === "insufficient_data") return "数据不足";
  return "追踪中";
}

function reviewResultLabel(result: NonNullable<Signal["performance"]>["reviewResult"]): string {
  if (result === "effective") return "有效";
  if (result === "weak") return "偏弱";
  if (result === "failed") return "失败";
  if (result === "insufficient_data") return "数据不足";
  return "待复盘";
}

function formatReviewAnalysis(value: string): string {
  const trimmed = value.trim();
  if (!trimmed) return "";
  if (!isRawReviewPayload(trimmed)) return trimmed;
  return extractReviewField(trimmed, "interpretation") ?? extractReviewField(trimmed, "summary") ?? "";
}

function isRawReviewPayload(value: string): boolean {
  return value.startsWith("{") && (
    value.includes("signalId") ||
    value.includes("performance") ||
    value.includes("interpretation") ||
    value.includes("historicalEvidence")
  );
}

function extractReviewField(value: string, field: string): string | null {
  const pattern = new RegExp(`[\"']${field}[\"']\\s*:\\s*[\"']([\\s\\S]*?)[\"']\\s*(?:,|})`);
  const match = value.match(pattern);
  return match?.[1]?.trim() || null;
}

function formatPercent(value: number | null): string {
  if (value === null) return "--";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}%`;
}
