from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.market_data.service import MarketDataService
from app.market_data.types import PriceType
from app.models import Transaction
from app.portfolio.engine import PortfolioEngine
from app.portfolio.types import LedgerTransaction
from app.valuation.engine import RealizedPnlEngine, ValuationEngine
from app.valuation.types import ValuationResult


class HistoricalValuationService:
    def __init__(self, session: Session) -> None:
        self.session = session

    def value_at(
        self,
        fund_id: UUID,
        as_of: datetime,
        max_price_age: timedelta,
        account_id: UUID | None = None,
        provider: str | None = None,
        price_type: PriceType = PriceType.CLOSE,
    ) -> ValuationResult:
        transactions = tuple(self._transactions(fund_id, as_of, account_id))
        state = PortfolioEngine().reconstruct(fund_id, transactions, as_of, account_id)
        prices = MarketDataService(self.session)
        quotes = {
            instrument_id: prices.latest_quote(
                instrument_id, as_of, max_price_age, provider, price_type
            )
            for instrument_id in {item.instrument_id for item in state.positions}
        }
        realized = RealizedPnlEngine().calculate(fund_id, transactions, as_of, account_id)
        return ValuationEngine().value(state, quotes, realized)

    def _transactions(
        self, fund_id: UUID, as_of: datetime, account_id: UUID | None
    ) -> tuple[LedgerTransaction, ...]:
        query = select(Transaction).where(
            Transaction.fund_id == fund_id, Transaction.effective_at <= as_of
        )
        if account_id is not None:
            query = query.where(Transaction.account_id == account_id)
        rows = self.session.scalars(query).all()
        return tuple(
            LedgerTransaction(
                id=row.id,
                fund_id=row.fund_id,
                account_id=row.account_id,
                transaction_type=row.transaction_type,
                effective_at=self._aware(row.effective_at),
                recorded_at=self._aware(row.recorded_at),
                source=row.source,
                external_id=row.external_id,
                instrument_id=row.instrument_id,
                quantity=row.quantity,
                unit_price=row.unit_price,
                amount=row.amount,
                fees=row.fees,
                currency=row.currency,
                trade_date=row.trade_date,
                settlement_date=row.settlement_date,
                reverses_transaction_id=row.reverses_transaction_id,
            )
            for row in rows
        )

    @staticmethod
    def _aware(value: datetime) -> datetime:
        from datetime import UTC

        return value.replace(tzinfo=UTC) if value.tzinfo is None else value
