export type Period = "5M" | "15M" | "1H" | "4H" | "1D";
export type StrengthGrade = "S" | "A" | "B" | "C";
export type WatchStatus = "pending" | "matched" | "unmatched";

export interface Candle {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  ma5: number;
  ma20: number;
  ma60: number;
}

export interface Strategy {
  id: string;
  name: string;
  source: "preset" | "ai";
  period: Period;
  enabled: boolean;
  conditions: string[];
  description: string;
  score: number;
  todaySignalCount: number;
  lastTriggeredAt: string | null;
  createdAt: string;
  symbolBlacklist: string[];
  runtime: StrategyRuntime;
  schedule: StrategySchedule;
}

export interface StrategyRuntime {
  language: "python";
  entrypoint: string;
  code: string;
  structuredConditions: GeneratedStrategyCondition[];
  aiAnalysis: string[];
  version: number;
}

export interface StrategySchedule {
  enabled: boolean;
  intervalSeconds: number;
  lastRunAt: string | null;
  lastStatus: "idle" | "success" | "error";
  lastError: string;
}

export interface GeneratedStrategy {
  name: string;
  period: Period;
  description: string;
  conditions: string[];
  signalType: string;
  strengthGrade: StrengthGrade;
  score: number;
  summary: string;
  tags: string[];
  structuredConditions: GeneratedStrategyCondition[];
  riskAdvice: {
    stopLoss: string;
    stopLossBuffer: string;
  };
  nextStep: string;
  signalDirection: string;
  expectedHoldingPeriod: string;
  riskLevel: string;
  applicableMarkets: string[];
  triggerFlow: string[];
  pythonCode: string;
  aiAnalysis: string[];
  historyStats: {
    winRate: number | null;
    profitLossRatio: number | null;
    averageHoldingHours: number | null;
  };
  generationSource: "llm" | "fallback";
  generationProvider: string;
  generationModel: string;
  generationBaseUrl: string;
  generationError: string;
  generationCached: boolean;
}

export interface GeneratedStrategyCondition {
  title: string;
  description: string;
  parameters: string[];
}

export interface CreateStrategyPayload {
  name: string;
  period: Period;
  description: string;
  conditions: string[];
  signalType?: string;
  score?: number;
  strengthGrade?: StrengthGrade;
  pythonCode?: string;
  structuredConditions?: GeneratedStrategyCondition[];
  aiAnalysis?: string[];
  scheduleEnabled?: boolean;
  intervalSeconds?: number;
  symbolBlacklist?: string[];
}

export interface UpdateStrategyPayload extends CreateStrategyPayload {
  enabled: boolean;
}

export interface StrategyRunResult {
  strategiesChecked: number;
  symbolsChecked: number;
  signalsCreated: number;
  errors: string[];
  createdSignals: Signal[];
}

export interface StrategyRunError {
  time: string;
  symbol: string;
  errorType: string;
  message: string;
  impact: string;
}

export interface StrategyRunProgress {
  jobId: string;
  running: boolean;
  cancelRequested: boolean;
  startedAt: string | null;
  finishedAt: string | null;
  currentStrategyName: string;
  currentPeriod: Period | null;
  currentSymbol: string;
  strategiesTotal: number;
  strategiesChecked: number;
  totalSymbols: number;
  scannedSymbols: number;
  pendingSymbols: number;
  signalsCreated: number;
  skippedSymbols: number;
  errorsCount: number;
  elapsedSeconds: number;
  estimatedRemainingSeconds: number;
  scanSpeedPerSecond: number;
  errors: StrategyRunError[];
  skipped: StrategyRunError[];
  createdSignals: Signal[];
}

export interface StrategyScanHistory {
  id: string;
  strategyName: string;
  period: Period | null;
  triggerSource: "manual" | "scheduled";
  status: "completed" | "cancelled" | "failed";
  startedAt: string | null;
  finishedAt: string | null;
  elapsedSeconds: number;
  strategiesChecked: number;
  totalSymbols: number;
  scannedSymbols: number;
  signalsCreated: number;
  errorsCount: number;
  skippedSymbols: number;
}

export type NewCoinListingStatus = "discovered" | "upcoming" | "listed";

export interface NewCoinListing {
  id: string;
  symbol: string;
  tradingPairs: string[];
  title: string;
  url: string;
  announcedAt: string | null;
  listedAt: string | null;
  status: NewCoinListingStatus;
  source: "binance";
  notifiedAt: string | null;
  createdAt: string;
  updatedAt: string;
}

export interface NewCoinScanResult {
  fetched: number;
  created: number;
  updated: number;
  notified: number;
  errors: string[];
  listings: NewCoinListing[];
}

export interface MarketRadarEnvironment {
  score: number;
  status: "tradable" | "watch_only" | "avoid";
  label: string;
  summary: string;
  notes: string[];
}

export interface MarketRadarMetrics {
  symbolsAnalyzed: number;
  risingRatio: number;
  volumeExpansionRatio: number;
  strongTrendRatio: number;
  averageVolatility: number;
  majorTrend: string;
}

export type MarketRadarSectionKey = "short_start" | "short_follow" | "trend_72h";

export interface MarketRadarSectionItem {
  symbol: string;
  category: MarketRadarSectionKey;
  score: number;
  periodLabel: string;
  previewCandles: Candle[];
  movePrimary: string;
  moveSecondary: string;
  quoteVolume24h: number;
  volumeRatio: number;
  pullbackFromHighPct: number;
  reason: string;
  riskNote: string;
}

export interface MarketRadarSection {
  key: MarketRadarSectionKey;
  title: string;
  description: string;
  items: MarketRadarSectionItem[];
}

