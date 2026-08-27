# Phase 3.1 Test Matrix

## Summary

| Suite | Count | Status |
|-------|-------|--------|
| Existing engine tests | 727 | ALL PASS |
| Phase 3.1 integration tests | 104 | ALL PASS |
| **Total** | **831** | **ALL PASS** |

## Existing Engine Tests (727 — UNCHANGED)

All original test files remain unmodified:

| File | Tests | Coverage |
|------|-------|----------|
| test_models.py | Match, MatchFeatures, StrategyConfig, BetRecord validation |
| test_features.py | XGEfficiency, RollingForm, RefereeVolatility calculators |
| test_backtest.py | StakingCalculator, SignalGenerator, BetLogger, Metrics, CV, WalkForward |
| test_integrity_gate.py | 8 critical invariants (temporal leakage, missing odds, quarantine, hash, determinism) |
| test_trust_boundaries.py | 6 trust boundary tests (validation, closing odds, proof hash, settlement, sources) |
| test_settlement_idempotency.py | Settlement service idempotency + conflict detection |
| test_prediction_lifecycle.py | PredictionEvent immutability, lifecycle transitions |
| test_integration_pipeline.py | Full provenance chain integration |
| test_xbacktest.py | XMetricBacktester walk-forward execution |
| test_xmetrics.py | xC, xB, xO vectorized computation |
| test_evaluator.py | Strategy condition evaluation |
| test_builder.py | StrategyBuilder fluent API |
| test_validator.py | StatisticalValidator t-test, Cohen's d, CI |
| test_fdr_control.py | FDRController Benjamini-Hochberg |
| test_market_friction.py | FrictionAdjustedBacktester |
| test_bookie_metrics.py | BookieMetrics (BTBR, vig-adjusted edge) |
| test_community_broadcaster.py | Signal broadcast formatting |
| test_crypto_exporter.py | Kelly staking, proof-of-alpha |
| test_deeplinker.py | Platform deep-link generation |
| test_data_adapter.py | FootyStatsAdapter, SyntheticDataLoader |
| test_footystats_api.py | API client rate limiting, caching |
| test_ingestion.py | Cache, validator, pipeline |
| test_integration.py | End-to-end CLI pipeline |
| test_domain.py | Domain object serialization |
| test_integrity.py | Phase 1 regression invariants |

## Phase 3.1 Integration Tests (104)

### A. Users (tests/integration/test_users.py) — 9 tests
- [x] Create user
- [x] Duplicate username rejected (case-insensitive)
- [x] Duplicate email rejected (case-insensitive)
- [x] NULL email allowed for multiple users
- [x] Username lookup case-insensitive
- [x] Nonexistent user returns None
- [x] Disable user (status change)
- [x] Invalid status rejected (CHECK constraint)
- [x] System user exists after migration

### B. Auth (tests/integration/test_auth.py) — 11 tests
- [x] Password hash and verify
- [x] Wrong password fails
- [x] Hash is not plaintext
- [x] JWT create and decode
- [x] Expired token rejected
- [x] Invalid token rejected
- [x] Tampered token rejected
- [x] Admin role in token
- [x] System context properties
- [x] User context not admin
- [x] Context is immutable (frozen)

### C. Event Log (tests/integration/test_event_log.py) — 7 tests
- [x] Append event
- [x] Append with JSONB payload
- [x] Multiple events per aggregate
- [x] UPDATE has no effect (RLS blocks)
- [x] DELETE has no effect (RLS blocks)
- [x] Actor ID stored correctly
- [x] Invalid actor_type rejected (CHECK)

### D. Idempotency (tests/integration/test_idempotency.py) — 6 tests
- [x] Store and retrieve
- [x] Nonexistent returns None
- [x] Duplicate key rejected
- [x] Same key different user allowed
- [x] Expired key not returned
- [x] Cleanup removes only expired

