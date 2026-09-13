# Pre-Phase-C Hardening Report — LLM_MATCHUP_V2

**Status: REVISE_LLM_LAYER. Phase C predictive evaluation has NOT been run and must not be run
against this generation.**

This report answers the 14 required questions for the Pre-Phase-C Hardening Patch applied to
the completed Phase-B Hybrid Quant + Sonnet Football Evidence Engine (`PHASE_B_V1`, frozen,
untouched). It covers a new, separately-frozen generation, `LLM_MATCHUP_V2`
(`research/llm_matchup/out/FREEZE_LLM_MATCHUP_V2.json`), built to measure — not to improve the
narrative sophistication of — the Sonnet-derived football-state instrument, per the patch's
final directive: *"Make Sonnet-derived football states sufficiently stable, adversarial,
measurable, and distinguishable from simple deterministic transformations before testing their
predictive value."*

Phase B's probability engine, champion model, contextual challenger, calibration, thresholds,
publication and prospective logic were **not touched** by this pass (patch §2). This is
entirely upstream instrumentation work.

## Correction note (read this first)

The controls stage of this pipeline (formation-label-shuffle / team-name / competition-name,
patch §24-§26) originally ran to completion but produced **zero usable rows** for all three
controls while still reporting `trip_rate: 0.0` — a false pass caused by an empty-sample
default, not a genuine null result. It was rerun (same code, same 15-fixture hardening control
set, no logic change) and produced real data. `eligibility.py` was then extended with an
explicit global identity-control gate and `mechanism_eligibility.json` /
`FREEZE_LLM_MATCHUP_V2.json` were regenerated. No other stage (repeatability, counter-evidence
golden cases, ablation-vs-noise, surrogate ladder, aggregate comparison) was rerun — those
artifacts were unaffected by the bug. Both the broken and corrected control results are kept
side by side in `out/hardening/pipeline_summary.json` under `"correction"` for audit.

---

## 1. Why were identical calls unstable?

Field-level repeatability (30 stratified fixtures × 3 identical calls, 952 mechanism-field
keys; `repeatability_field_level.csv`, `repeatability_summary.json`):

| Field | Agreement |
|---|---|
| status | 93.2% |
| strength | 93.2% |
| confidence/reliability | 94.1% |
| supporting evidence IDs | 82.8% |
| counter-evidence IDs | 98.6% |
| UNKNOWN flag | 99.6% |
| CONFLICTED flag | 100% |
| limitations/reason codes | 77.2% |

Applying the deterministic severity ladder (0=identical … 4=SUPPORTED↔CONFLICTED/UNKNOWN
reversal): 853/952 keys identical (severity 0), 91 adjacent-ordinal (severity 1), 4 substantial
strength shifts (severity 2), 0 status changes (severity 3), 4 outright reversals (severity 4).
**Semantically-stable fraction (severity ≤1) = 99.16%; severe disagreement = 0.42%.**
`instability_cause_counts`: 944 STABLE, 4 `RESOLVED_VS_UNCERTAIN_FLIP`, 4
`ONTOLOGY_BOUNDARY_OR_MODEL_NOISE`. So instability at the aggregate/semantic level is small and
concentrated at ontology boundaries (a field flipping between a resolved status and
UNKNOWN/CONFLICTED) rather than random noise across the whole label space — consistent with
patch §7's expectation that instability has identifiable causes rather than being uniform model
jitter. The weakest fields are free-text-ish (`limitations` reason codes, 77.2% agreement) and
citation-set membership (`support_ids`, 82.8%) — i.e. *which* evidence gets cited drifts more
than *what conclusion* is reached.

## 2. Which mechanisms were unstable?

