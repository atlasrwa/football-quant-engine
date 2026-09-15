# V5A2_FINAL_INTERFACE_CLOSURE — Execution Report

Run once, under explicit human authorization. Ceiling $9.22 (preregistered $9.2171).
**Actual spend $0.9775.** The battery halted on a preregistered stop rule at call 6 of 38.

---

## 1. Pre-call verification (at $0.00) — `out/v5a2/PRE_CALL_CHECK.json`

| Check | Result |
|---|---|
| 16 V5A.2 module hashes | match |
| 17 frozen upstream V2/V3/V5A/V5A.1 module hashes | match |
| 13 frozen artifact hashes vs authorization §8 | match |
| 20 packet hashes + 38 serialized request-byte hashes | match |
| `schema_v3` content hash | match |
| evaluator sha256 vs `EVALUATOR_FREEZE.json` | match |
| CHAMPION (`data/discovery/pilotC_stat_mixer.json`) | unchanged |
| stop rules vs preregistration | match |
| byte reproducibility, seeds 1/2/3/12345 | pass |
| test suite | 127 passed |
| interpreter | `/home/ubuntu/.venv/bin/python`, 3.12.3 |
| boto3 / botocore | 1.43.93 / 1.43.93 |
| `converse` on Bedrock Runtime client | present |
| credentials | acct 865147226910, `atlas-ubuntu-deployer` |

**Model/profile preflight.** `bedrock:GetInferenceProfile` returned `AccessDeniedException` —
a missing *describe* permission on this IAM principal, which says nothing about invoke. No
probe call was made. Invocability of `us.anthropic.claude-sonnet-4-6` in `us-east-1` is
evidenced by V5A.1's own log: 6 charged calls, HTTP 200, same model id, same region. The run
subsequently confirmed it: 6/6 calls returned.

**One new file, written and hashed before the first paid call.** No V5A.2 analyzer existed.
`_analyze_v5a2.py` (`6be0693c93a66044`) is a driver — it defines no metric and calls only
frozen evaluator functions. It pre-commits four aggregation choices (A1 validity definition;
A2 paired = primaries valid in both arms; A3 valid-per-arm over the 10 primaries only;
A4 repeat groups and discipline deltas include every charged call, failures scoring 0).
A2 and A3 are the stricter readings; A4 is V5A.1's inherited convention and inflates the
noise floor, making PASS harder. No frozen artifact was modified, before or after the run.

## 2. Calls and cost

| | |
|---|---|
| planned | 38 |
| attempted | 6 |
| **paid (charged)** | **6** |
| transport failures | 0 |
| never attempted (halted) | 32 |
| input tokens | 189,172 |
| output tokens | 27,333 |
| **actual cost** | **$0.977511** |
| ceiling | $9.2171 — **never approached** (10.6 %) |
| expected had it completed | $7.04 |

No call exceeded the ceiling guard; the ceiling was not the binding constraint and was never
raised. Observed inputs came in **below** the preregistered per-call estimates in both arms
(base 17,330 vs 18,450; research 59,926 vs 61,598), so the per-call worst-case guard never
fired.

## 3. Stop-rule checkpoints

`classify_stop` was evaluated after every charged call.

| after seq | charged | `failure_class = MODEL_SCHEMA_INVALID` (incl. firewall — see §5) | infra | consecutive transport fail | spend | fired |
|---|---|---|---|---|---|---|
| 1–4 | 1–4 | 0 | 0 | 0 | ≤$0.4517 | none (rate rule guarded: needs ≥6 calls) |
| 5 | 5 | 1 | 0 | 0 | $0.7146 | none (5 < 6) |
| **6** | **6** | **2** | **0** | **0** | **$0.9775** | **`V5A2_STOP_MODEL_SCHEMA_INVALID_RATE` — 2/6 = 0.333 > 0.30, class MODEL** |

The rule fired at the first call at which it was eligible to be evaluated. Honored exactly;
the run halted immediately and the remaining 32 calls were never attempted.

## 4. Infrastructure incidents

**Zero.** `n_transport_failures = 0`, `n_infrastructure_contract_failures = 0`,
`INFRASTRUCTURE_CONTRACT_FAILURE` never raised, no `AttributeError`, no apparatus defect on
any hypothesis. D4 is closed in practice, not only in test: every call reached the provider
and returned. The post-run hash reverification is clean — nothing frozen moved during the run.

## 5. Per-call outcomes (the five-way taxonomy, kept separate)

