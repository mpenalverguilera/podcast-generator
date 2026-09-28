from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.adapters import Adapters
from app.models import Article, ArticleScore, EpisodeItem
from app.pipeline import rank
from app.pipeline.rank import Candidate, _depth_for, recency_decay, select_stories
from app.schemas import ArticleScoreResult, InterestProfile, Topic, Usage
from tests.conftest import make_user_with_episode

_NOW = datetime(2026, 9, 24, tzinfo=UTC)


def _candidate(
    article_id: int,
    topic: str,
    relevance: float = 0.9,
    newsworthy: float = 0.9,
    already_covered: bool = False,
    published_at: datetime | None = None,
    is_stale: bool = False,
    depth: str = "headlines",
) -> Candidate:
    return Candidate(
        article_id=article_id,
        topic=topic,
        relevance=relevance,
        newsworthy=newsworthy,
        already_covered=already_covered,
        published_at=published_at if published_at is not None else _NOW,
        is_stale=is_stale,
        depth=depth,  # type: ignore[arg-type]
    )


# Story minutes (D-65): 6 min -> 690 story words / 135 = 5.11 min, per-topic cap max(2.56, 3) = 3;
# 10 min -> 1188 / 135 = 8.8 min, cap 4.4. Headlines cost 1.5 min, deep and focus 3.


def test_recency_decay_halves_every_half_life() -> None:
    assert recency_decay(_NOW, _NOW) == 1.0
    assert recency_decay(_NOW - timedelta(days=3), _NOW) == 0.5
    assert abs(recency_decay(_NOW - timedelta(days=6), _NOW) - 0.25) < 1e-9


def test_recency_decay_treats_missing_date_as_one_half_life_old() -> None:
    assert recency_decay(None, _NOW) == 0.5


def test_dated_article_beats_equally_scored_undated_one() -> None:
    # _candidate's `published_at=None` means "use the default fresh date," not
    # "undated" -- build the undated one directly via the dataclass instead.
    candidates = [
        Candidate(
            article_id=1,
            topic="AI",
            relevance=0.9,
            newsworthy=0.9,
            already_covered=False,
            published_at=None,  # undated -> decay 0.5
        ),
        _candidate(2, "AI", published_at=_NOW),  # dated, same relevance/newsworthy -> decay 1.0
    ]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)
    assert [s.article_id for s in selected] == [2, 1]


def test_deep_stories_take_twice_the_minutes_of_headlines() -> None:
    topics = ["AI", "F1", "Tech", "Rates", "Climate"]
    headlines = [_candidate(i, t) for i, t in enumerate(topics, start=1)]
    deep = [_candidate(i, t, depth="deep") for i, t in enumerate(topics, start=1)]
    assert len(select_stories(headlines, target_minutes=10, now=_NOW)) == 5  # 7.5 of 8.8 min
    assert len(select_stories(deep, target_minutes=10, now=_NOW)) == 3  # 9.0 of 8.8 + 0.25 slack


def test_at_least_two_stories_even_when_the_second_overshoots() -> None:
    candidates = [
        _candidate(1, "focus", depth="deep"),
        _candidate(2, "AI", depth="deep"),
        _candidate(3, "F1", depth="deep"),
    ]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)  # 5.11 min; 2 x 3 = 6
    assert [s.article_id for s in selected] == [1, 2]


def test_depth_for_uses_the_profile_and_treats_focus_as_deep() -> None:
    profile = InterestProfile(
        topics=[Topic(name="AI", description="", depth="deep"), Topic(name="F1", description="")]
    )
    assert _depth_for(profile, "AI") == "deep"
    assert _depth_for(profile, "F1") == "headlines"
    assert _depth_for(profile, "focus") == "deep"
    assert _depth_for(profile, "unknown") == "headlines"


def test_already_covered_and_low_score_are_dropped() -> None:
    candidates = [
        _candidate(1, "AI", already_covered=True),
        _candidate(2, "AI", relevance=0.4, newsworthy=0.4),  # 0.16, below 0.3
        _candidate(3, "AI", relevance=0.9, newsworthy=0.9),  # 0.81, kept
    ]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)
    assert [s.article_id for s in selected] == [3]


def test_focus_item_reserves_the_first_slot_even_when_outscored() -> None:
    candidates = [
        _candidate(1, "AI", relevance=0.95, newsworthy=0.95),
        _candidate(2, "focus", relevance=0.5, newsworthy=0.7),  # lower score, still goes first
    ]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)
    assert selected[0].article_id == 2
    assert selected[0].position == 0


def test_per_topic_cap_enforces_variety() -> None:
    # 6 min: cap 3 min per topic = two headline stories.
    candidates = [_candidate(i, "AI") for i in range(1, 6)]  # 5 strong AI candidates
    candidates += [_candidate(10, "F1", relevance=0.6, newsworthy=0.6)]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)
    ai_selected = [s for s in selected if s.topic == "AI"]
    assert len(ai_selected) == 2
    assert any(s.topic == "F1" for s in selected)


def test_same_article_under_two_topics_is_not_selected_twice() -> None:
    candidates = [
        _candidate(1, "AI", relevance=0.9, newsworthy=0.9),
        _candidate(1, "F1", relevance=0.9, newsworthy=0.9),
    ]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)
    assert len(selected) == 1


def test_story_ids_and_positions_are_sequential() -> None:
    # Distinct topics so the per-topic cap doesn't also filter this down --
    # that's covered separately by test_per_topic_cap_*.
    candidates = [_candidate(1, "AI"), _candidate(2, "F1"), _candidate(3, "Tech")]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)  # 3 x 1.5 of 5.11 min
    assert [s.story_id for s in selected] == ["s1", "s2", "s3"]
    assert [s.position for s in selected] == [0, 1, 2]


