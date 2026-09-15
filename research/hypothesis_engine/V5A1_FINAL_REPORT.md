# V5A.1 Final Report — Execution Stopped by Preregistered Stop Rule

**Experiment:** `V5A.1_FULL_FIDELITY_EVIDENCE_INTERFACE`
**Date:** 2026-09-14 · **Authorized ceiling:** $7.6947 · **Actual spend:** **$0.9084**
**Calls authorized:** 38 · **Calls completed:** **6** · **Stopped by:** `V5A1_EXECUTION_STOPPED_SCHEMA_INVALID_RATE` (2/6 > 0.30)

Machine-readable record: `research/hypothesis_oos/out/v5a1/execution/`
(`execution_log.jsonl`, `raw/`, `execution_summary.json`, `evaluation_results.json`,
`FROZEN_EXECUTION_RESULTS.json`).

---

## 1. Exact final hashes

| artifact | sha256 | state |
|---|---|---|
| `PREREGISTRATION.json` | `02d19e84f498f90a98f908336ce63dda4469693a38d871184d3d1dcfb74985d1` | **unchanged** |
| `packets_base.json` | `e321536a8bf8b161b0c28a49342cfc495e5647586bea0744bbcc6cbe47a4bae6` | **unchanged** |
| `packets_research.json` | `646f73e44703443300a7de9f5f2a0b7ee88c5b02c7c650ee1a445a8cae9ac3bf` | **unchanged** |
| `exposure_audit.json` | `8d51c235ac408a6b9d0f0e76ea83c63d06935d5c5649102ea0d72ca1a6817865` | **unchanged** |
| `evidence_id_audit.json` | `1e946ec54bccf787144ce2559259df82e44c1addddabf973ff1793211e6cb9fb` | **unchanged** |
| `ab_isolation_audit.json` | `c636ca3592d10390788426683d678da3c30b652ac3ea7be627674ec4588f0d5d` | **unchanged** |
| `section_position_audit.json` | `0ea1d294f1dec3ec7b03d57e9f8cb34e48e787c19739a61d4a83398e2732555e` | **unchanged** |
| `v5a1_evaluator.py` | `2bdd2365502d52016db217cbc0e6c531632ec15ad9e631e9bb37853741bacf5d` | **unchanged since freeze** |
| `EVALUATOR_FREEZE.json` | `ac5c51071347bf421e34f2a7e42e0b5ca08eb7c82a75aec4d78a745bf2b968d9` | addendum, written at $0 spend |
| CHAMPION `pilotC_stat_mixer.json` | `0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` | **unchanged** |

Every frozen hash captured before the first paid call reverified **UNCHANGED** after
execution. No frozen scientific artifact was modified before, during or after the run.

### Evaluator freeze (declared)

The V5A.1 preregistration froze the rubric **criteria** and the PASS/MIXED/FAIL **wording**
but shipped no evaluator **implementation** and no numeric threshold. Writing one after
seeing responses would have been exactly the tuning the mandate forbids, so `v5a1_evaluator.py`
was written, smoke-tested on synthetic responses, hashed and frozen via `EVALUATOR_FREEZE.json`
**before the first paid call, at `spend_usd_so_far = 0.0`**. Frozen artifacts were not touched;
the addendum is a new file. Its hash is identical before and after execution, and the analysis
driver refuses to score on any drift.

---

## 2. Execution record

| item | value |
|---|---|
| model | `us.anthropic.claude-sonnet-4-6` (resolved id identical) |
| region / API | us-east-1 / Bedrock `converse` with forced `toolChoice` |
| temperature / maxTokens | 0.0 / 8192 |
| calls planned | 38 |
| calls completed | **6** (4 base, 2 research; all on `mt_010243515`) |
| calls never attempted | 32 |
| infrastructure failures | 3 (zero cost, zero model contact) |
| input tokens | 171,542 |
| output tokens | 26,254 |
| **actual cost** | **$0.908436** |
| ceiling | $7.6947 — **never approached, never raised** |
| stop reason | `V5A1_EXECUTION_STOPPED_SCHEMA_INVALID_RATE` — 2/6 > 0.30 |

Every call was verified against its frozen `serialized_request_sha256` and scanned for
treatment labels **before** being sent. No hash drift, no label leak. No retries were
performed — none were preregistered.

---

## 3. Stop-rule status

