# Tasks: FootyStats Live API Client, Crypto-Native Signal Exporter & Beat the Bookie Metrics

#[[file:design.md]]

## Phase 1: Live API Client

- [x] Task 1: Create `src/engine/data/footystats_api.py` — `TokenBucket` rate limiter
- [x] Task 2: Implement `FootyStatsAPIClient` with disk caching and retry logic
- [x] Task 3: Implement endpoint methods: `get_todays_matches`, `get_match`, `get_league_referees`
- [x] Task 4: Wire API output through existing `FootyStatsAdapter`

## Phase 2: Beat the Bookie Metrics

- [x] Task 5: Create `src/engine/metrics/__init__.py` and `src/engine/metrics/bookie.py`
- [x] Task 6: Implement `BookieMetrics` dataclass
- [x] Task 7: Implement `BookieMetricsCalculator.compute_btbr()`
- [x] Task 8: Implement `BookieMetricsCalculator.compute_vig_adjusted_edge()`
- [x] Task 9: Implement `BookieMetricsCalculator.compute_confidence_index()`
- [x] Task 10: Implement `BookieMetricsCalculator.compute()` orchestrator

## Phase 3: Crypto Signal Exporter

- [x] Task 11: Create `src/engine/signals/__init__.py` and `src/engine/signals/crypto_exporter.py`
- [x] Task 12: Implement `KellyCalculator` with quarter-Kelly cap
- [x] Task 13: Implement `ProofOfAlpha.generate_hash()`
- [x] Task 14: Implement `CryptoSignalExporter.format_telegram()` and `format_discord()`
- [x] Task 15: Implement `CryptoSignalExporter.dispatch()` with dry-run support

## Phase 4: FastAPI Builder Endpoint

- [x] Task 16: Create `src/api/__init__.py` and `src/api/routes/__init__.py`
- [x] Task 17: Implement `POST /api/v1/builder/compile` with Pydantic models
- [x] Task 18: Implement `GET /api/v1/builder/result/{job_id}` polling endpoint

## Phase 5: Tests

- [x] Task 19: Create `tests/test_footystats_api.py` — rate limiter, caching, retry
- [x] Task 20: Create `tests/test_bookie_metrics.py` — BTBR, vig edge, confidence
- [x] Task 21: Create `tests/test_crypto_exporter.py` — Kelly, hash, webhook format

## Phase 6: Integration

- [x] Task 22: Update dependencies in `pyproject.toml`
- [x] Task 23: Verify all tests pass and push to main
