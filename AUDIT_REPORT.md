# AUDIT REPORT — Football Quant Engine

**Date:** 2026-08-24  
**Baseline:** 449 tests passing, 0 failures  
**Commit:** 0746c1b (football-quant-engine/main)

---

## Current Architecture

```
src/
├── models/           # Core domain: Match, MatchFeatures, StrategyConfig, BacktestResult
├── features/         # Feature calculators: rolling_form, xg_efficiency, referee_volatility, assembler
├── backtest/         # Walk-forward engine: engine, signal, metrics, staking, cross_validation, bet_log
├── ingestion/        # Data pipeline: provider (MockProvider), pipeline, client, cache, validator
├── engine/
│   ├── xmetrics.py   # Vectorized xC/xB/xO formulas
│   ├── evaluator.py  # Strategy condition evaluation (safe dispatch, no eval)
│   ├── backtest.py   # x-Metric walk-forward backtester
│   ├── validator.py  # Statistical validator (t-test, Cohen's d, CI)
│   ├── fdr.py        # Benjamini-Hochberg FDR + QuarantineTracker
│   ├── friction.py   # Market friction (vig, slippage, liquidity)
│   ├── builder.py    # No-code strategy builder (fluent API + JSON)
│   ├── data/         # BaseDataLoader, FootyStatsAdapter, SyntheticDataLoader, FootyStatsAPIClient
│   ├── metrics/      # Beat the Bookie (BTBR, vig-adjusted edge, confidence index)
│   └── signals/      # CryptoSignalExporter, CommunityBroadcaster, DeepLinker
├── api/
│   └── routes/       # builder.py (compile/result), builder_ui.py (templates)
data/
└── strategies/benchmarks/  # 10 seed strategies (4 xC, 3 xB, 3 xO)
tests/                      # 449 tests across 20 test files
```

---

## CRITICAL BUGS (Must Fix Before Any Release)

### C1: Temporal Leakage in `compute_xO()` — League Baseline Uses Future Data

**File:** `src/engine/xmetrics.py` lines 128-131  
**Issue:** `league_baseline = mean(all_hli)` computes the mean across the ENTIRE DataFrame including rows representing future matches. When the backtester pre-computes x-Metrics before the walk-forward loop, xO values for early matches are contaminated by data from later matches.  
**Impact:** Backtest results for xO strategies are unreliable. Any published xO signal carries look-ahead bias.  
**Fix:** Compute league baseline using an expanding window (cumulative mean up to each row) or rolling window.

### C2: Temporal Leakage in `RefereeVolatilityCalculator` — Global Two-Pass

**File:** `src/features/referee_volatility.py` lines 55-103  
**Issue:** Pass 1 accumulates ALL goals per referee across the entire match list. Pass 2 assigns the resulting volatility to every match. A match on matchday 5 gets a volatility computed from matchdays 1–380.  
**Impact:** Referee volatility feature is contaminated by future data. The existing walk-forward engine uses this feature for staking and signal generation.  
**Fix:** Rewrite as an expanding/rolling calculation — volatility at time T uses only matches before T.

### C3: Synthetic Odds Fabrication (Silent 1.90 Default)

**File:** `src/engine/evaluator.py` lines 219-226  
**Issue:** When odds data is NaN or the column is missing, the evaluator silently returns 1.90 decimal odds. This creates phantom betting opportunities and corrupts P&L calculations.  
**Impact:** Backtest ROI is unreliable when data has missing odds. Signals are generated for matches where no real odds exist.  
**Fix:** Return `None` / `NO_SIGNAL` when odds are missing. Propagate missing odds as signal suppression.

### C4: Fake CLV (Model Edge Mislabeled as Closing Line Value)

**File:** `src/engine/backtest.py` line 164, `src/engine/friction.py` line 189  
**Issue:** `clv = signal.edge * 100.0` — this is NOT Closing Line Value. The signal "edge" is the mean normalized distance from strategy thresholds (a geometric measure). Real CLV requires closing odds data.  
**Impact:** The `avg_clv_pct` metric in backtest results is meaningless. Beat the Bookie metrics built on this are misleading.  
**Fix:** Rename field to `model_edge_pct`. Implement real CLV only when closing odds are available.

### C5: Hardcoded `fdr_validated=True` in Community Broadcaster

**File:** `src/engine/signals/community_broadcaster.py` line 98  
**Issue:** Every broadcast signal unconditionally gets `fdr_validated=True`, regardless of whether FDR validation or quarantine was ever performed. The QuarantineTracker is completely disconnected from the broadcaster.  
**Impact:** Community receives signals falsely labeled as "FDR-VALIDATED" with a green badge. Violates trust.  
**Fix:** Wire QuarantineTracker into broadcaster. Only mark validated if the authoritative validator says so.

---

## HIGH-RISK QUANT ISSUES

### H1: Heuristic Probability for Kelly Sizing

**File:** `src/engine/signals/crypto_exporter.py` lines 215-224  
**Issue:** `_estimate_win_prob = implied + edge * 0.1` — arbitrary 0.1 scaling of a geometric edge metric fed into Kelly formula. No calibration, no empirical basis.  
**Risk:** Community members receive stake sizing recommendations based on numerology.  
**Recommendation:** Replace with risk-unit tiers (0.25U/0.50U/1.00U) for retail. Remove Kelly from public-facing outputs until calibrated probabilities are available.

