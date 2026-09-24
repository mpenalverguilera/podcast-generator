from types import SimpleNamespace

import pytest

from app.adapters.classifier import get_classifier
from app.adapters.classifier.jev import JevClassifier
from app.config import Settings
from app.models import Article
from app.schemas import InterestProfile, Topic


class StubClient:
    """Stands in for TypeSafeClient: records the call, answers every Noul it
    was asked with a fixed probability. No network."""

    def __init__(self, probs: dict[str, float], input_tokens: int = 1000) -> None:
        self.probs = probs
        self.input_tokens = input_tokens
        self.calls: list[dict] = []

    def system_one(self, state, questions, *, model):
        self.calls.append({"state": state, "questions": questions, "model": model})
        return SimpleNamespace(
            model=model,
            request_id="req-test",
            usage=SimpleNamespace(input_tokens=self.input_tokens, output_tokens=12),
            nouls={name: SimpleNamespace(noul=self.probs[name]) for name in questions},
        )


def _profile() -> InterestProfile:
    return InterestProfile(
        topics=[
            Topic(name="space", description="launches", include=["rockets"], exclude=["astrology"])
        ],
        avoid=["celebrity gossip"],
    )


def _article() -> Article:
    return Article(id=1, url_hash="h", url="u", title="Rocket launches", highlights=["It flew."])


def test_nouls_map_to_score_result_and_usage() -> None:
    client = StubClient({"relevant": 0.9, "newsworthy": 0.5})
    result, usage = JevClassifier(Settings(), client=client).score(
        _article(), _profile(), "space", []
    )

    assert result.topic == "space"
    assert result.relevance == 0.9
    assert result.newsworthy == 0.5
    assert result.score == pytest.approx(0.45)
    assert result.already_covered is False

    assert usage.provider == "typesafe"
    assert usage.model == "jev-1.13.0"
    assert usage.units_in == 1000
    assert usage.cost_usd == pytest.approx(1000 * 0.042 / 1_000_000)
    assert usage.cost_is_estimate is False
    assert usage.request_id == "req-test"

    state = client.calls[0]["state"]
    assert state["topic"]["exclude"] == ["astrology"]
    assert state["avoid"] == ["celebrity gossip"]


def test_already_covered_asked_only_with_recent_headlines() -> None:
    client = StubClient({"relevant": 0.9, "newsworthy": 0.9, "already_covered": 0.8})
    classifier = JevClassifier(Settings(), client=client)

    classifier.score(_article(), _profile(), "space", [])
    assert "already_covered" not in client.calls[0]["questions"]

    result, _ = classifier.score(_article(), _profile(), "space", ["Rocket launches"])
    assert "already_covered" in client.calls[1]["questions"]
    assert result.already_covered is True


def test_missing_key_raises() -> None:
    with pytest.raises(RuntimeError, match="TYPESAFE_API_KEY"):
        JevClassifier(Settings(typesafe_api_key=None))


def test_factory_returns_jev() -> None:
    settings = Settings(classifier_provider="jev", typesafe_api_key="ts-test")
    assert isinstance(get_classifier(settings), JevClassifier)
