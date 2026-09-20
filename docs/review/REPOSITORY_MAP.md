# Repository map — component status, file disposition, deprecation, backlog

Companion to `REVIEWER_GUIDE.md`. This is a map of what exists, what is authoritative,
and what is unverified. It is **not** a claim that the engine is ready.

Throughout: *VERIFIED_OFFLINE* names exactly what was exercised. *UNVERIFIED* means I did
not gather evidence, not that something is broken.

---

## A. Component status

| Capability | Authoritative entry point | Lifecycle | Verification | Known blocker |
|---|---|---|---|---|
| Provider / API integration | `src/providers/*`, `scripts/sync_provider_leagues.py` | ACTIVE | UNVERIFIED | needs live credentials; not exercised here |
| Data ingestion & identity | `src/research/matchup/corpus.py` + `scripts/multisrc_corpus.py`, `scripts/championship_adapter.py` | ACTIVE | EXTERNAL_DEPENDENCY_REQUIRED | raw corpus is out of Git (see §E) |
| LLM hypothesis selection | `src/research/hypothesis_v8c/runner.py` (`run_fixture_converse`, injected transport) | ACTIVE | VERIFIED_OFFLINE — mocked Converse, 18 tests | **never run against a live model**; resolved model identity never reported |
| LLM prompt / tool contract | `src/research/hypothesis_v8c/prompt.py` | ACTIVE | VERIFIED_OFFLINE — content-hashed, bound into provenance | — |
| Deterministic evaluation | `src/research/hypothesis_v8c/{universe,pre_t,compiler,scorer}.py` | ACTIVE | VERIFIED_OFFLINE — V8C suite | per-fixture universe build ~65–95 s |
| Controls (R / H) | `src/research/hypothesis_v8c/controls.py`, `control_coverage.py` | ACTIVE | VERIFIED_OFFLINE — max-matching + Hall bound | **K=8 set-level feasibility OPEN** |
| Validation & provenance | `select_freeze.py`, `receipt.py`, `anchor.py`, `score_frozen.py` | ACTIVE | VERIFIED_OFFLINE — 57 gate/anchor tests | — |
| Bundle / data gate | `src/research/hypothesis_v8c/bundle_gate.py` | ACTIVE | VERIFIED_OFFLINE — 15 tests, pinned digest | — |
| Hardening v3 (golden runs) | `src/research/llm_matchup/hardening/*` | ACTIVE | VERIFIED_OFFLINE — 104 tests | scientific content not audited |
| Discovery / ingestion | `scripts/pilotC_fixture_discovery.py`, `scripts/multisrc_step4_discovery.py`, `scripts/refresh_corpus.py`, `python -m src.cli corpus-ingest` | ACTIVE | UNVERIFIED | provider credentials required |
| Forecast commitments (Pilot C) | `scripts/pilotC_forward_predict.py` → `data/forward/commitments.jsonl` | ACTIVE | UNVERIFIED | entry point exists; execution not traced |
| Forward loop (Pilot C) | `scripts/pilotC_forward_loop.py`; `scripts/quarantine_forward_loop.py` | ACTIVE | UNVERIFIED | `quarantine_forward_loop.py` **is** in the live crontab (4 h); `pilotC_forward_loop.py` is **not** — it is run by hand |
| Settlement (Pilot C) | `scripts/pilotC_settle.py` → `data/discovery/pilotC_settled_log.json` | ACTIVE | UNVERIFIED | closing observation + evaluation + settlement in one script; execution not traced |
| Prospective capture (package) | `python -m src.research.prospective.cli` — `capture-due`, `capture-upcoming`, `capture-odds`, `capture-lineups`, `quality-report`; wrapped by tracked `scripts/prospective_capture_run.sh` | ACTIVE | UNVERIFIED | **not in the live crontab.** The `*/15` cadence appears only as a *recommendation* in `research/evaluation/prospective_*_report.md`. Fails closed and exits non-zero when no API key is configured, without attempting a request |
| Shadow-residual derivation | `python -m src.research.prospective.shadow_process run` | ACTIVE | UNVERIFIED | consumes persisted state only — **no provider request, no model call**. Joins both commitment ledgers with own market snapshots and appends idempotently. Explicitly **no league allowlist and not Pilot-C gated**. Not scheduled; intended to ride an existing scheduled run |
| Prospective shadow settlement | `python -m src.research.prospective.shadow_settle_process run`; also invoked from `src/research/prospective/cli.py:731` | ACTIVE | UNVERIFIED | grades frozen prospective shadows against canonical finals through an **injected** resolver; append-only, bounded provider use, fail-closed per shadow. Not scheduled |
| Publication | `scripts/forecast_broadcast.py` (cron, 15 min), `scripts/signals_telegram_bot.py` (cron, daily) | ACTIVE | UNVERIFIED | entry point exists; execution not traced |
| Scheduling & ops | live crontab, 8 entries → `scripts/{forecast_broadcast (×3 forms),fixture_alert_watcher,quarantine_forward_loop,signals_telegram_bot,sync_provider_leagues,refresh_corpus,pilotC_fixture_discovery}.py` + `python -m src.cli daily-signals` | ACTIVE | VERIFIED_OFFLINE — crontab read, all entry points tracked and present | jobs run on the deployed host only; see `REVIEWER_GUIDE.md` §3 for the exact schedule |
| Matchup research (PHASE F/G) | `src/research/matchup/run_*.py` | EXPERIMENTAL | UNVERIFIED | run directly; not scheduled |
| Leak-remediation diagnostics | `scripts/diagnose_*.py`, `*_9660.py` | EXPERIMENTAL | UNVERIFIED | read cached corpus; no network |
| Live-API integration probe | `test_hypothesis_layer_real_api.py` | EXPERIMENTAL | EXTERNAL_DEPENDENCY_REQUIRED | opt-in via `RUN_LIVE_API_TESTS=1`; real key + charges |

