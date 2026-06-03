export type Period = "1H" | "4H" | "1D";
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
