# Pilot C Hardening Report — Attestation, Coverage Bias, Statistical Rigour

Date: 2026-08-30. Repo: `football-quant-engine`. This work hardens the forward
experiment so the eventual readout is credible. **It is not a new modelling run,
and it does not draw any edge conclusion.**

> **What the pilot has and has not shown.** The pilot demonstrated the *conditions*
> for edge — a near-fair Betfair reference price (~1.1% overround), measurable
> book disagreement, and a calibrated model — and that the machinery runs end to
> end. **It has not demonstrated edge.** No edge conclusion may be drawn from
> unsettled fixtures. Every artifact below preserves that distinction.

---

## 1. Attestation status (priority — decaying-value item)

A shared, tamper-evident commit-reveal ledger now backs both forward pipelines:
`src/research/forward/attestation_ledger.py`.

- **Commitment binds prediction + fixture + reference price + timestamp** (SHA-256
  over canonical JSON). For Pilot C the Betfair (or fallback) over/under odds and
  de-vigged fair prob are part of the hash, so the benchmark cannot be re-chosen
  after the fact.
- **No backdating.** The commit anchor timestamp is taken from the ledger's own
  clock at append time, never from caller input. Records form a hash chain
  (`prev_hash`/`link_hash`) with a monotonic-timestamp guard, so any edit,
  reorder, or insertion is detectable by `verify_chain()`. The ledger refuses to
  append to a tampered file.
- **Pre-kickoff enforcement.** `commit()` refuses once `now >= kickoff`; such a
  prediction is flagged **unattested**, never backdated.
- **Auto-reveal after settlement**, binding the outcome to the prior commitment;
  reveal requires an existing commitment.
- Legacy `data/forward/commitments.jsonl` (294 records) migrated to the chained
  format via `scripts/migrate_forward_ledger.py`, **preserving each record's
  original timestamp** as the anchor (not backdating). Backup:
  `commitments.jsonl.legacy_bak`. Chain verifies.

### Honest counts (as of 2026-08-30 ~14:00 UTC)

| Pipeline | Predictions | Committed pre-kickoff | Cannot be attested (past kickoff) |
|---|---|---|---|
| A — corners/cards (`data/forward/`) | 298 | 186 | **112** |
| B — Pilot C (`pilotC_forward_predictions.json`) | 129 over 24 fixtures | 32 | **97** |

**The original "80" Pilot C predictions the brief referenced were all logged with
`status: finished` (past kickoff) and carried no commitment. All 80 are therefore
unprovable as forward record — they cannot be retroactively attested and were not
backdated.** This is exactly the decaying-value cost the brief warned about: the
forward set was logged as PROSPECTIVE but the kickoffs passed before commitment.
Going forward, every pre-kickoff prediction is committed automatically.

---

## 2. Covered-league top-up

`src/research/forward/covered_league_topup.py` + rewired
`scripts/pilotC_settle.py topup` and `scripts/pilotC_multibook_fetch.py`
(`PILOTC_COVERED_ONLY=1`, `PILOTC_MAX_FIXTURES` cap).

Policy: prioritise **upcoming fixtures in leagues that already have team history**;
**do not add new leagues**. Fetch order: upcoming both-covered → upcoming
one-covered → finished both-covered backlog. Everything in uncovered competitions
is excluded.

Dry-run plan (`data/discovery/pilotC_topup_plan.json`):

- Corpus teams: 480; covered competitions: 13.
- **Only 10 upcoming fixtures have both teams covered** — the binding constraint
  on sample growth, made explicit.
