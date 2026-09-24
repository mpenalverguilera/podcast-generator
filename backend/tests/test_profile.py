from app.adapters.llm.fake import FakeLLM
from app.config import Settings
from app.pipeline.profile import GUIDED_QUESTIONS, extract_profile


def test_extract_profile_returns_registry_fixture() -> None:
    answers = {
        "work": "Health tech and AI voice agents.",
        "fun": "Formula 1.",
        "avoid": "Celebrity gossip.",
        "depth": "Deep on AI voice agents, headlines for F1.",
    }

    profile, usage = extract_profile(answers, FakeLLM(), Settings())

    assert "celebrity gossip" in profile.avoid
    assert {t.name for t in profile.topics} == {"AI voice agents", "Formula 1"}
    assert usage.provider == "fake"


def test_extract_profile_skips_blank_answers() -> None:
    # Blank/missing answers must not raise a KeyError -- only answered
    # questions go into the rendered prompt.
    answers = {"work": "Health tech.", "fun": "", "depth": "Deep."}

    profile, _usage = extract_profile(answers, FakeLLM(), Settings())

    assert profile.topics


def test_guided_questions_have_stable_keys() -> None:
    keys = {q["key"] for q in GUIDED_QUESTIONS}
    assert keys == {"work", "fun", "avoid", "depth"}
