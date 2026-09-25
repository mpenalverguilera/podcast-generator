import time
from typing import TYPE_CHECKING

import httpx

from app.config import Settings, get_settings
from app.pricing import cost_for
from app.schemas import ArticleScoreResult, InterestProfile, Usage

if TYPE_CHECKING:
    from app.models import Article

# Jev (TypeSafe) is only reachable through Vercel's AI Gateway, not TypeSafe's own API -- the
# TYPESAFE_API_KEY/typesafe-sdk integration in docs/DECISIONS.md D-32 was hitting the wrong
# service entirely, hence its 401. See D-33 and
# https://vercel.com/docs/ai-gateway/modalities/evaluation for the request/response shape.
_BASE_URL = "https://ai-gateway.vercel.sh"
_EVALUATE_PATH = "/v1/evaluate"

_NEWSWORTHY_CRITERIA = {
    "true": "It reports a specific new event or development.",
    "false": "It is PR fluff, a listicle, a product roundup or an evergreen explainer.",
}
_ALREADY_COVERED_CRITERIA = {
    "true": "Same story and angle as one of the recent headlines.",
    "false": "A new story, or a meaningfully different angle on an old one.",
}


def _topic_criterion(name: str, description: str, include: list[str], exclude: list[str]) -> str:
    """One `criteria` value for the `topic` choice question. Vercel's choice primitive takes a
    flat name -> string map (see the docs), so include/exclude are folded into the string here
    rather than sent as nested state, matching what LLMClassifier's prompt already conveys."""
    parts = [description]
    if include:
        parts.append(f"Include: {', '.join(include)}.")
    if exclude:
        parts.append(f"Exclude: {', '.join(exclude)}.")
    return " ".join(parts)


def _build_request(
    model: str,
    article: "Article",
    profile: InterestProfile,
    recent_headlines: list[str],
) -> dict:
    state = {
        "title": article.title or "(no title)",
        "outlet": article.outlet or "unknown",
        "published_at": article.published_at.isoformat() if article.published_at else "unknown",
        "highlights": article.highlights or [],
        "topics": {
            t.name: {"description": t.description, "include": t.include, "exclude": t.exclude}
            for t in profile.topics
        },
        "avoid": profile.avoid,
        "recent_headlines": recent_headlines,
    }
    topic_criteria = {
        t.name: _topic_criterion(t.name, t.description, t.include, t.exclude)
        for t in profile.topics
    }
    topic_criteria["none"] = (
        "Not a genuine match for any listed topic, or matches something on the listener's "
        "avoid list."
    )
    questions = {
        "topic": {
            "type": "choice",
            "instructions": (
                "Which of the listed topics (if any) does this article genuinely belong to? A "
                "match requires fitting that topic's description and include list, not its "
                "exclude list, and not the listener's avoid list (see state.avoid)."
            ),
            "criteria": topic_criteria,
        },
        "newsworthy": {
            "type": "boolean",
            "instructions": (
                "Is this article a genuine news story about a real, recent event (funding, "
                "launch, research, policy, results)?"
            ),
            "criteria": _NEWSWORTHY_CRITERIA,
        },
        "already_covered": {
            "type": "boolean",
            "instructions": (
                "Is this the same story and angle as one of the state.recent_headlines the "
                "listener already heard?"
            ),
            "criteria": _ALREADY_COVERED_CRITERIA,
        },
    }
    return {"model": model, "state": state, "questions": questions}


class JevClassifier:
    """Real Classifier backed by TypeSafe's Jev, served through Vercel AI Gateway's evaluation
    API (D-33). One POST per (article, topic): a `choice` question over the profile's topic(s)
    plus "none" gives `relevance` -- rank.py already restricts `profile` to the single topic
    being scored before calling any classifier (D-23/D-25's per-topic re-check), so in practice
    this is a one-topic-vs-"none" choice, not a full re-classification across every topic -- a
    `boolean` gives `newsworthy`, and a second `boolean` gives `already_covered`.
    """

    def __init__(
        self, settings: Settings | None = None, client: httpx.Client | None = None
    ) -> None:
        self._settings = settings or get_settings()
        if client is None:
            if self._settings.ai_gateway_api_key is None:
                raise RuntimeError("AI_GATEWAY_API_KEY is not set; JevClassifier needs it")
            client = httpx.Client(
                base_url=_BASE_URL,
                headers={
                    "Authorization": (
                        f"Bearer {self._settings.ai_gateway_api_key.get_secret_value()}"
                    ),
                    "Content-Type": "application/json",
                },
                timeout=self._settings.jev_timeout_s,
            )
        self._client = client

    def score(
        self,
        article: "Article",
        profile: InterestProfile,
        topic: str,
        recent_headlines: list[str],
    ) -> tuple[ArticleScoreResult, Usage]:
        payload = _build_request(self._settings.model_jev, article, profile, recent_headlines)

        start = time.perf_counter()
        response = self._client.post(_EVALUATE_PATH, json=payload)
        latency_ms = int((time.perf_counter() - start) * 1000)
        response.raise_for_status()
        body = response.json()

        answers = body["answers"]
        topic_answer = answers["topic"]
        chosen = topic_answer["choice"]
        # `topic` is always one of profile.topics's names by the time it reaches a classifier
        # (rank.py's _profile_for_topic synthesizes a matching Topic if the name is missing), so
        # `topic` is always a valid key into `probabilities` -- except when "none" wins, which is
        # forced to 0 regardless of the raw probability mass `topic` still holds.
        relevance = 0.0 if chosen == "none" else topic_answer["probabilities"].get(topic, 0.0)
        newsworthy = answers["newsworthy"]["probability"]
        already_covered = answers["already_covered"]["probability"] > 0.5

        result = ArticleScoreResult(
            topic=topic,
            relevance=relevance,
            newsworthy=newsworthy,
            already_covered=already_covered,
            score=relevance * newsworthy,
        )

        gateway_meta = body.get("providerMetadata", {}).get("gateway", {})
        units_in = body["usage"]["inputTokens"]
        units_out = body["usage"]["outputTokens"]
        cost_usd, is_estimate = cost_for(
            "vercel_gateway",
            body.get("model"),
            units_in,
            units_out,
            market_cost_usd=float(gateway_meta["marketCost"]),
        )
        usage = Usage(
            provider="vercel_gateway",
            model=body.get("model", self._settings.model_jev),
            units_in=units_in,
            units_out=units_out,
            cost_usd=cost_usd,
            cost_is_estimate=is_estimate,
            latency_ms=latency_ms,
            # generationId is Vercel's id for this call, for debugging in the AI Gateway
            # dashboard -- stored where every other adapter's provider_request_id lives.
            request_id=gateway_meta.get("generationId"),
            usage_source="exact",
        )
        return result, usage
