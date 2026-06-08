from typing import Literal

from pydantic import BaseModel, Field


Period = Literal["1H", "4H", "1D"]
StrengthGrade = Literal["S", "A", "B", "C"]
WatchStatus = Literal["pending", "matched", "unmatched"]
GenerationSource = Literal["llm", "fallback"]
NewCoinListingStatus = Literal["discovered", "upcoming", "listed"]


class Candle(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float
    ma5: float
    ma20: float
    ma60: float


class Strategy(BaseModel):
    id: str
    name: str
    source: Literal["preset", "ai"]
    period: Period
    enabled: bool
    conditions: list[str]
    description: str
    score: int = Field(ge=0, le=100)
    todaySignalCount: int
    lastTriggeredAt: str | None
    createdAt: str
    symbolBlacklist: list[str] = Field(default_factory=list)
    runtime: "StrategyRuntime" = Field(default_factory=lambda: StrategyRuntime())
    schedule: "StrategySchedule" = Field(default_factory=lambda: StrategySchedule())


class StrategyRuntime(BaseModel):
    language: Literal["python"] = "python"
    entrypoint: str = "check_signal"
    code: str = ""
    structuredConditions: list["GeneratedStrategyCondition"] = Field(default_factory=list)
    aiAnalysis: list[str] = Field(default_factory=list)
    version: int = 1


class StrategySchedule(BaseModel):
    enabled: bool = True
    intervalSeconds: int = 300
    lastRunAt: str | None = None
    lastStatus: Literal["idle", "success", "error"] = "idle"
    lastError: str = ""


class GeneratedStrategy(BaseModel):
    name: str
    period: Period
    description: str
    conditions: list[str]
    signalType: str
    strengthGrade: StrengthGrade
    score: int = Field(ge=0, le=100)
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    structuredConditions: list["GeneratedStrategyCondition"] = Field(default_factory=list)
    riskAdvice: "GeneratedStrategyRiskAdvice" = Field(default_factory=lambda: GeneratedStrategyRiskAdvice())
    nextStep: str = ""
    signalDirection: str = "做多"
    expectedHoldingPeriod: str = "1~3天"
    riskLevel: str = "中等"
    applicableMarkets: list[str] = Field(default_factory=list)
    triggerFlow: list[str] = Field(default_factory=list)
    pythonCode: str = ""
    aiAnalysis: list[str] = Field(default_factory=list)
    historyStats: "GeneratedStrategyHistoryStats" = Field(default_factory=lambda: GeneratedStrategyHistoryStats())
    generationSource: GenerationSource = "fallback"
    generationProvider: str = ""
    generationModel: str = ""
    generationBaseUrl: str = ""
    generationError: str = ""
    generationCached: bool = False


class GeneratedStrategyCondition(BaseModel):
    title: str
    description: str
    parameters: list[str] = Field(default_factory=list)


class GeneratedStrategyRiskAdvice(BaseModel):
    stopLoss: str = "跌回关键突破位下方"
    stopLossBuffer: str = "3%"


class GeneratedStrategyHistoryStats(BaseModel):
    winRate: int | None = 68
    profitLossRatio: float | None = 2.18
    averageHoldingHours: int | None = 28


class GenerateStrategyRequest(BaseModel):
    period: Period
    conditions: list[str] = Field(min_length=1)
    forceRefresh: bool = False


class GenerateStrategyFromCodeRequest(BaseModel):
    period: Period
    pythonCode: str = Field(min_length=1)


class CreateStrategyRequest(BaseModel):
    name: str
    period: Period
    description: str
    conditions: list[str] = Field(min_length=1)
    signalType: str = "\u8d8b\u52bf\u4fe1\u53f7"
    score: int = Field(default=88, ge=0, le=100)
    strengthGrade: StrengthGrade = "A"
    pythonCode: str = ""
    structuredConditions: list[GeneratedStrategyCondition] = Field(default_factory=list)
    aiAnalysis: list[str] = Field(default_factory=list)
    scheduleEnabled: bool = True
    intervalSeconds: int = Field(default=300, ge=60)
    symbolBlacklist: list[str] = Field(default_factory=list)


class UpdateStrategyRequest(CreateStrategyRequest):
    enabled: bool = True


class ToggleEnabledRequest(BaseModel):
    enabled: bool


class StrategyRunResult(BaseModel):
    strategiesChecked: int
    symbolsChecked: int
    signalsCreated: int
    errors: list[str] = Field(default_factory=list)
    createdSignals: list["Signal"] = Field(default_factory=list)


class StrategyRunError(BaseModel):
    time: str
    symbol: str
    errorType: str
    message: str
    impact: str = "跳过该币种"


class StrategyRunProgress(BaseModel):
    jobId: str
    running: bool = False
    cancelRequested: bool = False
    triggerSource: Literal["manual", "scheduled"] = "manual"
    startedAt: str | None = None
    finishedAt: str | None = None
    currentStrategyName: str = ""
    currentPeriod: Period | None = None
    currentSymbol: str = ""
    strategiesTotal: int = 0
    strategiesChecked: int = 0
    totalSymbols: int = 0
    scannedSymbols: int = 0
    pendingSymbols: int = 0
    signalsCreated: int = 0
    skippedSymbols: int = 0
    errorsCount: int = 0
    elapsedSeconds: float = 0
    estimatedRemainingSeconds: float = 0
    scanSpeedPerSecond: float = 0
    errors: list[StrategyRunError] = Field(default_factory=list)
    skipped: list[StrategyRunError] = Field(default_factory=list)
    createdSignals: list["Signal"] = Field(default_factory=list)


class StrategyScanHistory(BaseModel):
    id: str
    strategyName: str
    period: Period | None = None
    triggerSource: Literal["manual", "scheduled"] = "manual"
    status: Literal["completed", "cancelled", "failed"] = "completed"
    startedAt: str | None = None
    finishedAt: str | None = None
    elapsedSeconds: float = 0
    strategiesChecked: int = 0
    totalSymbols: int = 0
    scannedSymbols: int = 0
    signalsCreated: int = 0
    errorsCount: int = 0
    skippedSymbols: int = 0


class StrategySchedulerStatus(BaseModel):
    running: bool = False
    checkIntervalSeconds: int = 15
    lastCheckedAt: str | None = None
    lastTriggeredAt: str | None = None
    dueStrategies: int = 0
    lastError: str = ""


class NewCoinListing(BaseModel):
    id: str
    symbol: str
    tradingPairs: list[str] = Field(default_factory=list)
    title: str
    url: str
    announcedAt: str | None = None
    listedAt: str | None = None
    status: NewCoinListingStatus = "discovered"
    source: Literal["binance"] = "binance"
    notifiedAt: str | None = None
    createdAt: str
    updatedAt: str


class NewCoinScanResult(BaseModel):
    fetched: int = 0
    created: int = 0
    updated: int = 0
    notified: int = 0
    errors: list[str] = Field(default_factory=list)
    listings: list[NewCoinListing] = Field(default_factory=list)


class NewCoinSchedulerStatus(BaseModel):
    running: bool = False
    checkIntervalSeconds: int = 180
    lastCheckedAt: str | None = None
    lastTriggeredAt: str | None = None
    lastError: str = ""


class AuthUser(BaseModel):
    id: str
    email: str
    createdAt: str


class RegisterRequest(BaseModel):
    email: str
    password: str = Field(min_length=8)


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=1)


