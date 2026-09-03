from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID


class ToolExecutionStatus(str, Enum):
    SUCCEEDED = "SUCCEEDED"
    UNAVAILABLE = "UNAVAILABLE"
    DENIED = "DENIED"
    INVALID = "INVALID"


class ConversationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    REFUSED = "REFUSED"
    FAILED = "FAILED"


class AIMessageRole(str, Enum):
    USER = "USER"
    ASSISTANT = "ASSISTANT"
    REFUSAL = "REFUSAL"


@dataclass(frozen=True, slots=True)
class SourceReference:
    source_type: str
    source_id: str
    label: str
    as_of: datetime | None
    input_hash: str | None = None

    def as_dict(self) -> dict[str, str | None]:
        return {
            "source_type": self.source_type,
            "source_id": self.source_id,
            "label": self.label,
            "as_of": None if self.as_of is None else self.as_of.isoformat(),
            "input_hash": self.input_hash,
        }


@dataclass(frozen=True, slots=True)
class ToolResult:
    data: dict[str, Any]
    sources: tuple[SourceReference, ...]
    warnings: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "data": self.data,
            "sources": [item.as_dict() for item in self.sources],
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True, slots=True)
class ToolContext:
    conversation_id: UUID
    actor_user_id: UUID
    fund_id: UUID


@dataclass(frozen=True, slots=True)
class ToolCall:
    call_id: str
    name: str
    arguments_json: str


@dataclass(frozen=True, slots=True)
class ModelTurn:
    response_id: str
    text: str | None
    tool_calls: tuple[ToolCall, ...]


@dataclass(frozen=True, slots=True)
class AssistantAnswer:
    conversation_id: UUID
    status: ConversationStatus
    text: str
    sources: tuple[SourceReference, ...]
    warnings: tuple[str, ...]
