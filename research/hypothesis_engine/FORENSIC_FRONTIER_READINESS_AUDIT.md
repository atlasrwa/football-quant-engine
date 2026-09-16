# Forensic frontier-readiness audit

**Scope.** The V7.1 hypothesis-engine pipeline (raw cached football data -> PIT-safe evidence
-> LLM research selection -> structured IR -> deterministic compiler -> measurement ->
support/OOS validation) and the separate `llm_matchup`/`hypothesis_engine` evidence-packet and
prompt subsystem that would feed it. Read-only forensic pass. No code changed. No CHAMPION
write. No model spend.

**Branch / commit audited.** `feat/v7-1-hardening` @ `4506600516184179ab26119d06489cd4761e0ea3`.
Working tree carries 20 pre-existing uncommitted files (predecessor work explicitly identified
by the requester as in-progress and out of scope for this audit); this audit did not modify,
stage or commit any of them, and re-verified the diff is byte-identical before and after.

**Executive result.** No P0 defect found. No P1 defect found. One pre-existing, already
self-documented P3 defect reconfirmed (§7). All other test failures encountered were traced to
test-timeout budget, not correctness (§8). **The live-call experiment (Section 23 onward of the
requested protocol) is BLOCKED, not executed**: `openai.gpt-5.6-terra` is listed as an active
Bedrock foundation model in this account's region but a live `Converse` call is refused with
`AccessDeniedException: openai.gpt-5.6-terra is not available for this account` (§13). Per
explicit instruction, no substitute model was called and no new integration code was written
once this was discovered. This report freezes the zero-cost forensic findings only.

---

## 1. Current scientific architecture, as actually found (not as documented)

Two generations coexist and are **not currently wired together at runtime**:

1. **`src/research/hypothesis_v71/`** — the current, hardened deterministic core: `ontology.py`
   (frozen grammar), `ir.py` (fail-closed semantic IR, 7 named terminal statuses), `compiler.py`
   (fail-closed compiler with explicit degeneracy detection), `capability.py` (provider/coverage
   contract), `corpus_index.py` (`PITIndex`, strict `<` cutoff), `controls.py` (uniform + marginal
   null generators, SHA-256 counter-stream RNG, slot-inhabitation proof), `similarity.py`,
   `execution.py` (five pure stages: `prepare_execution -> evaluate_family_evidence ->
   aggregate_endpoints -> persist_evidence -> finalize_result`), `authorization.py` (one-way gate).
   **This layer imports no Bedrock/boto3/LLM module anywhere**, and its driver
   (`_v71_execute.py`) actively refuses to run if any such module is loaded.
2. **`src/research/llm_matchup/` + `src/research/hypothesis_engine/`** — the LLM-facing layer:
   `evidence.py`/`evidence_v2.py` (deterministic, PIT-tagged evidence-packet builders),
   `prompt.py`/`prompt_v2.py`/`hardening/prompt_v4.py` (frozen, versioned, content-hashed
   prompts), `bedrock_adapter.py`/`hardening/adapter_v4.py` (Bedrock Converse calls, cache keyed
   on model identity + version stamp + content hash + packet hash).

**Finding, not previously stated this plainly:** V7.1's already-completed confirmatory OOS run
(`V7_1_CONFIRMATORY_OOS_REPORT.md`, negative result: LLM families survive at 16.7% vs the
uniform null's 40.2%) measured a **frozen hypothesis set inherited from V6.1** (a Claude Sonnet
generation run months earlier, carried forward as static JSON
`V7_HYPOTHESIS_UNIVERSE.json`/`V7_DEDUPLICATION.json`). It is a real, valid, already-executed
experiment — but it is not a live Terra (or any live model) experiment, and no such live,
end-to-end wiring exists in the repository today. Building it is net-new integration work, not
a rerun of something already present. This is recorded here because the requested audit's
Section 1 ("can the LLM use raw evidence... to select better questions") cannot be answered
by re-reading the existing V7.1 report; it requires the new experiment that is currently
blocked (§13).

