from collections.abc import Generator
from datetime import UTC, datetime
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db import Base
from app.market_data.types import IdentifierScheme
from app.models import Account, Fund, ImportBatch, ImportBatchStatus, Instrument, SecurityIdentifier

FUND_ID = UUID("10000000-0000-4000-8000-000000000001")
ACCOUNT_ID = UUID("50000000-0000-4000-8000-000000000001")
INSTRUMENT_ID = UUID("40000000-0000-4000-8000-000000000001")
BATCH_ID = UUID("60000000-0000-4000-8000-000000000001")
NOW = datetime(2026, 1, 1, tzinfo=UTC)


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as database_session:
        database_session.add_all(
            [
                Fund(
                    id=FUND_ID,
                    slug="hawk-fund",
                    name="SUNY New Paltz Hawk Fund",
                    base_currency="USD",
                    timezone="America/New_York",
                    created_at=NOW,
                ),
                Instrument(
                    id=INSTRUMENT_ID,
                    symbol="AAPL",
                    name="Apple Inc.",
                    asset_type="equity",
                    exchange="NASDAQ",
                    currency="USD",
                    is_active=True,
                ),
                SecurityIdentifier(
                    id=UUID("41000000-0000-4000-8000-000000000001"),
                    instrument_id=INSTRUMENT_ID,
                    scheme=IdentifierScheme.TICKER,
                    value="AAPL",
                    provider="",
                    valid_from=None,
                    valid_to=None,
                    is_primary=True,
                ),
            ]
        )
        database_session.flush()
        database_session.add(
            Account(
                id=ACCOUNT_ID,
                fund_id=FUND_ID,
                code="PRIMARY",
                name="Primary Brokerage",
                currency="USD",
                created_at=NOW,
            )
        )
        database_session.flush()
        database_session.add(
            ImportBatch(
                id=BATCH_ID,
                fund_id=FUND_ID,
                source="hawkfund_csv",
                filename="phase1.csv",
                content_sha256="a" * 64,
                parser_version="1",
                status=ImportBatchStatus.RECEIVED,
                initiated_by_user_id=None,
                received_at=NOW,
                completed_at=None,
                total_count=0,
                posted_count=0,
                duplicate_count=0,
                rejected_count=0,
                conflict_count=0,
                failure_summary=None,
            )
        )
        database_session.commit()
        yield database_session
