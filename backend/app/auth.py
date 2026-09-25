"""JWT auth for the API (docs/phases/05-api-scheduler.md step 1). Password
hashing reuses the same passlib CryptContext the CLI's seed-users command
already uses (app/cli.py), so a seeded user's hash verifies here unchanged."""

from datetime import UTC, datetime, timedelta

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Episode, User

JWT_ALGORITHM = "HS256"
JWT_EXPIRES_HOURS = 12

pwd_context = CryptContext(schemes=["bcrypt"])
_bearer_scheme = HTTPBearer(auto_error=False)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=JWT_EXPIRES_HOURS)}
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "not authenticated")
    settings = get_settings()
    try:
        payload = jwt.decode(
            credentials.credentials,
            settings.jwt_secret.get_secret_value(),
            algorithms=[JWT_ALGORITHM],
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired token") from exc

    user = db.get(User, int(payload["sub"]))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user


def require_owner_or_admin(episode: Episode, user: User) -> None:
    """Cross-user access is 403, not 404: this is an internal take-home
    project, not a product where hiding another user's episode ids matters,
    and a clear 403 is more debuggable than a misleading 404."""
    if not user.is_admin and episode.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "not your episode")
