# Championship Slice — Cache, Discover, EV Backtest

**Date:** 2026-08-29
**League/season:** English Championship (`comp_8321`), 2025/26 (`sn_3064530`) — the most
recent **completed** season (26/27 is current/in-progress; 25/26 has all 552 regular-season
matches finished).
**Data source:** TheStatsAPI (`https://api.thestatsapi.com/api`). All responses cached raw
under `data/thestatsapi/championship/`. All analysis reproducible offline.

---

## Headline answers

1. **Is Bet365 measurably sloppier on Championship than on EPL?** **No.** At the well-populated
   lines, Bet365's Championship market is calibrated ~as tightly as its EPL market. Market BSS
   vs naive hovers around zero: goals @2.5 **−0.18%** (n=200), goals @3.5 **+0.10%**, cards @3.5
   **+0.10%** (n=120), corners @9.5 **−0.83%** (n=109). The EPL reference is ~−0.35%. Overrounds
   are also EPL-like (goals ~5%, cards ~8%, corners ~8%). No down-tier calibration gap is visible
   in this slice.

2. **Do any candidates beat that market?** **No credible candidate.** The **sanity gate failed**
   on this slice (the known-good team-card-rate → cards signal is not detectable here), so all
   model-side EV results are reported but **not trusted**. The one eye-catching model-side number
   (cards @3.5 "model − market BSS +10–12%") is a small-sample artifact of a badly negative
   *market* BSS at n=28–50, not a real edge; every realized-return CI spans zero.

**Recommendation: DO NOT buy the paid plan on the strength of the down-tier inefficiency
thesis.** This slice provides no evidence that Championship is softer than EPL, which was the
thesis justifying volume. See "Buy / don't-buy" below for the fuller decision.

---

## Step 1 — Confirm & calibrate (23 requests)

Pulled health, season list, one fixture page, and 10 sampled finished matches (stats + odds).

- **Odds coverage (Bet365):** 10/10 sampled matches priced `total_goals`, `total_cards`,
  `match_corners`, `btts`. Full coverage — better than expected.
- **Overrounds:** goals 4.3–5.0%, cards ~7.5%, corners ~8.2–8.3% — comparable to EPL.
- **Field population:** all ~45 fields populated 10/10, **including all ~24 richer fields not in
  FootyStats** (blocked_shots, shots_inside/outside_box, big_chances(9/10), big_chances_missed,
  touches_in_penalty_area, fouled_in_final_third, accurate_crosses, accurate_long_balls,
  final_third_entries, all five duels, all five defending, all four goalkeeping, np_expected_goals)
  plus native half-splits.
- **Per-match cost:** exactly **2 requests** (1 stats + 1 odds).
- **Budget reality — correction to the brief:** the brief assumed ~425 trial requests. The live
  quota headers show **`X-Monthly-Quota-Limit = 10000`, ~9,400 remaining** after calibration —
  ~22× the assumed budget. Separately, the trial's **per-minute burst limit is only 12 req/min**
  (`X-RateLimit-Limit: 12`), which throttles bulk pulls (the client now paces at ~5.2s/request).

**Gate decision: GO.** Coverage is materially *better* than feared, so the "stop if worse than
expected" condition did not trigger.

## Step 2 — Balanced cache (all 24 teams, spread across the calendar)

- **Selection:** a deterministic calendar-stratified greedy selector picked **200 matches** so
  every team appears **16–17 times** (min 16, max 17, median 17 — the tightest possible split for
  200 matches / 24 teams). Matches are spread across all 10 months (Aug 2025 → May 2026), no
  clustering. This directly avoids the thin-history failure mode that the disagreement-decile test
  diagnosed. Selection logic in `scripts/championship_select_balanced.py`; no boundary tuning to
  chase a result.
- **Coverage on the 200:** stats **200/200**, Bet365 odds **200/200** (100%).
- **Full-history top-up:** the balanced 200 alone is too sparse per team (16 apps) to support
  point-in-time w5/w10 rolling windows — a probe returned **0 usable predictions**. So stats for
  **all 552 season fixtures** were cached (offline model gets each team's full chronological
  history); **EV evaluation still runs only on the balanced 200 matches that have odds.** This
  keeps the *evaluated* sample balanced while giving the model proper history — it does not change
  the model.
