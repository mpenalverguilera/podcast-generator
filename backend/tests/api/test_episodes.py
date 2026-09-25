import time
from datetime import UTC, datetime

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
        "/episodes/generate", json={"target_minutes": 4}, headers=auth_headers(token)
    )
    assert resp.status_code == 201, resp.text
    created = resp.json()
    assert created["target_minutes"] == 4
    episode_id = created["id"]

    detail = _poll_until_terminal(token, episode_id)
    assert detail["status"] == "ready", detail
    assert detail["target_minutes"] == 4
    assert detail["transcript"], "expected a non-empty transcript"
    assert detail["steps"], "expected pipeline_steps summaries"

    listing = client.get("/episodes", headers=auth_headers(token))
    assert listing.status_code == 200, listing.text
    assert any(e["id"] == episode_id for e in listing.json())

    audio_resp = client.get(
        f"/episodes/{episode_id}/audio",
        headers={**auth_headers(token), "Range": "bytes=0-99"},
    )
    assert audio_resp.status_code == 206, audio_resp.text
    assert audio_resp.headers["content-range"].startswith("bytes 0-99/")


def test_generate_without_override_uses_saved_default(db) -> None:
    make_user(db, email="default-minutes@example.com")
    token = login("default-minutes@example.com")

    resp = client.post("/episodes/generate", json={}, headers=auth_headers(token))
    assert resp.status_code == 201, resp.text
    assert resp.json()["target_minutes"] == 6  # make_user's fixture default

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
