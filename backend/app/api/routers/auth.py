import logging

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.schemas import LoginRequest, MeResponse, SignupRequest, TokenResponse
from app.auth import create_access_token, current_user, verify_password
from app.db import get_db
from app.models import Event, User
from app.users import create_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

EMAIL_TAKEN = "an account with this email already exists"


@router.post("/auth/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    user = db.scalar(select(User).where(User.email == body.email))
    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid email or password")
    logger.info("login: user %s", user.id)
    db.add(Event(user_id=user.id, type="login", is_synthetic=user.is_synthetic))
    db.commit()
    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/auth/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Open self-service registration; returns a token so the new user is
    signed in straight away. A taken email is a 409 (D-47)."""
    if db.scalar(select(User.id).where(User.email == body.email)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN)
    try:
        user = create_user(db, body.email, body.password)
        db.add(Event(user_id=user.id, type="signup", is_synthetic=False))
        db.commit()
    except IntegrityError as exc:
        # Two signups for the same email racing past the check above: the
        # unique index on users.email lets exactly one through.
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, EMAIL_TAKEN) from exc
    logger.info("signup: user %s", user.id)
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
