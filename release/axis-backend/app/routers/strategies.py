from fastapi import APIRouter
from fastapi import Response

from app.errors import ApiError
from app.models import (
    CreateStrategyRequest,
    GeneratedStrategy,
    GenerateStrategyFromCodeRequest,
    GenerateStrategyRequest,
    Strategy,
    StrategyScanHistory,
    StrategyRunProgress,
    StrategyRunResult,
    StrategySchedulerStatus,
    ToggleEnabledRequest,
    UpdateStrategyRequest,
)
from app.store import (
    cancel_strategy_run_job,
    get_strategy_run_job,
    get_strategy_run_history,
    get_strategy_scheduler_status,
    start_strategy_run_job,
    store,
)


router = APIRouter(prefix="/api/strategies", tags=["strategies"])


@router.get("", response_model=list[Strategy])
def list_strategies() -> list[Strategy]:
    return store.strategies


@router.post("/generate", response_model=GeneratedStrategy)
def generate_strategy(payload: GenerateStrategyRequest) -> GeneratedStrategy:
    return store.generate_strategy(payload.period, payload.conditions, payload.forceRefresh)


@router.post("/generate-from-code", response_model=GeneratedStrategy)
def generate_strategy_from_code(payload: GenerateStrategyFromCodeRequest) -> GeneratedStrategy:
    return store.generate_strategy_from_code(payload.period, payload.pythonCode)


@router.post("", response_model=Strategy)
def create_strategy(payload: CreateStrategyRequest) -> Strategy:
    try:
        return store.create_strategy(payload)
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="STRATEGY_VALIDATION_FAILED",
            message=str(exc),
            details={},
        ) from exc


@router.put("/{strategy_id}", response_model=Strategy)
def update_strategy(strategy_id: str, payload: UpdateStrategyRequest) -> Strategy:
    try:
        strategy = store.update_strategy(strategy_id, payload)
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="STRATEGY_VALIDATION_FAILED",
            message=str(exc),
            details={},
        ) from exc
    if strategy is not None:
        return strategy

    raise ApiError(
        status_code=404,
        code="STRATEGY_NOT_FOUND",
        message="Strategy not found",
        details={"strategyId": strategy_id},
    )


@router.delete("/{strategy_id}", status_code=204)
def delete_strategy(strategy_id: str) -> Response:
    try:
        deleted = store.delete_strategy(strategy_id)
    except ValueError as exc:
        raise ApiError(
            status_code=400,
            code="STRATEGY_DELETE_FAILED",
            message=str(exc),
            details={"strategyId": strategy_id},
        ) from exc
    if deleted:
        return Response(status_code=204)

    raise ApiError(
        status_code=404,
        code="STRATEGY_NOT_FOUND",
        message="Strategy not found",
        details={"strategyId": strategy_id},
    )


@router.post("/run-once", response_model=StrategyRunResult)
def run_strategies_once() -> StrategyRunResult:
    return store.run_strategies_once()


@router.post("/run", response_model=StrategyRunProgress)
def start_strategy_run() -> StrategyRunProgress:
    return start_strategy_run_job(store)


@router.get("/run-status", response_model=StrategyRunProgress)
def strategy_run_status() -> StrategyRunProgress:
    return get_strategy_run_job()


@router.get("/run-history", response_model=list[StrategyScanHistory])
def strategy_run_history() -> list[StrategyScanHistory]:
    return get_strategy_run_history(store)


@router.post("/run-cancel", response_model=StrategyRunProgress)
def cancel_strategy_run() -> StrategyRunProgress:
    return cancel_strategy_run_job()


@router.get("/scheduler-status", response_model=StrategySchedulerStatus)
def strategy_scheduler_status() -> StrategySchedulerStatus:
    return get_strategy_scheduler_status()


@router.patch("/{strategy_id}/enabled", response_model=Strategy)
def toggle_strategy_enabled(strategy_id: str, payload: ToggleEnabledRequest) -> Strategy:
    strategy = store.set_strategy_enabled(strategy_id, payload.enabled)
    if strategy is not None:
        return strategy

    raise ApiError(
        status_code=404,
        code="STRATEGY_NOT_FOUND",
        message="Strategy not found",
        details={"strategyId": strategy_id},
    )


@router.patch("/{strategy_id}/schedule-enabled", response_model=Strategy)
def toggle_strategy_schedule_enabled(strategy_id: str, payload: ToggleEnabledRequest) -> Strategy:
    strategy = store.set_strategy_schedule_enabled(strategy_id, payload.enabled)
    if strategy is not None:
        return strategy

    raise ApiError(
        status_code=404,
        code="STRATEGY_NOT_FOUND",
        message="Strategy not found",
        details={"strategyId": strategy_id},
    )
