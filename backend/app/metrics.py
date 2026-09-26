"""Admin dashboard metrics (docs/phases/07-dashboard.md step 2, docs/DECISIONS.md D-52).

Split in two layers per metric group: a `_fetch_*` function that runs one SQL
query against the date range (`[start, end)`, both UTC) and an
`include_synthetic` filter, and a plain-Python `compute` function that turns
those rows into the numbers the dashboard wants. The compute functions take
plain tuples/lists, not ORM objects, so they can be unit-tested on a tiny
literal fixture with no DB at all; the fetch functions get one DB-backed test
each. `build_metrics` wires both layers together for the API route.
"""

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

# app/metrics.py -> app/ -> backend/ -> repo root -> eval/results (same path-resolution
# pattern as app/config.py's _ENV_FILE).
EVAL_RESULTS_DIR = Path(__file__).resolve().parents[2] / "eval" / "results"

CLASSIFIER_EVAL_FIELDS = [
    "classifier",
    "n",
    "keep_gate_precision",
    "keep_gate_recall",
    "keep_gate_roc_auc",
    "relevance_accuracy",
    "relevance_roc_auc",
    "newsworthy_roc_auc",
    "selection_precision",
    "latency_p50_ms",
    "latency_p95_ms",
    "cost_per_100",
]


def _bounds(date_from: date, date_to: date) -> tuple[datetime, datetime]:
    """[from 00:00, to+1day 00:00) so `to` is an inclusive day, matching the
    date-range picker (7/30/60 days ending today)."""
    start = datetime(date_from.year, date_from.month, date_from.day, tzinfo=UTC)
    end = datetime(date_to.year, date_to.month, date_to.day, tzinfo=UTC) + timedelta(days=1)
    return start, end


def _percentile(values: list[float], pct: float) -> float:
    """Linear-interpolation percentile. Computed in Python (not SQL) because
    both stage_latency and stage_failure_rate are derived from the same one
    fetched row set."""
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = pct * (len(ordered) - 1)
    lo, hi = int(rank), min(int(rank) + 1, len(ordered) - 1)
    frac = rank - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


@dataclass(frozen=True)
class DailyCount:
    day: date
    count: int


@dataclass(frozen=True)
class EpisodesPerDay:
    day: date
    manual: int
    scheduled: int


@dataclass(frozen=True)
class TopicCount:
    topic: str
    count: int


@dataclass(frozen=True)
class RetentionCohort:
    cohort_week: date
    cohort_size: int
    retained: int

    @property
    def retention_rate(self) -> float:
        return self.retained / self.cohort_size if self.cohort_size else 0.0


@dataclass(frozen=True)
class StageLatency:
    stage: str
    p50_ms: float
    p95_ms: float


@dataclass(frozen=True)
class StageFailureRate:
    stage: str
    n: int
    failure_rate: float


@dataclass(frozen=True)
class DailyProviderCost:
    day: date
    provider: str
    cost_usd: float
    cost_is_estimate: bool


@dataclass(frozen=True)
class RatingByPromptVersion:
    script_prompt_version: str | None
    avg_rating: float
    n: int


@dataclass(frozen=True)
class ProductMetrics:
    dau: list[DailyCount]
    wau: list[DailyCount]
    new_users_per_day: list[DailyCount]
    episodes_per_day: list[EpisodesPerDay]
    listen_through_rate: float | None
    avg_percent_listened: float | None
    retention: list[RetentionCohort]
    top_topics: list[TopicCount]
    rating_ratio: float | None
    focus_request_usage_rate: float | None


@dataclass(frozen=True)
class OperationsMetrics:
    stage_latency: list[StageLatency]
    stage_failure_rate: list[StageFailureRate]
    cost_per_day_by_provider: list[DailyProviderCost]
    cost_per_listened_minute: float | None
    total_spend_usd: float
    total_spend_includes_estimate: bool


