# Reviewer guide — engine snapshot for independent audit

**Base SHA:** `bb85637c27233dc5981b968430cbff3260cd3817` (tip of `feat/v8c-experiment-repair`)
**Branch:** `review/engine-snapshot-audit`
**Manifest:** `docs/review/V8C_REVIEW_SNAPSHOT_MANIFEST_V1.json`

This is a **map of the implementation as it exists**, not a proposed design, and not a
statement that the pipeline is ready. Where something is missing or unverified, it says so.

Throughout: *inspected* means I read the code or ran it; *unverified* means I did not.

---

## 1. Why the deployed tree was not fully in Git

The repository is checked out at `/home/ubuntu` on the deployed host, so the **repo root is
the user's home directory**. Credential stores (`.ssh/`, `.aws/`, `.git-credentials`,
`.env`), unrelated toolchains (`llama.cpp/`, `android-sdk/`), nested repository copies and
~8,500 files of raw provider corpus all sit beside the source tree.

That layout made routine `git add` unsafe, so working code accumulated untracked. At the
time of this snapshot: **20 modified tracked files and 8,685 untracked entries**. Of those,
48 are genuine engine source, tests, research entry points or findings artifacts; the rest are
data, caches, credentials or unrelated projects. (An earlier revision said 29, before the
file-by-file re-inspection recorded in `REPOSITORY_MAP.md` §B.)

`.gitignore` did **not** previously cover `.ssh/`, `.aws/`, `.git-credentials`, `.env.cron`
or `.bash_history`. No secret was ever committed (verified against tracked history), but a
single `git add -A` would have published live credentials. This snapshot hardens
`.gitignore` with narrow, path-anchored rules.

## 2. What this snapshot adds

**56 files**: source, tests, research entry points, diagnostics, four small findings
artifacts and the packaging/organisational files. No data, no credentials, no bulk generated
output. The number is the `PUSH` total of `V8C_REVIEW_SNAPSHOT_MANIFEST_V1.json`, which is the
per-file authority; earlier revisions of this guide quoted 29 and then 48 and are superseded.

| Group | Count | Why |
|---|---|---|
| Modified tracked source | 6 | `bedrock_adapter`, `adapter_v4`, `golden_manifest`, `resume_golden_v3`, `tests/conftest`, `test_golden_v3_resume` — interdependent with the new modules |
| Hardening modules (new) | 12 | The `llm_matchup/hardening` v3 package: atomic IO, run locking, controls, eligibility, freeze, golden, versions, pre-spend audit |
| Tests (new) | 7 | Including two leakage tests and a censoring-provenance test |
| `matchup` modules (new) | 4 | `features`, `harness`, `design`, `gen_artifacts` |
| `matchup` PHASE F/G experiments | 7 | run directly, not scheduled — EXPERIMENTAL |
| Leak-remediation diagnostics | 5 | `scripts/diagnose_*`, `*_9660.py` — EXPERIMENTAL |
| Benchmarks | 2 | `run_benchmark.py`, `run_robustness_check.py` — EXPERIMENTAL |
| Findings artifacts | 4 | reports + `robustness_results.json`, 64 KB total |
| Live-API probe | 1 | opt-in via `RUN_LIVE_API_TESTS=1` |
| Packaging & organisation | 8 | `.env.example` (placeholders only), hardened `.gitignore`, `pyproject.toml`, `src/_repo_paths.py`, `tests/test_repo_paths.py`, this guide, `REPOSITORY_MAP.md`, the manifest |

**48 snapshot files + 8 packaging/organisation files = 56 PUSH**, matching
`counts.by_disposition.PUSH` in the manifest. The other inventory entries are 14 `KEEP_LOCAL`
and 1 `KEEP_EXTERNAL` directory group, counted separately.

**Dependency completeness (inspected).** `src/research/matchup/harness.py` imports
`sklearn`, which was installed on the host but never declared. A clean checkout therefore
could not collect the research test tree. Now declared as `scikit-learn==1.9.0`, matching
the version in the deployed venv (`/home/ubuntu/.venv`).

## 3. Repository layout and entry points

```
src/research/hypothesis_v8c/     Gate-A experiment: grammar, universe, pre-T evaluability,
                                 PIT context, compiler, scorer, controls, freeze, anchor
src/research/hypothesis_v71/     upstream scientific dependencies (compiler, capability,
                                 corpus index, similarity, estimator)
src/research/hypothesis_v7/      frozen similarity + PIT specification
src/research/llm_matchup/        LLM matchup research, Bedrock adapter, hardening v3
src/research/matchup/            corpus loader, features, design, harness
scripts/                         provider adapters, cron entry points, diagnostics
research/hypothesis_engine/      experiment runners and versioned evidence artifacts
tests/research/                  the research test tree (3,631 tests collected)
```

**Operational entry points (from the live crontab — inspected, not modified):**

