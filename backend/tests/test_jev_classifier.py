import json
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from app.adapters.classifier import get_classifier, jev
from app.adapters.classifier.fallback import FallbackClassifier
from app.adapters.classifier.jev import JevClassifier, JevRateLimited
from app.config import Settings
from app.models import Article
from app.schemas import InterestProfile, Topic

# A /v1/evaluate response in the `score`-question shape jev.v2 asks for (docs/DECISIONS.md D-45):
# the envelope (usage, providerMetadata) is a real captured response, the `answers` block is written
# from Vercel's documented `score` answer shape (score + per-rung probabilities). No secrets in it.
FIXTURE = json.loads(
    Path(__file__).parent.joinpath("fixtures/jev_evaluate.json").read_text(encoding="utf-8")
)
SETTINGS = Settings(ai_gateway_api_key="agw-test", jev_max_attempts=3)
_WINDOW = datetime(2026, 9, 20, tzinfo=UTC)


@pytest.fixture(autouse=True)
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """No real waiting, and no Jev pause leaking between tests; returns every sleep requested."""
    recorded: list[float] = []
    monkeypatch.setattr(jev.time, "sleep", recorded.append)
    monkeypatch.setattr(jev, "_cooldown_until", 0.0)
    return recorded


def _client(
    statuses: list[int | tuple[int, dict[str, str]]], requests: list[httpx.Request]
) -> tuple[httpx.Client, Callable[[], int]]:
    """A real httpx.Client over a MockTransport (no network) that answers each POST with the next
    entry in `statuses` -- a status, or (status, headers) -- the fixture body on 200."""
    remaining = list(statuses)

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        entry = remaining.pop(0)
        status, headers = entry if isinstance(entry, tuple) else (entry, {})
        body = FIXTURE if status == 200 else {"error": "x"}
        return httpx.Response(status, json=body, headers=headers)

    client = httpx.Client(
        base_url="https://ai-gateway.vercel.sh", transport=httpx.MockTransport(handler)
    )
    return client, lambda: len(requests)


def _profile() -> InterestProfile:
    return InterestProfile(
        topics=[
            Topic(
                name="Space launches",
                description="launches",
                include=["rockets"],
                exclude=["astrology"],
            ),
            Topic(name="Board games", description="tabletop"),
        ],
        avoid=["celebrity gossip"],
    )


def _article() -> Article:
    return Article(id=1, url_hash="h", url="u", title="Rocket launches", highlights=["It flew."])


def test_score_answers_are_normalized_and_usage_is_exact() -> None:
    requests: list[httpx.Request] = []
    client, _ = _client([200], requests)
    result, usage = JevClassifier(SETTINGS, client=client).score(
        _article(), _profile(), "Space launches", ["Old unrelated headline"], _WINDOW
    )

    assert result.topic == "Space launches"
    assert result.relevance == pytest.approx(3.72 / 4)  # 5 rungs -> score / 4
    assert result.newsworthy == pytest.approx(2.61 / 3)  # 4 rungs -> score / 3
    assert result.score == pytest.approx(result.relevance * result.newsworthy)
    assert result.already_covered is False  # fixture probability 0.04 <= 0.5
    assert result.is_stale is False  # jev.v2 has no staleness question (D-61)

    assert usage.provider == "vercel_gateway"
    assert usage.model == "typesafe-ai/jev"
    assert (usage.units_in, usage.units_out) == (742, 71)
    assert usage.cost_usd == pytest.approx(0.000031164)
    assert usage.cost_is_estimate is False
    assert usage.request_id == "gen_01M3AMH8T0EMMD94N6ZGHAKKYG"


def test_request_scores_only_the_one_topic_with_graded_questions() -> None:
    requests: list[httpx.Request] = []
    client, _ = _client([200], requests)
    JevClassifier(SETTINGS, client=client).score(
        _article(), _profile(), "Space launches", ["Old unrelated headline"], _WINDOW
    )

    sent = json.loads(requests[0].content)
    assert sent["model"] == "typesafe-ai/jev"
    assert sent["state"]["topic"]["name"] == "Space launches"
    assert sent["state"]["topic"]["exclude"] == ["astrology"]
    assert "Board games" not in json.dumps(sent["state"])  # other topics are scored separately
    assert sent["state"]["avoid"] == ["celebrity gossip"]
    assert sent["state"]["recent_headlines"] == ["Old unrelated headline"]
    assert sent["questions"]["relevance"]["type"] == "score"
    assert len(sent["questions"]["relevance"]["criteria"]) == 5
    assert sent["questions"]["newsworthy"]["type"] == "score"
    assert len(sent["questions"]["newsworthy"]["criteria"]) == 4
    assert sent["questions"]["already_covered"]["type"] == "boolean"