@dataclass(frozen=True)
class QualityMetrics:
    classifier_eval: list[dict]
    classifier_eval_date: str | None
    grounding_flags_avg_initial: float | None
    grounding_flags_avg_final: float | None
    rating_by_prompt_version: list[RatingByPromptVersion]


@dataclass(frozen=True)
class AdminMetrics:
    date_from: date
    date_to: date
    include_synthetic: bool
    product: ProductMetrics
    operations: OperationsMetrics
    quality: QualityMetrics


# ---------------------------------------------------------------------------
# Product: active users
# ---------------------------------------------------------------------------


def _fetch_event_user_days(
    db: Session, start: datetime, end: datetime, include_synthetic: bool
) -> list[tuple[date, int]]:
    rows = db.execute(
        text(
            """
            SELECT (created_at AT TIME ZONE 'UTC')::date AS day, user_id
            FROM events
            WHERE created_at >= :start AND created_at < :end
              AND (:include_synthetic OR NOT is_synthetic)
            """
        ),
        {"start": start, "end": end, "include_synthetic": include_synthetic},
    ).all()
    return [(row.day, row.user_id) for row in rows]


def active_users_by_day(
    user_days: list[tuple[date, int]], date_from: date, date_to: date
) -> tuple[list[DailyCount], list[DailyCount]]:
    """DAU per day, and WAU per day (trailing 7-day distinct users ending
    that day) -- both derived from the same one fetched row set."""
    by_day: dict[date, set[int]] = {}
    for day, user_id in user_days:
        by_day.setdefault(day, set()).add(user_id)

    days = [date_from + timedelta(days=i) for i in range((date_to - date_from).days + 1)]
    dau = [DailyCount(day=d, count=len(by_day.get(d, set()))) for d in days]
    wau = []
    for d in days:
        window = set()
        for offset in range(7):
            window |= by_day.get(d - timedelta(days=offset), set())
        wau.append(DailyCount(day=d, count=len(window)))
    return dau, wau


# ---------------------------------------------------------------------------
# Product: new users / episodes per day
# ---------------------------------------------------------------------------


def fetch_new_users_per_day(
    db: Session, start: datetime, end: datetime, include_synthetic: bool
) -> list[DailyCount]:
    rows = db.execute(
        text(
            """
            SELECT (created_at AT TIME ZONE 'UTC')::date AS day, COUNT(*) AS n
            FROM users
            WHERE created_at >= :start AND created_at < :end
              AND (:include_synthetic OR NOT is_synthetic)
            GROUP BY day ORDER BY day
            """
        ),
        {"start": start, "end": end, "include_synthetic": include_synthetic},
    ).all()
    return [DailyCount(day=row.day, count=row.n) for row in rows]


def fetch_episodes_per_day(
    db: Session, start: datetime, end: datetime, include_synthetic: bool
) -> list[EpisodesPerDay]:
    rows = db.execute(
        text(
            """
            SELECT (created_at AT TIME ZONE 'UTC')::date AS day,
                   COUNT(*) FILTER (WHERE trigger = 'manual') AS manual,
                   COUNT(*) FILTER (WHERE trigger = 'schedule') AS scheduled
            FROM episodes
            WHERE created_at >= :start AND created_at < :end
              AND (:include_synthetic OR NOT is_synthetic)
            GROUP BY day ORDER BY day
            """
        ),
        {"start": start, "end": end, "include_synthetic": include_synthetic},
    ).all()
    return [EpisodesPerDay(day=row.day, manual=row.manual, scheduled=row.scheduled) for row in rows]


def fetch_focus_request_usage_rate(
    db: Session, start: datetime, end: datetime, include_synthetic: bool
) -> float | None:
    row = db.execute(
        text(
            """
            SELECT COUNT(*) AS total,
                   COUNT(*) FILTER (WHERE focus_request IS NOT NULL) AS with_focus
            FROM episodes
            WHERE created_at >= :start AND created_at < :end AND trigger = 'manual'
              AND (:include_synthetic OR NOT is_synthetic)
            """
        ),
        {"start": start, "end": end, "include_synthetic": include_synthetic},
    ).one()
    return row.with_focus / row.total if row.total else None


