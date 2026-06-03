import { Eye, Plus } from "lucide-react";
import { KlineChart } from "../components/Charts";
import { StrengthGrade } from "../components/StrengthGrade";
import { formatDateTime, formatPrice } from "../data-format";
import type { Signal } from "../types";

interface SignalDetailProps {
  signal: Signal | null;
  isAddingToWatch: boolean;
  onBack: () => void;
  onAddToWatch: (signal: Signal) => Promise<void>;
}

export function SignalDetail({ signal, isAddingToWatch, onBack, onAddToWatch }: SignalDetailProps) {
  if (!signal) {
    return (
      <section className="page">
        <button className="secondary compact" onClick={onBack} type="button">返回</button>
        <div className="panel empty-state">未找到信号。</div>
      </section>
    );
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{signal.symbol} 信号详情</h1>
          <p>{signal.summary}</p>
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

      <div className="detail-layout">
        <section className="panel chart-panel">
          <div className="panel-title">
            <h2>K线走势</h2>
            <span className="muted">{signal.period} / {formatDateTime(signal.triggeredAt)}</span>
          </div>
          <KlineChart candles={signal.candles} signalTime={signal.triggeredAt} />
        </section>

        <aside className="panel detail-side">
          <div className="stat-block">
            <span>触发价格</span>
            <strong>{formatPrice(signal.price)}</strong>
          </div>
          <div className="stat-block">
            <span>策略</span>
            <strong>{signal.strategyName}</strong>
          </div>
          <div className="stat-block">
            <span>类型</span>
            <strong>{signal.signalType}</strong>
          </div>
          <StrengthGrade grade={signal.strengthGrade} score={signal.score} />
        </aside>
      </div>

      <section className="panel">
        <div className="panel-title">
          <h2>分析理由</h2>
          <Eye size={18} aria-hidden="true" />
        </div>
        <ul className="analysis-list">
          {signal.analysis.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </section>
  );
}
