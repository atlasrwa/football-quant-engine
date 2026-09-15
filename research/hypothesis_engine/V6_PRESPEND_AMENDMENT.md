# V6_PRESPEND_AMENDMENT.md — Amendment 1

**Experiment:** V6_GROUNDED_RESEARCH_GENERATOR
**Amendment date:** 2026-09-14 (pre-spend)
**Nature:** Legitimate pre-data hardening. NOT a post-hoc rescue.

---

## 0. Confirmation of pre-data status

At the time of this amendment:

- **Zero Bedrock/model API calls had occurred.** No `_execute_v6.py` run had been
  performed; `out/v6/execution/` did not exist.
- **Zero experimental outcomes had been observed.** No `scores.json`, no
  `execution_summary.json`, no adjudicated paid response existed.
- `spend_usd = 0.0` in every artifact.

Because there is no observed result, correcting a defect now cannot change any conclusion —
there is no conclusion yet. This is exactly the window in which the governing prompt permits
pre-spend correction, and the amendment does not touch any V3/V4/V5A/V5A.1/V5A.2 result,
does not modify CHAMPION, and does not weaken any scientific threshold.

---

## 1. Prior frozen state (preserved as historical evidence)

The pre-amendment freeze is preserved verbatim under:

```
research/hypothesis_oos/out/v6/prespend_freeze_pre_amendment_v1/
    PREREGISTRATION.json      sha256 b0ac30920e07dc886d207e5c3552267b67dd9c6bc196b6dc8c5e0fcfa3f62c24
    EVALUATOR_FREEZE.json      sha256 91d63edf9b1275c20d215ed9420f95d223afa2b563a97efaa6113593498c30e1
    V6_STATES.json             sha256 e38a1787b1e50fdccc55c69e5be5d56176afd7e269c534cf99d66c09993044b8
```

It is not overwritten. The new freeze sits alongside it in `out/v6/`.

---

## 2. Defect discovered

**AUDIT 12 — COST HARD CEILING — severity HIGH.**

`hard_ceiling_usd = $8.7961` was computed as `36 logical calls × max_tokens output`, and
`cost_model["hard_ceiling_is_a_true_bound"]` asserted it was a worst-case bound. It was not
a bound on **billable** cost, because a "call" in the billing sense is a **billable
attempt**, not a **logical call**, and nothing in the frozen apparatus forced those two to
be equal:

- The intended execution path (mirroring `_execute_v5a2.py`) constructs the client with a
  bare `boto3.client("bedrock-runtime", ...)` and **no `botocore.config.Config`**.
- The default retry mode for that client is `legacy` (**up to 5 total attempts**) and the
  default `read_timeout` is **60 s**.
- A Bedrock `Converse` call the server **accepts and bills**, but whose response body is not
  read within the timeout (plausible at `max_tokens = 8192`), raises `ReadTimeoutError`,
  which botocore **retries** — producing a **second billed generation for one logical
  call**.
- Worst case, one logical call could bill up to 5×, so the true worst-case billable spend
  was up to `5 × $8.7961`, not `$8.7961`.

The §37 hard-stop `hard_ceiling_not_a_bound` in `_v6_states.py` checked only the **prose**
of the claim (`"yes" in pre["cost_model"]["hard_ceiling_is_a_true_bound"]`), so it would
pass on the *sentence* while the *mechanism* was absent.

## 3. Why it matters scientifically / operationally

This is precisely the class of failure the project itself names as **D4**: *"a requirement
that is not asserted is not a requirement."* The V5A.1 authorization window was consumed by
an unasserted environment requirement. Here, the spend bound was an **estimate wearing a
bound's label**. Because V6's stop rules and authorization gate rest on the ceiling being a
true bound, an unbounded retry multiplier could breach the authorized spend envelope during
a real run. It does not affect the scientific endpoint, but it affects the spend guarantee
the human authorizes against — so it must be closed before authorization.

## 4. Fix (Option B — retries disabled, §28)

Retries are **disabled** for the experiment, so one logical call is at most one billable
attempt and `n_calls` billable attempts is a true worst case. The policy is a property of
the constructed client object, asserted at zero spend, not a sentence in a report.

### Exact rule changed

- **Before:** `hard_ceiling_usd = 36 × max_tokens`, claimed a bound; ceiling-is-a-bound
  hard-stop checked prose only; client built with default (retry-enabled) config; no
  execution driver existed.
- **After:** retries disabled on the frozen client (`total_max_attempts = 1`); the
  ceiling-is-a-bound hard-stop verifies the **mechanism**
  (`max_billable_attempts_per_call == 1` **and** `max_billable_attempts_total ==
  n_calls_total` **and** `transport_retry_policy.policy == "retries_disabled"`); a frozen
  execution driver `_execute_v6.py` constructs the client via `build_client()` and aborts
  at $0 if the client can retry.

### Files changed

