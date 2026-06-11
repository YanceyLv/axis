# Market Radar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Market Radar page that judges whether the current market supports short-term trading before recommending symbols to watch.

**Architecture:** The backend exposes `GET /api/market/radar`, computed from existing MySQL `market_klines` data without adding tables. The frontend adds a `market-radar` view using the existing app shell, fetch helper, and styling system.

**Tech Stack:** FastAPI, Pydantic, MySQL, React, TypeScript, Vite, lucide-react.

---

### Task 1: Backend Radar API

**Files:**
- Modify: `backend/app/models.py`
- Modify: `backend/app/store.py`
- Modify: `backend/app/routers/market.py`
- Test: `backend/tests/test_api.py`

- [ ] Add Pydantic models for market radar response: environment, metrics, recommendations, and opportunity groups.
- [ ] Add a store method that reads recent `1H` and `15M` candles per symbol from `market_klines`.
- [ ] Compute market score from breadth, volume expansion, trend participation, and volatility.
- [ ] Compute recommended symbols only from existing database candles.
- [ ] Expose `GET /api/market/radar`.
- [ ] Test that radar returns environment status and ranked recommendations from seeded K-line data.

### Task 2: Frontend Types And API

**Files:**
- Modify: `frontend/src/types.ts`
- Modify: `frontend/src/api.ts`

- [ ] Add TypeScript interfaces matching backend radar response.
- [ ] Add `api.marketRadar()` using `GET /api/market/radar`.

### Task 3: Market Radar Page

**Files:**
- Modify: `frontend/src/components/AppShell.tsx`
- Modify: `frontend/src/App.tsx`
- Create: `frontend/src/pages/MarketRadar.tsx`
- Modify: `frontend/src/styles.css`

- [ ] Add `market-radar` navigation item.
- [ ] Add page state loading and refresh behavior.
- [ ] Render market environment, recommendation table, opportunity distribution, and focus cards.
- [ ] Keep page dense, operational, and consistent with the existing app.

### Task 4: Verification And Progress

**Files:**
- Modify: `PROJECT_PROGRESS.md`

- [ ] Run backend focused tests.
- [ ] Run full backend tests.
- [ ] Run frontend build.
- [ ] Update project progress with modified files, verification commands, and risks.
