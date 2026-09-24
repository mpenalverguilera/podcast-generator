from typing import TYPE_CHECKING, Protocol

from app.schemas import ArticleScoreResult, InterestProfile, Usage

if TYPE_CHECKING:
    from app.models import Article


class Classifier(Protocol):
    # Note the asymmetry: `article` is the persisted ORM row (app.models.Article)
    # since classification runs against stored/fetched articles, while
    # `profile` is the Pydantic InterestProfile parsed out of
    # preferences.interest_profile JSONB. This matches ARCHITECTURE §6 exactly.
    def score(
        self, article: "Article", profile: InterestProfile, recent_headlines: list[str]
    ) -> tuple[ArticleScoreResult, Usage]: ...
