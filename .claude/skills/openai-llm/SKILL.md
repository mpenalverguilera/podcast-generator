---
name: openai-llm
description: How this project calls OpenAI models (profile extraction, query planning, classification, script writing, grounding check) with structured outputs and cost tracking. Use when writing or changing the LLM adapter, the classifier, or any runtime prompt.
---

# OpenAI in this project

Call shapes below are from memory of the Responses API and **must be confirmed in phase 00**
(`docs/phases/00-smoke-test.md`). Record what you confirm in `docs/DECISIONS.md` and fix this file.

## Which model for which job

| Job | Config key | Default | Reasoning | Why |
|---|---|---|---|---|
| Profile extraction (once per user) | `MODEL_PROFILE` | `gpt-6-sol` | low | Rare call, must understand loose descriptions |
| Query planning (per episode) | `MODEL_PLANNER` | `gpt-6-luna` | none | Short structured output |
| Classification (per candidate) | `MODEL_CLASSIFIER` | `gpt-6-luna` | none | High volume, simple decisions |
| Script writing (per episode) | `MODEL_SCRIPT` | `gpt-6-sol` | medium | Quality of writing matters most |
| Grounding check (per episode) | `MODEL_GROUNDING` | `gpt-6-luna` | low | Compare claims to sources |

Price table (per 1M tokens, Sept 2026 developer docs; keep in `app/pricing.py`):

| Model | Input | Cached input | Output |
|---|---|---|---|
| gpt-6-astra | 10.00 | 1.00 | 50.00 |
| gpt-6-sol | 2.00 | 0.20 | 10.00 |
| gpt-6-luna | 0.10 | 0.01 | 0.50 |

Reasoning tokens are billed as output. Phase 00 lists the models actually available to the key; if GPT-6 IDs are missing, use what the key has and update config.

## Structured output (Responses API + Pydantic) [VERIFY]

```python
from openai import OpenAI
from pydantic import BaseModel

client = OpenAI(api_key=settings.openai_api_key)

class QueryPlan(BaseModel):
    queries: list[PlannedQuery]

resp = client.responses.parse(
    model=settings.model_planner,
    input=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ],
    text_format=QueryPlan,
    reasoning={"effort": "none"},
)
plan: QueryPlan = resp.output_parsed           # None if the model refused
usage = resp.usage                              # input_tokens, output_tokens (incl. reasoning)
```

Rules:
- Every LLM call goes through `LLM.structured(...)` in `app/adapters/llm/openai.py`; it returns `(parsed_model, Usage)`.
- Handle refusal / `output_parsed is None` as a stage failure with a clear error.
- Pydantic models used as schemas: no `dict[str, Any]`, no unbounded free-form maps; give lists sensible `max_length` via `Field` where the prompt implies a bound.
- Retries: one automatic retry on 429/5xx with backoff (the SDK's `max_retries` is fine); one semantic retry when our own validation fails, with the validation errors appended to the prompt.
- Cost = input × price_in + output × price_out (+ cached input at the cached price if reported).

## Runtime prompts

Files in `backend/app/prompts/`, named `<name>.v<N>.md`, with a short front-matter header:
```
---
name: script_writer
version: 1
model_key: MODEL_SCRIPT
---
<system prompt text with {placeholders}>
```
A tiny loader renders placeholders with `str.format_map`. Never edit a version that has produced a stored episode; create `v2`. Store `{name: version}` on the episode in `prompt_versions`.

Prompts in this project: `profile_extractor`, `query_planner`, `classifier`, `script_writer`, `grounding_check`. For the script prompt, follow the `podcast-script` skill.

## Scheduled vs on-demand
Scheduled runs may use Flex processing (lower price, slower, occasionally unavailable) **[VERIFY]** parameter name (`service_tier="flex"`); fall back to standard on failure. "Generate now" always uses standard.
