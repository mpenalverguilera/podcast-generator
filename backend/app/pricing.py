from app.config import get_settings

# $ per 1M tokens: (input, cached_input, output). Reasoning tokens are billed as
# output. Confirmed against the openai-llm skill / docs/DECISIONS.md D-09.
OPENAI_PRICES_PER_1M: dict[str, tuple[float, float, float]] = {
    "gpt-6-astra": (10.00, 1.00, 50.00),
    "gpt-6-sol": (2.00, 0.20, 10.00),
    "gpt-6-luna": (0.10, 0.01, 0.50),
}

# $ per 1M input tokens. Output tokens are free for Jev. From docs.typesafe.ai/models
# (docs/DECISIONS.md D-32).
TYPESAFE_PRICES_PER_1M: dict[str, float] = {
    "jev-1.13.0": 0.042,
}


def cost_for(
    provider: str,
    model: str | None,
    units_in: int,
    units_out: int = 0,
    *,
    exa_cost_usd: float | None = None,
) -> tuple[float, bool]:
    """Returns (cost_usd, cost_is_estimate) for one provider call.

    cost_is_estimate is True only for ElevenLabs: its units_in (characters) is
    exact (the character-cost response header), but the $/character rate is a
    config default since the real plan price isn't visible with this key
    (docs/DECISIONS.md D-12).
    """
    if provider == "openai":
        if model not in OPENAI_PRICES_PER_1M:
            raise ValueError(f"no price entry for OpenAI model {model!r}")
        price_in, _price_cached, price_out = OPENAI_PRICES_PER_1M[model]
        cost = (units_in * price_in + units_out * price_out) / 1_000_000
        return cost, False

    if provider == "typesafe":
        if model not in TYPESAFE_PRICES_PER_1M:
            raise ValueError(f"no price entry for TypeSafe model {model!r}")
        return units_in * TYPESAFE_PRICES_PER_1M[model] / 1_000_000, False

    if provider == "exa":
        # Exa returns its own exact costDollars per call; there's no units*rate
        # to compute here, just pass through what the adapter already read.
        return (exa_cost_usd or 0.0), False

    if provider == "elevenlabs":
        settings = get_settings()
        cost = units_in * settings.elevenlabs_usd_per_1k_chars / 1000
        return cost, True

    # "local" (e.g. assemble, no external call) and "fake" adapters.
    return 0.0, False
