# Signal Discovery System Design

Date: 2026-05-31

## Goal

Build a high-fidelity, frontend/backend separated MVP for a USDT perpetual futures signal discovery system. The first version should feel like a real product and cover the full flow shown in the reference screens, while using mock market data and mock AI outputs behind stable API boundaries.

## Scope

The MVP covers these screens and flows:

1. Dashboard/home
2. Strategy center list
3. AI strategy generation modal
4. Signal center list
5. Signal detail
6. Watchlist list
7. Watchlist detail
8. Add watch item modal
9. Knowledge case detail

The product targets crypto USDT perpetual futures. Example symbols use pairs such as `ALLUSDT`, `SOLUSDT`, `WIFUSDT`, `PEPEUSDT`, and `DOGEUSDT`.

## Recommended Architecture

Use a two-app workspace:

```text
D:\Axis
  frontend\
  backend\
  docs\
```

### Frontend

Use React, TypeScript, and Vite.

Responsibilities:

- Render the full high-fidelity application shell with sidebar navigation.
- Implement all nine product screens and modal flows.
- Call the Python API through a small typed API client.
- Keep UI state for filters, selected entities, modal steps, generated strategy previews, and optimistic updates.
- Render trading-style tables, KPI cards, K-line panels, strength ratings, and condition status panels.

The frontend should not hardcode business data directly inside page components. Mock data comes from the backend API so the app can later switch to real data without rewriting the UI.

### Backend

Use Python, FastAPI, and Pydantic.

Responsibilities:

- Serve REST APIs for dashboard, strategies, signals, watchlist, and knowledge cases.
- Provide mock store data for the first version.
- Generate deterministic mock AI strategy previews from user inputs.
- Return mock K-line and indicator data for chart panels.
- Preserve API boundaries that can later be backed by exchange market data, strategy scans, and real LLM calls.

The first version should use an in-memory mock store. JSON file persistence can be added if needed, but a database is out of scope for the first build.

## Product Flow

### Dashboard

The dashboard gives the user a quick operating view:

- KPI cards for today's signals, enabled strategies, observed symbols, observation alerts, and running strategies.
- Latest signal table with symbol, strategy, type, score, and time.
- Seven-day signal trend chart.
- Compact recent strategy and watchlist activity panels.

### Strategy Center

The strategy list manages generated and preset strategies:

- Tabs for all strategies, running strategies, and paused strategies.
- Search and filters by strategy name and period.
- Strategy table with name, source, period, enabled state, today's signal count, last trigger time, and actions.
- Users can enable or disable strategies.
- The `AI Generate Strategy` action opens the strategy wizard.

### AI Strategy Generation

The AI generation modal is a three-step flow:

1. Input conditions: period selection and natural language condition list.
2. AI generation: backend returns generated strategy name, description, normalized rules, signal type, and strength grade.
3. Confirm and save: user saves the generated strategy into the strategy list.

The first version uses mock generation, but the API should be shaped as if a real LLM service will replace it:

- `POST /api/strategies/generate`
- `POST /api/strategies`

### Signal Center

The signal list helps users find triggered opportunities:

- Tabs for all signals, trend signals, and watch signals.
- Filters for period, score range, signal type, date range, and symbol/strategy keyword.
- Signal table with time, symbol, strategy, signal type, period, score, and operation.
- Clicking a signal opens the signal detail view.

### Signal Detail

The signal detail page explains why a signal triggered:

- Header with symbol, strategy, watch status, score, and actions.
- K-line and volume panel with mock moving average overlays.
- Period switcher for `1H`, `4H`, and `1D`.
- AI analysis panel listing trigger reasons.
- Signal strength card with grade and confidence bar.
- Action to add the symbol or signal into the watchlist.

### Watchlist

The watchlist tracks symbols and conditions after discovery:

- List page shows symbol, current price, 24H change, number of watch conditions, last trigger time, and actions.
- Detail page shows a K-line panel plus condition rows.
- Each condition has text, status, and last trigger time.

### Add Watch Item

The add watch modal supports:

- Symbol search and selected symbol chips.
- Condition type selection.
- Price, indicator, and breakout condition editing.
- Period selection.
- Notification toggle.
- Review list of added conditions before saving.

### Knowledge Case

The knowledge case detail page explains historical examples:

- Title, symbol, strategy, creation time, and case score.
- Historical K-line image/panel with annotated trigger points.
- AI replay summary.
- Key observations and related strategy link.

## Core Models

### Strategy

Fields:

- `id`
- `name`
- `source`: `preset` or `ai`
- `period`: `1H`, `4H`, or `1D`
- `enabled`
- `conditions`
- `description`
- `score`
- `todaySignalCount`
- `lastTriggeredAt`
- `createdAt`

### Signal

Fields:

- `id`
- `symbol`
- `period`
- `strategyId`
- `strategyName`
- `signalType`
- `score`
- `triggeredAt`
- `price`
- `summary`
- `analysis`
- `strengthGrade`
- `candles`

### WatchItem

Fields:

- `id`
- `symbol`
- `currentPrice`
- `change24h`
- `conditions`
- `lastTriggeredAt`
- `createdAt`

### WatchCondition

Fields:

- `id`
- `type`
- `period`
- `expression`
- `status`: `pending`, `matched`, or `unmatched`
- `lastTriggeredAt`

### KnowledgeCase

Fields:

- `id`
- `title`
- `symbol`
- `strategyId`
- `strategyName`
- `score`
- `createdAt`
- `summary`
- `reasons`
- `lessons`
- `candles`

## API Design

Base path: `/api`.

Dashboard:

- `GET /dashboard/summary`

Strategies:

- `GET /strategies`
- `POST /strategies/generate`
- `POST /strategies`
- `PATCH /strategies/{strategy_id}/enabled`

Signals:

- `GET /signals`
- `GET /signals/{signal_id}`

Watchlist:

- `GET /watchlist`
- `GET /watchlist/{watch_item_id}`
- `POST /watchlist`

Knowledge:

- `GET /knowledge/{case_id}`

## Error Handling

Backend errors should return JSON with:

- `code`
- `message`
- `details`

Frontend should show compact error states for failed API calls and empty states for filters with no results. Because the first version uses mock data, network and validation errors are the main expected failure modes.

## Testing

Backend:

- Use FastAPI test client.
- Verify dashboard summary endpoint.
- Verify strategy generation endpoint.
- Verify strategy save and enabled toggle.
- Verify signal detail and watchlist creation endpoints.

Frontend:

- Run TypeScript/build verification.
- Manually verify the main flows in browser:
  - Dashboard loads.
  - AI strategy can be generated and saved.
  - Saved strategy appears in the list.
  - Signal detail opens from signal list.
  - Signal can be added to watchlist.
  - Watchlist detail and knowledge case detail render.

## Non-Goals For First Version

- Real exchange API integration.
- Real database schema and migrations.
- Authentication and roles.
- Real LLM calls.
- Real trading or order execution.
- Notification delivery.

## Future Extension Points

- Replace mock candle service with Binance/OKX adapters.
- Replace in-memory store with SQLite or Postgres.
- Add a strategy scan scheduler.
- Add real indicator calculations with pandas or a technical analysis library.
- Add OpenAI-powered strategy generation and explanation.
- Add user accounts, saved workspaces, and notification channels.
