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

    for value in (-1, 1, 0):  # 0 clears the rating
        ok = client.post(
            "/events",
            json={"type": "episode_rated", "episode_id": episode.id, "payload": {"value": value}},
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


def test_playback_state_is_read_back_from_play_events(db) -> None:
    """played / completed / resume_position_s on GET /episodes and the resume
    point on GET /episodes/{id} come from the caller's own play events (D-46)."""
    user = make_user(db, email="resume@example.com")
    unplayed = _ready_episode(db, user)
    partial = _ready_episode(db, user)
    finished = _ready_episode(db, user)
    token = login("resume@example.com")

    def send(type_: str, episode: Episode, payload: dict | None = None) -> None:
        body = {"type": type_, "episode_id": episode.id, "payload": payload or {}}
        assert client.post("/events", json=body, headers=auth_headers(token)).status_code == 201

    send("play_started", partial)
    send("play_progress", partial, {"position_s": 15})
    send("play_progress", partial, {"position_s": 42.5})
    send("play_started", finished)
    send("play_progress", finished, {"position_s": 300})
    send("play_completed", finished)

    listing = {e["id"]: e for e in client.get("/episodes", headers=auth_headers(token)).json()}
    assert (listing[unplayed.id]["played"], listing[unplayed.id]["completed"]) == (False, False)
    assert listing[unplayed.id]["resume_position_s"] is None
    assert (listing[partial.id]["played"], listing[partial.id]["completed"]) == (True, False)
    assert listing[partial.id]["resume_position_s"] == 42.5
    assert (listing[finished.id]["played"], listing[finished.id]["completed"]) == (True, True)
    assert listing[finished.id]["resume_position_s"] is None

    detail = client.get(f"/episodes/{partial.id}", headers=auth_headers(token)).json()
    assert detail["resume_position_s"] == 42.5

    # A re-listen after finishing sets a resume point again.
    send("play_progress", finished, {"position_s": 20})
    detail = client.get(f"/episodes/{finished.id}", headers=auth_headers(token)).json()
    assert detail["resume_position_s"] == 20
