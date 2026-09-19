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
29 files are genuine engine source or tests; the rest are data, caches, credentials or
unrelated projects.

`.gitignore` did **not** previously cover `.ssh/`, `.aws/`, `.git-credentials`, `.env.cron`
or `.bash_history`. No secret was ever committed (verified against tracked history), but a
single `git add -A` would have published live credentials. This snapshot hardens
`.gitignore` with narrow, path-anchored rules.

## 2. What this snapshot adds

**29 files**, all source or tests. No data, no credentials, no generated artifacts.

| Group | Count | Why |
|---|---|---|
| Modified tracked source | 6 | `bedrock_adapter`, `adapter_v4`, `golden_manifest`, `resume_golden_v3`, `tests/conftest`, `test_golden_v3_resume` — interdependent with the new modules |
| Hardening modules (new) | 12 | The `llm_matchup/hardening` v3 package: atomic IO, run locking, controls, eligibility, freeze, golden, versions, pre-spend audit |
| Tests (new) | 7 | Including two leakage tests and a censoring-provenance test |
| `matchup` modules (new) | 4 | `features`, `harness`, `design`, `gen_artifacts` |

Plus: `.env.example` (placeholders only), hardened `.gitignore`, `scikit-learn` added to
`pyproject.toml`, this guide, and the manifest.

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
| daily 00:00 | `python -m src.cli daily-signals` → `scripts/signals_telegram_bot.py` |
| daily 00:30 | `scripts/sync_provider_leagues.py --refresh` |

All are tracked. They write to `data/` and `logs/`, which is why those paths show as
modified and are excluded here.

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
| Prospective / shadow / settlement | `data/forward/*`, `data/discovery/*` | ledgers | cron loops | **not inspected in this task** |

The last two rows are honest gaps: this snapshot was assembled from the V8C repair work, and
I did not trace the forecast/settlement paths end to end. A reviewer should not read their
presence in the layout as a statement that they are verified.

## 5. Known failures and unfinished work

**Collection errors (5) — pre-existing, not introduced here.** `tests/research/` fails to
collect 5 modules for `ModuleNotFoundError: hypothesis` / `sklearn` under the *system*
Python. Identical errors occur on the deployed tree, so this is an environment gap, not a
regression. Both are installed in `/home/ubuntu/.venv`; `sklearn` is now declared in
`pyproject.toml` and `hypothesis` was already in the dev extras.

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
pip install -e ".[dev]"

cp .env.example .env        # placeholders only; fill in locally, never commit

# collection (expect the 5 pre-existing errors only if deps are missing)
python -m pytest tests/research/ --collect-only -q

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
