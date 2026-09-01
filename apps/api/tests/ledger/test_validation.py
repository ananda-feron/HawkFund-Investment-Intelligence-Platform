from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.ledger.commands import CreateTransaction
from app.ledger.errors import TransactionValidationError
from app.ledger.validation import validate_transaction
from app.models import TransactionType
from tests.conftest import ACCOUNT_ID, BATCH_ID, FUND_ID, INSTRUMENT_ID

NOW = datetime(2026, 1, 10, tzinfo=UTC)


def valid_buy() -> CreateTransaction:
    return CreateTransaction(
        fund_id=FUND_ID,
        account_id=ACCOUNT_ID,
        transaction_type=TransactionType.BUY,
        instrument_id=INSTRUMENT_ID,
        quantity=Decimal("100"),
        unit_price=Decimal("200"),
        fees=Decimal("5"),
        effective_at=NOW,
        recorded_at=NOW,
        source="hawkfund_csv",
        external_id="TX-001",
        import_batch_id=BATCH_ID,
    )


def test_valid_buy_matches_the_contract() -> None:
    validate_transaction(valid_buy())


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"unit_price": None}, "unit_price is required"),
        ({"quantity": Decimal("0")}, "quantity must be greater than zero"),
        ({"currency": "EUR"}, "supports USD"),
        ({"amount": Decimal("10")}, "amount is not allowed"),
        ({"import_batch_id": None}, "import_batch_id is required"),
    ],
)
def test_invalid_buy_is_rejected(change: dict[str, object], message: str) -> None:
    with pytest.raises(TransactionValidationError, match=message):
        validate_transaction(replace(valid_buy(), **change))


def test_unknown_opening_cost_basis_is_valid_and_remains_none() -> None:
    command = replace(
        valid_buy(),
        transaction_type=TransactionType.OPENING_POSITION,
        unit_price=None,
        fees=Decimal("0"),
        external_id="OPEN-AAPL",
    )
    validate_transaction(command)
    assert command.unit_price is None


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(TransactionValidationError, match="timezone-aware"):
        validate_transaction(replace(valid_buy(), effective_at=NOW.replace(tzinfo=None)))
