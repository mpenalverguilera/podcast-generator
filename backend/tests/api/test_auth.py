from sqlalchemy import select

from app.models import Event, User
from tests.api.conftest import auth_headers, client, login, make_user


def test_login_success_and_me(db) -> None:
    make_user(db, email="alice@example.com")
    token = login("alice@example.com")

    resp = client.get("/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["is_admin"] is False
    assert body["has_profile"] is False, "make_user saves an empty profile"


def test_me_has_profile_once_a_topic_is_saved(db) -> None:
    make_user(db, email="topics@example.com")
    token = login("topics@example.com")
    profile = {"topics": [{"name": "F1", "description": "Formula 1"}], "avoid": []}
    resp = client.put(
        "/preferences", json={"interest_profile": profile}, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    assert client.get("/me", headers=auth_headers(token)).json()["has_profile"] is True


def test_login_wrong_password(db) -> None:
    make_user(db, email="bob@example.com")
    resp = client.post(
        "/auth/login", json={"email": "bob@example.com", "password": "wrong-password"}
    )
    assert resp.status_code == 401


def test_login_unknown_email(db) -> None:
    resp = client.post("/auth/login", json={"email": "nobody@example.com", "password": "whatever"})
    assert resp.status_code == 401


def test_me_without_token_is_401(db) -> None:
    resp = client.get("/me")
    assert resp.status_code == 401


def test_me_with_garbage_token_is_401(db) -> None:
    resp = client.get("/me", headers=auth_headers("not-a-real-jwt"))
    assert resp.status_code == 401


def _signup(email: str, password: str = "password123"):
    return client.post("/auth/signup", json={"email": email, "password": password})


def test_signup_creates_user_with_default_preferences_and_signs_in(db) -> None:
    resp = _signup("  New.User@Example.com ")
    assert resp.status_code == 201, resp.text
    token = resp.json()["access_token"]

    me = client.get("/me", headers=auth_headers(token)).json()
    assert me["email"] == "new.user@example.com", "email is stored trimmed and lowercased"
    assert me["is_admin"] is False
    assert me["has_profile"] is False

    user = db.scalar(select(User).where(User.email == "new.user@example.com"))
    assert user.preferences is not None and user.preferences.target_minutes == 6
    assert db.scalar(select(Event).where(Event.user_id == user.id, Event.type == "signup"))


def test_signup_existing_email_is_409(db) -> None:
    make_user(db, email="taken@example.com")
    resp = _signup("taken@example.com", "another-password")
    assert resp.status_code == 409
    assert "already exists" in resp.json()["detail"]


def test_signup_existing_email_different_case_is_409(db) -> None:
    assert _signup("case@example.com").status_code == 201
    assert _signup(" CASE@Example.COM").status_code == 409


def test_signup_short_password_is_422(db) -> None:
    assert _signup("short@example.com", "1234567").status_code == 422


def test_signup_invalid_email_is_422(db) -> None:
    assert _signup("not-an-email").status_code == 422


def test_login_after_signup_ignores_email_case(db) -> None:
    assert _signup("mixed@example.com", "correct-horse").status_code == 201
    resp = client.post(
        "/auth/login", json={"email": "Mixed@Example.com ", "password": "correct-horse"}
    )
    assert resp.status_code == 200, resp.text
