# QFE V2 Layer 3 — Component Evaluation

Frozen on: 2026-10-02
Bundle hash: `bc7ca4aa57577cd15902062718125537afacc6aaa04092322ffb3d27be28ee5c`
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
| goals | dynamic_dixon_coles | -0.000107 [-0.000993, +0.000776] | +0.000000 [-0.000000, +0.000000] | +0.000000 [-0.000000, +0.000000] | NOT_SUPPORTED_OR_INCONCLUSIVE |
| goals | dynamic_nb2 | -0.000006 [-0.000012, +0.000000] | +0.000000 [-0.000001, +0.000002] | +0.000000 [-0.000001, +0.000001] | NOT_SUPPORTED_OR_INCONCLUSIVE |
| goals | competition_dixon_coles | -0.002207 [-0.008182, +0.003331] | -0.001126 [-0.005752, +0.003484] | -0.000491 [-0.002720, +0.001765] | NOT_SUPPORTED_OR_INCONCLUSIVE |
| goals | tabular_hist_gradient_boosting | -0.016433 [-0.024202, -0.008740] | -0.013203 [-0.020870, -0.005857] | -0.005776 [-0.009417, -0.002348] | REJECT_MATERIALLY_WORSE |
| goals | similar_context | +0.002376 [-0.002824, +0.007096] | +0.001791 [-0.002233, +0.005984] | +0.000795 [-0.001173, +0.002847] | WEAK_MIXED_SIGNAL_CIS_CROSS_ZERO |
| corners | dynamic_side_nb2 | -0.011440 [-0.021534, -0.000997] | +0.002443 [+0.000771, +0.004025] | +0.001134 [+0.000336, +0.001881] | BINARY_MARKET_CANDIDATE_MIXED_TOTAL_DISTRIBUTION |
| corners | tabular_hist_gradient_boosting | -0.018467 [-0.031602, -0.005556] | -0.013576 [-0.022859, -0.005167] | -0.006063 [-0.010379, -0.002127] | REJECT_MATERIALLY_WORSE |
| corners | similar_context | +0.000177 [-0.006006, +0.005945] | +0.000727 [-0.004413, +0.005578] | +0.000283 [-0.002195, +0.002644] | WEAK_MIXED_SIGNAL_CIS_CROSS_ZERO |

## Interpretation

- Goals: tested Dixon-Coles/NB2 replacements are not supported; tabular is materially worse; similar-context remains a weak possible ensemble diversifier because mean gains are positive but CIs cross zero.
- Corners: side-NB2 improves binary over/under Log Loss and Brier with positive paired CIs, but worsens fold OOF total-count NLL. It is therefore retained only as a mixed binary-market candidate, not declared a universally superior count distribution.
- Corners similar-context is weak/inconclusive; tabular is materially worse.
- No calibration fitting, ensemble fitting, market comparison, or protected scoring is authorized by this evidence.
