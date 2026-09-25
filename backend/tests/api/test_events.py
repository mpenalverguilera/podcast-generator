from sqlalchemy import select

from app.models import Event
from tests.api.conftest import auth_headers, client, login, make_user


def test_post_event(db) -> None:
    user = make_user(db, email="listener@example.com")
    token = login("listener@example.com")

    resp = client.post(
        "/events",
        json={"type": "play_progress", "payload": {"position_s": 42}},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text

    row = db.scalar(select(Event).where(Event.id == resp.json()["id"]))
    assert row.user_id == user.id
    assert row.type == "play_progress"
    assert row.payload == {"position_s": 42}


def test_post_event_requires_auth(db) -> None:
    resp = client.post("/events", json={"type": "play_started"})
    assert resp.status_code == 401