# ---------------------------------------------------------------------------
# Product: top topics
# ---------------------------------------------------------------------------


def fetch_top_topics(
    db: Session, start: datetime, end: datetime, include_synthetic: bool, limit: int = 10
) -> list[TopicCount]:
    """Topics of the stories actually selected into an episode (article_scores
    joined through episode_items, not every scored candidate)."""
    rows = db.execute(
        text(
            """
            SELECT a_s.topic AS topic, COUNT(*) AS n
            FROM episode_items ei
            JOIN episodes e ON e.id = ei.episode_id
            JOIN article_scores a_s
              ON a_s.episode_id = ei.episode_id AND a_s.article_id = ei.article_id
            WHERE e.created_at >= :start AND e.created_at < :end
              AND (:include_synthetic OR NOT e.is_synthetic)
              AND a_s.topic IS NOT NULL
            GROUP BY a_s.topic ORDER BY n DESC LIMIT :limit
            """
        ),
        {"start": start, "end": end, "include_synthetic": include_synthetic, "limit": limit},
    ).all()
    return [TopicCount(topic=row.topic, count=row.n) for row in rows]


# ---------------------------------------------------------------------------
# Product: listen-through rate, avg % listened, cost per listened minute
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PlayEvent:
    user_id: int
    episode_id: int
    type: str
    position_s: float | None
    duration_s: float | None


def fetch_play_events(
    db: Session, start: datetime, end: datetime, include_synthetic: bool
) -> list[PlayEvent]:
    rows = db.execute(
        text(
            """
            SELECT ev.user_id, ev.episode_id, ev.type,
                   (ev.payload ->> 'position_s')::float AS position_s, e.duration_s
            FROM events ev JOIN episodes e ON e.id = ev.episode_id
            WHERE ev.type IN ('play_started', 'play_progress', 'play_completed')
              AND ev.created_at >= :start AND ev.created_at < :end
              AND (:include_synthetic OR NOT ev.is_synthetic)
            """
        ),
        {"start": start, "end": end, "include_synthetic": include_synthetic},
    ).all()
    return [
        PlayEvent(row.user_id, row.episode_id, row.type, row.position_s, row.duration_s)
        for row in rows
    ]


def _listen_sessions(play_events: list[PlayEvent]) -> dict[tuple[int, int], dict]:
    """One session per (user, episode): whether it started/completed, and the
    furthest known position (duration_s if completed, else the max reported
    position_s)."""
    sessions: dict[tuple[int, int], dict] = {}
    for ev in play_events:
        key = (ev.user_id, ev.episode_id)
        s = sessions.setdefault(
            key,
            {"started": False, "completed": False, "position_s": 0.0, "duration_s": ev.duration_s},
        )
        if ev.type == "play_started":
            s["started"] = True
        elif ev.type == "play_completed":
            s["completed"] = True
        elif ev.type == "play_progress" and ev.position_s is not None:
            s["position_s"] = max(s["position_s"], ev.position_s)
    return sessions


def listen_through_rate(play_events: list[PlayEvent]) -> float | None:
    sessions = _listen_sessions(play_events).values()
    started = sum(1 for s in sessions if s["started"])
    completed = sum(1 for s in sessions if s["completed"])
    return completed / started if started else None


def avg_percent_listened(play_events: list[PlayEvent]) -> float | None:
    """Average fraction (0-1) of an episode's duration listened to, same
    0-1 scale as every other ratio metric here (listen_through_rate,
    rating_ratio, retention_rate, failure_rate) so the one shared frontend
    formatPercent() -- which multiplies by 100 -- works uniformly. Returning
    a pre-multiplied 0-100 value here was D-52's bug: the dashboard showed
    "7119%" (see D-54)."""
    fractions = []
    for s in _listen_sessions(play_events).values():
        if not s["duration_s"]:
            continue
        position = s["duration_s"] if s["completed"] else s["position_s"]
        fractions.append(min(1.0, position / s["duration_s"]))
    return sum(fractions) / len(fractions) if fractions else None


