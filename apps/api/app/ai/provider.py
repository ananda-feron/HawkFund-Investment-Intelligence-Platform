from typing import Protocol

from app.ai.types import ModelTurn


class ModelProvider(Protocol):
    @property
    def model(self) -> str: ...

    def start(
        self,
        instructions: str,
        user_prompt: str,
        tools: tuple[dict[str, object], ...],
        safety_identifier: str,
    ) -> ModelTurn: ...

    def continue_with_tools(
        self,
        instructions: str,
        previous_response_id: str,
        tool_outputs: tuple[tuple[str, str], ...],
        tools: tuple[dict[str, object], ...],
        safety_identifier: str,
    ) -> ModelTurn: ...
