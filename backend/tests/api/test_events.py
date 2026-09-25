from datetime import UTC, datetime

from sqlalchemy import select

from app.models import Episode, EpisodeStatus, EpisodeTrigger, Event, User
from tests.api.conftest import auth_headers, client, login, make_user


def _ready_episode(db, owner: User) -> Episode:
    episode = Episode(
        user_id=owner.id,
        status=EpisodeStatus.READY,
        trigger=EpisodeTrigger.MANUAL,
        window_start=datetime.now(UTC),
        target_minutes=6,
        ready_at=datetime.now(UTC),
    )
    db.add(episode)
    db.commit()
    return episode


def test_post_event(db) -> None:
    user = make_user(db, email="listener@example.com")
    episode = _ready_episode(db, user)
    token = login("listener@example.com")

    resp = client.post(
        "/events",
        json={"type": "play_progress", "episode_id": episode.id, "payload": {"position_s": 42}},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text

    row = db.scalar(select(Event).where(Event.id == resp.json()["id"]))
    assert row.user_id == user.id
    assert row.episode_id == episode.id
    assert row.type == "play_progress"
    assert row.payload == {"position_s": 42}


def test_post_event_requires_auth(db) -> None:
    resp = client.post("/events", json={"type": "play_started", "episode_id": 1})
    assert resp.status_code == 401


def test_post_event_rejects_server_only_and_unknown_types(db) -> None:
    user = make_user(db, email="forger@example.com")
    episode = _ready_episode(db, user)
    token = login("forger@example.com")
    for event_type in ("generate_clicked", "settings_changed", "made_up"):
        resp = client.post(
            "/events",
            json={"type": event_type, "episode_id": episode.id},
            headers=auth_headers(token),
        )
        assert resp.status_code == 422, event_type


def test_post_event_validates_payloads(db) -> None:
    user = make_user(db, email="payloads@example.com")
    episode = _ready_episode(db, user)
    token = login("payloads@example.com")

    bad = [
        ("episode_rated", {"value": 5}),
        ("episode_rated", {"value": True}),
        ("episode_rated", {}),
        ("play_progress", {"position_s": -3}),
        ("play_progress", {}),
    ]
    for event_type, payload in bad:
        resp = client.post(
            "/events",
            json={"type": event_type, "episode_id": episode.id, "payload": payload},
            headers=auth_headers(token),
        )
        assert resp.status_code == 422, (event_type, payload)

    ok = client.post(
        "/events",
        json={"type": "episode_rated", "episode_id": episode.id, "payload": {"value": -1}},
        headers=auth_headers(token),
    )
    assert ok.status_code == 201, ok.text


def test_post_event_on_someone_elses_episode_is_403(db) -> None:
    owner = make_user(db, email="ep-owner@example.com")
    make_user(db, email="ep-stranger@example.com")
    episode = _ready_episode(db, owner)
    token = login("ep-stranger@example.com")

    resp = client.post(
        "/events",
        json={"type": "episode_rated", "episode_id": episode.id, "payload": {"value": 1}},
        headers=auth_headers(token),
    )
    assert resp.status_code == 403
    assert db.scalar(select(Event).where(Event.episode_id == episode.id)) is None
