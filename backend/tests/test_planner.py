from app.adapters import Adapters
from app.adapters.llm.fake import FakeLLM
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
