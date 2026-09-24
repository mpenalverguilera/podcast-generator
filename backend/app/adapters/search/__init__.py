from app.adapters.search.exa import ExaSource
from app.adapters.search.fake import FakeSearchSource
from app.adapters.search.protocol import SearchSource
from app.config import Settings, get_settings


def get_search_source(
    settings: Settings | None = None, override: str | None = None
) -> SearchSource:
    settings = settings or get_settings()
    provider = override or settings.search_provider
    if provider == "fake":
        return FakeSearchSource()
    if provider == "exa":
        return ExaSource(settings)
    raise ValueError(f"unknown search provider {provider!r}")
