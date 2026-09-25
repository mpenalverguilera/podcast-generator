import time
from datetime import datetime

from exa_py import Exa

from app.config import Settings, get_settings
from app.pricing import cost_for
from app.schemas import ContentResult, RawArticle, Usage


class ExaSource:
    """Real SearchSource backed by Exa. Call shapes per .claude/skills/exa-news-search
    and docs/DECISIONS.md D-09: snake_case kwargs only, contents.highlights on
    /search, top-level text on /contents, never category/numResults/domain
    filters/maxAgeHours."""

    provider = "exa"

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        if not settings.exa_api_key:
            raise RuntimeError("EXA_API_KEY is not set; cannot construct ExaSource")
        self._client = Exa(api_key=settings.exa_api_key.get_secret_value())

    def search(self, query: str, since: datetime | None) -> tuple[list[RawArticle], Usage]:
        start = time.monotonic()
        kwargs: dict = {"type": "auto", "contents": {"highlights": True}}
        if since is not None:
            kwargs["start_published_date"] = since.isoformat()
        res = self._client.search(query, **kwargs)
        latency_ms = int((time.monotonic() - start) * 1000)

        articles = [
            RawArticle(
                url=r.url,
                title=r.title,
                outlet=None,
                published_at=r.published_date,
                highlights=r.highlights or [],
            )
            for r in res.results
        ]
        cost_usd, is_estimate = cost_for("exa", None, 0, exa_cost_usd=res.cost_dollars.total)
        usage = Usage(
            provider="exa",
            model=None,
            units_in=len(articles),
            cost_usd=cost_usd,
            cost_is_estimate=is_estimate,
            latency_ms=latency_ms,
            usage_source="exact",
        )
        return articles, usage

    def get_contents(self, urls: list[str]) -> tuple[dict[str, ContentResult], Usage]:
        start = time.monotonic()
        res = self._client.get_contents(urls, text=True)
        latency_ms = int((time.monotonic() - start) * 1000)

        results: dict[str, ContentResult] = {}
        for r in res.results:
            results[r.url] = ContentResult(url=r.url, text=r.text, status="success")
        for status in res.statuses:
            if status.status == "error" and status.id not in results:
                results[status.id] = ContentResult(url=status.id, text=None, status="error")

        cost_usd, is_estimate = cost_for("exa", None, 0, exa_cost_usd=res.cost_dollars.total)
        usage = Usage(
            provider="exa",
            model=None,
            units_in=len(urls),
            cost_usd=cost_usd,
            cost_is_estimate=is_estimate,
            latency_ms=latency_ms,
            usage_source="exact",
        )
        return results, usage