def total_listened_minutes(play_events: list[PlayEvent]) -> float:
    total_seconds = 0.0
    for s in _listen_sessions(play_events).values():
        if not s["duration_s"]:
            continue
        total_seconds += s["duration_s"] if s["completed"] else s["position_s"]
    return total_seconds / 60


# ---------------------------------------------------------------------------
# Product: rating ratio, rating by prompt version
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RatingRow:
    episode_id: int
    value: int
    script_prompt_version: str | None


def fetch_latest_ratings(
    db: Session, start: datetime, end: datetime, include_synthetic: bool
) -> list[RatingRow]:
    """The latest episode_rated value per (user, episode), joined to the
    episode's script-writer prompt version. Ratings are append-only and a
    value of 0 means "cleared" (excluded)."""
    rows = db.execute(
        text(
            """
            WITH latest AS (
                SELECT DISTINCT ON (ev.user_id, ev.episode_id)
                       ev.episode_id, (ev.payload ->> 'value')::int AS value
                FROM events ev
                WHERE ev.type = 'episode_rated' AND ev.created_at >= :start AND ev.created_at < :end
                  AND (:include_synthetic OR NOT ev.is_synthetic)
                ORDER BY ev.user_id, ev.episode_id, ev.id DESC
            )
            SELECT latest.episode_id, latest.value, e.prompt_versions ->> 'script_writer' AS version
            FROM latest JOIN episodes e ON e.id = latest.episode_id
            WHERE latest.value IN (1, -1) AND (:include_synthetic OR NOT e.is_synthetic)
            """
        ),
        {"start": start, "end": end, "include_synthetic": include_synthetic},
    ).all()
    return [RatingRow(row.episode_id, row.value, row.version) for row in rows]


def rating_ratio(ratings: list[RatingRow]) -> float | None:
    up = sum(1 for r in ratings if r.value == 1)
    down = sum(1 for r in ratings if r.value == -1)
    return up / (up + down) if (up + down) else None


def rating_by_prompt_version(ratings: list[RatingRow]) -> list[RatingByPromptVersion]:
    by_version: dict[str | None, list[int]] = {}
    for r in ratings:
        by_version.setdefault(r.script_prompt_version, []).append(r.value)
    return [
        RatingByPromptVersion(version, sum(values) / len(values), len(values))
        for version, values in sorted(by_version.items(), key=lambda kv: (kv[0] is None, kv[0]))
    ]


# ---------------------------------------------------------------------------
# Product: retention
# ---------------------------------------------------------------------------


def fetch_retention_cohorts(
    db: Session, start: datetime, end: datetime, include_synthetic: bool
) -> list[RetentionCohort]:
    """Weekly signup cohorts, retained = played an episode in week 2 after
    signup (docs/DECISIONS.md D-52). Only cohorts whose week-2 window has
    fully elapsed by `end` are returned -- a cohort still mid-week-2 would
    show a misleadingly low rate."""
    rows = db.execute(
        text(
            """
            WITH cohorts AS (
                SELECT id AS user_id, date_trunc('week', created_at) AS cohort_week
                FROM users
                WHERE created_at >= :start AND created_at < :end
                  AND (:include_synthetic OR NOT is_synthetic)
            ),
            played_week2 AS (
                SELECT DISTINCT ev.user_id
                FROM events ev JOIN cohorts c ON c.user_id = ev.user_id
                WHERE ev.type IN ('play_started', 'play_progress', 'play_completed')
                  AND ev.created_at >= c.cohort_week + interval '7 days'
                  AND ev.created_at < c.cohort_week + interval '14 days'
            )
            SELECT c.cohort_week::date AS cohort_week, COUNT(*) AS cohort_size,
                   COUNT(*) FILTER (WHERE p.user_id IS NOT NULL) AS retained
            FROM cohorts c LEFT JOIN played_week2 p ON p.user_id = c.user_id
            WHERE c.cohort_week + interval '14 days' <= :end
            GROUP BY c.cohort_week ORDER BY c.cohort_week
            """
        ),
        {"start": start, "end": end, "include_synthetic": include_synthetic},
    ).all()
    return [RetentionCohort(row.cohort_week, row.cohort_size, row.retained) for row in rows]


