from app.adapters.classifier.fake import FakeClassifier
from app.adapters.classifier.fallback import FallbackClassifier
from app.adapters.classifier.jev import JevClassifier
from app.adapters.classifier.openai import LLMClassifier
from app.adapters.classifier.protocol import Classifier
from app.adapters.llm import get_llm
from app.config import Settings, get_settings


def get_classifier(settings: Settings | None = None, override: str | None = None) -> Classifier:
    settings = settings or get_settings()
    provider = override or settings.classifier_provider
    if provider == "fake":
        return FakeClassifier()
    if provider == "openai":
        return LLMClassifier(get_llm(settings), settings)
    if provider == "jev":
        # D-39: Jev is the default classifier (cheaper, faster and non-inferior to Luna on the
        # real eval), but falls back to Luna per article on any Jev error/timeout so a Jev
        # outage degrades one candidate's score, not the whole ranking stage.
        return FallbackClassifier(
            JevClassifier(settings), LLMClassifier(get_llm(settings), settings)
        )
    raise ValueError(f"unknown classifier provider {provider!r}")