- **FootyStats crosswalk join rate (reporting only):** 111/200 join to the FootyStats corpus via
  the validated crosswalk (mapped team pair + date ±1 day). The other 89 involve 25/26 promoted
  sides (Wrexham, Charlton, Oxford, …) that the 24/25-built crosswalk does not map at ≥0.9
  confidence. **The analysis uses TheStatsAPI data directly and does not depend on this join.**
- **Budget:** 768 cumulative live requests total (calibration + fixtures + 552 stats + 200 odds);
  **monthly quota remaining ≈ 8,660 of 10,000.**

## Steps 3 & 4 — Offline discovery + EV backtest

Model reused **verbatim** from `scripts/ev_test_metrics_vs_bet365.py` (Poisson GLM + L2 λ=0.01,
team empirical-Bayes shrinkage strength=10, point-in-time rolling features, multiplicative vig
removal). **No refit of the 7 metrics, no retune, no model substitution.** Championship data is
fed through an adapter (`scripts/championship_adapter.py`) that maps the TheStatsAPI stats schema
onto the exact FootyStats field names the model consumes — only the data source changes. Because
this is a single season, the train/predict split is a within-season expanding-window walk-forward
(the only point-in-time-safe option for one season; the original two-corpus split assumes multiple
prior seasons we do not have).

### Sanity gate — FAILED (and this is itself the key model-side finding)

Known-good check: a team's recent yellow-card rate should carry information about total match
cards, so predicted card-λ should **rank-correlate positively** with realized cards.

- Result: **Spearman(λ, actual cards) = −0.105 (p = 0.13, n = 215).** Predicted mean λ = 4.21
  matches actual mean 4.20 (calibrated on the *mean*), but the **ranking is slightly inverted** —
  matches the model rates higher for cards had a *lower* realized over-rate (0.55 vs 0.64).
- Per the standing rule ("sanity gate passes before any screening result is trusted"), **all
  model-side EV numbers below are reported but NOT trusted as evidence.** The team-card signal
  that worked on EPL does not transfer to this Championship season.

### Candidate accounting & cumulative FDR

- **7 existing metrics** run **as-is** (pre-registered/validated; already in the family — do not
  increment it).
- **7 new-field candidates** (metric × line), each mechanism-motivated:
  `def_block_cards`@3.5/4.5, `territory_corners`@9.5/10.5, `crosses_corners`@9.5/10.5,
  `bigchance_goals`@2.5.
- **Cumulative FDR family: 22,848 → 22,855** (+7). Deliberately tiny so survival is statistically
  possible on ~200 matches. **Nothing survives** — with the sanity gate failed and every CI
  spanning zero, no candidate is put forward as an FDR survivor.

### Market calibration (model-independent — the primary deliverable)

Bet365 implied probability (multiplicative de-vig) vs realized totals on the balanced 200.

| Market | Line | n | base over-rate | overround | **Market BSS vs naive** |
|--------|------|---|----------------|-----------|-------------------------|
| goals | 0.5 | 200 | 0.93 | 4.5% | −1.38% |
| goals | 1.5 | 200 | 0.71 | 4.9% | −0.51% |
| goals | **2.5** | 200 | 0.49 | 5.3% | **−0.18%** |
| goals | **3.5** | 200 | 0.28 | 5.0% | **+0.10%** |
| goals | 4.5 | 200 | 0.12 | 5.2% | −0.60% |
| goals | 5.5 | 200 | 0.04 | 3.9% | −3.31% |
| cards | **3.5** | 120 | 0.52 | 8.1% | **+0.10%** |
| cards | 4.5 | 55 | 0.38 | 7.7% | −2.51% |
| cards | 2.5 | 10 | 0.80 | 7.9% | −59.4% *(n=10, ignore)* |
| corners | **9.5** | 109 | 0.54 | 8.0% | **−0.83%** |
| corners | 10.5 | 84 | 0.43 | 8.1% | +0.95% |

**Reading:** at the high-n, near-50/50 lines — where BSS is most reliable — the market sits
essentially on top of naive (|BSS| ≤ ~1%), the signature of a well-calibrated book. The larger
negatives are at low-base-rate extremes (goals @0.5/@5.5, cards @4.5) where the naive base-rate
predictor is very hard to beat and Brier is noisy — the same structure seen on EPL, not evidence
of softness. **Championship ≈ EPL in market sharpness here.**