Per-stratum semantic stability (`per_stratum_semantic_stability`) is uniformly high (96.2–100%)
across BEHAVIOR_HEAVY, FORMATION_HEAVY, HIGH_SHRINKAGE, SMALL_N, STRONG_EVIDENCE, WEAK_EVIDENCE
and TACTICAL_CLUSTER_DIVERSE strata — no single stratum stands out as a stability outlier.
At the mechanism level (`mechanism_eligibility.csv`), only **`FOUL_DRAWING`** failed the
repeatability/sensitivity bar outright: `semantic_stable_frac=0.964`,
`severe_disagree_frac=0.036`, and `sensitivity_flag=UNSTABLE_SENSITIVITY` (ablation distance did
not exceed self-noise) → classified `RESEARCH_ONLY_UNSTABLE`. Every other measured mechanism
cleared the repeatability bar on its own.

## 3. Did Prompt V3 improve stability?

There is no Prompt V2 baseline run under identical conditions to A/B against, so this cannot be
answered as a before/after delta — it can only be answered against the patch's own bar. Against
that bar, Prompt V3 (two-pass candidate-then-falsification contract, no chain-of-thought) meets
the repeatability target: 99.16% semantic stability, 0.42% severe disagreement, well inside a
defensible "acceptable" range. What Prompt V3 does **not** do is prevent identity/label leakage
into the output — see §9–§11 below, which is the dominant finding of this pass.

## 4. Did counter-evidence recall improve on known adversarial cases?

Six golden adversarial packets (patch §14, cases A–F: crosses-vs-corners divergence,
box-pressure-vs-corner-concession conflict, small-N formation counterweight,
2H-score-state confound, provider disagreement, and a no-counter-evidence control), 2 calls
each (`counter_evidence_controls.json`):

- **Constraint pass rate: 5/6 (83.3%)** — in the cases where counter-evidence was expected,
  the emitted *state* was appropriately constrained (CONFLICTED, or not pushed to
  SUPPORTED+VERY_HIGH) rather than ignoring the conflicting signal.
- Case C (`FORMATION_WIDTH_INTERACTION`, small-N formation counterweight) failed entirely:
  0/2 calls returned OK (both were fail-closed rejects) — this case is untested, not merely
  unstable.
- **`n_explicit_recall_any = 0` and `min/mean_explicit_recall = 0.0` in every case that
  produced an OK call.** The model reaches the directionally-correct *aggregate* state (e.g.
  case B → CONFLICTED both calls) without ever explicitly citing the specific counter-evidence
  ID the case was designed to require. This is a meaningful gap even inside a "pass": we can
  confirm the *state* looks right, but not that the model is doing it by actually locating and
  citing the falsifying evidence, as the two-pass contract (patch §11) requires — as opposed to
  reaching a plausible label by some other route. This is flagged, not glossed over, per patch
  §4 (distinguish severity) and §56 (measurement quality over plausibility).

## 5. Did it invent counter-evidence?

No. `any_false_opposition = false` in all 6 golden cases, including case F (a control where
counter-evidence was NOT expected and none should be manufactured). No evidence of the
"reward counter-evidence quantity" failure mode patch §13 warns against.

## 6. Which states are trivially reproduced by raw features?

Surrogate ladder (S0 base-rate → S5 small interaction model) run against the persisted raw
input feature matrix (`raw_input_feature_matrix.csv`, `surrogate_results.csv/json`), 19
mechanisms with sufficient coverage:

- **Trivially reducible (S1 ≈ S0, a single raw feature matches or beats every richer surrogate):
  `CONTACT_INTENSITY` (98.3%) and `FOUL_TENDENCY` (93.1%).** These two are classified
  `REDUNDANT_WITH_DETERMINISTIC` (still fine to keep for interpretability per patch §51, not to
  claim as incremental intelligence).
