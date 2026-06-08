from fastapi import APIRouter

from app.models import NewCoinListing, NewCoinScanResult, NewCoinSchedulerStatus
from app.store import get_new_coin_scheduler_status, store


router = APIRouter(prefix="/api/new-coins", tags=["new-coins"])


@router.get("", response_model=list[NewCoinListing])
def list_new_coin_listings() -> list[NewCoinListing]:
    return store.new_coin_listings


@router.post("/scan", response_model=NewCoinScanResult)
def scan_new_coin_listings() -> NewCoinScanResult:
    return store.scan_new_coin_listings()


@router.get("/scheduler-status", response_model=NewCoinSchedulerStatus)
def new_coin_scheduler_status() -> NewCoinSchedulerStatus:
    return get_new_coin_scheduler_status()
