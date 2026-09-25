from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.schemas import EventCreate
from app.auth import current_user
from app.db import get_db
from app.models import Event, User

router = APIRouter(tags=["events"])


@router.post("/events", status_code=status.HTTP_201_CREATED)
def create_event(
    body: EventCreate, user: User = Depends(current_user), db: Session = Depends(get_db)
) -> dict:
    """Player telemetry and ratings (ARCHITECTURE §7): play_started,
    play_progress (client sends one every 15s with position in the payload),
    play_completed, episode_rated (+1/-1). No validation beyond auth -- this
    is a fire-and-forget analytics sink, not a state machine."""
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