**No authoritative implementation exists** for an end-to-end "fixture → forecast → settlement"
pipeline. V8C (hypothesis selection), hardening v3 (golden LLM runs) and the champion
forecasting path are **three separate capabilities** that share football data. They are not
versions of one another and must not be collapsed.

**Pilot C and `src/research/prospective/` are likewise distinct and neither supersedes the
other.** Pilot C is the `scripts/pilotC_*.py` family writing `data/discovery/` and
`data/forward/`; `src/research/prospective/` is a 48-module package writing
`data/prospective/`. `shadow_process` states in its own module docstring that membership is
decided by "which competitions have a committed forecast and a paired pre-kickoff snapshot —
never by league identity, and never by Pilot-C membership". Their relationship was **not**
traced in this pass; both are recorded, neither is marked obsolete.

## B. File disposition

Exact paths. `PUSH` = in this branch. Counts, taken from the final inventory in
`V8C_REVIEW_SNAPSHOT_MANIFEST_V1.json` (artifact `..._V3`): **56 PUSH**, 14 KEEP_LOCAL,
1 KEEP_EXTERNAL, 0 HOLD — 70 file entries plus 1 directory-group entry, counted separately.
The rows below group paths for readability; the manifest is the per-file authority.

| Path | Git status | Disposition | Reason | Dependencies |
|---|---|---|---|---|
| `src/research/llm_matchup/hardening/{atomic_io,run_lock}.py` | untracked → PUSH | PUSH | tracked `resume_golden_v3.py` imports both; resume path was broken on any clean clone | none |
| `src/research/llm_matchup/hardening/{audit_prespend,controls_v3_core,controls_v3_sonnet45,controls_v3_sonnet46,eligibility_v3_core,eligibility_v3_sonnet45,eligibility_v3_sonnet46,freeze_v3_sonnet46,golden_v3_sonnet46,versions_v3_sonnet46}.py` | untracked → PUSH | PUSH | companion modules of the same package | `adapter_v4` |
| `src/research/llm_matchup/{bedrock_adapter}.py`, `hardening/{adapter_v4,golden_manifest,resume_golden_v3}.py` | modified → PUSH | PUSH | interdependent with the new modules | boto3 |
| `src/research/matchup/{features,harness,design,gen_artifacts}.py` | untracked → PUSH | PUSH | imported by tracked `_run_v4_oos.py` and `llm_matchup/gen_artifacts.py` | numpy, sklearn (`harness`) |
| `src/research/matchup/{count_models,referee_env,run_count_uncertainty,run_experiments,run_gbt,run_phase_f_and_forensics,run_referee_cards}.py` | untracked → PUSH | PUSH | PHASE F/G research entry points, run directly | numpy, sklearn, scipy; `referee_env`/`run_referee_cards` import `scripts/pilotC_stat_mixer` (tracked) |
| `scripts/{diagnose_cards_edge,diagnose_corners,goals_vs_market_9660,rebuild_prior_only_9660,score_prior_only_9660}.py` | untracked → PUSH | PUSH | leak-remediation diagnostics; reviewable reasoning | numpy; cached corpus |
| `run_benchmark.py`, `run_robustness_check.py` | untracked → PUSH | PUSH | walk-forward benchmark and 25-league robustness check | numpy; cached corpus |
| `tests/research/test_{controls_v3_core,controls_v3_censoring_provenance,eligibility_v3_core,formation_leakage,formation_policy,golden_v3_sonnet46,matchup_leakage}.py` | untracked → PUSH | PUSH | cover the modules above; includes 2 leakage tests | pytest |
| `tests/conftest.py`, `tests/research/test_golden_v3_resume.py` | modified → PUSH | PUSH | hypothesis-profile registration; resume companion | pytest, hypothesis |
| `MARKET_RELATIVE_REPORT.md`, `PER_LEAGUE_STATMIXER_REPORT.md`, `fdr_analysis_results.md`, `robustness_results.json` | untracked → PUSH | PUSH | findings the diagnostics produced; 64 KB total | none |
| `test_hypothesis_layer_real_api.py` | untracked → PUSH | PUSH | integration coverage; opt-in guard added | `RUN_LIVE_API_TESTS=1`, live key |
| `.gitignore`, `.env.example`, `pyproject.toml` | modified/new → PUSH | PUSH | hygiene, placeholder config, dependency declarations (`scikit-learn`, `psycopg2-binary`, corrected `boto3`) | — |
| `src/_repo_paths.py` | new → PUSH | PUSH | derives the executable source root from its own canonical location; no environment variable can redirect it (§D, and "Source-root behaviour" below) | none |
| `tests/test_repo_paths.py` | new → PUSH | PUSH | regression coverage for the above: subprocess-isolated, proves a foreign `V8C_ROOT` cannot load a foreign module | pytest |
| `docs/review/{REPOSITORY_MAP.md,REVIEWER_GUIDE.md,V8C_REVIEW_SNAPSHOT_MANIFEST_V1.json}` | new → PUSH | PUSH | this map, the reviewer guide and the machine-readable inventory | — |
| `data/{creator,discovery,forecast_broadcast,forward}/*.jsonl,*.json` (11) | **modified, already tracked** | KEEP_LOCAL | append-only runtime ledgers written by live cron; churn is not source change | see §C |
| `research/llm_matchup/out/hardening_v3/*` (3) | **modified, already tracked** | KEEP_LOCAL | generated golden-run output | regenerated by its producer |
| `.ssh/`, `.aws/`, `.git-credentials`, `.env`, `.env.cron`, `.bash_history` | untracked | KEEP_LOCAL | live credentials and shell state | now gitignored |
| `data/thestatsapi/` (~8,500 files) | untracked | KEEP_EXTERNAL | raw provider corpus | see §E |
| `handoff_out/`, `.npm/`, `.cache/`, `llama.cpp/`, `android-sdk/`, `RWA-Atlas-Claude/`, `rwa-atlas-audit/` | untracked | KEEP_LOCAL / UNRELATED | bulk artifacts, caches, unrelated projects | now gitignored |
| `v8a-worktree/`, `v8a1-worktree/` | untracked | KEEP_LOCAL | **active git worktrees** on `feat/v8a-*` branches, not stale copies | do not delete |