- **Actual quota remaining: 4,908** (read live from the client budget snapshot;
  the brief's "5,220" was a stale snapshot). This run is capped at 38 fixtures ×
  3 books = **114 requests worst-case**, cache-first (only new pairs cost budget).
- Projected settleable sample: ~10 covered upcoming fixtures/week × 4 markets =
  **~40 settleable predictions/week**, i.e. ~10 per market/line.
- To reach n=385 per market/line: **~38.5 weeks → estimated readout ~2027-05-27**.

This is a sobering, honest timeline: the covered-league bias grows the settleable
sample as fast as possible, but the corpus is thin, so a meaningfully-powered
per-cell sample is roughly nine months out under current inflow.

---

## 3. Statistical rigour

### Pre-registration (committed before settlement)

`data/results/pilotC_preregistration.json`, attested immutably in
`data/forward/preregistration_ledger.jsonl` (document SHA-256
`ccc9a6d0…`). It fixes, before any settlement:

- **Primary hypothesis**: model forward probability beats the Betfair de-vigged
  fair price, net of overround, on settled + pre-kickoff-attested fixtures.
- **Reference price**: Betfair-exchange primary; proportional (multiplicative)
  de-vig; reference price bound into each commitment.
- **Multiple-testing family**: the 9 market/line cells (goals 1.5/2.5/3.5,
  corners 8.5/9.5/10.5, cards 3.5/4.5, btts), BH-FDR at q=0.10; per-league splits
  are secondary/exploratory and counted in their own family.
- **Edge threshold**: ≥1.0pp de-vigged prob edge to *select* a bet (above the
  ~0.55pp implied by Betfair's ~1.1% overround); ≥2.0% realized ROI to *claim*.
- **Minimum sample**: 385 settled + attested fixtures per cell.
- **Stopping rule**: fixed-sample, no peeking — analyse once ≥5/9 cells reach 385,
  or at a 2027-06-30 backstop; no primary edge statistic is viewed before then.

### Pilot 9-for-9 BSS treated as provisional

`data/results/pilotC_bss_provisionality.json`. Findings:

- **CV folds**: the train/test split *is* point-in-time (test strictly later in
  time), but hyperparameter selection uses `LogisticRegressionCV(cv=4)` =
  StratifiedKFold, which is **not** time-ordered — confined to the training 70%.
- **Did hyperparameter selection touch evaluation data?** No — CV ran only on the
  training 70%; BSS/ECE were computed on the held-out later slice. *But* the
  forward predictor reuses corpus-selected hyperparameters.
- **Relabel**: the 9-for-9 is a **corpus single-split OOS-in-time** result (large
  held-out n≈4,600/market), **not** a forward-OOS result. With respect to the
  forward experiment it is *in-sample-of-a-sample* and is **not** evidence for the
  primary hypothesis. (Note: the brief's "small forward sample" framing was
  imprecise — the sample is large but corpus-internal; the *forward* sample is
  currently zero settled.) BSS magnitudes are small (+0.5% to +4.1%).

### Two engine issues fixed (`scripts/ev_test_metrics_vs_bet365.py`)

- `simulate_flat_bet_return` now **bets whichever side the edge points to** (was
  OVER-only), grading the backed side. Re-running showed side-aware betting yields
  *negative* realized ROI (−1.5% to −10.7% on the tested lines) despite a +14%
  "theoretical EV" — a healthy reminder that theoretical EV is not realized edge.
- The `compute_metric_predictions` "walk-forward" docstring and the output
  `method` field are **relabelled accurately**: it is a single point-in-time
  train/test fit, not per-market walk-forward. Point-in-time safety is intact.

---

## 4. Book disagreement (measured now, no settlement needed)

`scripts/book_disagreement_analysis.py` → `data/results/book_disagreement.json`,
across Bet365 / Betfair-exchange / Pinnacle on 195 cached fixtures (de-vigged
fair-prob differences per market/line).

- **Pooled**: mean **1.29pp**, median **0.91pp**, p95 **3.47pp**, max 17.7pp;
  **46%** of pairs exceed the ~1pp threshold.
- **Bet365 vs Betfair** on core lines (e.g. goals 2.5): mean ~1.0pp, ~38% exceed
  1pp; several lines (btts, goals 1.5/3.5/4.5/5.5) are flagged **systematic**
  (Bet365 consistently biased one direction) rather than random.
- **Betfair vs Pinnacle** (two low-vig books): small, ~0.4–0.7pp, effectively
  random — as expected for two efficient books.
- Disagreement widens at extreme lines (6.5/7.5) where liquidity is thin.

Interpretation: disagreement is *often* below 1pp (median < 1pp), so cross-book
edge is structurally small — but a substantial minority of core Bet365-vs-Betfair
lines exceed 1pp and are partly systematic, so it is not structurally absent.
Worth knowing before weeks of collection.

---

## 5. Verification & ground rules

- Full test suite: baseline 2,173 passing; added 12 attestation + 6 covered-league
  tests. All pass. No regressions (see commit).
- Attestation wired first (decaying-value item). No edge conclusions drawn from
  unsettled fixtures. Pre-registration committed and attested before any
  settlement analysis. No backdating anywhere. Quota reported live (4,908) and the
  top-up is capped and reported per run.
- No shared/global config changed. `.gitignore`, MCP configs, and env files were
  not modified.

### Artifacts

| Path | What |
|---|---|
| `src/research/forward/attestation_ledger.py` | tamper-evident commit-reveal ledger + document attestation |
| `src/research/forward/covered_league_topup.py` | covered-league top-up policy |
| `scripts/book_disagreement_analysis.py` | book-vs-book disagreement |
| `scripts/migrate_forward_ledger.py` | one-time legacy ledger migration |
| `data/results/pilotC_preregistration.json` | pre-registered analysis plan (attested) |
| `data/forward/preregistration_ledger.jsonl` | pre-registration attestation |
| `data/results/pilotC_bss_provisionality.json` | 9-for-9 BSS provisionality |
| `data/results/book_disagreement.json` | book-disagreement distributions |
| `data/discovery/pilotC_topup_plan.json` | top-up projection + quota |
