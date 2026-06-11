import {
  ArrowLeft,
  BrainCircuit,
  CheckCircle2,
  Code2,
  GripVertical,
  Info,
  ListChecks,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  TrendingUp
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { CSSProperties } from "react";
import { extractStrategyErrorLine, splitCodeLines } from "../code-editor";
import { formatDateMinute, formatDateTime } from "../data-format";
import type { GeneratedStrategy, GeneratedStrategyCondition, Period, Strategy, StrategyRunProgress, StrategyRunResult, StrategyScanHistory } from "../types";

interface StrategiesProps {
  strategies: Strategy[];
  onToggleStrategy: (id: string, enabled: boolean) => Promise<void>;
  onToggleStrategySchedule: (id: string, enabled: boolean) => Promise<void>;
  onGenerateStrategy: (period: Period, conditions: string[], forceRefresh?: boolean) => Promise<GeneratedStrategy>;
  onGenerateStrategyFromCode: (period: Period, pythonCode: string) => Promise<GeneratedStrategy>;
  onSaveGeneratedStrategy: (generated: GeneratedStrategy) => Promise<void>;
  onUpdateStrategy: (strategy: Strategy) => Promise<void>;
  onDeleteStrategy: (id: string) => Promise<void>;
  onRunStrategiesOnce: () => Promise<StrategyRunResult>;
  onStartStrategyRun: () => Promise<StrategyRunProgress>;
  onLoadStrategyRunStatus: () => Promise<StrategyRunProgress>;
  onLoadStrategyRunHistory: () => Promise<StrategyScanHistory[]>;
  onCancelStrategyRun: () => Promise<StrategyRunProgress>;
  onStrategyRunFinished: () => Promise<void>;
}

type StrategyTab = "all" | "enabled" | "paused";
type PeriodFilter = Period | "all";
type PreviewTab = "summary" | "code" | "analysis";
type BuilderAction = "generate" | "save" | null;
type BuilderMode = "conditions" | "code";

const periods: Period[] = ["5M", "15M", "1H", "4H", "1D"];
const exampleConditions = ["价格突破前高", "站上均线", "放量上涨", "回踩不破均线", "成交量萎缩", "多头排列", "RSI超买", "MACD金叉"];

export function Strategies({ strategies, onToggleStrategy, onToggleStrategySchedule, onGenerateStrategy, onGenerateStrategyFromCode, onSaveGeneratedStrategy, onUpdateStrategy, onDeleteStrategy, onStartStrategyRun, onLoadStrategyRunStatus, onLoadStrategyRunHistory, onCancelStrategyRun, onStrategyRunFinished }: StrategiesProps) {
  const [tab, setTab] = useState<StrategyTab>("all");
  const [query, setQuery] = useState("");
  const [periodFilter, setPeriodFilter] = useState<PeriodFilter>("all");
  const [builderMode, setBuilderMode] = useState<BuilderMode | null>(null);
  const [editingStrategy, setEditingStrategy] = useState<Strategy | null>(null);
  const [runResult, setRunResult] = useState<StrategyRunResult | null>(null);
  const [runProgress, setRunProgress] = useState<StrategyRunProgress | null>(null);
  const [scanHistory, setScanHistory] = useState<StrategyScanHistory[]>([]);
  const [runError, setRunError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const runnableStrategiesCount = strategies.filter((strategy) => strategy.enabled && strategy.schedule.enabled && strategy.runtime.code.trim()).length;

  const filteredStrategies = useMemo(() => {
    const q = query.trim().toLowerCase();
    return strategies.filter((strategy) => {
      if (tab === "enabled" && !strategy.enabled) return false;
      if (tab === "paused" && strategy.enabled) return false;
      if (periodFilter !== "all" && strategy.period !== periodFilter) return false;
      if (!q) return true;
      return [strategy.name, strategy.description, strategy.source, strategy.period, ...strategy.conditions].join(" ").toLowerCase().includes(q);
    });
  }, [periodFilter, query, strategies, tab]);

  useEffect(() => {
    if (!runProgress?.running) return;
    const timer = window.setInterval(() => {
      void onLoadStrategyRunStatus().then((next) => {
        setRunProgress(next);
        setRunResult(runProgressFromStatus(next));
        if (!next.running) void handleRunFinished();
      }).catch((err) => setRunError(err instanceof Error ? err.message : "读取运行状态失败"));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [onLoadStrategyRunStatus, onStrategyRunFinished, onLoadStrategyRunHistory, runProgress?.running]);

  useEffect(() => {
    void loadScanHistory();
  }, [onLoadStrategyRunHistory]);

  useEffect(() => {
    void onLoadStrategyRunStatus().then((next) => {
      if (!next.jobId) return;
      setRunProgress(next);
      setRunResult(runProgressFromStatus(next));
      if (!next.running) void loadScanHistory();
    }).catch(() => {
      setRunProgress(null);
    });
  }, [onLoadStrategyRunStatus]);

  async function loadScanHistory() {
    try {
      setScanHistory(await onLoadStrategyRunHistory());
    } catch {
      setScanHistory([]);
    }
  }

  async function handleRunFinished() {
    await onStrategyRunFinished();
    await loadScanHistory();
  }

  if (builderMode) {
    return <StrategyBuilderPage mode={builderMode} onBack={() => setBuilderMode(null)} onGenerateStrategy={onGenerateStrategy} onGenerateStrategyFromCode={onGenerateStrategyFromCode} onSaveGeneratedStrategy={async (generated) => { await onSaveGeneratedStrategy(generated); setBuilderMode(null); }} />;
  }

  if (editingStrategy) {
    return <StrategyDetailEditor strategy={editingStrategy} onBack={() => setEditingStrategy(null)} onSave={async (nextStrategy) => { await onUpdateStrategy(nextStrategy); setEditingStrategy(null); }} />;
  }

  async function handleRunOnce() {
    if (running) return;
    setRunning(true);
    setRunError(null);
    setRunResult(null);
    try {
      const result = await onStartStrategyRun();
      setRunProgress(result);
      setRunResult(runProgressFromStatus(result));
      if (!result.running) void handleRunFinished();
    } catch (err) {
      setRunError(err instanceof Error ? err.message : "运行策略失败");
    } finally {
      setRunning(false);
    }
  }

  async function handleCancelRun() {
    const result = await onCancelStrategyRun();
    setRunProgress(result);
    setRunResult(runProgressFromStatus(result));
  }

  async function handleDeleteStrategy(strategy: Strategy) {
    if (strategy.enabled) return;
    const confirmed = window.confirm(`确认删除策略「${strategy.name}」？历史信号和扫描记录会保留。`);
    if (!confirmed) return;
    await onDeleteStrategy(strategy.id);
  }

  return (
    <section className="page strategy-page">
      <header className="page-header">
        <div><h1>策略中心</h1><p>管理预设策略和 AI 生成策略的运行状态。</p></div>
        <div className="toolbar-actions">
          <button className="secondary" disabled={running || runnableStrategiesCount === 0} onClick={() => void handleRunOnce()} title={runnableStrategiesCount === 0 ? "没有可运行的策略" : "立即运行所有启用策略"} type="button"><RefreshCw size={16} />{running ? "运行中..." : "立即运行"}</button>
          <button className="secondary" onClick={() => setBuilderMode("code")} type="button"><Code2 size={17} />粘贴代码生成</button>
          <button className="primary" onClick={() => setBuilderMode("conditions")} type="button"><Sparkles size={17} />AI生成策略</button>
        </div>
      </header>
      {runnableStrategiesCount === 0 ? <div className="strategy-run-summary warning"><span>无法运行</span><strong>当前没有启用且带 Python 代码的策略</strong><em>先启用策略后再运行</em></div> : null}
      {runError ? <div className="strategy-run-summary error"><span>运行失败</span><strong>{runError}</strong><em>请检查后端日志或行情网络</em></div> : null}
      {runProgress ? <StrategyRunPanel progress={runProgress} onCancel={handleCancelRun} /> : null}
      {!runProgress && runResult ? <div className={`strategy-run-summary ${runResult.errors.length ? "warning" : ""}`}><span>本次运行</span><strong>检查策略 {runResult.strategiesChecked}</strong><strong>扫描币种 {runResult.symbolsChecked}</strong><strong>新增信号 {runResult.signalsCreated}</strong>{runResult.errors.length ? <em>错误 {runResult.errors.length} 条</em> : <em>无错误</em>}</div> : null}
      <div className="strategy-content-grid">
        <div className="strategy-main-column">
          <div className="panel strategy-controls">
            <div className="tabs" role="tablist" aria-label="策略筛选">
              <button className={tab === "all" ? "active" : ""} onClick={() => setTab("all")} type="button">全部</button>
              <button className={tab === "enabled" ? "active" : ""} onClick={() => setTab("enabled")} type="button">运行中</button>
              <button className={tab === "paused" ? "active" : ""} onClick={() => setTab("paused")} type="button">已暂停</button>
            </div>
            <div className="toolbar-actions filters">
              <input aria-label="搜索策略" placeholder="搜索策略" value={query} onChange={(event) => setQuery(event.target.value)} />
              <select aria-label="按周期筛选策略" value={periodFilter} onChange={(event) => setPeriodFilter(event.target.value as PeriodFilter)}>
                <option value="all">全部周期</option>{periods.map((period) => <option key={period} value={period}>{period}</option>)}
              </select>
            </div>
            <span className="muted">共 {filteredStrategies.length} 个策略</span>
          </div>
          <section className="panel table-panel strategy-table-panel"><table className="table"><thead><tr><th>策略</th><th>周期</th><th>来源</th><th>得分</th><th>今日信号</th><th>最近触发</th><th>状态</th><th>定时任务</th><th>操作</th></tr></thead><tbody>
            {filteredStrategies.map((strategy) => <tr key={strategy.id}>
              <td><strong>{strategy.name}</strong><p className="table-note">{strategy.description}</p></td><td>{strategy.period}</td><td><span className="chip">{strategy.source === "ai" ? "AI" : "预设"}</span></td><td>{strategy.score}</td><td>{strategy.todaySignalCount}</td><td>{formatDateTime(strategy.lastTriggeredAt)}</td>
              <td><label className="switch"><input checked={strategy.enabled} onChange={(event) => void onToggleStrategy(strategy.id, event.target.checked)} type="checkbox" /><span>{strategy.enabled ? "运行中" : "已暂停"}</span></label></td>
              <td><label className="switch"><input checked={strategy.schedule.enabled} disabled={!strategy.enabled} onChange={(event) => void onToggleStrategySchedule(strategy.id, event.target.checked)} type="checkbox" /><span>{strategy.schedule.enabled ? "已开启" : "已关闭"}</span></label></td>
              <td><div className="table-actions"><button className="secondary compact" onClick={() => setEditingStrategy(strategy)} type="button">查看 / 编辑</button><button className="icon-button danger compact" disabled={strategy.enabled} onClick={() => void handleDeleteStrategy(strategy)} title={strategy.enabled ? "请先暂停策略再删除" : "删除策略"} type="button" aria-label={`删除策略 ${strategy.name}`}><Trash2 size={15} /></button></div></td>
            </tr>)}
          </tbody></table></section>
        </div>
        <RecentScanList history={scanHistory} onRefresh={loadScanHistory} />
      </div>
    </section>
  );
}

function StrategyRunPanel({ progress, onCancel }: { progress: StrategyRunProgress; onCancel: () => Promise<void> }) {
  const [skippedExpanded, setSkippedExpanded] = useState(false);
  const percent = progress.totalSymbols > 0 ? Math.min(100, Math.round((progress.scannedSymbols / progress.totalSymbols) * 100)) : 0;
  const statusText = progress.running ? "全市场扫描中..." : progress.cancelRequested ? "扫描已取消" : "扫描完成";
  const detailText = progress.running
    ? `正在执行策略：${progress.currentStrategyName || "-"} ${progress.currentPeriod ? `(${progress.currentPeriod})` : ""}`
    : progress.cancelRequested
      ? `已取消：完成 ${progress.scannedSymbols} / ${progress.totalSymbols} 个扫描任务`
      : `已完成：检查策略 ${progress.strategiesChecked} 个，扫描币种 ${progress.scannedSymbols} 个`;
  const currentText = progress.running ? `当前正在扫描：${progress.currentSymbol || "-"}` : `最后扫描时间：${formatDateTime(progress.finishedAt ?? progress.startedAt)}`;
  return (
    <section className="strategy-scan-panel">
      <div className="strategy-scan-donut" style={{ "--value": `${percent}%` } as CSSProperties}>
        <strong>{percent}%</strong>
        <span>{progress.running ? "扫描中" : progress.cancelRequested ? "已取消" : "已完成"}</span>
      </div>
      <div className="strategy-scan-main">
        <div className="strategy-scan-heading">
          <div>
            <h2>{statusText}</h2>
            <p>{detailText}</p>
          </div>
          <span>{progress.scannedSymbols} / {progress.totalSymbols}</span>
        </div>
        <div className="strategy-scan-bar"><span style={{ width: `${percent}%` }} /></div>
        <div className="strategy-scan-stats">
          <span><b>已扫描</b>{progress.scannedSymbols}</span>
          <span><b>待扫描</b>{progress.pendingSymbols}</span>
          <span className="positive"><b>发现信号</b>{progress.signalsCreated}</span>
          <span><b>跳过</b>{progress.skippedSymbols}</span>
          <span className={progress.errorsCount ? "negative" : ""}><b>错误</b>{progress.errorsCount}</span>
          <span><b>已用时间</b>{formatDuration(progress.elapsedSeconds)}</span>
          <span><b>预计剩余</b>{formatDuration(progress.estimatedRemainingSeconds)}</span>
          <span><b>扫描速度</b>{progress.scanSpeedPerSecond.toFixed(1)} 币种/秒</span>
        </div>
        <div className="strategy-scan-current">
          <span>{currentText}</span>
          {progress.running ? <button className="secondary compact" onClick={() => void onCancel()} type="button">取消扫描</button> : null}
        </div>
      </div>
      {progress.errors.length ? <div className="strategy-run-errors"><h3>错误详情（{progress.errors.length}）</h3><table><tbody>{progress.errors.slice(-8).map((error, index) => <tr key={`${error.symbol}-${index}`}><td>{formatDateTime(error.time)}</td><td>{error.symbol}</td><td><span>{error.errorType}</span></td><td>{error.message}</td><td>{error.impact}</td></tr>)}</tbody></table></div> : null}
      {progress.skipped.length ? <div className={`strategy-run-errors skipped ${skippedExpanded ? "expanded" : "collapsed"}`}><h3><span>跳过详情（{progress.skipped.length}）</span><button className="link-button" onClick={() => setSkippedExpanded((current) => !current)} type="button">{skippedExpanded ? "收起" : "展开"}</button></h3>{skippedExpanded ? <table><tbody>{progress.skipped.slice(-8).map((item, index) => <tr key={`${item.symbol}-${index}`}><td>{formatDateTime(item.time)}</td><td>{item.symbol}</td><td><span>{item.errorType}</span></td><td>{item.message}</td><td>{item.impact}</td></tr>)}</tbody></table> : null}</div> : null}
    </section>
  );
}

function RecentScanList({ history, onRefresh }: { history: StrategyScanHistory[]; onRefresh: () => Promise<void> }) {
  return <aside className="panel recent-scan-panel">
    <header><h2>最近扫描列表</h2><button className="link-button" onClick={() => void onRefresh()} type="button">更多</button></header>
    {history.length ? <div className="recent-scan-list">
      {history.slice(0, 6).map((item) => <article className="recent-scan-item" key={item.id}>
        <div className="recent-scan-item-head"><strong>{item.strategyName}</strong><span className={item.status === "completed" ? "success" : item.status === "cancelled" ? "muted" : "danger"}>{scanStatusLabel(item.status)}</span></div>
        <p><b>{item.period ?? "-"}</b><span>{formatDateMinute(item.finishedAt ?? item.startedAt, "暂无时间")}</span></p>
        <div><span>信号 <em className={item.signalsCreated ? "positive" : ""}>{item.signalsCreated}</em></span><span>错误 <em className={item.errorsCount ? "negative" : ""}>{item.errorsCount}</em></span><span>耗时 {formatDuration(item.elapsedSeconds)}</span></div>
      </article>)}
    </div> : <div className="recent-scan-empty">暂无扫描记录</div>}
  </aside>;
}

function scanStatusLabel(status: StrategyScanHistory["status"]): string {
  if (status === "cancelled") return "取消";
  if (status === "failed") return "失败";
  return "完成";
}

function runProgressFromStatus(progress: StrategyRunProgress): StrategyRunResult {
  return {
    strategiesChecked: progress.strategiesChecked,
    symbolsChecked: progress.scannedSymbols,
    signalsCreated: progress.signalsCreated,
    errors: progress.errors.map((error) => `${error.symbol}: ${error.message}`),
    createdSignals: progress.createdSignals
  };
}

function formatDuration(seconds: number): string {
  const normalized = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(normalized / 60);
  const rest = normalized % 60;
  return `00:${String(minutes).padStart(2, "0")}:${String(rest).padStart(2, "0")}`;
}

function StrategyDetailEditor({ strategy, onBack, onSave }: { strategy: Strategy; onBack: () => void; onSave: (strategy: Strategy) => Promise<void> }) {
  const safeStrategy = normalizeEditableStrategy(strategy);
  const [draft, setDraft] = useState(safeStrategy);
  const [blacklistText, setBlacklistText] = useState(safeStrategy.symbolBlacklist.join("\n"));
  const [blacklistExpanded, setBlacklistExpanded] = useState(false);
  const [analysisExpanded, setAnalysisExpanded] = useState(false);
  const [action, setAction] = useState<"save" | null>(null);
  const [error, setError] = useState<string | null>(null);
  const errorLine = useMemo(() => extractStrategyErrorLine(error), [error]);
  const parsedBlacklist = parseSymbolBlacklist(blacklistText);
  const canEdit = !safeStrategy.enabled;

  function updateStructuredConditions(nextConditions: GeneratedStrategyCondition[]) {
    setDraft((current) => ({ ...current, conditions: conditionsFromStructured(nextConditions), runtime: { ...current.runtime, structuredConditions: nextConditions } }));
  }

  function updateConditionParameter(conditionIndex: number, parameterIndex: number, value: string) {
    updateStructuredConditions(draft.runtime.structuredConditions.map((condition, i) => i !== conditionIndex ? condition : { ...condition, parameters: condition.parameters.map((parameter, j) => j === parameterIndex ? value : parameter) }));
  }

  function deleteCondition(index: number) {
    updateStructuredConditions(draft.runtime.structuredConditions.filter((_, i) => i !== index));
  }

  async function handleSave() {
    if (action || !canEdit) return;
    setAction("save");
    setError(null);
    try {
      await onSave({ ...safeStrategy, symbolBlacklist: parsedBlacklist, conditions: conditionsFromStructured(draft.runtime.structuredConditions), schedule: { ...safeStrategy.schedule, intervalSeconds: intervalSecondsForPeriod(safeStrategy.period) }, runtime: { ...safeStrategy.runtime, structuredConditions: draft.runtime.structuredConditions, code: draft.runtime.code } });
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存策略失败");
      setAction(null);
    }
  }

  return <section className="ai-workspace page"><div className="ai-workspace-shell strategy-edit-shell strategy-maintenance-shell">
    <header className="ai-workspace-header"><div className="ai-title-row"><button className="icon-button" disabled={action !== null} onClick={onBack} type="button" aria-label="返回策略中心"><ArrowLeft size={20} /></button><h1>{canEdit ? "查看 / 编辑策略" : "查看策略"}</h1></div><div className="toolbar-actions"><button className="secondary" disabled={action !== null} onClick={onBack} type="button">返回</button><button className="primary" disabled={action !== null || !canEdit} onClick={() => void handleSave()} type="button"><Save size={17} />{action === "save" ? "保存中..." : "保存策略"}</button></div></header>
    {!canEdit ? <div className="strategy-readonly-notice">策略运行中，只能查看。请先在策略中心暂停该策略后再编辑条件、黑名单或 Python 代码。</div> : null}
    <section className="strategy-maintenance-summary">
      <div className="strategy-maintenance-title"><span className="chip">{safeStrategy.source === "ai" ? "AI策略" : "预设策略"}</span><h2>{safeStrategy.name}</h2><p>{safeStrategy.description}</p></div>
      <div className="strategy-maintenance-meta"><span><b>周期</b>{periodLabel(safeStrategy.period)}</span><span><b>评分</b>{safeStrategy.score}</span><span><b>状态</b>{safeStrategy.enabled ? "运行中" : "已暂停"}</span><span><b>定时任务</b>{safeStrategy.schedule.enabled ? "已开启" : "已关闭"}</span><span><b>运行间隔</b>{intervalLabel(safeStrategy.period)}</span><span><b>最近运行</b>{formatDateTime(safeStrategy.schedule.lastRunAt)}</span></div>
    </section>
    <div className="strategy-maintenance-grid">
      <div className="strategy-maintenance-left">
        <EditableStructuredConditions conditions={draft.runtime.structuredConditions} disabled={!canEdit || action !== null} onDelete={deleteCondition} onParameterChange={updateConditionParameter} />
        <SymbolBlacklistEditor expanded={blacklistExpanded} value={blacklistText} parsedSymbols={parsedBlacklist} disabled={!canEdit || action !== null} onChange={setBlacklistText} onToggle={() => setBlacklistExpanded((current) => !current)} />
        <section className="strategy-analysis-compact"><button className="strategy-analysis-toggle" onClick={() => setAnalysisExpanded((current) => !current)} type="button"><BrainCircuit size={16} />AI 分析<span>{analysisExpanded ? "收起" : "展开"}</span></button>{analysisExpanded ? <div className="strategy-analysis-body">{safeStrategy.runtime.aiAnalysis.length ? safeStrategy.runtime.aiAnalysis.map((item, index) => <p key={`${item}-${index}`}>{item}</p>) : <p>暂无 AI 分析内容。</p>}</div> : null}</section>
      </div>
      <section className="strategy-code-panel"><header><div><Code2 size={17} /><strong>Python 代码</strong></div><span>{errorLine ? `第 ${errorLine} 行校验失败` : canEdit ? "可手动编辑，保存时会执行扫描校验" : "运行中策略仅可查看"}</span></header><CodeEditor ariaLabel="策略 Python 代码" disabled={!canEdit || action !== null} errorLine={errorLine} value={draft.runtime.code} onChange={(value) => { setError(null); setDraft((current) => ({ ...current, runtime: { ...current.runtime, code: value } })); }} /></section>
    </div>{error ? <p className="inline-error ai-page-error">{error}</p> : null}
  </div></section>;
}

function SymbolBlacklistEditor({ expanded, value, parsedSymbols, disabled, onChange, onToggle }: { expanded: boolean; value: string; parsedSymbols: string[]; disabled: boolean; onChange: (value: string) => void; onToggle: () => void }) {
  const previewSymbols = parsedSymbols.slice(0, 3);
  return <section className={`strategy-blacklist-editor ${expanded ? "expanded" : ""}`}>
    <button className="strategy-blacklist-summary" disabled={disabled} onClick={onToggle} type="button">
      <div><strong>币种黑名单</strong><span>支持换行、空格或逗号分隔，保存后该策略扫描会跳过这些币种</span></div>
      <div className="strategy-blacklist-chips">{previewSymbols.map((symbol) => <span key={symbol}>{symbol}</span>)}{parsedSymbols.length > previewSymbols.length ? <em>+{parsedSymbols.length - previewSymbols.length}</em> : null}</div>
      <b>{expanded ? "收起" : "编辑"}</b>
    </button>
    {expanded ? <div className="strategy-blacklist-body">
      <textarea disabled={disabled} rows={3} spellCheck={false} value={value} onChange={(event) => onChange(event.target.value)} placeholder={"BTCUSDT\nETHUSDT\nZKUSDT"} />
    </div> : null}
  </section>;
}

function EditableStructuredConditions({ conditions, disabled, onDelete, onParameterChange }: { conditions: GeneratedStrategyCondition[]; disabled: boolean; onDelete: (index: number) => void; onParameterChange: (conditionIndex: number, parameterIndex: number, value: string) => void }) {
  return <div className="ai-editor-preview strategy-edit-preview"><article className="ai-editable-conditions strategy-condition-editor-card"><h4>结构化条件<span>只能修改参数或删除条件</span></h4>
    {conditions.length ? conditions.map((condition, conditionIndex) => { const parameters = Array.isArray(condition.parameters) ? condition.parameters : []; return <div className="ai-editable-condition strategy-editable-condition" key={`editable-${conditionIndex}`}><span>{conditionIndex + 1}</span><div className="strategy-condition-fields"><strong>{condition.title || `条件 ${conditionIndex + 1}`}</strong><p>{condition.description}</p></div><div className="ai-param-editor strategy-param-editor">{parameters.length ? parameters.map((parameter, parameterIndex) => <label key={`editable-${conditionIndex}-${parameterIndex}`}><span>{parameterLabel(parameter, parameterIndex)}</span><ParameterNumberEditor disabled={disabled} parameter={parameter} ariaLabelPrefix={`条件 ${conditionIndex + 1} 参数 ${parameterIndex + 1}`} onChange={(nextParameter) => onParameterChange(conditionIndex, parameterIndex, nextParameter)} /></label>) : <em>该条件没有可编辑参数</em>}</div><button aria-label={`删除条件 ${conditionIndex + 1}`} className="icon-button danger strategy-condition-delete" disabled={disabled} onClick={() => onDelete(conditionIndex)} type="button"><Trash2 size={16} /></button></div>; }) : <p className="ai-preview-empty">暂无结构化条件，请重新生成策略后再编辑参数。</p>}
  </article></div>;
}

function StrategyBuilderPage({ mode, onBack, onGenerateStrategy, onGenerateStrategyFromCode, onSaveGeneratedStrategy }: { mode: BuilderMode; onBack: () => void; onGenerateStrategy: (period: Period, conditions: string[], forceRefresh?: boolean) => Promise<GeneratedStrategy>; onGenerateStrategyFromCode: (period: Period, pythonCode: string) => Promise<GeneratedStrategy>; onSaveGeneratedStrategy: (generated: GeneratedStrategy) => Promise<void> }) {
  const [period, setPeriod] = useState<Period>("1H");
  const [conditions, setConditions] = useState(["前面长期箱体震荡，最近10天振幅小于30%", "最近10根1小时K线，大部分都在MA20上方", "最近1小时放量突破，成交量大于过去24小时均量3倍"]);
  const [pythonCode, setPythonCode] = useState("def check_signal(candles):\n    if candles is None or len(candles) < 2:\n        return False\n    latest = candles[-1]\n    previous = candles[-2]\n    close = latest.get(\"close\") if isinstance(latest, dict) else getattr(latest, \"close\", None)\n    prev_close = previous.get(\"close\") if isinstance(previous, dict) else getattr(previous, \"close\", None)\n    return close is not None and prev_close is not None and close > prev_close");
  const [generated, setGenerated] = useState<GeneratedStrategy | null>(null);
  const [activeTab, setActiveTab] = useState<PreviewTab>("summary");
  const [action, setAction] = useState<BuilderAction>(null);
  const [error, setError] = useState<string | null>(null);
  const errorLine = useMemo(() => extractStrategyErrorLine(error), [error]);
  const inputPanelRef = useRef<HTMLElement | null>(null);
  const validConditions = conditions.map((item) => item.trim()).filter(Boolean);
  const validCode = pythonCode.trim();
  const busy = action !== null;
  const canGenerate = !busy && (mode === "code" ? validCode.length > 0 : validConditions.length > 0);
  const canSave = !busy && Boolean(generated);

  async function handleGenerate(forceRefresh = false) {
    if (!canGenerate) return;
    setAction("generate");
    setError(null);
    try {
      const next = mode === "code"
        ? await onGenerateStrategyFromCode(period, validCode)
        : await onGenerateStrategy(period, validConditions, forceRefresh);
      setGenerated(next);
      setActiveTab("summary");
      inputPanelRef.current?.scrollTo({ top: 0 });
    }
    catch (err) { setError(err instanceof Error ? err.message : "生成失败"); }
    finally { setAction(null); }
  }

  async function handleSave() {
    if (!generated || !canSave) return;
    setAction("save");
    setError(null);
    try { await onSaveGeneratedStrategy(generated); }
    catch (err) { setError(err instanceof Error ? err.message : "保存失败"); setAction(null); }
  }

  function updateGeneratedParameter(conditionIndex: number, parameterIndex: number, value: string) {
    if (!generated) return;
    const nextConditions = generated.structuredConditions.map((condition, i) => i !== conditionIndex ? condition : { ...condition, parameters: condition.parameters.map((parameter, j) => j === parameterIndex ? value : parameter) });
    setGenerated({ ...generated, conditions: conditionsFromStructured(nextConditions), structuredConditions: nextConditions, pythonCode: mode === "code" ? generated.pythonCode : buildPythonCodeFromConditions(nextConditions) });
  }

  return <section className={`ai-workspace page ${mode === "code" ? "ai-code-builder" : ""}`}><div className="ai-workspace-shell">
    <header className="ai-workspace-header"><div className="ai-title-row"><button className="icon-button" disabled={busy} onClick={onBack} type="button" aria-label="返回策略中心"><ArrowLeft size={20} /></button><h1>{mode === "code" ? "粘贴代码生成策略" : "AI 生成策略"}</h1></div></header>
    <div className="ai-stepper" aria-label="生成步骤"><StepBadge index={1} label={mode === "code" ? "粘贴代码" : "输入条件"} active /><StepBadge index={2} label={generated ? "AI 生成结构（预览）" : "AI 生成"} active={Boolean(generated)} /><StepBadge index={3} label="保存策略" active={false} /></div>
    <div className="ai-workspace-grid"><section className="ai-input-panel" ref={inputPanelRef}>
      <div className="ai-section-title"><span>1</span>选择周期</div><label className="ai-field"><select value={period} disabled={busy} onChange={(event) => { setPeriod(event.target.value as Period); setGenerated(null); }}>{periods.map((item) => <option key={item} value={item}>{periodLabel(item)}</option>)}</select></label><p className="ai-field-note">策略将在所选周期 K 线上进行检测</p>
      {mode === "code" ? <>
        <div className="ai-divider" /><div className="ai-section-title"><span>2</span>粘贴 Python 策略代码 <Info size={15} /></div><div className="ai-inline-tip"><Info size={14} /> 大模型只生成名称、条件和分析；保存时会检查代码，但不会改写代码。</div>
        <CodeEditor ariaLabel="粘贴 Python 策略代码" className="ai-paste-code-editor" disabled={busy} errorLine={errorLine} value={pythonCode} onChange={(value) => { setPythonCode(value); setGenerated(null); setError(null); }} />
      </> : <>
        <div className="ai-divider" /><div className="ai-section-title"><span>2</span>输入自然语言条件 <Info size={15} /></div><div className="ai-inline-tip"><Info size={14} /> 请尽量描述清晰具体，AI 将生成结构化策略逻辑</div>
        <div className="ai-condition-list">{conditions.map((condition, index) => <div className="ai-condition-item" key={`condition-${index}`}><GripVertical size={17} /><strong>{index + 1}</strong><input disabled={busy} value={condition} onChange={(event) => setConditions((current) => current.map((item, i) => i === index ? event.target.value : item))} /><button className="icon-button danger" disabled={busy || conditions.length <= 1} onClick={() => setConditions((current) => current.filter((_, i) => i !== index))} type="button"><Trash2 size={16} /></button></div>)}</div>
        <button className="ai-add-condition" disabled={busy} onClick={() => setConditions((current) => [...current, ""])} type="button"><Plus size={16} />添加条件</button>
        <div className="ai-examples"><span>示例条件（点击可快速添加）</span><div>{exampleConditions.map((example) => <button disabled={busy} key={example} onClick={() => setConditions((current) => [...current, example])} type="button">{example}</button>)}</div></div>
      </>}
      <div className="ai-input-actions"><button className="primary" disabled={!canGenerate} onClick={() => void handleGenerate(false)} type="button"><Sparkles size={17} />{action === "generate" ? "生成中..." : mode === "code" ? "解析代码生成策略" : "生成策略"}</button><button className="secondary" disabled={busy} onClick={() => { setGenerated(null); setActiveTab("summary"); setError(null); }} type="button">重置</button></div>
    </section><section className="ai-preview-workbench has-result"><div className="ai-result-preview">
      <header className="ai-result-header"><div><h2>策略预览</h2><span>{generated ? "AI 已生成结构化信息，以下内容可预览" : mode === "code" ? "请先粘贴代码并点击解析" : "请先输入条件并点击生成策略"}</span></div>{generated ? <div className="ai-result-actions"><GenerationBadge generated={generated} /><button className="secondary compact" disabled={busy} onClick={() => void handleGenerate(true)} type="button"><RefreshCw size={15} />重新生成</button></div> : null}</header>
      {generated?.generationSource === "fallback" ? <div className="generation-error">大模型未生效，已使用本地兜底结果。{generated.generationError ? `原因：${generated.generationError}` : "原因：大模型未返回可解析结果。"}</div> : null}
      {generated ? <><nav className="ai-preview-tabs" aria-label="策略预览标签">{[{ key: "summary" as PreviewTab, label: "策略与条件", icon: ListChecks }, { key: "code" as PreviewTab, label: "Python 代码", icon: Code2 }, { key: "analysis" as PreviewTab, label: "AI 分析", icon: BrainCircuit }].map((tab) => { const Icon = tab.icon; return <button className={activeTab === tab.key ? "active" : ""} key={tab.key} onClick={() => setActiveTab(tab.key)} type="button"><Icon size={16} />{tab.label}</button>; })}</nav>{activeTab === "summary" ? <StrategyGeneratedSummary generated={generated} codeLocked={mode === "code"} onParameterChange={updateGeneratedParameter} /> : null}{activeTab === "code" ? <CodeEditor ariaLabel="生成的 Python 代码" errorLine={errorLine} readOnly value={generated.pythonCode} /> : null}{activeTab === "analysis" ? <AnalysisPreview generated={generated} /> : null}</> : <div className="ai-empty-preview"><h2>策略预览</h2><div className="empty-illustration"><div /><Sparkles size={42} /></div><strong>{mode === "code" ? "请先粘贴代码并点击“解析代码生成策略”" : "请先输入条件并点击“生成策略”"}</strong><p>{mode === "code" ? "AI 将读取代码并生成名称、结构化条件和分析，代码会原样保留" : "AI 将自动生成策略总结、结构化条件和信号强度评估"}</p></div>}
    </div></section></div>
    <footer className="ai-workspace-footer"><span><Info size={15} /> 提示：生成的策略仅供参考，请结合实际市场情况进行验证和调整</span><div><button className="secondary" disabled={busy} onClick={onBack} type="button">取消</button><button className="primary" disabled={!canSave} onClick={() => void handleSave()} type="button"><Save size={17} />{action === "save" ? "保存中..." : "保存策略"}</button></div></footer>{error ? <p className="inline-error ai-page-error">{error}</p> : null}
  </div></section>;
}

function CodeEditor({ ariaLabel, className = "", disabled = false, errorLine = null, readOnly = false, value, onChange }: { ariaLabel: string; className?: string; disabled?: boolean; errorLine?: number | null; readOnly?: boolean; value: string; onChange?: (value: string) => void }) {
  const lines = splitCodeLines(value);
  const gutterRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  useEffect(() => {
    if (!errorLine || !textareaRef.current) return;
    const lineHeight = Number.parseFloat(window.getComputedStyle(textareaRef.current).lineHeight) || 22;
    textareaRef.current.scrollTop = Math.max(0, (errorLine - 1) * lineHeight - lineHeight * 3);
    if (gutterRef.current) gutterRef.current.scrollTop = textareaRef.current.scrollTop;
  }, [errorLine]);

  return <div className={`code-editor-shell ${className} ${errorLine ? "has-error-line" : ""}`}>
    <div className="code-editor-gutter" ref={gutterRef} aria-hidden="true">
      {lines.map((_, index) => {
        const lineNumber = index + 1;
        return <span className={lineNumber === errorLine ? "active" : ""} key={`line-${lineNumber}`}>{lineNumber}</span>;
      })}
    </div>
    <textarea
      aria-label={ariaLabel}
      className="code-editor-textarea"
      disabled={disabled}
      readOnly={readOnly}
      ref={textareaRef}
      spellCheck={false}
      value={value}
      onChange={(event) => onChange?.(event.target.value)}
      onScroll={(event) => {
        if (gutterRef.current) gutterRef.current.scrollTop = event.currentTarget.scrollTop;
      }}
    />
  </div>;
}

function StrategyGeneratedSummary({ generated, codeLocked = false, onParameterChange }: { generated: GeneratedStrategy; codeLocked?: boolean; onParameterChange: (conditionIndex: number, parameterIndex: number, value: string) => void }) {
  return <div className="ai-editor-preview"><section className="ai-strategy-identity"><div className="ai-strategy-icon"><TrendingUp size={31} /></div><div><h3>{generated.name || "AI 生成策略"}</h3><p>{generated.description || generated.summary || "大模型未返回策略描述，可保存前重新生成。"}</p></div><span>{generated.signalType || "AI策略"}</span></section><article className="ai-summary-text"><h4>策略总结</h4><p>{generated.summary || "大模型未返回策略总结。"}</p></article><article className="ai-editable-conditions"><h4>结构化条件<span>{codeLocked ? "修改参数只影响说明，不会改写 Python 代码" : "修改参数后会同步更新 Python 代码"}</span></h4>{generated.structuredConditions.length ? generated.structuredConditions.map((condition, conditionIndex) => <div className="ai-editable-condition" key={`${condition.title}-${conditionIndex}`}><span>{conditionIndex + 1}</span><div><strong>{condition.title || `条件 ${conditionIndex + 1}`}</strong><p>{condition.description}</p></div><div className="ai-param-editor">{condition.parameters.length ? condition.parameters.map((parameter, parameterIndex) => <label key={`${condition.title}-${parameterIndex}`}><span>{parameterLabel(parameter, parameterIndex)}</span><ParameterNumberEditor parameter={parameter} ariaLabelPrefix={`条件 ${conditionIndex + 1} 参数 ${parameterIndex + 1}`} onChange={(nextParameter) => onParameterChange(conditionIndex, parameterIndex, nextParameter)} /></label>) : <em>该条件没有可编辑参数</em>}</div></div>) : <p className="ai-preview-empty">大模型未返回结构化条件。</p>}</article></div>;
}

function GenerationBadge({ generated }: { generated: GeneratedStrategy }) {
  if (generated.generationSource === "llm") {
    return <span className="generation-badge llm">大模型生成：{generated.generationModel || "已生效"}</span>;
  }
  return <span className="generation-badge fallback">本地兜底{generated.generationModel ? `：${generated.generationModel}` : ""}</span>;
}

function AnalysisPreview({ generated }: { generated: GeneratedStrategy }) {
  return <div className="ai-analysis-preview"><article className="ai-analysis-card"><h4>策略总结</h4><p>{generated.summary || "大模型未返回总结。"}</p></article><article className="ai-analysis-card"><h4>关键标签</h4><div className="ai-analysis-tags">{(generated.tags.length ? generated.tags : [generated.signalType, generated.strengthGrade].filter(Boolean)).map((tag) => <span key={tag}>{tag}</span>)}</div></article><article className="ai-analysis-card"><h4>完整分析</h4>{(generated.aiAnalysis.length ? generated.aiAnalysis : ["大模型未返回额外分析。", generated.nextStep].filter(Boolean)).map((item, index) => <p key={`${item}-${index}`}>{item}</p>)}</article></div>;
}

function ParameterNumberEditor({ parameter, ariaLabelPrefix, disabled = false, onChange }: { parameter: string; ariaLabelPrefix: string; disabled?: boolean; onChange: (nextParameter: string) => void }) {
  const value = editableParameterValue(parameterValue(parameter));
  const pieces = splitNumberPieces(value);
  if (!pieces.some((piece) => piece.kind === "number")) return <input aria-label={ariaLabelPrefix} disabled={disabled} value={value} onChange={(event) => onChange(mergeParameter(parameter, event.target.value))} />;
  return <div className="ai-number-param">{pieces.map((piece, index) => {
    if (piece.kind === "text") return piece.value ? <span key={`text-${index}`}>{piece.value}</span> : null;
    if (isDerivedNumber(value, piece.numberIndex)) return <span key={`derived-${piece.numberIndex}`}>{piece.value}</span>;
    return <input aria-label={`${ariaLabelPrefix} 数字 ${piece.numberIndex + 1}`} disabled={disabled} inputMode="decimal" key={`number-${piece.numberIndex}`} min="0" step="any" type="number" value={piece.value} onChange={(event) => onChange(mergeParameter(parameter, replaceNumberAt(value, piece.numberIndex, event.target.value)))} />;
  })}</div>;
}

function StepBadge({ index, label, active }: { index: number; label: string; active: boolean }) {
  return <div className={`ai-step ${active ? "active" : ""}`}><span>{index}</span><strong>{label}</strong></div>;
}

function parameterLabel(parameter: string, index: number): string {
  const [label] = parameter.split(/[：:]/);
  const cleaned = label?.trim();
  return cleaned && cleaned !== parameter.trim() ? cleaned : `参数 ${index + 1}`;
}
function parameterValue(parameter: string): string { const parts = parameter.split(/[：:]/); return parts.length > 1 ? parts.slice(1).join(":").trim() : parameter.trim(); }
function editableParameterValue(value: string): string { return value.replace(/(\d+)天\s*\/\s*(\d+)根/g, "$2根"); }
function mergeParameter(parameter: string, value: string): string { const label = parameterLabel(parameter, 0); return label.startsWith("参数 ") ? value : `${label}：${value}`; }
function splitNumberPieces(value: string): Array<{ kind: "text"; value: string } | { kind: "number"; value: string; numberIndex: number }> { const pieces: Array<{ kind: "text"; value: string } | { kind: "number"; value: string; numberIndex: number }> = []; const matcher = /\d+(?:\.\d+)?/g; let lastIndex = 0; let numberIndex = 0; for (const match of value.matchAll(matcher)) { const index = match.index ?? 0; if (index > lastIndex) pieces.push({ kind: "text", value: value.slice(lastIndex, index) }); pieces.push({ kind: "number", value: match[0], numberIndex }); lastIndex = index + match[0].length; numberIndex += 1; } if (lastIndex < value.length) pieces.push({ kind: "text", value: value.slice(lastIndex) }); return pieces; }
function replaceNumberAt(value: string, targetIndex: number, nextNumber: string): string { let numberIndex = 0; return value.replace(/\d+(?:\.\d+)?/g, (match) => { if (numberIndex === targetIndex) { numberIndex += 1; return nextNumber; } numberIndex += 1; return match; }); }
function isDerivedNumber(value: string, numberIndex: number): boolean { return value.includes("/") && numberIndex > 0; }
function conditionsFromStructured(conditions: GeneratedStrategyCondition[]): string[] { return conditions.map((condition) => { const params = (Array.isArray(condition.parameters) ? condition.parameters : []).filter(Boolean).join("，"); return [condition.title, condition.description, params ? `参数：${params}` : ""].filter(Boolean).join(" - "); }); }
function parseSymbolBlacklist(value: string): string[] {
  const seen = new Set<string>();
  return value.split(/[\s,，;；]+/).map((symbol) => symbol.trim().toUpperCase()).filter((symbol) => {
    if (!symbol || seen.has(symbol)) return false;
    seen.add(symbol);
    return true;
  });
}
function normalizeEditableStrategy(strategy: Strategy): Strategy {
  const structuredConditions = Array.isArray(strategy.runtime?.structuredConditions)
    ? strategy.runtime.structuredConditions.map((condition) => ({ ...condition, parameters: Array.isArray(condition.parameters) ? condition.parameters : [] }))
    : [];
  return {
    ...strategy,
    conditions: Array.isArray(strategy.conditions) ? strategy.conditions : [],
    symbolBlacklist: Array.isArray(strategy.symbolBlacklist) ? strategy.symbolBlacklist.map((symbol) => symbol.trim().toUpperCase()).filter(Boolean) : [],
    runtime: {
      language: strategy.runtime?.language ?? "python",
      entrypoint: strategy.runtime?.entrypoint ?? "check_signal",
      code: strategy.runtime?.code ?? "",
      structuredConditions,
      aiAnalysis: Array.isArray(strategy.runtime?.aiAnalysis) ? strategy.runtime.aiAnalysis : [],
      version: strategy.runtime?.version ?? 1
    },
    schedule: {
      enabled: strategy.schedule?.enabled ?? false,
      intervalSeconds: strategy.schedule?.intervalSeconds ?? intervalSecondsForPeriod(strategy.period),
      lastRunAt: strategy.schedule?.lastRunAt ?? null,
      lastStatus: strategy.schedule?.lastStatus ?? "idle",
      lastError: strategy.schedule?.lastError ?? ""
    }
  };
}
function firstNumber(text: string, fallback: number): number { const match = text.match(/(\d+(?:\.\d+)?)/); return match ? Number(match[1]) : fallback; }
function wholeNumber(value: number, fallback: number): number { return Number.isFinite(value) && value > 0 ? Math.max(1, Math.round(value)) : fallback; }
function paramNumber(condition: GeneratedStrategyCondition | undefined, keywords: string[], fallback: number): number { if (!condition) return fallback; const source = condition.parameters.find((parameter) => keywords.some((keyword) => parameter.includes(keyword))) ?? `${condition.description} ${condition.parameters.join(" ")}`; return firstNumber(source, fallback); }
function barCountNumber(condition: GeneratedStrategyCondition | undefined, fallback: number): number { if (!condition) return fallback; const source = `${condition.parameters.join(" ")} ${condition.description}`; const matches = Array.from(source.matchAll(/(\d+(?:\.\d+)?)\s*根/g)); if (!matches.length) return wholeNumber(firstNumber(source, fallback), fallback); return wholeNumber(Number(matches[0][1]), fallback); }
function maPeriodNumber(condition: GeneratedStrategyCondition | undefined, fallback: number): number { if (!condition) return fallback; const source = `${condition.description} ${condition.parameters.join(" ")}`; const match = source.match(/MA\s*(\d+)/i); return match ? wholeNumber(Number(match[1]), fallback) : wholeNumber(paramNumber(condition, ["MA", "均线", "周期"], fallback), fallback); }

function buildPythonCodeFromConditions(conditions: GeneratedStrategyCondition[]): string {
  const joined = conditions.map((condition) => `${condition.title} ${condition.description} ${condition.parameters.join(" ")}`).join(" ");
  const rangeCondition = conditions.find((condition) => /箱体|震荡|振幅|收敛/.test(`${condition.title}${condition.description}`));
  const maCondition = conditions.find((condition) => /MA|均线|站上|多头/.test(`${condition.title}${condition.description}`));
  const volumeCondition = conditions.find((condition) => /量|成交/.test(`${condition.title}${condition.description}`));
  const rangeBars = barCountNumber(rangeCondition, 240);
  const amplitudePercent = rangeCondition ? paramNumber(rangeCondition, ["振幅", "幅度"], 30) : 30;
  const maPeriod = maPeriodNumber(maCondition, 20);
  const maBars = barCountNumber(maCondition, 10);
  const maRatio = maCondition ? paramNumber(maCondition, ["比例", "大部分"], 80) : 80;
  const volumeBars = barCountNumber(volumeCondition, 24);
  const volumeMultiplier = volumeCondition ? paramNumber(volumeCondition, ["倍数", "倍"], 3) : 3;
  const breakoutBars = volumeCondition ? paramNumber(volumeCondition, ["突破周期", "突破", "前高"], 48) : 48;
  const minBars = Math.max(rangeBars, maBars, volumeBars + 1, breakoutBars + 1, maPeriod);
  const maKey = `ma${maPeriod}`;
  return `# Generated from editable strategy parameters.
# Source conditions: ${joined || "empty"}

def get_value(candle, key):
    if isinstance(candle, dict):
        return candle.get(key)
    return getattr(candle, key, None)


def check_signal(candles):
    if candles is None or len(candles) < ${minBars}:
        return False

    range_window = candles[-${rangeBars}:]
    trend_window = candles[-${maBars}:]
    volume_window = candles[-${volumeBars + 1}:]
    breakout_window = candles[-${breakoutBars + 1}:-1]

    highs = [get_value(candle, "high") for candle in range_window]
    lows = [get_value(candle, "low") for candle in range_window]
    closes = [get_value(candle, "close") for candle in trend_window]
    ma_values = [get_value(candle, "${maKey}") for candle in trend_window]
    volumes = [get_value(candle, "volume") for candle in volume_window]
    breakout_highs = [get_value(candle, "high") for candle in breakout_window]
    latest_close = get_value(candles[-1], "close")

    if any(value is None for value in highs + lows + closes + ma_values + volumes + breakout_highs + [latest_close]):
        return False
    if min(lows) <= 0:
        return False

    range_compressed = (max(highs) / min(lows)) <= ${formatPythonNumber(1 + amplitudePercent / 100)}
    above_ma_count = sum(1 for close, ma_value in zip(closes, ma_values) if close > ma_value)
    trend_confirmed = above_ma_count / len(trend_window) >= ${formatPythonNumber(maRatio / 100)}
    average_volume = sum(volumes[:-1]) / max(len(volumes[:-1]), 1)
    volume_breakout = volumes[-1] >= average_volume * ${formatPythonNumber(volumeMultiplier)} if average_volume > 0 else False
    price_breakout = latest_close > max(breakout_highs)

    return range_compressed and trend_confirmed and volume_breakout and price_breakout
`;
}

function formatPythonNumber(value: number): string { return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, "").replace(/\.$/, ""); }
function runtimeStatusLabel(status: Strategy["schedule"]["lastStatus"]): string { const labels: Record<Strategy["schedule"]["lastStatus"], string> = { idle: "未运行", success: "成功", error: "失败" }; return labels[status]; }
function periodLabel(period: Period): string { const labels: Record<Period, string> = { "5M": "5分钟 (5M)", "15M": "15分钟 (15M)", "1H": "1小时 (1H)", "4H": "4小时 (4H)", "1D": "1天 (1D)" }; return labels[period]; }
function intervalSecondsForPeriod(period: Period): number { const seconds: Record<Period, number> = { "5M": 300, "15M": 900, "1H": 3600, "4H": 14400, "1D": 86400 }; return seconds[period]; }
function intervalLabel(period: Period): string { const labels: Record<Period, string> = { "5M": "5分钟", "15M": "15分钟", "1H": "1小时", "4H": "4小时", "1D": "1天" }; return labels[period]; }