## C. Deprecation

| Path / component | Replacement | Evidence | Retention reason | Proposed next action |
|---|---|---|---|---|
| *(none proposed)* | — | — | — | — |

No deprecation is proposed in this pass. Specifically **not** deprecated:

- `hypothesis_v7` / `v71` — frozen upstream specifications that `v8c` imports verbatim. A newer
  version existing is not evidence of obsolescence.
- `hypothesis_v8b1` / `v8b2` — `v8c` imports `v8b1.controls` and `v8b1.search`, and the frozen
  V8B.1 selection freeze is the provenance root of the exposed-50 cohort. Renaming or moving
  these would invalidate existing manifests and provenance hashes.
- `src/research/matchup/run_*` — no caller found, which makes them deprecation *candidates*, not
  removable. They are the PHASE F/G record.

**Tracked `data/` files — action proposed, deliberately deferred.** 74 files / 4.1 MB under
`data/` are tracked. They are **not** all cron-written: per the per-file classification in §F,
13 are `MUTABLE_LEDGER` rewritten by cron and 17 are `OPERATIONAL_STATE` rewritten by scheduled
jobs — 30 of 74. The remaining 44 are configuration inputs, frozen evidence, preregistrations
and human reports that no scheduled job rewrites. Churn is therefore real but narrower than the
file count suggests (`predictions.jsonl` alone carries +170 uncommitted lines).

