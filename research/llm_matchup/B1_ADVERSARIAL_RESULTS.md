# B1 — Adversarial Football Interpretation Results

Evaluates **interpretation fidelity**, not predictive performance (brief §16). Live Sonnet
on the frozen Phase-B stack. Harness: `src/research/llm_matchup/run_b1_adversarial.py`.

**Live scope note:** each Sonnet call is ≈ 45 s / ≈ 28k input tokens, and each fixture runs
up to 4 live calls (FULL, ABLATION, LABEL-SHUFFLE, REPEAT). A representative adversarial
subset of **10 fixtures** (33 live calls) was executed here within cost/latency limits; the
harness runs the full 30–50 design when given a larger budget. Selection is deterministic
and difficulty-stratified (formation instability, exact-cohort sparsity, family-vs-exact
strength, formation-family diversity).

## Headline metrics

| Metric | Value |
|--------|------:|
| Fixtures | 10 |
| FULL calls schema-valid / accepted | **10 / 10 (100 %)** |
| Formation-sensitive fixtures (ablation changed the state) | **10 / 10** |
| Ablation mean state-change fraction | 0.276 |
| Repeatability mean state-change fraction (temp≈0, cache off) | 0.135 |
| Repeatability stable (≤ 0.15 change) | 6 / 10 |
| Label-shuffle mean change | 0.336 |
| Genuine stereotype flags (net of repeatability noise) | **1 / 8 shuffle-eligible** |

## 1. Schema fidelity — strong

All 10 FULL-variant calls produced validator-accepted states: real evidence ids, PIT-safe
citations, correct A/B and FOR/AGAINST orientation, honest two-concept formation flags, no
probabilities/prose/predictions. No fabricated evidence references. No future-target
leakage. This matches the B0 finding that the deterministic contract holds under live use.

## 2. Formation-removal ablation (brief §20) — formation adds information

Removing the formation dimensions (`fc_*`, `fmx_*`, `formation_delta_*`, `formation_context`)
changed the resulting state in **all 10** fixtures, by 6–36 % of shared mechanisms on
average (mean 0.276). Notably, Sonnet emitted **zero explicit `FORMATION_*` family
mechanisms** — yet the ablation still shifted its **base** mechanism levels. Interpretation:
formation-conditioned evidence influences Sonnet's reasoning about width/box/corner
mechanisms even without dedicated formation mechanisms. Formation is not inert, but neither
does Sonnet lean on formation *labels* to manufacture formation-specific conclusions from
thin evidence.

## 3. Label-shuffle control (brief §21) — mostly clean, one real flag

We swapped the nominal formation labels while holding the behavioral evidence byte-identical
(verified in `tests/research/test_formation_policy.py::test_label_shuffle_changes_only_labels_not_behavior`).
Raw shuffle change must be read **net of repeatability noise** (Sonnet is not deterministic
even at temperature 0):

| Fixture | shuffle Δ | repeat Δ | net | verdict |
|---------|----------:|---------:|----:|---------|
| mt_406686899 | 0.00 | 0.17 | −0.17 | clean (shuffle call rejected, excluded) |
| mt_839956993 | 0.21 | 0.00 | +0.21 | within noise band |
| mt_974237747 | 0.18 | 0.15 | +0.03 | clean |
| mt_257690291 | 0.21 | 0.15 | +0.06 | clean |
| mt_361807430 | 1.00 | 0.76 | +0.24 | **instability**, not stereotype |
| mt_196035863 | 0.03 | 0.03 | +0.00 | clean |
| mt_257018290 | 0.12 | 0.03 | +0.09 | clean |
| mt_745924405 | 0.94 | 0.06 | **+0.88** | **GENUINE STEREOTYPE FLAG** |

- `mt_361807430`: the naive shuffle metric (1.00) looks alarming, but repeatability on the
  *same* input was 0.76 — the change is dominated by run-to-run instability, not label
  reliance. Net +0.24 is below the 0.34 threshold.
- `mt_745924405`: shuffle change 0.94 with repeatability 0.06 → net **+0.88**. This is a
  real stereotype-dependence case: swapping `4-4-1-1` ↔ `4-2-3-1` (behavior unchanged, stable
  output) moved almost the entire state. **Flagged.** One genuine case in eight.

This is the single most important B1 finding: the label-shuffle control only becomes
meaningful once repeatability noise is subtracted, and after that correction Sonnet shows
**low but non-zero** stereotype dependence (≈ 1/8).

## 4. Repeatability — a real concern

At temperature ≈ 0 with caching disabled, 6/10 fixtures were stable (≤ 0.15 change) but 4
were not, and one (`mt_361807430`) diverged by 0.76 between two identical calls. Sonnet on
Bedrock is **not** deterministic. Mitigation already in place: outputs are cached by
`(model, versions, packet_hash)` so a persisted research feature is stable once generated.
But the underlying generation variability must be reported and, for Phase C, either (a)
sampled-and-aggregated, or (b) treated as a noise source in the incremental-value test.

## 5. Matchup swap test (brief §19)
The metamorphic swap (A-vs-B → B-vs-A with venue / FOR-AGAINST / formation roles corrected)
is implemented via the packet's symmetric construction and the label-shuffle transform. The
byte-identical behavioral-evidence guarantee under relabeling is unit-tested. A full live
A↔B swap comparison is deferred to the larger-budget run; the deterministic transform is in
place and covered by tests.

## Verdict

B1 is **broadly a pass with two documented caveats**:
- ✅ 100 % schema fidelity, zero fabricated/leaked evidence, correct orientation, honest
  formation flags, formation demonstrably adds information.
- ⚠️ Repeatability is imperfect (4/10 not stable; one large divergence) — must be managed in
  Phase C.
- ⚠️ One genuine label-stereotype case (1/8) — below a failure threshold but non-zero; worth
  monitoring and a candidate for a prompt-v3 correction *before* B2 freeze if it recurs at
  scale.

Neither caveat meets the §40 STOP criteria (Sonnet is not inventing facts, not relying on
club-name stereotypes systematically, labels do not dominate behavior in aggregate). Proceed
to B2 with the caveats recorded.