| Schedule | Command |
|---|---|
| every 15 min | `scripts/forecast_broadcast.py` |
| hourly | `scripts/fixture_alert_watcher.py` |
| every 4 h | `scripts/quarantine_forward_loop.py` |
| daily 00:00 UTC | `python -m src.cli daily-signals` → `scripts/signals_telegram_bot.py` |
| daily 00:30 | `scripts/sync_provider_leagues.py --refresh` |
| daily 07:10 | `scripts/forecast_broadcast.py --coverage` |
| Mon & Thu 06:00 | `scripts/pilotC_fixture_discovery.py` |
| Sun 04:20 | `scripts/refresh_corpus.py --all-leagues` |

Eight entries, re-read from the live crontab for this revision; an earlier revision listed
only the first five. All are tracked. They write to `data/` and `logs/`, which is why those
paths show as modified and are excluded here.

**Not scheduled.** `src/research/prospective/{cli,shadow_process,shadow_settle_process}.py` are
the real entry points of the prospective package and appear in **no** crontab entry.
`cli capture-due` is wrapped by the tracked `scripts/prospective_capture_run.sh`, and a `*/15`
cadence for it appears in `research/evaluation/prospective_*_report.md` as a *recommendation*
only. `scripts/pilotC_forward_loop.py` is likewise not scheduled. See `REPOSITORY_MAP.md` §A.

## 4. Stage map

Producer → artifact → consumer, with gaps named.

| Stage | Producer | Artifact | Consumer | Known gap |
|---|---|---|---|---|
| Fixture universe | `V8B1_FIXTURE_MANIFEST.json` | 1000-fixture manifest | selection | — |
| PIT evidence packet | `hypothesis_v8c/packet.py` | packet + hash | LLM runner | — |
| LLM selection | `hypothesis_v8c/runner.py` (Converse, injected transport) | submitted/accepted IDs | `select_freeze` | **never run against a live model**; all runs used a deterministic mocked transport |
| Deterministic search | `hypothesis_v8c/universe.py` | PRE_T_EVALUABLE set | runner tool | — |
| Controls R / H | `hypothesis_v8c/controls.py` | matched pairs | freeze | **K=8 set-level feasibility OPEN** — see below |
| Freeze + provenance | `select_freeze.py` | `freeze.json` + receipt | process 2 | — |
| External anchor | `anchor.py` | anchor committed to git | `score_frozen` | — |
| Verification + scoring | `score_frozen.py` | records | aggregation | — |
| Endpoint | `aggregate.py` | S-vs-R, S-vs-H | inference | development runs use the outcome-free `structural_diagnostics` path |
| Forecast / market | `scripts/forecast_broadcast.py` | broadcasts | Telegram | **not inspected in this task** |
| Prospective / shadow / settlement (Pilot C) | `scripts/pilotC_{forward_predict,forward_loop,settle}.py` | `data/forward/*`, `data/discovery/*` ledgers | `scripts/quarantine_forward_loop.py` (the only one in cron) | **not inspected in this task** |
| Prospective / shadow / settlement (package) | `src/research/prospective/{cli,shadow_process,shadow_settle_process}.py` | `data/prospective/*` captures, shadows, settlements | each other; `cli.py` invokes `shadow_settle_process` | **not inspected in this task**; **not scheduled** — see §3 |

The last two rows are honest gaps: this snapshot was assembled from the V8C repair work, and
I did not trace the forecast/settlement paths end to end. A reviewer should not read their
presence in the layout as a statement that they are verified.

## 5. Known failures and unfinished work

**Collection — resolved.** A fresh venv from `pip install -e ".[dev,bedrock,persistence]"`
collects **3,722 tests with 0 errors**. The earlier 5 errors were undeclared dependencies
(`hypothesis`, `sklearn`) and one more surfaced during verification (`psycopg2`); all are now
declared. Verified with `PYTHONPATH` unset and `PYTHONNOUSERSITE=1`.

**Isolation limitation, stated plainly.** No container or separate host was available, so the
fresh checkout still lives under `/home/ubuntu` and that path remains readable. Isolation was
therefore established by *explicit origin verification* rather than by the filesystem: every
project module, including `multisrc_corpus` and `championship_adapter`, was asserted to load
from the checkout, and `sys.path` was asserted to contain no deployed-tree entry. That is
weaker than true isolation and is reported as such.

**Source root — the override is closed.** The first repair derived the root from
`src/_repo_paths.py` but then let `V8C_ROOT` replace it, and a reviewer reproduced importing a
dummy `multisrc_corpus` from a foreign directory through that override. The module now derives
`REPO_ROOT` from its own canonical location and reads no environment variable at all; there is
no fallback and no `/home/ubuntu` default. `tests/test_repo_paths.py` covers it in isolated
subprocesses and fails against the previous module with *"the foreign dummy module was
imported"*. Full statement of the behaviour, including what deliberately still uses `V8C_ROOT`:
`REPOSITORY_MAP.md` §G.

