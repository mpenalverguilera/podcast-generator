"""Writes a human-readable review file for one scripting-v2 episode
(docs/DECISIONS.md D-59): who it was for, what was selected, the outline,
the final dialogue, grounding flags, word budget and per-sub-step cost.

Run from the repo root:
    uv run --project backend python eval/scripts_v2/export_review.py --episode-id <id>
"""

# `app` is importable with no sys.path hack: backend is installed into its own venv.
import argparse
from pathlib import Path

from app.db import session_scope
from app.models import Article, ArticleScore, Episode, EpisodeItem, PipelineStep, Preferences, User
from app.pipeline.script import outlet_name, short_id, word_budget, word_count
from app.schemas import InterestProfile, Script
from sqlalchemy import select

_OUT_DIR = Path(__file__).parent


def _profile_lines(profile: InterestProfile) -> list[str]:
    lines = []
    for t in profile.topics:
        lines.append(f"- **{t.name}** ({t.depth}): {t.description}")
        if t.include:
            lines.append(f"  - include: {', '.join(t.include)}")
        if t.exclude:
            lines.append(f"  - exclude: {', '.join(t.exclude)}")
    lines.append(f"- avoid: {', '.join(profile.avoid) or '(nothing)'}")
    return lines


def _flag_lines(flags: list[dict]) -> list[str]:
    return [f'  - turn {f["turn_index"]}: "{f["claim"]}" — {f["reason"]}' for f in flags]


