from sqlalchemy import select

from app.models import Event
from app.voices import CURATED_VOICES
from tests.api.conftest import auth_headers, client, login, make_user


def test_profile_questions_is_public_shape(db) -> None:
    make_user(db)
    token = login()
    resp = client.get("/profile/questions", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    keys = {q["key"] for q in resp.json()}
    assert {"work", "fun", "avoid", "depth"} <= keys


def test_profile_extract_does_not_save(db) -> None:
    user = make_user(db)
    token = login()

    resp = client.post(
        "/profile/extract",
        json={"answers": {"work": "AI voice agents", "fun": "Formula 1"}},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    profile = resp.json()
    assert [t["name"] for t in profile["topics"]] == ["AI voice agents", "Formula 1"]

    # Not persisted: the user's saved preferences are untouched.
    db.refresh(user)
    assert db.get(type(user.preferences), user.id).interest_profile == {"topics": [], "avoid": []}


def test_get_and_put_preferences(db) -> None:
    make_user(db, email="prefs@example.com")
    token = login("prefs@example.com")

    resp = client.get("/preferences", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["target_minutes"] == 6

    resp = client.put(
        "/preferences",
        json={"target_minutes": 9, "tone": "playful", "schedule_cron": "0 8 * * *"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["target_minutes"] == 9
    assert body["tone"] == "playful"
    assert body["schedule_cron"] == "0 8 * * *"


def test_put_preferences_rejects_out_of_range_minutes(db) -> None:
    make_user(db, email="range@example.com")
    token = login("range@example.com")
    resp = client.put("/preferences", json={"target_minutes": 30}, headers=auth_headers(token))
    assert resp.status_code == 422


def test_put_preferences_rejects_invalid_cron(db) -> None:
    make_user(db, email="cron@example.com")
    token = login("cron@example.com")
    resp = client.put(
        "/preferences", json={"schedule_cron": "not a cron"}, headers=auth_headers(token)
    )
    assert resp.status_code == 422


def test_put_preferences_rejects_free_text_tone(db) -> None:
    make_user(db, email="tone@example.com")
    token = login("tone@example.com")
    resp = client.put("/preferences", json={"tone": "punchy"}, headers=auth_headers(token))
    assert resp.status_code == 422


def test_put_preferences_validates_host_voice(db) -> None:
    make_user(db, email="voice@example.com")
    token = login("voice@example.com")
    unknown = client.put(
        "/preferences",
        json={"host_a": {"name": "Alex", "voice_id": "not-a-curated-voice"}},
        headers=auth_headers(token),
    )
    assert unknown.status_code == 422

    curated = client.put(
        "/preferences",
        json={"host_a": {"name": "Alex", "voice_id": CURATED_VOICES[2].id}},
        headers=auth_headers(token),
    )
    assert curated.status_code == 200, curated.text
    assert curated.json()["host_a"]["voice_id"] == CURATED_VOICES[2].id


def test_put_preferences_emits_settings_changed_event(db) -> None:
    user = make_user(db, email="events@example.com")
    token = login("events@example.com")
    client.put("/preferences", json={"tone": "focused"}, headers=auth_headers(token))

    events = db.scalars(select(Event).where(Event.user_id == user.id)).all()
    assert any(e.type == "settings_changed" for e in events)


def test_put_preferences_emits_profile_updated_event(db) -> None:
    user = make_user(db, email="profile-events@example.com")
    token = login("profile-events@example.com")
    client.put(
        "/preferences",
        json={"interest_profile": {"topics": [], "avoid": ["sports"]}},
        headers=auth_headers(token),
    )

    events = db.scalars(select(Event).where(Event.user_id == user.id)).all()
    assert any(e.type == "profile_updated" for e in events)


def test_list_voices(db) -> None:
    make_user(db)
    token = login()
    resp = client.get("/voices", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    voices = resp.json()
    assert len(voices) >= 2
    assert all("id" in v and "name" in v and "label" in v for v in voices)
    # No preview files exist in this test environment, so every preview_url
    # is omitted (None), per docs/phases/05-api-scheduler.md step 2.
    assert all(v["preview_url"] is None for v in voices)


def test_voices_requires_auth(db) -> None:
    resp = client.get("/voices")
    assert resp.status_code == 401
