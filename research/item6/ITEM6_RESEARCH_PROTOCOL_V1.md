# ITEM 6 — NOVEL HYPOTHESIS DISCOVERY AND INCREMENTAL VALUE

`ITEM6_RESEARCH_PROTOCOL_V1` · zero-spend build · CHAMPION untouched · `LIVE_SONNET_CALLS=0`

---

## 0. Governing principle (enforced structurally)

The LLM is **not** the football predictor. It must never produce `p_model`, match/event
probabilities, effect sizes, odds, EV, betting edge, stakes, or latent matchup scores. Its only
scientific role is to **discover what the deterministic engine should measure**. Deterministic
code owns candidate formalization, data retrieval, support counts, similarity, measurement,
effect estimation, confounder handling, walk-forward OOS, model fitting, calibration, and
`p_model`.

This is enforced in code: `schema.FORBIDDEN_KEYS` rejects any response carrying a
numeric-authority field; the mechanism schema has no field that asks the model for a number;
the formalizer and registry never compute or store support, effect, similarity, or OOS.

## 1. Why Item 6 exists

Prior evidence chain:

- **V1**: LLM hypotheses were measurable, but the search space admitted a trivial venue shortcut.
- **V2**: LLM underperformed end-to-end, but a later audit found material information asymmetry.
- **V3**: with identical candidate information, the model and the deterministic selector tied
  exactly. The generation corpus was disciplined but low-entropy — single-condition dominant
  (≈97/112 one leg, ≈1/112 two legs), exactly one interaction family, ~80% semantic duplication,
  **zero** novel hypothesis families, zero genuine joint two-dimension conditions, zero
  nonlinearities, zero thresholds, zero sequencing, zero game-state constructions.

So the unresolved question is **not** "can the model generate a valid hypothesis" — it can. It is:

> Can a deliberately redesigned LLM hypothesis-discovery instrument generate genuinely novel,
> grounded, falsifiable football hypothesis **families** that deterministic baseline enumeration
> does not naturally produce, and do those families subsequently add OOS predictive information?

## 2. The frozen core scientific question

> "Can an LLM, given point-in-time-safe football evidence and an explicit description of what the
> deterministic engine already covers, discover novel, grounded, falsifiable hypothesis families
> that expand the measurable search space and subsequently produce incremental OOS predictive
> information?"

It contains **two claims, tested separately**:

- **CLAIM 1 (Stage 1)** — the LLM expands the research space.
- **CLAIM 2 (Stage 2)** — that expansion contains incremental predictive value.

Failure of Claim 1 ends the experiment before Stage 2.

The objective is **not** to make the LLM win. The experiment is built to be equally capable of
disproving the LLM hypothesis-layer thesis:

- **Outcome A** — the LLM genuinely expands the search space with novel, grounded, measurable
  ideas that later add OOS value; or
- **Outcome B** — even given a fairer generation instrument, it still fails to add incremental
  research value.

## 3. Two prospectively separated stages

- **STAGE 1 — GENERATION / RESEARCH-SPACE EXPANSION.** Does the new generator actually produce a
  *different kind* of research output? Judged by generation-quality endpoints, **not** by OOS
  results. OOS outcomes are invisible to every Stage-1 evaluator.
- **STAGE 2 — OOS INCREMENTAL-VALUE VALIDATION.** May occur **only** if Stage 1 passes its frozen
  gate. Compares feature/hypothesis **universes** (baseline vs baseline + frozen novel families).

### Stage-1 scientific question (frozen)

> "Does the redesigned generation instrument produce grounded, falsifiable, provider-safe
> football hypothesis families that are not baseline-equivalent, repeatably across a fresh
> cohort, and that survive deterministic formalization?"

### Stage-2 scientific question (frozen, prospective placeholder only)

> "Do hypotheses instantiated from LLM-discovered novel families provide OOS predictive
> information beyond hypotheses available from the deterministic baseline family universe?"

## 4. Key design changes vs the prior instrument

1. **No worked football example.** The scientific prompt (`ITEM6_MECHANISM_PROMPT_V1`) contains
   no concrete metric pair, interaction, direction, venue, profile, family, or `candidate_id`.
   Anti-imitation tests fail the build if any appears in the model-facing prompt body.
2. **Tell the model what is already covered.** `DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1`
   enumerates the covered families abstractly. Prior OOS success/failure of those families is
   **not** revealed (that is researcher knowledge, not treatment input).
3. **Mechanism discovery before formalization.** Phase A (mechanism discovery) and Phase B
   (research specification) are the model's job; Phase C (formalization) is deterministic code.
   The model does not determine support N, effect, similarity, feasibility, p-value, or OOS.
4. **Generate multiple mechanisms.** `K_MECHANISMS_PER_FIXTURE = 5` distinct mechanisms where
   they exist; explicit abstention (`NO_NOVEL_GROUNDED_MECHANISM`) is allowed and tracked.
