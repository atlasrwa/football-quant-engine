# QFE V2 Layer 3 — Component Evaluation

Frozen on: 2026-10-03
Bundle hash: `b4c7566577a15d5f6b007ad41a5d4de62c3ee54f7026df804260620465e0602e`
Chronology hash: `9cf5e680174b78b639a80bd85498ed04f3f79482634ced8194ae5c9192495269`
Development fold hash: `b019226b8ff7ff278cb334909becc847642838ca9fe3fca269a5332565123e1a`

> **DEVELOPMENT OOF ONLY. Calibration and protected outcomes are unscored.**

## Metric distinction

The earlier structured tournament's `side_joint_nll` evaluates the joint
home/away side-count likelihood. The fold OOF `total_count_nll` evaluates
the probability of the realized match total. They are different scoring
objects and are reported separately.

## Paired OOF component comparisons vs dynamic Poisson

| Target | Candidate | Total-count NLL Δ | Binary LL Δ | Brier Δ | Decision |
|---|---|---:|---:|---:|---|
| goals | dynamic_dixon_coles | -0.000114 [-0.000998, +0.000767] | -0.000000 [-0.000000, +0.000000] | -0.000000 [-0.000000, +0.000000] | NOT_SUPPORTED_OR_INCONCLUSIVE |
| goals | dynamic_nb2 | -0.000006 [-0.000012, +0.000000] | +0.000000 [-0.000001, +0.000002] | +0.000000 [-0.000001, +0.000001] | NOT_SUPPORTED_OR_INCONCLUSIVE |
| goals | competition_dixon_coles | -0.002202 [-0.008182, +0.003334] | -0.001121 [-0.005762, +0.003493] | -0.000489 [-0.002707, +0.001771] | NOT_SUPPORTED_OR_INCONCLUSIVE |
| goals | tabular_hist_gradient_boosting | -0.016429 [-0.024195, -0.008728] | -0.013197 [-0.020863, -0.005842] | -0.005774 [-0.009421, -0.002346] | REJECT_MATERIALLY_WORSE |
| goals | similar_context | +0.002381 [-0.002805, +0.007097] | +0.001796 [-0.002237, +0.005992] | +0.000797 [-0.001179, +0.002848] | WEAK_MIXED_SIGNAL_CIS_CROSS_ZERO |
| corners | dynamic_side_nb2 | -0.011473 [-0.021569, -0.001023] | +0.002440 [+0.000767, +0.004022] | +0.001132 [+0.000336, +0.001881] | BINARY_MARKET_CANDIDATE_MIXED_TOTAL_DISTRIBUTION |
| corners | tabular_hist_gradient_boosting | -0.018508 [-0.031624, -0.005592] | -0.013605 [-0.022899, -0.005208] | -0.006077 [-0.010396, -0.002144] | REJECT_MATERIALLY_WORSE |
| corners | similar_context | +0.000136 [-0.006040, +0.005912] | +0.000697 [-0.004452, +0.005553] | +0.000270 [-0.002213, +0.002635] | WEAK_MIXED_SIGNAL_CIS_CROSS_ZERO |

## Interpretation

- Goals: tested Dixon-Coles/NB2 replacements are not supported; tabular is materially worse; similar-context remains a weak possible ensemble diversifier because mean gains are positive but CIs cross zero.
- Corners: side-NB2 improves binary over/under Log Loss and Brier with positive paired CIs, but worsens fold OOF total-count NLL. It is therefore retained only as a mixed binary-market candidate, not declared a universally superior count distribution.
- Corners similar-context is weak/inconclusive; tabular is materially worse.
- No calibration fitting, ensemble fitting, market comparison, or protected scoring is authorized by this evidence.
