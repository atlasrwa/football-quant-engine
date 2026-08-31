# Is Championship Structurally Different, or Was 25/26 an Odd Season?

**Date:** 2026-08-29
**Question:** The F016 finding (card predictors flat on Championship 25/26) — is it **structural**
(Championship persistently lacks disciplinary persistence) or a **single-season artifact** (25/26
was unusual)?
**Verdict:** **STRUCTURAL, and cards-specific.** The card signal is flat across **all three**
Championship seasons measured (25/26, 24/25, 23/24), so 25/26 was not unusual. And the flatness
is confined to **cards/fouls** — corners and goals predictors survive on Championship at roughly
corpus strength. This is a targeted disciplinary-persistence limit, not a league-wide collapse of
all team-level signal.

**Method:** raw-feature correlation only — **no model, no GLM, no metric definitions, no fitting**
— identical to the instrument that produced the decisive F016 evidence. Rolling w5, point-in-time
(feature uses only prior matches, full window required), feature = home-team rolling + away-team
rolling, Spearman vs the realized match total. The script reproduces the F016 25/26 and corpus
numbers exactly before any new-season number is trusted (self-check passed: corpus cards +0.177,
25/26 cards −0.044).

---

## Results — per season, never pooled

Model-free raw-feature Spearman correlation (with Fisher-z 95% CI). `***`p<0.001 `**`p<0.01 `*`p<0.05.

### Cards (the F016 finding)

| Predictor → total cards | Corpus (25 lgs) | Champ 25/26 | Champ 24/25 | Champ 23/24 |
|---|---|---|---|---|
| team **yellow-card** rate (w5) | **+0.177*** [.161,.193] | −0.044 [−.162,.075] | +0.033 [−.084,.150] | +0.012 [−.091,.114] |
| team **foul** rate (w5) | **+0.175*** [.158,.191] | −0.010 [−.107,.088] | −0.030 [−.126,.068] | −0.041 [−.130,.049] |
| n (yellow / foul) | 13,992 / 13,700 | 275 / 405 | 280 / 409 | 367 / 476 |

**Every Championship cards correlation is statistically indistinguishable from zero (all p ≥ 0.37)
and every 95% CI excludes the corpus value +0.177.** This holds for two independent predictors
across three independent seasons. 25/26 (the season F016 flagged) is representative, not an
outlier — its −0.044 sits right in the same flat band as 24/25 (+0.033) and 23/24 (+0.012).

### Corners and goals (breadth check — is it cards-specific or league-wide?)

| Predictor → outcome | Corpus | 25/26 | 24/25 | 23/24 |
|---|---|---|---|---|
| corner rate → total corners | +0.067*** [.050,.083] | −0.001 | +0.087 (p=.07) | +0.067 |
| SOT rate → total goals | +0.107*** | +0.050 | +0.032 | +0.135** |
| xG rate → total goals | +0.099*** | +0.114* | +0.057 | +0.149*** |

- **Corners:** corpus persistence is itself weak (+0.067). Championship is in the same ballpark
  (+0.087 / +0.067, with one flat season) — CIs overlap corpus. Not a Championship-specific
  failure; corner-count persistence is just weak everywhere.
- **Goals:** Championship goal persistence **holds at corpus-comparable strength** — xG→goals is
  significant in 25/26 (+0.114*) and 23/24 (+0.149***), SOT→goals significant in 23/24 (+0.135**),
  and every Championship goal CI overlaps the corpus value. Goals-based team signal transfers fine.

---

## Interpretation

**The failure is structural and cards-specific.** Two things are now established that a single
season could not establish:

1. **Not a 25/26 artifact.** The card/foul → cards relationship is flat in all three Championship
   seasons, with every CI excluding the corpus +0.177. Repeating the measurement on independent
   seasons is the test the brief asked for, and it comes back the same each time.

2. **Not a league-wide loss of team-level signal.** Goals persistence survives on Championship at
   roughly the same strength as the corpus, and corners is corpus-level (weak everywhere). If the
   proposed "squad churn erases all team persistence" mechanism were the whole story, goals would
   have gone flat too — it didn't. So the mechanism is **specific to disciplinary behaviour**:
   a team's recent card/foul rate does not forecast its next match's cards in the Championship,
   even though its recent shooting/xG does forecast its goals.

