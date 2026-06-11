from fastapi import APIRouter

from app.models import Candle, MarketKlineStatusResponse, MarketRadarResponse, Period
from app.store import store


router = APIRouter(prefix="/api/market", tags=["market"])


@router.get("/klines/{symbol}", response_model=list[Candle])
def list_market_klines(symbol: str, period: Period) -> list[Candle]:
    return store.market_candles_for_symbol_period(symbol, period)


@router.get("/radar", response_model=MarketRadarResponse)
def get_market_radar() -> MarketRadarResponse:
    return store.market_radar()


@router.get("/kline-status", response_model=MarketKlineStatusResponse)
def get_market_kline_status() -> MarketKlineStatusResponse:
    return store.market_kline_status()
