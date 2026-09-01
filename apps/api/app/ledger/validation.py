from app.ledger.commands import CreateTransaction
from app.ledger.errors import TransactionValidationError
from app.ledger.types import TransactionType

TRADE_TYPES = {TransactionType.BUY, TransactionType.SELL}
CASH_AMOUNT_TYPES = {
    TransactionType.CASH_DEPOSIT,
    TransactionType.CASH_WITHDRAWAL,
    TransactionType.DIVIDEND,
    TransactionType.FEE,
    TransactionType.OPENING_CASH,
}


def validate_transaction(command: CreateTransaction) -> None:
    if command.currency != "USD":
        raise TransactionValidationError("Phase 1 supports USD transactions only")
    if command.effective_at.tzinfo is None or command.recorded_at.tzinfo is None:
        raise TransactionValidationError("effective_at and recorded_at must be timezone-aware")
    if not command.source.strip() or not command.external_id.strip():
        raise TransactionValidationError("source and external_id are required")
    if len(command.description or "") > 500:
        raise TransactionValidationError("description exceeds 500 characters")
    _positive_or_none("quantity", command.quantity)
    _positive_or_none("unit_price", command.unit_price)
    _positive_or_none("amount", command.amount)
    if command.fees < 0:
        raise TransactionValidationError("fees cannot be negative")

    kind = command.transaction_type
    if kind in TRADE_TYPES:
        _require(command.instrument_id, "instrument_id")
        _require(command.quantity, "quantity")
        _require(command.unit_price, "unit_price")
        _forbid(command.amount, "amount")
        _forbid(command.reverses_transaction_id, "reverses_transaction_id")
    elif kind in {TransactionType.CASH_DEPOSIT, TransactionType.CASH_WITHDRAWAL}:
        _require(command.amount, "amount")
        _forbid_trade_fields(command, permit_instrument=False)
    elif kind is TransactionType.DIVIDEND:
        _require(command.instrument_id, "instrument_id")
        _require(command.amount, "amount")
        _forbid(command.quantity, "quantity")
        _forbid(command.unit_price, "unit_price")
        _forbid(command.reverses_transaction_id, "reverses_transaction_id")
        _require_zero_fees(command)
    elif kind is TransactionType.FEE:
        _require(command.amount, "amount")
        _forbid(command.quantity, "quantity")
        _forbid(command.unit_price, "unit_price")
        _forbid(command.reverses_transaction_id, "reverses_transaction_id")
        _require_zero_fees(command)
    elif kind is TransactionType.OPENING_CASH:
        _require(command.amount, "amount")
        _forbid_trade_fields(command, permit_instrument=False)
    elif kind is TransactionType.OPENING_POSITION:
        _require(command.instrument_id, "instrument_id")
        _require(command.quantity, "quantity")
        _forbid(command.amount, "amount")
        _forbid(command.reverses_transaction_id, "reverses_transaction_id")
        _require_zero_fees(command)
    elif kind is TransactionType.REVERSAL:
        _require(command.reverses_transaction_id, "reverses_transaction_id")
        _forbid(command.instrument_id, "instrument_id")
        _forbid(command.quantity, "quantity")
        _forbid(command.unit_price, "unit_price")
        _forbid(command.amount, "amount")
        _require_zero_fees(command)
    else:
        raise TransactionValidationError(f"unsupported transaction type: {kind}")

    imported = command.source not in {"manual", "phase1_fixture"}
    if imported and command.import_batch_id is None:
        raise TransactionValidationError("import_batch_id is required for imported transactions")
    if command.source == "manual" and command.created_by_user_id is None:
        raise TransactionValidationError("created_by_user_id is required for manual transactions")


def _forbid_trade_fields(command: CreateTransaction, *, permit_instrument: bool) -> None:
    if not permit_instrument:
        _forbid(command.instrument_id, "instrument_id")
    _forbid(command.quantity, "quantity")
    _forbid(command.unit_price, "unit_price")
    _forbid(command.reverses_transaction_id, "reverses_transaction_id")
    _require_zero_fees(command)


def _positive_or_none(name: str, value: object | None) -> None:
    if value is not None and value <= 0:  # type: ignore[operator]
        raise TransactionValidationError(f"{name} must be greater than zero")


def _require(value: object | None, name: str) -> None:
    if value is None:
        raise TransactionValidationError(f"{name} is required")


def _forbid(value: object | None, name: str) -> None:
    if value is not None:
        raise TransactionValidationError(f"{name} is not allowed")


def _require_zero_fees(command: CreateTransaction) -> None:
    if command.fees != 0:
        raise TransactionValidationError("fees are allowed only on BUY and SELL")
