import time
from datetime import UTC, datetime

from app.config import get_settings
from app.models import Episode, EpisodeStatus, EpisodeTrigger
from tests.api.conftest import auth_headers, client, login, make_user


def _poll_until_terminal(
    token: str, episode_id: int, timeout: float = 20.0, stale: tuple[str, str | None] | None = None
) -> dict:
    """`stale`, if given, is the episode's pre-run (status, failed_stage) --
    used after POST /retry, where a GET can race ahead of the background
    thread and briefly still observe the pre-retry snapshot rather than the
    retry's own outcome. A read matching `stale` exactly is not yet terminal,
    even though "failed" is otherwise one of the two terminal statuses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        resp = client.get(f"/episodes/{episode_id}", headers=auth_headers(token))
        assert resp.status_code == 200, resp.text
        body = resp.json()
        if stale is not None and (body["status"], body["failed_stage"]) == stale:
            time.sleep(0.05)
            continue
        if body["status"] in ("ready", "failed"):
            return body
        time.sleep(0.2)
    raise AssertionError(f"episode {episode_id} did not reach a terminal status within {timeout}s")


def test_generate_list_detail_and_audio_range(db) -> None:
    make_user(db, email="gen@example.com")
    token = login("gen@example.com")

    resp = client.post(
        "/episodes/generate",
        json={"target_minutes": 4, "focus_request": "prior authorization"},
        headers=auth_headers(token),
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["target_minutes"] == 4
    episode_id = created["id"]

    detail = _poll_until_terminal(token, episode_id)
    assert detail["status"] == "ready", detail
    assert detail["target_minutes"] == 4
    assert detail["trigger"] == "manual"
    assert detail["focus_request"] == "prior authorization"
    assert detail["my_rating"] is None
    assert detail["steps"], "expected pipeline_steps summaries"

    sections = detail["sections"]
    assert [sections[0]["kind"], sections[-1]["kind"]] == ["intro", "outro"]
    assert sections[0]["heading"] is None and sections[0]["sources"] == []
    stories = [s for s in sections if s["kind"] == "story"]
    assert stories, "expected at least one story section"
    for story in stories:
        assert story["turns"] and story["sources"]
        assert story["heading"] == story["sources"][0]["title"]
        assert story["topic"]
    assert all(t["speaker"] in ("Alex", "Sam") for s in sections for t in s["turns"])

    listing = client.get("/episodes", headers=auth_headers(token))
    assert listing.status_code == 200, listing.text
    item = next(e for e in listing.json() if e["id"] == episode_id)
    assert item["trigger"] == "manual"
    assert item["focus_request"] == "prior authorization"
    assert item["failed_stage"] is None

    # A native <audio src> sends no Authorization header: the media token in
    # audio_url is the only credential.
    assert detail["audio_url"].startswith(f"/episodes/{episode_id}/audio?t=")
    audio_resp = client.get(detail["audio_url"], headers={"Range": "bytes=0-99"})
    assert audio_resp.status_code == 206, audio_resp.text
    assert audio_resp.headers["content-range"].startswith("bytes 0-99/")


def test_audio_needs_a_media_token_for_that_episode(db) -> None:
    make_user(db, email="audio@example.com")
    token = login("audio@example.com")
    first = client.post("/episodes/generate", json={}, headers=auth_headers(token)).json()
    first_detail = _poll_until_terminal(token, first["id"])
    second = client.post("/episodes/generate", json={}, headers=auth_headers(token)).json()
    second_detail = _poll_until_terminal(token, second["id"])

    audio = f"/episodes/{first['id']}/audio"
    assert client.get(audio, headers=auth_headers(token)).status_code == 422, "t is required"
    assert client.get(f"{audio}?t={token}").status_code == 401, "a login token isn't one"
    other_token = second_detail["audio_url"].split("?t=")[1]
    assert client.get(f"{audio}?t={other_token}").status_code == 401, "wrong episode"
    assert client.get(first_detail["audio_url"]).status_code == 200


def test_media_token_is_not_a_login_token(db) -> None:
    make_user(db, email="media-login@example.com")
    token = login("media-login@example.com")
    created = client.post("/episodes/generate", json={}, headers=auth_headers(token)).json()
    detail = _poll_until_terminal(token, created["id"])
    media_token = detail["audio_url"].split("?t=")[1]
    assert client.get("/me", headers=auth_headers(media_token)).status_code == 401


def test_my_rating_follows_the_latest_rating(db) -> None:
    user = make_user(db, email="rater@example.com")
    token = login("rater@example.com")
    episode = Episode(
        user_id=user.id,
        status=EpisodeStatus.READY,
        trigger=EpisodeTrigger.MANUAL,
        window_start=datetime.now(UTC),
        target_minutes=6,
    )
    db.add(episode)
    db.commit()
    created = {"id": episode.id}

    def rate(value: int) -> int | None:
        event = {"type": "episode_rated", "episode_id": created["id"], "payload": {"value": value}}
        resp = client.post("/events", json=event, headers=auth_headers(token))
        assert resp.status_code == 201, resp.text
        detail = client.get(f"/episodes/{created['id']}", headers=auth_headers(token))
        return detail.json()["my_rating"]

    assert rate(1) == 1
    assert rate(-1) == -1
    assert rate(0) is None, "0 clears the rating"


def test_generate_without_override_uses_saved_default(db) -> None:
    make_user(db, email="default-minutes@example.com")
    token = login("default-minutes@example.com")

    resp = client.post("/episodes/generate", json={}, headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    assert resp.json()["target_minutes"] == 3  # make_user's fixture default

    _poll_until_terminal(token, resp.json()["id"])


def test_generate_out_of_range_minutes_is_422(db) -> None:
    make_user(db, email="oor@example.com")
    token = login("oor@example.com")
    resp = client.post(
        "/episodes/generate", json={"target_minutes": 20}, headers=auth_headers(token)
    )
    assert resp.status_code == 422


def test_generate_conflicts_while_in_progress(db) -> None:
    make_user(db, email="conflict@example.com")
    token = login("conflict@example.com")

    first = client.post("/episodes/generate", json={}, headers=auth_headers(token))
    assert first.status_code == 201, first.text

    second = client.post("/episodes/generate", json={}, headers=auth_headers(token))
    assert second.status_code == 409, second.text

    _poll_until_terminal(token, first.json()["id"])


def test_episode_detail_requires_ownership(db) -> None:
    make_user(db, email="owner@example.com")
    make_user(db, email="stranger@example.com")
    owner_token = login("owner@example.com")
    stranger_token = login("stranger@example.com")

    created = client.post("/episodes/generate", json={}, headers=auth_headers(owner_token))
    episode_id = created.json()["id"]
    _poll_until_terminal(owner_token, episode_id)

    resp = client.get(f"/episodes/{episode_id}", headers=auth_headers(stranger_token))
    assert resp.status_code == 403


def test_retry_failed_episode(db) -> None:
    user = make_user(db, email="retry@example.com")
    token = login("retry@example.com")

    episode = Episode(
        user_id=user.id,
        status=EpisodeStatus.FAILED,
        failed_stage="planning",
        error="simulated failure",
        trigger=EpisodeTrigger.MANUAL,
        window_start=datetime.now(UTC),
        target_minutes=6,
    )
    db.add(episode)
    db.commit()
    db.refresh(episode)

    resp = client.post(f"/episodes/{episode.id}/retry", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "planning", "already out of 'failed' before the thread starts"

    # A double click: the episode is no longer failed, so no second runner.
    again = client.post(f"/episodes/{episode.id}/retry", headers=auth_headers(token))
    assert again.status_code == 409, again.text

    detail = _poll_until_terminal(token, episode.id, stale=("failed", "planning"))
    assert detail["status"] == "ready", detail


def test_forced_failure_then_retry_succeeds(db, monkeypatch) -> None:
    """The phase 06 walkthrough's "retry a forced failure", on fakes."""
    monkeypatch.setattr(get_settings(), "fake_fail_once_at", "ranking")
    make_user(db, email="forced@example.com")
    token = login("forced@example.com")

    created = client.post("/episodes/generate", json={}, headers=auth_headers(token)).json()
    failed = _poll_until_terminal(token, created["id"])
    assert (failed["status"], failed["failed_stage"]) == ("failed", "ranking")
    listing = client.get("/episodes", headers=auth_headers(token)).json()
    item = next(e for e in listing if e["id"] == created["id"])
    assert item["failed_stage"] == "ranking" and "forced failure" in item["error"]

    resp = client.post(f"/episodes/{created['id']}/retry", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    detail = _poll_until_terminal(token, created["id"], stale=("failed", "ranking"))
    assert detail["status"] == "ready", detail


def test_retry_non_failed_episode_is_409(db) -> None:
    make_user(db, email="notfailed@example.com")
    token = login("notfailed@example.com")

    created = client.post("/episodes/generate", json={}, headers=auth_headers(token))
    episode_id = created.json()["id"]
    _poll_until_terminal(token, episode_id)  # now ready

    resp = client.post(f"/episodes/{episode_id}/retry", headers=auth_headers(token))
    assert resp.status_code == 409


def test_episodes_require_auth(db) -> None:
    assert client.get("/episodes").status_code == 401
    assert client.post("/episodes/generate", json={}).status_code == 401


def test_retry_conflicts_with_another_running_episode(db) -> None:
    user = make_user(db, email="retry-busy@example.com")
    token = login("retry-busy@example.com")
    common = dict(
        user_id=user.id,
        trigger=EpisodeTrigger.MANUAL,
        window_start=datetime.now(UTC),
        target_minutes=6,
    )
    failed = Episode(status=EpisodeStatus.FAILED, failed_stage="planning", **common)
    running = Episode(status=EpisodeStatus.VOICING, **common)
    db.add_all([failed, running])
    db.commit()

    resp = client.post(f"/episodes/{failed.id}/retry", headers=auth_headers(token))
    assert resp.status_code == 409, resp.text
    db.refresh(failed)
    assert failed.status == EpisodeStatus.FAILED
