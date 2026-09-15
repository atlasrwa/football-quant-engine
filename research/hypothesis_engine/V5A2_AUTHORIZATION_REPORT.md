# V5A2_FINAL_INTERFACE_CLOSURE — Final Report and Authorization Request

**ZERO SPEND.** No Bedrock call, no LLM call, no network call was made in this task.
**This report does not authorize spend.**

---

## 1. Read this first: the cost ceiling changed, and why

| | V5A.1 (authorized) | V5A.2 |
|---|---|---|
| expected | $6.83 | **$7.04** |
| p90 | $7.18 | **$7.53** |
| **hard ceiling** | **$7.69** | **$9.22** |
| calls | 38 | 38 |

Expected and p90 both still fit under the previously authorized $7.69. **The ceiling does
not**, and the reason is a defect, not a change of plan.

**D6 — V5A.1's "hard ceiling" was not a bound.** It was computed assuming 4,096 output
tokens per call, while the request itself set `max_tokens = 8192`. A run could legally have
produced twice the output the ceiling priced. This is not theoretical: of the six calls
V5A.1 actually made, **three exceeded 4,096 output tokens** (4,329 / 4,729 / 5,232). The
ceiling was not breached only because input tokens came in below estimate.

V5A.2's ceiling uses the request's real `max_tokens`, so **$9.22 is a true worst case** —
every call maxing out its output budget. The honest summary:

> The previously authorized ceiling was not a bound. This one is, and it is ~20 % higher.

The expected cost is the number that should drive the decision; the ceiling is the number
that must not be exceeded. Both are now computed from **V5A.1's observed token counts** (the
one thing its six paid calls bought: real per-arm tokens-per-byte, 0.3725 base / 0.4247
research) rather than a chars/4 proxy.

## 2. What was wrong, and what was done

| ID | Defect | Status | Regression test |
|---|---|---|---|
| D1 | packet said `opponent_profile_response`, schema's dimension enum said `opponent_profile`, capability enum wanted `competition` — three namespaces, no stated relationship. Killed 2 of 6 paid calls, discarded 24 hypotheses unread. | **closed** — one ontology, all three surfaces projected from it | `test_d1_regression_advertised_capability_term_is_accepted` |
| D2 | validator rejected `INSUFFICIENT_EVIDENCE` + evidence refs; no prompt, schema or packet ever said so. 6 rejections. | **closed** — §5 preferred contract, stated in the prompt | `test_abstention_may_cite_valid_evidence` |
| D3 | one `venue` term meant both "the fixture has a home side" and "split prior matches by venue", making 30 base-arm rejections uninterpretable. | **closed** — split into two terms; **rejection preserved** | `test_d3_preserved_venue_conditioning_still_rejected_in_base_arm` |
| D4 | boto3 1.34.46 has no `converse`; the requirement lived in prose and nothing checked. Burned the authorized window on 3 AttributeErrors. | **closed** — asserted preflight at $0.00 | `test_transport_preflight_rejects_client_without_converse` |
| D5 | prose firewall caught `"probability of 0.62"` but not `"a 0.62 probability"`. Present since V2. | **closed** — `firewall_v4`, strictly additive | `test_d5_numeric_probability_claim_in_prose_is_blocked` |
| D6 | cost ceiling assumed 4,096 output tokens against a `max_tokens` of 8,192. | **closed** — ceiling uses the real bound | §1 above |

Plus two latent defects found while re-surfacing the packet: `competition` was advertised as
conditionable in an arm with **no competition data anywhere**, and the blinding audit
substring-matched `control` inside *"not a controlled comparison"*. Both closed.

**D5 and D6 were found by this iteration, not by the live run.** The generated battery found
D5 on its first pass; D6 fell out of recomputing the cost model.

## 3. Evidence that the closure holds

| Check | Result |
|---|---|
| generated surface cases | **3,680**, **0 violations** |
| advertised term returning `SCHEMA_INVALID` | **0** |
| `INFRASTRUCTURE_CONTRACT_FAILURE` anywhere | **0** |
| `MODEL_VISIBLE_ENUM_COVERAGE` | **121/121 = 100 %** |
| round-trip broken terms | **0 / 20** |
| evidence differences vs frozen V5A.1 | **0 / 20 packets** |
| arm identity leaks / treatment labels | **0 / 0** |
| PIT problems | **0** |
| evaluator paths exercised | **14, 0 failures** |
| byte reproducibility at seeds 1/2/3/12345 | **identical** |
| tests | **127 passing** (44 new, 47 V5A.1 inherited, no regressions) |

Human walkthrough, 7 hypothesis types × both arms: base **2/7** accepted (unconditioned +
abstention), research **7/7**. Every base rejection names the term the model wrote and the
state the packet declared for it.

## 4. What this does NOT claim

- **It does not claim Sonnet will pass.** The goal was never that. The apparatus is now
  coherent enough that a failure will be about the research approach rather than about our
  plumbing — and the experiment is allowed to fail.
- **No synthetic result here is evidence about any model.** The synthetic responses were
  written by the same process that wrote the validator, so they cannot show the contract is
  *discoverable* from the packet. That is precisely what the paid experiment tests.
- **The base arm now declares zero conditionable terms.** This is the honest description of
  a summary-only packet. The four availability-aware dimensions (`venue_use`,
  `recent_vs_long_use`, `opponent_profile_use`, `formation_use`) are therefore structurally
  zero in the base arm — they are **within-research-arm descriptives, not cross-arm
  comparisons**, and must not be read as findings about the model. The primary metric
  `grounded_accepted_n` is unaffected: both arms share a 12-hypothesis ceiling and the base
  arm can fill it with unconditioned questions.
