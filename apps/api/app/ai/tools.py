import json
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from app.ai.errors import DataUnavailable, InvalidToolCall
from app.ai.types import ToolContext, ToolExecutionStatus, ToolResult
from app.governance.authorization import AuthorizationService
from app.governance.errors import AuthorizationDenied
from app.governance.types import Permission


class ReadOnlyPortfolioTools(Protocol):
    def get_holdings(self, fund_id: UUID, as_of: datetime) -> ToolResult: ...

    def get_exposure(
        self, fund_id: UUID, as_of: datetime, max_price_age_seconds: int
    ) -> ToolResult: ...

    def get_risk(self, fund_id: UUID, as_of: datetime) -> ToolResult: ...

    def get_portfolio_snapshot(self, fund_id: UUID, as_of: datetime) -> ToolResult: ...

    def run_scenario(
        self,
        fund_id: UUID,
        scenario_id: UUID,
        as_of: datetime,
        max_price_age_seconds: int,
    ) -> ToolResult: ...

    def get_policy_breaches(self, fund_id: UUID, as_of: datetime) -> ToolResult: ...


def _schema(properties: dict[str, object], required: tuple[str, ...]) -> dict[str, object]:
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def _datetime_schema() -> dict[str, str]:
    return {"type": "string", "format": "date-time"}


TOOL_DEFINITIONS: tuple[dict[str, object], ...] = (
    {
        "type": "function",
        "name": "get_holdings",
        "description": (
            "Read holdings from the latest reproducible portfolio snapshot at or before a cutoff."
        ),
        "strict": True,
        "parameters": _schema({"as_of": _datetime_schema()}, ("as_of",)),
    },
    {
        "type": "function",
        "name": "get_exposure",
        "description": (
            "Calculate point-in-time sector, asset, geography, position, "
            "and concentration exposure."
        ),
        "strict": True,
        "parameters": _schema(
            {
                "as_of": _datetime_schema(),
                "max_price_age_seconds": {"type": "integer", "minimum": 0},
            },
            ("as_of", "max_price_age_seconds"),
        ),
    },
    {
        "type": "function",
        "name": "get_risk",
        "description": "Read persisted deterministic risk metrics at or before a cutoff.",
        "strict": True,
        "parameters": _schema({"as_of": _datetime_schema()}, ("as_of",)),
    },
    {
        "type": "function",
        "name": "get_portfolio_snapshot",
        "description": "Read the latest immutable portfolio snapshot at or before a cutoff.",
        "strict": True,
        "parameters": _schema({"as_of": _datetime_schema()}, ("as_of",)),
    },
    {
        "type": "function",
        "name": "run_scenario",
        "description": (
            "Preview a versioned scenario without persisting or changing portfolio state."
        ),
        "strict": True,
        "parameters": _schema(
            {
                "scenario_id": {"type": "string", "format": "uuid"},
                "as_of": _datetime_schema(),
                "max_price_age_seconds": {"type": "integer", "minimum": 0},
            },
            ("scenario_id", "as_of", "max_price_age_seconds"),
        ),
    },
    {
        "type": "function",
        "name": "get_policy_breaches",
        "description": "Read breach and unavailable outcomes from the latest policy evaluation.",
        "strict": True,
        "parameters": _schema({"as_of": _datetime_schema()}, ("as_of",)),
    },
)


class ToolRegistry:
    def __init__(
        self,
        authorization: AuthorizationService,
        services: ReadOnlyPortfolioTools,
    ) -> None:
        self.authorization = authorization
        self.services = services

    @property
    def definitions(self) -> tuple[dict[str, object], ...]:
        return TOOL_DEFINITIONS

    def execute(
        self, name: str, arguments_json: str, context: ToolContext
    ) -> tuple[ToolExecutionStatus, ToolResult | None, str | None]:
        try:
            self.authorization.require(
                context.actor_user_id, context.fund_id, Permission.USE_AI_ASSISTANT
            )
        except AuthorizationDenied as error:
            return ToolExecutionStatus.DENIED, None, str(error)
        try:
            arguments = self._arguments(name, arguments_json)
            result = self._dispatch(name, arguments, context)
            return ToolExecutionStatus.SUCCEEDED, result, None
        except DataUnavailable as error:
            return ToolExecutionStatus.UNAVAILABLE, None, str(error)
        except (InvalidToolCall, ValueError) as error:
            return ToolExecutionStatus.INVALID, None, str(error)

    def _dispatch(self, name: str, arguments: dict[str, Any], context: ToolContext) -> ToolResult:
        as_of = arguments["as_of"]
        if name == "get_holdings":
            return self.services.get_holdings(context.fund_id, as_of)
        if name == "get_exposure":
            return self.services.get_exposure(
                context.fund_id, as_of, arguments["max_price_age_seconds"]
            )
        if name == "get_risk":
            return self.services.get_risk(context.fund_id, as_of)
        if name == "get_portfolio_snapshot":
            return self.services.get_portfolio_snapshot(context.fund_id, as_of)
        if name == "run_scenario":
            return self.services.run_scenario(
                context.fund_id,
                arguments["scenario_id"],
                as_of,
                arguments["max_price_age_seconds"],
            )
        if name == "get_policy_breaches":
            return self.services.get_policy_breaches(context.fund_id, as_of)
        raise InvalidToolCall(f"unknown or non-read-only tool: {name}")

    @staticmethod
    def _arguments(name: str, payload: str) -> dict[str, Any]:
        if len(payload.encode()) > 8192:
            raise InvalidToolCall("tool arguments exceed 8192 bytes")
        try:
            raw = json.loads(payload)
        except json.JSONDecodeError as error:
            raise InvalidToolCall("tool arguments are not valid JSON") from error
        if not isinstance(raw, dict):
            raise InvalidToolCall("tool arguments must be a JSON object")
        fields = {
            "get_holdings": {"as_of"},
            "get_exposure": {"as_of", "max_price_age_seconds"},
            "get_risk": {"as_of"},
            "get_portfolio_snapshot": {"as_of"},
            "run_scenario": {"scenario_id", "as_of", "max_price_age_seconds"},
            "get_policy_breaches": {"as_of"},
        }.get(name)
        if fields is None:
            raise InvalidToolCall(f"unknown or non-read-only tool: {name}")
        if set(raw) != fields:
            raise InvalidToolCall("tool arguments have missing or unexpected fields")
        try:
            as_of = datetime.fromisoformat(str(raw["as_of"]).replace("Z", "+00:00"))
        except ValueError as error:
            raise InvalidToolCall("as_of must be an ISO-8601 timestamp") from error
        if as_of.tzinfo is None:
            raise InvalidToolCall("as_of must include a timezone")
        result: dict[str, Any] = {"as_of": as_of}
        if "max_price_age_seconds" in fields:
            age = raw["max_price_age_seconds"]
            if isinstance(age, bool) or not isinstance(age, int) or age < 0:
                raise InvalidToolCall("max_price_age_seconds must be a nonnegative integer")
            result["max_price_age_seconds"] = age
        if "scenario_id" in fields:
            try:
                result["scenario_id"] = UUID(str(raw["scenario_id"]))
            except ValueError as error:
                raise InvalidToolCall("scenario_id must be a UUID") from error
        return result
