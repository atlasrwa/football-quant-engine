# V6 PRE-SPEND EXACT PROVIDER TOKEN AMENDMENT

`V6_GROUNDED_RESEARCH_GENERATOR` — final narrow pre-spend infrastructure verification pass.

**Verdict: `V6_EXACT_TOKEN_BOUND_VERIFIED_AND_REFROZEN`.**

This amendment replaces the input-token term of the hard cost ceiling with AWS Bedrock's
provider-native `CountTokens` result for each of the 36 already-frozen requests. It is an
INFRASTRUCTURE / cost-accounting change only. No scientific parameter changed.

## Pre-conditions (unchanged by this amendment)

- Zero Bedrock inference calls have occurred.
- Zero V6 experimental observations exist.
- Spend authorization has NOT been granted.
- `CONVERSE_CALLS = 0`, `BEDROCK_INFERENCE_CALLS = 0`.

The only paid-service interaction added by this amendment is `bedrock:CountTokens`, which
AWS documents as non-generative and zero-charge.

## Why provider-native counting is stronger than the prior byte bound

The prior freeze (`prespend_freeze_cost_token_amendment_v2`) bounded each request's input
tokens by the **UTF-8 byte length** of the full canonical Converse token input. That is a
provably-conservative bound for byte-level BPE tokenization, but the claim that client-side
serialized UTF-8 bytes are a *formally proven* upper bound on Bedrock's provider-side token
accounting is stronger than provider documentation supports (structural tokenization of
message roles and the tool schema is not something the client can bound from first
principles with certainty). `CountTokens` returns the provider's own exact input-token count
for the identical Converse input, at no charge and with no inference. It closes that
uncertainty: the number in the ceiling is now the provider's own accounting, not a
client-side surrogate.

The exact provider count was verified to be `<=` the conservative byte bound for **every**
one of the 36 requests, confirming the old bound was genuinely conservative (never an
underestimate) and the tokenizer assumption holds.

## Model mapping (Audit 1)

- `execution_model_id` = `us.anthropic.claude-sonnet-4-6` (cross-region inference profile)
- `count_tokens_model_id` = `anthropic.claude-sonnet-4-6` (foundation-model id)
- `mapping_source` = strip the region-family prefix from the inference-profile id.
- `mapping_verified` = **true**, verified two ways against provider data, not string
  manipulation alone:
  1. `anthropic.claude-sonnet-4-6` is present in this account's `ListFoundationModels`.
  2. The `CountTokens` authorization ARN for the FM id is
     `arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6`.

`CountTokens` requires the foundation-model identifier; Claude tokenization is a property of
the model family and is identical across the regional copies the profile fans out to, so the
count is valid for every route the profile takes.

## IAM (Audit 2)

The execution identity (`arn:aws:iam::865147226910:user/atlas-ubuntu-deployer`) lacked
`bedrock:CountTokens`. A NEW, minimal inline policy `V6BedrockCountTokensOnly` was added
granting ONLY `bedrock:CountTokens`, scoped to exactly two resources:

- `arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-sonnet-4-6`
- `arn:aws:bedrock:us-east-1:865147226910:inference-profile/us.anthropic.claude-sonnet-4-6`

The inference policy (`AtlasLocalBedrockInvokePolicy`) was NOT modified. Token-counting and
inference authorization remain separated. No inference permission was broadened.

## Exact token result

| quantity | value |
|---|---|
| requests | 36 |
| counting method | `aws_bedrock_count_tokens` |
| total exact input tokens | 1,402,204 |
| total max output tokens | 294,912 (unchanged) |
| min / mean / max input tokens per request | 17,779 / 38,950.11 / 60,782 |
| `EXACT_INPUT_TOKEN_MANIFEST.json` SHA-256 | `d156be1d466da380c47de385e7348d511ceb54fef5857254d13325b81a29a5ae` |

Each entry is cryptographically bound to the canonical request SHA-256 and rebuilds to that
hash from the frozen packet via `v6_token_count.canonical_converse_request` — the same
function the execution driver sends to Converse. No second request builder exists.

## Cost proof (Audit 8/9)

Exact `Decimal` arithmetic; per-token price = frozen per-1k price / 1000; cents rounded UP.

- `MAX_INPUT_COST`  = 1,402,204 × $0.003/1k = **$4.21**
- `MAX_OUTPUT_COST` = 294,912 × $0.015/1k   = **$4.43**
- `MAX_TOKEN_COST` (exact, single global round-up) = **$8.64**
- `HARD_MAX_COST` (operational; sum of 36 per-request cent-up maxima) = **$8.79**
- `MAX_BILLABLE_ATTEMPTS` = 36 (`total_max_attempts = 1` per call; retries disabled)

The operational `HARD_MAX_COST` ($8.79) is the sum of each request's cent-up maximum,
mirroring the pre-call guard exactly so a fully-frozen run can never be falsely blocked. It
is `>= MAX_TOKEN_COST` ($8.64); the 15-cent gap is the deliberate per-request cent-up
padding of the existing guard, left unchanged. Both figures are reported; neither was
optimized.

## Difference from prior bounds

