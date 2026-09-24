import time

from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.models import Episode
from app.schemas import Usage


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    # No external provider call -- local ffmpeg/pydub work (phase 03). Still
    # gets a pipeline_steps row so every stage is accounted for uniformly.
    start = time.monotonic()
    latency_ms = int((time.monotonic() - start) * 1000)
    return Usage(provider="local", cost_usd=0.0, cost_is_estimate=False, latency_ms=latency_ms)
