from datetime import datetime
from typing import Protocol

from app.schemas import ContentResult, RawArticle, Usage


class SearchSource(Protocol):
    provider: str

    def search(self, query: str, since: datetime | None) -> tuple[list[RawArticle], Usage]: ...

    def get_contents(self, urls: list[str]) -> tuple[dict[str, ContentResult], Usage]: ...
