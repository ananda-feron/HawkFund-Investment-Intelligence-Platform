# ADR 0012: Explicit deterministic analytics and risk conventions

## Context

Performance and risk metrics can differ materially based on return treatment, sampling, alignment,
annualization, and tail definitions. Hidden library defaults would make results difficult to explain
or reproduce.

## Decision

Use pure Decimal-based engines with explicit inputs and policies:

- period return is `(ending value - external flow) / beginning value - 1`;
- cumulative return geometrically compounds period returns;
- volatility and tracking error use sample standard deviation and caller-supplied annualization
  periods, defaulting to 252;
- Sharpe subtracts the annual risk-free rate converted to a per-period rate;
- benchmark statistics use only exactly aligned timestamps;
- beta is sample covariance divided by benchmark sample variance;
- historical VaR uses the conservative nearest-rank loss quantile;
- expected shortfall averages losses at or beyond VaR;
- insufficient or zero-variance samples return unavailable rather than invented values.

## Alternatives

- Depend on NumPy/Pandas defaults: convenient, but conventions remain implicit and binary floating
  behavior complicates exact regression tests.
- Silently forward-fill benchmark observations: increases sample size while masking data gaps.
- Parametric normal VaR only: compact, but imposes a distribution assumption unsuitable as the
  sole initial method.

## Consequences

The calculations are transparent and regression-testable. The MVP is deliberately not optimized
for very large time series, and its historical VaR requires enough observations to be meaningful.