### Model-side EV results — ALL candidates, worst included (NOT TRUSTED; sanity gate failed)

Existing metrics (model−market BSS and flat-bet OVER ROI with 95% CI):

| Metric | Line | n | market BSS | model BSS | model−market | ROI [95% CI] |
|--------|------|---|-----------|-----------|--------------|--------------|
| cards_minimal_pair | 3.5 | 50 | −14.41% | −4.02% | +10.38% | +22.2% [−2, +45] |
| cards_minimal_pair | 4.5 | 21 | −4.56% | −6.99% | −2.43% | −21.3% [−61, +24] |
| cards_best_pair | 3.5 | 28 | −22.19% | −10.47% | +11.72% | +29.1% [−3, +58] |
| cards_best_pair | 4.5 | 9 | −0.34% | +4.47% | +4.81% | −5.6% [−77, +66] |
| cards_with_fouls | 3.5 | 36 | −16.07% | −11.15% | +4.91% | +24.7% [−3, +51] |
| cards_with_fouls | 4.5 | 10 | −1.08% | +0.18% | +1.26% | −15.0% [−79, +49] |
| cards_triple_halfsplit | 3.5 | 28 | −22.19% | −20.49% | +1.71% | +29.1% [−3, +58] |
| cards_triple_halfsplit | 4.5 | 9 | −0.34% | +3.87% | +4.21% | −5.6% [−77, +66] |
| goals_sot_xg | 1.5 | 94 | +0.42% | +0.89% | +0.47% | −4.9% [−17, +6] |
| goals_sot_xg | 2.5 | 94 | +0.97% | −2.16% | −3.13% | −8.0% [−28, +12] |
| goals_sot_xg | 3.5 | 94 | −0.46% | −4.43% | −3.97% | −7.8% [−38, +23] |
| goals_sot_count | 1.5 | 94 | +0.42% | +2.03% | +1.62% | −4.9% [−17, +6] |
| goals_sot_count | 2.5 | 94 | +0.97% | +0.16% | −0.81% | −8.0% [−28, +12] |
| goals_sot_count | 3.5 | 94 | −0.46% | −2.58% | −2.11% | −7.8% [−38, +23] |
| goals_count_xg | 1.5 | 156 | +0.10% | +2.70% | +2.59% | −8.9% [−19, +0] |
| goals_count_xg | 2.5 | 156 | +0.08% | −0.10% | −0.17% | −7.1% [−23, +9] |
| goals_count_xg | 3.5 | 156 | −0.24% | +1.06% | +1.30% | −6.1% [−30, +19] |

New-field candidates:

| Candidate | Line | n | market BSS | model BSS | model−market | ROI [95% CI] |
|-----------|------|---|-----------|-----------|--------------|--------------|
| def_block_cards | 3.5 | 60 | −3.50% | +0.71% | +4.21% | +10.8% [−12, +33] |
| def_block_cards | 4.5 | 22 | −4.96% | −11.26% | −6.31% | −24.0% [−63, +21] |
| territory_corners | 9.5 | 47 | −2.09% | −6.00% | −3.91% | −2.3% [−28, +23] |
| territory_corners | 10.5 | 46 | −0.96% | +0.50% | +1.46% | −24.3% [−52, +4] |
| crosses_corners | 9.5 | 47 | −2.09% | +2.76% | +4.86% | −2.3% [−28, +23] |
| crosses_corners | 10.5 | 46 | −0.96% | −2.31% | −1.35% | −24.3% [−52, +4] |
| bigchance_goals | 2.5 | 133 | −0.09% | −0.18% | −0.09% | −10.1% [−27, +6] |

**Why the cards @3.5 "+10–12%" is not an edge:** its apparent advantage comes entirely from the
*market* BSS being wildly negative there (−14% to −22%) on only 28–50 matches — a few
high-variance cards outcomes tanked the market's Brier on that thin subset. On the larger,
more reliable cards @3.5 market-calibration set (n=120), market BSS is **+0.10%**. Every ROI CI
in both tables spans zero. Combined with the failed sanity gate, there is no credible edge.

