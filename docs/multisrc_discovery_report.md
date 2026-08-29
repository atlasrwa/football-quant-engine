# Multi-Source Discovery: New Fields Across Three Second-Tier Leagues

**Date:** 2026-08-29
**Question:** Do metrics built from the ~24 TheStatsAPI-unique fields (never before searched)
beat the market in three structurally comparable second-tier leagues — English Championship,
French Ligue 2, Spanish La Liga 2?

**Headline:** **No candidate survives.** Across the gate-passing (league, target) cells, 484
computable 2-feature candidates were screened against a cumulative FDR family of 23,823 and
**zero survived.** This is now a *much stronger* negative than prior runs: the ~24 new fields
(defending block, touches in box, big chances, duels, np_xG, half-splits, ...) have finally
been tested, and they do not produce an exploitable, multiple-testing-robust edge in these
leagues. Two findings of independent value emerged along the way (below).

---

## Step 1 — Merge validation (blocking gate): PASSED

Discovery pairs FootyStats and TheStatsAPI fields on the same matches; a silent join mismatch
(the F016/D2 concern: legacy stats files had a match-ID namespace with zero overlap with the
cached match-lists) would corrupt every candidate. Verified on the **Championship 24/25 overlap
season**, the one season present in *both* sources (TheStatsAPI sn_2930227 + FootyStats corpus
comp 12451).

- 552 TheStatsAPI matches → **420 clean 1:1 joins** (crosswalk team-name + date ±1 day).
  - Join rate 76.1%, limited purely by **crosswalk coverage** (21 of 24 Championship teams
    mapped at conf ≥ 0.9; 132 matches involve an unmapped team). Among mapped pairs: **0 no-match,
    0 multi-candidate** — structurally clean, no silent picks.
- **Shared-field agreement on the 420 joins:** yellow_cards 95.0% exact / 99.4% within-1;
  corners 97.6% / 98.9%; shots-on-target 82.1% / 95.8% (mean abs diff 0.24); fouls 89.3% / 93.7%
  (MAD 0.42); possession 85.0% / 97.8% (MAD 0.44 pct pts).
- **Falsification (decisive):** the correct join agrees 95.0% on cards exact-match vs a
  **shuffled/namespace-mismatch null of 21.8%** [97.5pct 24.6%] — a 73-point gap. The join is
  real. The lower SOT/fouls agreement is genuine **provider measurement noise on subjective
  fields on the same matches**, not a join error.
- **Implication:** objective outcome fields (cards, corners, goals) are trustworthy across
  sources; SOT/fouls carry provider noise, so features must be single-source per league.
  Discovery uses TheStatsAPI-only features → TheStatsAPI/fixture outcomes within each league, so
  no cross-source field contamination is possible. The F016/D2 namespace issue applied to raw
  match-ID matching, which this crosswalk join does not use.

Artifacts: `scripts/multisrc_step1_merge_validation.py`, `scripts/multisrc_step1_falsify.py`,
`data/thestatsapi/championship/_step1_merge_validation.json`.

## Step 2 — Corpus (balanced, recent complete seasons)

Championship was already cached (3 seasons). Freshly pulled the two most recent **complete**
seasons for the two new leagues:

| League | Seasons | Matches | Per-team balance | Stats coverage |
|---|---|---|---|---|
| Championship | 25/26, 24/25, 23/24 | 552 × 3 | 24 teams × 46 (min=max=med) | ~98–100% |
| Ligue 2 | 25/26 (sn_3064056), 24/25 (sn_3057202) | 306 + 306 | 18 teams × 34 | 306/306, 303/306 |
| La Liga 2 | 25/26 (sn_8437950), 24/25 (sn_8425423) | 462 + 462 | 22 teams × 42 | 462/462, 462/462 |

Full regular seasons → **perfectly balanced by construction** (every team the same number of
appearances, spread across the whole calendar). The 3 missing Ligue 2 stats files were 404s
(handled gracefully).

**Field population (the ~24 new fields), the key Step-2 finding** (`_field_population.json`):
- **Championship**: ~98–100% for *all* fields, including `goals_prevented` and `np_expected_goals`.
- **Ligue 2** (both seasons): most fields 100%; sparser `np_xg` (76–87%), `big_chances_missed`
  (79–88%), `high_claims` (~70%); **`goals_prevented` 0% (unusable)**.
- **La Liga 2 25/26**: most 100%; `np_xg` 76%, `expected_goals` 90.5%; `goals_prevented` 0%.
- **La Liga 2 24/25**: most 100%; **the entire xG family is null (`expected_goals` 0%, `np_xg`
  0%)**; `goals_prevented` 0%.