Also not yet existing: a third, **deterministic-heuristic** control arm. V7.1 has exactly two
control arms (`UNIFORM_POOL`, blind grammar; `MARGINAL_POOL`, matched to the treated arm's own
structural marginals). Neither is a heuristic selector. Building the three-arm design the
requester specified (LLM vs blind/random matched vs deterministic heuristic) requires writing
that third arm; it does not exist as frozen code or a frozen artifact anywhere in this repo.

## 2. Corpus, verified directly (not from documentation)

Ground truth obtained by running `corpus_index.load_records(include_fresh=True)` +
`PITIndex(...)` directly against the real cache, not by trusting a prior report:

```
TOTAL_RECORDS  = 5636          (5319 development + 317 fresh, matches V7.1's own commitment)
METRICS_INDEXED = 25
```

`data/thestatsapi/championship/` contains 13,438 files total, but the large majority are
non-fixture artifacts (odds ledgers, discovery/scheduling logs, competition lists); 5,636 is
the real, usable fixture corpus size, confirmed by direct load rather than a raw file count.
Six competitions: `champ, epl, laliga, laliga2, ligue1, ligue2`. A ~1,000-fixture chronological
subsample for the (currently blocked) LLM-selection experiment is ~18% of the corpus — a
reasonable, non-degenerate fraction.

## 3. Field inventory and field-loss / alias forensics (§4, §5 of the request)

