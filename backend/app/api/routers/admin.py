"""GET /admin/metrics (docs/phases/07-dashboard.md step 2, docs/DECISIONS.md D-52)."""

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app import metrics
from app.api.schemas import (
    AdminMetricsOut,
    DailyCountOut,
    DailyProviderCostOut,
    EpisodesPerDayOut,
    OperationsMetricsOut,
    ProductMetricsOut,
    QualityMetricsOut,
    RatingByPromptVersionOut,
    RetentionCohortOut,
    StageFailureRateOut,
    StageLatencyOut,
    TopicCountOut,
)
from app.auth import admin_user
from app.db import get_db
from app.models import User

router = APIRouter(prefix="/admin", tags=["admin"])

DEFAULT_WINDOW_DAYS = 30


def _default_range() -> tuple[date, date]:
    today = datetime.now(UTC).date()
    return today - timedelta(days=DEFAULT_WINDOW_DAYS - 1), today


@router.get("/metrics", response_model=AdminMetricsOut)
def get_metrics(
    from_: date | None = Query(default=None, alias="from"),
    to: date | None = Query(default=None),
    include_synthetic: bool = Query(default=True),
    _admin: User = Depends(admin_user),
    db: Session = Depends(get_db),
) -> AdminMetricsOut:
    default_from, default_to = _default_range()
    date_from = from_ or default_from
    date_to = to or default_to

    result = metrics.build_metrics(db, date_from, date_to, include_synthetic)
    p, o, q = result.product, result.operations, result.quality
    return AdminMetricsOut(
        date_from=result.date_from,
        date_to=result.date_to,
        include_synthetic=result.include_synthetic,
        product=ProductMetricsOut(
            dau=[DailyCountOut(day=d.day, count=d.count) for d in p.dau],
            wau=[DailyCountOut(day=d.day, count=d.count) for d in p.wau],
            new_users_per_day=[
                DailyCountOut(day=d.day, count=d.count) for d in p.new_users_per_day
            ],
            episodes_per_day=[
                EpisodesPerDayOut(day=d.day, manual=d.manual, scheduled=d.scheduled)
                for d in p.episodes_per_day
            ],
            listen_through_rate=p.listen_through_rate,
            avg_percent_listened=p.avg_percent_listened,
            retention=[
                RetentionCohortOut(
                    cohort_week=r.cohort_week,
                    cohort_size=r.cohort_size,
                    retained=r.retained,
                    retention_rate=r.retention_rate,
                )
                for r in p.retention
            ],
            top_topics=[TopicCountOut(topic=t.topic, count=t.count) for t in p.top_topics],
            rating_ratio=p.rating_ratio,
            focus_request_usage_rate=p.focus_request_usage_rate,
        ),
        operations=OperationsMetricsOut(
            stage_latency=[
                StageLatencyOut(stage=s.stage, p50_ms=s.p50_ms, p95_ms=s.p95_ms)
                for s in o.stage_latency
            ],
            stage_failure_rate=[
                StageFailureRateOut(stage=s.stage, n=s.n, failure_rate=s.failure_rate)
                for s in o.stage_failure_rate
            ],
            cost_per_day_by_provider=[
                DailyProviderCostOut(
                    day=c.day,
                    provider=c.provider,
                    cost_usd=c.cost_usd,
                    cost_is_estimate=c.cost_is_estimate,
                )
                for c in o.cost_per_day_by_provider
            ],
            cost_per_listened_minute=o.cost_per_listened_minute,
            total_spend_usd=o.total_spend_usd,
            total_spend_includes_estimate=o.total_spend_includes_estimate,
        ),
        quality=QualityMetricsOut(
            classifier_eval=q.classifier_eval,
            classifier_eval_date=q.classifier_eval_date,
            grounding_flags_avg_initial=q.grounding_flags_avg_initial,
            grounding_flags_avg_final=q.grounding_flags_avg_final,
            rating_by_prompt_version=[
                RatingByPromptVersionOut(
                    script_prompt_version=r.script_prompt_version,
                    avg_rating=r.avg_rating,
                    n=r.n,
                )
                for r in q.rating_by_prompt_version
            ],
        ),
    )
