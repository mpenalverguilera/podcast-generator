"""Classifier grid for D-61: classifier.v2 (dates + is_stale) across model/reasoning configs.

Run from the repo root (real OpenAI calls, cached per config so a re-run costs nothing):
    uv run --project backend python eval/classifier_grid.py

Every config's scores are cached in results/grid/<prompt>__<model>__<reasoning>.jsonl, and a cached
row is reused only if its prompt version, model AND reasoning all match -- two configs never share
rows. The v1 Sol/none and Luna/none baselines are read from the notebook's frozen caches
(results/scores_sol.jsonl, results/scores_luna.jsonl) and never re-scored.

The decision rules were fixed in docs/DECISIONS.md D-61 before this script first ran.
"""

import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select

from app.adapters.classifier.openai import LLMClassifier
from app.adapters.llm.openai import OpenAILLM
from app.config import get_settings
from app.db import session_scope
from app.models import Article, Preferences, User
from app.pipeline import rank
from app.prompts import load_prompt
from app.schemas import InterestProfile

EVAL_DIR = Path(__file__).parent
ARTICLES_CSV = EVAL_DIR / "articles.csv"
RESULTS_DIR = EVAL_DIR / "results"
GRID_DIR = RESULTS_DIR / "grid"

# Episode 8 (the eval user's episode the D-44 set was built from): window and fetch day.
DEFAULT_WINDOW = datetime(2026, 9, 17, 20, 12, tzinfo=UTC)
DEFAULT_TODAY = datetime(2026, 9, 24, 20, 12, tzinfo=UTC)
EVAL_NOW = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)  # same pin as the notebook (D-44 B2)
THRESHOLD = 0.5
TYPICAL_CANDIDATES = 60  # median (article, topic) candidates over the real episodes so far
CONCURRENCY = 8  # rank.py's own classification pool size

PROMPT_VERSION = f"classifier.v{load_prompt('classifier').version}"
CONFIGS = [  # (name, model, reasoning); the first one is the baseline
    ("sol/none", "gpt-6-sol", "none"),
    ("luna/none", "gpt-6-luna", "none"),
    ("luna/low", "gpt-6-luna", "low"),
    ("luna/medium", "gpt-6-luna", "medium"),
]
V1_CACHES = {"sol/none": "scores_sol.jsonl", "luna/none": "scores_luna.jsonl"}

# D-61 non-inferiority margins (vs v2 Sol/none).
AUC_MARGIN = -0.05
DISCORDANT_TOLERANCE = 3  # Luna vs luna_rerun keep-gate disagreement (D-45)
SELECTION_MARGIN = -0.125


@dataclass
class Row:
    key: tuple[int, str]
    set: str
    synthetic: bool
    difficulty: str
    label_relevant: int
    label_newsworthy: int
    label_stale: int
    article: Article
    profile: InterestProfile
    window_start: datetime
    today: datetime

    @property
    def label_keep(self) -> int:
        return self.label_relevant & self.label_newsworthy


_LABEL = {"y": 1, "yes": 1, "1": 1, "n": 0, "no": 0, "0": 0}


def _dt(value: str, default: datetime) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC) if value else default


def load_rows() -> list[Row]:
    raw = list(csv.DictReader(ARTICLES_CSV.open(encoding="utf-8-sig")))
    settings = get_settings()
    rows = []
    with session_scope() as db:
        profiles: dict[str, InterestProfile] = {}

        def profile_for(email: str) -> InterestProfile:
            email = email or settings.seed_eval_user_email
            if email not in profiles:
                user = db.scalars(select(User).where(User.email == email)).one()
                prefs = db.get(Preferences, user.id)
                profiles[email] = InterestProfile.model_validate(prefs.interest_profile)
            return profiles[email]

        real_ids = [int(r["article_id"]) for r in raw if int(r["article_id"]) > 0]
        articles = {a.id: a for a in db.scalars(select(Article).where(Article.id.in_(real_ids)))}
        db.expunge_all()
        for r in raw:
            aid = int(r["article_id"])
            if aid > 0:
                article = articles[aid]
            else:  # synthetic: never persisted, built from the CSV's own columns
                article = Article(
                    id=aid,
                    url_hash=f"synthetic{aid}",
                    url="",
                    title=r["title"],
                    outlet=r["outlet"],
                    published_at=datetime.fromisoformat(r["published_at"]),
                    highlights=[r["highlights"]],
                )
            topic = r["fetched_topic"]
            rows.append(
                Row(
                    key=(aid, topic),
                    set=r["set"],
                    synthetic=r["synthetic"] == "1",
                    difficulty=r["stale_difficulty"],
                    label_relevant=_LABEL[r["label_relevant"].strip().lower()],
                    label_newsworthy=_LABEL[r["label_newsworthy"].strip().lower()],
                    label_stale=int(r["label_stale"]),
                    article=article,
                    profile=rank._profile_for_topic(profile_for(r["profile_email"]), topic, None),
                    window_start=_dt(r["window_start"], DEFAULT_WINDOW),
                    today=_dt(r["today"], DEFAULT_TODAY),
                )
            )
    return rows


