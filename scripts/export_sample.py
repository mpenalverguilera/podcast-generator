"""Phase 08 Part A: exports a ready episode as the repo-root sample files
reviewers read -- sample.mp3, sample.transcript.md, sample.meta.json.

Run from the repo root:
    uv run --project backend python scripts/export_sample.py --episode-id <id>
"""

import argparse
import json
import shutil
from collections import defaultdict
from pathlib import Path

from sqlalchemy import select

from app.db import session_scope
from app.models import Article, Episode, EpisodeItem, PipelineStep, Preferences
from app.pipeline.script import outlet_name, word_budget, word_count
from app.schemas import InterestProfile, Script

REPO_ROOT = Path(__file__).parent.parent


def build_transcript(episode: Episode, names: dict[str, str], sources: list[Article]) -> str:
    script = Script.model_validate(episode.script)
    out = [f"# {script.title}", "", script.summary, "", "## Sources", ""]
    for a in sources:
        out.append(f"- {outlet_name(a.outlet or a.url)}: [{a.title}]({a.url})")
    out += ["", "## Transcript", ""]
    for section in script.sections:
        for turn in section.turns:
            out.append(f"**{names[turn.speaker]}:** {turn.text}")
        out.append("")
    return "\n".join(out) + "\n"


def build_meta(episode: Episode, steps: list[PipelineStep], profile: InterestProfile) -> dict:
    by_stage: dict[str, dict] = defaultdict(
        lambda: {"cost_usd": 0.0, "latency_ms": 0, "cost_is_estimate": False}
    )
    for s in steps:
        row = by_stage[s.stage]
        row["cost_usd"] += float(s.cost_usd or 0)
        row["latency_ms"] += s.latency_ms or 0
        row["provider"] = s.provider
        row["model"] = s.model
        row["cost_is_estimate"] = row["cost_is_estimate"] or s.cost_is_estimate
    script = Script.model_validate(episode.script)
    total_words = sum(word_count(sec.turns) for sec in script.sections)
    total, frame, story = word_budget(episode.target_minutes)
    return {
        "episode_id": episode.id,
        "title": episode.title,
        "user": episode.user.email if episode.user else None,
        "focus_request": episode.focus_request,
        "target_minutes": episode.target_minutes,
        "prompt_versions": episode.prompt_versions,
        "topics": [t.name for t in profile.topics],
        "duration_s": episode.duration_s,
        "word_count": total_words,
        "word_budget": total,
        "grounding_flags": {
            "initial": len(episode.grounding_flags_initial or []),
            "final": len(episode.grounding_flags_final or []),
        },
        "cost_by_stage": {k: dict(v) for k, v in sorted(by_stage.items())},
        "total_cost_usd": round(sum(v["cost_usd"] for v in by_stage.values()), 4),
        "note": "elevenlabs cost_usd is an estimate (units_in x ELEVENLABS_USD_PER_1K_CHARS); "
        "see cost_is_estimate and docs/DECISIONS.md D-12",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episode-id", type=int, required=True)
    args = parser.parse_args()

    with session_scope() as db:
        episode = db.get(Episode, args.episode_id)
        if episode is None or episode.status.value != "ready":
            raise SystemExit(f"episode {args.episode_id} is not ready")
        prefs = db.get(Preferences, episode.user_id)
        names = {
            "host_a": (prefs.host_a or {}).get("name", "Alex") if prefs else "Alex",
            "host_b": (prefs.host_b or {}).get("name", "Sam") if prefs else "Sam",
        }
        profile = InterestProfile.model_validate((prefs.interest_profile if prefs else None) or {})
        items = list(
            db.scalars(
                select(EpisodeItem)
                .where(EpisodeItem.episode_id == episode.id)
                .order_by(EpisodeItem.position)
            )
        )
        sources = list(
            db.scalars(select(Article).where(Article.id.in_([i.article_id for i in items])))
        )
        sources.sort(key=lambda a: [i.article_id for i in items].index(a.id))
        steps = list(
            db.scalars(
                select(PipelineStep)
                .where(PipelineStep.episode_id == episode.id)
                .order_by(PipelineStep.id)
            )
        )

        shutil.copy(episode.audio_path, REPO_ROOT / "sample.mp3")
        (REPO_ROOT / "sample.transcript.md").write_text(
            build_transcript(episode, names, sources), encoding="utf-8"
        )
        meta = build_meta(episode, steps, profile)
        (REPO_ROOT / "sample.meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")

    print(f"wrote sample.mp3 ({episode.duration_s:.1f}s), sample.transcript.md, sample.meta.json")
    print(f"total cost: ${meta['total_cost_usd']:.4f}")


if __name__ == "__main__":
    main()
