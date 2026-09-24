"""Samples up to ~12 (article, fetched_topic) candidates per topic from one
real episode's `article_scores` rows into `eval/articles.csv`, for hand
labeling in Excel (docs/phases/04-quality.md Part A, docs/DECISIONS.md D-29
point 2). The episode should come from the dedicated eval user, fetched with
`--stop-after fetching` so nothing has been classified yet -- this script
only needs the candidates and their metadata, not scores.

Run (from the repo root, per docs/DECISIONS.md D-11):
    uv run --project backend python eval/build_set.py --episode-id <id>
"""

import argparse
import csv
import random
from pathlib import Path

# `app` is importable here with no sys.path hack: backend is uv_build-installed
# editable into backend/.venv (D-13), and `uv run --project backend` (D-11)
# runs this script with that interpreter regardless of cwd.
from app.db import session_scope
from app.models import Article, ArticleScore
from sqlalchemy import select

_DEFAULT_PER_TOPIC_CAP = 12
_DEFAULT_SEED = 4
_OUT_COLUMNS = [
    "article_id",
    "fetched_topic",
    "title",
    "outlet",
    "published_at",
    "highlights",
    "label_relevant",
    "label_newsworthy",
    "label_actual_topic",
]


def fetch_candidates(episode_id: int) -> list:
    with session_scope() as db:
        return db.execute(
            select(
                ArticleScore.article_id,
                ArticleScore.topic,
                Article.title,
                Article.outlet,
                Article.published_at,
                Article.highlights,
            )
            .join(Article, Article.id == ArticleScore.article_id)
            .where(ArticleScore.episode_id == episode_id)
        ).all()


def sample_per_topic(candidates: list, per_topic_cap: int, seed: int) -> list:
    """Shuffles deterministically (fixed seed) then caps each topic at
    per_topic_cap, so re-running with the same seed reproduces the same
    eval set from the same fetched candidates."""
    rng = random.Random(seed)
    by_topic: dict[str, list] = {}
    for row in candidates:
        by_topic.setdefault(row.topic or "", []).append(row)

    sampled = []
    for topic in sorted(by_topic):
        rows = list(by_topic[topic])
        rng.shuffle(rows)
        sampled.extend(rows[:per_topic_cap])
    return sampled


def to_csv_rows(sampled: list) -> list[dict]:
    return [
        {
            "article_id": row.article_id,
            "fetched_topic": row.topic or "",
            "title": row.title or "",
            "outlet": row.outlet or "",
            "published_at": row.published_at.isoformat() if row.published_at else "",
            "highlights": " | ".join(row.highlights or []),
            "label_relevant": "",
            "label_newsworthy": "",
            "label_actual_topic": "",
        }
        for row in sampled
    ]


def write_csv(rows: list[dict], out_path: Path) -> None:
    # utf-8-sig: Windows Excel misreads plain UTF-8 without the BOM
    # (docs/DECISIONS.md D-29 point 2).
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=_OUT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episode-id", type=int, required=True)
    parser.add_argument("--per-topic-cap", type=int, default=_DEFAULT_PER_TOPIC_CAP)
    parser.add_argument("--seed", type=int, default=_DEFAULT_SEED)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "articles.csv")
    args = parser.parse_args()

    candidates = fetch_candidates(args.episode_id)
    if not candidates:
        raise SystemExit(
            f"no article_scores rows for episode {args.episode_id}; "
            "run `cli generate --user <eval user> --stop-after fetching` first"
        )

    sampled = sample_per_topic(candidates, args.per_topic_cap, args.seed)
    rows = to_csv_rows(sampled)
    write_csv(rows, args.out)

    by_topic: dict[str, int] = {}
    for row in rows:
        by_topic[row["fetched_topic"]] = by_topic.get(row["fetched_topic"], 0) + 1
    print(f"wrote {len(rows)} rows to {args.out}")
    for topic, count in sorted(by_topic.items()):
        print(f"  {topic}: {count}")


if __name__ == "__main__":
    main()
