import time
from typing import TYPE_CHECKING, Any

from typesafe_sdk import Noul, TypeSafeClient

from app.adapters.classifier.openai import _topic_for
from app.config import Settings, get_settings
from app.pricing import cost_for
from app.schemas import ArticleScoreResult, InterestProfile, Usage

if TYPE_CHECKING:
    from app.models import Article

# Jev takes typed questions over a structured state, not a rendered prompt, so
# these live here rather than in app/prompts/*.vN.md (docs/DECISIONS.md D-32).
# One condition per Noul, per TypeSafe's own guidance. Bump the suffix on change.
QUESTIONS_V1: dict[str, Noul] = {
    "relevant": Noul(
        instructions=(
            "Does this article belong to the given topic: it matches the topic's description "
            "and include list, and is not about anything in the topic's exclude list or the "
            "listener's avoid list?"
        ),
        criteria={
            "true": "The article is squarely about this topic as the listener defined it.",
            "false": "The article is off-topic, only adjacent, excluded or on the avoid list.",
        },
    ),
    "newsworthy": Noul(
        instructions=(
            "Is this article a genuine news story about a real, recent event (funding, launch, "
            "research, policy, results)?"
        ),
        criteria={
            "true": "It reports a specific new event or development.",
            "false": "It is PR fluff, a listicle, a product roundup or an evergreen explainer.",
        },
    ),
}
ALREADY_COVERED_V1 = Noul(
    instructions=(
        "Is this article the same story and angle as one of the recent_headlines the listener "
        "already heard?"
    ),
)


class JevClassifier:
    """Real Classifier backed by TypeSafe's Jev: typed yes/no questions in,
    calibrated probabilities out. `relevance`/`newsworthy` are Jev's P(yes)
    directly; `score` is their product, the same combination rank.py uses."""

    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        self._settings = settings or get_settings()
        if client is None:
            if self._settings.typesafe_api_key is None:
                raise RuntimeError("TYPESAFE_API_KEY is not set; JevClassifier needs it")
            client = TypeSafeClient(api_key=self._settings.typesafe_api_key.get_secret_value())
        self._client = client

    def score(
        self,
        article: "Article",
        profile: InterestProfile,
        topic: str,
        recent_headlines: list[str],
    ) -> tuple[ArticleScoreResult, Usage]:
        t = _topic_for(profile, topic)
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
                "published_at": article.published_at.isoformat()
                if article.published_at
                else "unknown",
                "highlights": article.highlights or [],
            },
            "recent_headlines": recent_headlines,
        }
        questions = dict(QUESTIONS_V1)
        if recent_headlines:
            questions["already_covered"] = ALREADY_COVERED_V1

        start = time.perf_counter()
        resp = self._client.system_one(state, questions, model=self._settings.model_jev)
        latency_ms = int((time.perf_counter() - start) * 1000)

        relevance = resp.nouls["relevant"].noul
        newsworthy = resp.nouls["newsworthy"].noul
        already_covered = bool(recent_headlines) and resp.nouls["already_covered"].noul > 0.5
        result = ArticleScoreResult(
            topic=topic,
            relevance=relevance,
            newsworthy=newsworthy,
            already_covered=already_covered,
            score=relevance * newsworthy,
        )

        units_in = resp.usage.input_tokens or 0
        cost_usd, is_estimate = cost_for("typesafe", resp.model, units_in)
        usage = Usage(
            provider="typesafe",
            model=resp.model,
            units_in=units_in,
            units_out=resp.usage.output_tokens or 0,
            cost_usd=cost_usd,
            cost_is_estimate=is_estimate,
            latency_ms=latency_ms,
            request_id=resp.request_id,
            usage_source="exact",
        )
        return result, usage
