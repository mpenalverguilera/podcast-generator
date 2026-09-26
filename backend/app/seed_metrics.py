"""Synthetic dashboard data (docs/phases/07-dashboard.md step 1, docs/DECISIONS.md D-51).

Seeds `is_synthetic=true` users, preferences, episodes, pipeline_steps and
events so every phase-07 metric has something to show. Each row has the
shape the real app writes: event payloads match what the player and API
emit (`EventCreate`, `generate_clicked`), and a failed stage is recorded the
way the runner records one (provider "unknown", no cost). Stage latencies and
costs are drawn around the medians of our real `pipeline_steps`.

`build_dataset` is pure: given the rng, the window and the baselines, it
returns the same rows every time. `write_dataset` and `delete_seeded` are the
only functions that touch the DB. Seeded users are recognized by their email
domain, not by `is_synthetic`, because the phase-04 eval user is also
synthetic and owns real eval episodes that a reset must keep.
"""

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from sqlalchemy import delete, insert, select, text
from sqlalchemy.orm import Session

from app.config import Settings
from app.models import (
    ArticleScore,
    Episode,
    EpisodeItem,
    EpisodeStatus,
    EpisodeTrigger,
    Event,
    PipelineStep,
    Preferences,
    StepStatus,
    User,
)
from app.pipeline import STAGE_ORDER
from app.schemas import Topic

SEED_EMAIL_DOMAIN = "synthetic.invalid"

# The runner's stages in order. "grounding" isn't one of them: scripting
# writes that row itself, right after its own (D-30).
RUNNER_STAGES = [status.value for status, _ in STAGE_ORDER]
# Per-stage failure chance; the rest fail at 0.5%. Real failures cluster in
# the two stages that call a flaky provider at volume (Exa search, ElevenLabs).
FAIL_PROB = {"fetching": 0.03, "voicing": 0.04}
DEFAULT_FAIL_PROB = 0.005
FAIL_ERRORS = {
    "fetching": ["Exa search failed: 502 Bad Gateway", "Exa search timed out after 30s"],
    "voicing": [
        "ElevenLabs 429: too_many_concurrent_requests",
        "ElevenLabs 500: internal server error",
    ],
}
DEFAULT_FAIL_ERROR = "OpenAI request timed out"
# Stages whose work grows with the episode length (script size, characters voiced).
LENGTH_SCALED = {"scripting", "grounding", "voicing", "assembling"}
SPREAD_SIGMA = 0.35

TOPIC_POOL = [
    ("AI & machine learning", 10),
    ("Startups & venture capital", 6),
    ("Global politics", 6),
    ("Climate & energy", 5),
    ("Consumer tech", 5),
    ("Personal finance", 4),
    ("Health & medicine", 4),
    ("Football", 4),
    ("Space exploration", 3),
    ("Cybersecurity", 3),
    ("Formula 1", 3),
    ("Science", 3),
    ("Crypto", 2),
    ("Gaming", 2),
]
FOCUS_POOL = [
    "the latest on the EU AI Act",
    "anything new on interest rates",
    "what happened at the weekend's race",
    "follow-up on the chip export rules",
    "recent funding rounds in climate tech",
    "the newest model releases",
    "yesterday's election results",
    "big security breaches this week",
]
TARGET_MINUTES = [(3, 2), (5, 3), (6, 5), (8, 2), (10, 1)]


@dataclass(frozen=True)
class Baseline:
    """Typical numbers for one stage's SUCCESS row."""

    latency_ms: float
    cost_usd: float
    units_in: float
    units_out: float
    provider: str
    model: str | None
    cost_is_estimate: bool