Untracking the churning subset would reduce noise, but `git rm --cached` could affect
deployment, freeze verification and reproducibility of prior evidence. **Deferred for an
explicit decision; nothing was untracked in this pass.** A `.gitignore` rule does not untrack an
already-tracked file, so the churn persists until that decision is made. The individual
retention classifications in §F stand unchanged, including the **15 `UNRESOLVED_DEPENDENCY`
files whose migration remains blocked** — see the named list at the end of §F.

## D. Remaining functional work

| Defect | Affected component | Evidence | Priority |
|---|---|---|---|
| **309 files hardcode `/home/ubuntu`** (13 in this snapshot) | repo-wide; `corpus_index`, `golden`, `harness`, most `run_*` | `grep -rIl '"/home/ubuntu' --include='*.py'` | **P1** — blocks any non-`/home/ubuntu` checkout. Executable *import* paths are now derived (see the row below); data roots, output roots and evidence paths are not |
| **Executable source root was environment-redirectable** — CLOSED | `src/_repo_paths.py` | reproduced: a dummy `multisrc_corpus` in a foreign tree was imported when `V8C_ROOT` pointed there. Now derived from the module's own `realpath` with no environment input; `tests/test_repo_paths.py` fails against the previous module | **RESOLVED** in this amendment. Scope is `sys.path` only — it changes no scientific logic and repairs none of the provenance rows below |
| ~~**Declared boto3 is stale/incompatible**~~ — **declaration corrected** | `pyproject.toml` | was `boto3==1.34.69` (predates Converse, added 1.34.83); now declares `1.43.93`, matching the deployed venv. Verified **offline** against the bundled botocore service model | **COMPLETED (declaration only).** No client was built and no Bedrock request was made, so *live execution against the declared SDK remains UNVERIFIED* — tracked as its own row below |
| **Live execution against the declared Bedrock SDK never exercised** | `bedrock_adapter.py`, `hardening/adapter_v4.py` | offline service-model inspection only; no client, no request | **P1** — a corrected dependency pin is not evidence the call path works |
| **Spend guards are example values, effectiveness unverified** | `.env.example` `BEDROCK_MAX_AI_CALLS`, `AWS_DAILY_TOKEN_QUOTA` | set to 0 in the template; enforcement path not traced | **P1** — a template default is not an enforced guard |
| **K=8 set-level control feasibility OPEN** | `control_coverage.py` | Hall minimum degree = 1 over exposed-50; universal guarantee only to k=1 | **P1** — blocks confirmatory readiness; not disproven |
| **Live model resolution never exercised** | `runner.py` | every run used a mocked transport | **P1** — blocks any paid-pilot claim |
| **50-fixture composed rehearsal incomplete** | `_run_v8c_exposed50_rehearsal_v3.py` | two runs launched and cancelled; composed path proven at 2 fixtures | **P2** — `DEVELOPMENT_REHEARSAL_READY` not assertable |
| Feature / provenance defects carried from review | `matchup/features.py`, provenance stamps | reviewer finding, not re-derived here | **P2** — needs its own pass |
| ~~**Foreign-source fingerprinting**~~ — CLOSED | `src/research/llm_matchup/hardening/golden_manifest.py`, `hardening/formation_structure.py` | was: `_SRC` (line 38) hardcoded `/home/ubuntu/src/research/llm_matchup/hardening`, so `current_generation_fingerprint` hashed `sampling.py`/`neutralize_v3.py` from the deployed tree whichever checkout executed. Reproduced in an independent checkout: fingerprint matched the DEPLOYED bytes, not the executing ones, and `check_compatible` returned `compatible: True` over a changed scientific source. Now each covered module's loaded `__file__` is verified against this checkout before its bytes are hashed; `tests/research/test_golden_manifest_source_binding.py` fails 6/7 against the previous modules | **RESOLVED.** Schema unchanged, values identical on this host (verified against the frozen 4.5 manifest). Scope is what the fingerprint *attests to* — it repairs none of the other provenance rows here. See `REPAIR_GOLDEN_V3_SOURCE_BINDING.md` |
| **Manifest/ledger output root still bound to the deployed tree** | `src/research/llm_matchup/hardening/golden_manifest.py` `OUT` (line 46) | the literal `/home/ubuntu/research/llm_matchup/out/hardening_v3`, so an independent checkout reads and writes the *deployed* manifest and execution ledger | **P1 — OPEN.** Deliberately **outside** the source-binding repair above, which changed only what the fingerprint attests to. Output/manifest path configuration, not executable source resolution |
| Universe build ~65–95 s/fixture | `universe.py` | measured | **P3** — 947 fixtures ≈ 18 h per process |
| `data/` ledger churn | repo hygiene | §F: 19 candidates, 15 blocked by provenance | **P3** — decision pending |
| ~~**Simultaneous-kickoff leakage**~~ — CLOSED in `matchup/features.py` | `src/research/matchup/features.py` `StrengthRatings` | reproduced: iterating `sorted(recs, key=kickoff_unix)` snapshotted and updated match-by-match, so every later match of a shared kickoff instant saw results that had not happened at its own kickoff. **3,008 of 5,319 corpus matches (56.55%) share a kickoff.** Fixed by snapshotting each simultaneity group before updating any of it. Corpus effect: **4,321 of 10,638 (40.62%) attack snapshots changed**; snapshots that moved on a mere input shuffle went **4,668 → 0** | **RESOLVED** for the matchup feature builders. `LeagueEnvironment`/`prior_rows` verified correct by test. See `REPAIR_MATCHUP_TEMPORAL_INTEGRITY.md` |
| ~~**Season-boundary behaviour**~~ — CLOSED in `matchup/features.py` | `src/research/matchup/features.py`, `matchup/design.py` | reproduced: `current_season()` returns the season the team LAST PLAYED IN, so a fixture early in a new season received prior-season form labelled as current-season and met the cold-start floor with stale data. **134 of 10,638 (fixture, team) pairs (1.26%)** are affected. `target_season(rec)` added and used by the three `design.py` builders; `_roll` now abstains | **RESOLVED** for the matchup feature builders. `current_season` deliberately unchanged — it has consumers outside this package and answers a different question |
| **Same season-boundary defect in the LLM evidence path** | `src/research/llm_matchup/cohorts.py` `HistoryIndex.current_season` | identical shape (`seasons[-1] if seasons else None` = season last played in), and this class — not `matchup/features.py` — is what `evidence.py`, `evidence_v2.py` and `phaseb_harness.py` use | **P1 — OPEN.** Deliberately not repaired: changing it alters evidence packet contents and therefore the frozen 4.5/4.6 generation fingerprints. That is a decision about regenerating frozen scientific artifacts, not a bug fix |
| Matchup harness artifacts predate the temporal-integrity fix | `matchup/` outputs from `run_experiments`, `run_gbt`, `gen_artifacts`, `run_phase_f_and_forensics`, `run_count_uncertainty` | feature values changed for 40.62% of rating snapshots, so anything the harness produced before that commit was computed under the leaking builder | **P1 — OPEN.** Nothing was regenerated here; comparability requires a re-run, which is an execution decision |
| Provenance bound to the wrong checkout | `src/research/hypothesis_v8c/{receipt,anchor}.py`, `research/hypothesis_engine/_run_v8c_exposed50_rehearsal_v3.py` | reproduced: cross-checkout import failure; `ROOT` is now derived, but all three still accept a `V8C_ROOT` override for the *tree* they fingerprint | **P1** — partially repaired, needs audit. Deliberately **untouched by this amendment**, which changed `sys.path` resolution only |
| ~~**Missing core-module bindings in the 4.6 freeze**~~ — CLOSED for the extracted cores | `src/research/llm_matchup/hardening/freeze_v3_sonnet46.py` | was: `MODULES` bound the thin wrappers `controls_v3_sonnet46.py` / `eligibility_v3_sonnet46.py` but not `controls_v3_core.py` / `eligibility_v3_core.py`, which hold the control definitions and eligibility rules they delegate to. Also silent omission of absent sources, and `SRC_DIR` on the deployed tree. Required set 19 → 22 (`+` both cores `+ resume_golden_v3.py`, whose `classify_bedrock_error` is recorded into control results at `controls_v3_core.py:115,135`); absence now raises; `SRC_DIR` follows the executing checkout; `verify_freeze()` added and enforced in `freeze()`'s reverify branch. **Amended** after a reviewer reproduced three gaps in the first version: a foreign core loaded under its real dotted name still verified OK (origins of the loaded module objects are now validated: **every distinct reference** — `sys.modules` and the wrappers' bound attributes — is retained and checked, deduplicated by object identity, after a further reviewer counterexample showed the first fix overwrote one with the other and passed a foreign registry with a local wrapper; reuses `golden_manifest._verified_source_path`); a missing or unsupported `freeze_contract_version` still verified OK (`SUPPORTED_CONTRACTS` is now enforced ahead of the hashes); and a differing `generation_hash` was printed as drift then returned as accepted (now `FreezeGenerationMismatch`, with the side file written first and the historical freeze untouched) | **RESOLVED for the demonstrated defect.** Contract `..._v2_core_bound`; declared failure order is contract → missing bindings → foreign origin → byte mismatch → generation drift, all fail-closed with diagnostics preserved on every path. Pre-repair freezes stay readable but are not certified. See `REPAIR_V46_FREEZE_CORE_BINDINGS.md` |
| **Remaining unbound `hardening/*.py` in the 4.6 freeze** | `freeze_v3_sonnet46.py` `MODULES` | 22 of 42 bound after the core-binding repair. `aggregate.py`, `feature_matrix.py` and `freeze_v3_sonnet46.py` itself are still not hashed; none is reachable from either extracted core, so none was part of that demonstrated defect | **P1 — OPEN.** Deliberately not repaired: closing it needs a coverage decision, not a binding fix |
| **The stored 4.6 freeze is stale, and nothing detected it** | `research/llm_matchup/out/FREEZE_LLM_MATCHUP_V3_SONNET46.json` | measured against the deployed tree it was built from, with no review branch involved: `controls_v3_sonnet46.py` and `eligibility_v3_sonnet46.py` have both changed since — **2 of 19 bound modules already drifted**. `freeze()` computed the drift flag and returned the stale manifest anyway | **P1 — OPEN.** Regenerating the freeze is an execution decision, not a repository-organization one; **not** done here, and not rebaselined |
| **Requested model ID presented as resolved identity** | `src/research/llm_matchup/hardening/adapter_v4.py` | lines 166–167: `resolved_model_id` reads the `x-amzn-bedrock-invocation-model-id` response header but **defaults to the requested `model_id`** when the header is absent, so the manifest can record a requested ID as though it were observed | **P1 — OPEN**, reviewer finding. **Not repaired by this amendment**; distinct from the V8C `runner.py` row below |
| V8C freeze binding breadth not re-audited | `src/research/hypothesis_v8c/freeze.py` `CODE_MODULES` (line 76) | separate subsystem from the 4.6 freeze above. `receipt.BOUND_SOURCES` was widened to 51 entries; `CODE_MODULES` was not re-audited against it | **P1** — carried from the V8C work, distinct finding |
| V8C runner never reported a live model identity | `src/research/hypothesis_v8c/runner.py` provenance | the mock transport reports `NOT_APPLICABLE_MOCK_TRANSPORT`; the live path was never exercised | **P1** — distinct from the `adapter_v4.py` fallback row above; here nothing is misreported, nothing is reported at all |
| Spend enforcement | Bedrock config | `.env.example` values only; enforcement path not traced | **P1** |
| Lock / preflight coverage differences | `src/research/llm_matchup/hardening/run_lock.py`, preflight | reviewer finding; not re-derived here | **P2** |

