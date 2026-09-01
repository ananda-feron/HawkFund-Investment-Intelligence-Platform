from decimal import Decimal
from uuid import UUID

from app.exposures.engine import ExposureEngine
from app.exposures.types import InstrumentClassification, PositionExposureInput
from app.risk.engine import RiskEngine


def test_historical_var_expected_shortfall_beta_tracking_and_concentration() -> None:
    instrument = UUID(int=1)
    exposure = ExposureEngine().calculate(
        (PositionExposureInput(instrument, Decimal("1000")),),
        Decimal("0"),
        {instrument: InstrumentClassification(instrument, "Technology", "Equity", "US")},
    )
    returns = tuple(Decimal(item) for item in ("0.01", "-0.02", "0.03", "-0.05", "0.00"))
    benchmark = tuple(item / Decimal("2") for item in returns)

    result = RiskEngine().calculate(
        returns,
        benchmark,
        Decimal("1000"),
        exposure,
        confidence_level=Decimal("0.8"),
        annualization_periods=252,
    )

    assert result.value_at_risk_return == Decimal("0.02")
    assert result.expected_shortfall_return == Decimal("0.035")
    assert result.value_at_risk_amount == Decimal("20")
    assert result.expected_shortfall_amount == Decimal("35")
    assert result.beta == Decimal("2")
    assert result.tracking_error is not None
    assert result.largest_position_weight == Decimal("1")
