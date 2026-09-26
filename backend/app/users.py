"""Creating a user account. Shared by `cli seed-users` and `POST /auth/signup`
so a new user's defaults (empty profile, 6 min, default hosts, UTC) are
defined in one place (docs/DECISIONS.md D-47)."""

from sqlalchemy.orm import Session

from app.auth import hash_password
from app.config import get_settings
from app.models import Preferences, User


def create_user(
    db: Session, email: str, password: str, *, is_admin: bool = False, is_synthetic: bool = False
) -> User:
    """Adds the user and their default preferences row and flushes; the
    caller commits. Does not check for an existing email -- callers do, and
    the unique index on users.email is the backstop."""
    settings = get_settings()
    user = User(
        email=email,
        password_hash=hash_password(password),
        is_admin=is_admin,
        is_synthetic=is_synthetic,
    )
    db.add(user)
    db.flush()
    db.add(
        Preferences(
            user_id=user.id,
            interest_profile={"topics": [], "avoid": []},
            target_minutes=6,
            host_a={"name": "Alex", "voice_id": settings.default_voice_host_a},
            host_b={"name": "Sam", "voice_id": settings.default_voice_host_b},
            timezone="UTC",
        )
    )
    db.flush()
    return user