## E. External data

| Item | Detail |
|---|---|
| Purpose | Real football corpus for the research suites; without it those tests are `EXTERNAL_DEPENDENCY_REQUIRED` |
| Owner | Project operator (deployed host) |
| Location | Not in Git. Archive `V8C_DEV_EXPOSED50_HANDOFF_CORRECTED.tar.gz` |
| Integrity | SHA256 `ed6f8d37c769568802cf1d2dc2b1b6a70b41c661d75d27218a29173e3e0e8d78` |
| Layout | `data/thestatsapi/championship/` (season + per-fixture stats), `research/hypothesis_engine/` (selection freeze, fixture manifest, sealed-reserve ids), `research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json`, `loader_adapter/` |
| Supplied how | Transferred privately to an authorized environment; validated by `src/research/hypothesis_v8c/bundle_gate.py`, which verifies the digest, reads the manifest from inside the verified archive, requires an exact tree match, scans season files for sealed-reserve ids, and binds every loader root to the validated directory |
| Full corpus | ~8,500 files under `data/thestatsapi/` on the deployed host; not redistributed |

## F. Tracked `data/` retention — all 74 files classified individually

The earlier handoff called these "runtime ledgers". That was wrong: only 13 are.
**Nothing was untracked in this pass.** `KEEP_LOCAL` here describes a retention *proposal*,
not an action taken — the files remain tracked.

