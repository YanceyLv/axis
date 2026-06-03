import { KlineChart } from "../components/Charts";
import { formatDateTime, formatPercent, formatPrice } from "../data-format";
import type { Candle, WatchItem, WatchStatus } from "../types";

interface WatchDetailProps {
  item: WatchItem | null;
  candles: Candle[];
  onBack: () => void;
}

const statusLabel: Record<WatchStatus, string> = {
  pending: "待观察",
  matched: "已命中",
  unmatched: "未命中"
};

export function WatchDetail({ item, candles, onBack }: WatchDetailProps) {
  if (!item) {
    return (
      <section className="page">
        <button className="secondary compact" onClick={onBack} type="button">返回</button>
        <div className="panel empty-state">未找到观察项。</div>
      </section>
    );
  }

  return (
    <section className="page">
      <header className="page-header">
        <div>
          <h1>{item.symbol} 观察详情</h1>
          <p>创建于 {formatDateTime(item.createdAt)}</p>
        </div>
        <button className="secondary" onClick={onBack} type="button">返回</button>
      </header>

      <div className="split-layout">
        <section className="panel metric-panel">
          <span>当前价格</span>
          <strong>{formatPrice(item.currentPrice)}</strong>
        </section>
        <section className="panel metric-panel">
          <span>24H 变化</span>
          <strong className={item.change24h >= 0 ? "positive" : "negative"}>{formatPercent(item.change24h)}</strong>
        </section>
      </div>

      <section className="panel chart-panel">
        <div className="panel-title">
          <h2>K线图</h2>
          <span className="muted">{item.symbol}</span>
        </div>
        <KlineChart candles={candles} />
      </section>

      <section className="panel">
        <div className="panel-title">
          <h2>条件状态</h2>
          <span className="muted">{item.conditions.length} 个条件</span>
        </div>
        <div className="watch-condition-list">
          {item.conditions.map((condition) => (
            <article className={`watch-condition ${condition.status}`} key={condition.id}>
              <div>
                <strong>{condition.expression}</strong>
                <p>{condition.type} / {condition.period}</p>
              </div>
              <span>{statusLabel[condition.status]}</span>
              <small>{formatDateTime(condition.lastTriggeredAt, "暂无触发")}</small>
            </article>
          ))}
        </div>
      </section>
    </section>
  );
}
