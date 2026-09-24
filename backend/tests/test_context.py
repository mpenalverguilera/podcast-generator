from datetime import UTC, datetime, timedelta

from app.models import (
    Article,
    Episode,
    EpisodeItem,
    EpisodeStatus,
    EpisodeTrigger,
    Preferences,
    User,
)
from app.pipeline import context


def test_recent_headlines_excludes_self_and_limits_to_two(db) -> None:
    user = User(email="headlines@example.com", password_hash="x", is_admin=False, is_synthetic=True)
    db.add(user)
    db.flush()
    db.add(Preferences(user_id=user.id, host_a={"name": "Alex"}, host_b={"name": "Sam"}))

    now = datetime.now(UTC)

    def _ready_episode_with_headline(title: str, ready_at: datetime) -> Episode:
        ep = Episode(
            user_id=user.id,
            status=EpisodeStatus.READY,
            trigger=EpisodeTrigger.MANUAL,
            window_start=ready_at - timedelta(days=7),
            target_minutes=6,
            ready_at=ready_at,
        )
        db.add(ep)
        db.flush()
        article = Article(url_hash=f"hash-{title}", url=f"https://example.com/{title}", title=title)
        db.add(article)
        db.flush()
        db.add(EpisodeItem(episode_id=ep.id, article_id=article.id, position=0, story_id="s1"))
        return ep

    _oldest = _ready_episode_with_headline("oldest story", now - timedelta(days=21))
    _middle = _ready_episode_with_headline("middle story", now - timedelta(days=14))
    _newest = _ready_episode_with_headline("newest story", now - timedelta(days=7))
    current = _ready_episode_with_headline("current episode's own story", now)
    db.commit()

    headlines = context.recent_headlines(db, current)

    assert set(headlines) == {"newest story", "middle story"}


def test_load_profile_defaults_to_empty(db) -> None:
    user = User(
        email="empty-profile@example.com", password_hash="x", is_admin=False, is_synthetic=True
    )
    db.add(user)
    db.flush()
    db.add(Preferences(user_id=user.id, host_a={"name": "Alex"}, host_b={"name": "Sam"}))
    db.commit()

    profile = context.load_profile(db, user.id)

    assert profile.topics == []
    assert profile.avoid == []