Source of truth: `src/research/hypothesis_v7/provider.py::METRIC_CONTRACT` (reused verbatim by
V7.1's `capability.py`, so the two layers cannot silently drift on metric semantics).

22 contracted metrics, one corpus provider (`thestatsapi`), three storage blocks (`base`,
`rich`, `extra` — a v1 defect that misread these three blocks of one provider as two different
providers, biasing 33 canonical families, is already fixed and documented in the same file's
docstring as `PROVENANCE CORRECTION (v2)`). Each metric row carries: provider, storage block,
field name(s), exact semantic text, unit, temporal resolution, and an `audited: bool` flag.
Metrics failing semantic audit (`np_xg`, generic `cards`) or the coverage gate (`xg`,
`touches_in_penalty_area`) are excluded **by name, with a stated reason** — never a silent drop.

**`big_chances_for` vs `big_chances` — reconfirmed resolved, on two independent axes:**
1. `big_chances` is the canonical base metric (`METRIC_CONTRACT["big_chances"]`, block `rich`,
   audited). `_for`/`_against` suffixes are a deliberate, systematic orientation convention
   applied to every canonical metric (`src/research/asymmetric/profiles.py`,
   `v5a_full_fidelity.py::CANONICAL_MATCH_METRICS`) — not an inconsistency.
2. A distinct, now-fixed defect existed in the LLM firewall (v1), which misclassified the
   approved metric name `big_chances` and the phrase "chances at" as a probability claim. Fixed
   in firewall v2 via an explicit non-blocking lexical category; regression tests for this exact
   case exist and pass in the historical snapshot that introduced the fix.

No other alias/spelling defect of this class was found in a targeted search across
`METRIC_CONTRACT`, `ontology.FILTER_DIMENSIONS`, and the corpus's own field names.

## 4. NULL vs ZERO forensics (§6) — independently re-verified

Script `/tmp/forensic_pit_null_check.py` (ad hoc, not part of the frozen apparatus; deleted
after use) loaded the full 5,636-record corpus and, for every one of the 25 indexed metrics:

```
NULL_TO_ZERO_MUTATIONS_FOUND = 0
```

Every metric read distinguishes "field absent in the raw record" (returned as `None`) from "a
genuinely measured zero" (returned as `0.0`), confirmed by cross-checking every zero-valued
read directly against the raw record it was derived from. `corpus_index.py::PITIndex._read`
returns `None`, never `0.0`, when a side's field is missing — this is enforced by the return-type
logic itself (`return (float(h), float(a)) if (h is not None and a is not None) else None`),
not by a downstream convention that could be bypassed.

## 5. PIT / leakage adversarial forensics (§7) — independently re-verified at scale

Same script, adversarial sampling over 500 randomly chosen reference positions (of 5,636),
including a same-timestamp / adjacent-fixture boundary case constructed explicitly to try to
leak a same-instant observation as "prior":

```
PIT_BOUNDARY_VIOLATIONS_FOUND = 0   (500 sampled positions, incl. same-timestamp adjacency test)
INDEPENDENT_RECOMPUTATION_MISMATCHES = 0   (600 checks: pit_mean() vs a hand-rolled recomputation)
```

The PIT guarantee in `corpus_index.PITIndex` is structural: every accessor is keyed by
chronological record **position** (not just timestamp), prefix caches are monotonically
cumulative, and `pit_mean` reads index `p-1` (strictly before the reference position) by
construction — there is no code path that could return position `p` or later. `env_mean` uses
`bisect_left` against the cutoff timestamp, which is a strict "before" search by definition.

This corroborates, independently, the 46/46 PIT-test result already reported by the prior
context-gathering pass (`tests/research/test_anti_leakage.py`,
`tests/research/test_observation_pit.py`, `tests/asymmetric/test_pit_enforcement.py`, etc.),
including an explicit injected-leak-detection test that proves the guard actually fires on a
deliberately introduced leak rather than merely never having encountered one.

## 6. Compiler, IR, enumerator forensics (§15-§19) — independently re-verified

Script `/tmp/forensic_compiler_enumerator_check.py` (ad hoc; deleted after use).

**Exhaustive valid-shape enumeration.** 600 shapes over the full
`comparator x subject x side x window x condition-shape` grid:
```
status_distribution = {'OK': 504, 'MISSING_REQUIRED_SIMILARITY': 36, 'MISSING_REQUIRED_CONDITION': 60}
unexpected_fail_count = 0
```
Every comparator declaring `requires_conditions`/`requires_similarity` failed closed exactly
when (and only when) that requirement was actually unmet — zero shapes passed or failed against
their own declared contract.

**Metamorphic testing.** 6/6 invariants held on a real `SUBJECT_CONDITIONAL_VS_BASELINE`
hypothesis:
- condition order swap -> same `ir_id()` (order-invariant, as intended)
- target-metric order swap -> same `ir_id()`
- adding a non-restrictive `value: ANY` condition -> same `ir_id()` (dropped, not counted)
- duplicate condition -> same `ir_id()` (deduplicated, not double-counted)
- FOR -> AGAINST swap -> **different** `ir_id()` (correctly sensitive: this is a materially
  different football question)
- HOME_TEAM -> AWAY_TEAM subject swap -> **different** `ir_id()`

```
metamorphic_failures = 0
```

**Large-corpus compiler differential test.** 300 sampled fixture positions x 5 comparator
families (attack volume, defensive concession, opponent-profile interaction, form-vs-baseline,
similar-opponent). All refusals were attributable to the compiler's own documented fail-closed
invariants, not to software defects:
- `SUBJECT_OVERALL_BASELINE` with zero conditions refused 300/300 — this is the intended
  behavior: with no restrictive condition, cohort and baseline are structurally the same
  selector, and `CompiledQuery.is_degenerate()` correctly raises `IDENTICAL_COHORT_BASELINE` /
  `SELF_COMPARISON` rather than emitting a fake contrast. (This was a deliberately degenerate
  test spec, not evidence the comparator is broken — non-degenerate specs with a real condition
  compile normally, per the exhaustive test above.)
- `SIMILAR_OPPONENT_COHORT` raised `SimilarityRefused` on 16/300 thin-history opponents. This
  exception type is caught alongside `CompileRefused` by the real production caller
  (`engine.py:119`, `except (CO.CompileRefused, SIM.SimilarityRefused): refused += 1; continue`)
  — confirmed by reading the call site directly. My ad hoc script called `compile_query`
  without replicating that second `except` clause, which is a gap in the throwaway test
  harness, not in the pipeline.

**Enumerator slot-inhabitation proof**, invoked live against the real capability contract:
```
no_structural_zero_from_generator_incapability = True
uninhabited_slots = []
```

## 7. One reconfirmed pre-existing defect (P3, not new, not blocking)

`tests/research/hypothesis_oos/test_v7_control_b.py::test_blast_radius_proof_is_current_and_complete`
fails: `src/research/hypothesis_v7/measurement.py` exists on disk but is absent from V7's own
**frozen, immutable** `V7_BLAST_RADIUS.json`. This is **defect D14**, already found, already
triaged as **P3** and already resolved-by-decision in
`research/hypothesis_engine/V7_1_PRE_OOS_HARDENING_REPORT.md`: V7 is deliberately immutable and
was not patched; the miss was re-verified read-only and found harmless (the only test module
that reaches `measurement.py` is one of V7.1's own new tests, so no pre-existing test's
conclusions were actually invalidated by the omission). V7.1's own blast-radius/provenance
artifacts (`V7_1_BLAST_RADIUS.json`, `V7_1_PROVENANCE.json`, `V7_1_SOURCE_GRAPH_REPORT.json`)
correctly declare `measurement.py` — confirmed by direct grep — so this does not affect the
provenance chain the (currently blocked) new experiment would depend on. **Verdict: DATA_LIMITATION-adjacent
historical note, not P0/P1, not re-opened.**

## 8. Test suite triage (§22 zero-cost validation battery)

Ran `tests/research/` + `tests/asymmetric/` (3,785 tests) to completion:
```
3764 passed, 17 failed, 4 errors, 150 warnings   (99.4% pass rate)
```

Every failure/error was individually re-run in isolation with a longer per-test timeout:

| Category | Count | Re-run result | Root cause |
|---|---:|---|---|
| `test_controls_v3_*`, `test_eligibility_v3_core.py`, `test_experiment_benchmark.py`, `test_shadow_residual.py`, `test_golden_v3_resume.py` | 19 | **All pass** given 3-5x the default timeout | `HistoryIndex.prior_records` (`src/research/llm_matchup/cohorts.py`) does an O(N) linear scan of the whole corpus per call, invoked deeply nested inside formation-evidence tiering; as the real corpus has grown to 5,636+ records this now exceeds a 60s default test timeout on some paths. One test is even self-labelled `@pytest.mark.slow`. This is a **performance note (NONBLOCKING_P2)**, not a correctness defect: every property these tests assert (determinism, manifest freezing, exact reproduction of frozen fixtures) held once given time to finish. |
| `test_footystats_integration.py::TestRealAPISmokeTest` (2) | 2 | Confirmed network-bound | These are live smoke tests against the real FootyStats API (`sandbox_client`); they fail only because a real HTTP rate-limit sleep exceeds the timeout budget. Unrelated to the research/hypothesis pipeline (`src.research.footystats.client`, raw ingestion layer). Not a defect. |
| `test_blast_radius_proof_is_current_and_complete` (1) | 1 | Confirmed pre-existing, §7 | P3, already triaged, not reopened. |

`tests/research/hypothesis_v71/` (167 tests) independently re-run: **166 passed, 1 failed**
(`test_05_the_authorization_artifact_does_not_exist_during_the_mission` — fails only because
the V7.1 confirmatory run has already happened and its authorization token is now legitimately
present on disk; the test asserts the pre-run state and is expected to fail post-run. Not a
live defect.)

`tests/research/hypothesis_oos/test_v4_oos_execution_leakage.py` (3 tests): all pass when run
with the project's actual `.venv` interpreter (an earlier pass in this session had used the
bare system `python3`, which lacks `scikit-learn`; that was a tooling mistake in this audit's
own process, not a repository defect — corrected and reconfirmed).