| Kind | N | Retention policy | Why |
|---|---|---|---|
| MODEL_CONFIG_INPUT | 18 | RETAIN_VERSIONED | capability/market/strategy contract read at runtime; behaviour depends on content |
| OPERATIONAL_STATE | 17 | CANDIDATE_RUNTIME_STORAGE | mutable operational state rewritten by scheduled jobs |
| MUTABLE_LEDGER | 13 | CANDIDATE_RUNTIME_STORAGE | append-only ledger rewritten by cron; churn is not source change |
| FROZEN_EVIDENCE | 12 | RETAIN_VERSIONED | scientific evidence; may be cited by manifests or prior reports |
| PREREGISTRATION_ATTESTATION | 7 | RETAIN_VERSIONED | preregistration/attestation — versioning is the point |
| HUMAN_REPORT | 4 | RETAIN_VERSIONED | small human-readable report; review material |
| REGENERABLE_CACHE | 3 | CANDIDATE_EXTERNAL_EVIDENCE | regenerable from the provider corpus |

**15 of the 74 are `UNRESOLVED_DEPENDENCY`** — referenced by a freeze or manifest
artifact, so moving or untracking them would break a provenance reference. Migration for
those is **blocked pending an explicit decision**, regardless of their kind.

| Retention policy | N |
|---|---|
| CANDIDATE_EXTERNAL_EVIDENCE | 3 |
| CANDIDATE_RUNTIME_STORAGE | 19 |
| RETAIN_VERSIONED | 37 |
| UNRESOLVED_DEPENDENCY | 15 |

