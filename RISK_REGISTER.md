# RISK REGISTER — Football Quant Engine

## Severity Scale

| Level | Definition |
|-------|-----------|
| **CRITICAL** | Invalidates quantitative results. Must fix before any public use. |
| **HIGH** | Creates misleading outputs or violates trust assumptions. |
| **MEDIUM** | Architectural weakness that limits scalability or correctness. |
| **LOW** | Technical debt that should be addressed but doesn't corrupt results. |

---

## CRITICAL RISKS

| ID | Risk | Location | Impact | Mitigation |
|----|------|----------|--------|------------|
| R01 | **xO temporal leakage** — league_baseline computed from all rows (past + future) | `src/engine/xmetrics.py:128-131` | All xO backtest results are unreliable | Replace with expanding-window mean |
| R02 | **Referee volatility temporal leakage** — two-pass algorithm uses entire match history | `src/features/referee_volatility.py:55-103` | Referee feature contaminates all backtests using it | Rewrite as rolling/expanding computation |
| R03 | **Synthetic odds (1.90)** — missing odds silently replaced with arbitrary value | `src/engine/evaluator.py:219-226` | Fabricates betting opportunities, corrupts P&L | Return None → suppress signal |
| R04 | **Fake CLV** — `signal.edge * 100` labeled as Closing Line Value | `src/engine/backtest.py:164` | `avg_clv_pct` metric is meaningless | Rename to `model_edge_pct` |
| R05 | **Hardcoded validation badge** — `fdr_validated=True` on all broadcasts | `src/engine/signals/community_broadcaster.py:98` | False trust signal to community | Wire QuarantineTracker |

## HIGH RISKS

| ID | Risk | Location | Impact | Mitigation |
|----|------|----------|--------|------------|
| R06 | **Heuristic Kelly** — `implied + edge * 0.1` probability estimate | `src/engine/signals/crypto_exporter.py:215-224` | Unsafe stake recommendations | Replace with risk-unit tiers |
| R07 | **No strategy identity** — strategies tracked by name only | Entire codebase | Cannot version, reproduce, or track | Add strategy_id + version |
| R08 | **No PredictionEvent** — predictions are flat BetRecords | `src/engine/backtest.py` | Cannot build social/paper betting | Create canonical domain object |
| R09 | **Disconnected quarantine** — QuarantineTracker unused by any consumer | `src/engine/fdr.py` | Lifecycle is unenforceable | Integrate into broadcaster + API |
| R10 | **BACK/LAY always 1.90** — no odds column mapped for these directions | `src/engine/evaluator.py:212-216` | BACK/LAY strategies always get fabricated odds | Extend odds column mapping |

## MEDIUM RISKS

| ID | Risk | Location | Impact | Mitigation |
|----|------|----------|--------|------------|
| R11 | **In-memory job store** — unbounded dict, no persistence | `src/api/routes/builder.py:18` | Memory leak, data loss on restart | Implement JobRepository interface |
| R12 | **Hardcoded market line 2.5** — never overridden from source data | `src/ingestion/provider.py:130` | Settlement against wrong line | Parse actual line from data |
| R13 | **No user authentication** — API endpoints open to all | `src/api/routes/` | Unauthorized access | Add auth middleware |
| R14 | **Duplicate ingestion clients** — FootyStatsClient + FootyStatsAPIClient | `src/ingestion/client.py` + `src/engine/data/footystats_api.py` | Maintenance burden | Consolidate |
| R15 | **PPDA=0 treated as 0 not NaN** — division edge case in xO | `src/engine/xmetrics.py:135` | Masks missing data | Treat as NaN |

## LOW RISKS

| ID | Risk | Location | Impact | Mitigation |
|----|------|----------|--------|------------|
| R16 | Pydantic declared but unused | `pyproject.toml` | Wasted dependency | Remove or use |
| R17 | No type-checking CI | Project config | Type bugs possible | Add mypy |
| R18 | Test coupling to filesystem benchmarks | `tests/test_deeplinker.py` | Fragile tests | Use fixtures |
| R19 | No API versioning enforcement | `src/api/` | Breaking changes | Add version middleware |
| R20 | Proof-of-Alpha hash not integrated with predictions | `crypto_exporter.py` | Proofs are detached from canonical records | Attach to PredictionEvent |

---

## Risk Heat Map

```
                    LIKELIHOOD
              Low    Medium    High
         ┌─────────┬─────────┬─────────┐
  High   │  R06    │  R07    │ R01,R02 │
IMPACT   │  R08    │  R09    │ R03,R04 │
         ├─────────┼─────────┼─────────┤
  Medium │  R15    │  R11    │ R05,R10 │
         │  R14    │  R12    │         │
         ├─────────┼─────────┼─────────┤
  Low    │  R16-20 │  R13    │         │
         └─────────┴─────────┴─────────┘
```

---

## Immediate Actions Required (Phase 1)

1. Fix R01 — xO temporal leakage (expanding window)
2. Fix R02 — Referee volatility temporal leakage (rolling computation)
3. Fix R03 — Remove synthetic odds (return None → NO_SIGNAL)
4. Fix R04 — Rename fake CLV to `model_edge_pct`
5. Fix R05 — Wire quarantine status into broadcaster
6. Fix R06 — Replace heuristic Kelly with risk-unit tiers

All fixes must include regression tests.
All existing 449 tests must continue passing.
