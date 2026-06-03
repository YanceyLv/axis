from fastapi import APIRouter

from app.errors import ApiError
from app.models import CreateWatchItemRequest, WatchItem
from app.store import store


router = APIRouter(prefix="/api/watchlist", tags=["watchlist"])


@router.get("", response_model=list[WatchItem])
def list_watchlist() -> list[WatchItem]:
    return store.watchlist


@router.get("/{watch_item_id}", response_model=WatchItem)
def get_watch_item(watch_item_id: str) -> WatchItem:
    for watch_item in store.watchlist:
        if watch_item.id == watch_item_id:
            return watch_item

    raise ApiError(
        status_code=404,
        code="WATCH_ITEM_NOT_FOUND",
        message="Watch item not found",
        details={"watchItemId": watch_item_id},
    )


@router.post("", response_model=WatchItem)
def create_watch_item(payload: CreateWatchItemRequest) -> WatchItem:
    return store.create_watch_item(payload)