- **Consequences (reported, not worked around):** `goals_prevented` cannot support discovery
  outside the Championship. xG-based goals candidates cannot compute for La Liga 2 24/25 (the
  driver drops any match with a null feature and requires ≥30 predictions, so such candidates are
  auto-excluded there).

## Step 3 — Sanity gate, per league × target (gates the search)

Model-free raw-feature Spearman (per season, never pooled) first, then a model-based
walk-forward confirmation. **Search only where the gate passes.**

| League | cards | goals | corners |
|---|---|---|---|
| Championship | **FAIL** (expected, F017: −0.044/+0.033/+0.012) | **PASS** (S2 ρ +0.113) | FAIL (sign flips) |
| Ligue 2 | **PASS** (yellow→cards +; S2 ρ +0.141) | FAIL (weak SOT p>0.25; xG absent) | FAIL (sign flips) |
| La Liga 2 | **PASS** (both predictors +; S2 ρ +0.181) | FAIL* (S1 SOT + but S2 n/a: xG null 24/25) | FAIL (sign flips) |

**Gate-passing cells searched:** `champ/goals`, `ligue2/cards`, `laliga2/cards`.
Everything else is reported **untestable**, not searched.

**Finding of independent value (extends F017):** disciplinary-persistence is **not** a uniform
second-tier property. It is flat in the **Championship** (confirming F017 across a 4th and 5th
season) but **present in Ligue 2 and La Liga 2** (raw yellow-rate → cards consistently positive;
model-based ρ +0.14 / +0.18). So F017's "cards flat" result is **Championship-specific, not a
down-tier characteristic.** Corners persistence is flat in all three leagues (consistent with the
long-standing "corners weak everywhere" result). *(La Liga 2 goals: Stage-1 SOT→goals is actually
significant (+0.169, +0.108) but Stage-2 could not be established because xG — used by the
known-good goals metric — is null for 24/25; recorded as data-limited-untestable, not a clean
negative.)*

Artifacts: `scripts/multisrc_step3_sanity_gate.py`, `_step3_sanity_gate.json`.

## Step 4 — Discovery with the new fields

**Unit:** a small fitted 2-feature Poisson GLM + L2 (0.01) over point-in-time rolling team
features (the exact approach that produced the 7 validated metrics), within-season
expanding-window walk-forward. **Screening statistic:** Spearman(predicted λ, realized outcome),
one-sided positive.

**Candidate family sizing (reported before running, per the scale rule):** mechanism-motivated
feature pools keep the family bounded — cards 144 models, goals 196, corners 64 (× 2 lines
each). Only gate-passing cells are searched:

- `champ/goals` (392) + `ligue2/cards` (288) + `laliga2/cards` (288) = **968 new candidates**.
- **Cumulative FDR family: 22,855 → 23,823.** 484 candidates were computable and screened;
  BH correction applied against the *full cumulative family*, not per-run.

**Result: 0 survivors.** The strongest raw signals (all in La Liga 2 cards, defensive-engagement
features — tackles + fouls ρ +0.156, p < 0.0001; tackles + clearances; ball_recoveries) are real
associations but do **not** clear the multiple-testing bar of a 23,823-member family. All
candidates and near-misses are recorded in `data/results/multisrc_discovery.json`.

**Re-test of the 7 existing metrics on this corpus (honest demotion check, no refit):**
- Championship: cards metrics flat (ρ 0.01–0.03, none clear even uncorrected — consistent with
  F017); goals metrics detectable uncorrected (ρ +0.07 to +0.08).
- Ligue 2: `cards_minimal_pair` detectable uncorrected (ρ +0.141); others marginal.
- La Liga 2: all four cards metrics strongly detectable uncorrected (ρ +0.18–0.19, p < 0.0001) —
  they transfer well at the screening level.
- **None survive the corrected cumulative family. No demotions are warranted:** the 7 were
  already `TESTED_NEGATIVE` (priced-in, F013); this simply confirms they remain non-survivors
  under the enlarged family. Their per-league detectability is reported for honesty, but
  "clears uncorrected" is explicitly **not** the bar.

## Step 5 — EV backtest & market calibration

