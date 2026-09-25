import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.api.routers import auth, episodes, events, preferences
from app.config import get_settings
from app.db import session_scope
from app.logging_setup import configure_logging
from app.scheduler import recover_stuck_episodes_now, shutdown_scheduler, start_scheduler

configure_logging(get_settings().log_level)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    recovered = recover_stuck_episodes_now()
    if recovered:
        logger.warning("startup recovery: marked %d stuck episode(s) failed", recovered)
    start_scheduler()
    logger.info("API started")
    yield
    shutdown_scheduler()


app = FastAPI(title="Personal Podcast Generator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(preferences.router)
app.include_router(episodes.router)
app.include_router(events.router)


@app.get("/health")
def health() -> JSONResponse:
    try:
        with session_scope() as db:
            db.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok"})
    except Exception as exc:  # noqa: BLE001 -- health check must never raise
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)
