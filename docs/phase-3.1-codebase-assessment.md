# Phase 3.1 Codebase Assessment

**Generated:** 2026-08-24
**Purpose:** Pre-implementation assessment of the football-quant-engine repository before Phase 3.1 architectural changes.

---

## 1. Current Architecture Overview

The project is a **pure Python 3.12 library** (`football-quant-engine 0.1.0`) installed in editable mode. It has:

- **No web server running.** FastAPI is listed as an optional dependency (`[api]`) but is NOT installed.
- **No database.** All persistence is file-based (JSON/JSONL in `data/`).
- **No authentication.** No user model, no sessions, no tokens.
- **No migration framework.** No Alembic, no SQL files, no schema management.
- **No Docker.** Docker is not installed on the host.
- **No repository pattern.** Domain objects are created in-memory and optionally serialized to JSON files.

PostgreSQL 16 client is installed but the server is NOT installed (only `postgresql-client-16`).

### Technology Stack

| Layer | Technology | Status |
|-------|-----------|--------|
| Language | Python 3.12.3 | Installed |
| Package Manager | pip + setuptools | Active |
| Test Framework | pytest 8.0.2 + pytest-asyncio 0.23.5 | Active, 727 tests passing |
| HTTP Client | httpx 0.27.0 | Installed |
| Data | numpy 1.26.4, pandas 2.2.1, scipy 1.12.0 | Installed |
| Validation | pydantic 2.6.1 | Installed (unused — domain uses dataclasses) |
| Web Framework | FastAPI 0.109.2 | NOT installed (optional dep) |
| Auth Libraries | PyJWT 2.7.0, bcrypt 3.2.2 | Pre-installed system-wide |
| Database | PostgreSQL 16 client only | Server NOT installed |
| ORM/Driver | None | Nothing installed |
| Migration | None | No framework present |
| Virtual Env | `.venv/` | Active |

### File Structure (relevant)

```
/home/ubuntu/
├── pyproject.toml            # Build config, dependencies
├── src/
│   ├── __init__.py
│   ├── api/                  # Stub API (no FastAPI app created)
│   │   ├── routes/
│   │   │   ├── builder.py   # Strategy compile functions (not wired to router)
│   │   │   └── builder_ui.py # Benchmark strategy templates
│   ├── backtest/             # Walk-forward backtest engine (Phase 1)
│   ├── cli.py                # CLI entry point (5 subcommands)
│   ├── domain/               # Phase 2 domain objects (immutable dataclasses)
│   ├── engine/               # xMetric engine, evaluator, backtest, FDR, signals
│   ├── features/             # Feature calculators (xG eff, form, referee vol)
│   ├── ingestion/            # Cache, client, pipeline, provider, validator
│   ├── models/               # Core dataclasses (Match, MatchFeatures, config, results)
│   └── serializer.py         # JSON output
├── tests/                    # 727 tests, all passing
│   ├── conftest.py           # SyntheticMatchGenerator, tmp dirs
│   ├── fixtures/             # 4759_2023.json (sample data)
│   └── test_*.py             # 27 test files
├── data/
│   ├── raw/                  # File-based match cache (JSON per match)
│   ├── errors/               # Validation error JSONL
│   ├── features/             # (empty/unused)
│   ├── results/              # Backtest result JSON files
│   └── strategies/benchmarks/ # 10 benchmark strategy JSON files
└── docs/                     # Game docs (unrelated Survivor Royale)
```

---

## 2. Relevant Existing Modules

### A. Persistence Layer

**Current: File-based, no database.**

| Component | Storage | Location |
|-----------|---------|----------|
| `CacheManager` | JSON files per match | `data/raw/{league}_{season}_{id}.json` |
| `SchemaValidator` | Error JSONL log | `data/errors/validation_errors.jsonl` |
| `serializer.save_result()` | Backtest result JSON | `data/results/backtest_*.json` |
| `BetLogger.to_jsonl()` | Bet log JSONL | configurable path |
| Benchmark strategies | JSON files | `data/strategies/benchmarks/*.json` |
| `_job_store` (builder.py) | In-memory dict | Lost on process exit |

**No ORM. No SQL. No connection pooling. No transactions.**

### B. Domain Layer

All domain objects are **frozen dataclasses** (`frozen=True, slots=True`):

