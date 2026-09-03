from decimal import Decimal
from uuid import UUID

from app.governance.liquidity import (
    LiquidityEngine,
    PositionLiquidityInput,
    liquidity_metrics,
)


def test_liquidity_metrics_are_policy_ready_and_missing_data_is_explicit() -> None:
    result = LiquidityEngine().calculate(
        (
            PositionLiquidityInput(UUID(int=1), Decimal("400"), Decimal("1000")),
            PositionLiquidityInput(UUID(int=2), Decimal("500"), None),
        ),
        cash_value=Decimal("100"),
        portfolio_value=Decimal("1000"),
        participation_rate=Decimal("0.10"),
        horizon_days=Decimal("5"),
    )

    assert result.cash_weight == Decimal("0.1")
    assert result.liquid_within_horizon_weight == Decimal("0.5")
    assert result.maximum_days_to_liquidate is None
    assert result.warnings
    assert "liquidity.maximum_days_to_liquidate" not in liquidity_metrics(result)