See `REPOSITORY_MAP.md` §D for the full defect backlog, including 309 files that hardcode
`/home/ubuntu` for data, output and evidence roots. The stale `boto3==1.34.69` **declaration**
is corrected to `1.43.93`, matching the deployed venv and verified offline against the bundled
botocore service model; that is a packaging fix only, and **live execution against it remains
unverified** — no client was built and no Bedrock request was made.

**Unresolved scientific blockers (from the V8C work, carried forward):**

- **K=8 set-level control feasibility is OPEN.** Hall's minimum-degree test gives a universal
  guarantee only to k=1 over the exposed-50 universes (minimum degree 1). It is *not*
  disproven — the test is sufficient, not necessary — and the production greedy matcher
  achieved 8/8 on every probe tried. But unproven is OPEN, and it blocks confirmatory
  readiness. See `V8C_R_ACTION_SPACE_COVERAGE_V2.json`.
- **Live model resolution untested.** Every run used a mocked transport, so no resolved model
  identity has ever been reported by a real Bedrock call.
- **The 50-fixture composed rehearsal has not completed on the current code.** Two runs were
  launched and cancelled. The composed path is proven at 2 fixtures (smoke), not 50, so
  `DEVELOPMENT_REHEARSAL_READY` cannot honestly be asserted.

**Engineering blockers:** universe enumeration costs ~65–95 s per fixture, so any 50-fixture
pass is ~1 hour per process. At 947 fixtures that is ~18 h per process.

## 6. Setup and verification

```bash
git clone git@github.com:atlasrwa/football-quant-engine.git
cd football-quant-engine && git checkout review/engine-snapshot-audit
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,bedrock,persistence]"   # bedrock/persistence only if you need them

cp .env.example .env        # placeholders only; fill in locally, never commit

# collection (3,722 collected, 0 errors in a correctly provisioned venv)
python -m pytest tests/research/ --collect-only -q

# packaging regression: the source root resolves to THIS checkout (fast, offline)
python -m pytest tests/test_repo_paths.py -q

# the reviewer's original reproducer
python -m pytest tests/research/test_matchup_leakage.py -q

# the legacy live-API probe: collects, and skips unless RUN_LIVE_API_TESTS=1
python -m pytest test_hypothesis_layer_real_api.py -q -rs

# the 7 tests added by this snapshot
python -m pytest tests/research/test_controls_v3_core.py \
  tests/research/test_controls_v3_censoring_provenance.py \
  tests/research/test_eligibility_v3_core.py \
  tests/research/test_formation_leakage.py \
  tests/research/test_formation_policy.py \
  tests/research/test_golden_v3_sonnet46.py \
  tests/research/test_matchup_leakage.py -q

# the V8C suite
python -m pytest tests/research/hypothesis_v8c/ -q
```

`tests/research/hypothesis_v8c/` runs offline on synthetic fixtures. The 7 tests above are
slower (~10 min) because they build a corpus index.

## 7. External data

The research suites that need real football data read a provider cache that is **not in
Git** (~8,500 files). It is supplied out of band as a digest-pinned archive:

- **Archive:** `V8C_DEV_EXPOSED50_HANDOFF_CORRECTED.tar.gz`
- **SHA256:** `ed6f8d37c769568802cf1d2dc2b1b6a70b41c661d75d27218a29173e3e0e8d78`
- **Layout:** `data/thestatsapi/championship/` (season files + per-fixture stats),
  `research/hypothesis_engine/` (selection freeze, fixture manifest, sealed-reserve id list),
  `research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json`, `loader_adapter/`
- **Validation:** `src/research/hypothesis_v8c/bundle_gate.py` verifies the archive digest,
  reads the manifest from *inside* the verified archive, requires an exact tree match, scans
  season files for sealed-reserve ids, and binds every loader root to the validated directory.

Raw data is deliberately **not** uploaded to Git to make tests pass.

## 8. Credentials

Variable **names only** are in `.env.example`. No values are committed anywhere.

- **Local / server:** copy `.env.example` to `.env` and fill in. `.env` is gitignored.
- **AWS:** Bedrock credentials come from the instance role / OIDC / `~/.aws`, never from
  `.env`. `.aws/` is now gitignored.
- **GitHub Actions:** no workflow in this snapshot requires live credentials, and this task
  created and altered no secrets, roles or workflows.

> **GitHub Actions secrets are not automatically available to external reviewers or to the
> deployed server.** A reviewer cloning this branch gets no credentials and cannot make
> provider or model calls. That is intended.

## 9. Scope of this task

Review preparation only. No merge, no deployment, no paid API call, no experiment start, no
pipeline implementation. The deployed checkout at `/home/ubuntu` was not switched, reset or
cleaned, and no production cron job was interrupted.