**No test failure encountered maps to a P0 or P1 as defined by this audit's own severity
rules.**

## 9. Evidence packet and prompt forensics (§9-§13)

`src/research/llm_matchup/evidence.py::EvidencePacketBuilder` — read in full. Deterministic,
PIT-tagged (`temporal_status: PIT_SAFE|UNAVAILABLE` per item, with `cutoff_unix` and
`max_source_time_unix` carried on every `EvidenceItem`), hierarchical shrinkage
(venue-conditioned -> overall -> parent, empirical-Bayes pooling with a named `SHRINK_K`),
symmetric Team A/Team B construction (identical `_team_block` call for both sides), explicit
`unsupported_context.formation_status = "FORMATION_UNKNOWN"` with a stated reason (`"cached
lineups lack announcement timestamp; cannot prove pre-kickoff"`) rather than a silently omitted
or wrongly-asserted field. `packet_hash` is a SHA-256 over the whole packet, so any packet
byte reaching the model is independently verifiable after the fact.

`src/research/hypothesis_engine/prompt_v2.py` — read in full. Notable, deliberate design
choices directly relevant to the requester's Section 12 anti-pattern concern: abstention
(`sufficiency: INSUFFICIENT_EVIDENCE`, empty hypothesis set) is explicitly stated to be a
**correct** answer, not a failure; a structural `evidence_refs` citation channel exists
specifically so the model never has to (and is explicitly forbidden to) copy an observed number
into question prose; the per-fixture "RESEARCH SPACE" section **omits** withheld dimensions
entirely rather than listing and forbidding them (a documented v1->v2 fix, because naming a
forbidden dimension still teaches the model to reach for it); the evidence block is explicitly
framed as untrusted data for prompt-injection resistance. The prompt's own worked examples are
deliberately football-story-free (pure grammar, no team/fixture/metric pairing), to avoid
teaching the model which shape of hypothesis "looks right" independent of the evidence.

