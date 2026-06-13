from fastapi import APIRouter, Query

from app.errors import ApiError
from app.models import (
    Candle,
    MarketKlineBackfillRetryRequest,
    MarketKlineBackfillRetryResponse,
    MarketKlineStatusResponse,
    MarketRadarResponse,
    Period,
)
from app.store import MarketKlineBackfillRetryError, store


router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/klines/{symbol}", response_model=list[Candle])
def list_market_klines(symbol: str, period: Period, limit: int | None = Query(default=None, ge=1, le=5000)) -> list[Candle]:
    return store.market_candles_for_symbol_period(symbol, period, limit)


@router.get("/radar", response_model=MarketRadarResponse)
def get_market_radar() -> MarketRadarResponse:
    return store.market_radar()


@router.get("/kline-status", response_model=MarketKlineStatusResponse)
def get_market_kline_status() -> MarketKlineStatusResponse:
    return store.market_kline_status()


@router.post("/kline-backfill/retry", response_model=MarketKlineBackfillRetryResponse)
def retry_market_kline_backfill_task(payload: MarketKlineBackfillRetryRequest) -> MarketKlineBackfillRetryResponse:
    try:
        return store.retry_market_kline_backfill_task(payload.symbol, payload.period)
    except MarketKlineBackfillRetryError as exc:
        raise ApiError(
            status_code=exc.status_code,
            code=exc.code,
            message=exc.message,
            details=exc.details,
        ) from exc
