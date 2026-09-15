# SONNET46_HYPOTHESIS_V3 — Final Report

**Manifest hash:** `cfd9244067c9dc0ca18140f1d02460e9833b1df820cff7070713df6f6f8cce3f`
**Executed:** 56/56 frozen calls · **Spend:** $5.4620 of a $10.3694 ceiling
**Stop rule:** NOT triggered · **Mechanical verdict:** **FAIL**

Nothing was redesigned, repaired, optimized or reinterpreted after authorization. Every
gate, denominator, classifier and threshold below is the frozen one; the analyzer computes,
it does not decide.

---

## 1. Calls attempted and completed

| | |
|---|---|
| Planned | 56 |
| Attempted | 56 |
| **Completed** | **56** |
| Infrastructure-censored (in the battery) | **0** |
| `stopReason` | `tool_use` on all 56 |
| Resolved model id | `us.anthropic.claude-sonnet-4-6` on all 56 |
| Cache hits / retries | 0 / 0 |

All eight frozen arms executed in full: reference 12, repeatability 12, identity_alias 6,
irrelevant_field 6, profile_axis_perturbation 6, availability_ablation 6,
evidence_starvation 4, unsupported_data_trap 4.

---

## 2. Spend and token usage

| | |
|---|---|
| Input tokens | 1,137,193 |
| Output tokens | 136,695 |
| Total tokens | 1,273,888 |
| **Actual cost** | **$5.4620** |
| Preregistered expected | $5.66 |
| Hard ceiling | $10.3694 |
| Remaining | $4.9074 |
| Ceiling reached | No |

**The frozen calibration held.** Measured actual/chars-4 ratio **1.5588** against the frozen
**1.5938** — the guard was conservative by 2.2% in the safe direction, exactly as designed.
Actual spend came in 3.5% under the preregistered expectation.

---

## 3. Stop-rule status

`SCHEMA_INVALID` evaluated at every frozen checkpoint, numerator restricted to whole-response
failures that are *exactly* `SCHEMA_INVALID`:

| Checkpoint | SCHEMA_INVALID | Rate | Threshold | Action |
|---|---|---|---|---|
| 12 | 0/12 | 0.0000 | ≥0.25 | continue |
| 24 | 0/24 | 0.0000 | ≥0.25 | continue |
| 36 | 0/36 | 0.0000 | ≥0.25 | continue |
| 48 | 0/48 | 0.0000 | ≥0.25 | continue |
| 56 | 0/56 | 0.0000 | ≥0.25 | continue |

**Not triggered. Zero schema-invalid responses in the entire battery.** This is the single
cleanest result of the experiment: the residual risk flagged as the preregistration's #1
danger — whole-response rejection under the strict closed-enum schema, with a documented
16/64 (0.25) historical base rate — did not materialise at all. Showing the model the closed
contract in its tool spec eliminated it.

---

## 4. Infrastructure failures and censoring

**Within the battery: none.** Zero infrastructure-censored calls, zero retries, zero
censoring of any kind.

