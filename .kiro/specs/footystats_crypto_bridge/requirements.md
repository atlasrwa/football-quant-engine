# Requirements: FootyStats Live API Client, Crypto-Native Signal Exporter & Beat the Bookie Metrics

## Overview

Integrate the live FootyStats JSON API into the data pipeline, build a crypto-native webhook/Discord signal dispatch system for betting communities, and expose "Beat the Bookie" (CLV Edge %, Bookie-Crushing Yield) as primary public-facing metrics.

## Functional Requirements

### FR-1: Live FootyStats API Client
- **FR-1.1:** Implement async HTTP client for FootyStats JSON API with endpoints:
  - `GET /todays-matches` — fetch upcoming daily fixtures across leagues.
  - `GET /match` — pull detailed event stats per match.
  - `GET /league-referees` — fetch referee cards-per-foul data for xB model.
- **FR-1.2:** Implement token-bucket rate limiting at 60 requests/minute (configurable).
- **FR-1.3:** Implement disk-based caching (`diskcache`) to avoid duplicate API credit consumption. Cache TTL configurable (default: 1 hour for live matches, 24 hours for historical).
- **FR-1.4:** Route API JSON responses through `FootyStatsAdapter` to produce standardized `MatchRecord` DataFrames.
- **FR-1.5:** Exponential backoff retry on 429/5xx responses (max 3 retries).
- **FR-1.6:** API key management via environment variable `FOOTYSTATS_API_KEY`.

### FR-2: Beat the Bookie Metric Suite
- **FR-2.1:** Compute **Beat the Bookie Rate (BTBR %)**: percentage of signals where entry odds > closing odds.
- **FR-2.2:** Compute **Vig-Adjusted Edge %**: expected ROI after deducting market-specific bookmaker hold.
- **FR-2.3:** Compute **Confidence Index (0–100)**: inverse transform of FDR-adjusted p-value: `100 × (1 - p_adjusted)`.
- **FR-2.4:** Aggregate metrics at strategy level and per-signal level.
- **FR-2.5:** Return `BookieMetrics` dataclass with all three metrics plus supporting stats.

### FR-3: Crypto-Native Signal Exporter
- **FR-3.1:** Format live `Signal` objects into structured webhook payloads for Telegram and Discord.
- **FR-3.2:** Payload includes: match details, market line, recommended unit stake (Kelly fraction), Beat the Bookie Edge %, and FDR-Validated badge.
- **FR-3.3:** Dispatch payloads to configurable webhook URLs via async HTTP POST.
- **FR-3.4:** Implement **Proof-of-Alpha** cryptographic hasher: SHA-256 of `(strategy_json + unix_timestamp + validation_verdict_json)` for on-chain verifiable strategy commitments.
- **FR-3.5:** Kelly fraction calculation: `f* = (p*b - q) / b` where `p` = estimated win probability, `b` = decimal odds - 1, `q` = 1 - p. Cap at 0.25 (quarter-Kelly).
- **FR-3.6:** Support dry-run mode (format payload without dispatching).

### FR-4: No-Code Web Builder API Endpoint
- **FR-4.1:** Expose `POST /api/v1/builder/compile` FastAPI endpoint accepting JSON form data.
- **FR-4.2:** Convert form submission into valid `Strategy` object via `StrategyBuilder`.
- **FR-4.3:** Kick off asynchronous backtest via `FrictionAdjustedBacktester` and return job ID.
- **FR-4.4:** Expose `GET /api/v1/builder/result/{job_id}` to poll backtest results.
- **FR-4.5:** Input validation using Pydantic request models.

## Non-Functional Requirements

### NFR-1: Resilience
- API client must handle network timeouts (30s default), rate-limit responses, and partial data gracefully.
- Webhook dispatch failures must not crash the signal pipeline — log and continue.

### NFR-2: Security
- API keys never logged or included in error messages.
- Webhook URLs stored as environment variables, not hardcoded.
- Proof-of-Alpha hashes are deterministic and verifiable.

### NFR-3: Performance
- Rate limiter must not block the event loop (async-compatible).
- Disk cache lookups < 5ms for warm reads.
- Signal formatting < 1ms per signal.

### NFR-4: Backward Compatibility
- All existing tests (361) must continue passing.
- New modules are additive — no changes to existing engine interfaces.

### NFR-5: Dependencies
- Add `diskcache`, `fastapi`, `uvicorn` to optional dependencies.
- Core modules (metrics, exporter) depend only on stdlib + existing deps.
