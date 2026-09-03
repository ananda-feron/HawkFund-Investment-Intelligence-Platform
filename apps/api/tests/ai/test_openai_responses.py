from typing import Any

from app.ai.openai_responses import OpenAIResponsesProvider
from app.ai.tools import TOOL_DEFINITIONS


class FakeResponses:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(kwargs)
        if len(self.calls) == 1:
            return {
                "id": "resp-1",
                "output": [
                    {
                        "type": "function_call",
                        "call_id": "call-1",
                        "name": "get_holdings",
                        "arguments": '{"as_of":"2026-03-31T20:00:00Z"}',
                    }
                ],
            }
        return {"id": "resp-2", "output": [], "output_text": "Grounded answer"}


class FakeClient:
    def __init__(self) -> None:
        self.responses = FakeResponses()


def test_responses_adapter_disables_storage_and_serializes_tools() -> None:
    client = FakeClient()
    provider = OpenAIResponsesProvider(client, "configured-model")

    first = provider.start("instructions", "question", TOOL_DEFINITIONS, "safe-user")
    second = provider.continue_with_tools(
        "instructions",
        first.response_id,
        (("call-1", '{"status":"SUCCEEDED"}'),),
        TOOL_DEFINITIONS,
        "safe-user",
    )

    assert first.tool_calls[0].name == "get_holdings"
    assert second.text == "Grounded answer"
    assert client.responses.calls[0]["tool_choice"] == "required"
    assert client.responses.calls[1]["tool_choice"] == "auto"
    assert all(call["store"] is False for call in client.responses.calls)
    assert all(call["parallel_tool_calls"] is False for call in client.responses.calls)
    assert client.responses.calls[1]["previous_response_id"] == "resp-1"
