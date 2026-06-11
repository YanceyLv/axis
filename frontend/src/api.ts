import type {
  CreateStrategyPayload,
  CreateWatchItemPayload,
  AuthResponse,
  AppSettings,
  Candle,
  DashboardSummary,
  GeneratedStrategy,
  KnowledgeCase,
  MarketKlineStatusResponse,
  MarketRadarResponse,
  NewCoinListing,
  NewCoinScanResult,
  Period,
  Signal,
  Strategy,
  StrategyScanHistory,
  StrategyRunProgress,
  StrategyRunResult,
  UpdateStrategyPayload,
  UpdateSettingsPayload,
  WatchItem
} from "./types";

const jsonHeaders = { "Content-Type": "application/json" };
const authStorageKey = "trendai.auth";
const apiBaseUrl = (import.meta.env.VITE_API_BASE_URL ?? "").replace(/\/$/, "");

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  const token = readAuthToken();
  if (token && !headers.has("Authorization")) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${apiBaseUrl}${url}`, { ...init, headers });
  if (!response.ok) {
    const errorBody = await response.json().catch(() => null) as { message?: string; code?: string } | null;
    throw new Error(errorBody?.message ?? errorBody?.code ?? `API ${response.status}: ${url}`);
  }
  if (response.status === 204) {
    return undefined as T;
  }
  return response.json() as Promise<T>;
}

function readAuthToken(): string | null {
  const raw = window.localStorage.getItem(authStorageKey);
  if (!raw) return null;

  try {
    return (JSON.parse(raw) as { token?: string }).token ?? null;
  } catch {
    window.localStorage.removeItem(authStorageKey);
    return null;
  }
}

function normalizeStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : [];
}

function normalizeStrategy(strategy: Strategy): Strategy {
  const runtime = strategy.runtime ?? {};
  const schedule = strategy.schedule ?? {};
  const structuredConditions = Array.isArray(runtime.structuredConditions)
    ? runtime.structuredConditions.map((condition) => ({
        title: condition?.title ?? "",
        description: condition?.description ?? "",
        parameters: normalizeStringArray(condition?.parameters)
      }))
    : [];

  return {
    ...strategy,
    conditions: normalizeStringArray(strategy.conditions),
    symbolBlacklist: normalizeStringArray(strategy.symbolBlacklist).map((symbol) => symbol.trim().toUpperCase()).filter(Boolean),
    runtime: {
      language: runtime.language ?? "python",
      entrypoint: runtime.entrypoint ?? "check_signal",
      code: runtime.code ?? "",
      structuredConditions,
      aiAnalysis: normalizeStringArray(runtime.aiAnalysis),
      version: runtime.version ?? 1
    },
    schedule: {
      enabled: schedule.enabled ?? false,
      intervalSeconds: schedule.intervalSeconds ?? 3600,
      lastRunAt: schedule.lastRunAt ?? null,
      lastStatus: schedule.lastStatus ?? "idle",
      lastError: schedule.lastError ?? ""
    }
  };
}

export const api = {
  register: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/register", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ email, password })
    }),
  login: (email: string, password: string) =>
    request<AuthResponse>("/api/auth/login", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ email, password })
    }),
  settings: () => request<AppSettings>("/api/settings"),
  updateSettings: (payload: UpdateSettingsPayload) =>
    request<AppSettings>("/api/settings", {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify(payload)
    }),
  dashboard: () => request<DashboardSummary>("/api/dashboard/summary"),
  newCoins: () => request<NewCoinListing[]>("/api/new-coins"),
  scanNewCoins: () =>
    request<NewCoinScanResult>("/api/new-coins/scan", {
      method: "POST",
      headers: jsonHeaders
    }),
  strategies: async () => (await request<Strategy[]>("/api/strategies")).map(normalizeStrategy),
  generateStrategy: (period: Period, conditions: string[], forceRefresh = false) =>
    request<GeneratedStrategy>("/api/strategies/generate", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ period, conditions, forceRefresh })
    }),
  generateStrategyFromCode: (period: Period, pythonCode: string) =>
    request<GeneratedStrategy>("/api/strategies/generate-from-code", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ period, pythonCode })
    }),
  createStrategy: async (payload: CreateStrategyPayload) =>
    normalizeStrategy(await request<Strategy>("/api/strategies", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(payload)
    })),
  updateStrategy: (id: string, payload: UpdateStrategyPayload) =>
    request<Strategy>(`/api/strategies/${id}`, {
      method: "PUT",
      headers: jsonHeaders,
      body: JSON.stringify(payload)
    }).then(normalizeStrategy),
  deleteStrategy: (id: string) =>
    request<void>(`/api/strategies/${id}`, {
      method: "DELETE",
      headers: jsonHeaders
    }),
  runStrategiesOnce: () =>
    request<StrategyRunResult>("/api/strategies/run-once", {
      method: "POST",
      headers: jsonHeaders
    }),
  startStrategyRun: () =>
    request<StrategyRunProgress>("/api/strategies/run", {
      method: "POST",
      headers: jsonHeaders
    }),
  strategyRunStatus: () => request<StrategyRunProgress>("/api/strategies/run-status"),
  strategyRunHistory: () => request<StrategyScanHistory[]>("/api/strategies/run-history"),
  cancelStrategyRun: () =>
    request<StrategyRunProgress>("/api/strategies/run-cancel", {
      method: "POST",
      headers: jsonHeaders
    }),
  setStrategyEnabled: (id: string, enabled: boolean) =>
    request<Strategy>(`/api/strategies/${id}/enabled`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify({ enabled })
    }).then(normalizeStrategy),
  setStrategyScheduleEnabled: (id: string, enabled: boolean) =>
    request<Strategy>(`/api/strategies/${id}/schedule-enabled`, {
      method: "PATCH",
      headers: jsonHeaders,
      body: JSON.stringify({ enabled })
    }).then(normalizeStrategy),
  signals: () => request<Signal[]>("/api/signals"),
  signal: (id: string) => request<Signal>(`/api/signals/${id}`),
  marketKlines: (symbol: string, period: Period) =>
    request<Candle[]>(`/api/market/klines/${encodeURIComponent(symbol)}?period=${encodeURIComponent(period)}`),
  marketKlineStatus: () => request<MarketKlineStatusResponse>("/api/market/kline-status"),
  marketRadar: () => request<MarketRadarResponse>("/api/market/radar"),
  watchlist: () => request<WatchItem[]>("/api/watchlist"),
  watchItem: (id: string) => request<WatchItem>(`/api/watchlist/${id}`),
  createWatchItem: (payload: CreateWatchItemPayload) =>
    request<WatchItem>("/api/watchlist", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify(payload)
    }),
  knowledgeCase: (id: string) => request<KnowledgeCase>(`/api/knowledge/${id}`)
};
