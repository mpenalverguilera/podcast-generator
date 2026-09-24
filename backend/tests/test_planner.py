from datetime import UTC, datetime, timedelta

from app.adapters import Adapters
from app.adapters.llm.fake import FakeLLM
from app.models import (
    Article,
    Episode,
    EpisodeItem,
    EpisodeStatus,
    EpisodeTrigger,
    Preferences,
    User,
)
from app.pipeline import planner
from tests.conftest import make_user_with_episode

_ADAPTERS = Adapters(search=None, llm=FakeLLM(), classifier=None, tts=None)  # type: ignore[arg-type]


def test_run_stores_planned_queries_and_prompt_version(db) -> None:
    episode = make_user_with_episode(db)

    usage = planner.run(episode, _ADAPTERS, db)

    assert usage.provider == "fake"
    assert episode.planned_queries
    assert episode.prompt_versions == {"query_planner": 1}
    assert all({"topic", "query", "is_focus"} <= q.keys() for q in episode.planned_queries)


def test_focus_queries_flagged(db) -> None:
    episode = make_user_with_episode(db)

    planner.run(episode, _ADAPTERS, db)

    focus_queries = [q for q in episode.planned_queries if q["is_focus"]]
    non_focus_queries = [q for q in episode.planned_queries if not q["is_focus"]]
    assert focus_queries
    assert non_focus_queries


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

    headlines = planner._recent_headlines(db, current)

    assert set(headlines) == {"newest story", "middle story"}