def build_review(episode_id: int) -> str:
    with session_scope() as db:
        episode = db.get(Episode, episode_id)
        if episode is None or not episode.script:
            raise SystemExit(f"episode {episode_id} has no script")
        user = db.get(User, episode.user_id)
        prefs = db.get(Preferences, episode.user_id)
        names = {
            "host_a": (prefs.host_a or {}).get("name", "Alex") if prefs else "Alex",
            "host_b": (prefs.host_b or {}).get("name", "Sam") if prefs else "Sam",
        }
        profile = InterestProfile.model_validate((prefs.interest_profile if prefs else None) or {})
        script = Script.model_validate(episode.script)
        items = list(
            db.scalars(
                select(EpisodeItem)
                .where(EpisodeItem.episode_id == episode_id)
                .order_by(EpisodeItem.position)
            )
        )
        articles = {
            a.id: a
            for a in db.scalars(
                select(Article).where(Article.id.in_([i.article_id for i in items]))
            )
        }
        best: dict[int, ArticleScore] = {}
        for s in db.scalars(
            select(ArticleScore)
            .where(ArticleScore.episode_id == episode_id)
            .order_by(ArticleScore.score.desc().nulls_last())
        ):
            best.setdefault(s.article_id, s)
        step_rows = list(
            db.scalars(
                select(PipelineStep)
                .where(
                    PipelineStep.episode_id == episode_id,
                    PipelineStep.stage.in_(["scripting", "grounding"]),
                )
                .order_by(PipelineStep.id)
            )
        )
        steps = [
            f"- {s.stage} ({s.status.value}): {s.model}, ${float(s.cost_usd or 0):.4f}, "
            f"{(s.latency_ms or 0) / 1000:.1f}s"
            for s in step_rows
        ]
        initial = episode.grounding_flags_initial or []
        final = episode.grounding_flags_final or []
        title, target_minutes, focus = episode.title, episode.target_minutes, episode.focus_request
        email = user.email if user else "?"
        versions = episode.prompt_versions or {}

        out: list[str] = [f"# Episode {episode_id}: {title}", ""]
        out += [
            f"- **User:** {email}",
            f"- **Focus request:** {focus or '(none)'}",
            f"- **Target:** {target_minutes} min",
            f"- **Prompt versions:** {', '.join(f'{k} v{v}' for k, v in sorted(versions.items()))}",
            "",
            "## Listener profile",
            "",
            *_profile_lines(profile),
            "",
            "## Selected articles",
            "",
            "| id | outlet | title | topic | score | text | story |",
            "|---|---|---|---|---|---|---|",
        ]
        for item in items:
            a = articles[item.article_id]
            sc = best.get(a.id)
            score = f"{sc.score:.2f}" if sc and sc.score is not None else "-"
            text = "full text" if a.content else "highlights only"
            out.append(
                f"| {short_id(a.id)} | {outlet_name(a.outlet or a.url)} | {a.title or ''} | "
                f"{sc.topic if sc else '-'} | {score} | {text} | {item.story_id} |"
            )

    outline = script.outline
    out += ["", "## Outline", ""]
    if outline is None:
        out.append("(no outline: a scripting v1 episode)")
    else:
        out += [f"**Cold open hook:** {outline.cold_open_hook}", ""]
        for k, s in enumerate(outline.sections, start=1):
            out += [
                f"### {k}. {s.headline}",
                f"- sources: {', '.join(s.source_ids)} · topic: {s.topic_label} · depth: "
                f"{s.depth} · max words: {s.max_words}",
                f"- angle: {s.angle}",
                f"- stakes: {s.stakes}",
                f"- bridge in: {s.bridge_in or '(first section)'}",
                f"- key facts: {'; '.join(s.key_facts) or '-'}",
                f"- must not cover: {'; '.join(s.must_not_cover) or '-'}",
                "",
            ]
        for d in outline.dropped:
            out.append(f"- **dropped** {d.source_id}: {d.reason}")

    out += ["", "## Script", "", f"**{script.title}** — {script.summary}", ""]
    for i, section in enumerate(script.sections):
        heading = section.kind
        if section.kind == "story" and outline and i - 1 < len(outline.sections):
            heading = f"story {i}: {outline.sections[i - 1].headline}"
        out += [f"### [{i}] {heading}", ""]
        out += [f"**{names[t.speaker]}:** {t.text}  " for t in section.turns]
        out.append("")

    out += ["## Grounding", ""]
    out.append(f"Initial flags: {len(initial)} · final flags: {len(final)}")
    out.append("")
    for i in range(len(script.sections)):
        first = [f for f in initial if f["section_index"] == i]
        last = [f for f in final if f["section_index"] == i]
        if first or last:
            out.append(f"- section {i}: {len(first)} → {len(last)}")
            out += _flag_lines(last)

    total, frame, story = word_budget(target_minutes)
    wpm = total / target_minutes
    out += ["", "## Length", "", "| section | words | max |", "|---|---|---|"]
    targets = {k + 1: s.max_words for k, s in enumerate(outline.sections)} if outline else {}
    for i, section in enumerate(script.sections):
        target = targets.get(i, "-")
        if section.kind == "intro" or section.kind == "outro":
            target = f"frame {frame}"
        out.append(f"| [{i}] {section.kind} | {word_count(section.turns)} | {target} |")
    words = sum(word_count(s.turns) for s in script.sections)
    out += [
        "",
        f"Total {words} words vs a {total}-word budget ({(words - total) / total:+.0%}); "
        f"estimated {words / wpm:.1f} min at {wpm:.0f} wpm "
        f"(target {target_minutes} min).",
    ]

    out += [
        "",
        "## Cost and latency per sub-step",
        "",
        "| step | section | words | flags | cost | latency | note |",
        "|---|---|---|---|---|---|---|",
    ]
    for t in script.trace:
        out.append(
            f"| {t.step} | {'' if t.section is None else t.section} | {t.words or ''} | "
            f"{'' if t.flags is None else t.flags} | ${t.cost_usd:.4f} | "
            f"{t.latency_ms / 1000:.1f}s | {t.note or ''} |"
        )
    out += ["", "Stage rows (`pipeline_steps`):", ""]
    out += steps
    return "\n".join(out) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--episode-id", type=int, required=True)
    args = parser.parse_args()
    path = _OUT_DIR / f"episode_{args.episode_id}.md"
    path.write_text(build_review(args.episode_id), encoding="utf-8")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
