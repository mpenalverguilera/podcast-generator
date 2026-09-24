from datetime import UTC, datetime, timedelta

from app.pipeline.rank import Candidate, recency_decay, select_stories, story_count_for

_NOW = datetime(2026, 9, 24, tzinfo=UTC)


def _candidate(
    article_id: int,
    topic: str,
    relevance: float = 0.9,
    newsworthy: float = 0.9,
    already_covered: bool = False,
    published_at: datetime | None = None,
) -> Candidate:
    return Candidate(
        article_id=article_id,
        topic=topic,
        relevance=relevance,
        newsworthy=newsworthy,
        already_covered=already_covered,
        published_at=published_at if published_at is not None else _NOW,
    )


def test_recency_decay_halves_every_half_life() -> None:
    assert recency_decay(_NOW, _NOW) == 1.0
    assert recency_decay(_NOW - timedelta(days=3), _NOW) == 0.5
    assert abs(recency_decay(_NOW - timedelta(days=6), _NOW) - 0.25) < 1e-9


def test_recency_decay_treats_missing_date_as_fresh() -> None:
    assert recency_decay(None, _NOW) == 1.0


def test_story_count_floors_at_three() -> None:
    assert story_count_for(1) == 3
    assert story_count_for(6) == 5
    assert story_count_for(12) == 10


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
    # target_minutes=6 -> story_count=5, per_topic_cap=ceil(5/2)=3.
    candidates = [_candidate(i, "AI") for i in range(1, 6)]  # 5 strong AI candidates
    candidates += [_candidate(10, "F1", relevance=0.6, newsworthy=0.6)]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)
    ai_selected = [s for s in selected if s.topic == "AI"]
    assert len(ai_selected) == 3
    assert any(s.topic == "F1" for s in selected)


def test_same_article_under_two_topics_is_not_selected_twice() -> None:
    candidates = [
        _candidate(1, "AI", relevance=0.9, newsworthy=0.9),
        _candidate(1, "F1", relevance=0.9, newsworthy=0.9),
    ]
    selected = select_stories(candidates, target_minutes=6, now=_NOW)
    assert len(selected) == 1


def test_story_ids_and_positions_are_sequential() -> None:
    # Distinct topics so the per-topic cap (ceil(3/2)=2) doesn't also filter
    # this down -- that's covered separately by test_per_topic_cap_*.
    candidates = [_candidate(1, "AI"), _candidate(2, "F1"), _candidate(3, "Tech")]
    selected = select_stories(candidates, target_minutes=1, now=_NOW)  # story_count=3
    assert [s.story_id for s in selected] == ["s1", "s2", "s3"]
    assert [s.position for s in selected] == [0, 1, 2]
