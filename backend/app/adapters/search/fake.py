import json
from datetime import datetime
from pathlib import Path

from app.schemas import ContentResult, RawArticle, Usage

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


class FakeSearchSource:
    """Deterministic SearchSource for tests/CLI iteration. Reuses the real Exa
    responses captured in phase 00 (backend/tests/fixtures/exa_search.json and
    exa_contents.json) rather than inventing new ones, so the shape matches a
    real response exactly."""

    provider = "fake"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = fixtures_dir or FIXTURES_DIR
        self._search_fixture = json.loads((self._fixtures_dir / "exa_search.json").read_text())
        self._contents_fixture = json.loads((self._fixtures_dir / "exa_contents.json").read_text())

    def search(self, query: str, since: datetime | None) -> tuple[list[RawArticle], Usage]:
        articles = [
            RawArticle(
                url=r["url"],
                title=r["title"],
                outlet=None,
                published_at=r["published_date"],
                highlights=r["highlights"] or [],
            )
            for r in self._search_fixture["results"]
        ]
        usage = Usage(provider="fake", units_in=len(articles), usage_source="fake")
        return articles, usage

    def get_contents(self, urls: list[str]) -> tuple[dict[str, ContentResult], Usage]:
        by_url = {r["url"]: r for r in self._contents_fixture["results"]}
        results: dict[str, ContentResult] = {}
        for url in urls:
            r = by_url.get(url)
            if r:
                results[url] = ContentResult(url=url, text=r["text"], status="success")
            else:
                results[url] = ContentResult(url=url, text=None, status="error")
        usage = Usage(provider="fake", units_in=len(urls), usage_source="fake")
        return results, usage