### H2: No Strategy Identity or Versioning

**Files:** Entire codebase  
**Issue:** Strategies are tracked only by `name: str`. No `strategy_id`, `strategy_version`, `creator_id`, `created_at`, or `parent_strategy_id` exists anywhere.  
**Risk:** Cannot reproduce results. Cannot track mutations. Cannot build social features (follows, copies, provenance).  
**Recommendation:** Add frozen identity fields before any social feature work.

### H3: No PredictionEvent Domain Object

**Issue:** Individual predictions are logged as `BetRecord` / `XBetRecord` — flat tuples with no timestamp, no strategy version, no proof hash, no settlement lifecycle.  
**Risk:** Cannot implement paper betting, leaderboards, CLV tracking, or on-chain proofs from current data structures.

### H4: QuarantineTracker Is Disconnected

**File:** `src/engine/fdr.py`  
**Issue:** The quarantine system is fully implemented but never consumed by any downstream system (broadcaster, builder, API). It exists only in unit tests.  
**Impact:** The 90-day quarantine concept is architectural fiction — no strategy actually goes through it.

---

## MEDIUM ISSUES

### M1: In-Memory Job Store (Unbounded, No Persistence)

**File:** `src/api/routes/builder.py` line 18  
**Issue:** `_job_store: dict[str, dict] = {}` grows indefinitely. No TTL, no eviction, no persistence. Lost on restart.

### M2: Hardcoded Market Line (2.5)

**File:** `src/ingestion/provider.py` line 130  
**Issue:** `over_under_line=2.5` is hardcoded with a comment "override if present" but no override logic exists. Also in `footystats.py _compute_derived()`.

### M3: BACK/LAY Direction Always Gets 1.90 Odds

**File:** `src/engine/evaluator.py` lines 212-216  
**Issue:** `_get_odds_column()` returns `None` for BACK/LAY, triggering the 1.90 fallback.

### M4: xO Computation Returns 0 When PPDA is 0 (Not NaN)

**File:** `src/engine/xmetrics.py` lines 135-136  
**Issue:** `np.where(ppda != 0, 1.0/ppda, 0.0)` — a PPDA of 0 is likely missing data, should be NaN not 0.

### M5: No Authentication on API Endpoints

**Files:** `src/api/routes/builder.py`, `builder_ui.py`  
**Issue:** All endpoints are unauthenticated — any caller can compile strategies and poll results.

---

## TECHNICAL DEBT

| Area | Issue |
|------|-------|
| Dependencies | `pydantic==2.6.1` declared but never used in core code |
| Test isolation | Some tests read from `data/strategies/benchmarks/` (coupling tests to file system) |
| Duplicate backtest logic | `src/backtest/engine.py` and `src/engine/backtest.py` are parallel systems |
| Duplicate signal logic | `src/backtest/signal.py` (old) and `src/engine/evaluator.py` (new) |
| No type checking | No mypy/pyright configuration |
| No linting | No ruff/flake8 configuration |
| Untyped API models | `src/api/routes/builder.py` uses hand-written classes, not Pydantic models |

---

## DUPLICATE SYSTEMS

| System A | System B | Resolution |
|----------|----------|------------|
| `src/backtest/engine.py` (WalkForwardEngine) | `src/engine/backtest.py` (XMetricBacktester) | Keep both — different input models |
| `src/backtest/signal.py` (SignalGenerator) | `src/engine/evaluator.py` (StrategyEvaluator) | Keep both — different paradigms |
| `src/ingestion/client.py` (FootyStatsClient) | `src/engine/data/footystats_api.py` (FootyStatsAPIClient) | Consolidate under data/ |

---

## MISSING ABSTRACTIONS

1. **PredictionEvent** — canonical prediction record with lifecycle
2. **StrategyIdentity** — ID, version, creator, provenance
3. **StrategyLifecycle** — state machine (DRAFT → ... → LIVE)
4. **MarketEvent** — entry odds, closing odds, settlement
5. **JobRepository** — persistent job storage interface
6. **UserProfile** — social identity, reputation
7. **PaperBetPosition** — virtual bankroll tracking

---

## PRODUCT GAPS

1. No user identity system
2. No paper betting
3. No leaderboard
4. No strategy provenance (copy/fork tracking)
5. No real CLV tracking (requires closing odds feed)
6. No strategy lifecycle enforcement
7. No gamification (challenges, streaks, competitions)
8. No reputation engine
9. No subscription/tier enforcement

---

## RECOMMENDED IMPLEMENTATION ORDER

| Phase | Scope | Priority |
|-------|-------|----------|
| **Phase 1** | Fix C1-C5, H1 (integrity) | IMMEDIATE |
| **Phase 2** | PredictionEvent, StrategyIdentity, Lifecycle, Versioning | HIGH |
| **Phase 3** | JobRepository abstraction, API Pydantic models | MEDIUM |
| **Phase 4** | Social domain (User, Profile, Follow, PaperBet, Leaderboard) | MEDIUM |
| **Phase 5** | Live odds adapter, real CLV, market snapshots | MEDIUM |
| **Phase 6** | Advanced validation (CPCV, regime testing, calibration) | LOW |
| **Phase 7** | LLM strategy compiler, wallet identity, on-chain proofs | LOW |
| **Phase 8** | Marketplace, creator rewards, subscriptions | DEFERRED |
