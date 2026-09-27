"""Optional on-disk trace of the scripting stage (docs/DECISIONS.md D-60).

When SCRIPT_TRACE_DIR is set, script.run writes every intermediate step --
inputs, outline, each section's draft/flags/patch, polish, the polish check
and the final script -- plus the exact rendered prompt and usage of every
model call to <SCRIPT_TRACE_DIR>/<episode_id>/. When it is unset every method
here is a no-op and nothing touches the disk. Debugging aid only: nothing in
the pipeline reads these files back.
"""

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from app.adapters.llm.protocol import LLM
from app.schemas import RenderedPrompt, Turn, UnsupportedClaim, Usage


class ScriptTrace:
    def __init__(self, root: Path | None, episode_id: int) -> None:
        self.dir = Path(root) / str(episode_id) if root else None
        self.calls: list[dict[str, Any]] = []

    @property
    def enabled(self) -> bool:
        return self.dir is not None

    def write_text(self, name: str, text: str) -> None:
        if self.dir is None:
            return
        path = self.dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text.rstrip() + "\n", encoding="utf-8")

    def write_json(self, name: str, obj: Any) -> None:
        self.write_text(name, json.dumps(obj, indent=2, ensure_ascii=False, default=str))

    def wrap(self, llm: LLM, label: str, section: int | None = None) -> LLM:
        """The LLM itself when tracing is off; otherwise a proxy that records
        the rendered prompt and usage of the call made through it."""
        return llm if self.dir is None else _TracedLLM(llm, self, label, section)

    def record_call(
        self, label: str, section: int | None, prompt: RenderedPrompt, usage: Usage
    ) -> None:
        n = len(self.calls) + 1
        prompt_file = f"prompts/{n:02d}_{label}.txt"
        self.write_text(prompt_file, prompt.text)
        self.calls.append(
            {
                "n": n,
                "step": label,
                "section": section,
                "prompt": f"{prompt.name}.v{prompt.version}",
                "model": usage.model,
                "tokens_in": usage.units_in,
                "tokens_out": usage.units_out,
                "cost_usd": usage.cost_usd,
                "latency_ms": usage.latency_ms,
                "prompt_file": prompt_file,
            }
        )
        # Rewritten after every call, so a run that fails midway still
        # leaves a complete record of what it spent.
        self.write_json("calls.json", self.calls)


class _TracedLLM:
    def __init__(self, llm: LLM, trace: ScriptTrace, label: str, section: int | None) -> None:
        self._llm, self._trace, self._label, self._section = llm, trace, label, section

    def structured(
        self, prompt: RenderedPrompt, schema: type[BaseModel], model: str, reasoning: str
    ) -> tuple[BaseModel, Usage]:
        result, usage = self._llm.structured(prompt, schema, model, reasoning)
        self._trace.record_call(self._label, self._section, prompt, usage)
        return result, usage


# --- markdown renderers ---------------------------------------------------------


def turns_md(turns: list[Turn], names: dict[str, str]) -> str:
    return "\n".join(f"- **{i} {names[t.speaker]}:** {t.text}" for i, t in enumerate(turns))


def turns_diff_md(before: list[Turn], after: list[Turn], names: dict[str, str]) -> str:
    """Per turn: unchanged turns plain, changed ones as before → after. If
    polish changed the number of turns, the whole section is shown twice."""
    if len(before) != len(after):
        return (
            f"_turn count changed {len(before)} → {len(after)}_\n\n**before:**\n"
            f"{turns_md(before, names)}\n\n**after:**\n{turns_md(after, names)}"
        )
    lines = []
    for i, (b, a) in enumerate(zip(before, after, strict=True)):
        if (b.speaker, b.text) == (a.speaker, a.text):
            lines.append(f"- {i} {names[a.speaker]}: {a.text}")
        else:
            lines.append(
                f"- **{i} {names[a.speaker]} CHANGED**\n"
                f"  - before ({names[b.speaker]}): {b.text}\n"
                f"  - after → {a.text}"
            )
    return "\n".join(lines)


def claims_json(claims: list[UnsupportedClaim]) -> list[dict[str, Any]]:
    return [c.model_dump() for c in claims]
