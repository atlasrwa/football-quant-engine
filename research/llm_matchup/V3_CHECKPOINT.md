# V3 Checkpoint — Identity-Neutral LLM Evidence Processing

**This is an ENGINEERING checkpoint, not a scientific freeze.** No `FREEZE_LLM_MATCHUP_V3`
exists and none should be created until the sequence in §13 completes. `LLM_MATCHUP_V2`
(preserved, failed generation) and Phase C are both untouched.

```
ENGINEERING STATUS:                         PASS
SERIALIZED REQUEST IDENTITY AUDIT:          PASS on tested real packets
LIVE SMOKE STATUS:                          INCOMPLETE — AWS DAILY TOKEN QUOTA
SCIENTIFIC IDENTITY-NEUTRALITY VALIDATION:  NOT YET ESTABLISHED
PHASE C ELIGIBILITY:                        NO / LOCKED
FINAL V3 RECOMMENDATION:                    PENDING LIVE CONTROLS
```

## 1. Starting repository state (documented before any change)

```
branch: feat/model-oos-benchmark
HEAD:   224aef608f501496a06a7231401ee5706486890f
```

`git status --short` at the start of this checkpoint task showed the same pre-existing
unrelated working-tree state as every prior turn in this session (modified `data/` JSONL/JSON
files from other ongoing pipelines, and a long list of untracked dotfiles/tool directories
belonging to the environment, not this research). None of that was touched, staged, or
inspected further. `research/llm_matchup/` and `src/research/llm_matchup/` (both untracked
before this checkpoint) and the new test files are the only paths this checkpoint commits.

## 2. What "4 completed evaluations" actually means

Precise denominators (do not conflate infrastructure censorship with semantic failure):

| Quantity | Count |
|---|---|
| Fixtures in the frozen golden_v3 manifest | 20 |
| **Completed semantic evaluations** (a real Bedrock response was received and run through validator_v3) | **4** |
| **Accepted among completed evaluations** | **4 / 4 (100%)** |
| Validator rejects among completed evaluations | 0 |
| Remaining intended evaluations, infrastructure-censored (`AWS_DAILY_TOKEN_QUOTA`) | 16 |
| Of those 16, fixtures with a `READ_TIMEOUT` recorded on an earlier attempt (see §7) | 1 (`mt_584193286`) |
| Requests infrastructure-censored before their literal serialized text could be checked | 0 — the leak audit runs client-side before transmission, so all 20 were audited regardless of outcome |

**"4/20" is never reported as a 20% pass rate anywhere in this checkpoint.** The correct
statement is: 4 completed evaluations, 4/4 accepted, 16 not yet evaluated due to an external
quota, 0 evidence of semantic failure.

## 3. The 4 completed live observations — verified contents

All 4 are cached under `research/llm_matchup/out/hardening_v3/cache/` and persisted in
`out/hardening_v3/golden_v3_states.jsonl`. Per-record fields present and verified for each of
the 4 (`mt_012249215`, `mt_978814872`, `mt_581147561`, `mt_972821383`):

- fixture id — present
- `source_evidence_packet_hash` — present
- `neutral_llm_packet_hash` (via `packet_hash` on the sent packet) — present
- generation id (`LLM_MATCHUP_V3`) — present
- resolved Bedrock model id (`us.anthropic.claude-sonnet-4-5-20250929-v1:0`) — present
- prompt version (`sonnet_prompt_v4`), ontology version (`football_ontology_v2`), schema
  version (`football_state_schema_v3`), neutralization policy version
  (`neutralization_policy_v1`), formation structure version (`formation_structure_v1`) — all
  present via the version stamp
- validation result — implicit in `status: OK` (validator_v3 accepted with 0 rejects) plus
  the full structured state persisted alongside
- structured state, supporting evidence ids, counter-evidence ids — present in full in
  `golden_v3_states.jsonl`
- latency / input+output tokens / cost — present (`latency_s`, `input_tokens`,
  `output_tokens`, and `cost_usd` computed in `golden_v3_summary.json`)

**Documented gap (not fabricated):** the manifest for these 4 cached calls does **not**
contain an explicit `inference_config` field (temperature/topP/maxTokens) — it was implicit
via the fixed `versions_v3.INFERENCE_CONFIG` constant rather than stamped per call. This has
been fixed going forward (`adapter_v4.py` now records `inference_config` in every new call's
manifest), but the fix does **not** retroactively add the field to these 4 already-cached
records, and they were **not** re-run to backfill it (re-running would spend tokens for a
purely cosmetic metadata fix, which this checkpoint mandate forbids). The actual inference
config used for all 4 is on record in `versions_v3.INFERENCE_CONFIG` and is unchanged from
`versions_v2.INFERENCE_CONFIG` (frozen, patch §50: not touched).

