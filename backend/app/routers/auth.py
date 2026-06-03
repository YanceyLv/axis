import sqlite3

from fastapi import APIRouter

from app.errors import ApiError
from app.models import AuthResponse, LoginRequest, RegisterRequest
from app.store import store


router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthResponse)
def register(payload: RegisterRequest) -> AuthResponse:
    try:
        user, token = store.create_user(payload.email, payload.password)
    except sqlite3.IntegrityError:
        raise _duplicate_email_error(payload.email) from None
    except Exception as exc:
        if _is_duplicate_email_error(exc):
            raise _duplicate_email_error(payload.email) from None
        raise

    return AuthResponse(user=user, token=token)


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    auth_result = store.authenticate_user(payload.email, payload.password)
    if auth_result is None:
        raise ApiError(
            status_code=401,
            code="INVALID_CREDENTIALS",
            message="Invalid email or password",
            details={},
        )

    user, token = auth_result
    return AuthResponse(user=user, token=token)


def _duplicate_email_error(email: str) -> ApiError:
    return ApiError(
        status_code=409,
        code="EMAIL_ALREADY_REGISTERED",
        message="Email already registered",
        details={"email": email.strip().lower()},
    )


def _is_duplicate_email_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return "duplicate" in text or "unique" in text
