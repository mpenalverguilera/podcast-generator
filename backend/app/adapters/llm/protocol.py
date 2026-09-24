from typing import Protocol

from pydantic import BaseModel

from app.schemas import RenderedPrompt, Usage


class LLM(Protocol):
    def structured(
        self, prompt: RenderedPrompt, schema: type[BaseModel], model: str, reasoning: str
    ) -> tuple[BaseModel, Usage]: ...
