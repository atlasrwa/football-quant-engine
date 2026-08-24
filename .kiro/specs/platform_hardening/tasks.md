# Tasks: Platform Hardening & Anti-Overfitting Suite

#[[file:design.md]]

## Phase 1: Data Provider Abstraction Layer

- [x] Task 1: Create `src/engine/data/__init__.py` with exports
- [x] Task 2: Implement `src/engine/data/base.py` — `MATCH_RECORD_SCHEMA`, `BaseDataLoader` ABC, `validate_schema()`
- [x] Task 3: Implement `src/engine/data/footystats.py` — `FootyStatsAdapter` with declarative column mapping
- [x] Task 4: Implement `src/engine/data/synthetic.py` — `SyntheticDataLoader` with configurable edge cases

## Phase 2: FDR & Anti-p-Hacking

- [x] Task 5: Create `src/engine/fdr.py` — `FDRResult` dataclass, `FDRController` with BH procedure
- [x] Task 6: Implement `QuarantineStatus` enum and `QuarantineEntry` dataclass
- [x] Task 7: Implement `QuarantineTracker` — enter/check/promote lifecycle

## Phase 3: Market Friction Engine

- [x] Task 8: Create `src/engine/friction.py` — `MarketFrictionConfig` with margin/slippage/liquidity settings
- [x] Task 9: Implement `FrictionAdjustedBacktester._apply_vig()` — margin deduction
- [x] Task 10: Implement `FrictionAdjustedBacktester._apply_slippage()` — line drag model
- [x] Task 11: Implement `FrictionAdjustedBacktester._cap_stake()` — liquidity enforcement
- [x] Task 12: Implement `FrictionAdjustedBacktester.run()` — orchestrate friction pipeline

## Phase 4: Strategy Builder

- [x] Task 13: Create `src/engine/builder.py` — `StrategyBuilder` class with fluent API
- [x] Task 14: Implement `build()` validation and Strategy production
- [x] Task 15: Implement `to_json()` / `from_json()` / `from_dict()` serialization

## Phase 5: Tests

- [x] Task 16: Create `tests/test_data_adapter.py` — test all data loaders
- [x] Task 17: Create `tests/test_fdr_control.py` — test BH procedure + quarantine
- [x] Task 18: Create `tests/test_market_friction.py` — test vig, slippage, liquidity, full friction backtest
- [x] Task 19: Create `tests/test_builder.py` — test strategy builder + serialization

## Phase 6: Integration & Verification

- [x] Task 20: Update `src/engine/__init__.py` exports
- [x] Task 21: Run full test suite — verify all 264+ existing tests still pass
- [x] Task 22: Push to main