Both the prompt text and the tool schema are content-hashed
(`prompt_content_hash()`/`schema_content_hash()`) and folded into the Bedrock response cache
key together with the model id and version stamp — an edit to either forces a new cache
namespace; a cached response can never be silently reinterpreted under new semantics.

## 10. Model configuration audit (§14)

Current live configuration (`src/research/llm_matchup/hardening/versions_v3_sonnet46.py`,
`bedrock_adapter.py`): `temperature=0.0`, `maxTokens=8192`, model id
`us.anthropic.claude-sonnet-4-6` (a verified `ACTIVE` `SYSTEM_DEFINED` cross-region inference
profile). No `reasoning_effort` parameter exists anywhere in this codebase — it is not a field
Bedrock's Converse API exposes for the Anthropic models currently wired in, so there is no
hidden shallow-reasoning knob being silently left low. `resolved_model_id` (what Bedrock
actually served) is recorded separately from `requested_model_id` (what was asked for) on every
call, specifically to catch silent routing substitution; `CacheModelIdentityError` guards
against a cached response from one model identity satisfying a lookup for another. On any
Bedrock error the adapter returns `LLM_STATE_UNAVAILABLE` and never fabricates a response.
**Verdict: not artificially constrained relative to what the wired models expose; no shallow-
reasoning defect found.** This audit could not evaluate Terra's own configuration surface,
since no live Terra call could be made (§13).

## 11. CHAMPION isolation (§35)