---

## Honest interpretation (required)

- **Wide confidence intervals.** 200 matches, and per-line subsets of 9–156. Every realized-ROI
  CI spans zero. No positive point estimate is conclusive; the eye-catching ones sit on the
  thinnest subsets.
- **Single league, single season, small sample.** Nothing here validates a strategy. Any positive
  reading is a hypothesis for a larger study, not a result.
- **All candidates reported, worst included.** No post-hoc selection of a best-looking slice.
- **Multiple-comparison risk.** 7 existing + 7 new candidates × several lines were examined on
  already-cached data. The lone favorable-looking cells are what chance produces from many slices.
- **Most valuable output is the market-calibration number, and it is model-independent.** It does
  not rely on our (sanity-gate-failed) model, and it says Championship ≈ EPL in sharpness.
- **The sanity-gate failure is a genuine finding, not a bug.** The EPL-derived team-card signal
  does not transfer to Championship 25/26 (a different-composition league with promoted/volatile
  sides). This is exactly the mis-specification the gate exists to catch.

## Buy / don't-buy recommendation

**Lean: DON'T buy the paid plan for the down-tier inefficiency thesis.**

- The thesis that justified buying volume — "Championship is second tier, plausibly softer than
  EPL" — is **not supported**: Bet365's Championship market is about as well-calibrated as its EPL
  market at every well-populated line, with EPL-like overrounds.
- The model side gives no offsetting signal: the sanity gate failed, so the metrics that worked on
  EPL do not even carry their known signal here.
- Spending ~10,000–15,000 requests to scale this exact approach would most likely reproduce the
  EPL conclusion (market already priced in) one tier down.

**What would change the recommendation (and is cheap to check first, within the *existing*
trial budget — ~8,660 requests remain):**
- The sanity-gate failure may be a *this-season* artifact. Before any purchase, re-run the
  identical pipeline on **Championship 24/25 (`sn_2930227`)** and/or 23/24 — both are in the
  season list and would cost ~1,100 requests each, well within the remaining trial quota. If the
  sanity gate passes on another season and market BSS is still ~0, that is decisive
  evidence against the thesis and the purchase is not justified. If market BSS turns meaningfully
  negative on a fuller multi-season sample, revisit.
- Only consider the paid plan if a multi-season Championship (or lower-tier: League One/Two,
  which are also in coverage) replication shows market BSS materially below EPL's at high n.

---

## Ground-rules compliance

- **Step 1 gated Step 2** — coverage confirmed (better than expected) before the bulk pull.
- **No model substitution / no refit** of the 7 metrics — same Poisson GLM + L2 + shrinkage,
  reused verbatim via an adapter; only the data source and the (necessary) within-season
  walk-forward split differ, both stated explicitly.
- **Sanity gate ran first** and **failed**; all model-side results are flagged untrusted.
- **Cumulative FDR reported:** 22,848 → 22,855 (+7 new candidates).
- **Held-out set untouched.**
- **Everything cached raw; analysis reproducible offline** (`scripts/championship_step34_analysis.py`,
  results `data/results/championship_step34.json`).
- **Request usage reported per step;** the per-minute throttle was handled by pacing, not by
  abandoning the pull. Total 768 live requests, ~8,660 monthly quota remaining.
- **Shared/global config:** none changed. The run used two *per-process* env vars
  (`THESTATS_MAX_REQUESTS`, `THESTATS_MIN_INTERVAL`) as safety rails. `THESTATS_API_KEY` was
  already present in `~/.bashrc` (pre-existing; not added or modified by this work).

## Artifacts

- Client: `scripts/thestatsapi_client.py` (cache-first, quota-tracking, paced, abort-on-error)
- Calibration: `scripts/championship_step1_calibrate.py`
- Fixtures / selection: `scripts/championship_fetch_fixtures.py`, `championship_select_balanced.py`
- Bulk cache: `scripts/championship_step2_cache.py`, `championship_cache_all_stats.py`
- Adapter: `scripts/championship_adapter.py`
- Analysis: `scripts/championship_step34_analysis.py`
- Results: `data/results/championship_step34.json`
- Raw cache: `data/thestatsapi/championship/` (552 stats, 200 odds, fixtures, summaries)
