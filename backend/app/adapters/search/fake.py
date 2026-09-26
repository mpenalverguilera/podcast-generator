import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.schemas import ContentResult, RawArticle, Usage

FIXTURES_DIR = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def _rebase_published_dates(results: list[dict], now: datetime) -> dict[str, datetime]:
    """Maps each fixture result's url to a published_at shifted so the newest
    article lands 1 hour before `now`, preserving every article's original age
    relative to the others. The fixture's captured dates are calendar-fixed
    (2026-09-23/24); left as-is, rank.py's recency decay (3-day half-life)
    ages every article out of selection within about a week of capture --
    silently failing every fake-pipeline test with no code change on our
    side. Rebasing keeps the fixture "fresh" no matter when the suite runs."""
    parsed = {
        r["url"]: datetime.fromisoformat(r["published_date"].replace("Z", "+00:00"))
        for r in results
    }
    shift = (now - timedelta(hours=1)) - max(parsed.values())
    return {url: dt + shift for url, dt in parsed.items()}


class FakeSearchSource:
    """Deterministic SearchSource for tests/CLI iteration. Reuses the real Exa
    responses captured in phase 00 (backend/tests/fixtures/exa_search.json and
    exa_contents.json) rather than inventing new ones, so the shape matches a
    real response exactly. `published_date`s are rebased relative to "now" at
    construction time (see _rebase_published_dates) so the fixture never goes
    stale."""

    provider = "fake"

    def __init__(self, fixtures_dir: Path | None = None) -> None:
        self._fixtures_dir = fixtures_dir or FIXTURES_DIR
        self._search_fixture = json.loads((self._fixtures_dir / "exa_search.json").read_text())
        self._contents_fixture = json.loads((self._fixtures_dir / "exa_contents.json").read_text())
        self._published_at = _rebase_published_dates(
            self._search_fixture["results"], datetime.now(UTC)
        )

    def search(self, query: str, since: datetime | None) -> tuple[list[RawArticle], Usage]:
        articles = [
            RawArticle(
                url=r["url"],
                title=r["title"],
                outlet=None,
                published_at=self._published_at[r["url"]],
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