Qualitative spot-check of the 4 states (full detail in `golden_v3_states.jsonl`): all cite
real neutral evidence ids (e.g. `A_ATK_crosses_for_...`), use valid ontology enums
(`A_ADVANTAGE`, `STRONG_A_ADVANTAGE`, `MEDIUM_HIGH`, etc.), and set
`counter_evidence_search=PERFORMED` on every non-UNKNOWN assessment. This demonstrates the
V4/neutralized runtime **can** produce accepted, grounded structured states. **n=4 does not,
and is not claimed to, establish identity invariance, repeatability, evidence-sensitivity, or
Phase-C eligibility** — those require the live control battery in §13.

## 4. Fixture execution ledger (explicit per-fixture states, not collapsed to FAILED)

Persisted at `out/hardening_v3/golden_v3_execution_ledger.json`, backfilled from artifacts
already on disk (`golden_v3_summary.json` / `golden_v3_states.jsonl` for the current, n=20
run) plus this session's own tool-output transcript for the original n=15 run (whose states/
summary files were overwritten by the n=20 extension before a persistent ledger existed —
documented, not fabricated; see the ledger's own `"note"` field for exactly this provenance
split).

| Status | Count | Fixtures |
|---|---|---|
| `SUCCESS` | 4 | `mt_012249215`, `mt_978814872`, `mt_581147561`, `mt_972821383` |
| `AWS_DAILY_TOKEN_QUOTA` | 16 | remaining 16 (see ledger for full ids) |
| `NOT_ATTEMPTED` | 0 | — every fixture in the current 20-fixture manifest received at least one real attempt |

No fixture was replaced, swapped for an "easier" one, or dropped. The fixture set is
prefix-stable: fixtures 0–14 are byte-identical to the original n=15 selection; fixtures
15–19 are the approved n=15→20 extension attempted under the identical generation, per the
frozen `golden_v3_fixture_manifest.json`.

## 5. Generation/hash consistency guard

`out/hardening_v3/golden_v3_fixture_manifest.json` freezes:

```
fixture_manifest_hash: 1ec5bf739b49ad56d5837e609bd914bdd84cf2ed31dd4966ea7bc20a7e7f7316
generation_fingerprint:
  version_stamp.generation_id:              LLM_MATCHUP_V3
  version_stamp.prompt_version:             sonnet_prompt_v4
  version_stamp.packet_schema_version:      neutral_llm_evidence_packet_v1
  prompt_content_hash / schema_content_hash / ontology_content_hash
  neutralization_module_hash / formation_structure_hash / sampling_module_hash
  bedrock_model_id: us.anthropic.claude-sonnet-4-5-20250929-v1:0, region: us-east-1
  inference_config: {temperature: 0.0, topP: 1.0, maxTokens: 8192}
  sampling_params: {n: 20, max_scan: 200}
```

`golden_manifest.check_compatible()` recomputes every one of these fields (except
`sampling_params`, which is allowed to grow) and diffs them against the frozen values before
`resume_golden_v3.resume()` is permitted to make a single call. Any mismatch (a prompt edit,
an ontology change, a formation-structure table edit, etc.) returns
`ABORT_RESUME_GENERATION_MISMATCH` with the exact field-level diff, and **zero calls are
made**. This is unit-tested (`tests/research/test_golden_v3_resume.py::test_resume_aborts_on_generation_mismatch`)
against a mutated fingerprint, asserting the injected call counter stays at zero.

## 6. Quota-safe resume logic (implemented, tested, NOT executed live in this checkpoint)

`src/research/llm_matchup/hardening/resume_golden_v3.py`:

- **Idempotent.** A fixture already `SUCCESS` in the ledger is reused with zero new calls
  (`source: "ledger_cache"`). Tested.
- **Classifies, doesn't conflate.** `classify_bedrock_error()` distinguishes
  `AWS_DAILY_TOKEN_QUOTA` (message contains both `ThrottlingException` and the literal
  `"Too many tokens per day"`) from ordinary `THROTTLING_TRANSIENT` (any other
  `ThrottlingException`) and from `READ_TIMEOUT`. Tested against all three message shapes.
