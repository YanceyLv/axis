import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api } from "./api";
import { AppShell, type ViewKey } from "./components/AppShell";
import { AuthPage } from "./pages/AuthPage";
import { Dashboard } from "./pages/Dashboard";
import { KnowledgeCase } from "./pages/KnowledgeCase";
import { MarketDataStatus } from "./pages/MarketDataStatus";
import { MarketRadar } from "./pages/MarketRadar";
import { NewCoins } from "./pages/NewCoins";
import { SignalDetail } from "./pages/SignalDetail";
import { Signals } from "./pages/Signals";
import { Settings } from "./pages/Settings";
import { Strategies } from "./pages/Strategies";
import { WatchDetail } from "./pages/WatchDetail";
import { Watchlist } from "./pages/Watchlist";
import type {
  CreateWatchItemPayload,
  AuthResponse,
  AuthUser,
  AppSettings,
  DashboardSummary,
  GeneratedStrategy,
  KnowledgeCase as KnowledgeCaseType,
  MarketKlineStatusResponse,
  MarketRadarResponse,
  NewCoinListing,
  Period,
  Signal,
  Strategy,
  WatchItem,
  UpdateSettingsPayload
} from "./types";

const AUTH_STORAGE_KEY = "trendai.auth";

function readStoredAuth(): { user: AuthUser; token: string } | null {
  const raw = window.localStorage.getItem(AUTH_STORAGE_KEY);
  if (!raw) return null;

  try {
    return JSON.parse(raw) as { user: AuthUser; token: string };
  } catch {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    return null;
  }
}

