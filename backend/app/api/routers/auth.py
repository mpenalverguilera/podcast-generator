import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.schemas import LoginRequest, MeResponse, TokenResponse
from app.auth import create_access_token, current_user, verify_password
from app.db import get_db
from app.models import Event, User

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    logger.info("login: user %s", user.id)
    db.add(Event(user_id=user.id, type="login", is_synthetic=user.is_synthetic))
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=MeResponse)
def me(user: User = Depends(current_user)) -> MeResponse:
    profile = (user.preferences.interest_profile or {}) if user.preferences else {}
    return MeResponse(
        id=user.id,
        email=user.email,
        is_admin=user.is_admin,
        has_profile=bool(profile.get("topics")),
    )
