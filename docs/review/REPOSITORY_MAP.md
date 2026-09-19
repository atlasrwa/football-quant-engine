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
| Forecast commitments | `scripts/pilotC_forward_predict.py` → `data/forward/commitments.jsonl` | ACTIVE | UNVERIFIED | entry point exists; execution not traced |
| Prospective capture | `scripts/pilotC_forward_loop.py`, `scripts/quarantine_forward_loop.py` (cron, 4 h) | ACTIVE | UNVERIFIED | entry point exists; execution not traced |
| Shadow / closing evaluation | `scripts/pilotC_settle.py` (closing observation + evaluation) | ACTIVE | UNVERIFIED | entry point exists; execution not traced |
| Settlement | `scripts/pilotC_settle.py` → `data/discovery/pilotC_settled_log.json` | ACTIVE | UNVERIFIED | entry point exists; execution not traced |
| Publication | `scripts/forecast_broadcast.py` (cron, 15 min), `scripts/signals_telegram_bot.py` (cron, daily) | ACTIVE | UNVERIFIED | entry point exists; execution not traced |
| Scheduling & ops | crontab → `scripts/{forecast_broadcast,fixture_alert_watcher,quarantine_forward_loop,signals_telegram_bot,sync_provider_leagues}.py` | ACTIVE | VERIFIED_OFFLINE — all tracked, entry points exist | jobs run on the deployed host only |
| Matchup research (PHASE F/G) | `src/research/matchup/run_*.py` | EXPERIMENTAL | UNVERIFIED | run directly; not scheduled |
| Leak-remediation diagnostics | `scripts/diagnose_*.py`, `*_9660.py` | EXPERIMENTAL | UNVERIFIED | read cached corpus; no network |
| Live-API integration probe | `test_hypothesis_layer_real_api.py` | EXPERIMENTAL | EXTERNAL_DEPENDENCY_REQUIRED | opt-in via `RUN_LIVE_API_TESTS=1`; real key + charges |

**No authoritative implementation exists** for an end-to-end "fixture → forecast → settlement"
pipeline. V8C (hypothesis selection), hardening v3 (golden LLM runs) and the champion
forecasting path are **three separate capabilities** that share football data. They are not
versions of one another and must not be collapsed.

## B. File disposition

Exact paths. `PUSH` = in this branch. Counts: **48 PUSH**, 14 KEEP_LOCAL, 0 HOLD.

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
| `.gitignore`, `.env.example`, `pyproject.toml` | modified/new → PUSH | PUSH | hygiene, placeholder config, sklearn declaration | — |
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

**Tracked runtime ledgers — action proposed, deliberately deferred.** 74 files / 4.1 MB under
`data/` are tracked and rewritten by cron (`predictions.jsonl` alone carries +170 uncommitted
lines). Untracking them would reduce churn, but `git rm --cached` could affect deployment,
freeze verification and reproducibility of prior evidence. **Deferred for an explicit decision;
nothing was untracked in this pass.** A `.gitignore` rule does not untrack an already-tracked
file, so the churn persists until that decision is made.

## D. Remaining functional work

| Defect | Affected component | Evidence | Priority |
|---|---|---|---|
| **309 files hardcode `/home/ubuntu`** (13 in this snapshot) | repo-wide; `corpus_index`, `golden`, `harness`, most `run_*` | `grep -rIl '"/home/ubuntu' --include='*.py'` | **P1** — blocks any non-`/home/ubuntu` checkout; already forced ROOT-derivation fixes in `receipt.py`, `anchor.py`, the rehearsal harness |
| **Declared boto3 is stale/incompatible** | `pyproject.toml` vs deployed venv | declared `boto3==1.34.69`; installed `1.43.93` | **P1** — a clean `pip install -e .` gives an SDK the deployed code is not running against |
| **Spend guards are example values, effectiveness unverified** | `.env.example` `BEDROCK_MAX_AI_CALLS`, `AWS_DAILY_TOKEN_QUOTA` | set to 0 in the template; enforcement path not traced | **P1** — a template default is not an enforced guard |
| **K=8 set-level control feasibility OPEN** | `control_coverage.py` | Hall minimum degree = 1 over exposed-50; universal guarantee only to k=1 | **P1** — blocks confirmatory readiness; not disproven |
| **Live model resolution never exercised** | `runner.py` | every run used a mocked transport | **P1** — blocks any paid-pilot claim |
| **50-fixture composed rehearsal incomplete** | `_run_v8c_exposed50_rehearsal_v3.py` | two runs launched and cancelled; composed path proven at 2 fixtures | **P2** — `DEVELOPMENT_REHEARSAL_READY` not assertable |
| Feature / provenance defects carried from review | `matchup/features.py`, provenance stamps | reviewer finding, not re-derived here | **P2** — needs its own pass |
| Universe build ~65–95 s/fixture | `universe.py` | measured | **P3** — 947 fixtures ≈ 18 h per process |
| `data/` ledger churn | repo hygiene | §F: 19 candidates, 15 blocked by provenance | **P3** — decision pending |
| Simultaneous-kickoff leakage | evaluation / feature build | reviewer finding; not re-derived here | **P1** |
| Season-boundary behaviour | corpus / feature windows | reviewer finding; not re-derived here | **P1** |
| Provenance bound to the wrong checkout | `receipt.py`, `anchor.py` | reproduced: cross-checkout import failure; ROOT now derived | **P1** — partially repaired, needs audit |
| Missing scientific dependencies in freeze bindings | `freeze.py` `CODE_MODULES` | reviewer finding; `BOUND_SOURCES` widened to 51, `CODE_MODULES` not re-audited | **P1** |
| Requested vs observed model identity | `runner.py` provenance | mock transport reports `NOT_APPLICABLE_MOCK_TRANSPORT`; live never exercised | **P1** |
| Spend enforcement | Bedrock config | `.env.example` values only; enforcement path not traced | **P1** |
| Lock / preflight coverage differences | `run_lock.py`, preflight | reviewer finding; not re-derived here | **P2** |

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

Per-file detail: `V8C_REVIEW_SNAPSHOT_MANIFEST_V1.json` → `tracked_data_inventory.files`.
