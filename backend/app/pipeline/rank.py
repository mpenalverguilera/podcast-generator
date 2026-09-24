from sqlalchemy.orm import Session

from app.adapters import Adapters
from app.models import Article, ContentSource, Episode
from app.schemas import InterestProfile, Usage


def run(episode: Episode, adapters: Adapters, db: Session) -> Usage:
    # Throwaway, unpersisted Article -- just enough to exercise the Classifier
    # protocol's real/fake wiring. Real candidate scoring lands in phase 02/03.
    placeholder = Article(
        url_hash="stub",
        url="https://example.com/stub",
        title="Stub article",
        highlights=["stub highlight"],
        content_source=ContentSource.HIGHLIGHTS,
    )
    _, usage = adapters.classifier.score(placeholder, InterestProfile(), recent_headlines=[])
    return usage
