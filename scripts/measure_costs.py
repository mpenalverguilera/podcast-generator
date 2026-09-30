"""Measures what one episode really costs and how long each stage takes.

Two commands, run from the repo root:

    uv run --project backend python scripts/measure_costs.py run
    uv run --project backend python scripts/measure_costs.py report [--ids 1 2 3]

`run` creates (once) four measurement users from the eval interview answers,
then generates one 10-minute episode per user, stopping after scripting so no
ElevenLabs credit is spent. It finishes with `report` on those episodes.
Expected spend: about $0.55 per episode (OpenAI + Exa), about $2.20 in all,
inside DAILY_SPEND_CAP_USD.

`report` reads pipeline_steps for every real (non-synthetic) episode that got
through scripting, or for the given ids, and prints per-stage cost and time.
Voicing is estimated when it didn't run: characters sent to TTS x
ELEVENLABS_USD_PER_1K_CHARS (itself an estimate, D-12), and wall time from the
measured per-chunk speed (~40 chars/s, D-56) with chunks in parallel.
"""

import argparse
import json
import secrets
import statistics
from collections import defaultdict
from pathlib import Path

from app.adapters.llm import get_llm
from app.config import get_settings
from app.db import session_scope
from app.models import Episode, EpisodeStatus, EpisodeTrigger, PipelineStep, StepStatus, User
from app.pipeline.episodes import create_episode
from app.pipeline.profile import extract_profile
from app.pipeline.runner import STOPPED_AFTER, run_episode
from app.pipeline.voice import chunk_script
from app.schemas import Script
from sqlalchemy import select

REPO_ROOT = Path(__file__).parent.parent
PROFILES = {
    "measure-ai@example.com": REPO_ROOT / "eval/scripts_v2/profiles/v2-ai.json",
    "measure-general@example.com": REPO_ROOT / "eval/scripts_v2/profiles/v2-general.json",
    "measure-markets@example.com": REPO_ROOT / "eval/scripts_v2/profiles/v2-markets.json",
    "measure-space@example.com": REPO_ROOT / "eval/eval_user_answers.json",
}
MINUTES = 10
CHARS_PER_SECOND = 40  # per ElevenLabs chunk, measured in D-56 (37-48)
STAGES = ["planning", "fetching", "ranking", "extracting", "scripting", "voicing", "assembling"]


def _ensure_user(email: str, answers_path: Path) -> None:
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == email))
        if user is None:
            from app.users import create_user

            user = create_user(db, email, secrets.token_urlsafe(16))
            db.flush()
        # New users start with {"topics": [], "avoid": []}: that is not a profile.
        if (user.preferences.interest_profile or {}).get("topics"):
            return
        answers = json.loads(answers_path.read_text(encoding="utf-8"))
        profile, usage = extract_profile(answers, get_llm(get_settings()))
        if not profile.topics:
            raise SystemExit(f"{email}: profile extraction returned no topics; stopping")
        user.preferences.interest_profile = profile.model_dump()
        print(f"{email}: profile extracted (${usage.cost_usd:.4f}), {len(profile.topics)} topics")


def _release_parked(email: str) -> None:
    """An episode stopped after scripting stays 'voicing' (in progress), which
    would block the next one for this user (one in progress per user, D-37)."""
    with session_scope() as db:
        user = db.scalar(select(User).where(User.email == email))
        parked = db.scalars(
            select(Episode).where(
                Episode.user_id == user.id,
                Episode.status.not_in([EpisodeStatus.READY, EpisodeStatus.FAILED]),
            )
        ).all()
        for ep in parked:
            if (ep.error or "").startswith(STOPPED_AFTER):
                ep.failed_stage = ep.status.value
                ep.status = EpisodeStatus.FAILED


def run() -> list[int]:
    ids = []
    for email, answers_path in PROFILES.items():
        _ensure_user(email, answers_path)
        _release_parked(email)
        with session_scope() as db:
            owner = db.scalar(select(User).where(User.email == email))
            ep = create_episode(
                db, owner, focus=None, target_minutes=MINUTES, trigger=EpisodeTrigger.MANUAL
            )
            ep_id = ep.id
        print(f"{email}: episode {ep_id} running to scripting ...", flush=True)
        run_episode(ep_id, stop_after="scripting")
        ids.append(ep_id)
    return ids


