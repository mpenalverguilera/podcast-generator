import time

from pydantic import BaseModel

from app.schemas import RenderedPrompt, Usage

# Canned payloads keyed by schema class name, for schemas whose all-default
# construction wouldn't produce a useful fixture. Empty in phase 01 -- no real
# runtime schemas exist yet; phases 02-04 add entries here as their prompts and
# schemas land.
_REGISTRY: dict[str, dict] = {}


class FakeLLM:
    """Deterministic LLM for tests/CLI iteration. Never fabricates data for a
    schema nobody's told it how to fake: falls back to zero-arg construction
    only if every field has a default, otherwise raises."""

    def structured(
        self, prompt: RenderedPrompt, schema: type[BaseModel], model: str, reasoning: str
    ) -> tuple[BaseModel, Usage]:
        start = time.monotonic()
        name = schema.__name__
        if name in _REGISTRY:
            parsed = schema.model_validate(_REGISTRY[name])
        else:
            try:
                parsed = schema()
            except Exception as exc:
                raise NotImplementedError(
                    f"FakeLLM has no fixture for {name}; add one to _REGISTRY"
                ) from exc
        latency_ms = int((time.monotonic() - start) * 1000)
        usage = Usage(provider="fake", model=model, latency_ms=latency_ms, usage_source="fake")
        return parsed, usage
