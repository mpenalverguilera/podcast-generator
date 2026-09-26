from typing import Protocol

from app.schemas import Turn, Usage


class TTS(Protocol):
    # Provider name as pricing.cost_for knows it; lets the voice stage price a
    # batch before sending it, without isinstance checks on adapters.
    provider: str

    def synthesize_chunk(self, turns: list[Turn], seed: int | None) -> tuple[bytes, Usage]: ...
