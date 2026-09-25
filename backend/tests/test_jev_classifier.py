import copy
import json
from pathlib import Path

import httpx
import pytest

from app.adapters.classifier import get_classifier
from app.adapters.classifier.fallback import FallbackClassifier
from app.adapters.classifier.jev import JevClassifier
from app.config import Settings
from app.models import Article
from app.schemas import InterestProfile, Topic

# A real /v1/evaluate response, captured once against the live Vercel AI Gateway and committed
# with no secrets in it (docs/DECISIONS.md D-38) -- what gets tested is exactly the shape the
# gateway returns, not a hand-guessed one.
FIXTURE = json.loads(
    Path(__file__).parent.joinpath("fixtures/jev_evaluate.json").read_text(encoding="utf-8")
)


class StubClient:
    """Stands in for httpx.Client: records each call, answers with a given response body (the
    real captured fixture by default). No network."""

    def __init__(self, response_body: dict = FIXTURE, status_code: int = 200) -> None:
        self.response_body = response_body
        self.status_code = status_code
        self.calls: list[dict] = []

    def post(self, path: str, *, json: dict) -> httpx.Response:
        self.calls.append({"path": path, "json": json})
        request = httpx.Request("POST", "https://ai-gateway.vercel.sh" + path)
        return httpx.Response(self.status_code, json=self.response_body, request=request)


def _profile() -> InterestProfile:
    return InterestProfile(
        topics=[
            Topic(
                name="Space launches",
                description="launches",
                include=["rockets"],
                exclude=["astrology"],
            )
        ],
        avoid=["celebrity gossip"],
    )


def _article() -> Article:
    return Article(id=1, url_hash="h", url="u", title="Rocket launches", highlights=["It flew."])


def test_fixture_response_maps_to_score_result_and_usage() -> None:
    client = StubClient()
    result, usage = JevClassifier(Settings(ai_gateway_api_key="agw-test"), client=client).score(
        _article(), _profile(), "Space launches", ["Old unrelated headline"]
    )

    assert result.topic == "Space launches"
    assert result.relevance == 1.0  # fixture: choice="Space launches", probabilities[topic]=1
    assert result.newsworthy == pytest.approx(0.44)
    assert result.already_covered is False  # fixture probability 0.04 <= 0.5
    assert result.score == pytest.approx(0.44)

    assert usage.provider == "vercel_gateway"
    assert usage.model == "typesafe-ai/jev"
    assert usage.units_in == 742
    assert usage.units_out == 71
    assert usage.cost_usd == pytest.approx(0.000031164)
    assert usage.cost_is_estimate is False
    assert usage.request_id == "gen_01M3AMH8T0EMMD94N6ZGHAKKYG"

    sent = client.calls[0]["json"]
    assert sent["model"] == "typesafe-ai/jev"
    assert sent["questions"]["topic"]["criteria"]["none"].startswith("Not a genuine match")
    assert sent["state"]["avoid"] == ["celebrity gossip"]
    assert sent["state"]["recent_headlines"] == ["Old unrelated headline"]


def test_none_choice_forces_relevance_zero() -> None:
    body = copy.deepcopy(FIXTURE)
    body["answers"]["topic"] = {
        "type": "choice",
        "choice": "none",
        "probabilities": {"Space launches": 0.3, "none": 0.7},
    }
    client = StubClient(response_body=body)
    result, _ = JevClassifier(Settings(ai_gateway_api_key="agw-test"), client=client).score(
        _article(), _profile(), "Space launches", []
    )
    # Forced to 0 even though "Space launches" still held nonzero probability mass.
    assert result.relevance == 0.0
    assert result.score == 0.0


def test_missing_key_raises() -> None:
    with pytest.raises(RuntimeError, match="AI_GATEWAY_API_KEY"):
        JevClassifier(Settings(ai_gateway_api_key=None))


def test_factory_returns_jev_wrapped_in_fallback() -> None:
    """D-39: classifier_provider="jev" returns Jev wrapped in a per-article fallback to Luna,
    not a bare JevClassifier -- so a Jev outage degrades one candidate's score, not the stage."""
    settings = Settings(classifier_provider="jev", ai_gateway_api_key="agw-test")
    classifier = get_classifier(settings)
    assert isinstance(classifier, FallbackClassifier)
    assert isinstance(classifier._primary, JevClassifier)