- **No downstream promotion.** No predictive coefficients, candidate features, OOS search,
  thresholds or prospective predictions. Nothing here may reach `p_model` or CHAMPION.

## 5. Thresholds: what moved and what did not

**Unchanged from V5A.1, deliberately** — these predate its run and are therefore unreachable
by anything it revealed: `PRIMARY_METRIC = grounded_accepted_n`, `DISCIPLINE_TOLERANCE =
0.05`, `MIN_SELF_NOISE_FLOOR = 0.5`, the PASS/MIXED/FAIL gate, the **0.30** schema-invalid
rate, 3 consecutive transport failures, and the cost-ceiling rule.

**Reviewed as §15 requires — the 0.30 rule stands.** It fired correctly in V5A.1 given what
it could see; the defect was the numerator, not the number. Its numerator is now MODEL
failures only, and apparatus failures get their own **stricter** rule (halt on the first
one). The `≥ 6 calls` guard is made explicit rather than changed — V5A.1's rule was first
evaluated at 6 calls, so 6 is what it always was.

**New (a distinction, not a relaxation):** the evaluability gate — 8 paired fixtures, 8 valid
responses per arm, 3 repeatability groups per arm. Chosen from what a paired comparison
needs. V5A.1 is `NON_EVALUABLE` under it on all five counts, which is the correct description
of what happened to it.

## 6. §31 hard-stop checklist

| Condition | Status |
|---|---|
| any model-visible term not declared in the packet | **none** (20/20 declared, every packet) |
| any advertised term rejected as `SCHEMA_INVALID` | **none** (0 / 3,680) |
| any enum member never exercised | **none** (121/121) |
| any round-trip failure | **none** (0/20) |
| evaluator incomplete or unexercised | **complete**, 14 paths, 0 failures |
| evaluator not frozen before first paid call | **frozen** at $0.00 |
| transport preflight absent from the execution path | **present**, asserted at $0.00 |
| frozen module modified (V2/V3/V5A/V5A.1/CHAMPION) | **none** (17 upstream hashes recorded + re-verified) |
| artifacts not byte-reproducible | **reproducible** at 4 seeds |
| PIT or leakage problem | **none** |
| arm isolation broken / treatment label visible | **none** |
| any test failing | **none** (127 passing) |

## 7. Execution plan being requested

```
model        us.anthropic.claude-sonnet-4-6    temperature 0.0    max_tokens 8192
schema       hypothesis_set_schema_v3          forced toolChoice
calls        38  =  10 fixtures × 2 arms  +  3 fixtures × 2 arms × 3 repeats
prompt       v5a2_prompt_v1, byte-identical across arms
```

Before the first paid call, at $0.00, the driver re-verifies all module hashes (including 17
frozen upstream modules), the schema content hash, all 38 packet hashes **and** serialized
request byte hashes, the CHAMPION artifact, and the transport preflight. Any failure aborts
at zero spend. Each raw response is written to disk **before** it is scored.

`_execute_v5a2.py` refuses to run without `--i-have-authorization`. It is already written and
hashed into the preregistration, so the authorization covers a known driver.

## 8. Artifacts

```
out/v5a2/PREREGISTRATION.json          ba873841ce3d58ad
out/v5a2/EVALUATOR_FREEZE.json         b1dc1e2e18635ab6
out/v5a2/packets_base.json             b18029e1d46105a1
out/v5a2/packets_research.json         2718516026851460
out/v5a2/surface_battery.json          d480407d0e5708b9
out/v5a2/roundtrip_audit.json          fb49caa73618180d
out/v5a2/availability_audit.json       300b61f01f301223
out/v5a2/evidence_identity_audit.json  e384ac9064d38b42
out/v5a2/arm_isolation_audit.json      8c660696c80c39b0
out/v5a2/pit_audit.json                a15485ebc8822d28
out/v5a2/ontology_snapshot.json        37f77f9303e2156d
out/v5a2/evaluator_exercise.json       18273550222afd2f
out/v5a2/walkthrough.json              a3ed6d41d59f7a23
```

Reports: `V5A2_FINAL_INTERFACE_DESIGN.md`, `V5A2_PACKET_SURFACE_CONTRACT_AUDIT.md`,
`V5A2_SYNTHETIC_RESPONSE_COVERAGE.md`, `V5A2_EVALUATOR_FREEZE_REPORT.md`,
`V5A2_TRANSPORT_PREFLIGHT_REPORT.md`, `V5A2_FULL_PACKET_AUDIT.md`.

---

## Final states

```
V5A2_INTERFACE_CONTRACT_VALIDATED
V5A2_PACKET_SCHEMA_ROUNDTRIP_VALIDATED
V5A2_SYNTHETIC_SURFACE_COVERAGE_100_PERCENT
V5A2_EVALUATOR_FROZEN
V5A2_TRANSPORT_PREFLIGHT_VALIDATED
V5A2_FULLY_PREREGISTERED
V5A2_SPEND_AUTHORIZATION_REQUIRED
```

**Requested authorization:** $9.22 hard ceiling, $7.04 expected, $7.53 p90, 38 calls.
The previously authorized $7.69 does not cover the true worst case; a re-authorization at
$9.22, or an explicit instruction to cap lower and accept a mid-run cost stop, is required
before any call is made.

**STOP. No Bedrock call has been made. Explicit human authorization is required.**