# ---------------------------------------------------------------------------
# Operations: stage latency / failure rate / cost
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StepRow:
    day: date
    stage: str
    status: str
    provider: str
    cost_usd: float | None
    cost_is_estimate: bool
    latency_ms: int | None


def fetch_pipeline_steps(
    db: Session, start: datetime, end: datetime, include_synthetic: bool
) -> list[StepRow]:
    rows = db.execute(
        text(
            """
            SELECT (s.started_at AT TIME ZONE 'UTC')::date AS day, s.stage, s.status, s.provider,
                   s.cost_usd, s.cost_is_estimate, s.latency_ms
            FROM pipeline_steps s JOIN episodes e ON e.id = s.episode_id
            WHERE s.started_at >= :start AND s.started_at < :end
              AND (:include_synthetic OR NOT e.is_synthetic)
            """
        ),
        {"start": start, "end": end, "include_synthetic": include_synthetic},
    ).all()
    return [
        StepRow(
            row.day,
            row.stage,
            row.status,
            row.provider,
            float(row.cost_usd) if row.cost_usd is not None else None,
            row.cost_is_estimate,
            row.latency_ms,
        )
        for row in rows
    ]


def stage_latency(steps: list[StepRow]) -> list[StageLatency]:
    by_stage: dict[str, list[float]] = {}
    for s in steps:
        if s.status == "success" and s.latency_ms is not None:
            by_stage.setdefault(s.stage, []).append(s.latency_ms)
    return [
        StageLatency(stage, _percentile(values, 0.5), _percentile(values, 0.95))
        for stage, values in sorted(by_stage.items())
    ]


def stage_failure_rate(steps: list[StepRow]) -> list[StageFailureRate]:
    by_stage: dict[str, list[str]] = {}
    for s in steps:
        by_stage.setdefault(s.stage, []).append(s.status)
    return [
        StageFailureRate(stage, len(statuses), statuses.count("failed") / len(statuses))
        for stage, statuses in sorted(by_stage.items())
    ]


def cost_per_day_by_provider(steps: list[StepRow]) -> list[DailyProviderCost]:
    by_key: dict[tuple[date, str], list[StepRow]] = {}
    for s in steps:
        if s.cost_usd is not None:
            by_key.setdefault((s.day, s.provider), []).append(s)
    return [
        DailyProviderCost(
            day, provider, sum(s.cost_usd for s in rows), any(s.cost_is_estimate for s in rows)
        )
        for (day, provider), rows in sorted(by_key.items())
    ]


def total_spend(steps: list[StepRow]) -> tuple[float, bool]:
    costs = [s for s in steps if s.cost_usd is not None]
    return sum(s.cost_usd for s in costs), any(s.cost_is_estimate for s in costs)


# ---------------------------------------------------------------------------
# Quality: classifier eval, grounding flags
# ---------------------------------------------------------------------------


def load_latest_classifier_eval(
    results_dir: Path = EVAL_RESULTS_DIR,
) -> tuple[list[dict], str | None]:
    """The most recent dated eval/results/<date>.json (phase 04's classifier
    eval, eval/build_set.py), trimmed to the columns eval/results/latest.md's
    own table shows."""
    candidates = sorted(results_dir.glob("????-??-??.json"), reverse=True)
    if not candidates:
        return [], None
    data = json.loads(candidates[0].read_text())
    rows = [
        {field: row.get(field) for field in CLASSIFIER_EVAL_FIELDS}
        for row in data.get("classifiers", {}).values()
    ]
    return rows, data.get("date")