def fallback_baselines(settings: Settings) -> dict[str, Baseline]:
    """Medians of our real runs as of phase 07 (2026-09-26), for a DB with
    no real pipeline_steps yet."""
    s = settings
    return {
        "planning": Baseline(4828, 0.000207, 656, 284, "openai", s.model_planner, False),
        "fetching": Baseline(6906, 0.056, 54, 0, "exa", None, False),
        "ranking": Baseline(2633, 0.01083, 90591, 3358, "openai", s.model_classifier, False),
        "extracting": Baseline(672, 0.0045, 5, 0, "exa", None, False),
        "scripting": Baseline(46944, 0.050208, 8254, 3431, "openai", s.model_script, False),
        "grounding": Baseline(17514, 0.002153, 13175, 1638, "openai", s.model_grounding, False),
        "voicing": Baseline(126016, 0.63151, 5741, 0, "elevenlabs", s.elevenlabs_model, True),
        "assembling": Baseline(7266, 0.0, 0, 0, "local", None, False),
    }


def load_baselines(db: Session, settings: Settings) -> dict[str, Baseline]:
    """Per-stage medians and the most common provider/model from real
    SUCCESS rows (not synthetic, not fake adapters); stages with no real
    rows keep the fallback numbers."""
    rows = db.execute(
        text(
            """
            SELECT s.stage,
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY s.latency_ms),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY s.cost_usd),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY s.units_in),
                   percentile_cont(0.5) WITHIN GROUP (ORDER BY s.units_out),
                   mode() WITHIN GROUP (ORDER BY s.provider),
                   mode() WITHIN GROUP (ORDER BY s.model),
                   bool_or(s.cost_is_estimate)
            FROM pipeline_steps s JOIN episodes e ON e.id = s.episode_id
            WHERE s.status = 'success' AND s.provider <> 'fake' AND NOT e.is_synthetic
            GROUP BY s.stage
            """
        )
    ).all()
    baselines = fallback_baselines(settings)
    for stage, latency, cost, units_in, units_out, provider, model, estimate in rows:
        if stage in baselines:
            baselines[stage] = Baseline(
                float(latency or 0),
                float(cost or 0),
                float(units_in or 0),
                float(units_out or 0),
                provider,
                model,
                bool(estimate),
            )
    return baselines


@dataclass
class SeedEpisode:
    episode: dict
    steps: list[dict] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)


@dataclass
class SeedUser:
    user: dict
    preferences: dict
    episodes: list[SeedEpisode] = field(default_factory=list)
    # Events not tied to an episode (logins).
    events: list[dict] = field(default_factory=list)


def _weighted_sample(rng: random.Random, pool: list[tuple[str, int]], k: int) -> list[str]:
    names, weights = [n for n, _ in pool], [w for _, w in pool]
    picked: list[str] = []
    while len(picked) < k:
        name = rng.choices(names, weights)[0]
        if name not in picked:
            picked.append(name)
    return picked


def _spread(rng: random.Random) -> float:
    return rng.lognormvariate(0, SPREAD_SIGMA)


def _grounding_flags(rng: random.Random, count: int) -> list[dict]:
    return [
        {
            "section_index": rng.randint(1, 6),
            "turn_index": rng.randint(0, 8),
            "claim": "(synthetic) claim not found in the sources",
            "reason": "synthetic seed data",
            "suggested_fix": "synthetic seed data",
        }
        for _ in range(count)
    ]