5. **Do not force the existing grammar at discovery time.** Mechanism semantics are controlled
   free text; only the observable concepts are bounded. This is what lets the model transcend
   the V2/V3 grammar. Downstream deterministic parsing decides measurability.

## 5. Firewalls and invariants (frozen)

- `CHAMPION_INDEPENDENT = true`. Nothing in Item 6 enters production `p_model` automatically.
  Any positive Stage-2 result still requires the candidate-feature promotion protocol,
  prospective shadow validation, calibration comparison, and production review.
- `NO_LLM_NUMERICAL_PREDICTION = true`. Enforced by schema firewall + tests.
- `OOS_BLINDED_DURING_STAGE1 = true`. The Stage-1 grader sees only the pre-target packet, the
  generated mechanism, evidence refs, and the baseline coverage spec — never future OOS
  outcomes, markets, settlement, or ARM-D performance.
- `POINT_IN_TIME_SAFE = true`. All generation inputs must be available before target kickoff.
  Provider-unsafe and future-leakage concepts are rejected at formalization.
- Additive grammar extensions are **versioned Item-6-only** constructs; V2/V3 grammar is never
  mutated.

## 6. Pre-registered decision tree (frozen)

```
IF STAGE1_FAIL:
    STOP ITEM 6.
    Conclusion: LLM_HYPOTHESIS_DISCOVERY_NOT_SUPPORTED — even after removing example anchoring
    and explicitly targeting novel mechanisms, the LLM did not demonstrate repeatable
    research-space expansion.
    Do NOT proceed to Stage 2. Do NOT tune the same cohort. Do NOT rewrite thresholds.

IF STAGE1_PASS:
    FREEZE the accepted novel-family registry, formalization code, family deduplication, and
    all generated outputs BEFORE any OOS validation. Only then may Stage 2 be constructed.

IF STAGE2_FAIL:
    Conclude the novel LLM families did not demonstrate incremental predictive value.

IF STAGE2_PASS:
    Conclude LLM research-space expansion demonstrated incremental predictive value under the
    frozen design. Even then, do NOT directly modify CHAMPION.
```

## 7. Arms

- **ARM G-L** — the upgraded LLM generator (Stage 1 treatment). *Not run in this build.*
- **ARM G-D** — a deterministic hypothesis-family generator drawn only from the existing
  enumerated baseline families (`control_generator`). Not deliberately weakened. Establishes the
  covered space ARM G-L must exceed. By construction every G-D proposal formalizes to
  `F1_BASELINE_EQUIVALENT`.

The primary Stage-1 question is not "which sounds better" but: **does ARM G-L produce valid
measurable families outside ARM G-D's covered space?**

## 8. Artifacts (this build)

| # | Artifact | Path |
|---|---|---|
| 1 | Research protocol | `research/item6/ITEM6_RESEARCH_PROTOCOL_V1.md` |
| 2 | Baseline coverage spec | `research/item6/DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1.md` (+`.json`) |
| 3 | Mechanism prompt | `research/item6/ITEM6_MECHANISM_PROMPT_V1.md` |
| 4 | Mechanism schema | `research/item6/ITEM6_MECHANISM_SCHEMA_V1.md` · code `src/research/item6/schema.py` |
| 5 | Baseline-equivalence detector | `src/research/item6/baseline_equivalence.py` |
| 6 | Mechanism formalizer | `src/research/item6/formalizer.py` |
| 7 | Novel-family registry schema | `research/item6/NOVEL_FAMILY_REGISTRY_SCHEMA_V1.md` (+`.json`) |
| 8 | Stage-1 quality protocol | `research/item6/STAGE1_QUALITY_PROTOCOL_V1.md` · code `quality_protocol.py` |
| 9 | Stage-1 gate | `research/item6/STAGE1_GATE_V1.md` · code `stage1_gate.py` |
| 10 | Stage-1 power & cost | `research/item6/STAGE1_POWER_AND_COST_V1.md` |
| 11 | Fresh Stage-1 cohort | `research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json` |
| 12 | Stand-in rehearsal | `research/item6/_run_standin_rehearsal.py` · `out/STANDIN_REHEARSAL.json` |
| 13 | Stage-2 framework (placeholder) | `research/item6/STAGE2_FRAMEWORK_V1.md` |
| — | Composed integrity review + freeze | `research/item6/ITEM6_FREEZE_MANIFEST.json`, `ITEM6_BUILD_REPORT.md` |

## 9. Zero-spend guarantee

This build performs design, implementation, manifests, schemas, prompts, deterministic
baselines, a mock/stand-in rehearsal, tests, preregistration, and power analysis. It performs
**no** paid model call: `LIVE_SONNET_CALLS=0`, `BEDROCK_PAID_CALLS=0`, `NEW_SPEND_USD=0`. Stage-1
live execution requires explicit human spend authorization.
