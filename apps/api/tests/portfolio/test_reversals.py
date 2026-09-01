from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.ledger.types import TransactionType
from app.portfolio import CostBasisStatus, PortfolioEngine
from app.portfolio.errors import InvalidReversalError, NegativeHoldingError
from tests.portfolio.factories import AAPL_ID, FUND_ID, at, transaction


def test_reversal_and_replacement_apply_at_their_own_effective_times() -> None:
    original = transaction(
        1,
        TransactionType.BUY,
        effective_at=at(10),
        instrument_id=AAPL_ID,
        quantity=Decimal("100"),
        unit_price=Decimal("100"),
    )
    reversal = transaction(
        2,
        TransactionType.REVERSAL,
        effective_at=at(20),
        reverses=original.id,
    )
    replacement = transaction(
        3,
        TransactionType.BUY,
        effective_at=at(20),
        recorded_at=at(20, 1),
        instrument_id=AAPL_ID,
        quantity=Decimal("150"),
        unit_price=Decimal("100"),
    )
    engine = PortfolioEngine()

    before = engine.reconstruct(FUND_ID, [replacement, reversal, original], at(15))
    after = engine.reconstruct(FUND_ID, [replacement, reversal, original], at(31))

    assert before.positions[0].quantity == Decimal("100")
    assert before.cash == Decimal("-10000")
    assert after.positions[0].quantity == Decimal("150")
    assert after.cash == Decimal("-15000")
    assert after.metadata.applied_transaction_ids == (
        original.id,
        reversal.id,
        replacement.id,
    )


def test_reversing_a_sale_restores_its_actual_basis_effect() -> None:
    buy = transaction(
        1,
        TransactionType.BUY,
        instrument_id=AAPL_ID,
        quantity=Decimal("100"),
        unit_price=Decimal("100"),
    )
    sell = transaction(
        2,
        TransactionType.SELL,
        instrument_id=AAPL_ID,
        quantity=Decimal("25"),
        unit_price=Decimal("120"),
        fees=Decimal("5"),
    )
    reversal = transaction(3, TransactionType.REVERSAL, reverses=sell.id)

    state = PortfolioEngine().reconstruct(FUND_ID, [reversal, buy, sell], at(31))

    assert state.positions[0].quantity == Decimal("100")
    assert state.positions[0].total_cost_basis == Decimal("10000")
    assert state.cash == Decimal("-10000")


def test_reversal_before_target_is_rejected() -> None:
    original = transaction(
        2,
        TransactionType.BUY,
        effective_at=at(20),
        instrument_id=AAPL_ID,
        quantity=Decimal("100"),
        unit_price=Decimal("10"),
    )
    reversal = transaction(
        1,
        TransactionType.REVERSAL,
        effective_at=at(10),
        reverses=original.id,
    )
    with pytest.raises(InvalidReversalError, match="not applied before"):
        PortfolioEngine().reconstruct(FUND_ID, [original, reversal], at(31))


def test_target_cannot_be_reversed_twice() -> None:
    original = transaction(
        1,
        TransactionType.BUY,
        instrument_id=AAPL_ID,
        quantity=Decimal("100"),
        unit_price=Decimal("10"),
    )
    first = transaction(2, TransactionType.REVERSAL, reverses=original.id)
    second = transaction(3, TransactionType.REVERSAL, reverses=original.id)
    with pytest.raises(InvalidReversalError, match="already reversed"):
        PortfolioEngine().reconstruct(FUND_ID, [original, first, second], at(31))


def test_reversing_buy_after_partial_sale_cannot_create_negative_holding() -> None:
    buy = transaction(
        1,
        TransactionType.BUY,
        instrument_id=AAPL_ID,
        quantity=Decimal("100"),
        unit_price=Decimal("10"),
    )
    sell = transaction(
        2,
        TransactionType.SELL,
        instrument_id=AAPL_ID,
        quantity=Decimal("25"),
        unit_price=Decimal("10"),
    )
    reversal = transaction(3, TransactionType.REVERSAL, reverses=buy.id)
    with pytest.raises(NegativeHoldingError):
        PortfolioEngine().reconstruct(FUND_ID, [buy, sell, reversal], at(31))


def test_multiple_corrections_preserve_only_latest_replacement() -> None:
    original = transaction(
        1,
        TransactionType.BUY,
        instrument_id=AAPL_ID,
        quantity=Decimal("100"),
        unit_price=Decimal("10"),
    )
    reverse_original = transaction(2, TransactionType.REVERSAL, reverses=original.id)
    replacement = transaction(
        3,
        TransactionType.BUY,
        instrument_id=AAPL_ID,
        quantity=Decimal("150"),
        unit_price=Decimal("10"),
    )
    reverse_replacement = transaction(4, TransactionType.REVERSAL, reverses=replacement.id)
    latest = transaction(
        5,
        TransactionType.BUY,
        instrument_id=AAPL_ID,
        quantity=Decimal("125"),
        unit_price=Decimal("10"),
    )

    state = PortfolioEngine().reconstruct(
        FUND_ID,
        [latest, reverse_replacement, replacement, reverse_original, original],
        datetime(2026, 1, 31, tzinfo=UTC),
    )
    assert state.positions[0].quantity == Decimal("125")
    assert state.cash == Decimal("-1250")


def test_reversing_unknown_opening_restores_known_later_purchase() -> None:
    opening = transaction(
        1,
        TransactionType.OPENING_POSITION,
        instrument_id=AAPL_ID,
        quantity=Decimal("100"),
    )
    purchase = transaction(
        2,
        TransactionType.BUY,
        instrument_id=AAPL_ID,
        quantity=Decimal("50"),
        unit_price=Decimal("10"),
    )
    reversal = transaction(3, TransactionType.REVERSAL, reverses=opening.id)

    state = PortfolioEngine().reconstruct(
        FUND_ID, [reversal, purchase, opening], datetime(2026, 1, 31, tzinfo=UTC)
    )

    assert state.positions[0].quantity == Decimal("50")
    assert state.positions[0].total_cost_basis == Decimal("500")
    assert state.positions[0].cost_basis_status is CostBasisStatus.KNOWN
