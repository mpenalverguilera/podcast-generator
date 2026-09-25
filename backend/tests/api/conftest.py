"""Fixtures for the API test suite. Uses a plain TestClient(app) (not the
`with TestClient(app) as client:` context-manager form) so the FastAPI
lifespan never runs here -- that would start the real APScheduler thread and
call startup recovery against the shared test DB on every test module import,
which no API test needs (docs/phases/05-api-scheduler.md's own acceptance
only asks for a *manual* scheduler check, not an automated one). Scheduler
logic itself is covered directly in tests/test_scheduler.py, which calls its
functions without ever starting the scheduler thread."""

from fastapi.testclient import TestClient
from passlib.context import CryptContext
from sqlalchemy import select

from app.main import app
from app.models import Preferences, User

client = TestClient(app)
_pwd_context = CryptContext(schemes=["bcrypt"])


def make_user(db, *, email: str = "user@example.com", is_admin: bool = False) -> User:
    user = User(email=email, password_hash=_pwd_context.hash("password123"), is_admin=is_admin)
    db.add(user)
    db.flush()
    db.add(
        Preferences(
            user_id=user.id,
            interest_profile={"topics": [], "avoid": []},
            target_minutes=6,
            host_a={"name": "Alex", "voice_id": "voice-a"},
            host_b={"name": "Sam", "voice_id": "voice-b"},
            timezone="UTC",
        )
    )
    db.commit()
    db.refresh(user)
    return user


def login(email: str = "user@example.com", password: str = "password123") -> str:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def get_user(db, email: str) -> User:
    return db.scalar(select(User).where(User.email == email))
