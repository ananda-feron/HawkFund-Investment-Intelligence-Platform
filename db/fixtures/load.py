"""Load deterministic development bootstrap fixtures.

The loader is idempotent: rows use stable UUIDs and PostgreSQL upserts.
"""

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import create_engine, text

from app.config import get_settings

FUND_ID = UUID("10000000-0000-4000-8000-000000000001")
ACCOUNT_ID = UUID("50000000-0000-4000-8000-000000000001")
CREATED_AT = datetime(2026, 1, 1, tzinfo=UTC)

ROLES = [
    (UUID("20000000-0000-4000-8000-000000000001"), "analyst", "Student Analyst"),
    (UUID("20000000-0000-4000-8000-000000000002"), "manager", "Portfolio Manager"),
    (UUID("20000000-0000-4000-8000-000000000003"), "advisor", "Faculty Advisor"),
]
USERS = [
    (UUID("30000000-0000-4000-8000-000000000001"), "analyst@hawkfund.local", "Demo Analyst"),
    (UUID("30000000-0000-4000-8000-000000000002"), "manager@hawkfund.local", "Demo Manager"),
    (UUID("30000000-0000-4000-8000-000000000003"), "advisor@hawkfund.local", "Demo Advisor"),
]
INSTRUMENTS = [
    (UUID("40000000-0000-4000-8000-000000000001"), "AAPL", "Apple Inc.", "equity", "NASDAQ", "USD"),
    (
        UUID("40000000-0000-4000-8000-000000000002"),
        "MSFT",
        "Microsoft Corporation",
        "equity",
        "NASDAQ",
        "USD",
    ),
    (
        UUID("40000000-0000-4000-8000-000000000003"),
        "NVDA",
        "NVIDIA Corporation",
        "equity",
        "NASDAQ",
        "USD",
    ),
    (
        UUID("40000000-0000-4000-8000-000000000004"),
        "SPY",
        "SPDR S&P 500 ETF Trust",
        "etf",
        "NYSE_ARCA",
        "USD",
    ),
]


def load() -> None:
    engine = create_engine(get_settings().database_url)
    with engine.begin() as connection:
        connection.execute(
            text("""
                INSERT INTO funds (id, slug, name, base_currency, timezone, created_at)
                VALUES (:id, :slug, :name, :currency, :timezone, :created_at)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """),
            {
                "id": FUND_ID,
                "slug": "hawk-fund",
                "name": "SUNY New Paltz Hawk Fund",
                "currency": "USD",
                "timezone": "America/New_York",
                "created_at": CREATED_AT,
            },
        )
        for role_id, code, name in ROLES:
            connection.execute(
                text("""
                    INSERT INTO roles (id, code, name)
                    VALUES (:id, :code, :name)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                """),
                {"id": role_id, "code": code, "name": name},
            )
        for index, (user_id, email, name) in enumerate(USERS):
            connection.execute(
                text("""
                    INSERT INTO users (id, email, display_name, is_active, created_at)
                    VALUES (:id, :email, :name, true, :created_at)
                    ON CONFLICT (id) DO UPDATE SET display_name = EXCLUDED.display_name
                """),
                {"id": user_id, "email": email, "name": name, "created_at": CREATED_AT},
            )
            connection.execute(
                text("""
                    INSERT INTO user_roles (user_id, role_id, fund_id)
                    VALUES (:user_id, :role_id, :fund_id)
                    ON CONFLICT DO NOTHING
                """),
                {"user_id": user_id, "role_id": ROLES[index][0], "fund_id": FUND_ID},
            )
        for instrument_id, symbol, name, asset_type, exchange, currency in INSTRUMENTS:
            connection.execute(
                text("""
                    INSERT INTO instruments
                        (id, symbol, name, asset_type, exchange, currency, is_active)
                    VALUES
                        (:id, :symbol, :name, :asset_type, :exchange, :currency, true)
                    ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
                """),
                {
                    "id": instrument_id,
                    "symbol": symbol,
                    "name": name,
                    "asset_type": asset_type,
                    "exchange": exchange,
                    "currency": currency,
                },
            )
        connection.execute(
            text("""
                INSERT INTO accounts (id, fund_id, code, name, currency, created_at)
                VALUES (:id, :fund_id, :code, :name, :currency, :created_at)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """),
            {
                "id": ACCOUNT_ID,
                "fund_id": FUND_ID,
                "code": "PRIMARY",
                "name": "Primary Brokerage",
                "currency": "USD",
                "created_at": CREATED_AT,
            },
        )
    print("Loaded deterministic fixtures: 1 fund, 1 account, 3 users, 3 roles, 4 instruments.")


if __name__ == "__main__":
    load()
