# V6.1 PRE-SPEND EXECUTION-DRIVER AMENDMENT

Experiment: `V6.1_GROUNDED_RESEARCH_GENERATOR_EVALUATOR_REPAIR`
Amendment: `v6_1_execution_driver_amendment_v1`
Class: **PRE-SPEND APPARATUS AMENDMENT** (execution apparatus only; no scientific change)
Spend: **$0.00** — zero Converse, zero InvokeModel, zero experimental observations.

---

## 1. Root cause

The frozen V6.1 package contained a complete scientific design (fixtures, packets,
evaluator, metric contracts, execution schedule, exact CountTokens manifest, hard cost
bound) but **no V6.1-bound execution driver**. The only executor,
`research/hypothesis_engine/_execute_v6.py`, is hard-bound to `out/v6` — the immutable,
COMPLETE V6 experiment — and cannot be reused without endangering V6 history. The V6.1
preregistration carried no execution-driver hash, so a human authorization could not bind to
an executable implementation.

A pre-spend execution attempt correctly halted with **`V6_1_EXECUTION_BLOCKED_COST_GUARD`**
because the mandatory prospective cost guard could not be proven from an actual V6.1 driver
that did not exist. This is an **apparatus-completeness defect, not a scientific-result
defect**.

## 2. Prior freeze preserved

The previous V6.1 pre-spend freeze is **untouched** (byte-for-byte). This amendment only
reads it and writes new files. Verified unchanged after the amendment:

| artifact | sha256 (prefix) |
|---|---|
| PREREGISTRATION.json | `93c2374248ec1c2f` |
| EVALUATOR_FREEZE.json | `4fe9c18b3a18f0a4` |
| fixture_selection.json | `557c5f4ea67e29d6` |
| packets_base.json | `d8d86e8a89f440e9` |
| packets_research.json | `0c9e3ddf74d474f1` |
| call_schedule.json | `dc74772778ba9c60` |
| INPUT_TOKEN_MANIFEST.json | `8c2ecae80731c621` |
| EXACT_INPUT_TOKEN_MANIFEST.json | `583593c992743c63` |
| V6_1_STATES.json | `e7056e9227b012ce` |
| arm_isolation_audit.json | `053a42fd03fde45e` |
| pit_audit.json | `1dfebf38f7657311` |
| V6_1_DESIGN_COMPARISON.json | `0ff43c2924464814` |

CHAMPION `data/discovery/pilotC_stat_mixer.json` = `0b8f5ff3dc4ddf15…` — unchanged.

## 3. Files added / changed

**Added (execution apparatus only):**
- `research/hypothesis_engine/_execute_v6_1.py` — the thin V6.1 execution driver
  (`v6_1_execute_v1`), sha256 `3a7f1a85aef695490cb250c9ce247ada7453ab4058c35b8d48d868d4dddd2d9f`.
- `tests/research/hypothesis_oos/test_execute_v6_1.py` — 41 executor tests.
- `research/hypothesis_engine/_freeze_v6_1_execution_driver.py` — the amendment freeze script.

**Added artifacts (new, prior freeze untouched):**
- `out/v6_1/EXECUTION_DRIVER_FREEZE.json` — driver hash + 36 transitive execution-module hashes.
- `out/v6_1/PREREGISTRATION_EXECUTION_AMENDMENT.json` — prior prereg content **plus** an
  `execution_apparatus` block binding the driver path/hash/version. Adds one key; changes nothing else.
- `out/v6_1/DRY_RUN_REPORT.json` — synthetic, zero-inference dry-run report (not a
  model-observation artifact).

**Changed scientific components:** none.

## 4. The driver is a THIN executor (no scientific policy)

It loads fixtures, arms, replicate counts, prompts, packets, treatment, call order,
max_tokens, thresholds, evaluator logic, stop thresholds and self-noise parameters from the
already-frozen V6.1 artifacts. `version_stamp()["defines_scientific_policy"] == False`. It
hardcodes no threshold (`0.05`, `1.645`, `DISCIPLINE_TOLERANCE`, `MIN_PAIRED_FIXTURES`,
`Z_MULTIPLIER` are all absent). Requests are built only by the frozen
`v6_token_count.canonical_converse_request`; the verdict is `v6_1_verdict.final_verdict`,
run separately (never recomputed in the driver). If a required execution value is not frozen,
the driver raises `MissingContractError` rather than inventing it.

## 5. Guarantees proven

- **Path isolation.** `assert_v6_1_paths` requires `experiment_id` startswith `V6.1`, output
  under `out/v6_1`, and NOT under `out/v6`. Every write is guarded by
  `assert_write_target_is_v6_1`. Non-V6.1 ids, `out/v6`, `out/v6/execution`, and arbitrary
  dirs all raise `PathSafetyError`.
