"""Phase 00 smoke test: Exa.

Confirms:
- /search with highlights + startPublishedDate, exact response attribute names, cost
- date-filter result-count difference vs no date filter
- /contents with text=True for top 2 URLs, statuses
- saves both raw responses (no keys) to backend/tests/fixtures/

Run (from repo root): uv run --project backend python scripts/smoke/exa_check.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv
from exa_py import Exa

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

FIXTURES = ROOT / "backend" / "tests" / "fixtures"
QUERY = "latest news on AI voice agents this week"


def to_jsonable(obj):
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if hasattr(obj, "__dict__"):
        return {k: to_jsonable(v) for k, v in vars(obj).items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [to_jsonable(v) for v in obj]
    return obj


def main() -> int:
    exa = Exa()

    window_start = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

    print("== /search with startPublishedDate ==")
    res_dated = exa.search(
        QUERY,
        type="auto",
        contents={"highlights": True},
        start_published_date=window_start,
    )
    print("response attributes:", [a for a in dir(res_dated) if not a.startswith("_")])
    print("result count:", len(res_dated.results))
    print("cost_dollars:", getattr(res_dated, "cost_dollars", "MISSING ATTR"))
    for r in res_dated.results[:5]:
        highlight_len = len("".join(r.highlights)) if r.highlights else 0
        print(f"- {r.title!r} | {r.published_date} | highlight_len={highlight_len}")

    print("\n== /search without date filter (comparison) ==")
    res_undated = exa.search(
        QUERY,
        type="auto",
        contents={"highlights": True},
    )
    print("result count (dated):", len(res_dated.results))
    print("result count (undated):", len(res_undated.results))

    top_urls = [r.url for r in res_dated.results[:2]]
    print(f"\n== /contents text=True for top 2 URLs: {top_urls} ==")
    res_contents = exa.get_contents(top_urls, text=True)
    print("statuses:", getattr(res_contents, "statuses", "MISSING ATTR"))
    for r in res_contents.results:
        text_len = len(r.text) if getattr(r, "text", None) else 0
        print(f"- {r.url}: text_len={text_len}")

    FIXTURES.mkdir(parents=True, exist_ok=True)
    (FIXTURES / "exa_search.json").write_text(
        json.dumps(to_jsonable(res_dated), indent=2), encoding="utf-8"
    )
    (FIXTURES / "exa_contents.json").write_text(
        json.dumps(to_jsonable(res_contents), indent=2), encoding="utf-8"
    )
    print(f"\nSaved fixtures to {FIXTURES}")

    total_cost = (getattr(res_dated, "cost_dollars", None) or {})
    print("\ncost_dollars (dated search):", total_cost)

    return 0


if __name__ == "__main__":
    sys.exit(main())