| bound | input tokens | hard ceiling |
|---|---|---|
| heuristic estimate (empirical bytes/token, DIAGNOSTIC only) | 1,457,486 | — |
| prior UTF-8 conservative bound (amendment v2) | 4,095,821 | $16.85 |
| provider-native exact count (this amendment) | 1,402,204 | $8.79 |

The UTF-8 byte bound was ~2.9× the exact count because it dominates structural overhead by
counting the bytes of the entire serialized request (system + every message + full JSON tool
schema) rather than the provider's tokenized form. The exact count sits slightly BELOW the
empirical diagnostic estimate, which merely confirms the empirical ratio (calibrated on
V5A.1) modestly over-predicts here. **A lower ceiling is not a scientific improvement** — it
is a tighter, provider-authoritative accounting of the same frozen requests.

## Exact files changed

- `research/hypothesis_engine/_count_tokens_v6.py` — NEW CountTokens driver (no inference).
- `research/hypothesis_engine/_freeze_v6.py` — consumes the frozen exact counts (keyed by
  request SHA-256) as the input-token term; falls back to the byte bound if the exact
  manifest is absent; freeze remains deterministic and makes no network call.
- `research/hypothesis_engine/_v6_states.py` — adds state
  `V6_EXACT_PROVIDER_TOKEN_BOUND_VALIDATED` and a hard-stop for a missing/incomplete exact
  manifest.
- `tests/research/hypothesis_oos/test_v6_exact_tokens.py` — NEW (21 tests).
- `tests/research/hypothesis_oos/test_v6_prespend.py` — 1 test updated (the diagnostic
  estimate is no longer the bound, so the invariant is now exact `<=` byte bound + all-exact).
- Regenerated artifacts under `research/hypothesis_oos/out/v6/`:
  `EXACT_INPUT_TOKEN_MANIFEST.json` (new), `count_tokens_audit_log.jsonl` (new, operational
  metadata only), `INPUT_TOKEN_MANIFEST.json`, `PREREGISTRATION.json`, `V6_STATES.json`.

## Old / new hashes

| artifact | old (v2 byte-bound) | new (v3 exact) |
|---|---|---|
| `INPUT_TOKEN_MANIFEST.json` | `cea58ce4…c079970` | `d65f45a0…634ae5a` |
| `PREREGISTRATION.json` | `40e75ece…01fe3c4` | `f123e8b4…de83864` |
| `EVALUATOR_FREEZE.json` | `d0c78442…690d71c` | `d0c78442…690d71c` (UNCHANGED) |
| `V6_STATES.json` | `f1b1c8ac…5bac14f4` | `81241f40…412d04d3` |
| `EXACT_INPUT_TOKEN_MANIFEST.json` | (did not exist) | `d156be1d…1a29a5ae` |

`EVALUATOR_FREEZE.json` is byte-identical: token accounting is not an evaluator input, so the
scientific evaluator freeze is provably untouched.

## Historical freezes (preserved)

- `prespend_freeze_pre_amendment_v1/` — untouched.
- `prespend_freeze_cost_token_amendment_v2/` — untouched (the byte-bound pre-spend state).
- `prespend_freeze_exact_token_amendment_v3/` — NEW; the exact-token pre-spend state.

Nothing was overwritten.

## Tests, reproducibility, CHAMPION

- Tests: `test_v6_prespend` 69/69, `test_v6_exact_tokens` 21/21; full engine + OOS suites
  728/728 pass. The 26 Audit-15 conditions are covered.
- Reproducibility: `EXACT_INPUT_TOKEN_MANIFEST.json`, `INPUT_TOKEN_MANIFEST.json`,
  `PREREGISTRATION.json`, `EVALUATOR_FREEZE.json`, `V6_STATES.json` are byte-identical under
  `PYTHONHASHSEED` 1, 2, 3, 12345 — including the exact manifest regenerated via live
  CountTokens under each seed. Operational metadata (request ids, timestamps, latency) is
  isolated to `count_tokens_audit_log.jsonl` and never enters the deterministic files.
- CHAMPION: `data/discovery/pilotC_stat_mixer.json` SHA-256 unchanged
  (`0b8f5ff3…410c00c9`); no V6 module is on any CHAMPION prediction path.

## Scientific integrity

`V6_SCIENTIFIC_DESIGN_CHANGED = false`. No fixture, arm, prompt, evidence packet, hypothesis
schema, adjudication, firewall, compiler, qualified-rate definition, abstention semantics,
self-noise estimator, the 0.363 planning statistic, the 0.229 MDE diagnostic, the Z
threshold, discipline gates, stop rules, fixture diversity, repeat structure, verdict logic,
or PASS/MIXED/FAIL/NULL semantics changed. The self-noise minimum detectable difference at
sd 0.363 remains 0.228685.

## Terminal state

```
V6_HYPOTHESIS_LEVEL_ADJUDICATION_VALIDATED
V6_FIREWALL_SEMANTICS_VALIDATED
V6_BALANCED_EXECUTION_DESIGN_VALIDATED
V6_SELF_NOISE_DESIGN_VALIDATED
V6_EVALUATOR_FROZEN
V6_FULLY_PREREGISTERED
V6_EXACT_PROVIDER_TOKEN_BOUND_VALIDATED
V6_SPEND_AUTHORIZATION_REQUIRED   ← STOP. Awaiting explicit human spend authorization.
```