def _simulate_episode(
    rng: random.Random,
    baselines: dict[str, Baseline],
    created_at: datetime,
    trigger: EpisodeTrigger,
    focus: str | None,
    target_minutes: int,
    lead_topic: str,
) -> SeedEpisode:
    """Walks the runner's stages. A failure stops the run, as in the runner:
    a FAILED row for that stage and nothing after it."""
    scale = target_minutes / 6
    cursor = created_at
    steps: list[dict] = []
    failed_stage: str | None = None
    error: str | None = None
    for stage in RUNNER_STAGES:
        base = baselines[stage]
        if rng.random() < FAIL_PROB.get(stage, DEFAULT_FAIL_PROB):
            failed_stage = stage
            error = rng.choice(FAIL_ERRORS.get(stage, [DEFAULT_FAIL_ERROR]))
            latency = int(base.latency_ms * rng.uniform(0.1, 1.0))
            steps.append(
                {
                    "stage": stage,
                    "status": StepStatus.FAILED,
                    "provider": "unknown",
                    "model": None,
                    "units_in": None,
                    "units_out": None,
                    "cost_usd": None,
                    "cost_is_estimate": False,
                    "latency_ms": latency,
                    "started_at": cursor,
                    "finished_at": cursor + timedelta(milliseconds=latency),
                    "error": error,
                }
            )
            cursor += timedelta(milliseconds=latency)
            break
        for row_stage in [stage, "grounding"] if stage == "scripting" else [stage]:
            b = baselines[row_stage]
            factor = _spread(rng) * (scale if row_stage in LENGTH_SCALED else 1)
            latency = int(b.latency_ms * factor)
            units_in = int(b.units_in * factor)
            steps.append(
                {
                    "stage": row_stage,
                    "status": StepStatus.SUCCESS,
                    "provider": b.provider,
                    "model": b.model,
                    "units_in": units_in,
                    "units_out": int(b.units_out * factor),
                    "cost_usd": round(b.cost_usd * factor, 6),
                    "cost_is_estimate": b.cost_is_estimate,
                    "latency_ms": latency,
                    "started_at": cursor,
                    "finished_at": cursor + timedelta(milliseconds=latency),
                    "error": None,
                }
            )
            cursor += timedelta(milliseconds=latency)

    reached = RUNNER_STAGES.index(failed_stage) if failed_stage else len(RUNNER_STAGES)
    scripted = reached > RUNNER_STAGES.index("scripting")
    prompt_versions = None
    if reached > 0:
        prompt_versions = {"query_planner": 1, **({"script_writer": 1} if scripted else {})}
    initial = final = None
    if scripted:
        n_initial = min(int(rng.expovariate(1 / 5)), 15)
        n_final = sum(rng.random() < 0.35 for _ in range(n_initial))
        initial, final = _grounding_flags(rng, n_initial), _grounding_flags(rng, n_final)

    ready = failed_stage is None
    episode = {
        "status": EpisodeStatus.READY if ready else EpisodeStatus.FAILED,
        "failed_stage": failed_stage,
        "error": error,
        "trigger": trigger,
        "focus_request": focus,
        "window_start": created_at - timedelta(days=1),
        "target_minutes": target_minutes,
        "prompt_versions": prompt_versions,
        "grounding_flags_initial": initial,
        "grounding_flags_final": final,
        "title": f"{lead_topic} and more: your {created_at:%A} briefing" if scripted else None,
        "summary": "Synthetic episode (seed-metrics)." if scripted else None,
        "duration_s": round(target_minutes * 60 * rng.gauss(1, 0.1), 1) if ready else None,
        "is_synthetic": True,
        "created_at": created_at,
        "ready_at": cursor if ready else None,
    }
    return SeedEpisode(episode=episode, steps=steps)


def _event(type_: str, at: datetime, payload: dict | None = None) -> dict:
    return {"type": type_, "payload": payload, "is_synthetic": True, "created_at": at}


def _simulate_play(rng: random.Random, seed_episode: SeedEpisode, play_at: datetime) -> list[dict]:
    """The player's telemetry for one listen: play_started, play_progress
    about every 60s of audio (the real player ticks every 15s; metrics only
    read the furthest position), then play_completed or a last progress at
    the stop point; sometimes a rating."""
    duration = seed_episode.episode["duration_s"]
    fraction = 1.0 if rng.random() < 0.45 else rng.betavariate(2, 2)
    listened = duration * fraction
    events = [_event("play_started", play_at)]
    position = 60
    while position < listened:
        events.append(
            _event("play_progress", play_at + timedelta(seconds=position), {"position_s": position})
        )
        position += 60
    end = play_at + timedelta(seconds=listened)
    if fraction >= 1.0:
        events.append(_event("play_completed", end))
    else:
        events.append(_event("play_progress", end, {"position_s": math.floor(listened)}))
    if rng.random() < 0.3:
        value = 1 if rng.random() < 0.6 + 0.3 * fraction else -1
        events.append(_event("episode_rated", end + timedelta(seconds=10), {"value": value}))
    return events