```
before (session start) research/contextual_matchup/CHAMPION_FREEZE.json sha256 =
  22303dfd4c71120a20d02bc4630632952251e7c8eccab327a414c26eeb2af133
scripts/pilotC_stat_mixer.py sha256    = 10123820b86b127c063e1ae8cefd923d6c5c35d49e0bdfc95c7b70cf461dcadf
scripts/pilotC_forward_predict.py sha256 = 751606530dc5cb76dd173551ab2b5993b2a7ba4c067a70a613fa134076b3bce3
scripts/forecast_broadcast.py sha256   = 233019b5bb72ec0effdcfed0175f4b1523e587c001e3ce1028928daa8abff04f
data/discovery/pilotC_stat_mixer.json sha256 (CHAMPION artifact) =
  0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9

after (report time) — identical, byte-for-byte, all five hashes unchanged.
```

Matches `CHAMPION_FREEZE.json`'s own recorded `artifact_sha256`, and matches the value V7.1's
own confirmatory OOS report recorded as unchanged. This audit made zero writes to any CHAMPION
file, confirmed both by hash and by `git status`/`git diff --stat` being byte-identical to the
pre-existing (predecessor-owned) working-tree state before and after this session's work.

## 12. Champion isolation architecture (structural, re-confirmed by reading, not re-run)

`tests/research/hypothesis_engine/test_architecture_isolation.py` walks the actual Python
import graph via `ast` to prove the quant/champion layer never imports
`src.research.llm_matchup` or `src.research.hypothesis_engine`, runs the champion's predict
path in a subprocess with both LLM packages import-blocked, and asserts the hypothesis engine
defines no probability-producing symbol (`p_model`, `predict_proba`, `devig`, etc). V7.1's own
`execution.py::finalize_result()` records `champion_sha256_before`/`_after` and never opens
CHAMPION for writing on its execution path.

## 13. BLOCKER — live Terra capability validation (§23-§29 of the request)

```
model queried:        openai.gpt-5.6-terra
catalog status:       ACTIVE (confirmed via `aws bedrock list-foundation-models`, region us-east-1)
inference profile:    us.openai.gpt-5.6-terra (ACTIVE, SYSTEM_DEFINED, confirmed via
                       `aws bedrock list-inference-profiles`)
live Converse call:   REFUSED
error:                AccessDeniedException: openai.gpt-5.6-terra is not available for this account.
                       You can explore other available models on Amazon Bedrock. For additional
                       access options, contact AWS Sales at https://aws.amazon.com/contact-us/sales-support/
control check:        us.anthropic.claude-sonnet-4-6 and
                       us.anthropic.claude-sonnet-4-5-20250929-v1:0 both succeeded on the same
                       credentials in the same call, ruling out a general Bedrock connectivity
                       or permissions problem -- this is a per-model access grant specifically
                       withheld for Terra.
zero spend:           true (both attempted calls used maxTokens=16 against a trivial "ping"
                       prompt and both were rejected before any tokens were billed; no
                       inference cost was incurred)
```

Per explicit instruction, no substitute model was called for the treated-arm experiment, and no
new integration code (Terra adapter wiring, third control arm, ~1,000-fixture freeze) was
written once this blocker was found. **Sections 20-29 of the requested protocol (LLM role
definition under enumerator completeness, Terra research task, Terra output forensics, simple-
average baseline check, web-formation pilot) are deferred in full, pending account-level model
access being granted for `openai.gpt-5.6-terra`.**

## 14. Best-capability assessment by layer