| Module | Objects |
|--------|---------|
| `src/models/match.py` | `Match` |
| `src/models/features.py` | `MatchFeatures` |
| `src/models/config.py` | `StrategyConfig` |
| `src/models/results.py` | `BetRecord`, `FoldResult`, `BacktestResult` |
| `src/domain/prediction.py` | `PredictionEvent`, `PredictionStatus`, `PredictionSource` |
| `src/domain/settlement.py` | `Settlement`, `SettlementOutcome` |
| `src/domain/provenance.py` | `DatasetVersion`, `FeatureVersion`, `ModelVersion` |
| `src/domain/backtest_run.py` | `BacktestRun`, `BacktestStatus`, `ValidationRun`, `ValidationStatus` |
| `src/domain/market.py` | `MarketDefinition`, `MarketPrice`, `MarketType`, `PriceSide`, `PriceType` |
| `src/engine/evaluator.py` | `Condition`, `Strategy`, `Signal` |
| `src/engine/backtest.py` | `XBacktestConfig`, `XBetRecord`, `FoldMetrics`, `XBacktestResult`, `StrategyIdentityInfo` |
| `src/engine/strategy_identity.py` | `StrategyIdentity`, `StrategyRegistry` |
| `src/engine/fdr.py` | `FDRResult`, `FDRController`, `QuarantineEntry`, `QuarantineStatus`, `QuarantineTracker` |
| `src/engine/validator.py` | `ValidationCriteria`, `ValidationVerdict` |
| `src/engine/settlement_service.py` | `MatchResult`, `SettlementResult`, `PredictionSettlementService` |
| `src/engine/friction.py` | `MarketFrictionConfig` |
| `src/engine/metrics/bookie.py` | `BookieMetrics` |
| `src/engine/signals/crypto_exporter.py` | `SignalPayload`, `DispatchResult`, `ProofOfAlpha`, `KellyCalculator` |
| `src/engine/signals/deeplinker.py` | `DeepLink`, `DeepLinkConfig` |

**Key observation:** All state is in-memory during execution and discarded. No persistence boundary exists.

### C. API Layer

**Status: Stub only. No running FastAPI application.**

- `src/api/routes/builder.py` defines `CompileRequest`, `CompileResponse`, `BacktestResultResponse` as plain classes (not Pydantic models).
- Functions `compile_strategy()`, `get_result()`, `update_job()` operate on an in-memory `_job_store` dict.
- No router, no middleware, no dependency injection, no app instance.
- FastAPI is not even installed in the current environment.

### D. Test Architecture

- **Framework:** pytest 8.0.2 + pytest-asyncio 0.23.5
- **Count:** 727 tests across 27 files
- **Execution time:** ~18 seconds
- **All passing** as of assessment time.
- **Fixtures:** `SyntheticMatchGenerator` produces deterministic `Match` lists. `tmp_cache_dir`, `tmp_errors_dir` provide temp filesystem.
- **No mocking framework** beyond stdlib. No database fixtures. No integration test containers.
- **Coverage:** Not measured (no pytest-cov configured).

### E. Migration Mechanism

**None exists.** No Alembic, no raw SQL migration directory, no versioning scheme. This is a greenfield implementation.

### F. Authentication Approach

**None exists.** No user model, no auth middleware, no token generation. PyJWT and bcrypt are available system-wide but unused by the project.

### G. API Framework

**FastAPI declared but not installed.** Listed under `[project.optional-dependencies.api]`:
```
fastapi==0.109.2
uvicorn==0.27.1
```
Neither is in the active environment. No app instance exists.

### H. Database Configuration

**None.** No connection strings, no environment variables referencing PostgreSQL, no ORM config. The `.env.example` and `.env.local` files belong to a separate project (Survivor Royale/Next.js game) co-located in the same repo.

### I. CLI Behavior

`src/cli.py` provides 5 subcommands:

| Command | Behavior | Auth Required |
|---------|----------|---------------|
| `ingest` | Fetch matches from API or fixtures, cache to JSON files | No |
| `features` | Run FeatureAssembler on ingested matches | No |
| `backtest` | Full pipeline → BacktestResult → JSON output | No |
| `run` | Same as backtest with progress display | No |
| `daily-signals` | Live signal generation → append to JSONL | No |

Common args: `--league-id`, `--season`, `--verbose`, `--config-file`, `--mode`.

**No `--user` flag. No authentication. Operates anonymously.**

---

## 3. Conflicts Discovered

| # | Conflict | Resolution Strategy |
|---|----------|-------------------|
| 1 | **No PostgreSQL server** — only client installed | Install `postgresql-16` server, create database, create roles. |
| 2 | **No database driver** — asyncpg/psycopg not installed | Add `asyncpg`, `sqlalchemy` (for Alembic only), `alembic` to dependencies. |
| 3 | **No FastAPI installed** — API layer cannot function | Install `fastapi`, `uvicorn`, `python-multipart` (for form data). |
| 4 | **Match.id is an integer (FootyStats ID)** — used directly throughout engine as the identity key | Create adapter: internal surrogate UUID for DB, but engine continues using `Match.id` (integer) without modification. Mapping table: `external_id → match_id`. |
| 5 | **StrategyRegistry is in-memory** — `_strategies` dict lost on exit | Wrap with PostgreSQL repository. Registry becomes a cache/facade over the DB. |
| 6 | **PredictionSettlementService is in-memory** — `_pending`, `_settlements` dicts | Wrap with PostgreSQL repository. Service logic untouched; storage swapped via injection. |
| 7 | **QuarantineTracker is in-memory** — `_entries` dict | Same pattern: repository adapter beneath existing interface. |
| 8 | **builder.py uses plain classes not Pydantic** — incompatible with FastAPI validation | Create proper Pydantic request/response models for the API layer. Leave builder.py untouched. |
| 9 | **CI workflow is Node.js only** — no Python CI | Add Python test job to CI or create separate workflow. (Not blocking for Phase 3.1.) |
| 10 | **Co-located unrelated project** — Survivor Royale Next.js game shares repo root | Ignore entirely. Phase 3.1 only touches `src/`, `tests/`, `docs/`, `migrations/`, `pyproject.toml`. |
| 11 | **`data/` directory used for file persistence** — will coexist with PostgreSQL | No conflict: file cache remains for CLI offline mode. PostgreSQL is the authoritative store for API mode. |

