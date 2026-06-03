from fastapi import APIRouter

from app.models import DashboardSummary
from app.store import store


router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_dashboard_summary() -> DashboardSummary:
    enabled_count = sum(1 for strategy in store.strategies if strategy.enabled)

    return DashboardSummary(
        todaySignals=sum(strategy.todaySignalCount for strategy in store.strategies),
        enabledStrategies=enabled_count,
        watchSymbols=len(store.watchlist),
        observationAlerts=sum(
            1
            for watch_item in store.watchlist
            for condition in watch_item.conditions
            if condition.status == "matched"
        ),
        runningStrategies=enabled_count,
        signalTrend=[
            {"date": "2026-05-27", "count": 2},
            {"date": "2026-05-28", "count": 3},
            {"date": "2026-05-29", "count": 4},
            {"date": "2026-05-30", "count": 4},
            {"date": "2026-05-31", "count": len(store.signals)},
        ],
        latestSignals=store.signals[:5],
        recentStrategies=store.strategies[:3],
        recentWatchlist=store.watchlist[:3],
    )
