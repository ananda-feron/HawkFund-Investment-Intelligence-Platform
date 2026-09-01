import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from app.ledger.types import TransactionType
from app.portfolio.errors import (
    InvalidEngineInput,
    InvalidReversalError,
    NegativeCostBasisError,
    NegativeHoldingError,
)
from app.portfolio.types import (
    CashBalance,
    CostBasisStatus,
    LedgerTransaction,
    PortfolioState,
    PositionState,
    ReconstructionMetadata,
)

ENGINE_VERSION = "portfolio-reconstruction-v1"
ZERO = Decimal("0")


@dataclass(slots=True)
class _Position:
    quantity: Decimal = ZERO
    known_cost: Decimal = ZERO
    uncertainty_count: int = 0
    source_transaction_ids: list[UUID] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class _Effect:
    transaction_type: TransactionType
    account_id: UUID
    instrument_id: UUID | None
    cash_delta: Decimal
    quantity_delta: Decimal
    known_cost_delta: Decimal
    uncertainty_delta: int


class PortfolioEngine:
    def reconstruct(
        self,
        fund_id: UUID,
        transactions: Iterable[LedgerTransaction],
        as_of: datetime,
        account_id: UUID | None = None,
    ) -> PortfolioState:
        if as_of.tzinfo is None:
            raise InvalidEngineInput("as_of must be timezone-aware")
        supplied = tuple(transactions)
        self._validate_scope_and_timestamps(fund_id, supplied)
        included = [
            transaction
            for transaction in supplied
            if transaction.effective_at <= as_of
            and (account_id is None or transaction.account_id == account_id)
        ]
        ordered = tuple(
            sorted(
                included,
                key=lambda item: (item.effective_at, item.recorded_at, str(item.id)),
            )
        )

        cash: dict[UUID, Decimal] = {}
        positions: dict[tuple[UUID, UUID], _Position] = {}
        effects: dict[UUID, _Effect] = {}
        transaction_types: dict[UUID, TransactionType] = {}
        reversed_targets: set[UUID] = set()

        for transaction in ordered:
            cash.setdefault(transaction.account_id, ZERO)
            if transaction.transaction_type is TransactionType.REVERSAL:
                effect = self._reversal_effect(
                    transaction, effects, transaction_types, reversed_targets
                )
                reversed_targets.add(self._required_reversal_target(transaction))
            else:
                effect = self._apply_original(transaction, positions)
                effects[transaction.id] = effect
                transaction_types[transaction.id] = transaction.transaction_type

            cash[effect.account_id] += effect.cash_delta
            if effect.instrument_id is not None:
                self._apply_position_effect(
                    transaction.id,
                    effect,
                    positions,
                )

        output_positions = self._positions(positions)
        cash_by_account = tuple(
            CashBalance(account, "USD", amount)
            for account, amount in sorted(cash.items(), key=lambda item: str(item[0]))
        )
        warnings = self._warnings(cash_by_account, output_positions)
        applied_ids = tuple(item.id for item in ordered)
        metadata = ReconstructionMetadata(
            as_of=as_of,
            calculation_version=ENGINE_VERSION,
            canonical_input_hash=self._input_hash(fund_id, account_id, as_of, ordered),
            applied_transaction_count=len(ordered),
            applied_transaction_ids=applied_ids,
            last_applied_transaction_id=applied_ids[-1] if applied_ids else None,
        )
        return PortfolioState(
            fund_id=fund_id,
            account_id=account_id,
            currency="USD",
            cash=sum(cash.values(), ZERO),
            cash_by_account=cash_by_account,
            positions=output_positions,
            warnings=warnings,
            metadata=metadata,
        )

    def _validate_scope_and_timestamps(
        self, fund_id: UUID, transactions: tuple[LedgerTransaction, ...]
    ) -> None:
        seen_ids: set[UUID] = set()
        for transaction in transactions:
            if transaction.id in seen_ids:
                raise InvalidEngineInput(f"duplicate transaction id: {transaction.id}")
            seen_ids.add(transaction.id)
            if transaction.fund_id != fund_id:
                raise InvalidEngineInput("all transactions must belong to the requested fund")
            if transaction.effective_at.tzinfo is None or transaction.recorded_at.tzinfo is None:
                raise InvalidEngineInput("transaction timestamps must be timezone-aware")
            if transaction.currency != "USD":
                raise InvalidEngineInput("Phase 1 reconstruction supports USD only")
            if transaction.fees < ZERO:
                raise InvalidEngineInput(f"fees cannot be negative: {transaction.id}")
            self._validate_transaction_shape(transaction)

    def _validate_transaction_shape(self, transaction: LedgerTransaction) -> None:
        kind = transaction.transaction_type
        if kind in {TransactionType.BUY, TransactionType.SELL}:
            self._required_instrument(transaction)
            self._required_quantity(transaction)
            self._required_price(transaction)
            if transaction.amount is not None or transaction.reverses_transaction_id is not None:
                raise InvalidEngineInput(f"invalid trade fields: {transaction.id}")
            return
        if kind in {TransactionType.CASH_DEPOSIT, TransactionType.CASH_WITHDRAWAL}:
            self._required_amount(transaction)
            self._require_no_position_fields(transaction)
            return
        if kind is TransactionType.DIVIDEND:
            self._required_instrument(transaction)
            self._required_amount(transaction)
            if (
                transaction.quantity is not None
                or transaction.unit_price is not None
                or transaction.fees != ZERO
                or transaction.reverses_transaction_id is not None
            ):
                raise InvalidEngineInput(f"invalid dividend fields: {transaction.id}")
            return
        if kind is TransactionType.FEE:
            self._required_amount(transaction)
            if (
                transaction.quantity is not None
                or transaction.unit_price is not None
                or transaction.fees != ZERO
                or transaction.reverses_transaction_id is not None
            ):
                raise InvalidEngineInput(f"invalid fee fields: {transaction.id}")
            return
        if kind is TransactionType.OPENING_CASH:
            self._required_amount(transaction)
            self._require_no_position_fields(transaction)
            return
        if kind is TransactionType.OPENING_POSITION:
            self._required_instrument(transaction)
            self._required_quantity(transaction)
            if (
                transaction.amount is not None
                or transaction.fees != ZERO
                or transaction.reverses_transaction_id is not None
            ):
                raise InvalidEngineInput(f"invalid opening-position fields: {transaction.id}")
            return
        if kind is TransactionType.REVERSAL:
            self._required_reversal_target(transaction)
            if (
                transaction.instrument_id is not None
                or transaction.quantity is not None
                or transaction.unit_price is not None
                or transaction.amount is not None
                or transaction.fees != ZERO
            ):
                raise InvalidEngineInput(f"invalid reversal fields: {transaction.id}")
            return
        raise InvalidEngineInput(f"unsupported transaction type: {kind}")

    def _require_no_position_fields(self, transaction: LedgerTransaction) -> None:
        if (
            transaction.instrument_id is not None
            or transaction.quantity is not None
            or transaction.unit_price is not None
            or transaction.reverses_transaction_id is not None
            or transaction.fees != ZERO
        ):
            raise InvalidEngineInput(f"invalid cash-only fields: {transaction.id}")

    def _apply_original(
        self,
        transaction: LedgerTransaction,
        positions: dict[tuple[UUID, UUID], _Position],
    ) -> _Effect:
        kind = transaction.transaction_type
        if kind is TransactionType.OPENING_CASH:
            return self._cash_effect(transaction, self._required_amount(transaction))
        if kind is TransactionType.CASH_DEPOSIT:
            return self._cash_effect(transaction, self._required_amount(transaction))
        if kind is TransactionType.CASH_WITHDRAWAL:
            return self._cash_effect(transaction, -self._required_amount(transaction))
        if kind is TransactionType.DIVIDEND:
            self._required_instrument(transaction)
            return self._cash_effect(transaction, self._required_amount(transaction))
        if kind is TransactionType.FEE:
            return self._cash_effect(transaction, -self._required_amount(transaction))
        if kind is TransactionType.BUY:
            instrument_id = self._required_instrument(transaction)
            quantity = self._required_quantity(transaction)
            price = self._required_price(transaction)
            purchase_cost = quantity * price + transaction.fees
            return _Effect(
                kind,
                transaction.account_id,
                instrument_id,
                -purchase_cost,
                quantity,
                purchase_cost,
                0,
            )
        if kind is TransactionType.SELL:
            instrument_id = self._required_instrument(transaction)
            quantity = self._required_quantity(transaction)
            price = self._required_price(transaction)
            position = positions.get((transaction.account_id, instrument_id), _Position())
            if quantity > position.quantity:
                raise NegativeHoldingError(transaction.id, "sell exceeds available quantity")
            sale_cash = quantity * price - transaction.fees
            if position.uncertainty_count == 0:
                if position.quantity == ZERO:
                    raise NegativeHoldingError(transaction.id, "sell has no available quantity")
                basis_removed = position.known_cost * quantity / position.quantity
                uncertainty_delta = 0
            else:
                basis_removed = position.known_cost if quantity == position.quantity else ZERO
                uncertainty_delta = 1
            return _Effect(
                kind,
                transaction.account_id,
                instrument_id,
                sale_cash,
                -quantity,
                -basis_removed,
                uncertainty_delta,
            )
        if kind is TransactionType.OPENING_POSITION:
            instrument_id = self._required_instrument(transaction)
            quantity = self._required_quantity(transaction)
            if transaction.unit_price is None:
                known_cost = ZERO
                uncertainty_delta = 1
            else:
                known_cost = quantity * transaction.unit_price
                uncertainty_delta = 0
            return _Effect(
                kind,
                transaction.account_id,
                instrument_id,
                ZERO,
                quantity,
                known_cost,
                uncertainty_delta,
            )
        raise InvalidEngineInput(f"unsupported transaction type: {kind}")

    def _reversal_effect(
        self,
        transaction: LedgerTransaction,
        effects: dict[UUID, _Effect],
        transaction_types: dict[UUID, TransactionType],
        reversed_targets: set[UUID],
    ) -> _Effect:
        target_id = self._required_reversal_target(transaction)
        if target_id not in effects:
            raise InvalidReversalError(
                f"reversal target was not applied before reversal: {target_id}"
            )
        if transaction_types.get(target_id) is TransactionType.REVERSAL:
            raise InvalidReversalError("a reversal cannot target another reversal")
        if target_id in reversed_targets:
            raise InvalidReversalError(f"transaction already reversed: {target_id}")
        target = effects[target_id]
        if target.account_id != transaction.account_id:
            raise InvalidReversalError("reversal must use the target account")
        return _Effect(
            TransactionType.REVERSAL,
            target.account_id,
            target.instrument_id,
            -target.cash_delta,
            -target.quantity_delta,
            -target.known_cost_delta,
            -target.uncertainty_delta,
        )

    def _apply_position_effect(
        self,
        transaction_id: UUID,
        effect: _Effect,
        positions: dict[tuple[UUID, UUID], _Position],
    ) -> None:
        assert effect.instrument_id is not None
        key = (effect.account_id, effect.instrument_id)
        position = positions.setdefault(key, _Position())
        new_quantity = position.quantity + effect.quantity_delta
        if new_quantity < ZERO:
            raise NegativeHoldingError(transaction_id)
        new_cost = position.known_cost + effect.known_cost_delta
        if new_cost < ZERO:
            raise NegativeCostBasisError(
                f"known cost basis became negative at transaction {transaction_id}"
            )
        new_uncertainty = position.uncertainty_count + effect.uncertainty_delta
        if new_uncertainty < 0:
            raise InvalidReversalError("reversal removed cost-basis uncertainty that was absent")
        position.quantity = new_quantity
        position.known_cost = new_cost
        position.uncertainty_count = new_uncertainty
        position.source_transaction_ids.append(transaction_id)

    def _positions(
        self, positions: dict[tuple[UUID, UUID], _Position]
    ) -> tuple[PositionState, ...]:
        result: list[PositionState] = []
        for (account_id, instrument_id), position in sorted(
            positions.items(), key=lambda item: (str(item[0][0]), str(item[0][1]))
        ):
            if position.quantity == ZERO:
                continue
            if position.uncertainty_count:
                total_cost = None
                average_cost = None
                status = CostBasisStatus.UNKNOWN
            else:
                total_cost = position.known_cost
                average_cost = position.known_cost / position.quantity
                status = CostBasisStatus.KNOWN
            result.append(
                PositionState(
                    account_id=account_id,
                    instrument_id=instrument_id,
                    quantity=position.quantity,
                    total_cost_basis=total_cost,
                    average_cost=average_cost,
                    cost_basis_status=status,
                    source_transaction_ids=tuple(position.source_transaction_ids),
                )
            )
        return tuple(result)

    def _warnings(
        self,
        cash: tuple[CashBalance, ...],
        positions: tuple[PositionState, ...],
    ) -> tuple[str, ...]:
        warnings = [f"NEGATIVE_CASH:{item.account_id}" for item in cash if item.amount < ZERO]
        warnings.extend(
            f"UNKNOWN_COST_BASIS:{item.account_id}:{item.instrument_id}"
            for item in positions
            if item.cost_basis_status is CostBasisStatus.UNKNOWN
        )
        return tuple(sorted(warnings))

    def _input_hash(
        self,
        fund_id: UUID,
        account_id: UUID | None,
        as_of: datetime,
        ordered: tuple[LedgerTransaction, ...],
    ) -> str:
        payload = {
            "fund_id": str(fund_id),
            "account_id": None if account_id is None else str(account_id),
            "as_of": as_of.isoformat(),
            "calculation_version": ENGINE_VERSION,
            "transactions": [item.canonical_dict() for item in ordered],
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode()).hexdigest()

    def _cash_effect(self, transaction: LedgerTransaction, amount: Decimal) -> _Effect:
        return _Effect(
            transaction.transaction_type,
            transaction.account_id,
            None,
            amount,
            ZERO,
            ZERO,
            0,
        )

    def _required_amount(self, transaction: LedgerTransaction) -> Decimal:
        if transaction.amount is None or transaction.amount <= ZERO:
            raise InvalidEngineInput(f"positive amount required: {transaction.id}")
        return transaction.amount

    def _required_quantity(self, transaction: LedgerTransaction) -> Decimal:
        if transaction.quantity is None or transaction.quantity <= ZERO:
            raise InvalidEngineInput(f"positive quantity required: {transaction.id}")
        return transaction.quantity

    def _required_price(self, transaction: LedgerTransaction) -> Decimal:
        if transaction.unit_price is None or transaction.unit_price <= ZERO:
            raise InvalidEngineInput(f"positive unit price required: {transaction.id}")
        return transaction.unit_price

    def _required_instrument(self, transaction: LedgerTransaction) -> UUID:
        if transaction.instrument_id is None:
            raise InvalidEngineInput(f"instrument required: {transaction.id}")
        return transaction.instrument_id

    def _required_reversal_target(self, transaction: LedgerTransaction) -> UUID:
        if transaction.reverses_transaction_id is None:
            raise InvalidReversalError(f"reversal target required: {transaction.id}")
        return transaction.reverses_transaction_id
