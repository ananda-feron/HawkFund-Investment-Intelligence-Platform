from collections.abc import Mapping
from typing import Any, Protocol, cast

from app.ai.errors import ModelProtocolError
from app.ai.types import ModelTurn, ToolCall


class ResponsesResource(Protocol):
    def create(self, **kwargs: Any) -> Any: ...


class OpenAIClient(Protocol):
    responses: ResponsesResource


class OpenAIResponsesProvider:
    """Responses API adapter with an injected OpenAI-compatible client."""

    def __init__(self, client: OpenAIClient, model: str) -> None:
        if not model.strip():
            raise ValueError("model is required")
        self.client = client
        self._model = model

    @property
    def model(self) -> str:
        return self._model

    def start(
        self,
        instructions: str,
        user_prompt: str,
        tools: tuple[dict[str, object], ...],
        safety_identifier: str,
    ) -> ModelTurn:
        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            input=[{"role": "user", "content": user_prompt}],
            tools=list(tools),
            tool_choice="required",
            parallel_tool_calls=False,
            store=False,
            safety_identifier=safety_identifier,
        )
        return self._turn(response)

    def continue_with_tools(
        self,
        instructions: str,
        previous_response_id: str,
        tool_outputs: tuple[tuple[str, str], ...],
        tools: tuple[dict[str, object], ...],
        safety_identifier: str,
    ) -> ModelTurn:
        response = self.client.responses.create(
            model=self.model,
            instructions=instructions,
            previous_response_id=previous_response_id,
            input=[
                {"type": "function_call_output", "call_id": call_id, "output": output}
                for call_id, output in tool_outputs
            ],
            tools=list(tools),
            tool_choice="auto",
            parallel_tool_calls=False,
            store=False,
            safety_identifier=safety_identifier,
        )
        return self._turn(response)

    @staticmethod
    def _turn(raw: Any) -> ModelTurn:
        payload = OpenAIResponsesProvider._mapping(raw)
        response_id = payload.get("id")
        if not isinstance(response_id, str):
            raise ModelProtocolError("provider response has no string id")
        calls: list[ToolCall] = []
        for item in payload.get("output", []):
            if not isinstance(item, Mapping) or item.get("type") != "function_call":
                continue
            call_id = item.get("call_id")
            name = item.get("name")
            arguments = item.get("arguments")
            if not all(isinstance(value, str) for value in (call_id, name, arguments)):
                raise ModelProtocolError("provider returned an invalid function call")
            calls.append(ToolCall(cast(str, call_id), cast(str, name), cast(str, arguments)))
        output_text = payload.get("output_text")
        text = output_text if isinstance(output_text, str) and output_text.strip() else None
        return ModelTurn(response_id, text, tuple(calls))

    @staticmethod
    def _mapping(raw: Any) -> Mapping[str, Any]:
        if isinstance(raw, Mapping):
            return raw
        model_dump = getattr(raw, "model_dump", None)
        if callable(model_dump):
            payload = model_dump()
            if isinstance(payload, Mapping):
                return payload
        raise ModelProtocolError("provider response cannot be converted to a mapping")
