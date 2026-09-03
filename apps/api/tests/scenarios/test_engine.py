from decimal import Decimal
from uuid import UUID

import pytest

from app.exposures.types import InstrumentClassification
from app.scenarios.engine import ScenarioEngine
from app.scenarios.errors import InvalidScenario
from app.scenarios.types import (
    InstrumentSensitivity,
    ScenarioDefinition,
    ScenarioKind,
    ScenarioShock,
    ShockTargetType,
    ShockUnit,
)
from tests.conftest import FUND_ID
from tests.scenarios.factories import valuation

AAPL = UUID(int=11)
MSFT = UUID(int=12)
SPY = UUID(int=13)


def shock(number: int, target_type, target: str, magnitude: str, unit, sequence: int):
    return ScenarioShock(UUID(int=number), target_type, target, Decimal(magnitude), unit, sequence)


def definition(*shocks: ScenarioShock) -> ScenarioDefinition:
    return ScenarioDefinition(
        UUID(int=100), FUND_ID, "Stress", 1, ScenarioKind.HYPOTHETICAL, shocks, {}
    )


def test_security_scenario_calculates_position_and_portfolio_impact() -> None:
    scenario = definition(
        shock(1, ShockTargetType.SECURITY, str(AAPL), "-0.20", ShockUnit.RELATIVE_RETURN, 1),
        shock(2, ShockTargetType.SECURITY, str(MSFT), "-0.15", ShockUnit.RELATIVE_RETURN, 2),
        shock(3, ShockTargetType.SECURITY, str(SPY), "-0.10", ShockUnit.RELATIVE_RETURN, 3),
    )
    baseline = valuation(((AAPL, "400"), (MSFT, "300"), (SPY, "200")), cash="100")

    result = ScenarioEngine().apply(baseline, scenario, {})

    assert result.pnl_impact == Decimal("-145.00")
    assert result.projected.portfolio_value == Decimal("855.00")
    assert result.portfolio_return_impact == Decimal("-0.145")
    assert {item.instrument_id: item.projected_market_value for item in result.positions} == {
        AAPL: Decimal("320.00"),
        MSFT: Decimal("255.00"),
        SPY: Decimal("180.00"),
    }
    assert baseline.portfolio_value == Decimal("1000")


def test_market_sector_rate_and_factor_shocks_have_explicit_contributions() -> None:
    scenario = definition(
        shock(1, ShockTargetType.MARKET, "ALL", "-0.10", ShockUnit.RELATIVE_RETURN, 1),
        shock(2, ShockTargetType.SECTOR, "Technology", "-0.05", ShockUnit.RELATIVE_RETURN, 2),
        shock(3, ShockTargetType.RATE, "USD", "0.01", ShockUnit.YIELD_CHANGE, 3),
        shock(4, ShockTargetType.FACTOR, "Growth", "-0.10", ShockUnit.FACTOR_MOVE, 4),
    )
    baseline = valuation(((AAPL, "100"),))
    classifications = {AAPL: InstrumentClassification(AAPL, "Technology", "Equity", "US")}
    sensitivities = {AAPL: InstrumentSensitivity(AAPL, Decimal("5"), (("Growth", Decimal("1.2")),))}

    result = ScenarioEngine().apply(baseline, scenario, classifications, sensitivities)

    assert result.positions[0].return_impact == Decimal("-0.32")
    assert result.positions[0].projected_market_value == Decimal("68.00")
    assert tuple(item.return_impact for item in result.positions[0].contributions) == (
        Decimal("-0.10"),
        Decimal("-0.05"),
        Decimal("-0.05"),
        Decimal("-0.120"),
    )


def test_missing_sensitivity_is_disclosed_and_nonpositive_price_is_rejected() -> None:
    rate = definition(shock(1, ShockTargetType.RATE, "USD", "0.01", ShockUnit.YIELD_CHANGE, 1))
    result = ScenarioEngine().apply(valuation(((AAPL, "100"),)), rate, {})
    assert result.pnl_impact == Decimal("0")
    assert "missing duration" in result.warnings[0]

    total_loss = definition(
        shock(2, ShockTargetType.SECURITY, str(AAPL), "-1", ShockUnit.RELATIVE_RETURN, 1)
    )
    with pytest.raises(InvalidScenario):
        ScenarioEngine().apply(valuation(((AAPL, "100"),)), total_loss, {})