| preregistered stop rule | status |
|---|---|
| hash mismatch | not triggered |
| PIT leakage | not triggered |
| outcome leakage | not triggered |
| market leakage | not triggered |
| treatment-label leakage | not triggered |
| provenance failure | not triggered |
| **schema-invalid rate > 0.30** | **FIRED — 2/6, execution halted at seq 6** |
| **transport failure > 3 consecutive** | **FIRED once (first attempt, $0), see §4** |
| semantic conflict | not triggered |
| unexpected truncation | not triggered |
| unexplained evidence omission | not triggered |
| cost ceiling $7.6947 | not triggered ($0.9084) |
| duplicate evidence id | not triggered |
| `valid_evidence_ids == 0` | not triggered |

The stop rule is honored exactly as written and is **not** reinterpreted below.

---

## 4. MODEL_BEHAVIOR vs INFRASTRUCTURE_BEHAVIOR

### INFRASTRUCTURE_BEHAVIOR (D4) — resolved, $0

The first execution attempt failed 3 consecutive times with
`AttributeError: 'BedrockRuntime' object has no attribute 'converse'`. The system
interpreter's boto3 is 1.34.46, which predates the Converse API. **No call reached the
model; $0 was spent.** The frozen `> 3 consecutive` rule fired correctly.

Root cause found: `/home/ubuntu/.venv` carries boto3 1.43.93 with Converse — the environment
prior valid Sonnet executions used (V3: 56/56 `COMPLETED`, same region, same account, same
`converse` + `toolConfig` pattern). That interpreter reproduces **every** frozen request hash
and passes all 47 pre-spend tests. Resumption re-sent byte-identical frozen requests; because
no model response had ever been observed, this is resumption after an infrastructure fix, not
a scientific retry. The 3 failure records are preserved immutably in `execution_log.jsonl`.

My zero-spend capability check verified credentials, region and model visibility but
**constructed the runtime client without checking that `converse` existed on it**. That is the
gap that let the V3-style transport incident recur, and it is recorded as a defect against my
own pre-flight, not against the science.

### MODEL_BEHAVIOR — what the 6 completed calls actually show

| seq | arm | rep | hyps | accepted | refs | valid refs | fabricated | whole-response failure |
|---:|---|---:|---:|---:|---:|---:|---:|---|
| 1 | base | 0 | 12 | **0** | 46 | **46** | 0 | — |
| 2 | base | 1 | 12 | 0 | 0 | 0 | 0 | `LATENT_GRADING_VIOLATION` |
| 3 | base | 2 | 12 | **0** | 60 | **60** | 0 | — |
| 4 | base | 3 | 12 | **0** | 53 | **53** | 0 | — |
| 5 | research | 0 | 12 | 0 | 0 | 0 | 0 | `SCHEMA_INVALID` |
| 6 | research | 1 | 12 | 0 | 0 | 0 | 0 | `SCHEMA_INVALID` |

**The evidence interface — the thing V5A.1 was built to fix — worked.** In every base-arm
response that parsed, the model cited 46–60 evidence ids and **every single one resolved**:
`valid_evidence_reference_rate = 1.0`, `fabricated_evidence_rate = 0.0`. The V5A HS-1
failure (zero resolvable ids in the treatment arm, grounded acceptance pinned at zero by the
plumbing) **did not recur**.

Grounded acceptance was nevertheless **0 in both arms**, for three separate reasons — two of
which are interface defects that my pre-spend battery missed.

---

## 5. Defects found during execution

### D1 — `required_capabilities` namespace mismatch · MATERIAL INTERFACE DEFECT · research arm

The packet advertises **dimension** names (`opponent_profile`, `own_formation_family`,
`opponent_formation_family`). `schema_v2`'s `required_capabilities` enum accepts only
**context-source** names (`competition`, `historical_formation`, `venue`, …). The model,
told by the availability map that `opponent_profile` was exposed, wrote
`required_capabilities: ["opponent_profile"]` — and the **entire response** was rejected as
`SCHEMA_INVALID`. Both research-arm calls died this way; 24 hypotheses were discarded.

```
$.hypotheses[1].required_capabilities[0]: 'opponent_profile' not in enum (11 allowed)
$.hypotheses[2].comparison: 'OPPONENT_PROFILE_INTERACTION' not in enum (5 allowed)
```

Nothing in the packet, the prompt or the citation instructions says the two fields use
different namespaces. **Missed by the pre-spend battery** because every synthetic hypothesis
passed either `caps=()` or a correct context-source name — the packet's advertised surface
was never round-tripped through `required_capabilities`.

