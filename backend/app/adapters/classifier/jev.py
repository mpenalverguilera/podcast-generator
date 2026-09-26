import logging
import threading
import time
from email.utils import parsedate_to_datetime
from typing import TYPE_CHECKING

import httpx

from app.adapters.classifier.openai import topic_for
from app.config import Settings, get_settings
from app.pricing import cost_for
from app.schemas import ArticleScoreResult, InterestProfile, Usage

if TYPE_CHECKING:
    from app.models import Article

logger = logging.getLogger(__name__)

# Jev (TypeSafe) is only reachable through Vercel's AI Gateway, not TypeSafe's own API -- see
# docs/DECISIONS.md D-40 and https://vercel.com/docs/ai-gateway/modalities/evaluation for the
# request/response shape.
_BASE_URL = "https://ai-gateway.vercel.sh"
_EVALUATE_PATH = "/v1/evaluate"

# Jev takes typed questions, not a rendered text prompt, so its "prompt" lives here rather than in
# app/prompts/*.vN.md (D-39). Bump this whenever the questions or state below change: the eval
# notebook tags every cached score with it, so a change re-scores instead of reusing stale rows.
# v1 (D-40): relevance as a topic-vs-"none" `choice`, newsworthy as a `boolean`.
# v2 (D-42): both as graded `score` questions about the single topic being scored.
JEV_PROMPT_VERSION = "jev.v2"

# `score` criteria are ordered lowest -> highest; Jev returns an interpolated `score` in
# [0, len - 1], normalized to 0-1 below. Definitions follow classifier.v1.md (what Luna/Sol get)
# and the D-41 label rules.
_RELEVANCE_RUNGS = [
    "off-topic: not about this topic at all, on the listener's avoid list, or an index, listing "
    "or home page rather than an article",
    "tangential: only mentions the topic in passing, or is about something on the topic's "
    "exclude list",
    "adjacent: related to the topic but not what this listener asked for",
    "on-topic: fits the topic's description",
    "squarely on-topic: fits the description and matches the topic's include list",
]
_NEWSWORTHY_RUNGS = [
    "not news: an index or listing page, PR fluff, a listicle, a product roundup, advice or an "
    "evergreen explainer or feature",
    "feature with a weak news hook: mostly evergreen content pegged to something recent",
    "minor news: a real but small or incremental development, or a rehash of known news",
    "genuine news: reports a specific new event -- funding, launch, research, policy, results",
]
_ALREADY_COVERED_CRITERIA = {
    "true": "Same story and angle as one of the recent headlines.",
    "false": "A new story, or a meaningfully different angle on an old one.",
}

# Two different failures, handled differently (D-42):
# - 502/503/504: random and brief (~2% of calls, the next one almost always succeeds, D-41 point
#   6). Retried a few times with a short backoff.
# - 429: a rate limit (Vercel's free tier limits each model per account, and the gateway rejects
#   before trying any host). Retrying quickly keeps the account over the limit, so a 429 pauses
#   every Jev call in this process for `jev_rate_limit_cooldown_s` instead; during the pause
#   score() raises JevRateLimited without an HTTP call, and FallbackClassifier uses the
#   OpenAI classifier (MODEL_CLASSIFIER).
# Either way a `retry-after` header wins when Vercel sends one and it is short enough to wait.
_SERVER_ERROR_STATUS = {502, 503, 504}
_BACKOFF_BASE_S = 0.5
_MAX_RETRY_AFTER_WAIT_S = 10.0  # longer waits become a cooldown, never a blocked ranking thread

# The rate limit is per account, not per JevClassifier, and rank.py classifies from 8 threads --
# so the pause is module-wide and guarded by a lock.
_cooldown_lock = threading.Lock()
_cooldown_until = 0.0  # time.monotonic() deadline; 0 = not cooling down


class JevRateLimited(RuntimeError):
    """Jev is paused after a 429; `remaining_s` is how long until it may be called again."""

    def __init__(self, remaining_s: float) -> None:
        super().__init__(f"Jev rate limited, paused for another {remaining_s:.0f}s")
        self.remaining_s = remaining_s


def cooldown_remaining_s() -> float:
    with _cooldown_lock:
        return max(0.0, _cooldown_until - time.monotonic())


def _start_cooldown(seconds: float) -> None:
    global _cooldown_until
    with _cooldown_lock:
        _cooldown_until = max(_cooldown_until, time.monotonic() + seconds)


def _retry_after_s(response: httpx.Response) -> float | None:
    """`retry-after` as seconds (it may be a number or an HTTP date); None if absent or bad."""
    header = response.headers.get("retry-after")
    if not header:
        return None
    try:
        return max(0.0, float(header))
    except ValueError:
        pass
    try:
        return max(0.0, parsedate_to_datetime(header).timestamp() - time.time())
    except (TypeError, ValueError):
        return None