### The 15 blocked migrations, named

Unchanged by this amendment. Each is referenced by a freeze or manifest artifact, so moving or
untracking it would break a provenance reference; all 15 remain `UNRESOLVED_DEPENDENCY` and
remain tracked.

| # | Path | Kind |
|---|---|---|
| 1 | `data/attestations/research_preregistrations.jsonl` | PREREGISTRATION_ATTESTATION |
| 2 | `data/creator/hypotheses.jsonl` | MUTABLE_LEDGER |
| 3 | `data/discovery/MM_CALIBRATION_AUDIT_REPORT.md` | HUMAN_REPORT |
| 4 | `data/discovery/corpus/_refresh_report.json` | OPERATIONAL_STATE |
| 5 | `data/discovery/corpus/manifest.json` | OPERATIONAL_STATE |
| 6 | `data/discovery/pilotC_discovery_log.jsonl` | MUTABLE_LEDGER |
| 7 | `data/discovery/pilotC_discovery_status.json` | OPERATIONAL_STATE |
| 8 | `data/discovery/pilotC_settled_log.json` | OPERATIONAL_STATE |
| 9 | `data/discovery/pilotC_stat_mixer.json` | MODEL_CONFIG_INPUT |
| 10 | `data/discovery/provider_league_registry.json` | OPERATIONAL_STATE |
| 11 | `data/forecast_broadcast/broadcasts.jsonl` | MUTABLE_LEDGER |
| 12 | `data/forward/commitments.jsonl` | MUTABLE_LEDGER |
| 13 | `data/forward/predictions.jsonl` | MUTABLE_LEDGER |
| 14 | `data/forward/run_log.jsonl` | MUTABLE_LEDGER |
| 15 | `data/results/leak_consumer_audit.md` | HUMAN_REPORT |

