import logging

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.db import session_scope

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")

app = FastAPI(title="Personal Podcast Generator")


@app.get("/health")
def health() -> JSONResponse:
    try:
        with session_scope() as db:
            db.execute(text("SELECT 1"))
        return JSONResponse({"status": "ok"})
    except Exception as exc:  # noqa: BLE001 -- health check must never raise
        return JSONResponse({"status": "error", "detail": str(exc)}, status_code=503)
