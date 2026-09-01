import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from uuid import UUID

from app.ledger.types import TransactionType


class CostBasisStatus(str, Enum):
    KNOWN = "KNOWN"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class LedgerTransaction:
    id: UUID
    fund_id: UUID
    account_id: UUID
    transaction_type: TransactionType
    effective_at: datetime
    recorded_at: datetime
    source: str
    external_id: str
    instrument_id: UUID | None = None
    quantity: Decimal | None = None
    unit_price: Decimal | None = None
    amount: Decimal | None = None
    fees: Decimal = Decimal("0")
    currency: str = "USD"
    trade_date: date | None = None
    settlement_date: date | None = None
    reverses_transaction_id: UUID | None = None

    def canonical_dict(self) -> dict[str, str | None]:
        return {
            "id": str(self.id),
            "fund_id": str(self.fund_id),
            "account_id": str(self.account_id),
            "transaction_type": self.transaction_type.value,
            "effective_at": self.effective_at.isoformat(),
            "recorded_at": self.recorded_at.isoformat(),
            "source": self.source,
            "external_id": self.external_id,
            "instrument_id": _optional_str(self.instrument_id),
            "quantity": _optional_str(self.quantity),
            "unit_price": _optional_str(self.unit_price),
            "amount": _optional_str(self.amount),
            "fees": str(self.fees),
            "currency": self.currency,
            "trade_date": _optional_str(self.trade_date),
            "settlement_date": _optional_str(self.settlement_date),
            "reverses_transaction_id": _optional_str(self.reverses_transaction_id),
        }


@dataclass(frozen=True, slots=True)
class CashBalance:
    account_id: UUID
    currency: str
    amount: Decimal


@dataclass(frozen=True, slots=True)
class PositionState:
    account_id: UUID
    instrument_id: UUID
    quantity: Decimal
    total_cost_basis: Decimal | None
    average_cost: Decimal | None
    cost_basis_status: CostBasisStatus
    source_transaction_ids: tuple[UUID, ...]


@dataclass(frozen=True, slots=True)
class ReconstructionMetadata:
    as_of: datetime
    calculation_version: str
    canonical_input_hash: str
    applied_transaction_count: int
    applied_transaction_ids: tuple[UUID, ...]
    last_applied_transaction_id: UUID | None


@dataclass(frozen=True, slots=True)
class PortfolioState:
    fund_id: UUID
    account_id: UUID | None
    currency: str
    cash: Decimal
    cash_by_account: tuple[CashBalance, ...]
    positions: tuple[PositionState, ...]
    warnings: tuple[str, ...]
    metadata: ReconstructionMetadata

    def canonical_dict(self) -> dict[str, object]:
        return {
            "fund_id": str(self.fund_id),
            "account_id": _optional_str(self.account_id),
            "currency": self.currency,
            "cash": str(self.cash),
            "cash_by_account": [
                {
                    "account_id": str(balance.account_id),
                    "currency": balance.currency,
                    "amount": str(balance.amount),
                }
                for balance in self.cash_by_account
            ],
            "positions": [
                {
                    "account_id": str(position.account_id),
                    "instrument_id": str(position.instrument_id),
                    "quantity": str(position.quantity),
                    "total_cost_basis": _optional_str(position.total_cost_basis),
                    "average_cost": _optional_str(position.average_cost),
                    "cost_basis_status": position.cost_basis_status.value,
                    "source_transaction_ids": [
                        str(item) for item in position.source_transaction_ids
                    ],
                }
                for position in self.positions
            ],
            "warnings": list(self.warnings),
            "metadata": {
                "as_of": self.metadata.as_of.isoformat(),
                "calculation_version": self.metadata.calculation_version,
                "canonical_input_hash": self.metadata.canonical_input_hash,
                "applied_transaction_count": self.metadata.applied_transaction_count,
                "applied_transaction_ids": [
                    str(item) for item in self.metadata.applied_transaction_ids
                ],
                "last_applied_transaction_id": _optional_str(
                    self.metadata.last_applied_transaction_id
                ),
            },
        }

    def canonical_json(self) -> str:
        return json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))


def _optional_str(value: object | None) -> str | None:
    return None if value is None else str(value)