- **Prospective cost guard.** Before every paid call:
  `accounted_spend + frozen max_request_cost_usd(next) <= hard_ceiling_usd`, checked BEFORE
  `client.converse()`. Breach → `V6_1_STOP_COST_CEILING` (APPARATUS), zero further spend.
  There is exactly **one** `client.converse(**request)` call site (line 337), and the
  statement immediately before it is `request = verify_request_binding(...)`.
- **No retries.** Client built by `v6_transport.build_client()` (total_max_attempts=1);
  `assert_no_retries` proven on the live client before the first request; a retry-enabled
  client aborts at $0.
- **Raw before adjudication.** `call_once` writes and hashes the raw response before
  returning; adjudication runs only after. A raw-persistence failure →
  `V6_1_STOP_RAW_PERSISTENCE`, no adjudication.
- **Schedule fidelity.** 36 frozen calls consumed verbatim; schedule↔token-manifest identity
  join verified; canonical request hash re-derived and compared to the frozen manifest per
  call; duplicate index rejected; missing manifest entry → `V6_1_STOP_TOKEN_MANIFEST_MISSING`.
- **Terminal state.** After COMPLETE/STOPPED/ABORTED, no further call is permitted
  (`TerminalStateError`).

## 6. Cost bound revalidation (unchanged)

Recomputed from the frozen manifests: total exact input tokens **1,312,305**, total max
output tokens **294,912**, hard maximum **$8.52**, max billable attempts **36**. Adding the
executor did not change any token count or request byte. The driver's dry-run worst-case
total equals **$8.52 ≤ $8.52**.

## 7. Reproducibility (PYTHONHASHSEED 1 / 2 / 3 / 12345)

Byte-identical across all four seeds:
- driver sha256 `3a7f1a85…`
- dry-run report content hash `7292565a…`
- execution-module manifest hash `0dd0f144…` (36 modules)

The underlying frozen fixture selection, packets, schedule and token manifest were verified
stable (the dry-run reverify passed identically under every seed).

## 8. Hostile final audit

Every forbidden path was attempted and **blocked**: target V6, write into `out/v6`, bypass
the cost guard, retry a billed call, alter scheduling (duplicate index), rebuild treatment
(tampered packet → request-hash mismatch), skip the request-hash check (single guarded call
site), adjudicate before raw persistence, continue after a terminal stop, and generate an
extra call beyond the frozen 36.

## 9. Tests

Full `tests/research/hypothesis_oos/` + `tests/research/hypothesis_engine/`:
**846 passed, 0 failed, 0 skipped, 0 xfail** (805 prior + 41 new executor tests). No
unconditional skips or xfails concealing failures.

## 10. Authorization

The previous spend authorization was bound to a package without an executor and is treated
as **EXPIRED / UNCONSUMED**. This amendment authorizes creation, testing, audit, hashing and
freezing of the execution apparatus only. It does **NOT** authorize paid execution. Fresh
explicit human authorization, bound to the driver hash
`3a7f1a85aef695490cb250c9ce247ada7453ab4058c35b8d48d868d4dddd2d9f`, is required.

**Spend state:** `CONVERSE_CALLS = 0`, `INVOKEMODEL_CALLS = 0`,
`EXPERIMENTAL_OBSERVATIONS = 0`, `SPEND = $0.00`, `SPEND_AUTHORIZATION = REQUIRED`.

**STOP at `V6_1_SPEND_AUTHORIZATION_REQUIRED`.**


---

# AMENDMENT v2 — UNKNOWN-AFTER-SEND BILLING ACCOUNTING

Amendment: `v6_1_execution_driver_amendment_v2`
Class: **PRE-SPEND APPARATUS AMENDMENT** (runtime cost accounting only; no scientific change)
Spend: **$0.00**.

## Verdict

**V6_1_UNKNOWN_BILLING_ACCOUNTING_FIXED_AND_REFROZEN**

## Root cause (what "35 charged" meant)

In v1 the driver's cost accounting used the frozen `v5a2_transport.TransportAccounting`, where:
- `record_transport_failure` records `charged: False` and adds **nothing** to `spend_usd`;
- `would_exceed_ceiling(p)` returns `(spend_usd + p) > ceiling`, using **only confirmed usage**.

So a request that entered `client.converse()` and then raised (Bedrock may have accepted and
billed it) contributed **$0** to the next-call guard. In the lost-response test, "35 charged"
meant 35 confirmed-usage calls; the 1 lost-after-send call was accounted as **zero exposure** —
a conservative-accounting violation. The global $8.52 structural cap (36 attempts × frozen
maxima) still held, but the runtime guard's own arithmetic was unsound.

