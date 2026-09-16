# V8A — PRE-SPEND REPORT (brief §25)

**No `Converse` call has been made.** Spend so far: **$0.00**. `converse_called = false` in
`V8A_FREEZE.json`. This artifact exists so that it precedes the first paid call, as the brief
requires.

Every input-token figure below is the **exact provider-native count** from Bedrock
`CountTokens`, which is non-generative and free — not an estimate.

---

## 1. Model identity and access

| Item | Value |
|---|---|
| execution model id | `us.anthropic.claude-sonnet-4-6` |
| access status | **ACTIVE**, verified via `bedrock list-inference-profiles` |
| CountTokens model id | `anthropic.claude-sonnet-4-6` |
| region | `us-east-1` |
| AWS identity | `arn:aws:iam::865147226910:user/atlas-ubuntu-deployer` |
| temperature | 0.0 |
| max_tokens pass 1 / pass 2 | 8192 / 2048 |
| retries on billable path | **0** (`botocore max_attempts=0`) |

### 1.1 Interpreter requirement — a real blocker, found and resolved

The system interpreter `/usr/bin/python3` carries **boto3 1.34.46, whose
`BedrockRuntime` client has no `converse` method at all**. Executing there would have failed
every call — the process-wide SDK incompatibility this repository has already been bitten by
once. Execution and token counting therefore run on **`/home/ubuntu/.venv/bin/python`
(boto3 1.43.93)**, which exposes both `converse` and `count_tokens`. Import isolation to the
worktree was re-verified under that interpreter, and the pipeline battery re-run there:
**21/21 passing**.

### 1.2 Terra — Arm C is STOPPED, not substituted

`V8A_TERRA_ARM_EXECUTED = false`.

**Blocker (exact):** No model named "Terra" exists anywhere in this repository; no OpenAI or
other non-Bedrock credential is present in the environment; no provider adapter for such a
model exists. Brief §19/§33 forbid silently substituting another model or calling another
model "Terra", so the arm is stopped. Arms A, B and D proceed.

---

## 2. Fixtures

| Item | Value |
|---|---|
| fixtures frozen | **12** |
| competition mix | {"champ": 2, "epl": 2, "laliga": 2, "laliga2": 2, "ligue1": 2, "ligue2": 2} |
| eligible pool | 915 |
| excluded — V7.1 confirmatory / future V8 pool | 317 |
| excluded — V7 confirmatory window 2025-01-01..2026-05-31 | 3,606 |
| excluded — every prior LLM experiment's target fixtures | 21 |
| excluded — insufficient prior history | 793 |
| selection reads outcomes / effects | **false / false** |
| fixture manifest sha256 | `c9e53ec4229eb331022c8548f2e1c2fb6709454c8921319243a498a6f7f799cf` |

Fixture ids are frozen and will not change after outputs are read.

---

## 3. Planned calls

| Arm / pass | Purpose | Calls | min tokens | max tokens | mean |
|---|---|---|---|---|---|
| Arm A pass 1 | V6.1 incumbent protocol, one pass | 12 | 45,352 | 59,794 | 50,268 |
| Arm B pass 1 | V8A deep-football, pass 1 | 12 | 38,913 | 51,938 | 42,542 |
| Arm B pass 2 | V8A generic novelty challenge, pass 2 (bound) | 96 | 5,384 | 5,384 | 5,384 |

* **Hard maximum call count: 120** (Arm A 12, Arm B pass 1
  12, Arm B pass 2 at most 96).
* Arm C: 0 (blocked). Arm D: 0 (deterministic, no model).
* Pass-2 granularity: **ONE_CALL_PER_CANDIDATE**. Its 96 calls are an
  upper bound — 12 fixtures × 8 max candidates. Fewer candidates means fewer calls, and
  abstention is an acceptable outcome, so the real count will likely be lower.
* Pass 2 is priced with a **worst-case maximal candidate payload**, so the ceiling holds
  however large the real candidates are.

### Cost ceiling

