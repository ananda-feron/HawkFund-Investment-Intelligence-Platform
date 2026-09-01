# Portfolio analytics and risk semantics

## Performance

- Valuation observations must be positive, uniquely timestamped, and timezone-aware.
- External contributions and withdrawals are removed from the period numerator before calculating
  return. The caller must provide those flows; a raw change in portfolio value is not assumed to be
  investment performance.
- Cumulative return is geometric, not a sum of returns.
- Drawdown follows the cash-flow-adjusted compounded wealth index divided by its prior peak minus
  one. Contributions therefore cannot manufacture a new performance peak. Maximum drawdown is the
  most negative observation.
- Basic attribution is beginning position weight multiplied by security return. It is additive
  contribution analysis, not a full Brinson sector allocation/selection model.
- Portfolio and benchmark returns align by exact timestamp. Missing dates are not forward-filled.

## Exposure

- Classifications are effective-dated and sourced. Phase 3 dimensions are sector, asset class, and
  geography.
- Every weight uses total portfolio NAV, including cash, as denominator.
- Cash appears as `CASH` in each classification dimension. Missing classifications appear as
  `UNCLASSIFIED` with a warning.
- Concentration reports largest position weight and the Herfindahl index (sum of squared security
  weights). Cash is not a security position and is excluded from that index.
- Phase 3 exposure is long-only; negative market values fail explicitly.

## Risk

- Volatility, beta, and tracking error follow ADR 0012.
- VaR and expected shortfall are positive loss magnitudes. Amount metrics multiply return risk by
  current portfolio value.
- Historical VaR is an estimate, not a guarantee. No distributional confidence claim is added
  beyond the selected empirical confidence level.

## Controls

Named metrics such as `sector.Technology`, `risk.beta`, and
`concentration.largest_position_weight` feed versioned rules. A maximum rule breaches only when the
observed value is strictly greater than its threshold. A 38.4% observation against 35% produces a
3.4 percentage-point breach represented as ratio `0.034`. Boundary equality passes. Missing metrics
are `UNAVAILABLE`, not pass.

Out of scope: factor models, marginal/component VaR, derivatives, short exposure, FX, stress tests,
scenario simulation, optimization, API/UI surfaces, and AI explanations.
