from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.models import Episode
from app.schemas import Turn, Usage


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    turns = [
        Turn(speaker="host_a", text="This is a stub turn."),
        Turn(speaker="host_b", text="Agreed."),
    ]
    _, usage = adapters.tts.synthesize_chunk(turns, seed=episode.id)
    return usage