**Hard maximum spend: $11.23 USD.**

Computed per request at the frozen `max_tokens`, rounded **up**, with retries disabled, at
$0.003/1K input and $0.015/1K output. Output is charged at the full `max_tokens` so the bound
holds whatever the model actually emits.

---

## 4. Frozen hashes

| Artifact | sha256 |
|---|---|
| V8A pass-1 system prompt | `4507603ffb66357beb75351d5b22adb00d03e67207e8175ef8395d4ac8f48c91` |
| V8A pass-2 system prompt | `6968206082324d5bf58c6138671f8175e4c2985a599126c64013b8e0d6c1bdde` |
| V8A schema content | `029bcd0f64a0c6afebaba38cdf26c7fb3911a08413e06e68626fec89bb61eb4e` |
| Arm A system prompt (`v6_prompt_v1`) | `e5a4529dfa69b8f4437e2f45ea7a9522304c5377abe927cc6373acdf271e244b` |
| Arm A schema (`hypothesis_set_schema_v4`) | `94b77cbac6b3cc1f444aeb9610d224eb536fe1948b8c33578ef74a75bdb57092` |
| fixture manifest | `c9e53ec4229eb331022c8548f2e1c2fb6709454c8921319243a498a6f7f799cf` |
| generic library keys | `80a72d4919ec69364cc8678ba6730c6482f510e30ae53fc49fbfdc28b2ba78c8` |
| V8A packets | `07b1e4772163859c403155f85bb757224b1b2f283399b86c12167661570f72f5` |
| Arm A packets | `8e04b237c90a6c9f540bfe2c23b1f58bc59ad3485e80d29e370725b06f213329` |
| capability manifest | `cdf3721f591f45fbf98ec28a050b3290b4a4e08369f2f4058747165cf415eae6` |
| call plan | `dcca015c16781de5146d00fd2141c4fd72835e986a0613d2a712343071a05120` |

Both prompts are frozen **before** the first paid call. Neither blinding battery reports a
violation. If results disappoint, a revision becomes V8A.1 with its own sample.

---

## 5. Evidence integrity

| Check | Result |
|---|---|
| all V8A packets PIT-clean | **True** |
| no banned tokens (closing line, settlement, market price, p_model, EV) | **False** |
| Arm A packets built with the genuine V6.1 builder | **12/12**, none missing |
| Arm A prompt reconstructed or approximated | **false** — reproduced verbatim |
| pipeline battery | **21/21 passing** |

---

## 6. Generic library

| Item | Value |
|---|---|
| materialized entries (retrieval only) | 406,944 |
| distinct structural keys | 406,944 |
| shared metric vocabulary | 24 metrics, identical for every arm |
| membership decided | **analytically, against the generator's image** — not by sampling |
| predicate agrees with the real generator | **True** (1,910 non-degenerate draws, 0 unreachable) |
| exposes survival / effects / p-values / fold performance | **false** on every one |

---

## 7. CHAMPION protection

| Item | Value |
|---|---|
| identity | `pilotC_stat_mixer.elasticnet_logistic_full_corpus` |
| composite sha256 BEFORE | `778339321631f0a15e42738977c810c055aaeb65315c52852e0370618b8baef8` |
| self-consistent with `CHAMPION_FREEZE.json` | {"artifact": true, "forward_predict_py": true, "scope_config": true, "stat_mixer_py": true} |

The same composite is recomputed after execution and must be identical. V8A is not imported
by production inference, and no dependency runs from CHAMPION into V8A.

---

## 8. Gate

Everything brief §25 requires is present: model ids, access status, fixture count, planned
calls by arm, the two-pass novelty call count, max tokens per request, the computed cost
ceiling, the hard maximum call count, prompt hashes, evidence packet hashes, the generic
library hash and the fixture manifest hash. No secret or API key appears in any artifact.

**Spend authorised up to $11.23 for at most 120 calls on
`us.anthropic.claude-sonnet-4-6`. Arm C remains stopped.**