| seq | arm | rep | in | out | outcome | accepted / n |
|---|---|---|---|---|---|---|
| 1 | base | 0 | 17,330 | 3,801 | VALID_MODEL_RESPONSE | 6 / 12 |
| 2 | base | 1 | 17,330 | 3,892 | VALID_MODEL_RESPONSE | 0 / 12 |
| 3 | base | 2 | 17,330 | 4,390 | VALID_MODEL_RESPONSE | 7 / 12 |
| 4 | base | 3 | 17,330 | 4,164 | VALID_MODEL_RESPONSE | 0 / 12 |
| 5 | research | 0 | 59,926 | 5,547 | MODEL_FIREWALL_VIOLATION | 0 / 12 |
| 6 | research | 1 | 59,926 | 5,539 | MODEL_FIREWALL_VIOLATION | 0 / 12 |

- **INFRASTRUCTURE_FAILURE: 0**
- **MODEL_SCHEMA_INVALID: 0** — no response was malformed against the schema
- **MODEL_AVAILABILITY_VIOLATION (whole-response): 0**
- **MODEL_FIREWALL_VIOLATION: 2**
- **VALID_MODEL_RESPONSE: 4**

**A naming caveat that must not be glossed.** `validator_v4` assigns `failure_class =
MODEL_SCHEMA_INVALID` to a firewall violation. The stop rule's numerator is therefore fed by
firewall violations, and the rule named "schema-invalid rate" fired on two events that were
*not* schema invalidity. The rule's **class attribution (MODEL) is correct** and the halt is
attributable to model behavior either way, so this changes no conclusion — but the separation
the authorization asks for exists in this report, not in the frozen `failure_class` field.

## 6. Firewall violations — exactly what happened

Both research-arm responses were rejected whole on a single token of prose:

- **seq 5**, `$.hypotheses[8].question`: matched `'50%'` —
  *"Does AWAY_TEAM's possession dominance (ALL_PRIOR mean well above 50%) translate into a
  proportionally higher final_third_entries rate…"*
- **seq 6**, `$.hypotheses[7].question`: matched `'60%'`

Class `B_EVIDENCE_VALUE_REPRODUCTION`, a rule **present since `firewall_v2`** — not one of
V5A.2's D5 additions. The packet does supply possession statistics
(`SUMMARY:*:possession_for/against`), so the rule's rationale applies: the model attached a
numeric threshold to a packet-supplied statistic in prose instead of referencing it by id.

**Blast radius.** One offending question out of twelve rejected all twelve hypotheses, and
**88 (seq 5) and 95 (seq 6) evidence references were discarded unread.** This is the frozen
design: `NUMERICAL_AUTHORITY_VIOLATION` is a whole-response failure. It was not modified.

## 7. Grounding results

Measured only where responses validated — i.e. the base arm.

Two denominators are in play and they are kept apart. The frozen evaluator's pooled rates are
computed over **primary calls only** (`rep == 0`), which for the base arm means **seq 1 alone**.
The four-call column aggregates all base responses. Both are stated; neither is blended.

| | base primary (seq 1) | all 4 base calls | research (2 calls) |
|---|---|---|---|
| grounded acceptance rate | 0.50 (6/12) | **0.271** (13/48) | not measured |
| unsupported dimension rate | 0.50 (6/12) | **0.729** (35/48) | not measured |
| abstention rate | 0.333 (4/12) | 0.229 (11/48) | not measured |
| valid evidence reference rate | 1.00 (46/46) | **1.00** (215/215) | not measured |
| fabricated evidence rate | 0.00 | **0.00** (0/215) | not measured |
| compilability | 1.00 (6/6) | **1.00** (13/13) | not measured |
| redundancy rate | 0.00 | 0.00 | not measured |
| degenerate (`ANY`) conditions | 0 | 0 | not measured |
| abstentions citing valid evidence | 4/4 | **11/11** (D2 contract used correctly) | not measured |

Only the **seq-1 column** fed the frozen evaluator's discipline deltas. The four-call column is
descriptive.

**Zero fabricated evidence references across every reference the model emitted in a
validating response.** That is the strongest single positive signal in the run.

The research-arm column reads "not measured", not "zero". `score_response` returns early on a
whole-response failure, so its ref counts, compilability, availability-use figures and
diversity counts are `_blank_score` defaults — **artifacts of the early return, not
measurements.** The research responses did in fact carry 88 and 95 well-formed evidence
references; they were never scored. Any table that prints research-arm zeros here is printing
a placeholder.

## 8. Availability violations