## Fix (apparatus only, in the driver)

The frozen shared module `v5a2_transport.py` was **not** modified (it is used by immutable V6).
The correction lives entirely in `_execute_v6_1.py`:

- New billing states: `NOT_SENT` (zero exposure), `CONFIRMED` (actual usage), `UNKNOWN_AFTER_SEND`
  (reserves the request's **frozen maximum**, never released).
- New local accumulator `unresolved_reserved_exposure`.
- Guard (before every `client.converse()`):
  `confirmed_actual_spend + unresolved_reserved_exposure + frozen_max(next) <= HARD_MAX_COST`.
- On post-send failure (`except Exception`): add the frozen max to `unresolved_reserved_exposure`,
  record `UNKNOWN_AFTER_SEND` in a billing ledger with transport evidence (request hash, send ts,
  exception, no_retry), no fabricated model response.
- Raw-persistence failure now accounts **confirmed** cost (the response was received = billed),
  never zero.
- `RequestHashMismatch` (raised before `converse`) stays `NOT_SENT`, zero exposure.
- Reporting separates `confirmed_provider_cost_usd`, `unknown_after_send_max_exposure_usd`,
  `conservative_accounted_exposure_usd`, `hard_ceiling_usd`.

## Accounting state machine

```
NOT_SENT            paid method never entered (guard trip / hash mismatch / missing manifest)  -> $0
CONFIRMED           converse() returned usage                                                  -> actual cost (<= frozen max)
UNKNOWN_AFTER_SEND  converse() entered then raised; billing unknowable; NO RETRY               -> frozen max reserved, never released
```

## Cost-guard formula (before every request)

```
confirmed_actual_spend + unresolved_reserved_exposure + frozen_max_request_cost(next) <= $8.52
```

## Lost-response worked example (seq 1, frozen max $0.18)

send → converse() raises → `UNKNOWN_AFTER_SEND` → `unresolved_reserved_exposure += $0.18`
(never released, no retry). Next call's budget = `$8.52 − confirmed − $0.18 − next_max`. Verified:
confirmed $0.03675, unknown exposure $0.18, conservative $0.21675 ≤ $8.52.

## Worst-case proof (AUDIT 5)

Sum of all 36 frozen per-request maxima = **exactly $8.52** (Decimal). Each `UNKNOWN_AFTER_SEND`
reserves exactly its frozen max; there are 36 requests, one billable attempt each, no retries,
no calls outside the 36. Therefore even if every attempt became `UNKNOWN_AFTER_SEND`, total
reserved exposure ≤ $8.52. (In practice the frozen transport stop fires at 3 consecutive
failures, capping earlier.)

## Driver hash status

- Old: `v6_1_execute_v1` — `3a7f1a85aef695490cb250c9ce247ada7453ab4058c35b8d48d868d4dddd2d9f`
- New: `v6_1_execute_v2` — `847fe1c4e471a9fa62715e5aba8180cd8c230eb6bcf359416b7b6e1acc9aad12`

Execution-driver freeze and amendment prereg regenerated; prior freeze untouched;
36 execution-module deps re-bound.

## Tests

`test_execute_v6_1.py`: **61 passed** (41 prior + 20 new `TestUnknownBillingAccounting`, covering
AUDIT-10 items 1–20). Full `hypothesis_oos` + `hypothesis_engine`: **866 passed, 0 failed, 0
skipped, 0 xfail**.

## Reproducibility

Byte-identical across PYTHONHASHSEED 1/2/3/12345: driver `847fe1c4`, dry-run content `d6b7f9e7`.

## Scientific hashes / CHAMPION / frozen transport

All scientific artifacts unchanged (PREREGISTRATION `93c23742`, EVALUATOR_FREEZE `4fe9c18b`,
fixture_selection `557c5f4e`, packets, schedule `dc747727`, token manifests `8c2ecae8`/`583593c9`).
CHAMPION `0b8f5ff3` unchanged. Frozen shared `v5a2_transport.py` `368224b9` **unchanged** (not
edited). Cost bound unchanged (1,312,305 / 294,912 / $8.52 / 36).

## Spend state

`CONVERSE_CALLS = 0`, `INVOKEMODEL_CALLS = 0`, `EXPERIMENTAL_OBSERVATIONS = 0`,
`SPEND = $0.00`, `SPEND_AUTHORIZATION = REQUIRED`. Fresh human authorization, bound to driver
hash `847fe1c4…`, required.

**STOP at `V6_1_SPEND_AUTHORIZATION_REQUIRED`.**
