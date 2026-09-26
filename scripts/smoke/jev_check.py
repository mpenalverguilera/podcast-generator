"""Smoke test: Jev via Vercel AI Gateway (docs/DECISIONS.md D-40).

Confirms:
- AI_GATEWAY_API_KEY loads from .env and authenticates against https://ai-gateway.vercel.sh
- the production JevClassifier (jev.v2, D-42) posts to /v1/evaluate and parses its graded
  relevance/newsworthy `score` answers and already_covered `boolean`, exact token usage and AI
  Gateway's marketCost correctly -- expect high relevance for the launch article, low relevance and
  newsworthiness for the listicle, and values in between rather than only 0 or 1

One article, three questions in one request: a few hundred input tokens, well under $0.001.

Run (from repo root): uv run --project backend python scripts/smoke/jev_check.py
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from app.adapters.classifier.jev import JevClassifier
from app.models import Article
from app.schemas import InterestProfile, Topic


def main() -> int:
    profile = InterestProfile(
        topics=[
            Topic(
                name="Space launches",
                description="Orbital and crewed rocket launches, launch providers and missions",
                include=["SpaceX", "NASA", "rocket launches"],
                exclude=["astrology", "sci-fi movies"],
            )
        ],
        avoid=["celebrity gossip"],
    )
    on_topic = Article(
        id=1,
        url_hash="smoke-1",
        url="",
        title="SpaceX launches 24 Starlink satellites from Cape Canaveral",
        outlet="example.com",
        published_at=datetime.now(UTC),
        highlights=["A Falcon 9 lifted off on Tuesday night and the booster landed on a droneship."],
    )
    listicle = Article(
        id=2,
        url_hash="smoke-2",
        url="",
        title="10 best telescopes for beginners in 2026",
        outlet="example.com",
        published_at=datetime.now(UTC),
        highlights=["Our editors picked the top budget telescopes for stargazing at home."],
    )

    classifier = JevClassifier()
    for article in (on_topic, listicle):
        result, usage = classifier.score(article, profile, "Space launches", [])
        print(f"{article.title!r}")
        print(
            f"  relevance={result.relevance:.3f} newsworthy={result.newsworthy:.3f} "
            f"already_covered={result.already_covered} score={result.score:.3f}"
        )
        print(
            f"  model={usage.model} input_tokens={usage.units_in} output_tokens={usage.units_out} "
            f"market_cost=${usage.cost_usd:.8f} latency={usage.latency_ms}ms "
            f"generation_id={usage.request_id}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