def test_stale_candidates_are_never_selected_even_when_top_scored() -> None:
    candidates = [
        _candidate(1, "Football", relevance=1.0, newsworthy=1.0, is_stale=True),
        _candidate(2, "focus", relevance=1.0, newsworthy=1.0, is_stale=True),
        _candidate(3, "Football", relevance=0.7, newsworthy=0.7),
    ]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)
    assert [s.article_id for s in selected] == [3]


def test_every_topic_gets_a_slot_before_any_topic_gets_a_second() -> None:
    # 10 min: 8.8 min, cap 4.4. Pure score order would give AI and Markets every slot, leaving
    # Rates and Climate out entirely.
    candidates = [_candidate(i, "AI", relevance=0.95, newsworthy=0.95) for i in range(1, 5)]
    candidates += [_candidate(i, "Markets", relevance=0.9, newsworthy=0.9) for i in range(10, 13)]
    candidates += [_candidate(20, "Rates", relevance=0.6, newsworthy=0.6)]
    candidates += [_candidate(30, "Climate", relevance=0.56, newsworthy=0.56)]
    selected = select_stories(candidates, target_minutes=10, now=_NOW)

    topics = [s.topic for s in selected]
    assert sorted(set(topics)) == ["AI", "Climate", "Markets", "Rates"]
    # Coverage takes 6 min; the leftover goes by score until the cap / budget stop it.
    assert topics.count("AI") == 2
    assert topics.count("Markets") == 2


def test_coverage_prefers_stronger_topics_when_slots_run_out() -> None:
    # 6 min fits three headline stories (4.5 of 5.11 min) but there are four topics: the three
    # with the best top candidate win.
    candidates = [
        _candidate(1, "Weak", relevance=0.56, newsworthy=0.56),
        _candidate(2, "Strong", relevance=0.95, newsworthy=0.95),
        _candidate(3, "Strong", relevance=0.94, newsworthy=0.94),
        _candidate(4, "Mid", relevance=0.8, newsworthy=0.8),
        _candidate(5, "Good", relevance=0.9, newsworthy=0.9),
    ]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)
    assert [s.article_id for s in selected] == [2, 5, 4]


def test_focus_stays_first_and_topic_coverage_follows() -> None:
    candidates = [
        _candidate(1, "AI", relevance=0.95, newsworthy=0.95),
        _candidate(2, "AI", relevance=0.94, newsworthy=0.94),
        _candidate(3, "F1", relevance=0.6, newsworthy=0.6),
        _candidate(4, "focus", relevance=0.6, newsworthy=0.6, depth="deep"),
    ]
    # 8 min = 7.04 story minutes: focus 3 + AI 1.5 + F1 1.5 = 6.0, and AI's second story
    # (7.5) no longer fits.
    selected = select_stories(candidates, target_minutes=8, now=_NOW)
    # Focus first; coverage gives F1 a slot although AI's second story outscores it; after the
    # focus slot, stories run in score order.
    assert [s.article_id for s in selected] == [4, 1, 3]


def test_coverage_skips_ineligible_candidates_and_keeps_the_cap() -> None:
    # A topic whose only candidates are stale, already covered or below 0.3 gets no slot, and
    # the fill step still respects the per-topic cap (6 min -> 3 min = two headline stories).
    candidates = [_candidate(i, "AI") for i in range(1, 7)]
    candidates += [
        _candidate(10, "Rates", is_stale=True),
        _candidate(11, "Rates", already_covered=True),
        _candidate(12, "Rates", relevance=0.4, newsworthy=0.4),
        _candidate(20, "F1", relevance=0.6, newsworthy=0.6),
    ]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)
    topics = [s.topic for s in selected]
    assert "Rates" not in topics
    assert topics.count("AI") == 2
    assert topics.count("F1") == 1
    assert len(selected) == 3  # AI is capped and nothing else is eligible


class _StaleStubClassifier:
    """Marks articles whose title contains "stale" as stale; records the window it was given."""

    def __init__(self) -> None:
        self.windows: list[datetime] = []

    def score(self, article, profile, topic, recent_headlines, window_start):
        self.windows.append(window_start)
        result = ArticleScoreResult(
            topic=topic,
            relevance=0.9,
            newsworthy=0.9,
            score=0.81,
            is_stale="stale" in (article.title or ""),
        )
        return result, Usage(provider="fake", usage_source="fake")


def test_run_passes_the_episode_window_and_drops_stale_articles(db) -> None:
    episode = make_user_with_episode(db)
    titles = ["fresh one", "stale match from February", "fresh two"]
    for i, title in enumerate(titles):
        article = Article(
            url_hash=f"h{i}",
            url=f"https://example.com/{i}",
            title=title,
            published_at=datetime.now(UTC),
        )
        db.add(article)
        db.flush()
        db.add(ArticleScore(episode_id=episode.id, article_id=article.id, topic="AI"))
    db.flush()
    classifier = _StaleStubClassifier()
    adapters = Adapters(search=None, llm=None, classifier=classifier, tts=None)

    rank.run(episode, adapters, db)

    assert classifier.windows == [episode.window_start] * 3
    items = db.scalars(select(EpisodeItem).where(EpisodeItem.episode_id == episode.id)).all()
    assert {db.get(Article, item.article_id).title for item in items} == {"fresh one", "fresh two"}