- **Partially reducible (a single feature does most of the work but isn't perfect):**
  `BOOKING_CONVERSION`, `BOX_PRESSURE`, `BOX_PRESSURE_MATCHUP`, `CLEARANCE_DEPENDENCE`,
  `CONTACT_MATCHUP`, `CORNER_CONCESSION`, `SET_PIECE_GENERATION`, `SHOT_VOLUME`,
  `TERRITORIAL_PRESSURE` — 9 mechanisms.
- **Irreducible/noisy (no simple surrogate does well, S1 well under 55–60% and S3–S5 no
  better):** `BOX_PROTECTION`, `CORNER_MECHANISM_MATCHUP`, `CROSS_ALLOWANCE`,
  `SHOT_CREATION_MATCHUP`, `SHOT_SUPPRESSION`, `WIDE_PRESSURE_MATCHUP`, `WIDTH_PRESSURE` — 7
  mechanisms.
- `SHOT_QUALITY`: insufficient coverage (4 fixtures, 1 distinct label) to run the ladder.

## 7. Which require multidimensional interaction?

**None.** `n_multidimensional = 0` — no mechanism's surrogate ladder showed a materially better
S3–S5 (interacting-features) fit than the best single-feature S1. Per patch §20, the correct
reading of this is **not** "Sonnet reduces to one feature everywhere" (17/19 measured
mechanisms are only *partially* or *not at all* reducible by any simple surrogate — see §6) —
it is that where a raw feature is informative, one feature already captures most of it, and
where no simple surrogate works, adding interaction terms doesn't help either. Combined with
§21 below, the irreducible group is the more interesting case, but "irreducible by a small
surrogate" is not yet evidence of "Sonnet performing genuine interaction reasoning" — see §8.

## 8. Does evidence-induced variation exceed self-noise?

Ablation-vs-noise (`ablation_noise_summary.json`, 9 usable fixtures of 15 sampled — 6 skipped
for insufficient OK calls on the ablated packet): mean ablation distance 0.163 vs. mean
self-noise 0.042 — **evidence-induced change exceeds self-noise in 6/9 fixtures (66.7%)**,
`n_unstable_sensitivity = 5` mechanisms flagged `UNSTABLE_SENSITIVITY` (ablation distance did
not clear the noise bar) out of 40 mechanisms examined at this stage. So for roughly two-thirds
of usable fixtures, removing evidence moves the state by more than repeating the identical
packet does — a real, if not overwhelming, signal-over-noise margin. The 40% skip rate on the
ablated call itself (fail-closed rejects/unavailable) is a coverage limitation on this
particular study, not a stability finding — see "Known limitations" below.

## 9. Does formation still matter after controlling for LLM noise?

**No — this remains unproven, and coverage is now worse than in Phase B, not better.**
`n_formation_mechanisms = 0` in the ablation-vs-noise study (no formation-conditioned mechanism
had ablation data to evaluate at all, so `n_formation_meaningful` is vacuously 0/0), and
every `FORMATION_*` mechanism (`FORMATION_BEHAVIOR_FIT`, `FORMATION_BOX_INTERACTION`,
`FORMATION_TRANSITION_STATE`, `FORMATION_VS_OPP_DEFENSIVE_PROFILE`,
`FORMATION_WIDTH_INTERACTION`) shows `coverage: 0` in `mechanism_eligibility.csv` →
`INSUFFICIENT_COVERAGE`. Phase B's "formation adds information 10/10" (patch §23's starting
point) has **not** been re-confirmed net of noise in this pass; it has not been re-tested at
all for lack of labelled coverage. This is an open item for the next hardening iteration, not a
finding either way.

## 10. Does formation label alone influence Sonnet?

**Yes, and materially.** Formation label-shuffle control (behavior, numeric evidence, sample
sizes and context held fixed; only the nominal home/away formation label swapped):
**12 usable fixtures, 9 tripped (75.0% trip rate), mean shuffle distance 0.107** against a
mean self-noise reference in the same range as §1 (~0.01–0.20 per fixture). This is
`FORMATION_STEREOTYPE_SENSITIVITY` at a rate far above any defensible "acceptably low" bar
(pre-committed at 20% for this gate — see "Thresholds" below). Patch §49's rule — *"a formation
label alone cannot support a behavioral mechanism"* — is **not currently enforced** by
Prompt V3/Schema V3/Validator V3 in practice, whatever the prompt says on paper.

