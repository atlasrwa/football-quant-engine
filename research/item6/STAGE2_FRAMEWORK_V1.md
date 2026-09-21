# STAGE2_FRAMEWORK_V1 — prospective placeholder only

`item6_stage2_framework_v1` · **BLOCKED unless `STAGE1_PASS`** · no cohort generated, no outcomes
evaluated, no outcome-driven family filters built in this document.

Stage 2 activation is contingent on Stage 1 passing its frozen gate and the novel-family registry
being frozen. This document specifies the framework prospectively; it does not run it.

## Scientific question (frozen)

> "Do hypotheses instantiated from LLM-discovered novel families provide OOS predictive
> information beyond hypotheses available from the deterministic baseline family universe?"

The contribution under test is **search-space expansion**, so we compare feature/hypothesis
**universes**, not one LLM hypothesis vs one deterministic hypothesis.

## Nested models

- **M0 (BASE)** — features/candidates derived from the deterministic baseline family universe
  only.
- **M1 (BASE+LLM)** — the identical M0 universe **plus** candidates/features derived from the
  frozen LLM-discovered novel families. The **only** difference between M0 and M1 is the
  availability of the frozen novel-family set.

Both universes then pass through **identical**: feature screening, regularization, walk-forward
training, calibration, and evaluation. The LLM does not choose coefficients and does not set
probabilities.

## Controlling candidate multiplicity fairly

Stage 2 must NOT reward the LLM merely for producing more candidates. Options, to be fixed
prospectively at activation:

- matched family budgets between M0 and M1;
- a pre-specified feature-selection algorithm applied identically to both universes;
- nested models with regularization (M1 must beat M0 *after* penalizing added degrees of
  freedom);
- incremental (nested) likelihood-ratio-style tests.

The statistically cleanest design will be frozen at activation; the default is **nested,
regularized models with a pre-specified identical selection algorithm**, so M1 wins only if the
novel families carry information beyond what regularization would otherwise shrink away.

## Primary endpoint (predictive, not sign-persistence)

Preregistered model-level metric — **incremental OOS log loss** (M1 vs M0) on the prospectively
defined target, with **Brier delta** and **calibration/ECE** as co-primary/secondary. **Hit rate
is not the main metric.** If the research target is a specific market/statistic, it is defined
prospectively at activation.

## Secondary endpoints

Incremental OOS likelihood, Brier delta, calibration/ECE, feature-selection frequency of novel
families, stability across folds, and (later) genuine prospective shadow performance. **Betting
P&L is never primary research evidence.**

## Walk-forward OOS

Strict chronological walk-forward. No future leakage. No tuning on the final OOS block. All family
definitions are frozen before the folds they influence (the registry is frozen at Stage-1 pass).

## Multiplicity

Novel families may be numerous. Control multiplicity via regularization / hierarchical shrinkage,
with BH-FDR for family-level inferential diagnostics where appropriate. **No cherry-picking the
best LLM family after observing OOS.**

## Confounders

For candidate measurements: venue, competition, season, opponent strength, score state, cards,
manager/tactical regime where actually observable, formation where supported, and
sample-size/reliability. No causal claims.

## Similarity

Any similar-opponent concept is deterministic. The LLM may propose similarity *dimensions*; code
computes similarity scores, neighbors, and thresholds. No invented LLM similarity scores.

## Champion firewall (unchanged)

`CHAMPION_INDEPENDENT = true`. A positive Stage-2 result still requires the candidate-feature
promotion protocol, prospective shadow validation, calibration comparison, and production review.
Nothing enters production `p_model` automatically.

## Decision

- `STAGE2_FAIL` → conclude novel LLM families did not demonstrate incremental predictive value.
- `STAGE2_PASS` → conclude LLM research-space expansion demonstrated incremental predictive value
  under the frozen design. Even then, do not directly modify CHAMPION.
