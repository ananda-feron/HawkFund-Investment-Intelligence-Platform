from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from app.models import TransactionType


@dataclass(frozen=True, slots=True)
class CreateTransaction:
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
    import_batch_id: UUID | None = None
    created_by_user_id: UUID | None = None
    reverses_transaction_id: UUID | None = None
    correction_command_id: UUID | None = None
    description: str | None = None
    source_metadata: dict[str, Any] | None = None

    def canonical_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: _json_value(value) for key, value in sorted(payload.items())}

    def economic_payload(self) -> dict[str, Any]:
        canonical = self.canonical_payload()
        excluded = {
            "recorded_at",
            "import_batch_id",
            "created_by_user_id",
            "correction_command_id",
            "description",
            "source_metadata",
        }
        return {key: value for key, value in canonical.items() if key not in excluded}


def _json_value(value: Any) -> Any:
    if isinstance(value, UUID | Decimal | date | datetime):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in sorted(value.items())}
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    return value
