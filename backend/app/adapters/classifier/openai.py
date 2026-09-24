from typing import TYPE_CHECKING

from app.adapters.llm.protocol import LLM
from app.config import Settings, get_settings
from app.schemas import ArticleScoreResult, InterestProfile, RenderedPrompt, Usage

if TYPE_CHECKING:
    from app.models import Article


class LLMClassifier:
    """Real Classifier, composed from an LLM adapter (not a fresh OpenAI client)
    per ARCHITECTURE §6's "(wraps LLM)". The real classify prompt lands in
    phase 02/04 (query planning / classifier eval) -- this is a minimal working
    implementation, not a fake, so CLASSIFIER_PROVIDER=openai resolves to
    something real today."""

    def __init__(self, llm: LLM, settings: Settings | None = None) -> None:
        self._llm = llm
        self._settings = settings or get_settings()

    def score(
        self, article: "Article", profile: InterestProfile, recent_headlines: list[str]
    ) -> tuple[ArticleScoreResult, Usage]:
        topics = ", ".join(t.name for t in profile.topics) or "general news"
        prompt = RenderedPrompt(
            name="classifier_inline",
            version=0,
            text=(
                f"Score this article's relevance to the reader's interests: {topics}.\n"
                f"Title: {article.title}\n"
                f"Highlights: {article.highlights}\n"
                f"Recently covered headlines: {recent_headlines}\n"
                "Return relevance (0-1), newsworthy (0-1), already_covered (bool), "
                "and an overall score (0-1)."
            ),
        )
        parsed, usage = self._llm.structured(
            prompt,
            ArticleScoreResult,
            model=self._settings.model_classifier,
            reasoning="none",
        )
        return parsed, usage