This is the same *class* of defect V5A.1 existed to eliminate: the packet invites something
the frozen stack cannot express.

### D2 — abstention contract never stated · MATERIAL INTERFACE DEFECT · both arms

`validator._validate_one` rejects an `INSUFFICIENT_EVIDENCE` hypothesis that cites evidence
("an INSUFFICIENT_EVIDENCE abstention must not cite evidence"). The prompt says abstention
is "a correct and valued answer" but never says such a hypothesis must carry **no**
`evidence_refs`. The model abstained *and* cited its reasons — 6 rejections across seq 1, 3, 4.

Missed by the battery because the abstention test constructed empty refs itself, so the
contract was tested but never *communicated*.

### D3 — availability-map compliance · MODEL_BEHAVIOR OBSERVATION · base arm

30 of 36 base-arm hypotheses conditioned on `venue` or used `SUBJECT_VENUE_BASELINE`, and 7
used `LEAGUE_ENVIRONMENT_BASELINE`, against a packet that truthfully declares
`venue_splits = NOT_EXPOSED_IN_PACKET` and a prompt that says to act only on `EXPOSED_TO_LLM`.
The admissibility gate refused all of them: `unsupported_dimension_rate = 1.0`.

This is a **genuine measurement**, not a defect — the gate behaved exactly as designed, and
this is precisely the "unsupported dimension use" the rubric exists to score. But with **3
completed base-arm calls on one fixture** it is **not concludable**, and it is recorded as an
observation only.

### D4 — transport environment · INFRASTRUCTURE · §4 above

---

## 6. Frozen gate table and mechanical verdict

The frozen evaluator was run **exactly once** over the immutable completed response set. Its
hash was verified against `EVALUATOR_FREEZE.json` before scoring. Nothing in the
normalization, evidence-reference rules, meaningful-interaction classifier, groundedness
definition, availability denominators, thresholds, gates or repeatability calculation was
changed.

| gate input | value |
|---|---|
| primary metric | `grounded_accepted_n` (SUFFICIENT + validator-accepted + non-abstention) |
| paired fixtures available | **1** (`mt_010243515`) — 32 calls never ran |
| mean paired difference (research − base) | **0.0000** |
| self-noise pooled SD | 0.0 (base `[0,0,0,0]`, research `[0,0]`) |
| self-noise floor used | 0.5 (`MIN_SELF_NOISE_FLOOR` applied — a zero spread must not manufacture a PASS) |
| compilability delta | 0.0 |
| firewall-clean delta | 0.0 |
| fabricated-evidence delta | 0.0 |
| unsupported-dimension delta | −1.0 |
| discipline degraded | none |

| gate | fires? |
|---|---|
| FAIL (discipline degraded beyond 0.05) | no |
| PASS (mean paired diff > self-noise floor) | no — 0.0000 ≤ 0.5 |
| **FAIL (mean paired diff ≤ 0)** | **YES — 0.0000** |
| MIXED | no |

### Paired fixture result

| fixture | base | research | diff |
|---|---:|---:|---:|
| mt_010243515 | 0 | 0 | **+0** |

### Repeatability baseline

| fixture | arm | n | values | SD |
|---|---|---:|---|---:|
| mt_010243515 | base | 4 | `[0, 0, 0, 0]` | 0.0 |
| mt_010243515 | research | 2 | `[0, 0]` | 0.0 |

The repeats are perfectly consistent — but at zero, so they measure the defects, not model
self-noise. **No usable self-noise baseline was established.**

### Pooled rates (replicate 0)

| metric | base | research |
|---|---:|---:|
| grounded_acceptance_rate | 0.0 | 0.0 |
| valid_evidence_reference_rate | **1.0** | 0.0 (no response parsed) |
| fabricated_evidence_rate | **0.0** | 0.0 |
| unsupported_dimension_rate | 1.0 | 0.0 (no response parsed) |
| firewall_clean_rate | 1.0 | 1.0 |
| abstention_rate | 0.167 | 0.0 |

Every other required metric (meaningful conditionality, meaningful interactions, venue use,
recent-vs-long use, opponent-profile use, formation restraint, baseline diversity,
metric-family diversity, redundancy, evidence specificity) is recorded per call in
`evaluation_results.json`. **All are uninformative**: with 0 accepted hypotheses in both arms
and 32 calls unrun, they measure the defects above, not research behaviour.

---

## 7. Scientific interpretation