## 11. Do club/competition names influence Sonnet improperly?

**Yes, on both counts.**
- **Team-name control** (real names vs. `TEAM_A`/`TEAM_B`, evidence byte-identical, competition
  held real): 13 usable fixtures, **9 tripped (69.2%), mean distance 0.118.**
- **Competition-name control** (real competition vs. `COMP_NEUTRAL`, team names held real): 13
  usable fixtures, **7 tripped (53.8%), mean distance 0.088.**

Both are far above the noise floor and the pre-committed 20% bar. The runtime default of
sending neutral identifiers (`NEUTRAL_IDENTIFIERS_DEFAULT = True`, patch §25) is the right
mitigation and should stay in place — but these controls prove the *risk it exists to prevent*
is real, not hypothetical: if real identifiers were ever sent, the closed-world contract would
be violated at a high rate. The closed-world contract is "real, not aspirational" (patch §25)
only for the *default* runtime path; the underlying model behavior beneath the neutral-identity
default has not been shown to be closed-world-honest.

## 12. Is sample-and-aggregate necessary?

Single-vs-3-call comparison from the repeatability states (`aggregate_comparison.json`, 987
mechanism instances): **67.98% STABLE, 23.0% flagged UNSTABLE by aggregation, 9.02% WEAK.**
Roughly a quarter of mechanism instances would be silently over-confident if only a single call
were trusted — 3-call aggregation (preserving disagreement as `UNSTABLE` rather than
majority-voting it away, per patch §32/§33) is doing real, non-trivial work here and is
recommended to keep. It does **not**, however, do anything for the identity-sensitivity finding
above — aggregation smooths call-to-call noise, not systematic label-driven bias; 3 identical
calls to a real-name packet would still average out to a real-name-biased answer.

## 13. What does it cost?

Total spend on this hardening generation, corrected controls included:

| Stage | Cost (USD) |
|---|---|
| Repeatability (30 fixtures × 3 calls) | $15.82 |
| Counter-evidence golden cases (6 cases × 2 calls) | $0.39 |
| Ablation-vs-noise (15 fixtures) | $9.41 |
| Identity controls, corrected (15 fixtures) | $19.83 |
| **Total, corrected generation** | **≈ $45.46** |
| Sunk cost: original broken controls run (0 usable rows) | $8.47 |

Cost per fixture (repeatability stage): $0.527. Cost per semantically-stable state: $0.017.
Cost per accepted (OK) state: $0.198. **Cost per Phase-C-usable mechanism is currently
undefined (0 mechanisms are usable post-gate)** — see §14.

Known limitation: `hardened_call_manifest.csv` (and therefore the `cost_accounting` block in
`mechanism_eligibility.json`) only logs the repeatability stage's calls; counter-evidence,
ablation and controls costs are tracked separately in their own stage summaries and are
included in the total above by hand. Unifying call logging across all stages is recommended
before the next hardening iteration so cost accounting doesn't require manual reconciliation.

## 14. Which mechanisms are Phase-C eligible?

**None, currently.** The identity-control global gate (added in this pass) fails:

```
if team_name_sensitivity fails          # FAIL: trip_rate=0.692, n=13
or competition_name_sensitivity fails   # FAIL: trip_rate=0.538, n=13
or formation_label_sensitivity fails:   # FAIL: trip_rate=0.750, n=12
    LLM layer = NOT PHASE_C ELIGIBLE
```

All three fail. Per patch §25 ("FAIL CLOSED for that mechanism/prompt configuration") this is
a **global** gate over the shared prompt/schema/runtime configuration, not a per-mechanism
verdict — so it overrides every mechanism's pre-gate classification. Before the gate, 18
mechanisms were `PHASE_C_ELIGIBLE` and 2 `REDUNDANT_WITH_DETERMINISTIC`; all 20 are now
`REJECTED`, with the pre-gate class and the gate's reason preserved per-row in
`mechanism_eligibility.csv`/`.json` for audit (nothing is hidden — patch §32/§33/§44). The
remaining 9 mechanisms are unaffected by the gate because they were already not going to
proceed: 8 `INSUFFICIENT_COVERAGE`, 1 (`FOUL_DRAWING`) `RESEARCH_ONLY_UNSTABLE`.