- **Stops on quota, doesn't retry indefinitely.** The instant one call classifies as
  `AWS_DAILY_TOKEN_QUOTA`, every remaining not-yet-attempted fixture in that `resume()` call
  is recorded `NOT_ATTEMPTED` (never `FAILED`) and no further calls are made. Tested with an
  injected fake `call_fn` and a call counter asserting exactly 2 calls happen (1 success, 1
  quota trip) out of 4 fixtures.
- **Full attempt history, never overwritten.** Every attempt (not just the latest) is
  appended to the ledger per fixture, so an old `READ_TIMEOUT` is never silently lost when a
  later attempt succeeds or fails differently. Tested across two sequential `resume()` calls.
- **`dry_run=True`** reports what would be attempted with **zero** calls — this is what was
  actually run against the real, current manifest+ledger in this checkpoint (see §8) to
  confirm the resume path's classification without spending anything.

14/14 new tests in `test_golden_v3_resume.py` pass offline (a fake `FakeResult`/`call_fn` is
injected everywhere; the real `adapter_v4.analyze_matchup_v4` is never invoked by the test
suite).

## 7. The read-timeout ambiguity (documented, not resolved)

`mt_584193286`'s first attempt (original n=15 run) returned:

```
Read timeout on endpoint URL: ".../model/us.anthropic.claude-sonnet-4-5-20250929-v1%3A0/converse"
```

Its second attempt (n=20 run, same fixture, same packet) returned the ordinary
`AWS_DAILY_TOKEN_QUOTA` `ThrottlingException`. **Bedrock's Converse API is synchronous
request/response with no job id to poll**, and `adapter_v4._save_cache()` is only reached
after a response is successfully parsed and validated — on any exception path (including a
client-side read timeout) nothing is ever written to cache. This means: (a) there is no
cache-based or other safe way to determine whether Sonnet actually completed inference for
that specific request before the client gave up waiting, and (b) precisely because nothing
was cached, the second attempt is **not** a double-count of the same observation — it is
either the first real observation for that fixture, or a second independent inference call
if the first one did in fact complete server-side and simply never reached us. Both attempts
are kept, separately classified, in the ledger; neither is treated as authoritative over the
other, and no state was fabricated to fill the gap.

## 8. Confirmation: no new Bedrock calls were made in this checkpoint task

Every artifact-producing action in this checkpoint was one of:
- reading existing on-disk artifacts (`golden_v3_summary.json`, `golden_v3_states.jsonl`,
  the cache directory) — no network;
- `golden_manifest.build_manifest()` / `save_manifest_if_absent()` — pure hashing of existing
  code/config, no network;
- the ledger backfill script — pure bookkeeping from artifacts + this session's own
  transcript, no network;
- `resume_golden_v3.resume(dry_run=True)` run once against the real manifest+ledger, which by
  construction makes zero calls (verified: attempt counts per fixture in the ledger are
  unchanged before/after, `1` or `2` each, matching the backfill exactly);
- the new pytest suite, which exercises `resume()` exclusively via an injected fake
  `call_fn`, never the real adapter.

No `adapter_v4.analyze_matchup_v4` invocation with a real Bedrock client occurred after the
n=20 smoke run concluded.

## 9. Engineering vs. scientific status (kept explicitly separate, patch §14)