**The primary scientific question was not answered, and the mechanical FAIL must not be read
as an answer to it.**

The question was: *does the research arm's additional full-fidelity history increase grounded,
non-degenerate, deterministically measurable, contextually justified hypotheses beyond model
self-noise, without materially reducing discipline?* Answering it requires both arms to be
able to produce admissible hypotheses. In this run:

- the **research arm never produced a parseable response** — both calls died on D1, a schema
  namespace mismatch, before any hypothesis could be scored;
- the **base arm produced 36 well-formed, perfectly grounded hypotheses** (100% valid
  references, 0 fabricated) that were all refused for using a dimension the packet says it
  does not expose (D3) or for citing evidence on an abstention (D2);
- **1 of 10 fixtures** was reached, and **6 of 38 calls**.

So the mechanical verdict is **FAIL**, and it is a faithful application of the frozen gate to
the data that exists — but what it measures is the **interface**, not the science. The
comparison is degenerate: 0 versus 0, on one fixture, with the treatment arm structurally
unable to return a response.

**What this run does establish, positively:** the V5A HS-1 fix works in live use. The common
evidence interface resolved 159 model-authored citations with zero fabrications across three
calls. That was the central defect of the aborted V5A and it did not recur. The firewall
caught a real latent-grading violation (`home_advantage` in `candidate_confounders`). Cost
control, blinding and hash integrity all held.

**What it also establishes:** V5A.1's pre-spend battery, though it grew to 47 tests, did not
round-trip the packet's own advertised surface through every field of the frozen output
schema. D1 and D2 are both instances of the same gap — a contract the packet implies but never
states, and that no synthetic test exercised the way a model would.

---

## 8. Negative-result and non-promotion compliance

Per the mandate's negative-result rule, **the result is preserved as it stands**. I have not
changed history depth, summary density, prompt ordering, opponent-profile bands, interaction
instructions or thresholds, and I have not re-run, repaired or regenerated any call.

Per §33 (*"If a defect is found afterward: ABORT V5A.1. Do not repair frozen artifacts."*),
two material interface defects were found after the freeze.

**Recommendation: `ABORT_V5A1_CURRENT_VERSION`.** A new preregistered version is required.
Fixing D1 or D2 means changing either the packet's advertised surface, the prompt's stated
contract, or the frozen schema — each of which moves a preregistered hash, which is a new
version by definition, not a repair.

| confirmation | status |
|---|---|
| V2 / V3 / V4 artifacts unchanged | **confirmed** — 532 frozen engine tests pass; every module hashed in the V5A freeze byte-identical |
| V5A (aborted) artifacts unchanged | **confirmed** — 6 files, original hashes |
| CHAMPION unchanged | **confirmed** — `0b8f5ff3…c00c9` |
| `p_model` untouched | **confirmed** — no V5A.1 module imports or references it |
| no feature promotion | **confirmed** — no CHAMPION feature created, no cohort tuned, no similarity rule changed, no hypothesis promoted |
| V5B not run | **confirmed** |
| no predictive effects estimated | **confirmed** |
| no OOS search run | **confirmed** |
| frozen artifacts modified | **none** |

---

## 9. What a V5A.2 must carry (recorded, not implemented)

1. A single capability namespace, or an explicit in-packet mapping from every advertised
   dimension to the `required_capabilities` value the schema expects — plus a pre-spend test
   that round-trips **every** advertised dimension through **every** schema field.
2. The abstention contract stated in the prompt: an `INSUFFICIENT_EVIDENCE` hypothesis carries
   no `evidence_refs`.
3. A transport pre-flight that asserts the *operation exists on the client* (`hasattr(client,
   "converse")`) and pins the interpreter, not merely that credentials and the model resolve.
4. A pre-spend battery whose synthetic hypotheses are generated **from the packet's own
   advertised surface**, rather than hand-written — the gap that let D1 and D2 through.
5. D3 (availability-map compliance) is a legitimate research question and should be measured
   on its own terms, with enough calls to be concludable.

---

**V5A1_EXECUTION_COMPLETE**

**V5A1_VERDICT: FAIL**

*(Mechanical, per the frozen gate: mean paired `grounded_accepted_n` difference 0.0000 ≤ 0,
no discipline degradation. Scientifically this verdict reflects two post-freeze interface
defects and a battery stopped at 6 of 38 calls — not a measured answer to the primary
question. Recommendation: `ABORT_V5A1_CURRENT_VERSION`.)*
