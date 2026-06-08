import { ExternalLink, RefreshCw, Rocket, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { formatDateTime } from "../data-format";
import type { NewCoinListing, NewCoinScanResult } from "../types";

interface NewCoinsProps {
  listings: NewCoinListing[];
  onScan: () => Promise<NewCoinScanResult>;
}

export function NewCoins({ listings, onScan }: NewCoinsProps) {
  const [scanResult, setScanResult] = useState<NewCoinScanResult | null>(null);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState("");

  const stats = useMemo(() => {
    const upcoming = listings.filter((item) => item.status === "upcoming").length;
    const notified = listings.filter((item) => item.notifiedAt).length;
    return { total: listings.length, upcoming, notified };
  }, [listings]);

  async function handleScan() {
    setScanning(true);
    setError("");
    try {
      const result = await onScan();
      setScanResult(result);
      if (result.errors.length) {
        setError(result.errors.join("\n"));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "新币检测失败");
    } finally {
      setScanning(false);
    }
  }

  return (
    <section className="page new-coins-page">
      <header className="page-header">
        <div>
          <h1>新币检测</h1>
          <p>监控 Binance 新币上市公告，发现即将上线的币种并触发 Pushover 提醒。</p>
        </div>
        <button className="primary" disabled={scanning} onClick={() => void handleScan()} type="button">
          <RefreshCw size={16} aria-hidden="true" />
          {scanning ? "检测中" : "立即检测"}
        </button>
      </header>

      <div className="kpis new-coin-kpis">
        <article className="card kpi-card">
          <span>已发现</span>
          <strong>{stats.total}</strong>
        </article>
        <article className="card kpi-card">
          <span>即将上线</span>
          <strong>{stats.upcoming}</strong>
        </article>
        <article className="card kpi-card">
          <span>已提醒</span>
          <strong>{stats.notified}</strong>
        </article>
        <article className="card new-coin-source-card">
          <Rocket size={19} />
          <span>数据来源</span>
          <strong>Binance 公告</strong>
        </article>
      </div>

      {scanResult ? (
        <div className={`strategy-run-summary ${scanResult.errors.length ? "warning" : ""}`}>
          <span>本次检测</span>
          <strong>抓取 {scanResult.fetched}</strong>
          <strong>新增 {scanResult.created}</strong>
          <strong>更新 {scanResult.updated}</strong>
          <strong>提醒 {scanResult.notified}</strong>
        </div>
      ) : null}
      {error ? <div className="inline-error">{error}</div> : null}

      <section className="panel table-panel new-coin-table-panel">
        <table className="table">
          <thead>
            <tr>
              <th>币种</th>
              <th>交易对</th>
              <th>状态</th>
              <th>公告标题</th>
              <th>公告时间</th>
              <th>提醒</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            {listings.map((item) => (
              <tr key={item.id}>
                <td>
                  <strong>{item.symbol}</strong>
                  <p className="table-note">{item.source.toUpperCase()}</p>
                </td>
                <td>
                  <div className="new-coin-pairs">
                    {item.tradingPairs.map((pair) => <span key={pair}>{pair}</span>)}
                  </div>
                </td>
                <td><span className={`new-coin-status ${item.status}`}>{statusLabel(item.status)}</span></td>
                <td className="new-coin-title">{item.title}</td>
                <td>{formatDateTime(item.announcedAt)}</td>
                <td>
                  {item.notifiedAt ? (
                    <span className="new-coin-notified"><ShieldCheck size={14} />已提醒</span>
                  ) : (
                    <span className="muted">未提醒</span>
                  )}
                </td>
                <td>
                  <a className="secondary compact new-coin-link" href={item.url} target="_blank" rel="noreferrer">
                    <ExternalLink size={14} />
                    公告
                  </a>
                </td>
              </tr>
            ))}
            {!listings.length ? (
              <tr>
                <td className="empty-table-cell" colSpan={7}>还没有检测到新币公告，点击“立即检测”开始扫描。</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </section>
    </section>
  );
}

function statusLabel(status: NewCoinListing["status"]): string {
  const labels: Record<NewCoinListing["status"], string> = {
    discovered: "已发现",
    upcoming: "即将上线",
    listed: "已上线",
  };
  return labels[status];
}
