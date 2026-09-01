from decimal import Decimal

import pytest

from app.ledger.types import TransactionType
from app.portfolio import CostBasisStatus, PortfolioEngine
from app.portfolio.errors import NegativeHoldingError
from tests.portfolio.factories import (
    AAPL_ID,
    ACCOUNT_ID,
    FUND_ID,
    MSFT_ID,
    OTHER_ACCOUNT_ID,
    at,
    transaction,
)


def test_moving_weighted_average_and_sale_basis() -> None:
    state = PortfolioEngine().reconstruct(
        FUND_ID,
        [
            transaction(
                1,
                TransactionType.BUY,
                instrument_id=AAPL_ID,
                quantity=Decimal("100"),
                unit_price=Decimal("100"),
            ),
            transaction(
                2,
                TransactionType.BUY,
                instrument_id=AAPL_ID,
                quantity=Decimal("100"),
                unit_price=Decimal("120"),
            ),
            transaction(
                3,
                TransactionType.SELL,
                instrument_id=AAPL_ID,
                quantity=Decimal("50"),
                unit_price=Decimal("140"),
                fees=Decimal("5"),
            ),
        ],
        at(31),
    )

    position = state.positions[0]
    assert position.quantity == Decimal("150")
    assert position.total_cost_basis == Decimal("16500")
    assert position.average_cost == Decimal("110")
    assert position.cost_basis_status is CostBasisStatus.KNOWN
    assert state.cash == Decimal("-15005")


def test_buy_fees_are_capitalized() -> None:
    state = PortfolioEngine().reconstruct(
        FUND_ID,
        [
            transaction(
                1,
                TransactionType.BUY,
                instrument_id=AAPL_ID,
                quantity=Decimal("10"),
                unit_price=Decimal("20"),
                fees=Decimal("5"),
            )
        ],
        at(31),
    )

    assert state.positions[0].total_cost_basis == Decimal("205")
    assert state.positions[0].average_cost == Decimal("20.5")


def test_multiple_accounts_and_instruments_remain_separate() -> None:
    state = PortfolioEngine().reconstruct(
        FUND_ID,
        [
            transaction(
                1,
                TransactionType.BUY,
                instrument_id=AAPL_ID,
                quantity=Decimal("10"),
                unit_price=Decimal("10"),
            ),
            transaction(
                2,
                TransactionType.BUY,
                account_id=OTHER_ACCOUNT_ID,
                instrument_id=AAPL_ID,
                quantity=Decimal("20"),
                unit_price=Decimal("10"),
            ),
            transaction(
                3,
                TransactionType.BUY,
                instrument_id=MSFT_ID,
                quantity=Decimal("30"),
                unit_price=Decimal("10"),
            ),
        ],
        at(31),
    )

    quantities = {
        (position.account_id, position.instrument_id): position.quantity
        for position in state.positions
    }
    assert quantities == {
        (ACCOUNT_ID, AAPL_ID): Decimal("10"),
        (OTHER_ACCOUNT_ID, AAPL_ID): Decimal("20"),
        (ACCOUNT_ID, MSFT_ID): Decimal("30"),
    }
    assert state.cash == Decimal("-600")
    assert len(state.cash_by_account) == 2


def test_complete_liquidation_omits_zero_quantity_position() -> None:
    state = PortfolioEngine().reconstruct(
        FUND_ID,
        [
            transaction(
                1,
                TransactionType.BUY,
                instrument_id=AAPL_ID,
                quantity=Decimal("10"),
                unit_price=Decimal("10"),
            ),
            transaction(
                2,
                TransactionType.SELL,
                instrument_id=AAPL_ID,
                quantity=Decimal("10"),
                unit_price=Decimal("12"),
            ),
        ],
        at(31),
    )

    assert state.positions == ()
    assert state.cash == Decimal("20")


def test_oversell_fails_at_the_offending_transaction() -> None:
    sell = transaction(
        2,
        TransactionType.SELL,
        instrument_id=AAPL_ID,
        quantity=Decimal("11"),
        unit_price=Decimal("12"),
    )
    with pytest.raises(NegativeHoldingError) as error:
        PortfolioEngine().reconstruct(
            FUND_ID,
            [
                transaction(
                    1,
                    TransactionType.BUY,
                    instrument_id=AAPL_ID,
                    quantity=Decimal("10"),
                    unit_price=Decimal("10"),
                ),
                sell,
            ],
            at(31),
        )

    assert error.value.transaction_id == sell.id


def test_unknown_opening_basis_never_becomes_zero() -> None:
    state = PortfolioEngine().reconstruct(
        FUND_ID,
        [
            transaction(
                1,
                TransactionType.OPENING_POSITION,
                instrument_id=AAPL_ID,
                quantity=Decimal("100"),
            ),
            transaction(
                2,
                TransactionType.BUY,
                instrument_id=AAPL_ID,
                quantity=Decimal("10"),
                unit_price=Decimal("25"),
            ),
        ],
        at(31),
    )

    position = state.positions[0]
    assert position.quantity == Decimal("110")
    assert position.total_cost_basis is None
    assert position.average_cost is None
    assert position.cost_basis_status is CostBasisStatus.UNKNOWN
    assert any(item.startswith("UNKNOWN_COST_BASIS:") for item in state.warnings)


def test_partial_sale_preserves_unknown_basis() -> None:
    state = PortfolioEngine().reconstruct(
        FUND_ID,
        [
            transaction(
                1,
                TransactionType.OPENING_POSITION,
                instrument_id=AAPL_ID,
                quantity=Decimal("100"),
            ),
            transaction(
                2,
                TransactionType.SELL,
                instrument_id=AAPL_ID,
                quantity=Decimal("25"),
                unit_price=Decimal("30"),
            ),
        ],
        at(31),
    )

    assert state.positions[0].quantity == Decimal("75")
    assert state.positions[0].total_cost_basis is None
    assert state.positions[0].cost_basis_status is CostBasisStatus.UNKNOWN


def test_complete_liquidation_of_unknown_basis_omits_position() -> None:
    state = PortfolioEngine().reconstruct(
        FUND_ID,
        [
            transaction(
                1,
                TransactionType.OPENING_POSITION,
                instrument_id=AAPL_ID,
                quantity=Decimal("100"),
            ),
            transaction(
                2,
                TransactionType.SELL,
                instrument_id=AAPL_ID,
                quantity=Decimal("100"),
                unit_price=Decimal("30"),
            ),
        ],
        at(31),
    )

    assert state.positions == ()