def _episode_row(db, ep: Episode, rate: float) -> dict | None:
    steps = db.scalars(select(PipelineStep).where(PipelineStep.episode_id == ep.id)).all()
    cost: dict[str, float] = defaultdict(float)
    secs: dict[str, float] = defaultdict(float)
    for s in steps:
        if s.provider == "system":
            continue
        cost[s.stage] += float(s.cost_usd or 0)
        secs[s.stage] += (s.latency_ms or 0) / 1000
    ok = {s.stage for s in steps if s.status == StepStatus.SUCCESS}
    if "scripting" not in ok or not ep.script:
        return None
    # The scripting row's latency is the sum of the writer calls only; the
    # grounding calls run between them and have their own row.
    secs["scripting"] += secs.pop("grounding", 0.0)
    cost["scripting"] += cost.pop("grounding", 0.0)

    script = Script.model_validate(ep.script)
    chunks = chunk_script(script)
    chars = sum(len(t.text) for c in chunks for t in c)
    words = sum(len(t.text.split()) for sec in script.sections for t in sec.turns)
    voiced = "voicing" in ok
    if not voiced:
        cost["voicing"] = chars / 1000 * rate
        longest = max(sum(len(t.text) for t in c) for c in chunks)
        secs["voicing"] = longest / CHARS_PER_SECOND  # <= 4 chunks, all in parallel
        secs["assembling"] = 15.0  # measured 8-23 s
    return {
        "id": ep.id,
        "minutes": ep.target_minutes,
        "words": words,
        "chars": chars,
        "voiced": voiced,
        "cost": dict(cost),
        "secs": dict(secs),
    }


def report(ids: list[int] | None) -> None:
    rate = get_settings().elevenlabs_usd_per_1k_chars
    with session_scope() as db:
        q = select(Episode).join(User).where(User.is_synthetic.is_(False)).order_by(Episode.id)
        if ids:
            q = q.where(Episode.id.in_(ids))
        rows = [r for ep in db.scalars(q).all() if (r := _episode_row(db, ep, rate))]
    if not rows:
        print("no episodes with a successful scripting stage")
        return

    print(f"\nElevenLabs rate: ${rate}/1k chars (estimate). 'est' = voicing not run, estimated.\n")
    stage_cols = " ".join(f"{s[:5]:>12}" for s in STAGES)
    head = f"{'ep':>6} {'min':>3} {'words':>5} {'chars':>5} {stage_cols}"
    print(head + f" {'TOTAL':>14}")
    for r in rows:
        cells = [f"${r['cost'].get(s, 0):.3f}/{r['secs'].get(s, 0):.0f}s" for s in STAGES]
        tot_c, tot_s = sum(r["cost"].values()), sum(r["secs"].values())
        flag = "" if r["voiced"] else " est"
        print(
            f"{r['id']:>6} {r['minutes']:>3} {r['words']:>5} {r['chars']:>5} "
            + " ".join(f"{c:>12}" for c in cells)
            + f" ${tot_c:.2f}/{tot_s:.0f}s{flag}"
        )

    def med(key: str, stage: str) -> float:
        return statistics.median(r[key].get(stage, 0) for r in rows)

    print(f"\nMedian over {len(rows)} episodes:")
    by_provider = {
        "OpenAI": sum(med("cost", s) for s in ("planning", "ranking", "scripting")),
        "ElevenLabs (est)": med("cost", "voicing"),
        "Exa": sum(med("cost", s) for s in ("fetching", "extracting")),
    }
    total_c = sum(med("cost", s) for s in STAGES)
    total_s = sum(med("secs", s) for s in STAGES)
    for s in STAGES:
        c, t = med("cost", s), med("secs", s)
        print(f"  {s:<11} ${c:.3f} ({c / total_c:4.0%})   {t:5.0f}s ({t / total_s:4.0%})")
    print(f"  {'total':<11} ${total_c:.2f}          {total_s:5.0f}s")
    for p, c in sorted(by_provider.items(), key=lambda kv: -kv[1]):
        print(f"  {p:<17} ${c:.3f} ({c / total_c:.0%})")


def main() -> None:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("run")
    rep = sub.add_parser("report")
    rep.add_argument("--ids", type=int, nargs="*")
    args = parser.parse_args()
    if args.cmd == "run":
        report(run())
    else:
        report(args.ids)


if __name__ == "__main__":
    main()
