from fastapi import APIRouter

from app.errors import ApiError
from app.models import Signal
from app.store import store


router = APIRouter(prefix="/api/signals", tags=["signals"])


@router.get("", response_model=list[Signal])
def list_signals() -> list[Signal]:
    return [
        signal.model_copy(update={"performance": store.performance_for_signal(signal.id)})
        for signal in store.signals
    ]


@router.get("/{signal_id}", response_model=Signal)
def get_signal(signal_id: str) -> Signal:
    for signal in store.signals:
        if signal.id == signal_id:
            return signal.model_copy(
                update={
                    "candles": store.market_candles_for_signal(signal),
                    "performance": store.performance_for_signal(signal.id),
                }
            )

    raise ApiError(
        status_code=404,
        code="SIGNAL_NOT_FOUND",
        message="Signal not found",
        details={"signalId": signal_id},
    )
