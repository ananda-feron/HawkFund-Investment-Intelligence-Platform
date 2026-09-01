from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.market_data.types import PriceQuote
from app.portfolio.types import CostBasisStatus


@dataclass(frozen=True, slots=True)
class PositionValuation:
    account_id: UUID
    instrument_id: UUID
    quantity: Decimal
    price: Decimal
    market_value: Decimal
    cost_basis: Decimal | None
    unrealized_pnl: Decimal | None
    cost_basis_status: CostBasisStatus
    quote: PriceQuote


@dataclass(frozen=True, slots=True)
class ValuationResult:
    fund_id: UUID
    as_of: datetime
    currency: str
    cash_value: Decimal
    securities_value: Decimal
    portfolio_value: Decimal
    unrealized_pnl: Decimal | None
    realized_pnl: Decimal | None
    positions: tuple[PositionValuation, ...]
    warnings: tuple[str, ...]
    reconstruction_input_hash: str


@dataclass(frozen=True, slots=True)
class RealizedPnlResult:
    amount: Decimal | None
    warnings: tuple[str, ...]