# ---------------------------------------------------------------- scoring + cache


def cache_path(model: str, reasoning: str) -> Path:
    return GRID_DIR / f"{PROMPT_VERSION}__{model}__{reasoning}.jsonl"


def load_cache(path: Path, prompt_version: str, model: str, reasoning: str) -> dict:
    if not path.exists():
        return {}
    out = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        # v1 notebook rows predate the reasoning field; they all ran with reasoning="none".
        if (rec.get("prompt_version"), rec.get("model"), rec.get("reasoning", "none")) != (
            prompt_version,
            model,
            reasoning,
        ):
            continue
        out[(rec["article_id"], rec["fetched_topic"])] = rec
    return out


def score_config(rows: list[Row], llm: OpenAILLM, model: str, reasoning: str) -> dict:
    path = cache_path(model, reasoning)
    cached = load_cache(path, PROMPT_VERSION, model, reasoning)
    todo = [r for r in rows if r.key not in cached]
    settings = get_settings().model_copy(
        update={"model_classifier": model, "model_classifier_reasoning": reasoning}
    )

    def one(row: Row) -> dict:
        classifier = LLMClassifier(llm, settings, clock=lambda: row.today)
        result, usage = classifier.score(row.article, row.profile, row.key[1], [], row.window_start)
        return {
            "article_id": row.key[0],
            "fetched_topic": row.key[1],
            "prompt_version": PROMPT_VERSION,
            "model": model,
            "reasoning": reasoning,
            "relevance": result.relevance,
            "newsworthy": result.newsworthy,
            "is_stale": result.is_stale,
            "cost_usd": usage.cost_usd,
            "latency_ms": usage.latency_ms,
            "units_out": usage.units_out,
        }

    # The first responses.parse call builds the SDK's generic response type lazily, and several
    # threads doing that at once fail ("BaseModel cannot be instantiated directly"): warm up with
    # one sequential call before fanning out.
    if todo:
        rec = one(todo[0])
        cached[(rec["article_id"], rec["fetched_topic"])] = rec
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        for rec in pool.map(one, todo[1:]):
            cached[(rec["article_id"], rec["fetched_topic"])] = rec
    GRID_DIR.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(cached[row.key]) + "\n")
    print(f"{model}/{reasoning}: {len(todo)} new calls, {len(rows)} rows")
    return cached


# ---------------------------------------------------------------- metrics


def roc_auc(y, s):
    pos = [v for t, v in zip(y, s) if t == 1]
    neg = [v for t, v in zip(y, s) if t == 0]
    if not pos or not neg:
        return float("nan")
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def prec_rec(y, p):
    tp = sum(1 for t, q in zip(y, p) if t and q)
    fp = sum(1 for t, q in zip(y, p) if not t and q)
    fn = sum(1 for t, q in zip(y, p) if t and not q)
    return (
        tp / (tp + fp) if tp + fp else float("nan"),
        tp / (tp + fn) if tp + fn else float("nan"),
    )


def keep_pred(rec) -> int:
    return int(rec["relevance"] * rec["newsworthy"] >= rank._MIN_SCORE)


def selection(rows: list[Row], scores: dict) -> set[int]:
    cands = [
        rank.Candidate(
            article_id=r.key[0],
            topic=r.key[1],
            relevance=scores[r.key]["relevance"],
            newsworthy=scores[r.key]["newsworthy"],
            already_covered=False,
            published_at=r.article.published_at,
            is_stale=scores[r.key].get("is_stale", False),
        )
        for r in rows
    ]
    return {s.article_id for s in rank.select_stories(cands, target_minutes=10, now=EVAL_NOW)}