**Before the battery: a transport misconfiguration, at zero spend.** The first invocation of
`_run_v3.py` used the system interpreter (boto3 1.34.46), which predates the Bedrock
`converse` API. All 12 attempted calls raised `AttributeError` **before any request reached
AWS**: 0 input tokens, 0 output tokens, $0.0000, no model contact. Because no valid paid
inference had occurred, the post-authorization freeze (which binds "after the first valid
paid inference") had not engaged. Only the interpreter changed — to `/home/ubuntu/.venv`
(boto3 1.43.93), the same environment the frozen V2 run used. No fixture, packet, prompt,
schema, contract, threshold or stop rule was touched, and the runner's preflight re-verified
the manifest hash, prompt hash, schema hash, all 56 packet hashes and all 56
serialized-request hashes as clean before the first real call.

The 12 censored records are preserved verbatim in
`hypothesis_states.ABORTED_TRANSPORT_PREFLIGHT.jsonl` with a written note. They are not part
of the battery: they contacted no model and carry no model behaviour. Leaving them in the
live states file would have caused resume-by-seq to silently skip 12 of the 56 frozen calls.

**Test suite: 488/488 pass** under the venv. Earlier in this project I reported "1
pre-existing failure (`sklearn` missing)". That was an artifact of invoking pytest under the
*system* interpreter; the venv has `sklearn 1.9.0` and the full suite, including the
architecture-isolation test that runs CHAMPION with the LLM packages blocked, passes there.

---

## 5. Discipline gates

Measured on all 56 completed calls.

| Gate | Numerator / Denominator | Value | Threshold | Result |
|---|---|---|---|---|
| D1 schema validity | 56 non-SCHEMA_INVALID / 56 | **1.0000** | ≥0.95 | **PASS** |
| D2 whole-response validity | 55 clean / 56 | **0.9821** | ≥0.90 | **PASS** |
| D3 query compilability | 536 fully compiled / 536 accepted | **1.0000** | ≥0.85 | **PASS** |
| D4 evidence grounding | 536 accepted / 550 emitted | **0.9745** | ≥0.95 | **PASS** |
| D5 fabricated evidence | 0 / 56 | **0** | =0 | **PASS** |
| D6 capability awareness | 0 unavailable requests / 550 | **0.0000** | ≤0.05 | **PASS** |
| D7 numerical authority | 2 blocking (class A) / 56 | **2** | =0 | **FAIL** |
| D8 latent grading | 2 GRADE-layer / 56 | **2** | =0 | **FAIL** |
| D9 leakage | 0 / 56 | **0** | =0 | **PASS** |
| D10 non-redundancy | median over clean reference responses | 0.0000 | ≤0.35 | **NOT MET** (n=11 < 12) |
| D11 metric richness | median over clean reference responses | 10.0 | ≥5 | **NOT MET** (n=11 < 12) |
| D12 identity invariance (relative) | 0.1935 / floor 0.1894 | **1.0214** | ≥0.90 | **PASS** |
| D13 irrelevant invariance (relative) | 0.2152 / floor 0.1894 | **1.1365** | ≥0.90 | **PASS** |
| D14 evidence sensitivity | 6 sensitive / 6 pairs | **1.0000** | ≥0.50 | **PASS** |

**Query compilability is 1.0000 — 536 of 536.** Against V2's 0.4881. Not one accepted
hypothesis failed to compile.

**D7/D8 — the two failures, and they are the same two findings.** One reference response
(seq 11, `mt_010443150`) listed `home_advantage` twice in `candidate_confounders`.
`firewall_v2` classifies latent-grading findings as class A at the GRADE layer, so they count
in both gates. Zero tolerance is zero tolerance: the response was whole-rejected and both
gates fail. **The firewall was not touched after seeing responses.**

**D10/D11 — fail-closed on N, a cascade from that single response.** Both are medians over
reference responses with no whole-response failure. Seq 11's rejection left n=11 against a
frozen minimum of 12, so both score NOT MET regardless of value — and their values were
excellent (redundancy 0.0000 against a ≤0.35 bar; metric richness 10.0 against a ≥5 bar).
This is the preregistered fail-closed-on-N rule operating exactly as written. It is harsh,
and it is frozen.

**Firewall classification across all 56 calls:** class A 2 · class B **0** · class C 13
(suppressed). Zero evidence-value reproduction — the structural evidence-reference channel
added in prompt-v2 appears to have closed V2's one genuine Gate-E breach entirely.

**The pre-spend axis gate fired twice in the live run.** Seq 32 (`irrelevant_field`) and seq
39 (`profile_axis_perturbation`) each emitted `opponent_profile` with `axis: shots_for` — the
exact broken vocabulary entry discovered and gated during preregistration. Both were rejected
with `UNSUPPORTED_CONTEXT_SOURCE`. Without that gate they would have passed schema and the
frozen compiler and produced query plans with no resolvable metric. Those 2 rejections plus
the 12 hypotheses in the whole-rejected seq-11 response account for all 14 non-accepted
hypotheses (550 − 536).

---

## 6. Research-depth gates P1–P4

Measured on the 11 clean reference responses, eligibility-aware denominators.

| Gate | Numerator / Denominator | V2 replay | V3 | Threshold | Result |
|---|---|---|---|---|---|
| P1 meaningful multi-condition | 1 / 112 accepted | 0.0000 | **0.0089** | ≥0.10 | **FAIL** |
| P2 beyond-venue conditioning | 59 / 158 intents | 0.0616 | **0.3734** | ≥0.20 | **PASS** |
| P3 opponent-profile utilization | 11 / 11 eligible fixtures | 0.3333 | **1.0000** | ≥0.50 | **PASS** |
| P4 comparison entropy (bits) | over 158 intents | 0.2987 | **0.8783** | ≥0.60 | **PASS** |

**Depth criteria met: 3 of 4 → depth outcome PASS.**

Supporting detail (reported, never gated):

- **Restricting-leg distribution:** 0 legs → 14 · 1 leg → 97 · **2 legs → 1**. The
  condition-count distribution is overwhelmingly single-condition.
- **Interaction families observed:** exactly one — `{opponent_profile, venue}`.
- **Condition dimension usage:** venue 81 · opponent_profile 54 · opponent_formation_family
  4 · own_formation_family 1.
- **Comparison mix:** SUBJECT_OVERALL_BASELINE 133 · LEAGUE_ENVIRONMENT_BASELINE 10 ·
  SUBJECT_RECENT_VS_LONG_BASELINE 8 · SUBJECT_VENUE_BASELINE 7.
- **Venue-only intent rate:** 0.5063. **Overall-baseline rate:** 0.8418.
- **Formation utilization:** 2 of 3 eligible fixtures (0.6667). *Measured, not controlled, at
  N=3 — no formation claim may be made in either direction.*

---

## 7. Restraint gates

| Gate | Numerator / Denominator | Value | Threshold | Result |
|---|---|---|---|---|
| R1 conditions on withheld dimensions | 0 / 56 calls | **0** | =0 | **PASS** |
| R2 gratuitous conditions | 0 / 99 reference conditions | **0.0000** | ≤0.05 | **PASS** |
| R3 ANY-padding | 0 / 99 reference conditions | **0.0000** | ≤0.02 | **PASS** |
| R4 unsupported-data trap | 0 bad / 4 | **0** | =0 | **PASS** |
| R5 abstention on starved packets | 4 / 4 | **1.0000** | ≥0.70 | **PASS** |

**All five restraint gates pass, several perfectly.** Zero ANY-padding, zero gratuitous
conditions, zero conditions on any withheld dimension across all 56 calls, zero fabrication
under the baited trap.

**Abstention was total and correct.** All four starved packets returned
`{"hypotheses": []}` — abstention quality 1.0 on every one. Under V2's scoring definition
this ideal behaviour would have scored **0.0**; the corrected definition built during the
infrastructure task is what makes it legible.

---

## 8. Meaningful multi-condition examples

Exactly **one** hypothesis in the entire reference arm passed the frozen six-check
classifier — seq 8, `mt_010444904`, H6:

> *"Does the home team concede fewer big chances when playing at home against opponents with
> a high shots_on_target_for profile, compared to its overall baseline, given its recorded
> big_chances_against average?"*
>
> conditions: `venue=HOME` + `opponent_profile=HIGH, axis=shots_on_target_for`
> comparison: `SUBJECT_OVERALL_BASELINE` · family: `{opponent_profile, venue}`

This is a genuine, well-formed, compilable conditional research question of exactly the shape
V3 was built to detect. It is also the only one.

---

## 9. Representative failures

1. **`home_advantage` as a candidate confounder** (seq 11, ×2) — the model named a variable
   to *control for*, not an asserted advantage, but `firewall_v2` matches banned grade tokens
   by value anywhere in the payload. Whole response rejected; D7, D8 fail; D10, D11 cascade
   to NOT MET on N.
2. **`axis: shots_for`** (seq 32, seq 39) — the model reached for an axis that the vocabulary
   declares but the capability inventory cannot back. Caught by the pre-spend axis gate.
3. **Single-condition dominance** — 97 of 112 classified hypotheses carry exactly one
   restricting leg; only 1 carries two.

---

## 10. Paired-control results

**Repeatability floor (18 same-input pairs, 6 fixtures × 3 samples): median Jaccard
0.1894.** At temperature 0.0, the generator reproduces only ~19% of its own normalized
research intent on a byte-identical input.

| Control | Median Jaccard | Ratio to floor | Reading |
|---|---|---|---|
| identity_alias (6) | 0.1935 | 1.0214 | invariant *relative to its own noise* |
| irrelevant_field (6) | 0.2152 | 1.1365 | invariant *relative to its own noise* |

**profile_axis_perturbation (6):** surface-sensitivity **6/6**. Every perturbation moved
intent on the frozen offensive shot surface — not merely different text, but a delta touching
the perturbed surface. Axis-selection response (reported, not gated) was **2/6**: only
`mt_012232295` and `mt_010243938` moved their chosen `opponent_profile` axis into or out of
the perturbed `shots_on_target_*` family. In three of the remaining four, the perturbed axis
was already in use before perturbation.

**availability_ablation (6):** **6/6 clean.** Every ablated response dropped
`opponent_profile` conditioning entirely, with zero conditions on the withheld dimension,
while continuing to produce research (intent counts moved 12→20, 23→12, 13→20, 23→12, 16→12,
9→10 — the arm continued working, it did not collapse). All six reference partners *had* used
profile, so the disappearance denominator is 6 (≥3) and the rate is a real **1.0000**, not
`INSUFFICIENT_N`.

---

## 11. Mechanical verdict

```
Discipline gates: 10 PASS, 4 NOT MET  (D7, D8, D10, D11)
Restraint gates:   5 PASS, 0 NOT MET
Depth criteria:    3 of 4 met  ->  depth outcome PASS

Rule: FAIL if any DISCIPLINE or RESTRAINT gate is not met,
      or fewer than 2 DEPTH criteria are met.
```

## **SONNET46_HYPOTHESIS_V3 = FAIL**

Driven entirely by the discipline family. Depth reached PASS and restraint was flawless; four
discipline criteria did not hold, and all four trace to a single response containing the
token `home_advantage`.

**Severity note (reporting precision, not reinterpretation).** The four NOT-MET discipline
gates are not four independent defects. D7 and D8 count *the same two findings* — the two
`home_advantage` occurrences in `candidate_confounders` of seq 11 (`mt_010443150`) — because
`firewall_v2` labels a GRADE-layer finding class A, so it is registered by both the
class-A gate and the grade-layer gate. D10 and D11 are N-cascades: seq 11's whole-response
rejection dropped the clean-reference count to 11, below the frozen minimum of 12, so both
gates return NOT MET on insufficient N rather than on any observed quality shortfall. The
underlying evidence is one response and two findings. This does not soften the verdict: D7
and D8 both genuinely fail under their frozen definitions, those definitions are
zero-tolerance, and FAIL is correct as computed.

---

## 12. Scientific interpretation

*Separate from the verdict. It does not and cannot change it.*

**Disciplined — with one lapse that the instrument amplified.** 536/536 compilation, zero
fabrication, zero leakage, zero unavailable-capability requests, zero schema-invalid
responses. The V2 encoding catastrophe is gone: compilability went 0.4881 → 1.0000 on live
generation. The one genuine lapse — `home_advantage` in a confounder list — is, in my
reading, the same *class* of instrumentation collision as V2's `big_chances`/"chances at"
false positive: naming a confounder to control for is not grading a matchup. But I did not
touch the firewall after seeing it, and under the frozen rules it is a true failure. Its
knock-on effect is disproportionate: one response cost four discipline criteria, two of them
purely because losing one response dropped n from 12 to 11.

**Context-aware.** Opponent-profile utilization went 0.333 → **1.000**; beyond-venue
conditioning 0.062 → 0.373; comparison entropy 0.299 → 0.878. The model used the axis
vocabulary it was shown, reached for `LEAGUE_ENVIRONMENT_BASELINE` and
`SUBJECT_RECENT_VS_LONG_BASELINE` that V2 never touched, and — the strongest signal — it
stopped using `opponent_profile` completely in 6/6 ablations while continuing to produce
research. That is capability-boundary respect, not pattern repetition.

**Conditionally insightful — but only just.** One meaningful two-condition hypothesis in 112.
The prompt-scaffolding confound identified in the V2 replay is now resolved in a specific
direction: given a correct, exposed contract, Sonnet **broadened** its conditioning
substantially but did not **compose** it. It learned to vary one dimension at a time. The
"zero two-condition hypotheses" finding from V2 was not purely an artifact of the broken
contract — it moved from 0/132 to 1/112, which is a change in kind but not in magnitude.

**Not artificially complex, and appropriately restrained.** Zero padding, zero gratuitous
conditions, zero unsupported interactions, and total correct abstention on all four starved
packets. The anti-circularity design worked: the model was not pushed into manufacturing
interactions to satisfy a depth target.

**The most important unreported-by-gates finding: the repeatability floor is 0.1894.** At
temperature 0.0 the model reproduces under a fifth of its own research intent on identical
input. The relative-invariance correction built during the infrastructure task is what makes
D12/D13 interpretable at all — against V2's absolute 0.80 bar both would have failed on noise
alone. But passing *relative to a floor that low* is a weak claim: identity invariance holds
because nothing is stable, not because identity is irrelevant. For a research layer whose
output is meant to be a reproducible scientific record, sub-0.2 self-agreement is a
first-order problem that no gate in this preregistration was designed to catch.

**Overall reading.** Sonnet 4.6 behaved as a disciplined, restrained, capability-aware
hypothesis generator that genuinely exploits the research ontology it is shown — and that
neither composes conditions nor reproduces itself. The FAIL is real and mechanically correct;
it is also narrower than it looks, resting on one token in one response. The depth result
(3/4, PASS) and the restraint result (5/5, PASS) are the substantive scientific content, and
the compilation and abstention numbers say the corrected infrastructure works.

---

## 13. Promotion status

**No hypothesis, intent, query plan or feature was promoted to anything.** No candidate
feature was created. No effect size was estimated from any LLM output. No betting
recommendation was produced or published. The 536 compiled query plans were never executed
against data — compilation was verified, not run.

Any hypothesis from this run would still have to pass, in order: deterministic historical
measurement → sample/coverage sufficiency → confounder-aware analysis → walk-forward OOS →
prospective shadow validation → candidate feature consideration → quant model/calibration.
None of those stages was entered.

## 14. Architecture confirmation

**CHAMPION untouched.** `research/contextual_matchup/CHAMPION_FREEZE.json` unmodified.
`p_model` unchanged. Calibration unchanged. Prediction engine unchanged. Market comparison
unchanged. Prospective publication unchanged. Every V3 module imports only from within
`research.hypothesis_engine`; the runner that touches Bedrock lives outside the package, and
`test_architecture_isolation.py` — including the test that runs CHAMPION with the LLM
packages blocked — passes.

**V2 untouched.** `SONNET46_HYPOTHESIS_V2 = FAIL` stands. Zero files modified under
`out/hypothesis_v1_sonnet46_v2/` or `out/V2_COUNTERFACTUAL_REPLAY_v3contract/`.

---

## Artifacts

```
out/hypothesis_v3_sonnet46/hypothesis_states.jsonl      56 raw responses + provenance
out/hypothesis_v3_sonnet46/execution_ledger.json        spend, tokens, stop-rule status
out/hypothesis_v3_sonnet46/call_manifest.csv            per-call index
out/hypothesis_v3_sonnet46/evaluation_report.json       every measurement
out/hypothesis_v3_sonnet46/verdict.json                 the mechanical verdict
out/hypothesis_v3_sonnet46/cache/<sha256>.json          write-once raw cache (56)
out/hypothesis_v3_sonnet46/hypothesis_states.ABORTED_TRANSPORT_PREFLIGHT.jsonl
out/hypothesis_v3_sonnet46/TRANSPORT_PREFLIGHT_ABORT_NOTE.md
```

Raw model output was never overwritten by normalized, validated or repaired output.

---

**HYPOTHESIS_SONNET46_V3_BATTERY_COMPLETE**

**Frozen deterministic verdict: SONNET46_HYPOTHESIS_V3 = FAIL**
