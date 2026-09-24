import time

from openai import OpenAI
from pydantic import BaseModel

from app.config import Settings, get_settings
from app.pricing import cost_for
from app.schemas import RenderedPrompt, Usage


class OpenAILLM:
    """Real LLM adapter. Call shape per .claude/skills/openai-llm and
    docs/DECISIONS.md D-09: client.responses.parse(..., text_format=schema,
    reasoning={"effort": reasoning}); output_parsed is None on refusal, which we
    treat as a stage failure rather than silently passing None along."""

    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        if not settings.openai_api_key:
            raise RuntimeError("OPENAI_API_KEY is not set; cannot construct OpenAILLM")
        self._client = OpenAI(api_key=settings.openai_api_key.get_secret_value())

    def structured(
        self, prompt: RenderedPrompt, schema: type[BaseModel], model: str, reasoning: str
    ) -> tuple[BaseModel, Usage]:
        start = time.monotonic()
        resp = self._client.responses.parse(
            model=model,
            input=[{"role": "user", "content": prompt.text}],
            text_format=schema,
            reasoning={"effort": reasoning},
        )
        latency_ms = int((time.monotonic() - start) * 1000)

        if resp.output_parsed is None:
            raise RuntimeError(f"OpenAI refused to produce structured output for {schema.__name__}")

        usage = resp.usage
        cost_usd, is_estimate = cost_for("openai", model, usage.input_tokens, usage.output_tokens)
        return resp.output_parsed, Usage(
            provider="openai",
            model=model,
            units_in=usage.input_tokens,
            units_out=usage.output_tokens,
            cost_usd=cost_usd,
            cost_is_estimate=is_estimate,
            latency_ms=latency_ms,
            usage_source="exact",
        )
