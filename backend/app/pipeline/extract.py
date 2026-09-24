from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.models import Episode
from app.schemas import Usage


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    _, usage = adapters.search.get_contents(["https://example.com/stub"])
    return usage