**Established (engineering):**
- Structural identity neutralization is implemented, deterministic, hashed, and functioning
  correctly against real fixture data (34/34 unit tests; 25+ real fixtures scanned clean; all
  20 golden-batch requests' literal serialized text scanned clean).
- The hard interface guard genuinely refuses a non-neutralized packet and genuinely passes a
  correctly-neutralized one through.
- The V4 runtime, when it does get a response, produces schema-valid, evidence-grounded,
  counter-evidence-compliant states (n=4, 4/4 accepted).

**NOT yet established (scientific):**
- Whether V3's identity-token invariance controls (team/competition/formation alias swaps)
  actually hold under live inference — **zero** live control calls have been made.
- Whether V3 improved on V2's 75%/69%/54% trip rates at all.
- Repeatability, evidence-sensitivity-vs-noise, and surrogate non-triviality for V3 — all
  unmeasured.
- Mechanism eligibility and the global identity gate for V3 — unmeasured (the gate mechanism
  itself, added to `eligibility.py` in the prior turn, is implemented and tested, but has no
  V3 `controls_summary.json` to evaluate yet).

**"Literal request inspection demonstrates real identifiers no longer reach Sonnet. Only the
live invariance controls can demonstrate that the resulting inference behavior is
sufficiently identity-insensitive."** These are different claims and this checkpoint asserts
only the first one.

## 10. Exact resume workflow (prepared now, NOT executed)

When Bedrock capacity returns:

```bash
# 1. Dry run first -- zero calls, confirms the generation-compatibility guard still passes
#    and reports exactly what remains.
.venv/bin/python -c "
from src.research.llm_matchup.hardening import resume_golden_v3 as RG
print(RG.resume(dry_run=True))"

# 2. If step 1 reports status=RESUMED (not ABORT_*), resume for real:
.venv/bin/python -c "
from src.research.llm_matchup.hardening import resume_golden_v3 as RG
out = RG.resume()
print(out['status'], 'stopped_for_quota:', out['stopped_for_quota'])
print(out['results'])"
```

If step 1 ever reports `ABORT_RESUME_GENERATION_MISMATCH`, STOP and reconcile the diff before
touching Bedrock — do not force a resume across a code/version change (patch §5).

If `resume()` again reports `stopped_for_quota: true` before reaching all 20 fixtures, treat
it exactly as this checkpoint did: stop, do not retry in a loop, wait for capacity, re-run
step 1.

## 11. Future sequence (prepared, per checkpoint mandate §13 — NOT executed)

```
STEP A  Resume only missing golden-smoke calls from the frozen manifest (§10 above).
STEP B  If golden smoke violates structural/semantic acceptance criteria -> STOP, REVISE_LLM_LAYER.
STEP C  If golden smoke completes cleanly -> run the precommitted identity-control battery
        (team-alias / competition-alias / formation-id-alias invariance, using
        neutralize_v3.alias_team_tokens / alias_competition_token / alias_formation_id).
STEP D  Compute V2 -> V3 comparison: team/competition/formation trip rates, mean control
        distances, self-noise -- using the SAME distance/severity definitions as V2
        (ablation_noise.state_distance), never redefined after seeing V3 results.
STEP E  Run football-evidence behavior-sensitivity controls: identity-token perturbation
        should be ~self-noise; meaningful evidence perturbation should exceed self-noise.
STEP F  Repeatability + field-level stability for V3 (repeatability.py, reused).
STEP G  Raw-feature surrogate analysis for V3 (surrogate_ladder.py, reused).
STEP H  Mechanism eligibility + the GLOBAL identity gate (eligibility.py, already extended
        and tested) against V3's controls_summary.json. Same precommitted 0.20 trip-rate
        bar as V2 -- not moved after seeing V3 results (checkpoint mandate SS15).
STEP I  Write V3 final reports (IDENTITY_NEUTRALIZATION_V3.md, FORMATION_STRUCTURE_POLICY.md,
        V3_CONTROL_RESULTS.md, V3_FINAL_RECOMMENDATION.md) and, only if warranted,
        FREEZE_LLM_MATCHUP_V3.json.
STEP J  STOP. Even if V3 passes every gate, Phase C requires separate explicit authorization.
```

## 12. Files this checkpoint touches

New, under `research/llm_matchup/`:
`FORMATION_STRUCTURE_V1.json`, `V3_CHECKPOINT.md`,
`out/hardening_v3/golden_v3_fixture_manifest.json`,
`out/hardening_v3/golden_v3_execution_ledger.json`,
`out/hardening_v3/golden_v3_states.jsonl`, `out/hardening_v3/golden_v3_summary.json`,
`out/hardening_v3/cache/*.json` (4 real cached Bedrock responses + intermediate cache entries
from the earlier smoke attempts).

New, under `src/research/llm_matchup/hardening/`: `versions_v3.py`, `formation_structure.py`,
`neutralize_v3.py`, `prompt_v4.py`, `adapter_v4.py`, `audit_request.py`, `run_golden_v3.py`,
`golden_manifest.py`, `resume_golden_v3.py`.

New tests: `tests/research/test_llm_matchup_identity_neutral.py`,
`tests/research/test_golden_v3_resume.py`.

Modified (metadata-only, no behavior change): none of V2's files. `adapter_v4.py`'s
`inference_config` manifest field was added in this checkpoint (see §3) — this is a new file
in this same commit, not a modification to any previously-committed file.

**Untouched:** `LLM_MATCHUP_V2` (frozen), `PRE_PHASE_C_HARDENING.md`, all Phase-B/Phase-A
modules, the champion model, the contextual quant challenger, calibration, publication,
prospective logic, and every unrelated file in the working tree.
