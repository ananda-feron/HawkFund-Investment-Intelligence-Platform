from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class RiskResult:
    observation_count: int
    confidence_level: Decimal
    annualized_volatility: Decimal | None
    beta: Decimal | None
    value_at_risk_return: Decimal
    expected_shortfall_return: Decimal
    value_at_risk_amount: Decimal
    expected_shortfall_amount: Decimal
    tracking_error: Decimal | None
    largest_position_weight: Decimal
    herfindahl_index: Decimal
