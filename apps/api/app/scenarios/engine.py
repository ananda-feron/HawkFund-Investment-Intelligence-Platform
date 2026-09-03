import hashlib
import json
from collections.abc import Mapping
from dataclasses import replace
from decimal import Decimal
from uuid import UUID

from app.exposures.types import InstrumentClassification
from app.scenarios.errors import InvalidScenario
from app.scenarios.types import (
    InstrumentSensitivity,
    ScenarioDefinition,
    ScenarioPositionResult,
    ScenarioResult,
    ScenarioShock,
    ShockContribution,
    ShockTargetType,
    ShockUnit,
)
from app.valuation.types import PositionValuation, ValuationResult

ZERO = Decimal("0")
ONE = Decimal("1")


class ScenarioEngine:
    def apply(
        self,
        valuation: ValuationResult,
        definition: ScenarioDefinition,
        classifications: Mapping[UUID, InstrumentClassification],
        sensitivities: Mapping[UUID, InstrumentSensitivity] | None = None,
    ) -> ScenarioResult:
        if definition.fund_id != valuation.fund_id:
            raise InvalidScenario("scenario and valuation must belong to the same fund")
        self._validate(definition)
        sensitivities = sensitivities or {}
        warnings: list[str] = []
        position_results: list[ScenarioPositionResult] = []
        projected_positions: list[PositionValuation] = []
        for position in valuation.positions:
            contributions: list[ShockContribution] = []
            for shock in sorted(definition.shocks, key=lambda item: (item.sequence, str(item.id))):
                impact = self._impact(
                    position.instrument_id,
                    shock,
                    classifications.get(position.instrument_id),
                    sensitivities.get(position.instrument_id),
                    warnings,
                )
                if impact is not None:
                    contributions.append(
                        ShockContribution(shock.id, shock.target_type, shock.target, impact)
                    )
            return_impact = sum((item.return_impact for item in contributions), ZERO)
            if return_impact <= -ONE:
                raise InvalidScenario(
                    f"combined shocks imply a nonpositive price for {position.instrument_id}"
                )
            projected_price = position.price * (ONE + return_impact)
            projected_market_value = position.market_value * (ONE + return_impact)
            pnl = projected_market_value - position.market_value
            projected_unrealized = (
                None
                if position.cost_basis is None
                else projected_market_value - position.cost_basis
            )
            projected_positions.append(
                replace(
                    position,
                    price=projected_price,
                    market_value=projected_market_value,
                    unrealized_pnl=projected_unrealized,
                )
            )
            position_results.append(
                ScenarioPositionResult(
                    position.instrument_id,
                    position.price,
                    projected_price,
                    position.market_value,
                    projected_market_value,
                    return_impact,
                    pnl,
                    tuple(contributions),
                )
            )
        securities = sum((item.market_value for item in projected_positions), ZERO)
        pnl_impact = securities - valuation.securities_value
        unrealized_values = tuple(item.unrealized_pnl for item in projected_positions)
        projected_unrealized = (
            None
            if any(item is None for item in unrealized_values)
            else sum((item for item in unrealized_values if item is not None), ZERO)
        )
        projected = replace(
            valuation,
            securities_value=securities,
            portfolio_value=valuation.cash_value + securities,
            unrealized_pnl=projected_unrealized,
            positions=tuple(projected_positions),
            warnings=valuation.warnings + tuple(warnings),
        )
        portfolio_return = pnl_impact / valuation.portfolio_value
        return ScenarioResult(
            definition,
            valuation.as_of,
            valuation,
            projected,
            tuple(position_results),
            pnl_impact,
            portfolio_return,
            tuple(warnings),
            self._hash(valuation, definition, classifications, sensitivities),
            dict(classifications),
        )

    def _impact(
        self,
        instrument_id: UUID,
        shock: ScenarioShock,
        classification: InstrumentClassification | None,
        sensitivity: InstrumentSensitivity | None,
        warnings: list[str],
    ) -> Decimal | None:
        if shock.target_type is ShockTargetType.SECURITY:
            return shock.magnitude if shock.target == str(instrument_id) else None
        if shock.target_type is ShockTargetType.MARKET:
            return shock.magnitude
        if shock.target_type is ShockTargetType.SECTOR:
            if classification is None:
                warning = (
                    f"sector shock {shock.id} skipped for {instrument_id}: missing classification"
                )
                if warning not in warnings:
                    warnings.append(warning)
                return None
            return shock.magnitude if classification.sector == shock.target else None
        if shock.target_type is ShockTargetType.RATE:
            if sensitivity is None or sensitivity.rate_duration is None:
                warning = f"rate shock {shock.id} skipped for {instrument_id}: missing duration"
                if warning not in warnings:
                    warnings.append(warning)
                return None
            return -sensitivity.rate_duration * shock.magnitude
        if shock.target_type is ShockTargetType.FACTOR:
            loading = None if sensitivity is None else sensitivity.factor_loading(shock.target)
            if loading is None:
                warning = (
                    f"factor shock {shock.id} skipped for {instrument_id}: "
                    f"missing {shock.target} loading"
                )
                if warning not in warnings:
                    warnings.append(warning)
                return None
            return loading * shock.magnitude
        raise InvalidScenario(f"unsupported shock target type: {shock.target_type}")

    @staticmethod
    def _validate(definition: ScenarioDefinition) -> None:
        if definition.version <= 0 or not definition.name.strip():
            raise InvalidScenario("scenario name and positive version are required")
        sequences = [item.sequence for item in definition.shocks]
        if len(sequences) != len(set(sequences)) or any(item <= 0 for item in sequences):
            raise InvalidScenario("shock sequence values must be unique and positive")
        for shock in definition.shocks:
            if not shock.target.strip():
                raise InvalidScenario("shock target is required")
            if shock.target_type is ShockTargetType.SECURITY:
                try:
                    UUID(shock.target)
                except ValueError as error:
                    raise InvalidScenario(
                        "security shock target must be an instrument UUID"
                    ) from error
            if shock.target_type is ShockTargetType.MARKET and shock.target != "ALL":
                raise InvalidScenario("market shock target must be ALL")
            if shock.target_type is ShockTargetType.RATE and shock.target != "USD":
                raise InvalidScenario("Phase 4 rate shock target must be USD")
            expected = {
                ShockTargetType.SECURITY: ShockUnit.RELATIVE_RETURN,
                ShockTargetType.MARKET: ShockUnit.RELATIVE_RETURN,
                ShockTargetType.SECTOR: ShockUnit.RELATIVE_RETURN,
                ShockTargetType.RATE: ShockUnit.YIELD_CHANGE,
                ShockTargetType.FACTOR: ShockUnit.FACTOR_MOVE,
            }[shock.target_type]
            if shock.unit is not expected:
                raise InvalidScenario(f"{shock.target_type.value} shock requires {expected.value}")

    @staticmethod
    def _hash(
        valuation: ValuationResult,
        definition: ScenarioDefinition,
        classifications: Mapping[UUID, InstrumentClassification],
        sensitivities: Mapping[UUID, InstrumentSensitivity],
    ) -> str:
        payload = {
            "valuation_hash": valuation.reconstruction_input_hash,
            "as_of": valuation.as_of.isoformat(),
            "baseline": {
                "cash": str(valuation.cash_value),
                "portfolio_value": str(valuation.portfolio_value),
                "positions": [
                    {
                        "instrument_id": str(item.instrument_id),
                        "price": str(item.price),
                        "market_value": str(item.market_value),
                        "quote_observation_id": str(item.quote.observation_id),
                    }
                    for item in sorted(valuation.positions, key=lambda row: str(row.instrument_id))
                ],
            },
            "scenario": {
                "id": str(definition.id),
                "name": definition.name,
                "version": definition.version,
                "kind": definition.kind.value,
                "source_metadata": definition.source_metadata,
                "shocks": [
                    {
                        "id": str(item.id),
                        "target_type": item.target_type.value,
                        "target": item.target,
                        "magnitude": str(item.magnitude),
                        "unit": item.unit.value,
                        "sequence": item.sequence,
                    }
                    for item in sorted(definition.shocks, key=lambda row: row.sequence)
                ],
            },
            "classifications": {
                str(key): [value.sector, value.asset_class, value.geography]
                for key, value in sorted(classifications.items(), key=lambda item: str(item[0]))
            },
            "sensitivities": {
                str(key): {
                    "rate_duration": None
                    if value.rate_duration is None
                    else str(value.rate_duration),
                    "factor_loadings": [
                        [name, str(loading)] for name, loading in sorted(value.factor_loadings)
                    ],
                }
                for key, value in sorted(sensitivities.items(), key=lambda item: str(item[0]))
            },
            "calculation_version": "scenario-v1",
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