| File | Change |
|---|---|
| `src/research/hypothesis_oos/v6_transport.py` | `v6_transport_v1 → v6_transport_v2`. Added `MAX_BILLABLE_ATTEMPTS_PER_CALL=1`, `READ_TIMEOUT_SECONDS=900`, `CONNECT_TIMEOUT_SECONDS=20`, `TRANSPORT_CONFIG_KWARGS`, `build_client()`, `client_max_attempts()`, `retry_policy_report()`, `assert_no_retries()`, `RetryPolicyViolation` (subclass of `TransportPreflightFailure`). `preflight()` now asserts no-retries on the constructed client. `version_stamp()` extended. |
| `research/hypothesis_engine/_freeze_v6.py` | `cost_model` gains `max_billable_attempts_per_call`, `max_billable_attempts_total`, `transport_retry_policy`; `hard_ceiling_is_a_true_bound` now states the retries-disabled mechanism. `_execute_v6.py` added to the frozen `MODULES` list. |
| `research/hypothesis_engine/_v6_states.py` | `hard_ceiling_not_a_bound` now delegates to `_hard_ceiling_not_a_bound(pre)`, which checks the numeric mechanism rather than the prose. |
| `research/hypothesis_engine/_execute_v6.py` | **New** frozen execution driver. Refuses to run without `--i-have-authorization`; reverifies all frozen hashes at $0; builds the no-retry client and runs preflight (which asserts no-retries); consumes the frozen flat schedule verbatim; guards cost before each call; writes raw responses before scoring; uses `v6_stop.classify_stop`; keeps EXECUTION_STATUS and SCIENTIFIC_VERDICT separate. |
| `tests/research/hypothesis_oos/test_v6_prespend.py` | +8 regression tests (see §6). |

**No scientific threshold, denominator, gate order, self-noise formula, discipline
tolerance, schedule, or evaluability minimum was changed.** The dollar ceiling value is
**unchanged** ($8.7961): the fix makes the existing number honest, it does not inflate it.

## 5. New frozen hashes (post-amendment)

```
PREREGISTRATION.json   6c34a4883c691dfbc5dc91ecd5ac30a3179ea1132b7862d11b0ae9f2c575adc9
EVALUATOR_FREEZE.json   d0c78442df6d63fba5a1fd83d0d5ad80d84691ae2da1c039e8b427032690d71c
V6_STATES.json          4c95308fd3a65d73cada38660b6db9d8b51a06fa49e5e20c3607717a4dbb2959
v6_transport.py         80a10b4a0c78af9898a0319aeb3e3c2e6588c8eddeeb05c3f66b4f9e551fc3a1
```

Batteries (`adversarial_battery.json`, `synthetic_mutation_battery.json`,
`call_schedule.json`, `packet_identity_audit.json`, `arm_isolation_audit.json`,
`pit_audit.json`) are **byte-identical to the pre-amendment build** — proof the transport
change did not touch adjudication.

## 6. Test results

- V6 pre-spend suite (`test_v6_prespend.py`): **48 passed** (was 40; +8).
- Full V6 + engine suite in the pinned venv: **683 passed, 0 failed** (was 675; +8).
- New tests: `test_transport_preflight_rejects_retry_enabled_client`,
  `test_build_client_disables_retries`,
  `test_unknown_client_retry_config_is_treated_as_unbounded`,
  `test_hard_ceiling_prices_max_tokens_on_every_call`,
  `test_hard_ceiling_is_a_billable_bound_only_because_retries_are_disabled`,
  `test_states_ceiling_hardstop_checks_mechanism_not_prose`,
  `test_final_call_boundary_refuses_to_start_an_unaffordable_call`,
  `test_retry_cost_boundary_one_logical_call_bills_once`.

## 7. Reproducibility

`PREREGISTRATION.json`, `EVALUATOR_FREEZE.json`, and `V6_STATES.json` rebuild
**byte-identically** under `PYTHONHASHSEED = 1, 2, 3, 12345`:

```
seed=1      PREREG=6c34a4883c691dfb  EVAL=d0c78442df6d63fb  STATES=4c95308fd3a65d73
seed=2      PREREG=6c34a4883c691dfb  EVAL=d0c78442df6d63fb  STATES=4c95308fd3a65d73
seed=3      PREREG=6c34a4883c691dfb  EVAL=d0c78442df6d63fb  STATES=4c95308fd3a65d73
seed=12345  PREREG=6c34a4883c691dfb  EVAL=d0c78442df6d63fb  STATES=4c95308fd3a65d73
```

## 8. CHAMPION isolation

CHAMPION artifact unchanged: `pilotC_stat_mixer.json` sha256
`0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9` (matches frozen). No V6
module imports into a CHAMPION prediction path and vice versa; 22/22 architecture-isolation
tests pass in the pinned venv.

## 9. Final state

All §38 states re-emitted; `any_hard_stop = False`; run ends at
**V6_SPEND_AUTHORIZATION_REQUIRED**. This amendment does **not** authorize spend and does
**not** make any Bedrock call.
