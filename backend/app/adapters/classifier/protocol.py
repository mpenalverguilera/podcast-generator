from typing import TYPE_CHECKING, Protocol

from app.schemas import ArticleScoreResult, InterestProfile, Usage

if TYPE_CHECKING:
    from app.models import Article


class Classifier(Protocol):
    # Note the asymmetry: `article` is the persisted ORM row (app.models.Article)
    # since classification runs against stored/fetched articles, while
    # `profile` is the Pydantic InterestProfile parsed out of
    # preferences.interest_profile JSONB.
    #
    # `topic` is a deviation from ARCHITECTURE §6's literal signature (logged in
    # docs/DECISIONS.md): fetch already tags each `article_scores` row with the
    # one topic that found it (one row per matching topic, D-21), so ranking
    # needs to score an article against that *specific* topic, not have the
    # classifier re-guess which of the profile's topics is best.
    def score(
        self,
        article: "Article",
        profile: InterestProfile,
        topic: str,
        recent_headlines: list[str],
    ) -> tuple[ArticleScoreResult, Usage]: ...