Per-file detail for all 74: `V8C_REVIEW_SNAPSHOT_MANIFEST_V1.json` → `tracked_data_inventory.files`.

---

## G. Source-root behaviour

Packaging only. This section states exactly what `src/_repo_paths.py` does, because the
previous behaviour was reproducibly wrong in a way that documentation had understated.

**What it does.** `REPO_ROOT` is `os.path.realpath()` of the directory one level above this
module's own directory — that is, the checkout the interpreter is executing. `SCRIPTS_DIR` is
`<REPO_ROOT>/scripts`. `ensure_repo_importable()` and `ensure_scripts_importable()` prepend
those to `sys.path` and return them. Re-derived for this amendment: **18 sites across 16
library modules** — 15 helper calls in 13 modules, plus 3 modules under
`prediction_engine/eval/` that import `SCRIPTS_DIR` as a module-level constant
(`baselines.py`, `walk_forward.py`, `candidate_cards_league_prior.py`). Those 3 are why a
validating override was rejected: a guard for them would have to fire at import time.

**What it cannot do.**

- **No environment variable can redirect it.** `V8C_ROOT` is not read by this module at all.
  The override previously applied here was reproducibly exploitable: with `V8C_ROOT` set to a
  foreign directory containing `scripts/multisrc_corpus.py`, the running checkout imported the
  foreign module. `tests/test_repo_paths.py` recreates that dummy, and fails against the
  previous version of the module with `AssertionError: the foreign dummy module was imported`.
- **No fallback.** There is no `/home/ubuntu` default, no parent-directory search and no
  second candidate root. If `scripts/` is not where the derivation says it is, the import fails
  where it always did.
- **No silent duplication.** Insertion is idempotent by *canonical* directory, so
  `<repo>/scripts` and `<repo>/scripts/../scripts` are recognised as one entry.

**What is out of scope, and still uses `V8C_ROOT`.** Data, output and provenance roots are a
separate concern and were not touched. `src/research/hypothesis_v8c/receipt.py`,
`src/research/hypothesis_v8c/anchor.py` and
`research/hypothesis_engine/_run_v8c_exposed50_rehearsal_v3.py` each still derive a *tree* root
with a `V8C_ROOT` override. Those are provenance and output roots, not `sys.path` entries, and
they remain open in §D. `V8C_ROOT` was confirmed unset in the live crontab, the deployed
environment and the shell profiles, so removing it from import resolution changes no scheduled
job's behaviour.

**What did not change.** No scientific logic, no module import order, no module names, no
deployed checkout and no production job.
