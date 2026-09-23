# Sol V1 Panel Support Audit

Source novelty freeze: `b068780497ea59713e268fb272bf44939f83f23e`

This stage is outcome-blind. It does not settle any target, fit any model, score OOS, or read market results.

## Headline

- Frozen class-C templates: **124**
- Templates with at least one non-null panel value: **124**
- Zero-support templates: **0**
- Global coverage >= 60% (diagnostic only): **1**
- Global coverage < 60% but nonzero (diagnostic only): **123**
- Near-duplicate feature pairs |r| >= 0.95: **44**
- Very-near pairs |r| >= 0.99: **44**

## Selection rule

No feature is pruned here for coverage, correlation or style-strength correlation. The frozen OOS design already specifies a **60% coverage screen fit on each training fold only**. That remains the availability gate. Exact canonical duplicates were already removed before this stage.

## Family support

- **BOOKINGS**: 20 templates; 20 with support; median global coverage 0.4978.
- **CORNERS**: 24 templates; 24 with support; median global coverage 0.4215.
- **GOALS**: 32 templates; 32 with support; median global coverage 0.4324.
- **TEAM_TOTALS**: 48 templates; 48 with support; median global coverage 0.4215.

## Interpretation

Coverage and redundancy can tell us whether the frozen Sol ideas are operationally usable, but not whether they predict outcomes. Any predictive claim remains blocked until the subsequent frozen walk-forward M0-versus-M1 experiment.
