# Scenario and stress-testing semantics

## Scenario definition

A definition belongs to one fund and has an immutable identity, name, positive version, kind, source
metadata, and uniquely ordered shocks. Supported shocks are:

| Target | Unit | Position impact |
| --- | --- | --- |
| Security | Relative return | Applies to the matching instrument UUID |
| Market | Relative return | Applies to every security position |
| Sector | Relative return | Applies to positions with the effective sector classification |
| Rate | Yield change | `-duration × yield change` |
| Factor | Factor move | `loading × factor move` |

Magnitudes use decimal ratios: `-0.20` means -20%, and `0.01` means a 100-basis-point yield
increase. Applicable contributions are added. A projected price must remain positive.

## Historical scenarios

`HISTORICAL` means the shock bundle was designed to represent a historical episode. It does not
automatically replay historical constituents or claim exact calibration. Source metadata must state
the methodology. The deterministic fixtures label their crisis scenario as an illustrative proxy.

## Before and after

```text
accepted point-in-time valuation
        + versioned scenario and effective sensitivities
        -> projected valuation
        -> projected exposures
        -> projected sample risk
        -> policy evaluation
        -> immutable comparison evidence
```

Reported comparison includes portfolio and position P&L, sector/asset/geography weight changes,
volatility, beta, VaR, expected shortfall, tracking error, concentration changes, and baseline versus
projected policy outcomes. `UNAVAILABLE` remains distinct from pass.

Projected risk appends the scenario return to the supplied observed sample and appends the explicit
benchmark scenario return to the benchmark sample. It is a stressed-sample comparison, not a
forecast. Scenario execution never changes cash, holdings, transactions, accepted prices, or cost
basis.

## Provenance and limitations

Each stored run hashes every material input and stores position-level shock contribution evidence.
Missing duration, factor loading, or sector classification produces a warning and no guessed
contribution. Current limitations include linear sensitivities, no convexity or option repricing, no
factor interaction model, no trade/rebalancing scenarios, and no Monte Carlo simulation.
