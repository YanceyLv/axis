import { Eye, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { Modal } from "../components/Modal";
import { formatDateTime, formatPercent, formatPrice } from "../data-format";
import type { CreateWatchItemPayload, Period, WatchCondition, WatchItem } from "../types";

interface WatchlistProps {
  watchlist: WatchItem[];
  onOpenWatch: (id: string) => void;
  onCreateWatchItem: (payload: CreateWatchItemPayload) => Promise<void>;
}

const periods: Period[] = ["5M", "15M", "1H", "4H", "1D"];

export function Watchlist({ watchlist, onOpenWatch, onCreateWatchItem }: WatchlistProps) {
  const [modalOpen, setModalOpen] = useState(false);

  return (
    <section className="page watchlist-page">
      <header className="page-header">
        <div>
          <h1>观察池</h1>
          <p>跟踪重点币种和待确认条件。</p>
        </div>
        <button className="primary" onClick={() => setModalOpen(true)} type="button">
          <Plus size={17} aria-hidden="true" />
          加入观察
        </button>
      </header>

      <section className="panel table-panel watchlist-table-panel">
        <table className="table">
          <thead>
            <tr>
              <th>币种</th>
              <th>当前价格</th>
              <th>24H</th>
              <th>条件数</th>
              <th>最近触发</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {watchlist.map((item) => (
              <tr key={item.id}>
                <td><strong>{item.symbol}</strong></td>
                <td>{formatPrice(item.currentPrice)}</td>
                <td className={item.change24h >= 0 ? "positive" : "negative"}>{formatPercent(item.change24h)}</td>
                <td>{item.conditions.length}</td>
                <td>{formatDateTime(item.lastTriggeredAt)}</td>
                <td>{formatDateTime(item.createdAt)}</td>
                <td>
                  <button className="secondary compact" onClick={() => onOpenWatch(item.id)} type="button">
                    <Eye size={15} aria-hidden="true" />
                    查看
                  </button>
                </td>
              </tr>
            ))}
            {!watchlist.length ? (
              <tr>
                <td className="empty-table-cell" colSpan={7}>暂无观察币种</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>

      {modalOpen ? (
        <AddWatchModal
          onClose={() => setModalOpen(false)}
          onCreateWatchItem={async (payload) => {
            await onCreateWatchItem(payload);
            setModalOpen(false);
          }}
        />
      ) : null}
    </section>
  );
}

function AddWatchModal({
  onClose,
  onCreateWatchItem
}: {
  onClose: () => void;
  onCreateWatchItem: (payload: CreateWatchItemPayload) => Promise<void>;
}) {
  const [symbol, setSymbol] = useState("ALLUSDT");
  const [conditions, setConditions] = useState<WatchCondition[]>([
    {
      id: `condition-${Date.now()}`,
      type: "price",
      period: "1H",
      expression: "价格 > 0.3000",
      status: "pending",
      lastTriggeredAt: null
    }
  ]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasSymbol = symbol.trim().length > 0;
  const payloadConditions = conditions.filter((condition) => condition.expression.trim());
  const validationMessage = !hasSymbol
    ? "请输入币种"
    : payloadConditions.length === 0
      ? "请至少填写一个观察条件"
      : null;

  async function handleSave() {
    if (validationMessage) {
      setError(validationMessage);
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onCreateWatchItem({ symbol: symbol.trim().toUpperCase(), conditions: payloadConditions });
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
      setBusy(false);
    }
  }

  return (
    <Modal title="加入观察" onClose={onClose}>
      <div className="modal-body">
        <div className="form-grid">
          <label>
            <span>币种</span>
            <input value={symbol} onChange={(event) => setSymbol(event.target.value)} />
          </label>
        </div>

        <div className="condition-list">
          <div className="panel-title">
            <h3>观察条件</h3>
            <button
              className="secondary compact"
              onClick={() =>
                setConditions([
                  ...conditions,
                  {
                    id: `condition-${Date.now()}`,
                    type: "price",
                    period: "1H",
                    expression: "",
                    status: "pending",
                    lastTriggeredAt: null
                  }
                ])
              }
              type="button"
            >
              <Plus size={15} aria-hidden="true" />
              添加
            </button>
          </div>
          {conditions.map((condition, index) => (
            <div className="watch-form-row" key={condition.id}>
              <select
                value={condition.period}
                onChange={(event) => {
                  const next = [...conditions];
                  next[index] = { ...condition, period: event.target.value as Period };
                  setConditions(next);
                }}
              >
                {periods.map((period) => (
                  <option key={period} value={period}>{period}</option>
                ))}
              </select>
              <input
                value={condition.expression}
                onChange={(event) => {
                  const next = [...conditions];
                  next[index] = { ...condition, expression: event.target.value };
                  setConditions(next);
                }}
                placeholder="价格 > 0.3000"
              />
              <button
                className="icon-button"
                onClick={() => setConditions(conditions.filter((item) => item.id !== condition.id))}
                type="button"
                aria-label="删除条件"
              >
                <Trash2 size={16} aria-hidden="true" />
              </button>
            </div>
          ))}
        </div>

        {validationMessage ? <p className="inline-error">{validationMessage}</p> : null}
        {error && error !== validationMessage ? <p className="inline-error">{error}</p> : null}
        <footer className="modal-actions">
          <button className="secondary" onClick={onClose} type="button">取消</button>
          <button className="primary" disabled={busy || Boolean(validationMessage)} onClick={handleSave} type="button">
            {busy ? "保存中..." : "保存"}
          </button>
        </footer>
      </div>
    </Modal>
  );
}