def quality(d44: list[Row], scores: dict) -> dict:
    y_keep = [r.label_keep for r in d44]
    recs = [scores[r.key] for r in d44]
    keep_p, keep_r = prec_rec(y_keep, [keep_pred(x) for x in recs])
    picks = selection(d44, scores)
    keep_ids = {r.key[0] for r in d44 if r.label_keep}
    return {
        "keep_auc": roc_auc(y_keep, [x["relevance"] * x["newsworthy"] for x in recs]),
        "keep_p": keep_p,
        "keep_r": keep_r,
        "news_auc": roc_auc([r.label_newsworthy for r in d44], [x["newsworthy"] for x in recs]),
        "rel_auc": roc_auc([r.label_relevant for r in d44], [x["relevance"] for x in recs]),
        "sel_prec": len(picks & keep_ids) / len(picks) if picks else float("nan"),
    }


def discordant_net(d44: list[Row], base: dict, chal: dict) -> int:
    base_wins = chal_wins = 0
    for r in d44:
        b = keep_pred(base[r.key]) == r.label_keep
        c = keep_pred(chal[r.key]) == r.label_keep
        base_wins += b and not c
        chal_wins += c and not b
    return base_wins - chal_wins


def staleness(rows: list[Row], scores: dict) -> dict:
    fresh = [r for r in rows if r.label_stale == 0]
    fps = [r for r in fresh if scores[r.key]["is_stale"]]
    out = {"fp": len(fps), "fp_rows": [r.key[0] for r in fps], "fresh_n": len(fresh)}
    for label, pick in [
        ("real", lambda r: not r.synthetic),
        ("synthetic", lambda r: r.synthetic),
    ]:
        for diff in ("easy", "medium", "hard"):
            group = [r for r in rows if r.label_stale == 1 and pick(r) and r.difficulty == diff]
            if group:
                hit = sum(1 for r in group if scores[r.key]["is_stale"])
                out[f"{label}_{diff}"] = f"{hit}/{len(group)}"
    return out


