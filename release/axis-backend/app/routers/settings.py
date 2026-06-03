from fastapi import APIRouter

from app.models import AppSettingsResponse, AppSettingsUpdate
from app.store import store


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("", response_model=AppSettingsResponse)
def get_settings() -> AppSettingsResponse:
    return store.get_settings()


@router.put("", response_model=AppSettingsResponse)
def update_settings(payload: AppSettingsUpdate) -> AppSettingsResponse:
    return store.update_settings(payload)
