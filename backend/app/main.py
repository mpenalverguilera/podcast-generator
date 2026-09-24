import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.config import get_settings
from app.db import session_scope
from app.logging_setup import configure_logging

configure_logging(get_settings().log_level)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("API started")
    yield


app = FastAPI(title="Personal Podcast Generator", lifespan=lifespan)


@app.get("/health")
def health() -> JSONResponse:
    try:
        with session_scope() as db:
            db.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok"})
    except Exception as exc:  # noqa: BLE001 -- health check must never raise
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)
