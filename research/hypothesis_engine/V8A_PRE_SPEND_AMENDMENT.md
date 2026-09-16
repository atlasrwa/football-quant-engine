# V8A — PRE-SPEND AMENDMENT

**This artifact precedes the re-spend it authorises**, as brief §25 requires of any spend gate.

## Why an amendment exists

A **P1 apparatus defect** was found mid-run, before the run completed and **before any
structural result was computed or viewed**.

### V8A-D1 — The pass-1 output ceiling bound for Arm B, truncating every response before the candidates array

**Root cause.** The V8A protocol requires behavioural reconnaissance and an attack x defense interaction map to be emitted BEFORE any candidate, and the schema orders them that way on purpose. Both sections are substantial. At max_tokens=8192 Arm B spent the entire output budget on them and generation stopped with the `candidates` key absent from the response object entirely.

**Evidence.** 2 of 2 executed Arm B pass-1 responses: stop_reason=max_tokens, output_tokens=8192/8192, response keys = [fixture_id, interaction_map, reconnaissance]. Arm A on the same ceiling: 12 of 12 stop_reason=tool_use, max 6730 output tokens.

**Why this is not a result.** A truncated response is structurally incapable of containing the quantity being measured. Reading it as an abstention would have inverted a headline metric, because brief section 21 scores abstention as SUCCESSFUL behaviour.

**When it was found.** BEFORE the run completed and BEFORE any structural result was computed or viewed. No outcome existed that could have informed the fix. This is a stronger position than the V6 -> V6.1 precedent, where the evaluator defect was found post-run.

---

## The fix, and why it is not prompt engineering

max_tokens_pass1 8192 -> 24576 and max_tokens_pass2 2048 -> 8192. These are EXECUTION parameters. The prompt, the schema, the fixture sample and the packets are byte-identical -- proved by seven unchanged hashes.

Brief §24 forbids editing *the prompt* and re-running the same sample while calling it the
same experiment. That rule is aimed at tuning toward outputs we like. This change:

* touches **no prompt text** — both system-prompt hashes are unchanged;
* touches **no schema** — the schema content hash is unchanged;
* touches **no fixture** — the fixture manifest hash is unchanged;
* touches **no evidence** — both packet-set hashes are unchanged;
* was decided from a `stop_reason`, not from a result. No structural rate had been computed.

### Proof that the sample and the prompt did not move

| Artifact | sha256 | moved? |
|---|---|---|
| fixture manifest | `c9e53ec4229eb331022c8548f2e1c2fb` | **no** |
| `packets_v8a.json` | `07b1e4772163859c403155f8…` | **no** |
| `packets_arm_a.json` | `8e04b237c90a6c9f540bfe2c…` | **no** |
| V8A pass-1 system prompt | `4507603ffb66357beb75351d…` | **no** |
| V8A pass-2 system prompt | `6968206082324d5bf58c6138…` | **no** |
| V8A schema content | `029bcd0f64a0c6afebaba38c…` | **no** |
| Arm A system prompt (`v6_prompt_v1`) | `e5a4529dfa69b8f4437e2f45…` | **no** |

Only the call plan and its cost fields differ. The freeze was **re-run**, not hand-edited, so
the driver's `ABORT_FROZEN_ARTIFACT_DRIFT` precondition still guards execution.

---

## Arm A is not re-run

The 8192 ceiling never bound for Arm A: all 12 responses stopped naturally at tool_use with at most 6730 output tokens. At temperature 0, max_tokens is purely a stopping condition, so a ceiling that never binds cannot alter the emitted tokens. Re-running Arm A would spend money to reproduce identical output.

Arm A therefore keeps its 12 completed responses. The effective condition is identical across
arms: neither arm's output was shaped by the ceiling.

---

## The class-level guard, so this cannot recur silently

`load_ok` now REJECTS any cached record whose stop_reason is max_tokens -- a truncated record is perfectly self-consistent and would otherwise cache forever. The driver records a max_tokens stop as an error that counts toward the three-consecutive fail-fast. The scorer keeps ABSTENTION, TRUNCATED and ERROR as three distinct states and excludes truncation from every abstention count.

---

## Free determinism check on the re-run

At temperature 0 the truncated prefix is deterministic, so the re-run must reproduce byte-identical reconnaissance and interaction_map for mt_196560745 and mt_257078511 before continuing into candidates. The discarded responses are preserved under out/v8a/truncated_prefix_evidence/ for that diff.

---

## Spend

| Item | Value |
|---|---|
| billed before the amendment | **$3.4309** |
| of which discarded as truncated | $0.4994 |
| responses retained | 12 (all Arm A) |
| previous ceiling | $11.23 |
| **new ceiling** | **$25.72** |
| hard maximum call count | 120 |
| max_tokens pass 1 / pass 2 | 24576 / 8192 |
| retries on the billable path | 0 |

The ceiling rises because output is charged at the full `max_tokens` so the bound holds
whatever is emitted. Actual spend is billed on real output tokens and will be far below it;
the actual figure is reported against this ceiling in the development report.

**Re-spend authorised up to $25.72 for at most 120 calls on
`us.anthropic.claude-sonnet-4-6`. Arm C remains stopped.**