def cost_latency(recs: list[dict]) -> dict:
    lat = sorted(x["latency_ms"] for x in recs)
    per_call = sum(x["cost_usd"] for x in recs) / len(recs)
    p50 = lat[len(lat) // 2]
    return {
        "cost_100": per_call * 100,
        "cost_episode": per_call * TYPICAL_CANDIDATES,
        "p50": p50,
        "p95": lat[min(len(lat) - 1, int(len(lat) * 0.95))],
        # rank.py classifies 8 at a time, so an episode waits ~candidates/8 rounds.
        "episode_s": TYPICAL_CANDIDATES / CONCURRENCY * (sum(lat) / len(lat)) / 1000,
        "out_tokens": sum(x.get("units_out", 0) for x in recs) / len(recs),
    }


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    rows = load_rows()
    d44 = [r for r in rows if r.set == "d44"]
    llm = OpenAILLM(get_settings())
    scores = {name: score_config(rows, llm, m, rsn) for name, m, rsn in CONFIGS}
    v1 = {
        name: load_cache(RESULTS_DIR / f, "classifier.v1", CONFIGS_BY_NAME[name][0], "none")
        for name, f in V1_CACHES.items()
    }

    base_name = CONFIGS[0][0]
    base_q = quality(d44, scores[base_name])
    table = []
    for name, _m, _r in CONFIGS:
        q = quality(d44, scores[name])
        st = staleness(rows, scores[name])
        cl = cost_latency([scores[name][r.key] for r in rows])
        disc = discordant_net(d44, scores[base_name], scores[name])
        checks = {
            "keep_auc": q["keep_auc"] - base_q["keep_auc"] >= AUC_MARGIN,
            "news_auc": q["news_auc"] - base_q["news_auc"] >= AUC_MARGIN,
            "discordant": disc <= DISCORDANT_TOLERANCE,
            "selection": q["sel_prec"] - base_q["sel_prec"] >= SELECTION_MARGIN,
            "zero_fp": st["fp"] == 0,
        }
        table.append({"name": name, **q, **st, **cl, "disc": disc, "checks": checks})

    passing = [t for t in table if all(t["checks"].values())]
    winner = min(passing, key=lambda t: t["cost_100"]) if passing else None

    v1_rows = []
    for name, cache in v1.items():
        q1 = quality(d44, cache)
        q2 = quality(d44, scores[name])
        v1_rows.append((name, q1, q2, discordant_net(d44, cache, scores[name])))

    write_report(table, winner, v1_rows, rows)
    raw = {"prompt_version": PROMPT_VERSION, "table": table, "winner": winner and winner["name"]}
    (RESULTS_DIR / "classifier_v2_grid.json").write_text(
        json.dumps(raw, indent=2, default=str), encoding="utf-8"
    )


CONFIGS_BY_NAME = {name: (m, r) for name, m, r in CONFIGS}


def write_report(table, winner, v1_rows, rows) -> None:
    n_d44 = sum(1 for r in rows if r.set == "d44")
    lines = [
        "# Classifier v2 grid (D-61)",
        "",
        f"Prompt `{PROMPT_VERSION}`; {len(rows)} rows ({n_d44} original D-44 rows for quality, "
        "all rows for staleness). Rules fixed in advance in `docs/DECISIONS.md` D-61. "
        f"Per-episode figures assume {TYPICAL_CANDIDATES} candidates (median of real episodes).",
        "",
        f"**Chosen: {winner['name'] if winner else 'none passed -- keep sol/none'}**",
        "",
        "## Quality (D-44 rows) and the D-61 gates, vs sol/none",
        "",
        "| config | keep AUC | keep P | keep R | news AUC | rel AUC | sel. prec | discordant net "
        "| stale FPs | passes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for t in table:
        failed = [k for k, ok in t["checks"].items() if not ok]
        lines.append(
            f"| {t['name']} | {t['keep_auc']:.3f} | {t['keep_p']:.2f} | {t['keep_r']:.2f} | "
            f"{t['news_auc']:.3f} | {t['rel_auc']:.3f} | {t['sel_prec']:.3f} | {t['disc']} | "
            f"{t['fp']}/{t['fresh_n']} | {'yes' if not failed else 'no: ' + ', '.join(failed)} |"
        )
    lines += [
        "",
        "## Stale recall (hits / stale rows)",
        "",
        "| config | real easy | real medium | synthetic easy | synthetic medium | synthetic hard "
        "| false positives (article ids) |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in table:
        lines.append(
            f"| {t['name']} | {t.get('real_easy', '-')} | {t.get('real_medium', '-')} | "
            f"{t.get('synthetic_easy', '-')} | {t.get('synthetic_medium', '-')} | "
            f"{t.get('synthetic_hard', '-')} | {t['fp_rows'] or 'none'} |"
        )
    lines += [
        "",
        "## Cost and latency",
        "",
        "| config | $/100 calls | $/episode | p50 ms | p95 ms | ~episode wait s "
        "| avg output tokens |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in table:
        lines.append(
            f"| {t['name']} | ${t['cost_100']:.4f} | ${t['cost_episode']:.4f} | {t['p50']} | "
            f"{t['p95']} | {t['episode_s']:.1f} | {t['out_tokens']:.0f} |"
        )
    lines += [
        "",
        "## v1 vs v2 on the same model (D-44 rows)",
        "",
        "| model | keep AUC v1 -> v2 | news AUC v1 -> v2 | rel AUC v1 -> v2 | sel. prec v1 -> v2 "
        "| keep-gate discordant net (v1 - v2) |",
        "|---|---|---|---|---|---|",
    ]
    for name, q1, q2, disc in v1_rows:
        lines.append(
            f"| {name} | {q1['keep_auc']:.3f} -> {q2['keep_auc']:.3f} | "
            f"{q1['news_auc']:.3f} -> {q2['news_auc']:.3f} | "
            f"{q1['rel_auc']:.3f} -> {q2['rel_auc']:.3f} | "
            f"{q1['sel_prec']:.3f} -> {q2['sel_prec']:.3f} | {disc} |"
        )
    lines += [
        "",
        "Selection precision uses the current `select_stories` (topic coverage, stale skip) for "
        "both v1 and v2, so the v1 numbers differ from `latest.md`'s.",
    ]
    (RESULTS_DIR / "classifier_v2_grid.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
