# ARCHITECTURE MAP — Football Quant Engine

## Module Dependency Graph

```
src/models/          ← Pure domain objects (no external deps)
    │
    ├── Match        ← Input data model
    ├── MatchFeatures← Feature vectors
    ├── StrategyConfig← Backtest parameters
    └── BacktestResult← Output model

src/ingestion/       ← Data acquisition layer
    │
    ├── provider.py     Protocol + MockProvider (fixture-based)
    ├── pipeline.py     Orchestrator (fetch → cache → validate → parse)
    ├── client.py       Async HTTP (FootyStats legacy)
    ├── cache.py        File-based JSON cache
    └── validator.py    Schema validation + error logging

src/features/        ← Feature computation layer
    │
    ├── assembler.py           Orchestrates calculators → MatchFeatures
    ├── rolling_form.py        ✓ Temporal (look-ahead free)
    ├── xg_efficiency.py       ✓ Temporal (look-ahead free)
    └── referee_volatility.py  ⚠ GLOBAL (uses future data)

src/backtest/        ← Original O/U backtest engine
    │
    ├── engine.py       WalkForwardEngine (orchestrator)
    ├── signal.py       SignalGenerator (heuristic composite)
    ├── metrics.py      MetricsAggregator (ROI, Sharpe, p-value)
    ├── staking.py      StakingCalculator (variance-based)
    ├── cross_validation.py  TemporalCrossValidator (fold generator)
    └── bet_log.py      BetLogger (accumulate + serialize)

src/engine/          ← x-Metric execution layer (newer)
    │
    ├── xmetrics.py     XMetricEngine (xC, xB, xO formulas)
    ├── evaluator.py    StrategyEvaluator (safe condition dispatch)
    ├── backtest.py     XMetricBacktester (walk-forward) + StrategyIdentityInfo
    ├── validator.py    StatisticalValidator (t-test, CI)
    ├── fdr.py          FDRController + QuarantineTracker
    ├── friction.py     FrictionAdjustedBacktester
    ├── builder.py      StrategyBuilder (fluent + JSON)
    ├── strategy_identity.py  StrategyIdentity + StrategyRegistry
    ├── orchestrator.py      BacktestOrchestrator (provenance chain)
    ├── settlement_service.py PredictionSettlementService (idempotent)
    ├── quarantine_bridge.py  QuarantineSettlementBridge (paper P&L)
    ├── data/
    │   ├── base.py          BaseDataLoader ABC + schema
    │   ├── footystats.py    FootyStatsAdapter (declarative mapping)
    │   ├── footystats_api.py  Live API client (rate limit + cache)
    │   └── synthetic.py     SyntheticDataLoader (stress test)
    ├── metrics/
    │   └── bookie.py        BookieMetricsCalculator (BTBR, confidence)
    └── signals/
        ├── crypto_exporter.py    CryptoSignalExporter + Kelly + ProofOfAlpha
        ├── community_broadcaster.py  CommunityBroadcaster
        └── deeplinker.py        DeepLinker (Stake/Rollbit/Polymarket)

src/domain/          ← Phase 2 domain model (immutable, persistence-free)
    │
    ├── prediction.py       PredictionEvent + PredictionStatus + PredictionSource
    ├── settlement.py       Settlement + SettlementOutcome
    ├── provenance.py       DatasetVersion + FeatureVersion + ModelVersion
    ├── backtest_run.py     BacktestRun + ValidationRun
    ├── market.py           MarketDefinition + MarketPrice
    ├── factories.py        PredictionEventFactory + SettlementFactory
    └── provenance_builder.py  ProvenanceBuilder

src/api/             ← HTTP API layer
    └── routes/
        ├── builder.py      compile/result (in-memory job store)
        └── builder_ui.py   Templates endpoint (10 benchmarks)

data/
├── raw/             .gitkeep
├── features/        .gitkeep
├── results/         Backtest output JSONs
├── errors/          Validation error logs
├── cache/           Disk cache for API
└── strategies/benchmarks/  10 seed strategy JSONs
```

## Data Flow (End-to-End)

```
1. Raw Data
   └─► FootyStatsAdapter / SyntheticDataLoader / MockProvider
        └─► Canonical DataFrame (MATCH_RECORD_SCHEMA)

2. Feature Computation
   └─► XMetricEngine.compute_all()
        └─► DataFrame + [home_xC, away_xC, home_xB, away_xB, home_xO, away_xO]

3. Strategy Evaluation
   └─► StrategyEvaluator.evaluate(df, strategies)
        └─► List[Signal] (match_index, direction, edge, odds)

4. Backtesting
   └─► XMetricBacktester.run() OR FrictionAdjustedBacktester.run()
        └─► XBacktestResult (bets, folds, metrics)
   └─► BacktestOrchestrator.run() [with provenance]
        └─► OrchestratedBacktestResult (provenance + PredictionEvents)

5. Validation
   └─► StatisticalValidator.validate(bets) → ValidationVerdict
   └─► FDRController.correct(p_values) → FDRResult[]

6. Prediction Emission
   └─► PredictionEventFactory.from_signal() → PredictionEvent (PENDING)
   └─► PredictionEventFactory.from_backtest_bet() → PredictionEvent (SETTLED)

7. Distribution
   └─► CommunityBroadcaster / CryptoSignalExporter
        └─► Telegram/Discord webhooks + PredictionEvent

8. Settlement (idempotent)
   └─► PredictionSettlementService.settle_match(MatchResult)
        └─► Settlement (WIN/LOSS/VOID/PUSH)
        └─► Callbacks (quarantine bridge)

9. Quarantine (wired via settlement bridge)
   └─► QuarantineSettlementBridge._on_settlement()
        └─► QuarantineTracker.update_paper_pnl()
        └─► promote() / reject() after 90 days
```

## Entry Points

| Entry Point | Location | Type |
|-------------|----------|------|
| CLI | `src/cli.py` | argparse (ingest, features, backtest, run, daily-signals) |
| API | `src/api/routes/builder.py` | compile_strategy(), get_result() |
| API | `src/api/routes/builder_ui.py` | get_templates() |
| Library | `src/engine/__init__.py` | Python imports |

## External Dependencies

| Dependency | Version | Used By |
|-----------|---------|---------|
| httpx | 0.27.0 | API clients (ingestion, signals) |
| numpy | 1.26.4 | All numeric computation |
| scipy | 1.12.0 | t-tests, statistical validation |
| pydantic | 2.6.1 | Declared but unused in core |
| pandas | 2.2.1 | x-Metric engine, data adapters |
| pytest | 8.0.2 | Testing (dev) |
| pytest-asyncio | 0.23.5 | Async test support (dev) |