def fetch_grounding_flag_counts(
    db: Session, start: datetime, end: datetime, include_synthetic: bool
) -> tuple[list[int], list[int]]:
    """Flag counts per scripted episode (grounding_flags_initial is a real
    JSON array), so episodes that failed before scripting don't drag the
    average to 0. `IS NOT NULL` alone doesn't identify those: SQLAlchemy's
    JSON/JSONB type stores a Python None as the JSON scalar `null`, not a SQL
    NULL (none_as_null defaults to False), so an unscripted episode's column
    is "not SQL NULL" while still holding no array -- jsonb_typeof is the
    check that actually works, on both grounding_flags_initial (the WHERE)
    and grounding_flags_final (may itself be JSON null even when initial
    is a real array with zero final flags)."""
    rows = db.execute(
        text(
            """
            SELECT jsonb_array_length(grounding_flags_initial) AS initial_n,
                   CASE WHEN jsonb_typeof(grounding_flags_final) = 'array'
                        THEN jsonb_array_length(grounding_flags_final) ELSE 0 END AS final_n
            FROM episodes
            WHERE created_at >= :start AND created_at < :end
              AND jsonb_typeof(grounding_flags_initial) = 'array'
              AND (:include_synthetic OR NOT is_synthetic)
            """
        ),
        {"start": start, "end": end, "include_synthetic": include_synthetic},
    ).all()
    return [row.initial_n for row in rows], [row.final_n for row in rows]


def _avg(values: list[int]) -> float | None:
    return sum(values) / len(values) if values else None


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def build_metrics(
    db: Session, date_from: date, date_to: date, include_synthetic: bool
) -> AdminMetrics:
    start, end = _bounds(date_from, date_to)

    user_days = _fetch_event_user_days(db, start, end, include_synthetic)
    dau, wau = active_users_by_day(user_days, date_from, date_to)
    play_events = fetch_play_events(db, start, end, include_synthetic)
    ratings = fetch_latest_ratings(db, start, end, include_synthetic)
    steps = fetch_pipeline_steps(db, start, end, include_synthetic)
    spend_usd, spend_is_estimate = total_spend(steps)
    listened_minutes = total_listened_minutes(play_events)
    grounding_initial, grounding_final = fetch_grounding_flag_counts(
        db, start, end, include_synthetic
    )
    eval_rows, eval_date = load_latest_classifier_eval()

    product = ProductMetrics(
        dau=dau,
        wau=wau,
        new_users_per_day=fetch_new_users_per_day(db, start, end, include_synthetic),
        episodes_per_day=fetch_episodes_per_day(db, start, end, include_synthetic),
        listen_through_rate=listen_through_rate(play_events),
        avg_percent_listened=avg_percent_listened(play_events),
        retention=fetch_retention_cohorts(db, start, end, include_synthetic),
        top_topics=fetch_top_topics(db, start, end, include_synthetic),
        rating_ratio=rating_ratio(ratings),
        focus_request_usage_rate=fetch_focus_request_usage_rate(db, start, end, include_synthetic),
    )
    operations = OperationsMetrics(
        stage_latency=stage_latency(steps),
        stage_failure_rate=stage_failure_rate(steps),
        cost_per_day_by_provider=cost_per_day_by_provider(steps),
        cost_per_listened_minute=(spend_usd / listened_minutes if listened_minutes else None),
        total_spend_usd=spend_usd,
        total_spend_includes_estimate=spend_is_estimate,
    )
    quality = QualityMetrics(
        classifier_eval=eval_rows,
        classifier_eval_date=eval_date,
        grounding_flags_avg_initial=_avg(grounding_initial),
        grounding_flags_avg_final=_avg(grounding_final),
        rating_by_prompt_version=rating_by_prompt_version(ratings),
    )
    return AdminMetrics(
        date_from=date_from,
        date_to=date_to,
        include_synthetic=include_synthetic,
        product=product,
        operations=operations,
        quality=quality,
    )
