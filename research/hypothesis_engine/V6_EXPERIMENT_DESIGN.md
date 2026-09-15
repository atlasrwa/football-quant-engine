# V6_GROUNDED_RESEARCH_GENERATOR — Experiment Design

**Status: pre-spend. This document does NOT authorize spend.**
Model `us.anthropic.claude-sonnet-4-6`, temperature 0.0, max_tokens 8192. Zero Bedrock calls have been made.

## 1. The scientific question

> Given richer PIT-safe football history, can the LLM generate better grounded, non-degenerate, deterministically measurable football research hypotheses than from compressed/base evidence, beyond model self-noise and without loss of discipline?

V6 tests the **research-question layer only**. It stops before predictive feature promotion (§1, §40). The LLM proposes *what to measure*; it never authors `p_model`, probabilities, odds, EV, stakes, advantage scores or effect sizes.

## 2. Not a repair of V5A.2

V5A, V5A.1 and V5A.2 remain immutable historical experiments. V6 **reuses their validated interface and their packets unchanged** and changes only two things:
1. **How a response is adjudicated** — per hypothesis, not per response (§3).
2. **How the run is scheduled and judged** — balanced round-robin (§6), diversity-gated stops (§7), first-class self-noise (§9), a frozen scientific verdict (§25/§26).

The V5A.2 packets are shipped **byte-identical** (`packet_identity_audit.json`: 0 differences). Nothing about the evidence is re-derived.

## 3. Architecture (preserved)

```
football history
 → LLM proposes what to measure
 → deterministic compiler
 → deterministic measurement
 → statistical validation
 → candidate feature
 → OOS validation
 → model/calibration → p_model → market → prospective
```

**V6 stops at the first arrow's output.** Even a PASS proves only that richer evidence improves the research-question layer, not predictive value (§40).

## 4. Arms

| | Arm A (base) | Arm B (research) |
|---|---|---|
| Evidence | derived summaries only (`ALL_PRIOR`, venue `ANY`) | full match rows + summaries + opponent-profile cohorts + short windows + venue splits |
| Windows | `ALL_PRIOR` | `ALL_PRIOR`, `W5`, `W10` |
| Conditionable terms | **none** | opponent_profile, historical_venue_conditioning, competition, own/opponent_formation_family |
| Evidence ids (fixture mt_010243515) | 114 | 3366 |

The arms differ **only** in evidence representation. The packet never serializes which arm it is (M-6); `arm_isolation_audit.json` shows 0 identity leaks and no treatment labels.

## 5. Battery (§27, derived — not inherited)

- 10 paired fixtures × 2 arms = **20 primary calls**
- 4 repeat fixtures × 2 arms × 2 extra repeats = **16 self-noise calls**
- **Total: 36 calls.** V5A.2's 38 is not carried over.

## 6. Primary endpoint (§10, §21, §22)

The unit is the **QUALIFIED_RESEARCH_HYPOTHESIS**: schema-valid ∧ grounded ∧ availability-compliant ∧ numeric-authority-compliant ∧ compiler-valid ∧ non-degenerate ∧ non-redundant ∧ contextually supported. The primary comparison is the **paired per-fixture Arm B − Arm A qualified-rate difference**, benchmarked against the self-noise standard error at the same aggregation level.

## 7. Cost (§28)

| | value |
|---|---|
| calls | 36 |
| est. input tokens | 1,457,486 |
| expected cost | **$6.74** |
| p90 cost | $7.20 |
| hard ceiling (max_tokens on every call) | **$8.80** |

The ceiling is a true bound under the frozen request parameters.

## 8. Verdicts (§25/§26)

`EVALUABILITY (§26) → DISCIPLINE (§25) → PRIMARY (§21,§22)`, all thresholds frozen before spend. A run that fails coverage is `NON_EVALUABLE` and issues no PASS/MIXED/FAIL. A clean FAIL is a valid, valuable outcome (§39).

## 9. Downstream boundary (§40)

V6 produces no coefficients, candidate features, OOS search, thresholds or prospective predictions. Nothing here may be promoted to `p_model` or CHAMPION. A separate deterministic-measurement experiment is the only next stage, and it is out of scope here.
