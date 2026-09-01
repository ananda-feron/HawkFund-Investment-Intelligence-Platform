from decimal import Decimal

from app.ledger.types import TransactionType
from app.portfolio import PortfolioEngine
from tests.portfolio.factories import AAPL_ID, FUND_ID, at, transaction


def test_all_cash_effects_reconstruct_exactly() -> None:
    transactions = [
        transaction(1, TransactionType.OPENING_CASH, amount=Decimal("1000")),
        transaction(2, TransactionType.CASH_DEPOSIT, amount=Decimal("500")),
        transaction(
            3,
            TransactionType.BUY,
            instrument_id=AAPL_ID,
            quantity=Decimal("10"),
            unit_price=Decimal("20"),
            fees=Decimal("1"),
        ),
        transaction(
            4,
            TransactionType.SELL,
            instrument_id=AAPL_ID,
            quantity=Decimal("2"),
            unit_price=Decimal("30"),
            fees=Decimal("2"),
        ),
        transaction(
            5,
            TransactionType.DIVIDEND,
            instrument_id=AAPL_ID,
            amount=Decimal("10"),
        ),
        transaction(6, TransactionType.FEE, amount=Decimal("3")),
        transaction(7, TransactionType.CASH_WITHDRAWAL, amount=Decimal("100")),
    ]

    state = PortfolioEngine().reconstruct(FUND_ID, transactions, at(31))

    assert state.cash == Decimal("1264")
    assert state.cash_by_account[0].amount == Decimal("1264")
    assert state.warnings == ()


def test_negative_cash_is_preserved_as_warning() -> None:
    state = PortfolioEngine().reconstruct(
        FUND_ID,
        [transaction(1, TransactionType.FEE, amount=Decimal("25"))],
        at(31),
    )

    assert state.cash == Decimal("-25")
    assert state.warnings[0].startswith("NEGATIVE_CASH:")


def test_opening_position_does_not_affect_cash() -> None:
    state = PortfolioEngine().reconstruct(
        FUND_ID,
        [
            transaction(
                1,
                TransactionType.OPENING_POSITION,
                instrument_id=AAPL_ID,
                quantity=Decimal("100"),
                unit_price=Decimal("50"),
            )
        ],
        at(31),
    )

    assert state.cash == Decimal("0")