No whole-response availability violation occurred. Within the four validating base-arm
responses, the per-hypothesis inadmissibility counts were **6, 12, 5, 12 of 12** — the base
packet declares **zero conditionable terms**, so any conditioned hypothesis is inadmissible
there by construction. This is the D3-preserved rejection behaving as designed.

**The mechanism is exact.** Across all four base calls,
`grounded_accepted_n = 12 − n_unsupported_dimension` holds with no residual:

| seq | inadmissible | accepted | 12 − inadmissible |
|---|---|---|---|
| 1 | 6 | 6 | 6 |
| 2 | 12 | 0 | 0 |
| 3 | 5 | 7 | 7 |
| 4 | 12 | 0 | 0 |

**Every admissible hypothesis was accepted, and every rejection was an availability
rejection.** Nothing was rejected for grounding, fabrication, compilation, redundancy,
degeneracy or firewall reasons in the base arm — not once in 48 hypotheses.

The four availability-aware dimensions (`venue_use`, `recent_vs_long_use`,
`opponent_profile_use`, `formation_use`) are **0 in both arms**, but for different and
non-comparable reasons: structurally zero in base (nothing exposed), and unmeasured in
research (early return). **No cross-arm inference may be drawn from them.**

## 9. Paired Arm A vs Arm B results

**None. Zero paired fixtures.** One fixture (`mt_010243515`) was reached; its base primary
validated and its research primary was a firewall violation, so it does not pair. The 20
paired calls of the manifest were never completed — call ordering is fixture-major, so all 6
paid calls fell on that single fixture.

No mean paired difference, no discipline comparison and no arm ranking is reported, because
none exists. The `discipline_deltas` written to `evaluation_results.json`
(compilability −1.0, firewall_clean −1.0) are computed from **n = 1 primary per arm against a
failed response** and are not evidence about either arm; the frozen `final_verdict` correctly
refused to consume them.

## 10. Repeatability / self-noise

One group per arm, against a preregistered minimum of three.

| group | n | values (`grounded_accepted_n`) | SD |
|---|---|---|---|
| base / mt_010243515 | 4 | **6, 0, 7, 0** | 3.269 |
| research / mt_010243515 | 2 | 0, 0 | 0.000 |

Pooled SD **2.3117**; the 0.5 minimum floor was not binding.

At `temperature = 0.0`, against a **byte-identical request** (same `serialized_request_sha256`
on all four base calls), the primary metric took values 0, 6, 7 and 0. Output token counts
also differed (3,801 / 3,892 / 4,390 / 4,164). This is a substantive observation — but with
one group per arm it is **below the preregistered minimum and cannot be treated as an
estimate of self-noise.** It is recorded, not relied upon.

## 11. Evaluator gates

Frozen evaluator `v5a2_evaluator_v1`, sha256 `fb92b9f0…36518`, verified identical to
`EVALUATOR_FREEZE.json` before scoring. Run exactly once.

| gate | minimum | observed | met |
|---|---|---|---|
| paired fixtures | 8 | **0** | no |
| valid responses, base | 8 | **1** | no |
| valid responses, research | 8 | **0** | no |
| repeatability groups, base | 3 | **1** | no |
| repeatability groups, research | 3 | **1** | no |

**All five fail.** No PASS/MIXED/FAIL was issued, by the evaluator's own rule.

---

## 12. Execution status

```
EXECUTION_STATUS = STOPPED
```

Halted at call 6 of 38 by `V5A2_STOP_MODEL_SCHEMA_INVALID_RATE` (2/6 = 0.333 > 0.30, class
MODEL). Clean halt: zero infrastructure incidents, zero transport failures, spend $0.9775
against a $9.2171 ceiling. The apparatus did what it was built to do — it stopped the run on
model behavior rather than on its own plumbing, which is the opposite of V5A.1.

## 13. Scientific evaluability

```
SCIENTIFIC_STATUS = NON_EVALUABLE
```

Five of five evaluability criteria unmet. The battery terminated far before the preregistered
evaluability minimum, so this is reported regardless of any mechanical partial score.

## 14. Mechanical verdict

```
SCIENTIFIC_VERDICT = None (no PASS / MIXED / FAIL issued)
```

The frozen `final_verdict` issues no verdict on a NON_EVALUABLE run, because with this little
valid data "FAIL" would be a claim the data cannot support. Reported as `None` — not as FAIL.

## 15. Scientific interpretation

**What this run does not answer.** It produced no evidence on the primary question — whether
Arm B's richer evidence surface yields better-grounded hypotheses. Zero paired observations,
one fixture, six calls. Any Arm A vs Arm B statement would be fabrication.

