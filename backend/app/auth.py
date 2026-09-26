"""JWT auth for the API (docs/phases/05-api-scheduler.md step 1). Password
hashing lives here only: app/users.create_user (used by both the CLI's
seed-users and POST /auth/signup) hashes with hash_password below."""

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
MEDIA_TOKEN_EXPIRES_HOURS = 1

pwd_context = CryptContext(schemes=["bcrypt"])
_bearer_scheme = HTTPBearer(auto_error=False)


def hash_password(plain_password: str) -> str:
    return pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return pwd_context.verify(plain_password, password_hash)


def create_access_token(user_id: int) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {"sub": str(user_id), "iat": now, "exp": now + timedelta(hours=JWT_EXPIRES_HOURS)}
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def create_media_token(kind: str, ref: str | int) -> str:
    """Short-lived token for one media file, carried in a URL query param
    because a native <audio src> can't send an Authorization header. It has
    no `sub`, so it can never pass current_user, and it is scoped to one
    file, so a leaked URL exposes that file for an hour and nothing else.
    docs/DECISIONS.md D-40."""
    settings = get_settings()
    now = datetime.now(UTC)
    payload = {
        "media": kind,
        "ref": str(ref),
        "iat": now,
        "exp": now + timedelta(hours=MEDIA_TOKEN_EXPIRES_HOURS),
    }
    return jwt.encode(payload, settings.jwt_secret.get_secret_value(), algorithm=JWT_ALGORITHM)


def verify_media_token(token: str, kind: str, ref: str | int) -> None:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token, settings.jwt_secret.get_secret_value(), algorithms=[JWT_ALGORITHM]
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid or expired media token") from exc
    if payload.get("media") != kind or payload.get("ref") != str(ref):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "media token is not for this file")


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

    sub = payload.get("sub")  # a media token has none (create_media_token)
    user = db.get(User, int(sub)) if sub else None
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
