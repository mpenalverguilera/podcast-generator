import logging
from typing import TYPE_CHECKING

from app.adapters.classifier.protocol import Classifier
from app.schemas import ArticleScoreResult, InterestProfile, Usage

if TYPE_CHECKING:
    from app.models import Article

logger = logging.getLogger(__name__)


class FallbackClassifier:
    """Wraps a `primary` Classifier with a `fallback`: any exception from `primary.score()`
    (a timeout, an HTTP error, a malformed response) scores that one article with `fallback`
    instead, rather than failing the whole ranking stage over one candidate. Used to make Jev
    (`docs/DECISIONS.md` D-44/D-45) safe to run: a Jev outage degrades one article's score to the
    OpenAI classifier's (`MODEL_CLASSIFIER`), not the episode.

    `Usage.fallback_count` is set to 1 on the returned `Usage` whenever the fallback fired (0 on
    the primary's own success), so `rank.run` can sum it into the ranking stage's
    `pipeline_steps.fallback_count` the same way it already sums cost/units -- how often Jev
    needed the fallback is then visible per episode, not just inferred from an error log.
    """

    def __init__(self, primary: Classifier, fallback: Classifier) -> None:
        self._primary = primary
        self._fallback = fallback

    def score(
        self,
        article: "Article",
        profile: InterestProfile,
        topic: str,
        recent_headlines: list[str],
    ) -> tuple[ArticleScoreResult, Usage]:
        try:
            return self._primary.score(article, profile, topic, recent_headlines)
        except Exception:
            logger.warning(
                "primary classifier failed for article %s topic %r, falling back",
                article.id,
                topic,
                exc_info=True,
            )
            result, usage = self._fallback.score(article, profile, topic, recent_headlines)
            return result, usage.model_copy(update={"fallback_count": 1})
