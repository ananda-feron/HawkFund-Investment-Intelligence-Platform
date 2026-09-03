# ADR 0015: Transparent additive shock model

## Context

Security, market, sector, rate, and factor stresses need a common calculation model. Sophisticated
factor covariance and pricing models are not yet part of HawkFundOS, so hidden approximations would
create false precision.

## Decision

Represent each scenario as an ordered, versioned bundle of typed shocks. Applicable return impacts
are additive at the position level:

- security, market, and sector shocks are direct relative returns;
- rate impact is `-rate duration × yield change`;
- factor impact is `factor loading × factor move`.

Every position retains the contribution from each applicable shock. A combined impact at or below
-100% is rejected rather than producing a nonpositive price. Missing classifications or
sensitivities skip only the unsupported contribution and produce an explicit warning. Historical
scenarios are calibrated shock bundles with source metadata; the label alone does not imply an exact
historical replay.

For before/after risk, the one-period scenario portfolio return is appended to the observed return
sample. The caller supplies the corresponding benchmark scenario return. This convention is
explicit because it changes sample-based volatility, beta, VaR, expected shortfall, and tracking
error.

## Alternatives

- Multiply all shocks: avoids additive overlap but is less natural for linear factor contributions.
- Infer missing factor loadings: produces complete-looking output from unsupported assumptions.
- Claim historical replay from a name and date: misleading without calibrated historical factor and
  security data.

## Consequences

Results are explainable and deterministic but remain first-order approximations. Nonlinear pricing,
convexity, options, cross-factor interactions, and calibrated stress models are future work.