---

## 4. Proposed Compatibility Adapters

### Adapter 1: Match Identity Bridge

```
Engine expects: Match(id=12345, ...)  [integer, FootyStats-specific]
Database has:   matches(match_id=UUID, external_id=12345, external_source='footystats')
```

**Solution:** The repository loads from DB and constructs `Match` objects using `external_id` as the `id` field. The engine never sees UUIDs. The DB uses its own surrogate PK internally for foreign keys.

### Adapter 2: Strategy Registry Persistence

```
Current: StrategyRegistry._strategies: dict[str, List[StrategyIdentity]]
Phase 3: strategies + strategy_versions tables
```

**Solution:** Create `PostgresStrategyRepository` that implements the same interface as `StrategyRegistry` but reads/writes PostgreSQL. Existing `StrategyRegistry` remains for in-memory test usage. `_compute_hash()` is reused verbatim.

### Adapter 3: Settlement Service Persistence

```
Current: PredictionSettlementService._pending, _settlements, _all_predictions (dicts)
Phase 3: predictions + settlements tables
```

**Solution:** Create `PersistentSettlementService` wrapping `PredictionSettlementService`. On `register_prediction()`, also INSERT to DB. On `settle_match()`, also INSERT settlement + UPDATE prediction status. Idempotency enforced by UNIQUE constraint.

### Adapter 4: CLI Authentication

```
Current: CLI operates without auth
Phase 3: All writes require user context
```

**Solution:** Add `--user` flag to CLI. Default: system user UUID. When `--user` is provided, set `app.user_id` session variable. CLI bypasses JWT (trusted local execution). API uses JWT.

### Adapter 5: API Layer Bootstrap

```
Current: No FastAPI app exists
Phase 3: Full REST API with auth, middleware, routes
```

**Solution:** Create `src/api/app.py` with FastAPI application. Wire existing builder logic + new auth/strategy/user routes. Existing `builder.py` functions become service-layer calls invoked by proper route handlers.

---

## 5. Environment Requirements for Phase 3.1

### Must Install

| Package | Purpose | Version |
|---------|---------|---------|
| `postgresql-16` | Database server | System package |
| `asyncpg` | Async PostgreSQL driver | 0.29.x |
| `alembic` | Migration framework | 1.13.x |
| `sqlalchemy` | Alembic metadata + migration DSL | 2.0.x |
| `fastapi` | Web framework | 0.109.2 (pinned) |
| `uvicorn` | ASGI server | 0.27.1 (pinned) |
| `python-multipart` | Form data parsing | Latest |
| `passlib[bcrypt]` | Password hashing | Latest |

### Database Setup Required

```
1. Install postgresql-16 server
2. Create database: football_quant_engine
3. Create roles: fqe_app, fqe_readonly
4. Enable extensions: uuid-ossp or pgcrypto (for gen_random_uuid)
5. Run migrations
```

---

## 6. Risk Assessment

| Risk | Probability | Impact | Mitigation |
|------|------------|--------|------------|
| Existing tests break from import changes | Low | High | Run full suite after each file touch. No engine module modifications. |
| PostgreSQL server unavailable in environment | Medium | Blocking | Install as first step; fall back to SQLite for local dev if needed. |
| Content hash divergence between registry and DB | Low | Critical | Single implementation: reuse `StrategyRegistry._compute_hash()` everywhere. |
| Match ID type mismatch (int vs UUID) | Medium | Medium | Adapter pattern: engine uses int, DB uses bigint surrogate. |
| CLI backward incompatibility | Low | Medium | `--user` defaults to system user; no behavior change without flag. |

---

## 7. Conclusion

The codebase is clean, well-structured, and test-rich. It has **zero existing persistence infrastructure** beyond file-based JSON caching. Phase 3.1 is a greenfield database/API implementation that wraps the existing engine via adapters. No engine code requires modification.

**Recommended implementation approach:**
1. Install PostgreSQL server + Python dependencies
2. Create migration framework (Alembic or raw SQL with version tracking)
3. Build tables in dependency order
4. Create repository interfaces + PostgreSQL implementations
5. Create FastAPI app with auth middleware
6. Wire routes using repositories
7. Verify all 727 existing tests still pass