**No FDR survivors → nothing to EV-test at the candidate level.** The model-independent part of
Step 5 (market's own BSS vs naive) was run on balanced odds subsets, most recent complete season
per league (Ligue 2 108 matches, 12/team; La Liga 2 110, 10/team; perfectly balanced).

**Decisive odds-coverage gap (reported, not substituted):** **Bet365 offers no total_cards market
for Ligue 2 (0/108) or La Liga 2 (1/110).** The two leagues where cards persistence actually
*exists* have **no cards market to monetize** through this operator. This is the pivotal result
for the product: a real signal with no tradable market is not an edge.

**Market BSS vs naive (Bet365, model-independent):**

| Market / line | Ligue 2 | La Liga 2 |
|---|---|---|
| goals @2.5 | +3.65% (orr 6.0%) | +1.81% (orr 6.0%) |
| goals @3.5 | +3.81% | +2.11% |
| goals @1.5 | +1.20% | −0.35% |
| corners @9.5 | −0.50% (orr 8.3%, n=87) | −2.56% (orr 8.2%, n=78) |
| cards | **no market** | **no market** |

Goals markets are EPL-like (near-naive to mildly positive, overrounds 4.5–6.8%); corners at 9.5
are near-naive/slightly negative with ~8% overround. **Second-tier is not measurably sloppier
than EPL** — consistent with F015. 

**Benchmark caveat (stated prominently):** Bet365 is a comparatively **sharp** book; the operator
actually used (bc.game) is understood to price softer. A candidate that merely tied Bet365 could
plausibly be +EV at a softer book, so market-referenced results here are a **conservative lower
bound**. This is untested without bc.game odds and is not overstated — but moot in this run, since
nothing survived to EV-test and the cards market (the only place a signal was found) does not
exist at Bet365 for these leagues.

Artifacts: `scripts/multisrc_step5_market_calibration.py`, `multisrc_select_balanced_odds.py`,
`data/results/multisrc_market_calibration.json`.

## Step 6 — Honest interpretation

- **The broader claim is now tested, not just the narrow one.** Prior runs supported only
  "metrics from basic public stats don't beat the market." This run searched the ~24
  TheStatsAPI-unique fields for the first time, across three leagues, and **nothing survived
  cumulative FDR.** The negative is meaningfully stronger and closes the question for these
  fields/leagues at this sample size.
- **Two positive by-products** (both hypotheses for held-out confirmation, not validated
  findings):
  1. **Cards persistence is league-specific, not tier-specific** — present in Ligue 2 / La Liga 2,
     flat in the Championship. This refines F017.
  2. **The strongest new-field signal is defensive-engagement → cards in La Liga 2** (tackles,
     fouls, clearances, ball_recoveries). It is a near-miss under FDR and — critically — has no
     Bet365 cards market to exploit.
- **Wide CIs / caveats:** per-cell n is 300–900; a positive point estimate whose significance
  does not clear the cumulative family is a hypothesis, not a result. La Liga 2 cards near-misses
  should be treated as directions for a held-out check, not signals to deploy.
- **Held-out set: untouched.** No held-out data was read in this task.

## What this does NOT change

- **F015** (market-calibration/buy conclusion) stands, reinforced: second-tier goals/corners
  markets are EPL-like; the down-tier inefficiency thesis remains unsupported.
- **F016/F017** stand; F017 is refined (Championship-specific, not second-tier-wide cards flatness).

## Budget & config

- **Requests this task: 1,774 live** — 2 season-list + 18 fixture-page + 1,534 stats + 218 odds
  (2 sanity/calibration analyses were zero-cost, cache-only). No held-out reads.
- **Monthly quota remaining ≈ 5,770 of 10,000** (cumulative project live requests 3,658). Paced
  against the 12 req/min burst cap; the client absorbed several 429s via Retry-After without
  overspending.
- **No shared/global config changed.** Only per-process env rails
  (`THESTATS_MAX_REQUESTS=4000` to lift the default 425 local cap for this larger corpus,
  `THESTATS_MIN_INTERVAL` default 5.2s). `THESTATS_API_KEY` pre-existing in env. Cache dir is the
  existing `data/thestatsapi/championship/` (cache keys namespaced by league tag, e.g.
  `ligue2_stats_*`, `laliga2_odds_*`).
- **Fetcher committed** (`scripts/multisrc_fetch.py`, git ee0a0b0 + odds-command follow-up),
  per the standing rule that a prior session's uncommitted fetch code blocked a later task.

## Artifacts

- Fetcher: `scripts/multisrc_fetch.py` (parameterized, cache-first, committed)
- Corpus loader: `scripts/multisrc_corpus.py`; field population: `scripts/multisrc_field_population.py`
- Step 1: `scripts/multisrc_step1_merge_validation.py`, `scripts/multisrc_step1_falsify.py`
- Step 3: `scripts/multisrc_step3_sanity_gate.py`
- Step 4: `scripts/multisrc_step4_discovery.py`
- Step 5: `scripts/multisrc_select_balanced_odds.py`, `scripts/multisrc_step5_market_calibration.py`
- Results: `data/results/multisrc_discovery.json`, `data/results/multisrc_market_calibration.json`,
  `data/thestatsapi/championship/_step1_merge_validation.json`, `_step3_sanity_gate.json`,
  `_field_population.json`
- Raw cache: `data/thestatsapi/championship/{ligue2,laliga2}_stats_*.json`, `_odds_*.json`, fixtures
