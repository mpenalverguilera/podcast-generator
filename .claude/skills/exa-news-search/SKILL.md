---
name: exa-news-search
description: How this project calls Exa to find and extract news for podcast episodes. Use when writing or changing the Exa adapter, the fetch or extract pipeline stages, or anything that builds Exa requests.
---

# Exa in this project

Canonical API reference: Exa's official `build-with-exa` skill (installed in phase 00 with
`npx skills add exa-labs/agent-skills --skill build-with-exa`). If this file and that skill disagree
on request shapes, the official skill wins; update this file.

## Two calls, two jobs

| Stage | Endpoint | Why |
|---|---|---|
| Fetch (every planned query) | `POST /search` with highlights | Cheap excerpts, enough to classify relevance and newsworthiness |
| Extract (selected 4–8 URLs only) | `POST /contents` with full text | The script needs broad context; pay for text only where it is used |

## `/search` — exact request

```python
from exa_py import Exa

exa = Exa(api_key=settings.exa_api_key)
res = exa.search(
    query,                                   # natural language, recency in the text: "latest ... this week"
    type="auto",
    contents={"highlights": True},           # always pass contents explicitly (SDK default differs)
    start_published_date=window_start.isoformat(),
)
```

Raw HTTP equivalent (camelCase):
```json
{"query": "latest news on AI voice agent startups this week", "type": "auto",
 "contents": {"highlights": true}, "startPublishedDate": "2026-09-17T00:00:00Z"}
```

Rules (from Exa's guidance, applied to this product):
- **Do not set** `category` (not even `"news"`), `numResults` (default 10 is our product choice), `includeDomains` / `excludeDomains`, `maxAgeHours`, `summary`, or `text` on search.
- `startPublishedDate` is justified here: the episode window ("since your last episode") is a stated bounded window we must enforce. It drops undated or misdated pages, so if a query returns fewer than 3 results, **retry once without it** and keep results whose `publishedDate` is inside the window or missing. Confirmed in phase 00: for a fast-moving topic ("AI voice agents this week") both the 7-day-windowed and unfiltered queries returned the full 10-result default with no visible count difference — the retry-without-filter path exists for slower-moving or narrower topics, not as the common case.
- Source preferences from the profile ("prefers primary sources") go into the query phrasing, not filters.
- Python SDK: snake_case keyword arguments (`start_published_date`, `output_schema`); camelCase raises `TypeError`.

Map each result to `RawArticle`: `url`, `title`, `published_date`, `author`, `highlights` (join the list), outlet = URL host. Record `res.cost_dollars` as the step cost.

Confirmed in phase 00 (exa-py 2.22.2): the SDK response object exposes snake_case attributes, not the raw HTTP's camelCase JSON keys. `search()` response: `results`, `statuses`, `cost_dollars` (a `CostDollars` object with `.total` and `.search`/`.contents` breakdowns, not a raw float), `output`, `resolved_search_type`, `auto_date`, `context`, `search_time`. There is **no `request_id` / `requestId` attribute** on the SDK object (only on the raw HTTP response), so don't log it from the SDK result. Each result item: `id`, `url`, `title`, `author`, `published_date`, `highlights`, `highlight_scores`, `text`, `summary`, `score`, `image`, `favicon`, `crawl_date`, `snapshot_at`, `subpages`, `extras`, `entities`.

## `/contents` — exact request

```python
res = exa.get_contents(urls, text=True)      # top-level text on /contents, NOT nested in contents
```

- HTTP 200 does not mean every URL worked. Read `statuses` per URL; on `error`, keep the stored highlights and mark `content_source="highlights"`.
- Truncate stored text to ~6,000 characters per article before it reaches the script prompt.

## Adapter contract

```python
class SearchSource(Protocol):
    def search(self, query: str, since: datetime | None) -> tuple[list[RawArticle], Usage]: ...
    def get_contents(self, urls: list[str]) -> tuple[dict[str, ContentResult], Usage]: ...
```

`FakeSearchSource` returns deterministic fixtures from `backend/tests/fixtures/exa_*.json` (capture real responses in phase 00, with no keys in them).

## Pitfalls seen in the wild
- Nesting `text` inside `contents` on `/contents` (wrong) or putting `highlights` at the top level on `/search` (wrong).
- Stacking `text` + `highlights`: double billing for two views of the same page.
- Using `maxAgeHours` as a recency filter: it controls crawl freshness, not publication date.
- `/findSimilar` is deprecated; use `/search`.