def _build_request(
    model: str,
    article: "Article",
    profile: InterestProfile,
    topic: str,
    recent_headlines: list[str],
) -> dict:
    t = topic_for(profile, topic)
    state = {
        "topic": {
            "name": t.name,
            "description": t.description,
            "include": t.include,
            "exclude": t.exclude,
        },
        "avoid": profile.avoid,
        "article": {
            "title": article.title or "(no title)",
            "outlet": article.outlet or "unknown",
            "published_at": (
                article.published_at.isoformat() if article.published_at else "unknown"
            ),
            "highlights": article.highlights or [],
        },
        "recent_headlines": recent_headlines,
    }
    questions = {
        "relevance": {
            "type": "score",
            "instructions": (
                "How well does state.article match state.topic for this listener? Judge against "
                "this one topic only, using its description, include and exclude lists, and "
                "state.avoid (never relevant)."
            ),
            "criteria": _RELEVANCE_RUNGS,
        },
        "newsworthy": {
            "type": "score",
            "instructions": (
                "How newsworthy is state.article? A first-party announcement of a real event "
                "still counts as news."
            ),
            "criteria": _NEWSWORTHY_RUNGS,
        },
        "already_covered": {
            "type": "boolean",
            "instructions": (
                "Is state.article the same story and angle as one of the "
                "state.recent_headlines the listener already heard?"
            ),
            "criteria": _ALREADY_COVERED_CRITERIA,
        },
    }
    return {"model": model, "state": state, "questions": questions}


def _normalized(answer: dict, rung_count: int) -> float:
    return min(1.0, max(0.0, answer["score"] / (rung_count - 1)))


class JevClassifier:
    """Real Classifier backed by TypeSafe's Jev, served through Vercel AI Gateway's evaluation
    API (D-40). One POST per (article, topic) with two graded `score` questions (relevance to the
    single topic being scored, newsworthiness) and a `boolean` for already_covered (D-42).

    Failures (D-42): 502/503/504 and transport errors are retried up to `jev_max_attempts` times
    with a short backoff; a 429 pauses Jev process-wide for `jev_rate_limit_cooldown_s` and
    raises JevRateLimited. Either way a short `retry-after` is honored first. Whatever still
    fails raises, which is when FallbackClassifier scores the article with the OpenAI
    classifier (MODEL_CLASSIFIER) instead.
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

    def _post(self, payload: dict) -> dict:
        remaining = cooldown_remaining_s()
        if remaining > 0:
            raise JevRateLimited(remaining)

        attempts = self._settings.jev_max_attempts
        for attempt in range(1, attempts + 1):
            try:
                response = self._client.post(_EVALUATE_PATH, json=payload)
                response.raise_for_status()
                return response.json()
            except httpx.TransportError as e:
                if attempt == attempts:
                    raise
                wait_s = _BACKOFF_BASE_S * 2 ** (attempt - 1)
                logger.warning("jev transport error (%s), retrying in %.1fs", e, wait_s)
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                retry_after = _retry_after_s(e.response)
                short_retry_after = (
                    retry_after is not None and retry_after <= _MAX_RETRY_AFTER_WAIT_S
                )
                last_attempt = attempt == attempts
                if status == 429:
                    if short_retry_after and not last_attempt:
                        wait_s = retry_after
                        logger.warning("jev 429, retry-after %.1fs, retrying", wait_s)
                    else:
                        cooldown_s = max(self._settings.jev_rate_limit_cooldown_s, retry_after or 0)
                        _start_cooldown(cooldown_s)
                        logger.warning(
                            "jev 429 rate limited (retry-after=%s), pausing Jev for %.0fs",
                            retry_after,
                            cooldown_s,
                        )
                        raise JevRateLimited(cooldown_s) from e
                elif status in _SERVER_ERROR_STATUS and not last_attempt:
                    wait_s = (
                        retry_after if short_retry_after else _BACKOFF_BASE_S * 2 ** (attempt - 1)
                    )
                    logger.warning(
                        "jev %d on attempt %d/%d, retrying in %.1fs",
                        status,
                        attempt,
                        attempts,
                        wait_s,
                    )
                else:
                    raise
            time.sleep(wait_s)
        raise AssertionError("unreachable")  # the loop always returns or raises

    def score(
        self,
        article: "Article",
        profile: InterestProfile,
        topic: str,
        recent_headlines: list[str],
    ) -> tuple[ArticleScoreResult, Usage]:
        payload = _build_request(
            self._settings.model_jev, article, profile, topic, recent_headlines
        )

        # Latency covers every attempt: it is what the ranking stage actually waited.
        start = time.perf_counter()
        body = self._post(payload)
        latency_ms = int((time.perf_counter() - start) * 1000)

        answers = body["answers"]
        relevance = _normalized(answers["relevance"], len(_RELEVANCE_RUNGS))
        newsworthy = _normalized(answers["newsworthy"], len(_NEWSWORTHY_RUNGS))
        result = ArticleScoreResult(
            topic=topic,
            relevance=relevance,
            newsworthy=newsworthy,
            already_covered=answers["already_covered"]["probability"] > 0.5,
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
