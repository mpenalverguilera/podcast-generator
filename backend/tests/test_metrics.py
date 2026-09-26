import json
from datetime import UTC, date, datetime, timedelta

from app import metrics
from app.metrics import PlayEvent, RatingRow, StepRow
from app.models import (
    Article,
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

# ---------------------------------------------------------------------------
# Pure compute functions -- tiny literal fixtures, no DB.
# ---------------------------------------------------------------------------


def test_active_users_by_day_dau_and_trailing_wau() -> None:
    d0, d1, d8 = date(2026, 1, 1), date(2026, 1, 2), date(2026, 1, 9)
    user_days = [(d0, 1), (d0, 2), (d1, 1), (d8, 3)]
    dau, wau = metrics.active_users_by_day(user_days, date(2026, 1, 1), date(2026, 1, 9))

    by_day = {row.day: row.count for row in dau}
    assert by_day[d0] == 2 and by_day[d1] == 1 and by_day[d8] == 1

    wau_by_day = {row.day: row.count for row in wau}
    # d1's trailing 7-day window still sees d0's two users plus d1's one (union).
    assert wau_by_day[d1] == 2
    # d8 is 7 days after d0, so d0's users have fallen out of the trailing window.
    assert wau_by_day[d8] == 1


def test_listen_through_rate_and_avg_percent_listened() -> None:
    events = [
        PlayEvent(1, 10, "play_started", None, 100.0),
        PlayEvent(1, 10, "play_completed", None, 100.0),
        PlayEvent(2, 11, "play_started", None, 100.0),
        PlayEvent(2, 11, "play_progress", 25.0, 100.0),
    ]
    assert metrics.listen_through_rate(events) == 0.5
    assert metrics.avg_percent_listened(events) == (1.0 + 0.25) / 2


def test_listen_through_rate_is_none_with_no_plays() -> None:
    assert metrics.listen_through_rate([]) is None
    assert metrics.avg_percent_listened([]) is None


def test_total_listened_minutes_uses_duration_when_completed() -> None:
    events = [
        PlayEvent(1, 10, "play_started", None, 120.0),
        PlayEvent(1, 10, "play_completed", None, 120.0),
        PlayEvent(2, 11, "play_started", None, 120.0),
        PlayEvent(2, 11, "play_progress", 30.0, 120.0),
    ]
    assert metrics.total_listened_minutes(events) == (120.0 + 30.0) / 60


def test_rating_ratio_and_by_prompt_version() -> None:
    # fetch_latest_ratings' SQL already restricts value to (1, -1) -- a clear
    # (0) never reaches these compute functions.
    ratings = [
        RatingRow(1, 1, "1"),
        RatingRow(2, 1, "1"),
        RatingRow(3, -1, "1"),
        RatingRow(4, -1, "2"),
    ]
    assert metrics.rating_ratio(ratings) == 0.5  # 2 up, 2 down overall

    by_version = {r.script_prompt_version: r for r in metrics.rating_by_prompt_version(ratings)}
    assert by_version["1"].avg_rating == 1 / 3 and by_version["1"].n == 3
    assert by_version["2"].avg_rating == -1 and by_version["2"].n == 1


def test_stage_latency_percentiles() -> None:
    steps = [
        StepRow(date(2026, 1, 1), "voicing", "success", "elevenlabs", 0.1, True, ms)
        for ms in (100, 200, 300, 400)
    ]
    [latency] = metrics.stage_latency(steps)
    assert latency.stage == "voicing"
    assert latency.p50_ms == 250.0
    assert latency.p95_ms == 385.0


def test_stage_failure_rate() -> None:
    steps = [
        StepRow(date(2026, 1, 1), "fetching", "success", "exa", 0.01, False, 100),
        StepRow(date(2026, 1, 1), "fetching", "success", "exa", 0.01, False, 100),
        StepRow(date(2026, 1, 1), "fetching", "failed", "unknown", None, False, 50),
    ]
    [rate] = metrics.stage_failure_rate(steps)
    assert rate.stage == "fetching" and rate.n == 3 and rate.failure_rate == 1 / 3


def test_cost_per_day_by_provider_and_total_spend_flags_estimate() -> None:
    steps = [
        StepRow(date(2026, 1, 1), "voicing", "success", "elevenlabs", 1.0, True, 1000),
        StepRow(date(2026, 1, 1), "voicing", "success", "elevenlabs", 2.0, True, 1000),
        StepRow(date(2026, 1, 1), "planning", "success", "openai", 0.5, False, 100),
    ]
    costs = {(c.day, c.provider): c for c in metrics.cost_per_day_by_provider(steps)}
    eleven = costs[(date(2026, 1, 1), "elevenlabs")]
    assert eleven.cost_usd == 3.0 and eleven.cost_is_estimate is True
    openai = costs[(date(2026, 1, 1), "openai")]
    assert openai.cost_usd == 0.5 and openai.cost_is_estimate is False

    total, is_estimate = metrics.total_spend(steps)
    assert total == 3.5 and is_estimate is True


def test_load_latest_classifier_eval_picks_newest_file_and_trims_fields(tmp_path) -> None:
    older = {"date": "2026-09-01", "classifiers": {"luna": {"classifier": "luna", "n": 10}}}
    newer = {
        "date": "2026-09-02",
        "classifiers": {
            "sol": {
                "classifier": "sol",
                "n": 20,
                "keep_gate_precision": 0.9,
                "internal_debug_field": "not in the trimmed output",
            }
        },
    }
    (tmp_path / "2026-09-01.json").write_text(json.dumps(older))
    (tmp_path / "2026-09-02.json").write_text(json.dumps(newer))
    (tmp_path / "not-a-date.jsonl").write_text("{}")

    rows, eval_date = metrics.load_latest_classifier_eval(tmp_path)
    assert eval_date == "2026-09-02"
    assert rows == [
        {
            "classifier": "sol",
            "n": 20,
            "keep_gate_precision": 0.9,
            "keep_gate_recall": None,
            "keep_gate_roc_auc": None,
            "relevance_accuracy": None,
            "relevance_roc_auc": None,
            "newsworthy_roc_auc": None,
            "selection_precision": None,
            "latency_p50_ms": None,
            "latency_p95_ms": None,
            "cost_per_100": None,
        }
    ]


def test_load_latest_classifier_eval_with_no_files_returns_empty(tmp_path) -> None:
    assert metrics.load_latest_classifier_eval(tmp_path) == ([], None)


# ---------------------------------------------------------------------------
# DB-backed fetch functions and the end-to-end orchestrator.
# ---------------------------------------------------------------------------


def _user(
    db, email: str, *, is_synthetic: bool = False, created_at: datetime | None = None
) -> User:
    user = User(email=email, password_hash="x", is_synthetic=is_synthetic)
    db.add(user)
    db.flush()
    if created_at is not None:
        user.created_at = created_at
    db.add(Preferences(user_id=user.id, host_a={"name": "A"}, host_b={"name": "B"}))
    return user


def _episode(
    db,
    user: User,
    *,
    created_at: datetime,
    trigger: EpisodeTrigger = EpisodeTrigger.MANUAL,
    focus_request: str | None = None,
    duration_s: float | None = 100.0,
    is_synthetic: bool = False,
) -> Episode:
    episode = Episode(
        user_id=user.id,
        status=EpisodeStatus.READY,
        trigger=trigger,
        focus_request=focus_request,
        window_start=created_at,
        target_minutes=6,
        duration_s=duration_s,
        prompt_versions={"script_writer": "1"},
        is_synthetic=is_synthetic,
    )
    db.add(episode)
    db.flush()
    episode.created_at = created_at
    return episode


def test_fetch_episodes_per_day_and_focus_usage_respect_synthetic_filter(db) -> None:
    day = datetime(2026, 2, 1, 12, tzinfo=UTC)
    real_user = _user(db, "real@example.com")
    synth_user = _user(db, "synth@example.com", is_synthetic=True)
    _episode(db, real_user, created_at=day, focus_request="ai news")
    _episode(db, real_user, created_at=day, trigger=EpisodeTrigger.SCHEDULE)
    _episode(db, synth_user, created_at=day, is_synthetic=True)
    db.commit()

    start, end = metrics._bounds(date(2026, 2, 1), date(2026, 2, 1))

    with_synthetic = metrics.fetch_episodes_per_day(db, start, end, True)
    assert with_synthetic == [metrics.EpisodesPerDay(day=date(2026, 2, 1), manual=2, scheduled=1)]
    real_only = metrics.fetch_episodes_per_day(db, start, end, False)
    assert real_only == [metrics.EpisodesPerDay(day=date(2026, 2, 1), manual=1, scheduled=1)]

    assert metrics.fetch_focus_request_usage_rate(db, start, end, True) == 1 / 2


def test_fetch_top_topics_counts_only_selected_stories(db) -> None:
    user = _user(db, "reader@example.com")
    created_at = datetime(2026, 2, 1, tzinfo=UTC)
    episode = _episode(db, user, created_at=created_at)
    kept = Article(url_hash="a1", url="https://x/1")
    dropped = Article(url_hash="a2", url="https://x/2")
    db.add_all([kept, dropped])
    db.flush()
    db.add_all(
        [
            ArticleScore(episode_id=episode.id, article_id=kept.id, topic="AI"),
            ArticleScore(episode_id=episode.id, article_id=dropped.id, topic="Sports"),
            EpisodeItem(episode_id=episode.id, article_id=kept.id, position=0, story_id="s1"),
        ]
    )
    db.commit()

    start, end = metrics._bounds(date(2026, 2, 1), date(2026, 2, 1))
    topics = metrics.fetch_top_topics(db, start, end, True)
    assert topics == [metrics.TopicCount(topic="AI", count=1)]


def test_fetch_retention_cohorts_counts_week2_plays(db) -> None:
    # A Monday, so date_trunc('week', ...) lands exactly on signup day.
    signup = datetime(2026, 2, 2, 9, tzinfo=UTC)
    returner = _user(db, "returns@example.com", created_at=signup)
    _user(db, "churns@example.com", created_at=signup)
    db.flush()
    db.add(
        Event(
            user_id=returner.id,
            type="play_started",
            created_at=signup + timedelta(days=8),
        )
    )
    db.commit()

    start, end = metrics._bounds(date(2026, 2, 2), date(2026, 3, 1))
    [cohort] = metrics.fetch_retention_cohorts(db, start, end, True)
    assert cohort.cohort_week == date(2026, 2, 2)
    assert cohort.cohort_size == 2
    assert cohort.retained == 1
    assert cohort.retention_rate == 0.5


def test_fetch_grounding_flag_counts_ignores_unscripted_episodes(db) -> None:
    """Regression test: SQLAlchemy's JSONB type stores a Python None as the
    JSON scalar `null` (none_as_null defaults to False), not a SQL NULL, once
    the attribute is explicitly assigned rather than left at its unset
    default -- exactly what app/seed_metrics.py's bulk insert does for every
    unscripted episode. `jsonb_array_length` on that JSON `null` raises
    "cannot get array length of a scalar", so the fetch must check
    jsonb_typeof, not IS NOT NULL. A scripted episode with no final flags yet
    (grounding_flags_final explicitly None) exercises the same case on the
    other column."""
    user = _user(db, "reader2@example.com")
    created_at = datetime(2026, 2, 1, tzinfo=UTC)
    scripted = _episode(db, user, created_at=created_at)
    scripted.grounding_flags_initial = [{"a": 1}, {"a": 2}]
    scripted.grounding_flags_final = [{"a": 1}]
    zero_final = _episode(db, user, created_at=created_at)
    zero_final.grounding_flags_initial = [{"a": 1}]
    zero_final.grounding_flags_final = None  # explicit assignment -> JSON `null`, not SQL NULL
    unscripted = _episode(db, user, created_at=created_at)
    unscripted.status = EpisodeStatus.FAILED
    unscripted.failed_stage = "fetching"
    unscripted.grounding_flags_initial = None  # explicit assignment -> JSON `null`, not SQL NULL
    db.commit()

    start, end = metrics._bounds(date(2026, 2, 1), date(2026, 2, 1))
    initial, final = metrics.fetch_grounding_flag_counts(db, start, end, True)
    assert sorted(initial) == [1, 2]
    assert sorted(final) == [0, 1]


def test_build_metrics_end_to_end_matches_manual_spot_check(db) -> None:
    day = datetime(2026, 2, 1, tzinfo=UTC)
    user = _user(db, "spotcheck@example.com")
    db.flush()
    for _ in range(3):
        episode = _episode(db, user, created_at=day)
        db.add(
            PipelineStep(
                episode_id=episode.id,
                stage="voicing",
                status=StepStatus.SUCCESS,
                provider="elevenlabs",
                cost_usd=1.5,
                cost_is_estimate=True,
                latency_ms=1000,
                started_at=day,
            )
        )
    db.commit()

    result = metrics.build_metrics(db, date(2026, 2, 1), date(2026, 2, 1), include_synthetic=True)
    assert result.operations.total_spend_usd == 4.5  # manual check: 3 episodes x $1.50
    assert result.operations.total_spend_includes_estimate is True
    assert result.product.episodes_per_day == [
        metrics.EpisodesPerDay(day=date(2026, 2, 1), manual=3, scheduled=0)
    ]
