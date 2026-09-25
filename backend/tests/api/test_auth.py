from tests.api.conftest import auth_headers, client, login, make_user


def test_login_success_and_me(db) -> None:
    make_user(db, email="alice@example.com")
    token = login("alice@example.com")

    resp = client.get("/me", headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert body["is_admin"] is False


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