**What it does establish.**

1. **The interface closure holds under live conditions.** Zero infrastructure contract
   failures, zero transport failures, zero schema-invalid responses, zero advertised terms
   rejected. Every V5A.1 failure mode (D1–D4) stayed closed against a real model. The halt
   is attributable to model behavior, which is what V5A.2 was built to make possible.

2. **Grounding discipline was excellent where measurable.** 215/215 evidence references valid,
   zero fabrications, 13/13 accepted hypotheses compiled, zero degenerate conditions, zero
   redundancy, and all 11 abstentions used the D2 contract correctly — abstaining *and* citing
   the evidence for the gap, the preferred form. Across 48 base-arm hypotheses **not one was
   rejected for grounding, fabrication, compilation, redundancy, degeneracy or firewall
   reasons**: `accepted = 12 − inadmissible` holds exactly on all four calls (§8), so every
   rejection was availability, and every admissible hypothesis passed.

3. **Two failure modes are recorded as genuine model behavior, per the authorization.**
   - *Research arm:* both responses put a percentage into prose about a packet-supplied
     statistic. The contract is stated in the prompt and the rule predates V5A.2. The model
     violated a stated contract it had been told about. That is a model result.
   - *Base arm:* two of four identical calls conditioned every hypothesis on dimensions the
     base packet declares unavailable. Also a model result.

**On the interpretation constraint, applied honestly.** Arm A's zero exposed conditionable
dimensions were not counted against it: its 6 and 7 accepted hypotheses came from
unconditioned questions filling the same 12-hypothesis ceiling, and no availability-dimension
count entered any comparison. Arm B received no credit for volume — it produced 88 and 95
evidence references and 24 hypotheses and scored zero, because the frozen firewall rejected
both responses whole. Raw counts bought it nothing, exactly as specified.

**Two confounds a reader must hold onto.** Both are properties of the frozen design, recorded
rather than repaired:

- The rate rule became eligible at 6 calls, and the frozen fixture-major call order means the
  first 6 calls are all **one fixture**. The stop therefore fired on within-fixture behavior,
  and 2/2 is a sample of one fixture, not of the research arm.
- A single prose token voided 12 hypotheses and ~90 evidence references, twice. The frozen
  whole-response semantics mean the research arm's actual grounding quality is unknown, not
  poor.

**No rescue is proposed.** Neither confound is an objectively demonstrable apparatus *defect*:
the firewall rule is long-standing and correctly applied, the call order was preregistered,
and the model did write the numbers. The experiment is uninterpretable because it stopped
early on model behavior — which the authorization names as an acceptable outcome. Nothing was
changed, and no V5A.3 was created. Any successor must be separately designed and
preregistered.

---

## 16. Boundary confirmations

- **No feature promotion occurred.** No predictive coefficient, candidate feature, OOS search,
  threshold or prospective prediction was produced or written.
- **CHAMPION remained unchanged.** `data/discovery/pilotC_stat_mixer.json` sha256 verified
  identical to `champion_protection.frozen_sha256` both before and after the run.
- **All earlier experiments remained untouched.** Post-run reverification of all 17 frozen
  upstream V2/V3/V5A/V5A.1 module hashes plus all 16 V5A.2 module hashes returned zero
  problems. All 13 frozen V5A.2 artifacts are byte-identical to their pre-run hashes.
- **No downstream work performed.** V5B not run; no predictive effects measured; no hypothesis
  promoted; `p_model` untouched; no similarity tuning; no OOS feature fishing; no market
  result consulted.
- **The frozen apparatus was not modified** — not to reduce cost, not after seeing outputs.
  `max_tokens` remained 8192. The only file created is the analysis driver, written and
  hashed before the first paid call.

## 17. Artifacts

```
out/v5a2/PRE_CALL_CHECK.json                  zero-spend verification record
out/v5a2/execution/execution_log.jsonl        per-call log, written before scoring
out/v5a2/execution/execution_summary.json     transport accounting + stop
out/v5a2/execution/scores.json                driver-side scores
out/v5a2/execution/raw/001..006.json          immutable raw responses
out/v5a2/execution/evaluation_results.json    frozen evaluator output
research/hypothesis_engine/_analyze_v5a2.py   6be0693c93a66044 (pre-spend)
```

```
V5A2_EXECUTION_COMPLETE
EXECUTION_STATUS   = STOPPED
SCIENTIFIC_STATUS  = NON_EVALUABLE
SCIENTIFIC_VERDICT = None (no PASS/MIXED/FAIL issued)
```
