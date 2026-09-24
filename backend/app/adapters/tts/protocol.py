from typing import Protocol

from app.schemas import Turn, Usage


class TTS(Protocol):
    def synthesize_chunk(self, turns: list[Turn], seed: int | None) -> tuple[bytes, Usage]: ...