export default function App() {
  const [auth, setAuth] = useState<{ user: AuthUser; token: string } | null>(() => readStoredAuth());
  const [view, setView] = useState<ViewKey>("dashboard");
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [signals, setSignals] = useState<Signal[]>([]);
  const [marketKlineStatus, setMarketKlineStatus] = useState<MarketKlineStatusResponse | null>(null);
  const [marketKlineStatusLoading, setMarketKlineStatusLoading] = useState(false);
  const [marketKlineAutoRefresh, setMarketKlineAutoRefresh] = useState(true);
  const [marketRadar, setMarketRadar] = useState<MarketRadarResponse | null>(null);
  const [marketRadarLoading, setMarketRadarLoading] = useState(false);
  const [newCoins, setNewCoins] = useState<NewCoinListing[]>([]);
  const [selectedSignalDetail, setSelectedSignalDetail] = useState<Signal | null>(null);
  const [watchlist, setWatchlist] = useState<WatchItem[]>([]);
  const [knowledgeCase, setKnowledgeCase] = useState<KnowledgeCaseType | null>(null);
  const [settings, setSettings] = useState<AppSettings | null>(null);
  const [selectedSignalId, setSelectedSignalId] = useState("");
  const [selectedWatchId, setSelectedWatchId] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyMessage, setBusyMessage] = useState<string | null>(null);
  const [addingSignalWatchId, setAddingSignalWatchId] = useState<string | null>(null);
  const addingSignalWatchIdsRef = useRef(new Set<string>());

  function handleAuthenticated(nextAuth: AuthResponse) {
    const storedAuth = { user: nextAuth.user, token: nextAuth.token };
    window.localStorage.setItem(AUTH_STORAGE_KEY, JSON.stringify(storedAuth));
    setAuth(storedAuth);
  }

  function handleLogout() {
    window.localStorage.removeItem(AUTH_STORAGE_KEY);
    setAuth(null);
    setView("dashboard");
  }

  const loadInitialData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [dashboardData, strategyData, signalData, newCoinData, watchData] = await Promise.all([
        api.dashboard(),
        api.strategies(),
        api.signals(),
        api.newCoins(),
        api.watchlist()
      ]);
      setDashboard(dashboardData);
      setStrategies(strategyData);
      setSignals(signalData);
      setNewCoins(newCoinData);
      setWatchlist(watchData);
      setKnowledgeCase(null);
    } catch (err) {
      if (err instanceof Error && err.message === "Authentication required") {
        handleLogout();
        return;
      }
      setError(err instanceof Error ? err.message : "加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (auth) void loadInitialData();
  }, [auth, loadInitialData]);

  const selectedSignal = useMemo(
    () => selectedSignalDetail ?? signals.find((signal) => signal.id === selectedSignalId) ?? null,
    [selectedSignalDetail, selectedSignalId, signals]
  );
  const selectedWatch = useMemo(
    () => watchlist.find((item) => item.id === selectedWatchId) ?? null,
    [selectedWatchId, watchlist]
  );
  const selectedWatchCandles = useMemo(() => {
    if (!selectedWatch) return [];
    const watchSymbol = selectedWatch.symbol.toUpperCase();
    const matchingSignal = signals.find((signal) => signal.symbol.toUpperCase() === watchSymbol);
    return matchingSignal?.candles ?? [];
  }, [selectedWatch, signals]);

  const refreshDashboardAndStrategies = useCallback(async () => {
    const [dashboardData, strategyData] = await Promise.all([api.dashboard(), api.strategies()]);
    setDashboard(dashboardData);
    setStrategies(strategyData);
  }, []);

  const refreshDashboardAndWatchlist = useCallback(async () => {
    const [dashboardData, watchData] = await Promise.all([api.dashboard(), api.watchlist()]);
    setDashboard(dashboardData);
    setWatchlist(watchData);
    if (watchData[0]) setSelectedWatchId(watchData[0].id);
  }, []);

  const loadSettings = useCallback(async () => {
    const nextSettings = await api.settings();
    setSettings(nextSettings);
  }, []);

  const saveSettings = useCallback(async (payload: UpdateSettingsPayload) => {
    const nextSettings = await api.updateSettings(payload);
    setSettings(nextSettings);
  }, []);

  async function handleToggleStrategy(id: string, enabled: boolean) {
    setError(null);
    setBusyMessage("正在更新策略状态...");
    try {
      await api.setStrategyEnabled(id, enabled);
      await refreshDashboardAndStrategies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新策略失败");
    } finally {
      setBusyMessage(null);
    }
  }

  async function handleToggleStrategySchedule(id: string, enabled: boolean) {
    setError(null);
    setBusyMessage("正在更新定时任务...");
    try {
      await api.setStrategyScheduleEnabled(id, enabled);
      await refreshDashboardAndStrategies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "更新定时任务失败");
    } finally {
      setBusyMessage(null);
    }
  }

  async function handleGenerateStrategy(period: Period, conditions: string[], forceRefresh = false) {
    return api.generateStrategy(period, conditions, forceRefresh);
  }

  async function handleGenerateStrategyFromCode(period: Period, pythonCode: string) {
    return api.generateStrategyFromCode(period, pythonCode);
  }

  async function handleSaveGeneratedStrategy(generated: GeneratedStrategy) {
    setError(null);
    setBusyMessage("正在保存策略...");
    try {
      await api.createStrategy({
        name: generated.name,
        period: generated.period,
        description: generated.description,
        conditions: generated.conditions,
        signalType: generated.signalType,
        score: generated.score,
        strengthGrade: generated.strengthGrade,
        pythonCode: generated.pythonCode,
        structuredConditions: generated.structuredConditions,
        aiAnalysis: generated.aiAnalysis,
        scheduleEnabled: true,
        intervalSeconds: intervalSecondsForPeriod(generated.period),
        symbolBlacklist: []
      });
      await refreshDashboardAndStrategies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存策略失败");
      throw err;
    } finally {
      setBusyMessage(null);
    }
  }

  async function handleUpdateStrategy(strategy: Strategy) {
    setError(null);
    setBusyMessage("正在保存策略...");
    try {
      await api.updateStrategy(strategy.id, {
        name: strategy.name,
        period: strategy.period,
        description: strategy.description,
        conditions: strategy.conditions,
        signalType: strategy.runtime.entrypoint || "趋势信号",
        score: strategy.score,
        pythonCode: strategy.runtime.code,
        structuredConditions: strategy.runtime.structuredConditions,
        aiAnalysis: strategy.runtime.aiAnalysis,
        scheduleEnabled: strategy.schedule.enabled,
        intervalSeconds: intervalSecondsForPeriod(strategy.period),
        symbolBlacklist: strategy.symbolBlacklist,
        enabled: strategy.enabled
      });
      await refreshDashboardAndStrategies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存策略失败");
      throw err;
    } finally {
      setBusyMessage(null);
    }
  }

  async function handleDeleteStrategy(id: string) {
    setError(null);
    setBusyMessage("正在删除策略...");
    try {
      await api.deleteStrategy(id);
      await refreshDashboardAndStrategies();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除策略失败");
      throw err;
    } finally {
      setBusyMessage(null);
    }
  }

  async function handleRunStrategiesOnce() {
    setError(null);
    setBusyMessage("正在运行策略...");
    try {
      const result = await api.runStrategiesOnce();
      const [, nextSignals] = await Promise.all([
        refreshDashboardAndStrategies(),
        api.signals()
      ]);
      setSignals(nextSignals);
      return result;
    } catch (err) {
      setError(err instanceof Error ? err.message : "运行策略失败");
      throw err;
    } finally {
      setBusyMessage(null);
    }
  }

  async function handleStartStrategyRun() {
    setError(null);
    return api.startStrategyRun();
  }

  async function handleScanNewCoins() {
    const result = await api.scanNewCoins();
    setNewCoins(await api.newCoins());
    return result;
  }

  async function handleRefreshMarketRadar() {
    setMarketRadarLoading(true);
    setError(null);
    try {
      setMarketRadar(await api.marketRadar());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载市场雷达失败");
    } finally {
      setMarketRadarLoading(false);
    }
  }

  const handleRefreshMarketKlineStatus = useCallback(async () => {
    setMarketKlineStatusLoading(true);
    setError(null);
    try {
      setMarketKlineStatus(await api.marketKlineStatus());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载数据采集状态失败");
    } finally {
      setMarketKlineStatusLoading(false);
    }
  }, []);

  async function handleLoadStrategyRunStatus() {
    return api.strategyRunStatus();
  }

  async function handleLoadStrategyRunHistory() {
    return api.strategyRunHistory();
  }

  async function handleCancelStrategyRun() {
    return api.cancelStrategyRun();
  }

  useEffect(() => {
    if (!auth || view !== "market-data" || !marketKlineAutoRefresh) return;
    const timer = window.setInterval(() => {
      void handleRefreshMarketKlineStatus();
    }, 10000);
    return () => window.clearInterval(timer);
  }, [auth, view, marketKlineAutoRefresh, handleRefreshMarketKlineStatus]);

  useEffect(() => {
    if (!auth || view !== "market-radar" || marketRadar || marketRadarLoading) return;
    void handleRefreshMarketRadar();
  }, [auth, view, marketRadar, marketRadarLoading]);

  useEffect(() => {
    if (!auth || view !== "market-data" || marketKlineStatus || marketKlineStatusLoading) return;
    void handleRefreshMarketKlineStatus();
  }, [auth, view, marketKlineStatus, marketKlineStatusLoading, handleRefreshMarketKlineStatus]);

  async function handleStrategyRunFinished() {
    const [, nextSignals] = await Promise.all([
      refreshDashboardAndStrategies(),
      api.signals()
    ]);
    setSignals(nextSignals);
  }

  async function handleCreateWatchItem(payload: CreateWatchItemPayload) {
    setError(null);
    setBusyMessage("正在加入观察池...");
    try {
      await api.createWatchItem(payload);
      await refreshDashboardAndWatchlist();
    } catch (err) {
      setError(err instanceof Error ? err.message : "加入观察失败");
      throw err;
    } finally {
      setBusyMessage(null);
    }
  }

  async function handleAddSignalToWatch(signal: Signal) {
    if (addingSignalWatchIdsRef.current.has(signal.id)) return;
    addingSignalWatchIdsRef.current.add(signal.id);
    setAddingSignalWatchId(signal.id);
    try {
      await handleCreateWatchItem({
        symbol: signal.symbol,
        conditions: [
          {
            id: `signal-${signal.id}`,
            type: "signal",
            period: signal.period,
            expression: `${signal.signalType}: ${signal.summary}`,
            status: "pending",
            lastTriggeredAt: null
          }
        ]
      });
      setView("watchlist");
    } finally {
      addingSignalWatchIdsRef.current.delete(signal.id);
      setAddingSignalWatchId(null);
    }
  }

  async function openSignal(id: string) {
    setSelectedSignalId(id);
    setView("signal-detail");
    setSelectedSignalDetail(signals.find((signal) => signal.id === id) ?? null);
    try {
      const detail = await api.signal(id);
      setSelectedSignalDetail(detail);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载信号详情失败");
    }
  }

  function openWatch(id: string) {
    setSelectedWatchId(id);
    setView("watch-detail");
  }

  function renderView() {
    if (loading) {
      return (
        <section className="page">
          <div className="panel empty-state">正在加载数据...</div>
        </section>
      );
    }

    if (error && !dashboard) {
      return (
        <section className="page">
          <div className="panel empty-state">
            <h1>加载失败</h1>
            <p>{error}</p>
            <button className="primary" onClick={() => void loadInitialData()} type="button">重试</button>
          </div>
        </section>
      );
    }

    switch (view) {
      case "dashboard":
        return dashboard ? <Dashboard dashboard={dashboard} onOpenSignal={openSignal} onOpenWatch={openWatch} /> : null;
      case "market-radar":
        return (
          <MarketRadar
            radar={marketRadar}
            loading={marketRadarLoading}
            onRefresh={handleRefreshMarketRadar}
            onCreateWatchItem={handleCreateWatchItem}
          />
        );
      case "market-data":
        return (
          <MarketDataStatus
            status={marketKlineStatus}
            loading={marketKlineStatusLoading}
            autoRefresh={marketKlineAutoRefresh}
            onRefresh={handleRefreshMarketKlineStatus}
            onToggleAutoRefresh={() => setMarketKlineAutoRefresh((value) => !value)}
          />
        );
      case "strategies":
        return (
          <Strategies
            strategies={strategies}
            onToggleStrategy={handleToggleStrategy}
            onToggleStrategySchedule={handleToggleStrategySchedule}
          onGenerateStrategy={handleGenerateStrategy}
          onGenerateStrategyFromCode={handleGenerateStrategyFromCode}
          onSaveGeneratedStrategy={handleSaveGeneratedStrategy}
            onUpdateStrategy={handleUpdateStrategy}
            onDeleteStrategy={handleDeleteStrategy}
            onRunStrategiesOnce={handleRunStrategiesOnce}
          onStartStrategyRun={handleStartStrategyRun}
          onLoadStrategyRunStatus={handleLoadStrategyRunStatus}
          onLoadStrategyRunHistory={handleLoadStrategyRunHistory}
          onCancelStrategyRun={handleCancelStrategyRun}
            onStrategyRunFinished={handleStrategyRunFinished}
          />
        );
      case "signals":
        return <Signals signals={signals} onOpenSignal={openSignal} />;
      case "new-coins":
        return <NewCoins listings={newCoins} onScan={handleScanNewCoins} />;
      case "signal-detail":
        return (
          <SignalDetail
            signal={selectedSignal}
            isAddingToWatch={selectedSignal ? addingSignalWatchId === selectedSignal.id : false}
            onBack={() => setView("signals")}
            onAddToWatch={handleAddSignalToWatch}
          />
        );
      case "watchlist":
        return <Watchlist watchlist={watchlist} onOpenWatch={openWatch} onCreateWatchItem={handleCreateWatchItem} />;
      case "watch-detail":
        return <WatchDetail item={selectedWatch} candles={selectedWatchCandles} onBack={() => setView("watchlist")} />;
      case "knowledge":
        return knowledgeCase ? <KnowledgeCase knowledgeCase={knowledgeCase} /> : null;
      case "settings":
        return <Settings settings={settings} onLoadSettings={loadSettings} onSaveSettings={saveSettings} />;
      default:
        return null;
    }
  }

  if (!auth) {
    return (
      <AuthPage
        onLogin={api.login}
        onRegister={api.register}
        onAuthenticated={handleAuthenticated}
      />
    );
  }

  return (
    <AppShell activeView={view} onNavigate={setView} userEmail={auth.user.email} onLogout={handleLogout}>
      {error && dashboard ? <div className="app-alert">{error}</div> : null}
      {busyMessage ? <div className="app-busy">{busyMessage}</div> : null}
      {renderView()}
    </AppShell>
  );
}

function intervalSecondsForPeriod(period: Period): number {
  const seconds: Record<Period, number> = {
    "5M": 300,
    "15M": 900,
    "1H": 3600,
    "4H": 14400,
    "1D": 86400
  };
  return seconds[period];
}
