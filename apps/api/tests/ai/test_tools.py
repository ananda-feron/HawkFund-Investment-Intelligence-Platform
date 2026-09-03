import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.ai.tools import TOOL_DEFINITIONS, ToolRegistry
from app.ai.types import SourceReference, ToolContext, ToolExecutionStatus, ToolResult
from app.governance.authorization import AuthorizationService
from tests.conftest import FUND_ID
from tests.governance.factories import ANALYST_ID, seed_roles

AS_OF = datetime(2026, 3, 31, 20, tzinfo=UTC)


class FakeTools:
    calls: list[tuple[object, ...]]

    def __init__(self) -> None:
        self.calls = []

    def get_holdings(self, fund_id: UUID, as_of: datetime) -> ToolResult:
        self.calls.append(("get_holdings", fund_id, as_of))
        return ToolResult(
            {"holdings": []},
            (SourceReference("portfolio_snapshot", "snapshot-1", "Snapshot", as_of),),
        )

    def get_exposure(
        self, fund_id: UUID, as_of: datetime, max_price_age_seconds: int
    ) -> ToolResult:
        raise AssertionError("unexpected call")

    def get_risk(self, fund_id: UUID, as_of: datetime) -> ToolResult:
        raise AssertionError("unexpected call")

    def get_portfolio_snapshot(self, fund_id: UUID, as_of: datetime) -> ToolResult:
        raise AssertionError("unexpected call")

    def run_scenario(
        self,
        fund_id: UUID,
        scenario_id: UUID,
        as_of: datetime,
        max_price_age_seconds: int,
    ) -> ToolResult:
        raise AssertionError("unexpected call")

    def get_policy_breaches(self, fund_id: UUID, as_of: datetime) -> ToolResult:
        raise AssertionError("unexpected call")


def test_tool_schemas_are_strict() -> None:
    assert {item["name"] for item in TOOL_DEFINITIONS} == {
        "get_holdings",
        "get_exposure",
        "get_risk",
        "get_portfolio_snapshot",
        "run_scenario",
        "get_policy_breaches",
    }
    assert all(item["strict"] is True for item in TOOL_DEFINITIONS)
    assert all(item["parameters"]["additionalProperties"] is False for item in TOOL_DEFINITIONS)  # type: ignore[index]


def test_registry_binds_fund_to_authorized_context(session) -> None:
    seed_roles(session)
    tools = FakeTools()
    registry = ToolRegistry(AuthorizationService(session), tools)
    context = ToolContext(uuid4(), ANALYST_ID, FUND_ID)

    status, result, error = registry.execute(
        "get_holdings", json.dumps({"as_of": AS_OF.isoformat()}), context
    )

    assert status is ToolExecutionStatus.SUCCEEDED
    assert result is not None and error is None
    assert tools.calls == [("get_holdings", FUND_ID, AS_OF)]


def test_registry_rejects_scope_override_and_mutation_tool(session) -> None:
    seed_roles(session)
    tools = FakeTools()
    registry = ToolRegistry(AuthorizationService(session), tools)
    context = ToolContext(uuid4(), ANALYST_ID, FUND_ID)

    override = json.dumps({"as_of": AS_OF.isoformat(), "fund_id": str(uuid4())})
    first = registry.execute("get_holdings", override, context)
    second = registry.execute("approve_proposal", "{}", context)

    assert first[0] is ToolExecutionStatus.INVALID
    assert second[0] is ToolExecutionStatus.INVALID
    assert tools.calls == []


def test_registry_denies_actor_without_fund_role(session) -> None:
    registry = ToolRegistry(AuthorizationService(session), FakeTools())
    context = ToolContext(uuid4(), uuid4(), FUND_ID)

    status, result, error = registry.execute(
        "get_holdings", json.dumps({"as_of": AS_OF.isoformat()}), context
    )

    assert status is ToolExecutionStatus.DENIED
    assert result is None
    assert error is not None