def _simulate_user(
    rng: random.Random,
    index: int,
    start: datetime,
    end: datetime,
    signup: datetime,
    baselines: dict[str, Baseline],
    settings: Settings,
    password_hash: str,
) -> SeedUser:
    engagement = rng.betavariate(2, 2)
    scheduled = rng.random() < 0.5
    churn_at = (
        signup + timedelta(days=max(1.0, rng.expovariate(1 / 14))) if rng.random() < 0.25 else None
    )
    topics = _weighted_sample(rng, TOPIC_POOL, rng.randint(2, 4))
    target_minutes = rng.choices([m for m, _ in TARGET_MINUTES], [w for _, w in TARGET_MINUTES])[0]
    seed_user = SeedUser(
        user={
            "email": f"seed-{index:04d}@{SEED_EMAIL_DOMAIN}",
            "password_hash": password_hash,
            "is_admin": False,
            "is_synthetic": True,
            "created_at": signup,
        },
        preferences={
            "interest_profile": {
                "topics": [Topic(name=t, description=t).model_dump() for t in topics],
                "avoid": [],
            },
            "target_minutes": target_minutes,
            "host_a": {"name": "Alex", "voice_id": settings.default_voice_host_a},
            "host_b": {"name": "Sam", "voice_id": settings.default_voice_host_b},
            # Never a schedule: the real scheduler would run paid episodes for it.
            "schedule_cron": None,
            "timezone": "UTC",
            "updated_at": signup,
        },
    )

    active_until = min(churn_at, end) if churn_at else end
    day = max(signup, start).replace(hour=0, minute=0, second=0, microsecond=0)
    while day < active_until:
        weekend = 0.6 if day.weekday() >= 5 else 1.0
        first_day = day <= signup
        created_at: datetime | None = None
        focus: str | None = None
        trigger = EpisodeTrigger.SCHEDULE if scheduled else EpisodeTrigger.MANUAL
        if first_day and signup >= start:
            # Activation: most new users generate right after onboarding.
            if rng.random() < 0.8:
                created_at = signup + timedelta(minutes=rng.uniform(5, 30))
                trigger = EpisodeTrigger.MANUAL
        elif scheduled:
            if rng.random() < 0.9:
                created_at = day + timedelta(hours=6, minutes=rng.uniform(0, 60))
        elif rng.random() < (0.2 + 0.7 * engagement) * weekend:
            created_at = day + timedelta(hours=rng.uniform(7, 22))

        if created_at is not None and created_at < active_until:
            if trigger == EpisodeTrigger.MANUAL and rng.random() < 0.3:
                focus = rng.choice(FOCUS_POOL)
            seed_episode = _simulate_episode(
                rng, baselines, created_at, trigger, focus, target_minutes, topics[0]
            )
            ready_at = seed_episode.episode["ready_at"]
            if max(s["finished_at"] for s in seed_episode.steps) < end:
                if trigger == EpisodeTrigger.MANUAL:
                    seed_episode.events.append(
                        _event(
                            "generate_clicked",
                            created_at,
                            {"target_minutes": target_minutes, "overridden": False},
                        )
                    )
                if ready_at and rng.random() < (0.35 + 0.55 * engagement) * weekend:
                    delay_h = (
                        rng.uniform(0.5, 12)
                        if trigger == EpisodeTrigger.SCHEDULE
                        else rng.expovariate(3)
                    )
                    play = _simulate_play(rng, seed_episode, ready_at + timedelta(hours=delay_h))
                    # A listen still in the future hasn't happened yet.
                    if play[-1]["created_at"] < end:
                        seed_episode.events.extend(play)
                seed_user.episodes.append(seed_episode)
        day += timedelta(days=1)

    # One login per active day, a moment before the day's first action.
    first_action: dict = {}
    for ep in seed_user.episodes:
        for ev in ep.events:
            d = ev["created_at"].date()
            first_action[d] = min(first_action.get(d, ev["created_at"]), ev["created_at"])
    for d in sorted(first_action):
        login_at = first_action[d] - timedelta(minutes=rng.uniform(0.5, 3))
        seed_user.events.append(_event("login", max(login_at, signup)))
    return seed_user


