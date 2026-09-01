import random
from dataclasses import replace
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest

from app.ledger.types import TransactionType
from app.portfolio import PortfolioEngine
from app.portfolio.errors import InvalidEngineInput
from tests.portfolio.factories import (
    AAPL_ID,
    FUND_ID,
    MSFT_ID,
    OTHER_FUND_ID,
    at,
    transaction,
)


def time_series() -> list:
    return [
        transaction(
            10,
            TransactionType.BUY,
            effective_at=at(10),
            instrument_id=AAPL_ID,
            quantity=Decimal("100"),
            unit_price=Decimal("10"),
        ),
        transaction(
            20,
            TransactionType.BUY,
            effective_at=at(20),
            instrument_id=MSFT_ID,
            quantity=Decimal("100"),
            unit_price=Decimal("20"),
        ),
        transaction(
            21,
            TransactionType.SELL,
            effective_at=datetime(2026, 2, 10, tzinfo=UTC),
            instrument_id=AAPL_ID,
            quantity=Decimal("25"),
            unit_price=Decimal("12"),
        ),
        transaction(
            22,
            TransactionType.BUY,
            effective_at=datetime(2026, 3, 1, tzinfo=UTC),
            instrument_id=AAPL_ID,
            quantity=Decimal("50"),
            unit_price=Decimal("11"),
        ),
    ]


def test_point_in_time_reconstruction_uses_effective_cutoff() -> None:
    engine = PortfolioEngine()
    january = engine.reconstruct(FUND_ID, time_series(), datetime(2026, 1, 31, 23, 59, tzinfo=UTC))
    february = engine.reconstruct(FUND_ID, time_series(), datetime(2026, 2, 28, 23, 59, tzinfo=UTC))

    january_quantities = {item.instrument_id: item.quantity for item in january.positions}
    february_quantities = {item.instrument_id: item.quantity for item in february.positions}
    assert january_quantities == {AAPL_ID: Decimal("100"), MSFT_ID: Decimal("100")}
    assert february_quantities == {AAPL_ID: Decimal("75"), MSFT_ID: Decimal("100")}
    assert january.metadata.applied_transaction_count == 2
    assert february.metadata.applied_transaction_count == 3


def test_input_order_does_not_change_canonical_result() -> None:
    transactions = time_series()
    baseline = PortfolioEngine().reconstruct(
        FUND_ID, transactions, datetime(2026, 3, 31, tzinfo=UTC)
    )
    for seed in range(10):
        shuffled = transactions.copy()
        random.Random(seed).shuffle(shuffled)
        candidate = PortfolioEngine().reconstruct(
            FUND_ID, shuffled, datetime(2026, 3, 31, tzinfo=UTC)
        )
        assert candidate == baseline
        assert candidate.canonical_json() == baseline.canonical_json()


def test_uuid_breaks_equal_timestamp_ties_deterministically() -> None:
    instant = at(10)
    first = transaction(
        1,
        TransactionType.BUY,
        effective_at=instant,
        recorded_at=instant,
        instrument_id=AAPL_ID,
        quantity=Decimal("10"),
        unit_price=Decimal("10"),
    )
    second = transaction(
        2,
        TransactionType.SELL,
        effective_at=instant,
        recorded_at=instant,
        instrument_id=AAPL_ID,
        quantity=Decimal("5"),
        unit_price=Decimal("10"),
    )

    state = PortfolioEngine().reconstruct(FUND_ID, [second, first], at(31))
    assert state.positions[0].quantity == Decimal("5")
    assert state.metadata.applied_transaction_ids == (first.id, second.id)


def test_account_scope_filters_before_reconstruction() -> None:
    transactions = time_series()
    scoped = PortfolioEngine().reconstruct(
        FUND_ID, transactions, at(31), account_id=transactions[0].account_id
    )
    assert scoped.account_id == transactions[0].account_id


def test_naive_as_of_and_mixed_funds_are_rejected() -> None:
    with pytest.raises(InvalidEngineInput, match="as_of"):
        PortfolioEngine().reconstruct(FUND_ID, [], datetime(2026, 1, 31))

    foreign = replace(time_series()[0], fund_id=OTHER_FUND_ID)
    with pytest.raises(InvalidEngineInput, match="requested fund"):
        PortfolioEngine().reconstruct(FUND_ID, [foreign], at(31))


def test_duplicate_transaction_ids_are_rejected() -> None:
    original = time_series()[0]
    duplicate = replace(original, external_id="DIFFERENT")
    assert duplicate.id == UUID(int=10)
    with pytest.raises(InvalidEngineInput, match="duplicate transaction id"):
        PortfolioEngine().reconstruct(FUND_ID, [original, duplicate], at(31))


def test_malformed_domain_record_is_rejected() -> None:
    malformed = transaction(
        1,
        TransactionType.BUY,
        instrument_id=AAPL_ID,
        quantity=Decimal("10"),
        unit_price=Decimal("10"),
        fees=Decimal("-1"),
    )
    with pytest.raises(InvalidEngineInput, match="fees cannot be negative"):
        PortfolioEngine().reconstruct(FUND_ID, [malformed], at(31))
