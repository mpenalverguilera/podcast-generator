"""Fact-checker noise for D-61: grounding_check.v2 with Luna at low vs medium, 3 runs each.

Run from the repo root (real OpenAI calls; cached, so a re-run costs nothing):
    uv run --project backend python eval/grounding_noise.py [<trace root>]

Inputs are the rendered grounding prompts that the D-60 scripting trace saved for each story
section's first check (`<trace root>/<episode>/prompts/NN_sK_ground.txt`), so every run sees
exactly the prompt production sent. The trace root defaults to the main checkout's data/tmp.
The decision rule was fixed in docs/DECISIONS.md D-61 before this script first ran.
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.adapters.llm.openai import OpenAILLM
from app.config import get_settings
from app.schemas import GroundingReport, RenderedPrompt

EVAL_DIR = Path(__file__).parent
RESULTS_DIR = EVAL_DIR / "results"
CACHE = RESULTS_DIR / "grounding_noise.jsonl"
DEFAULT_TRACE_ROOT = EVAL_DIR.parents[3] / "data" / "tmp"  # worktree -> main checkout
EPISODES = ["15708", "15709", "15710"]
REASONING_LEVELS = ["low", "medium"]
RUNS = 3
PROMPT_VERSION = 2  # the traces were rendered from grounding_check.v2
_TURN_RE = re.compile(r"^\s*turn (\d+):", re.MULTILINE)
_SECTION_RE = re.compile(r"^Section (\d+) \(", re.MULTILINE)


def load_sections(root: Path) -> list[dict]:
    sections = []
    for ep in EPISODES:
        for path in sorted((root / ep / "prompts").glob("*_s[0-9]_ground.txt")):
            text = path.read_text(encoding="utf-8")
            turns = [
                (int(si), int(ti))
                for si, block in _split_sections(text)
                for ti in _TURN_RE.findall(block)
            ]
            sections.append({"id": f"{ep}/{path.stem}", "text": text, "turns": turns})
    return sections


def _split_sections(text: str) -> list[tuple[str, str]]:
    starts = list(_SECTION_RE.finditer(text))
    return [
        (m.group(1), text[m.start() : starts[i + 1].start() if i + 1 < len(starts) else None])
        for i, m in enumerate(starts)
    ]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_TRACE_ROOT
    sections = load_sections(root)
    assert len(sections) == 12, f"expected 12 story sections, found {len(sections)}"
    settings = get_settings()
    model = settings.model_grounding
    llm = OpenAILLM(settings)

    cached = {}
    if CACHE.exists():
        for line in CACHE.read_text(encoding="utf-8").splitlines():
            rec = json.loads(line)
            cached[(rec["section"], rec["model"], rec["reasoning"], rec["run"])] = rec

    jobs = [
        (s, r, n)
        for s in sections
        for r in REASONING_LEVELS
        for n in range(RUNS)
        if (s["id"], model, r, n) not in cached
    ]

    def one(job) -> dict:
        section, reasoning, run = job
        prompt = RenderedPrompt(
            name="grounding_check", version=PROMPT_VERSION, text=section["text"]
        )
        report, usage = llm.structured(prompt, GroundingReport, model=model, reasoning=reasoning)
        return {
            "section": section["id"],
            "model": model,
            "reasoning": reasoning,
            "run": run,
            "flags": [[c.section_index, c.turn_index, c.claim] for c in report.unsupported],
            "cost_usd": usage.cost_usd,
            "latency_ms": usage.latency_ms,
        }

    # Warm-up call first: concurrent first calls to responses.parse race (see classifier_grid.py).
    if jobs:
        rec = one(jobs[0])
        cached[(rec["section"], rec["model"], rec["reasoning"], rec["run"])] = rec
    with ThreadPoolExecutor(max_workers=6) as pool:
        for rec in pool.map(one, jobs[1:]):
            cached[(rec["section"], rec["model"], rec["reasoning"], rec["run"])] = rec
    RESULTS_DIR.mkdir(exist_ok=True)
    CACHE.write_text("".join(json.dumps(r) + "\n" for r in cached.values()), encoding="utf-8")
    print(f"{len(jobs)} new calls")

    total_turns = sum(len(s["turns"]) for s in sections)
    lines = [
        "# Fact-checker noise (D-61)",
        "",
        f"`grounding_check.v2`, {model}, {len(sections)} story sections from episodes "
        f"{', '.join(EPISODES)} ({total_turns} turns), {RUNS} runs per reasoning level. A turn "
        "*flips* when it is flagged in some runs and not in others.",
        "",
        "| reasoning | flipping turns | sections with a flip | avg flags / section | "
        "$ / check | p50 ms | max ms |",
        "|---|---|---|---|---|---|---|",
    ]
    summary = {}
    for reasoning in REASONING_LEVELS:
        flips = sections_with_flip = flags = 0
        recs = []
        for s in sections:
            runs = [cached[(s["id"], model, reasoning, n)] for n in range(RUNS)]
            recs += runs
            flagged = [{(f[0], f[1]) for f in r["flags"]} for r in runs]
            section_flips = sum(1 for t in s["turns"] if 0 < sum(t in f for f in flagged) < RUNS)
            flips += section_flips
            sections_with_flip += section_flips > 0
            flags += sum(len(r["flags"]) for r in runs)
        lat = sorted(r["latency_ms"] for r in recs)
        cost = sum(r["cost_usd"] for r in recs) / len(recs)
        summary[reasoning] = {"flips": flips, "cost": cost}
        lines.append(
            f"| {reasoning} | {flips}/{total_turns} | {sections_with_flip}/{len(sections)} | "
            f"{flags / len(recs):.2f} | ${cost:.5f} | {lat[len(lat) // 2]} | {lat[-1]} |"
        )
    low, med = summary["low"], summary["medium"]
    cut = 1 - med["flips"] / low["flips"] if low["flips"] else 0.0
    ratio = med["cost"] / low["cost"]
    choice = "medium" if cut >= 1 / 3 and ratio < 2 else "low"
    lines += [
        "",
        f"medium vs low: flips cut by {cut:.0%}, cost x{ratio:.2f}. Rule (D-61): medium if flips "
        f"drop by at least a third at under 2x the cost. **Chosen: {choice}.**",
    ]
    (RESULTS_DIR / "grounding_noise.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