def build_dataset(
    rng: random.Random,
    *,
    days: int,
    users: int,
    end: datetime,
    baselines: dict[str, Baseline],
    settings: Settings,
    password_hash: str,
) -> list[SeedUser]:
    """`users` synthetic users over the `days` days before `end`. About 20%
    existed before the window; the rest sign up on a rising curve with
    quieter weekends."""
    start = end - timedelta(days=days)
    day_weights = [
        (1 + 2 * d / days) * (0.6 if (start + timedelta(days=d)).weekday() >= 5 else 1.0)
        for d in range(days)
    ]
    dataset = []
    for i in range(users):
        if rng.random() < 0.2:
            signup = start - timedelta(days=rng.uniform(1, 30))
        else:
            d = rng.choices(range(days), day_weights)[0]
            signup = start + timedelta(days=d, hours=rng.uniform(7, 23))
        dataset.append(
            _simulate_user(rng, i + 1, start, end, signup, baselines, settings, password_hash)
        )
    return dataset


def _seeded_user_ids():
    return select(User.id).where(User.email.like(f"%@{SEED_EMAIL_DOMAIN}"))


def delete_seeded(db: Session) -> int:
    """Removes every row owned by a seeded user; returns how many users."""
    user_ids = _seeded_user_ids()
    episode_ids = select(Episode.id).where(Episode.user_id.in_(user_ids))
    count = len(db.execute(user_ids).all())
    db.execute(delete(Event).where(Event.user_id.in_(user_ids)))
    db.execute(delete(PipelineStep).where(PipelineStep.episode_id.in_(episode_ids)))
    db.execute(delete(EpisodeItem).where(EpisodeItem.episode_id.in_(episode_ids)))
    db.execute(delete(ArticleScore).where(ArticleScore.episode_id.in_(episode_ids)))
    db.execute(delete(Episode).where(Episode.user_id.in_(user_ids)))
    db.execute(delete(Preferences).where(Preferences.user_id.in_(user_ids)))
    db.execute(delete(User).where(User.id.in_(user_ids)))
    return count


_CHUNK = 1000


def _next_ids(db: Session, table: str, n: int) -> list[int]:
    """Reserves n ids from the table's own sequence, so rows can be linked
    in Python before insert instead of relying on RETURNING order."""
    return list(
        db.scalars(
            text("SELECT nextval(pg_get_serial_sequence(:t, 'id')) FROM generate_series(1, :n)"),
            {"t": table, "n": n},
        )
    )


def _insert(db: Session, model: type, rows: list[dict]) -> None:
    # One multi-row INSERT ... VALUES per chunk. An executemany of the same
    # rows ran one statement per row here and took over a minute at the
    # default size (D-51).
    for i in range(0, len(rows), _CHUNK):
        db.execute(insert(model).values(rows[i : i + _CHUNK]))


def write_dataset(db: Session, dataset: list[SeedUser]) -> dict[str, int]:
    user_ids = _next_ids(db, "users", len(dataset))
    owned = list(zip(dataset, user_ids, strict=True))
    flat = [(uid, ep) for u, uid in owned for ep in u.episodes]
    episode_ids = _next_ids(db, "episodes", len(flat))
    users = [{**u.user, "id": uid} for u, uid in owned]
    preferences = [{**u.preferences, "user_id": uid} for u, uid in owned]
    episodes = [
        {**ep.episode, "id": eid, "user_id": uid}
        for (uid, ep), eid in zip(flat, episode_ids, strict=True)
    ]
    steps = [
        {**s, "episode_id": eid}
        for (_, ep), eid in zip(flat, episode_ids, strict=True)
        for s in ep.steps
    ]
    events = [
        {**e, "user_id": uid, "episode_id": eid}
        for (uid, ep), eid in zip(flat, episode_ids, strict=True)
        for e in ep.events
    ] + [{**e, "user_id": uid, "episode_id": None} for u, uid in owned for e in u.events]
    for model, rows in (
        (User, users),
        (Preferences, preferences),
        (Episode, episodes),
        (PipelineStep, steps),
        (Event, events),
    ):
        _insert(db, model, rows)
    return {
        "users": len(users),
        "episodes": len(episodes),
        "pipeline_steps": len(steps),
        "events": len(events),
    }
