from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from app.governance.errors import GovernanceError

ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class PositionLiquidityInput:
    instrument_id: UUID
    market_value: Decimal
    average_daily_volume_value: Decimal | None


@dataclass(frozen=True, slots=True)
class PositionLiquidity:
    instrument_id: UUID
    days_to_liquidate: Decimal | None
    market_value: Decimal


@dataclass(frozen=True, slots=True)
class LiquidityResult:
    cash_weight: Decimal
    liquid_within_horizon_weight: Decimal
    maximum_days_to_liquidate: Decimal | None
    positions: tuple[PositionLiquidity, ...]
    warnings: tuple[str, ...]


class LiquidityEngine:
    def calculate(
        self,
        positions: Iterable[PositionLiquidityInput],
        cash_value: Decimal,
        portfolio_value: Decimal,
        participation_rate: Decimal = Decimal("0.10"),
        horizon_days: Decimal = Decimal("5"),
    ) -> LiquidityResult:
        rows = tuple(positions)
        if portfolio_value <= ZERO or cash_value < ZERO:
            raise GovernanceError(
                "liquidity requires positive portfolio value and nonnegative cash"
            )
        if not ZERO < participation_rate <= Decimal("1") or horizon_days < ZERO:
            raise GovernanceError("invalid participation rate or liquidity horizon")
        output: list[PositionLiquidity] = []
        warnings: list[str] = []
        liquid_value = cash_value
        all_known = True
        for item in rows:
            if item.market_value < ZERO:
                raise GovernanceError("Phase 5 liquidity supports long-only positions")
            if item.average_daily_volume_value is None or item.average_daily_volume_value <= ZERO:
                days = None
                all_known = False
                warnings.append(f"missing liquidity evidence for {item.instrument_id}")
            else:
                days = item.market_value / (item.average_daily_volume_value * participation_rate)
                if days <= horizon_days:
                    liquid_value += item.market_value
            output.append(PositionLiquidity(item.instrument_id, days, item.market_value))
        known_days = tuple(
            item.days_to_liquidate for item in output if item.days_to_liquidate is not None
        )
        maximum = max(known_days) if all_known and known_days else None
        return LiquidityResult(
            cash_value / portfolio_value,
            liquid_value / portfolio_value,
            maximum,
            tuple(sorted(output, key=lambda item: str(item.instrument_id))),
            tuple(warnings),
        )


def liquidity_metrics(result: LiquidityResult) -> dict[str, Decimal]:
    metrics = {
        "liquidity.cash_weight": result.cash_weight,
        "liquidity.liquid_within_horizon_weight": result.liquid_within_horizon_weight,
    }
    if result.maximum_days_to_liquidate is not None:
        metrics["liquidity.maximum_days_to_liquidate"] = result.maximum_days_to_liquidate
    return metrics
