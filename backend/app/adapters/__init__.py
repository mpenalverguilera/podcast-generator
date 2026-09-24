from dataclasses import dataclass

from app.adapters.classifier import get_classifier
from app.adapters.classifier.protocol import Classifier
from app.adapters.llm import get_llm
from app.adapters.llm.protocol import LLM
from app.adapters.search import get_search_source
from app.adapters.search.protocol import SearchSource
from app.adapters.tts import get_tts
from app.adapters.tts.protocol import TTS
from app.config import Settings, get_settings


@dataclass
class Adapters:
    search: SearchSource
    llm: LLM
    classifier: Classifier
    tts: TTS


def get_adapters(
    settings: Settings | None = None, overrides: dict[str, str] | None = None
) -> Adapters:
    settings = settings or get_settings()
    overrides = overrides or {}
    return Adapters(
        search=get_search_source(settings, overrides.get("search")),
        llm=get_llm(settings, overrides.get("llm")),
        classifier=get_classifier(settings, overrides.get("classifier")),
        tts=get_tts(settings, overrides.get("tts")),
    )