Why disciplinary persistence specifically? Hypotheses (not tested here, clearly labelled
speculative): cards depend heavily on the *referee* and the *specific opponent/occasion* rather
than a stable team trait, and the Championship's high fixture density, promotion/relegation
pressure, and roster churn may make disciplinary output more situation-driven than trait-driven —
whereas shooting volume/xG is a more stable stylistic property that survives churn. This is a
direction for investigation, not a conclusion.

## Product implication (metric generalization)

This belongs in the product's design assumptions:

- **Cards-based metrics must be validated per league before deployment; do not assume the
  corpus-validated disciplinary persistence transfers.** For the **Championship specifically,
  cards-based strategies should be excluded** — the underlying persistence the metrics rely on is
  absent across every season tested.
- **Goals-based (and, weakly, corners) team signal does transfer to the Championship**, so the
  per-league-validation requirement is targeted, not a blanket ban on the league.
- More broadly: a signal surviving cumulative FDR across ~25 leagues is **not** evidence it holds
  in a 26th. Generalization must be measured, not assumed — cheaply, with exactly this
  model-free raw-feature check, before any modelling or odds spend.

## What this does NOT change

- **The market-calibration conclusion (F015) stands, untouched.** Championship market BSS at
  well-populated lines is EPL-like and the down-tier inefficiency thesis is unsupported. That is
  model-independent and unaffected by anything here. The buy decision is **not** re-litigated.
- **F016's diagnosis stands and is strengthened:** the sanity-gate failure was a genuine
  signal-absence finding, not a pipeline bug — now confirmed structural and cards-specific rather
  than season-specific.

## Honest limitations

- Per-season n for Championship is 275–492 usable matches; individual CIs are wide (±~0.10). The
  strength of the conclusion comes from **consistency across three independent seasons plus two
  independent predictors**, not from any single estimate.
- Full regular seasons (552 matches, every team exactly 46 appearances) — perfectly balanced by
  construction, so no per-team-coverage confound. Reported below.
- Rolling-window feasibility means early-season matches (before a team has 5 priors) are excluded;
  this is identical point-in-time handling to the corpus measurement, so the comparison is fair.

## Per-team coverage (balance)

Both new seasons are complete regular seasons: **24 teams, every team exactly 46 appearances**
(min = max = median = 46). This is the maximally balanced sample — no team is over- or
under-represented, so the flat correlations cannot be a coverage artifact.

## Budget & config

- **Requests used:** fixtures (12) + stats (1,104) = 1,116 live requests this task; no odds
  fetched (this analysis does not touch market prices). Cumulative across the project: 1,884 live
  requests; **monthly quota remaining ≈ 7,544 of 10,000.** Paced against the 12 req/min burst cap.
- **Adapter robustness fix (flagged):** `championship_adapter._cell` now guards against a `None`
  stat node (older seasons return `expected_goals` present-but-null on some matches, which the
  original `.get(stat, {})` didn't cover). This is a **null-handling robustness fix only** — no
  field mapping or model logic changed. Verified the 25/26 self-check numbers are **unchanged**
  after the fix (cards still −0.044 / −0.010), so it does not affect the F016 comparison.
- **No shared/global config changed.** Only per-process env vars (`THESTATS_MAX_REQUESTS`,
  `THESTATS_MIN_INTERVAL`) were used as rails; `THESTATS_API_KEY` pre-existing in `~/.bashrc`.

## Artifacts

- Analysis: `scripts/champ_raw_feature_corr.py` (model-free; reproduces F016 as a self-check)
- Fetchers: `scripts/champ_seasons_fetch_fixtures.py`, `scripts/champ_seasons_cache_stats.py`
- Results: `data/thestatsapi/championship/_raw_feature_corr_by_season.json`
- Raw cache: `data/thestatsapi/championship/` (1,104 new stats for 24/25 + 23/24, fixtures)