---

## Exit criteria (patch §56)

| Criterion | Status |
|---|---|
| Accepted states remain fully evidence-grounded | ✅ fail-closed validator unchanged, no salvage |
| No leakage introduced | ✅ (this pass exists to check exactly this) |
| **Counter-evidence controls pass** | ⚠️ states directionally correct (5/6), but explicit recall of the cited counter-evidence is 0% — not a clean pass |
| Repeatability understood and acceptable | ✅ 99.16% semantically stable, causes identified |
| Evidence-induced change exceeds self-noise for eligible mechanisms | ⚠️ true in 6/9 usable fixtures; formation-specific coverage is 0 |
| Formation behavior survives noise controls | ❌ not established — 0 usable formation-mechanism coverage |
| **Formation-label stereotype sensitivity acceptably low** | ❌ **75% trip rate** |
| **Team-name / competition-name controls pass** | ❌ **69% / 54% trip rate** |
| Raw-feature surrogate analysis available | ✅ full S0–S5 ladder against persisted raw features |
| Frozen hardened generation exists | ✅ `LLM_MATCHUP_V2`, re-frozen after correction |

## Recommendation

**REVISE_LLM_LAYER.**

This is not a borderline call. The instrument is repeatable (§1/§3) and its counter-evidence
*behavior* is directionally sound (§4/§5), and 3-call aggregation is worth keeping (§12) — but
it is currently **not closed-world**: a formation-label swap alone flips ~3/4 of packets, and
real vs. neutral team/competition identifiers flip roughly half to two-thirds of packets, at
magnitudes far above the model's own call-to-call noise. That is precisely the failure mode
patch §§10, 24–26, 48–49 exist to catch, and it means Sonnet's structured states are
substantially driven by identity/label stereotypes rather than by the supplied evidence alone,
for a large share of fixtures. Per the explicit gate specified for this hardening pass:

```
if team_name_sensitivity fails
or competition_name_sensitivity fails
or formation_label_sensitivity fails:
    LLM layer = NOT PHASE_C ELIGIBLE
```

All three fail → **the LLM layer is NOT PHASE_C ELIGIBLE.** **Phase C predictive evaluation
must not be run against `LLM_MATCHUP_V2`** in its current form. Recommended next steps before
another hardening attempt: (1) strengthen the closed-world instruction in Prompt V3 specifically
around formation labels and identifiers (patch §48/§49 are written but evidently not binding
model behavior); (2) consider whether the neutral-identifier runtime default alone is sufficient
mitigation or whether the underlying reasoning needs to be evidence-anchored more forcefully
(e.g. explicit "you must not use TEAM_A/TEAM_B or formation label as evidence" reinforcement
adjacent to each mechanism, not just in the system prompt preamble); (3) re-run this same
controls battery against the revised prompt/schema (which will mint a new generation id per
patch §1) before any further consideration of Phase C; (4) separately, restore formation-
mechanism coverage so §9 can actually be answered, and tighten the counter-evidence explicit-
recall metric so §4's "pass" is not just directionally-correct luck.

---

*Machine-readable artifacts: `out/hardening/{repeatability_field_level,repeatability_severity,
counter_evidence_controls,raw_input_feature_matrix,surrogate_results,ablation_vs_noise,
formation_ablation_v2,formation_label_shuffle_v2,team_name_control,competition_name_control,
mechanism_eligibility,hardened_call_manifest}.{csv,json}`, `out/hardening/pipeline_summary.json`
(includes the pre-correction values under `"correction"`), `out/FREEZE_LLM_MATCHUP_V2.json`.*