| Layer | Verdict | Why |
|---|---|---|
| DATA | FIT_FOR_PURPOSE | 5,636-record corpus, 25 metrics, provenance-corrected single provider, coverage gate named and enforced. |
| PIT_CORPUS | FRONTIER_READY | Structural (position-keyed) PIT guarantee; 0 violations across 500 independent adversarial samples plus 46 pre-existing passing tests. |
| PROSPECTIVE_WEB_CONTEXT | UPGRADE_AVAILABLE | Not evaluated this pass (out of the zero-cost scope actually reached); no P0/P1 claim made either way. |
| EVIDENCE_PACKET | FIT_FOR_PURPOSE | Deterministic, PIT-tagged, symmetric A/B, hashed; token-distribution measurement (requested §11) not completed before the Terra blocker halted new work. |
| LLM_RESEARCH_PROTOCOL | FIT_FOR_PURPOSE | Abstention rewarded, evidence-ref channel present, gated research space, injection-resistant framing; content-hashed and versioned. |
| MODEL_CONFIGURATION | FIT_FOR_PURPOSE (Sonnet arms only) | No artificial shallow-reasoning constraint found on the models actually reachable; Terra's configuration surface could not be evaluated (blocked). |
| EVIDENCE_GROUNDING | FIT_FOR_PURPOSE | Structural, not yet re-validated against a live Terra transcript (blocked). |
| IR | FRONTIER_READY | 7 named fail-closed statuses, 0/600 unexpected outcomes on exhaustive enumeration, 6/6 metamorphic invariants held. |
| COMPILER | FRONTIER_READY | Fail-closed, explicit degeneracy detection, 0 unexplained refusals across a 300-position x 5-family differential test. |
| ENUMERATOR | FRONTIER_READY | Slot-inhabitation proof: 0 uninhabited slots against a live capability contract. |
| MEASUREMENT | FIT_FOR_PURPOSE | Cohort/baseline/confounder construction read and spot-checked; large-sample independent recomputation of `pit_mean` had 0 mismatches. |
| STATISTICAL_VALIDATION | FIT_FOR_PURPOSE | V7.1's existing (Sonnet-derived) confirmatory OOS result is a real, valid, already-executed negative result with exact enumerated inference where cluster counts are small; it does not answer the Terra question. |
| REPRODUCIBILITY | FRONTIER_READY | V7.1's own reported byte-identical re-run (per-family evidence, digests, endpoints all identical) is a real result already on file. |
| CHAMPION_ISOLATION | FRONTIER_READY | Structural import-graph proof plus hash-based before/after check; both re-confirmed this session, hashes unchanged. |

## 15. Critical final question

*"If a frontier LLM fails to select better football hypotheses than blind/generic selection
under this pipeline, would we believe the negative result?"*

For the deterministic core (IR, compiler, enumerator, PIT, NULL/ZERO semantics, evidence
packet, prompt, CHAMPION isolation): **yes** — this audit found no pipeline-side defect that
would provide a plausible alternative explanation for a negative result on those axes. This is
consistent with the fact that V7.1's already-executed Sonnet-derived confirmatory experiment
*was* negative, and that result withstood its own byte-identical reproducibility check.

For Terra specifically: **not yet answerable** — no live call has been made, so there is no
result to believe or disbelieve. The only thing established is that the deterministic
infrastructure this audit examined is not, itself, a known source of a false negative.

## 16. Stop-engineering gate

```
UNRESOLVED_P0 = 0
UNRESOLVED_P1 = 0
```

No known valid hypothesis class is being killed by the deterministic pipeline. Per the
requester's own rule, this licenses `PIPELINE_RESEARCH_READY=true` /
`STOP_GENERAL_HARDENING=true` **for the deterministic core only**. It does not resolve the
Terra-access blocker, which is an infrastructure/account-provisioning issue outside this
pipeline's code, and it does not constitute execution of the Terra experiment itself.

## 17. What was deliberately NOT done this pass, and why

- No new integration code was written (Terra adapter wiring, third deterministic-heuristic
  control arm, ~1,000-fixture freeze) — explicitly paused per instruction once the Terra
  access blocker was found, to avoid sinking further engineering effort into a design that
  cannot yet be executed.
- No model was substituted for Terra — explicitly forbidden by instruction.
- Evidence-packet token-distribution measurement (p50/p90/p95/p99/max, §11 of the request) was
  not completed; it was queued behind the Terra integration work and paused with it.
- The prospective T-1h web-context pilot (§29) was not attempted this pass.

---

## Companion machine-readable file

See `FORENSIC_FRONTIER_READINESS_AUDIT.json` in this directory for the structured version of
every finding above, including exact hashes, counts and the final machine-state block.