@pytest.mark.parametrize("server_error", [502, 503, 504])
def test_server_errors_are_retried_with_backoff(server_error: int, sleeps: list[float]) -> None:
    requests: list[httpx.Request] = []
    client, count = _client([server_error, server_error, 200], requests)
    result, _ = JevClassifier(SETTINGS, client=client).score(
        _article(), _profile(), "Space launches", [], _WINDOW
    )
    assert count() == 3
    assert sleeps == [0.5, 1.0]
    assert result.relevance > 0


def test_server_error_gives_up_after_max_attempts() -> None:
    requests: list[httpx.Request] = []
    client, count = _client([503, 503, 503], requests)
    with pytest.raises(httpx.HTTPStatusError):
        JevClassifier(SETTINGS, client=client).score(
            _article(), _profile(), "Space launches", [], _WINDOW
        )
    assert count() == 3


def test_short_retry_after_is_honored(sleeps: list[float]) -> None:
    requests: list[httpx.Request] = []
    client, count = _client(
        [(503, {"retry-after": "2"}), (429, {"retry-after": "1"}), 200], requests
    )
    JevClassifier(SETTINGS, client=client).score(
        _article(), _profile(), "Space launches", [], _WINDOW
    )
    assert count() == 3
    assert sleeps == [2.0, 1.0]


def test_429_pauses_jev_without_further_calls() -> None:
    requests: list[httpx.Request] = []
    client, count = _client([429], requests)
    classifier = JevClassifier(SETTINGS, client=client)
    with pytest.raises(JevRateLimited):
        classifier.score(_article(), _profile(), "Space launches", [], _WINDOW)
    assert count() == 1
    assert jev.cooldown_remaining_s() == pytest.approx(300, abs=5)

    # While paused, calls fail fast with no HTTP request, so FallbackClassifier moves on to Luna.
    with pytest.raises(JevRateLimited):
        classifier.score(_article(), _profile(), "Space launches", [], _WINDOW)
    assert count() == 1


def test_long_retry_after_on_429_extends_the_pause() -> None:
    requests: list[httpx.Request] = []
    client, _ = _client([(429, {"retry-after": "600"})], requests)
    with pytest.raises(JevRateLimited):
        JevClassifier(SETTINGS, client=client).score(
            _article(), _profile(), "Space launches", [], _WINDOW
        )
    assert jev.cooldown_remaining_s() == pytest.approx(600, abs=5)


def test_calls_resume_once_the_pause_is_over(monkeypatch: pytest.MonkeyPatch) -> None:
    requests: list[httpx.Request] = []
    client, count = _client([429, 200], requests)
    classifier = JevClassifier(SETTINGS, client=client)
    with pytest.raises(JevRateLimited):
        classifier.score(_article(), _profile(), "Space launches", [], _WINDOW)
    monkeypatch.setattr(jev, "_cooldown_until", 0.0)  # the 5 minutes have passed
    result, _ = classifier.score(_article(), _profile(), "Space launches", [], _WINDOW)
    assert count() == 2
    assert result.relevance > 0


def test_retry_after_accepts_an_http_date() -> None:
    response = httpx.Response(429, headers={"retry-after": "Wed, 21 Oct 2099 07:28:00 GMT"})
    assert jev._retry_after_s(response) > 3600
    assert jev._retry_after_s(httpx.Response(429, headers={"retry-after": "soon"})) is None
    assert jev._retry_after_s(httpx.Response(429)) is None


def test_client_errors_are_not_retried() -> None:
    requests: list[httpx.Request] = []
    client, count = _client([400], requests)
    with pytest.raises(httpx.HTTPStatusError):
        JevClassifier(SETTINGS, client=client).score(
            _article(), _profile(), "Space launches", [], _WINDOW
        )
    assert count() == 1


def test_missing_key_raises() -> None:
    with pytest.raises(RuntimeError, match="AI_GATEWAY_API_KEY"):
        JevClassifier(Settings(ai_gateway_api_key=None))


def test_factory_returns_jev_wrapped_in_fallback() -> None:
    """D-44: classifier_provider="jev" returns Jev wrapped in a per-article fallback to Luna,
    not a bare JevClassifier -- so a Jev outage degrades one candidate's score, not the stage."""
    settings = Settings(classifier_provider="jev", ai_gateway_api_key="agw-test")
    classifier = get_classifier(settings)
    assert isinstance(classifier, FallbackClassifier)
    assert isinstance(classifier._primary, JevClassifier)
