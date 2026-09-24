"""Smoke test: TypeSafe Jev (the phase 00 check that was deferred, docs/DECISIONS.md D-32).

Confirms:
- TYPESAFE_API_KEY loads from .env and authenticates
- the production JevClassifier returns probabilities, exact input tokens and a cost

One call, a few hundred input tokens: well under $0.0001.

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
            f"score={result.score:.3f}"
        )
        print(
            f"  model={usage.model} input_tokens={usage.units_in} cost=${usage.cost_usd:.7f} "
            f"latency={usage.latency_ms}ms request_id={usage.request_id}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