export interface MarketRadarResponse {
  updatedAt: string;
  environment: MarketRadarEnvironment;
  metrics: MarketRadarMetrics;
  opportunityGroups: Record<string, number>;
  sections: MarketRadarSection[];
}

export interface MarketKlineTaskCard {
  name: string;
  status: "running" | "waiting" | "completed" | "warning";
  statusLabel: string;
  phase: string;
  progressCurrent: number | null;
  progressTotal: number | null;
  progressPercent: number | null;
  primaryMetric: string;
  secondaryMetric: string;
  lastRunAt: string | null;
  lastError: string;
}

export interface MarketKlinePeriodProgress {
  period: Period;
  total: number;
  completed: number;
  running: number;
  pending: number;
  failed: number;
  progressPercent: number;
}

export interface MarketKlineCoverage {
  period: Period;
  rows: number;
  symbols: number;
  targetWindow: string;
  earliestOpenTime: string | null;
  latestOpenTime: string | null;
  status: "normal" | "empty";
  statusLabel: string;
}

export interface MarketKlineRunningTask {
  symbol: string;
  period: Period;
  pagesFetched: number;
  storedCandles: number;
  nextStart: string;
  targetEnd: string;
  updatedAt: string;
  lastError: string;
}

export interface MarketKlineFailedTask {
  symbol: string;
  period: Period;
  pagesFetched: number;
  storedCandles: number;
  nextStart: string;
  targetEnd: string;
  updatedAt: string;
  lastError: string;
}

export interface MarketKlineBackfillRetryResponse {
  symbol: string;
  period: Period;
  status: "pending" | "running" | "completed";
  statusLabel: string;
  storedCandles: number;
  pagesFetched: number;
  message: string;
  updatedAt: string;
}

export interface MarketKlineRecentTask {
  type: "backfill" | "incremental" | "cleanup";
  status: string;
  target: string;
  amount: string;
  updatedAt: string | null;
  note: string;
}

export interface MarketKlineStatusResponse {
  updatedAt: string;
  overallStatus: "running" | "waiting" | "completed" | "warning";
  overallStatusLabel: string;
  activePhase: string;
  cards: MarketKlineTaskCard[];
  periodProgress: MarketKlinePeriodProgress[];
  coverage: MarketKlineCoverage[];
  runningTasks: MarketKlineRunningTask[];
  failedTasks: MarketKlineFailedTask[];
  recentTasks: MarketKlineRecentTask[];
  risks: string[];
}

export interface AuthUser {
  id: string;
  email: string;
  createdAt: string;
}

export interface AuthResponse {
  user: AuthUser;
  token: string;
}

export interface AppSettings {
  llm?: {
    provider: string;
    baseUrl: string;
    model: string;
    apiKeySet: boolean;
  };
  api?: {
    provider: string;
    baseUrl: string;
    model?: string;
    apiKeySet: boolean;
  };
  pushover: {
    enabled: boolean;
    userKeySet: boolean;
    appTokenSet: boolean;
  };
}

export interface UpdateSettingsPayload {
  llm: {
    provider: string;
    baseUrl: string;
    model: string;
    apiKey: string;
  };
  pushover: {
    enabled: boolean;
    userKey: string;
    appToken: string;
  };
}

export interface Signal {
  id: string;
  symbol: string;
  period: Period;
  strategyId: string;
  strategyName: string;
  signalType: string;
  score: number;
  triggeredAt: string;
  price: number;
  summary: string;
  analysis: string[];
  strengthGrade: StrengthGrade;
  candles: Candle[];
  performance?: SignalPerformance | null;
}

export interface SignalPerformance {
  id: string;
  signalId: string;
  symbol: string;
  period: Period;
  strategyId: string;
  strategyName: string;
  entryPrice: number;
  status: "tracking" | "completed" | "insufficient_data";
  trackingPeriod: Period;
  change1hPct: number | null;
  change4hPct: number | null;
  change24hPct: number | null;
  maxGainPct: number | null;
  maxDrawdownPct: number | null;
  bestPrice: number | null;
  worstPrice: number | null;
  evaluatedUntil: string | null;
  reviewStatus: "pending" | "generated" | "failed" | "skipped";
  reviewResult: "effective" | "weak" | "failed" | "insufficient_data" | null;
  reviewSummary: string;
  reviewAnalysis: string;
  reviewSuggestions: string[];
  reviewGeneratedAt: string | null;
  reviewSource: "rules" | "llm";
  createdAt: string;
  updatedAt: string;
}

export interface WatchCondition {
  id: string;
  type: string;
  period: Period;
  expression: string;
  status: WatchStatus;
  lastTriggeredAt: string | null;
}

export interface WatchItem {
  id: string;
  symbol: string;
  currentPrice: number;
  change24h: number;
  conditions: WatchCondition[];
  lastTriggeredAt: string | null;
  createdAt: string;
}

export interface CreateWatchItemPayload {
  symbol: string;
  conditions: WatchCondition[];
}

export interface KnowledgeCase {
  id: string;
  title: string;
  symbol: string;
  strategyId: string;
  strategyName: string;
  score: number;
  createdAt: string;
  summary: string;
  reasons: string[];
  lessons: string[];
  candles: Candle[];
}

export interface DashboardSummary {
  todaySignals: number;
  enabledStrategies: number;
  watchSymbols: number;
  observationAlerts: number;
  runningStrategies: number;
  signalTrend: Array<{ date: string; count: number }>;
  latestSignals: Signal[];
  recentStrategies: Strategy[];
  recentWatchlist: WatchItem[];
}
