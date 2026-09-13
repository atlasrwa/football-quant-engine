# B0 — Live Bedrock Sonnet Smoke Test

**Purpose: ENGINEERING VALIDATION ONLY** (brief §14). B0 does not tune any predictive
idea. It confirms the real Bedrock path works, records model identity, and fails closed on
bad input.

## Environment / identity (brief §15, §25)

| Field | Value |
|-------|-------|
| Bedrock model / inference profile | `us.anthropic.claude-sonnet-4-5-20250929-v1:0` |
| AWS region | `us-east-1` |
| Access path | Bedrock Runtime `Converse` with strict tool input schema (structured output) |
| ontology_version | `football_ontology_v2` |
| schema_version | `football_state_schema_v2` |
| prompt_version | `sonnet_prompt_v2` |
| packet_schema_version | `fixture_evidence_packet_v2` |
| formation_policy_version | `formation_policy_v1` |
| formation_family_version | `formation_family_v1` |
| inference config | `temperature=0.0`, `maxTokens=8192` (topP omitted — see note) |

The resolved model id is persisted per call in `out/phase_b_calls.csv` and the per-call
cache manifest. No silent model drift.

### Engineering fixes required to make the live path work (recorded, not hidden)

1. **boto3 upgrade** `1.34.69 → 1.43.93` in the research venv — the older botocore lacked
   the `converse` operation. Medium-risk dependency change, confined to the research venv.
2. **`temperature` + `topP` cannot both be sent** to Sonnet 4.5 via Converse (returns a
   `ValidationException`). The adapter now sends `temperature` only.
3. **`maxTokens` 4096 → 8192.** At 4096 the structured output was truncated mid-JSON,
   producing "missing required field" rejections. 8192 lets the full state complete
   (observed output ≈ 3.7k–5.4k tokens).
4. **Model default** changed from `anthropic.claude-3-5-sonnet-20241022-v2:0` (not enabled
   for on-demand in this account) to the cross-region inference profile above.

## Result (n = 8 fixtures)

| Metric | Value |
|--------|-------|
| Calls attempted | 8 |
| Live OK (schema-valid, validator-accepted) | 7 |
| Live rejected (fail-closed) | 1 |
| Bedrock failures / unavailable | 0 |
| Schema-valid % | **87.5 %** |
| Input tokens / call | ≈ 28,000 |
| Output tokens / call | ≈ 3,700–5,400 |
| Latency / call | ≈ 37–52 s |

### The single rejection is a *correct* fail-closed catch

`mt_978826968`: `context_flags` / `invalid enum value 'MEDIUM_HIGH'` — Sonnet placed a
confidence value in a slot whose enum did not permit it. The deterministic validator
rejected the whole output (no partial salvage), exactly as designed. This is desirable
behavior: the validator does not trust the LLM.

## Engineering checks (all PASS)

| Check | Result | How verified |
|-------|--------|--------------|
| `converse_ok` — real structured request works | ✅ | ≥1 live OK response with a `toolUse` block |
| `identity_recorded` — model id persisted per call | ✅ | `resolved_model_id` present in manifest |
| `cache_hit_works` — packet-hash caching | ✅ | second call on same packet returns `cache_hit=true` |
| `invalid_fails_closed` — bad output rejected | ✅ | corrupt tool input → `ValidationError` |
| `aws_exception_maps_unavailable` | ✅ | impossible model id → `LLM_STATE_UNAVAILABLE` (never fabricated) |
| `no_credentials_logged` | ✅ | manifest scanned for `aws_secret`/`session_token`/etc. — none present |
| `no_probability_leak` | ✅ | validated states scanned for probability/betting keys — none |

## Observations (recorded, NOT tuned)

- Sonnet emitted **zero** `FORMATION_*` family mechanisms in B0. The formation-conditioned
  evidence for these fixtures is dominated by sparse exact cohorts (often `n=1`, `LOW`
  reliability) that degrade to `VENUE_OVERALL`/`FAMILY` tiers. Sonnet's choice to lean on
  the more reliable behavioral mechanisms rather than invent formation conclusions from
  thin evidence is a *faithful* behavior consistent with the closed-world rules. Whether it
  uses formation evidence when it is materially present is tested in B1 (§18, §20, §21).
- No prose, no probabilities, no predictions appeared in any accepted output.
- Orientation (A=home, B=away; FOR/AGAINST) was correct in all accepted outputs
  (validator-enforced + manual spot check in `PHASE_B_AUDIT.md`).

## Verdict

**B0 PASSES.** The live Bedrock Sonnet path is engineering-sound: structured output works,
identity is recorded, caching works, and every failure mode fails closed without
fabrication. Proceed to B1.
