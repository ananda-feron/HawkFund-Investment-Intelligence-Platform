from decimal import Decimal
from uuid import UUID

from app.exposures.engine import ExposureEngine
from app.exposures.types import InstrumentClassification, PositionExposureInput

AAPL = UUID(int=1)
MSFT = UUID(int=2)
BOND = UUID(int=3)


def test_exposures_weights_top_holdings_and_concentration() -> None:
    positions = (
        PositionExposureInput(AAPL, Decimal("300")),
        PositionExposureInput(MSFT, Decimal("100")),
        PositionExposureInput(BOND, Decimal("100")),
    )
    classifications = {
        AAPL: InstrumentClassification(AAPL, "Technology", "Equity", "United States"),
        MSFT: InstrumentClassification(MSFT, "Technology", "Equity", "United States"),
        BOND: InstrumentClassification(BOND, "Government", "Fixed Income", "United States"),
    }

    result = ExposureEngine().calculate(positions, Decimal("500"), classifications, top_n=2)

    assert result.portfolio_value == Decimal("1000")
    assert result.largest_position_weight == Decimal("0.3")
    assert result.herfindahl_index == Decimal("0.11")
    assert tuple(item.instrument_id for item in result.top_holdings) == (AAPL, MSFT)
    assert {item.category: item.weight for item in result.sector_exposure} == {
        "CASH": Decimal("0.5"),
        "Technology": Decimal("0.4"),
        "Government": Decimal("0.1"),
    }
    assert {item.category: item.weight for item in result.asset_allocation}["Equity"] == Decimal(
        "0.4"
    )


def test_missing_classification_is_explicit() -> None:
    result = ExposureEngine().calculate(
        (PositionExposureInput(AAPL, Decimal("100")),), Decimal("0"), {}
    )
    assert result.sector_exposure[0].category == "UNCLASSIFIED"
    assert result.warnings
