# Per-League Pilot-C Stat-Mixer — All 25 Corpus Leagues

## What was run

The existing Pilot-C stat-mixer (`scripts/pilotC_stat_mixer.py`) pools **all** leagues
into one training matrix (`n_train ≈ 10,753`) and reports **one** BSS/ECE per market —
the widely-cited "9-for-9 positive BSS" result. The only *league-specific* evidence in
the repo previously covered ~4–6 leagues (Championship / La Liga 2 / Ligue 2 +
`family_transfer` on EPL / La Liga / Ligue 1).

This run evaluates the **identical methodology independently for every league** we hold a
two-season corpus for: **25 leagues, 50 seasons, 15,362 completed matches**
(`data/discovery/corpus`). FootyStats coverage is 45+ leagues; 25 have the two-season
corpus required for this model. The remaining chosen leagues (League One/Two, Segunda,
Japan J1, Argentina, etc.) are `BLOCKED_NO_TWO_SEASON_CORPUS` in
`provider_league_registry.json` and cannot be tested until their corpus is built.

- Script: `scripts/pilotC_per_league.py`
- Output: `data/results/pilotC_per_league.json`
- Log: `logs/pilotC_per_league.log`

**Methodology is byte-for-byte the pooled pilot's** — the runner imports
`POOLS`, `WINDOWS`, `FIELD`, `build_histories`, `match_features`, `outcome`,
`feat_names` directly from `pilotC_stat_mixer.py`:

- PIT team-keyed rolling means over w5 / w10 / season-to-date, both teams, for + against.
- Elastic-net logistic; `GridSearchCV` over `C × l1_ratio` with `TimeSeriesSplit(4)`.
- Chronological 70/30 outer split; ≥60% feature-coverage rule on training rows only;
  median-impute + standardize fit on training only.

The only intended difference: **rolling histories are league-internal** (a team's form
within its own league), and everything is grouped and scored per league.

## Headline result

**The pooled "9-for-9 positive" does not replicate at the league level.**

| Market | Pooled BSS | Leagues run | Mean BSS | Median BSS | Positive / total | Best league |
|---|---:|---:|---:|---:|---:|---|
| goals 1.5 | +1.53 | 21 | −2.16 | −0.42 | 4/21 | Netherlands Eredivisie +2.26 |
| goals 2.5 | +1.67 | 21 | −0.22 | −0.00 | 8/21 | France Ligue 1 +4.66 |
| goals 3.5 | +1.82 | 21 | −1.59 | −0.54 | 6/21 | France Ligue 1 +2.69 |
| corners 8.5 | +1.62 | 21 | −1.07 | −0.35 | 5/21 | Spain La Liga +0.94 |
| corners 9.5 | +1.52 | 21 | −0.82 | −0.26 | 4/21 | Spain La Liga +1.67 |
| corners 10.5 | +1.66 | 21 | −0.81 | −0.50 | 3/21 | Spain La Liga +1.56 |
| cards 3.5 | +4.08 | 21 | −1.65 | −1.05 | 3/21 | Spain La Liga +2.39 |
| cards 4.5 | +3.78 | 21 | −1.89 | −1.65 | 7/21 | Italy Serie A +4.85 |
| btts | +0.54 | 21 | −1.31 | −0.36 | 1/21 | England Championship +0.19 |

- **41 of 189** league×market cells that ran are positive (**21.7%**). Every market's
  median BSS is negative or ≈0. The pooled numbers were positive on all 9.
- The largest, data-richest leagues are the *worst*: England Championship (n=1114)
  mean −1.66, USA MLS (n=1062) −2.00, Germany 2. Bundesliga −2.53.

## Per-league ranking (mean BSS across a league's markets)

| League | n | positive cells | mean BSS | max BSS |
|---|---:|---:|---:|---:|
| France Ligue 1 | 611 | 3/9 | +0.65 | +4.66 |
| Spain La Liga | 760 | 7/9 | +0.34 | +2.39 |
| Italy Serie A | 760 | 4/9 | +0.16 | +4.85 |
| Sweden Allsvenskan | 480 | 4/9 | +0.09 | +2.17 |
| Scotland Premiership | 456 | 2/9 | −0.24 | +0.42 |
| England Premier League | 760 | 1/9 | −0.27 | +1.58 |
| Germany Bundesliga | 612 | 2/9 | −0.94 | +3.62 |
| … | | | | |
| Norway Eliteserien | 480 | 4/9 | −2.97 | +2.01 |
| Switzerland Super League | 456 | 0/9 | −3.37 | −0.00 |

Full ordering is in `logs/pilotC_per_league.log`.

Only **Spain La Liga** is convincingly positive across a market family (corners 8.5/9.5/10.5
all positive, cards 3.5 +2.39). France Ligue 1 (goals) and Italy Serie A (cards 4.5 +4.85)
show isolated single-market positives. None of these has been FDR-corrected across the
189-cell family, and each is a single chronological 70/30 split — so they are **candidate
signal generators, not validated edges**, exactly as the executive brief requires.

## Leagues that could not be tested alone

Four leagues were reported `insufficient_rows` on all 9 markets because the 70% training
split falls below the 300-row minimum:

| League | n matches | ~train rows |
|---|---:|---:|
| Austria Bundesliga | 390 | ~273 |
| Denmark Superliga | 386 | ~270 |
| Finland Veikkausliiga | 344 | ~241 |
| Australia A-League | 339 | ~237 |

This is itself a finding: a two-season corpus for a ~180-match/season league cannot
support a per-league elastic-net model. These leagues are precisely the case for the
executive brief's **#1 recommendation — hierarchical partial pooling** — so a league
borrows strength from the league-family prior instead of standing alone.

## Interpretation (consistent with the executive brief)

1. The pooled "9/9 positive BSS" is largely a **cross-league pooling artifact**: pooling
   adds sample and between-league dispersion that a single global base-rate cannot match,
   which inflates BSS. Isolate each league and the effect mostly vanishes.
2. Raw prior-only stat mixing, per league, is **near-fair-market-neutral** — small
   positive skill in a few competitions (La Liga corners/cards, Ligue 1 / Serie A goals /
   cards), negative or zero in most.
3. This does **not** contradict the audit's ranking. It reinforces it: the value is not in
   more raw-stat mixing but in (a) **hierarchical pooling** so thin leagues borrow strength
   and rich leagues are not overfit, then (b) the **early-market-to-close residual model**
   once immutable opening/entry/close snapshots exist.

## Honesty notes

- BSS is corpus-internal out-of-sample-in-time on a single 70/30 split, not walk-forward,
  not FDR-corrected across the 189-cell family, and **not** forward or price-relative.
  It measures calibration skill vs each league's own base rate, not betting edge.
- Nothing in `src/` or the existing pilot artifacts was modified; this is an additive
  research runner and a new results file.
