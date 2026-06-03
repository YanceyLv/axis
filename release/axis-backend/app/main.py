from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.errors import ApiError, api_error_handler
from app.routers import auth, dashboard, knowledge, settings, signals, strategies, watchlist
from app.store import start_strategy_scheduler, stop_strategy_scheduler, store


@asynccontextmanager
async def lifespan(_app: FastAPI):
    start_strategy_scheduler(store)
    try:
        yield
    finally:
        stop_strategy_scheduler()


app = FastAPI(lifespan=lifespan)
app.add_exception_handler(ApiError, api_error_handler)


def _cors_origins() -> list[str]:
    defaults = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ]
    configured = [
        origin.strip()
        for origin in os.getenv("CORS_ALLOW_ORIGINS", "").split(",")
        if origin.strip()
    ]
    return [*defaults, *configured]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.middleware("http")
async def require_api_auth(request, call_next):
    if request.method == "OPTIONS":
        return await call_next(request)

    path = request.url.path
    if not path.startswith("/api") or path == "/api/health" or path.startswith("/api/auth/"):
        return await call_next(request)

    authorization = request.headers.get("Authorization", "")
    prefix = "Bearer "
    token = authorization[len(prefix):].strip() if authorization.startswith(prefix) else ""
    if not token or store.user_for_token(token) is None:
        return JSONResponse(
            status_code=401,
            content={"code": "AUTH_REQUIRED", "message": "Authentication required", "details": {}},
        )

    return await call_next(request)


app.include_router(dashboard.router)
app.include_router(auth.router)
app.include_router(settings.router)
app.include_router(strategies.router)
app.include_router(signals.router)
app.include_router(watchlist.router)
app.include_router(knowledge.router)
