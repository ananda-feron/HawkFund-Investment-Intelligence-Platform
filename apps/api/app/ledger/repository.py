from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Transaction, TransactionStatus, TransactionType


class TransactionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def by_source_identity(
        self, fund_id: UUID, source: str, external_id: str
    ) -> Transaction | None:
        return self.session.scalar(
            select(Transaction).where(
                Transaction.fund_id == fund_id,
                Transaction.source == source,
                Transaction.external_id == external_id,
            )
        )

    def by_id(self, transaction_id: UUID) -> Transaction | None:
        return self.session.get(Transaction, transaction_id)

    def has_posted_cash_activity(self, account_id: UUID) -> bool:
        cash_types = {
            TransactionType.BUY,
            TransactionType.SELL,
            TransactionType.CASH_DEPOSIT,
            TransactionType.CASH_WITHDRAWAL,
            TransactionType.DIVIDEND,
            TransactionType.FEE,
            TransactionType.OPENING_CASH,
        }
        statement = select(Transaction.id).where(
            Transaction.account_id == account_id,
            Transaction.status == TransactionStatus.POSTED,
            Transaction.transaction_type.in_(cash_types),
        )
        return self.session.scalar(statement.limit(1)) is not None

    def has_posted_quantity_activity(self, account_id: UUID, instrument_id: UUID) -> bool:
        quantity_types = {
            TransactionType.BUY,
            TransactionType.SELL,
            TransactionType.OPENING_POSITION,
        }
        statement = select(Transaction.id).where(
            Transaction.account_id == account_id,
            Transaction.instrument_id == instrument_id,
            Transaction.status == TransactionStatus.POSTED,
            Transaction.transaction_type.in_(quantity_types),
        )
        return self.session.scalar(statement.limit(1)) is not None

    def reversal_for(self, transaction_id: UUID) -> Transaction | None:
        return self.session.scalar(
            select(Transaction).where(
                Transaction.transaction_type == TransactionType.REVERSAL,
                Transaction.reverses_transaction_id == transaction_id,
            )
        )

    def add(self, transaction: Transaction) -> Transaction:
        self.session.add(transaction)
        self.session.flush()
        return transaction
