from datetime import UTC, datetime

from app.models import Episode, EpisodeStatus, EpisodeTrigger, PipelineStep, StepStatus
from tests.api.conftest import auth_headers, client, login, make_user


def _episode(db, owner, *, created_at: datetime) -> Episode:
    episode = Episode(
        user_id=owner.id,
        status=EpisodeStatus.READY,
        trigger=EpisodeTrigger.MANUAL,
        window_start=created_at,
        target_minutes=6,
        duration_s=100.0,
    )
    db.add(episode)
    db.flush()
    episode.created_at = created_at
    db.commit()
    return episode


def test_metrics_requires_auth(db) -> None:
    resp = client.get("/admin/metrics")
    assert resp.status_code == 401


def test_metrics_rejects_non_admin(db) -> None:
    make_user(db, email="regular@example.com", is_admin=False)
    token = login("regular@example.com")
    resp = client.get("/admin/metrics", headers=auth_headers(token))
    assert resp.status_code == 403


def test_metrics_default_range_and_shape(db) -> None:
    make_user(db, email="admin@example.com", is_admin=True)
    token = login("admin@example.com")
    resp = client.get("/admin/metrics", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["include_synthetic"] is True
    # Defaults to a 30-day window ending today.
    assert body["date_to"] == datetime.now(UTC).date().isoformat()
    for section in ("product", "operations", "quality"):
        assert section in body
    assert "dau" in body["product"] and "stage_latency" in body["operations"]
    assert "classifier_eval" in body["quality"]


def test_metrics_date_range_and_include_synthetic_filter_episode_counts(db) -> None:
    admin = make_user(db, email="admin2@example.com", is_admin=True)
    _episode(db, admin, created_at=datetime(2026, 2, 1, tzinfo=UTC))
    _episode(db, admin, created_at=datetime(2026, 3, 1, tzinfo=UTC))
    token = login("admin2@example.com")

    resp = client.get(
        "/admin/metrics",
        params={"from": "2026-02-01", "to": "2026-02-01"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["date_from"] == "2026-02-01" and body["date_to"] == "2026-02-01"
    assert body["product"]["episodes_per_day"] == [
        {"day": "2026-02-01", "manual": 1, "scheduled": 0}
    ]


def test_metrics_total_spend_matches_manual_sum(db) -> None:
    admin = make_user(db, email="admin3@example.com", is_admin=True)
    day = datetime(2026, 4, 1, tzinfo=UTC)
    episode = _episode(db, admin, created_at=day)
    db.add_all(
        [
            PipelineStep(
                episode_id=episode.id,
                stage="planning",
                status=StepStatus.SUCCESS,
                provider="openai",
                cost_usd=0.02,
                latency_ms=500,
                started_at=day,
            ),
            PipelineStep(
                episode_id=episode.id,
                stage="voicing",
                status=StepStatus.SUCCESS,
                provider="elevenlabs",
                cost_usd=0.63,
                cost_is_estimate=True,
                latency_ms=90000,
                started_at=day,
            ),
        ]
    )
    db.commit()
    token = login("admin3@example.com")

    resp = client.get(
        "/admin/metrics",
        params={"from": "2026-04-01", "to": "2026-04-01"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    ops = resp.json()["operations"]
    assert ops["total_spend_usd"] == 0.65  # manual check: 0.02 + 0.63
    assert ops["total_spend_includes_estimate"] is True
