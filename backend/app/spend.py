from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Episode, PipelineStep


def daily_spend_usd(db: Session, today: date) -> float:
    """Real spend only: seeded dashboard rows (is_synthetic episodes, phase
    07) never cost anything and must not trip the cap. D-51."""
    total = db.scalar(
        select(func.coalesce(func.sum(PipelineStep.cost_usd), 0))
        .join(Episode, Episode.id == PipelineStep.episode_id)
        .where(func.date(PipelineStep.started_at) == today, Episode.is_synthetic.is_(False))
    )
    return float(total or 0.0)
