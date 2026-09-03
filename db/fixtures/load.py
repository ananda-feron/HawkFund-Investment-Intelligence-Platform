"""Load deterministic development bootstrap fixtures.

The loader is idempotent: rows use stable UUIDs and PostgreSQL upserts.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import create_engine, text

from app.config import get_settings

FUND_ID = UUID("10000000-0000-4000-8000-000000000001")
ACCOUNT_ID = UUID("50000000-0000-4000-8000-000000000001")
RISK_POLICY_ID = UUID("a0000000-0000-4000-8000-000000000001")
SECURITY_STRESS_ID = UUID("b1000000-0000-4000-8000-000000000001")
HISTORICAL_STRESS_ID = UUID("b1000000-0000-4000-8000-000000000002")
FACTOR_STRESS_ID = UUID("b1000000-0000-4000-8000-000000000003")
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

SECURITY_IDENTIFIERS = [
    (UUID(f"41000000-0000-4000-8000-00000000000{index}"), instrument[0], instrument[1])
    for index, instrument in enumerate(INSTRUMENTS, start=1)
]

CLASSIFICATIONS = [
    (UUID(f"42000000-0000-4000-8000-00000000000{index}"), instrument[0], sector, asset, geography)
    for index, (instrument, sector, asset, geography) in enumerate(
        zip(
            INSTRUMENTS,
            ("Technology", "Technology", "Technology", "Diversified"),
            ("Equity", "Equity", "Equity", "ETF"),
            ("United States",) * 4,
            strict=True,
        ),
        start=1,
    )
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
        connection.execute(
            text("""
                INSERT INTO risk_policies
                    (id, fund_id, name, version, effective_from, effective_to,
                     created_at, created_by_user_id)
                VALUES
                    (:id, :fund_id, 'Hawk Fund Base Policy', 1, :effective_from,
                     NULL, :created_at, NULL)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """),
            {
                "id": RISK_POLICY_ID,
                "fund_id": FUND_ID,
                "effective_from": CREATED_AT,
                "created_at": CREATED_AT,
            },
        )
        for rule_id, metric_key, threshold, explanation in (
            (
                UUID("a1000000-0000-4000-8000-000000000001"),
                "sector.Technology",
                Decimal("0.35"),
                "Technology exposure {observed}; policy limit {threshold}; breach {breach} {unit}",
            ),
            (
                UUID("a1000000-0000-4000-8000-000000000002"),
                "concentration.largest_position_weight",
                Decimal("0.10"),
                "Largest position {observed}; policy limit {threshold}; breach {breach} {unit}",
            ),
        ):
            connection.execute(
                text("""
                    INSERT INTO risk_policy_rules
                        (id, policy_id, metric_key, operator, threshold, unit,
                         explanation_template)
                    VALUES
                        (:id, :policy_id, :metric_key, 'MAX', :threshold, 'ratio',
                         :explanation)
                    ON CONFLICT (id) DO UPDATE SET threshold = EXCLUDED.threshold
                """),
                {
                    "id": rule_id,
                    "policy_id": RISK_POLICY_ID,
                    "metric_key": metric_key,
                    "threshold": threshold,
                    "explanation": explanation,
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
        for identifier_id, instrument_id, ticker in SECURITY_IDENTIFIERS:
            connection.execute(
                text("""
                    INSERT INTO security_identifiers
                        (id, instrument_id, scheme, value, provider,
                         valid_from, valid_to, is_primary)
                    VALUES (:id, :instrument_id, 'TICKER', :ticker, '', NULL, NULL, true)
                    ON CONFLICT (id) DO UPDATE SET value = EXCLUDED.value
                """),
                {"id": identifier_id, "instrument_id": instrument_id, "ticker": ticker},
            )
        for classification_id, instrument_id, sector, asset_class, geography in CLASSIFICATIONS:
            connection.execute(
                text("""
                    INSERT INTO instrument_classifications
                        (id, instrument_id, sector, asset_class, geography, effective_from,
                         effective_to, source, source_metadata, recorded_at)
                    VALUES
                        (:id, :instrument_id, :sector, :asset_class, :geography, :effective_from,
                         NULL, 'fixture', CAST('{}' AS jsonb), :recorded_at)
                    ON CONFLICT (id) DO UPDATE SET sector = EXCLUDED.sector
                """),
                {
                    "id": classification_id,
                    "instrument_id": instrument_id,
                    "sector": sector,
                    "asset_class": asset_class,
                    "geography": geography,
                    "effective_from": CREATED_AT,
                    "recorded_at": CREATED_AT,
                },
            )
        for scenario_id, name, kind, description, source_metadata in (
            (
                SECURITY_STRESS_ID,
                "Security Selloff",
                "HYPOTHETICAL",
                "AAPL -20%, MSFT -15%, and SPY -10%.",
                {},
            ),
            (
                HISTORICAL_STRESS_ID,
                "Historical Equity Crisis Proxy",
                "HISTORICAL",
                "Illustrative broad-market and technology shocks; not a calibrated replay.",
                {"methodology": "illustrative_proxy", "historical_label": "equity_crisis"},
            ),
            (
                FACTOR_STRESS_ID,
                "Rates and Growth Stress",
                "HYPOTHETICAL",
                "A 100 bp rate increase and a -15% Growth factor movement.",
                {},
            ),
        ):
            connection.execute(
                text("""
                    INSERT INTO scenario_definitions
                        (id, fund_id, name, version, kind, description, source_metadata,
                         created_at, created_by_user_id)
                    VALUES
                        (:id, :fund_id, :name, 1, :kind, :description,
                         CAST(:source_metadata AS jsonb), :created_at, NULL)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": scenario_id,
                    "fund_id": FUND_ID,
                    "name": name,
                    "kind": kind,
                    "description": description,
                    "source_metadata": json.dumps(source_metadata, sort_keys=True),
                    "created_at": CREATED_AT,
                },
            )
        shocks = (
            (
                "b2000000-0000-4000-8000-000000000001",
                SECURITY_STRESS_ID,
                "SECURITY",
                str(INSTRUMENTS[0][0]),
                "-0.20",
                "RELATIVE_RETURN",
                1,
            ),
            (
                "b2000000-0000-4000-8000-000000000002",
                SECURITY_STRESS_ID,
                "SECURITY",
                str(INSTRUMENTS[1][0]),
                "-0.15",
                "RELATIVE_RETURN",
                2,
            ),
            (
                "b2000000-0000-4000-8000-000000000003",
                SECURITY_STRESS_ID,
                "SECURITY",
                str(INSTRUMENTS[3][0]),
                "-0.10",
                "RELATIVE_RETURN",
                3,
            ),
            (
                "b2000000-0000-4000-8000-000000000004",
                HISTORICAL_STRESS_ID,
                "MARKET",
                "ALL",
                "-0.30",
                "RELATIVE_RETURN",
                1,
            ),
            (
                "b2000000-0000-4000-8000-000000000005",
                HISTORICAL_STRESS_ID,
                "SECTOR",
                "Technology",
                "-0.10",
                "RELATIVE_RETURN",
                2,
            ),
            (
                "b2000000-0000-4000-8000-000000000006",
                FACTOR_STRESS_ID,
                "RATE",
                "USD",
                "0.01",
                "YIELD_CHANGE",
                1,
            ),
            (
                "b2000000-0000-4000-8000-000000000007",
                FACTOR_STRESS_ID,
                "FACTOR",
                "Growth",
                "-0.15",
                "FACTOR_MOVE",
                2,
            ),
        )
        for shock_id, scenario_id, target_type, target, magnitude, unit, sequence in shocks:
            connection.execute(
                text("""
                    INSERT INTO scenario_shocks
                        (id, scenario_id, target_type, target, magnitude, unit, sequence)
                    VALUES
                        (:id, :scenario_id, :target_type, :target, :magnitude, :unit, :sequence)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": UUID(shock_id),
                    "scenario_id": scenario_id,
                    "target_type": target_type,
                    "target": target,
                    "magnitude": Decimal(magnitude),
                    "unit": unit,
                    "sequence": sequence,
                },
            )
        for index, (instrument_id, loading) in enumerate(
            zip(
                (item[0] for item in INSTRUMENTS),
                ("1.10", "1.00", "1.40", "0.85"),
                strict=True,
            ),
            start=1,
        ):
            connection.execute(
                text("""
                    INSERT INTO instrument_risk_sensitivities
                        (id, instrument_id, effective_from, effective_to, rate_duration,
                         factor_loadings, source, source_metadata, recorded_at)
                    VALUES
                        (:id, :instrument_id, :effective_from, NULL, NULL,
                         CAST(:factor_loadings AS jsonb), 'fixture', CAST('{}' AS jsonb),
                         :recorded_at)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": UUID(f"b3000000-0000-4000-8000-00000000000{index}"),
                    "instrument_id": instrument_id,
                    "effective_from": CREATED_AT,
                    "factor_loadings": json.dumps({"Growth": loading}, sort_keys=True),
                    "recorded_at": CREATED_AT,
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
    print(
        "Loaded deterministic fixtures: 1 fund, 1 account, 3 users, "
        "3 roles, 4 instruments, classifications, 1 risk policy, and 3 scenarios."
    )


if __name__ == "__main__":
    load()
