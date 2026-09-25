from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.schemas import EventCreate
from app.auth import current_user, require_owner_or_admin
from app.db import get_db
from app.models import Episode, Event, User

router = APIRouter(tags=["events"])


@router.post("/events", status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Player telemetry and ratings (ARCHITECTURE §7): play_started,
    play_progress (client sends one every 15s with position_s), play_completed,
    episode_rated (+1/-1). Type and payload shape are validated by EventCreate;
    the episode must be the caller's own, so nobody can add plays or ratings
    to someone else's episode and skew the phase-07 metrics."""
    episode = db.get(Episode, body.episode_id)
    if episode is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "episode not found")
    require_owner_or_admin(episode, user)

    event = Event(
        user_id=user.id,
        episode_id=body.episode_id,
        type=body.type,
        payload=body.payload,
        is_synthetic=user.is_synthetic,
    )
    db.add(event)
    db.commit()
    return {"id": event.id}
