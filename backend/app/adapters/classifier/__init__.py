from app.adapters.classifier.fake import FakeClassifier
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
        # Cut from phase 04 per its own "cut first" line and README's "Jev
        # optional" -- see docs/DECISIONS.md D-31. Not built anywhere yet.
        raise NotImplementedError("JevClassifier is not built; cut from phase 04, see D-31")
    raise ValueError(f"unknown classifier provider {provider!r}")