### E. Matches (tests/integration/test_matches.py) — 8 tests
- [x] Insert match
- [x] Duplicate external_id same source rejected
- [x] Same external_id different source allowed
- [x] total_goals generated correctly
- [x] Negative goals rejected
- [x] Invalid odds rejected
- [x] NULL odds allowed
- [x] Raw data JSONB stored

### F. Match Repository (tests/integration/test_match_repository.py) — 12 tests
- [x] Basic round-trip
- [x] NULL optional fields
- [x] Retrieved match is frozen dataclass
- [x] Engine uses external_id (not surrogate)
- [x] Surrogate ID lookup
- [x] Get by surrogate returns Match
- [x] Different sources coexist
- [x] Upsert updates goals
- [x] Upsert preserves surrogate ID
- [x] List returns chronological order
- [x] List filters by league and season
- [x] **Engine compatibility (FeatureAssembler produces valid features)**

### G. Strategies (tests/integration/test_strategies.py) — 17 tests
- [x] Content hash matches StrategyRegistry._compute_hash() exactly
- [x] Different definitions → different hashes
- [x] Hash is deterministic
- [x] Hash independent of JSON key order
- [x] Create strategy
- [x] owner_id immutable (trigger)
- [x] Visibility change allowed
- [x] Create first version (v=1)
- [x] Version auto-increments
- [x] Duplicate content_hash detectable (app-level dedup)
- [x] Version definition immutable (trigger)
- [x] Deprecation allowed (lifecycle field)
- [x] Get latest version
- [x] Create fork with lineage
- [x] Fork update blocked (RLS)
- [x] Fork delete blocked (RLS)
- [x] Fork lineage lookup

### H. Event Service (tests/integration/test_event_service.py) — 5 tests
- [x] Emit returns event ID
- [x] Emit with payload stored correctly
- [x] Correlation ID groups events
- [x] All event types are valid strings
- [x] Event visible within transaction

### I. Idempotency Service (tests/integration/test_idempotency_service.py) — 10 tests
- [x] New key returns None
- [x] Existing key same hash returns cached
- [x] Existing key different hash raises conflict
- [x] Store succeeds
- [x] Duplicate store raises
- [x] Request hash deterministic
- [x] Key order independent
- [x] Different values → different hash
- [x] Hash is SHA-256 (64 chars)
- [x] Concurrent version creation: no duplicate numbers
- [x] Content hash detectable for dedup

### J. API (tests/integration/test_api.py) — 18 tests
- [x] Health check
- [x] Register success
- [x] Register duplicate username (409)
- [x] Login success
- [x] Login wrong password (401)
- [x] Get /me authenticated
- [x] Get /me unauthenticated (401)
- [x] Create strategy (201)
- [x] Create strategy requires auth (401)
- [x] Get own strategy
- [x] Get strategy version
- [x] Update visibility
- [x] Fork strategy
- [x] Idempotency: duplicate returns cached
- [x] Idempotency: different body → 409
- [x] Correlation ID in response
- [x] Client-provided correlation ID preserved
- [x] **IDOR: cannot read other user's private strategy (404)**

## Invariant Preservation

| # | Invariant | Status |
|---|-----------|--------|
| I1 | xO temporal leakage | PASS (test_integrity_gate.py) |
| I2 | Referee temporal leakage | PASS |
| I3 | Missing odds → NO_SIGNAL | PASS |
| I4 | Missing closing odds → CLV unavailable | PASS |
| I5 | Quarantine promotion gate | PASS |
| I6 | Content hash integrity | PASS |
| I7 | Deterministic results | PASS |
| I8 | fdr_validated not forgeable | PASS (test_trust_boundaries.py) |
| I9 | Closing odds from MatchResult only | PASS |
| I10 | Proof hash computed server-side | PASS |
| I11 | Settlement outcome computed not provided | PASS |
| I12 | Backtest/live separation | PASS |
| I13 | No synthetic data fabrication | PASS |
| I14 | Settlement idempotency | PASS (test_settlement_idempotency.py) |
