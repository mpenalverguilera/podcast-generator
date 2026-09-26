from datetime import datetime

from sqlalchemy import select

from app.config import get_settings
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


def test_profile_extract_rejects_empty_answers(db) -> None:
    make_user(db)
    token = login()

    resp = client.post("/profile/extract", json={"answers": {}}, headers=auth_headers(token))
    assert resp.status_code == 422, resp.text

    resp = client.post(
        "/profile/extract",
        json={"answers": {"work": "  ", "fun": ""}},
        headers=auth_headers(token),
    )
    assert resp.status_code == 422, resp.text


def test_get_and_put_preferences(db) -> None:
    make_user(db, email="prefs@example.com")
    token = login("prefs@example.com")

    resp = client.get("/preferences", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["target_minutes"] == 3

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


def test_next_run_at_follows_the_schedule(db) -> None:
    make_user(db, email="next-run@example.com")
    token = login("next-run@example.com")
    assert client.get("/preferences", headers=auth_headers(token)).json()["next_run_at"] is None

    resp = client.put(
        "/preferences",
        json={"schedule_cron": "30 7 * * 1-5", "timezone": "Europe/Madrid"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 200, resp.text
    next_run = datetime.fromisoformat(resp.json()["next_run_at"])
    assert (next_run.hour, next_run.minute) == (7, 30)
    assert next_run.weekday() < 5
    assert next_run > datetime.now(next_run.tzinfo)

    cleared = client.put("/preferences", json={"schedule_cron": None}, headers=auth_headers(token))
    assert cleared.json()["next_run_at"] is None


def test_length_options(db) -> None:
    make_user(db)
    token = login()
    resp = client.get("/preferences/length-options", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    options = resp.json()
    assert [o["minutes"] for o in options] == list(range(3, 13))
    stories = [o["stories"] for o in options]
    assert all(n >= 1 for n in stories) and stories == sorted(stories)


def test_voice_preview_needs_the_media_token(db, tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(get_settings(), "data_dir", tmp_path)
    voice = CURATED_VOICES[0]
    (tmp_path / "voice_previews").mkdir()
    (tmp_path / "voice_previews" / f"{voice.id}.mp3").write_bytes(b"ID3fake")
    make_user(db)
    token = login()

    voices = client.get("/voices", headers=auth_headers(token)).json()
    preview_url = next(v["preview_url"] for v in voices if v["id"] == voice.id)
    assert preview_url.startswith(f"/voices/{voice.id}/preview?t=")

    # Plain <audio src>: no Authorization header, the token is the credential.
    assert client.get(preview_url).status_code == 200
    assert client.get(f"/voices/{voice.id}/preview?t={token}").status_code == 401
    other = CURATED_VOICES[1].id
    wrong_voice = preview_url.replace(f"/voices/{voice.id}/", f"/voices/{other}/")
    assert client.get(wrong_voice).status_code == 401