class AuthResponse(BaseModel):
    user: AuthUser
    token: str


class LlmSettingsResponse(BaseModel):
    provider: str = "openai"
    baseUrl: str = ""
    model: str = ""
    apiKeySet: bool = False


class PushoverSettingsResponse(BaseModel):
    enabled: bool = False
    userKeySet: bool = False
    appTokenSet: bool = False


class AppSettingsResponse(BaseModel):
    llm: LlmSettingsResponse = Field(default_factory=LlmSettingsResponse)
    pushover: PushoverSettingsResponse = Field(default_factory=PushoverSettingsResponse)


class LlmSettingsUpdate(BaseModel):
    provider: str = "openai"
    baseUrl: str = ""
    model: str = ""
    apiKey: str = ""


class PushoverSettingsUpdate(BaseModel):
    enabled: bool = False
    userKey: str = ""
    appToken: str = ""


class AppSettingsUpdate(BaseModel):
    llm: LlmSettingsUpdate = Field(default_factory=LlmSettingsUpdate)
    pushover: PushoverSettingsUpdate = Field(default_factory=PushoverSettingsUpdate)


class Signal(BaseModel):
    id: str
    symbol: str
    period: Period
    strategyId: str
    strategyName: str
    signalType: str
    score: int = Field(ge=0, le=100)
    triggeredAt: str
    price: float
    summary: str
    analysis: list[str]
    strengthGrade: StrengthGrade
    candles: list[Candle]


class MarketKline(BaseModel):
    id: str
    symbol: str
    period: Period
    openTime: str
    candle: Candle
    createdAt: str
    updatedAt: str


class WatchCondition(BaseModel):
    id: str
    type: str
    period: Period
    expression: str
    status: WatchStatus
    lastTriggeredAt: str | None


class WatchItem(BaseModel):
    id: str
    symbol: str
    currentPrice: float
    change24h: float
    conditions: list[WatchCondition]
    lastTriggeredAt: str | None
    createdAt: str


class CreateWatchItemRequest(BaseModel):
    symbol: str
    conditions: list[WatchCondition] = Field(min_length=1)


class KnowledgeCase(BaseModel):
    id: str
    title: str
    symbol: str
    strategyId: str
    strategyName: str
    score: int
    createdAt: str
    summary: str
    reasons: list[str]
    lessons: list[str]
    candles: list[Candle]


class DashboardSummary(BaseModel):
    todaySignals: int
    enabledStrategies: int
    watchSymbols: int
    observationAlerts: int
    runningStrategies: int
    signalTrend: list[dict[str, int | str]]
    latestSignals: list[Signal]
    recentStrategies: list[Strategy]
    recentWatchlist: list[WatchItem]
