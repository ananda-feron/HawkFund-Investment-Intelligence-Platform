from collections.abc import Iterable, Mapping
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.ledger.types import TransactionType
from app.market_data.types import FreshnessStatus, PriceQuote
from app.portfolio.engine import PortfolioEngine
from app.portfolio.types import CostBasisStatus, LedgerTransaction, PortfolioState
from app.valuation.errors import MissingValuationPrice
from app.valuation.types import PositionValuation, RealizedPnlResult, ValuationResult

ZERO = Decimal("0")


class ValuationEngine:
    def value(
        self,
        state: PortfolioState,
        quotes: Mapping[UUID, PriceQuote],
        realized_pnl: RealizedPnlResult,
    ) -> ValuationResult:
        positions: list[PositionValuation] = []
        warnings = list(state.warnings) + list(realized_pnl.warnings)
        for position in state.positions:
            quote = quotes.get(position.instrument_id)
            if quote is None:
                raise MissingValuationPrice(
                    f"missing price for instrument {position.instrument_id}"
                )
            if quote.currency != state.currency:
                raise MissingValuationPrice(
                    f"currency mismatch for instrument {position.instrument_id}"
                )
            market_value = position.quantity * quote.price
            unrealized = (
                None
                if position.total_cost_basis is None
                else market_value - position.total_cost_basis
            )
            if quote.freshness is FreshnessStatus.STALE:
                warnings.append(
                    f"stale price for {position.instrument_id}: "
                    f"observed {quote.observed_at.isoformat()}"
                )
            positions.append(
                PositionValuation(
                    position.account_id,
                    position.instrument_id,
                    position.quantity,
                    quote.price,
                    market_value,
                    position.total_cost_basis,
                    unrealized,
                    position.cost_basis_status,
                    quote,
                )
            )
        securities = sum((item.market_value for item in positions), ZERO)
        unrealized_values = [item.unrealized_pnl for item in positions]
        total_unrealized = (
            None
            if any(item is None for item in unrealized_values)
            else sum((item for item in unrealized_values if item is not None), ZERO)
        )
        return ValuationResult(
            state.fund_id,
            state.metadata.as_of,
            state.currency,
            state.cash,
            securities,
            state.cash + securities,
            total_unrealized,
            realized_pnl.amount,
            tuple(positions),
            tuple(warnings),
            state.metadata.canonical_input_hash,
        )


class RealizedPnlEngine:
    """Moving-average trade P&L using the portfolio engine's cost-basis semantics."""

    def calculate(
        self,
        fund_id: UUID,
        transactions: Iterable[LedgerTransaction],
        as_of: datetime,
        account_id: UUID | None = None,
    ) -> RealizedPnlResult:
        eligible = sorted(
            (
                item
                for item in transactions
                if item.effective_at <= as_of
                and (account_id is None or item.account_id == account_id)
            ),
            key=lambda item: (item.effective_at, item.recorded_at, str(item.id)),
        )
        prefix: list[LedgerTransaction] = []
        effects: dict[UUID, Decimal | None] = {}
        total = ZERO
        active_unknown_sales: set[UUID] = set()
        warnings: list[str] = []
        reconstruction = PortfolioEngine()
        for transaction in eligible:
            if transaction.transaction_type is TransactionType.SELL:
                prior = reconstruction.reconstruct(
                    fund_id, prefix, transaction.effective_at, account_id
                )
                position = next(
                    (
                        item
                        for item in prior.positions
                        if item.account_id == transaction.account_id
                        and item.instrument_id == transaction.instrument_id
                    ),
                    None,
                )
                if (
                    position is None
                    or transaction.quantity is None
                    or transaction.unit_price is None
                ):
                    effect = None
                elif (
                    position.cost_basis_status is CostBasisStatus.UNKNOWN
                    or position.average_cost is None
                ):
                    effect = None
                    warnings.append(
                        f"realized P&L unavailable for sell {transaction.id}: unknown cost basis"
                    )
                else:
                    effect = (
                        transaction.quantity * transaction.unit_price
                        - transaction.fees
                        - transaction.quantity * position.average_cost
                    )
                effects[transaction.id] = effect
                if effect is None:
                    active_unknown_sales.add(transaction.id)
                else:
                    total += effect
            elif transaction.transaction_type is TransactionType.REVERSAL:
                target = transaction.reverses_transaction_id
                if target in effects:
                    effect = effects[target]
                    if effect is None:
                        active_unknown_sales.discard(target)
                    else:
                        total -= effect
            prefix.append(transaction)
        return RealizedPnlResult(None if active_unknown_sales else total, tuple(warnings))
