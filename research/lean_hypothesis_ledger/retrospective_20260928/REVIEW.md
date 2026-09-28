> EXCLUDED BY USER — 28 September 2026: The user considers these fixture analyses incorrect. This document is retained only as an audit trail, excluded from pilot counts, performance summaries, model validation and promotion evidence. See QFE-USER-EXCLUSION-20260928-TUR-SWE-ROU in the ledger.

# Retrospective market-disagreement review — 28 September 2026

This review covers Türkiye–Italy, Sweden–Poland and Romania–Bosnia. It reconstructs the recorded pre-match scans and extends their supported market coverage. It is not a blind replay: result-bearing pages were encountered during research. No result or post-match statistic enters the calculations, and no selection is backdated or added to the 40-test pilot.

## What was recoverable

The ledger recorded the corner scan at 18:39:07 UTC and goal/card diagnostics at 18:42:53 UTC, ahead of the identified 18:45 kickoff. Those events, their source inputs, and prices remain unchanged. Extra YesPlay team-goal/result quotes were visible in the earlier conversation; they are archived in this retrospective replay now, not falsely assigned an earlier file timestamp. Secondary quotes are reference prices, not verified executable Rushbet offers or closing prices.

The corner helper is reproducible. Its context is the mean of team venue corners-for and opponent venue corners-against; the displayed screenshot rate and context are weighted by screenshot N and 10. The code's minimum-N convention does not eliminate overlap between samples. Source compatibility, neutral-venue classification and dispersion remain unvalidated. Total corners additionally assume independent team Poissons.

The goal helper is a probability converter for supplied intensities. The previous narrative about a contextual GF/xG/venue shrinkage estimator was not backed by a recoverable estimator in the inspected package. Therefore this review preserves both previously recorded diagnostics: (own GF + opponent GA)/2 and separately (own xGF + opponent xGA)/2. Neither is selected, blended or described as calibrated. The two-scenario range is not a confidence interval. Home advantage and schedule strength are not modeled.

Cards use raw displayed averages only. No frozen referee/opponent-adjusted card model was recovered. Undefined screenshot 'cards' cannot automatically be compared with yellow-card or bookings-points contracts.

## Findings and contextual challenges

### Türkiye–Italy

The original corner calculation disagreed most clearly on Türkiye O4.5 and total O8.5. Italy O4.5 and the editorial total O9.5 price also showed numerical gaps. These are correlated expressions of one high-corner environment, not independent discoveries.

A source/window sensitivity using SportsGambler's last-10 overall corner rates (Türkiye 6.5, Italy 7.4) with its venue context retains these positive gaps. That is not a calibrated robustness test: the team lists and coverage still require auditing. Newly retrieved Tipsters trend claims point the other way for Italy O4.5 (Italy under in 8/10 away, opponents of Türkiye under in 9/10). Their window compatibility is unverified; they are counterevidence to investigate, not a substitute probability. A high mean can coexist with a low threshold hit rate when the distribution is skewed.

Goals O2.5 and BTTS Yes clear the reference price only in the GF/GA scenario. Neither team-goal ladder produces a positive gap in both scenarios. Türkiye win has only a small two-scenario gap (+1.1 to +1.6 percentage points at 2.95), insufficient to call robust against the missing adjustments.

The displayed card means sum to 4.30. Raw Poisson U4.5 is 57.04%, U5.5 73.67%. A newly retrieved Oliver international sample averages approximately 4.3 yellow cards; domestic samples differ. No numerical referee adjustment or comparable two-sided cards quote is justified.

### Sweden–Poland

Poland O3.5 corners and total O9.5 retain positive numerical gaps in the source/window sensitivity. Sweden O5.5 does not: probability drops from 54.07% to 43.22%, below 48.31% break-even. This is a concrete reason to distinguish the team markets.

The expanded result scan identifies Poland win at 3.65: 34.09–34.33% in the two goal scenarios against 27.40% break-even and approximately 25.89% normalized market reference. This is a previously missed diagnostic disagreement, reconstructed now. Both scenarios share the same omitted home advantage and schedule corrections, so agreement is not independent validation. No result of this fixture was used to choose it.

Goals O2.5 and BTTS Yes change sign versus break-even across scenarios; team-goal ladders do not yield an all-scenario positive gap. The archived recent histories contain very different opponents for Sweden and Poland, making unadjusted all-competition scoring comparisons particularly uncertain.

Cards warrant a concrete price request: total U4.5 and Poland U2.5. Raw probabilities are 70.07% and 67.67%, respectively; corresponding diagnostic fair prices are about 1.43 and 1.48, before any margin for model error. Newly retrieved Poland disciplinary trends point toward the team under, but do not establish an edge. Referee Alberola Rojas is confirmed; published card averages differ materially with source/window. We did not choose whichever referee average supports an under. No verified compatible quote means no priced disagreement.

### Romania–Bosnia

Corner markets mostly agree with the recorded baseline. Total U8.5 at 1.98 is 51.28% versus 50.51% break-even: only +0.77 percentage points. That is too fragile to elevate based on these uncertain inputs.

O2.5 and BTTS Yes change sign across the two goal scenarios. Romania win at 2.32 clears both, but the gap contracts from +5.37 to +1.74 points in the xG scenario. This is a secondary diagnostic, not a strong confirmed disagreement.

Romania's 2.38 goals versus 1.69 displayed xG, 7/7 penalties, and a 7–1 San Marino result in the published home history raise schedule/penalty questions. They do not justify an invented subtraction from lambda. The two 2025 H2Hs are a small, partly red-card-affected sample, not a fitted adjustment.

A pre-match editorial advocated total yellow cards O4.5 at 1.60, citing the two 2025 H2Hs. Raw displayed-card Poisson yields only 48.11% for over 4.5 versus a 62.50% price hurdle, if and only if definitions match. Definitions were not verified, so the calculated comparison is illustrative and excluded from executable EV fields. No opposing quote supports an under bet. Godinho's assignment was identified, but no compatible pre-cutoff referee sample was secured.

## Scope and decisions

- Original numerical corner disagreements: Türkiye O4.5, Italy O4.5, total O8.5/O9.5; Sweden O5.5, Poland O3.5, total O9.5.
- Priority for the missing Rushbet comparison would have been Türkiye O4.5, Türkiye–Italy total corners, Poland O3.5 and Sweden–Poland total corners. Sweden team O5.5 is source-sensitive; Italy team O4.5 has contrary distribution evidence.
- Expanded result diagnostic: Poland win is the largest gap retained in both supplied goal scenarios. Türkiye and Romania wins have smaller/more fragile gaps.
- Goals totals/BTTS/team-goals: no priced selection survives both diagnostics; this does not prove the market correct.
- Bookings: under hypotheses, especially Sweden–Poland total and Poland team, remain unpriced research questions.
- First-half and player markets lack appropriate inputs. Asian lines, exact-score/combinations and highly correlated derivatives are not promoted to separate discoveries. No weather, lineup or similar-opponent numerical adjustment was invented without a specified estimator and timestamped inputs.
- No new declaration, settlement, return or hit-rate entry. The existing pilot remains 11 declarations, 7 wins, 4 losses, zero pending, with mixed historical/prospective provenance.

## Data correction

The old Türkiye–Italy total O9.5 corner row contains a stale ev_under despite under_odds being null. That value is invalid. This review omits it and appends an annotation to the ledger; the original event is preserved. No opposite 9.5 price is inferred from the 8.5 table.

## Reproducibility

Run python3 research/lean_hypothesis_ledger/retrospective_20260928/replay.py from the repository. calculations.json contains both sides of every supported two-way quote, both goal scenarios, normalized reference probabilities, break-even gaps and hypothetical EV. EV is arithmetic on diagnostic probabilities, not expected realized profit validated by calibration. No-vig uses normalized reciprocals of each same-row quote pair; secondary quote attribution/timing remains unverified.

The corner sensitivity replaces the screenshot overall rate/N with SportsGambler last-10 overall rates, while retaining the same venue context and original formula. It is a newly constructed source/window check, not a new fitted model or a confidence bound.

## Sources and retrieval classes

Recorded pre-match sources:
- https://www.sportsgambler.com/betting-tips/football/turkey-vs-italy-prediction-lineups-odds-2026-09-28/
- https://www.sportsgambler.com/betting-tips/football/sweden-vs-poland-prediction-lineups-odds-2026-09-28/
- https://www.sportsgambler.com/betting-tips/football/romania-vs-bosnia-herzegovina-prediction-lineups-odds-2026-09-28/
- https://yesplay.bet/sports/events/turkiye-italy-68931480
- https://yesplay.bet/sports/events/sweden-poland-68932616
- https://scores24.live/en/soccer/m-28-09-2026-romania-bosnia-herzegovina-prediction (editorial yellow-card quote)

Additional contextual pages retrieved after completion, not used to refit numeric inputs:
- https://tipsters.net/matches/soccer/28-09-2026-turkey-italy
- https://legalbet.com/game-center/turkey-italy-28-09-2026/
- https://scores24.live/en/soccer/m-28-09-2026-sweden-poland-prediction
- https://www.uefa.com/uefanationsleague/match/2047985--sweden-vs-poland/
- https://www.nfsbih.ba/en/teams/men/a-national-team/a-national-team-matches?id=292&view=match

SportsGambler pages were re-read after completion for contextual histories; only explicitly earlier dated matches informed narrative. Dynamic result panels, current cumulative statistics and match outcomes are excluded from calculations. Snapshot sources may update, so stored ledger numbers govern the replay.

## Complete calculated scan

### Türkiye–Italy — corners

| Market | p lean | Odds | BE | No-vig ref | Gap BE pp | Other-window p |
|---|---:|---:|---:|---:|---:|---:|
| Türkiye over 4.5 corners | 69.04% | 1.8772 | 53.27% | 48.52% | +15.77 | 72.81% |
| Türkiye under 4.5 corners | 30.96% | 1.7692 | 56.52% | 51.48% | -25.56 | 27.19% |
| Italy over 4.5 corners | 59.51% | 2.0700 | 48.31% | 43.92% | +11.21 | 70.82% |
| Italy under 4.5 corners | 40.49% | 1.6211 | 61.69% | 56.08% | -21.20 | 29.18% |
| Total over 8.5 corners | 77.06% | 1.6711 | 59.84% | 55.09% | +17.23 | 84.82% |
| Total under 8.5 corners | 22.94% | 2.0500 | 48.78% | 44.91% | -25.84 | 15.18% |
| Total over 9.5 corners | 66.27% | 2.0400 | 49.02% | unavailable | +17.25 | 76.19% |

Goals: GF/GA and xG/xGA diagnostics, not fitted model probabilities.

| Market | Odds | BE | p GF/GA | p xG/xGA | Gap BE GF/GA | Gap BE xG/xGA |
|---|---:|---:|---:|---:|---:|---:|
| Total 2.5 goals over | 1.64 | 60.94% | 64.85% | 52.34% | +3.92 | -8.60 |
| Total 2.5 goals under | 2.20 | 45.45% | 35.15% | 47.66% | -10.31 | +2.21 |
| BTTS (over=Yes; under=No) over | 1.54 | 64.94% | 65.79% | 56.14% | +0.85 | -8.80 |
| BTTS (over=Yes; under=No) under | 2.39 | 41.84% | 34.21% | 43.86% | -7.63 | +2.02 |
| Total 1.5 goals over | 1.20 | 83.33% | 84.62% | 76.38% | +1.29 | -6.96 |
| Total 1.5 goals under | 4.40 | 22.73% | 15.38% | 23.62% | -7.35 | +0.90 |
| Total 2.5 goals over | 1.65 | 60.61% | 64.85% | 52.34% | +4.25 | -8.27 |
| Total 2.5 goals under | 2.20 | 45.45% | 35.15% | 47.66% | -10.31 | +2.21 |
| Total 3.5 goals over | 2.55 | 39.22% | 42.85% | 30.14% | +3.63 | -9.08 |
| Total 3.5 goals under | 1.50 | 66.67% | 57.15% | 69.86% | -9.51 | +3.19 |
| Total 4.5 goals over | 4.50 | 22.22% | 24.47% | 14.77% | +2.25 | -7.45 |
| Total 4.5 goals under | 1.19 | 84.03% | 75.53% | 85.23% | -8.51 | +1.20 |
| Türkiye 0.5 goals over | 1.25 | 80.00% | 79.71% | 73.68% | -0.29 | -6.32 |
| Türkiye 0.5 goals under | 3.55 | 28.17% | 20.29% | 26.32% | -7.88 | -1.85 |
| Türkiye 1.5 goals over | 2.20 | 45.45% | 47.35% | 38.55% | +1.89 | -6.90 |
| Türkiye 1.5 goals under | 1.60 | 62.50% | 52.65% | 61.45% | -9.85 | -1.05 |
| Türkiye 2.5 goals over | 4.70 | 21.28% | 21.54% | 15.10% | +0.26 | -6.17 |
| Türkiye 2.5 goals under | 1.15 | 86.96% | 78.46% | 84.90% | -8.49 | -2.06 |
| Italy 0.5 goals over | 1.20 | 83.33% | 82.54% | 76.19% | -0.80 | -7.14 |
| Italy 0.5 goals under | 4.10 | 24.39% | 17.46% | 23.81% | -6.93 | -0.58 |
| Italy 1.5 goals over | 1.94 | 51.55% | 52.06% | 42.02% | +0.51 | -9.53 |
| Italy 1.5 goals under | 1.77 | 56.50% | 47.94% | 57.98% | -8.56 | +1.48 |
| Italy 2.5 goals over | 3.90 | 25.64% | 25.47% | 17.50% | -0.17 | -8.14 |
| Italy 2.5 goals under | 1.22 | 81.97% | 74.53% | 82.50% | -7.44 | +0.53 |
| Türkiye win | 2.95 | 33.90% | 35.46% | 35.02% | +1.56 | +1.12 |
| Draw | 3.45 | 28.99% | 22.81% | 25.40% | -6.18 | -3.58 |
| Italy win | 2.38 | 42.02% | 41.74% | 39.58% | -0.28 | -2.44 |

Cards diagnostics: no verified comparable prices.

| Market | Raw p | Diagnostic fair odds |
|---|---:|---:|
| Türkiye under 1.5 cards | 25.42% | 3.935 |
| Türkiye under 2.5 cards | 50.10% | 1.996 |
| Türkiye under 3.5 cards | 72.07% | 1.388 |
| Italy under 1.5 cards | 51.53% | 1.941 |
| Italy under 2.5 cards | 77.56% | 1.289 |
| Italy under 3.5 cards | 91.70% | 1.091 |
| Total under 3.5 cards | 37.72% | 2.651 |
| Total under 4.5 cards | 57.04% | 1.753 |
| Total under 5.5 cards | 73.67% | 1.357 |

### Sweden–Poland — corners

| Market | p lean | Odds | BE | No-vig ref | Gap BE pp | Other-window p |
|---|---:|---:|---:|---:|---:|---:|
| Sweden over 5.5 corners | 54.07% | 2.0700 | 48.31% | 43.90% | +5.76 | 43.22% |
| Sweden under 5.5 corners | 45.93% | 1.6200 | 61.73% | 56.10% | -15.79 | 56.78% |
| Poland over 3.5 corners | 72.42% | 1.6300 | 61.35% | 55.83% | +11.07 | 73.50% |
| Poland under 3.5 corners | 27.58% | 2.0600 | 48.54% | 44.17% | -20.96 | 26.50% |
| Total over 9.5 corners | 64.18% | 1.9100 | 52.36% | 48.24% | +11.83 | 57.60% |
| Total under 9.5 corners | 35.82% | 1.7800 | 56.18% | 51.76% | -20.36 | 42.40% |

Goals: GF/GA and xG/xGA diagnostics, not fitted model probabilities.

| Market | Odds | BE | p GF/GA | p xG/xGA | Gap BE GF/GA | Gap BE xG/xGA |
|---|---:|---:|---:|---:|---:|---:|
| Total 2.5 goals over | 1.64 | 60.98% | 65.64% | 54.59% | +4.66 | -6.39 |
| Total 2.5 goals under | 2.20 | 45.45% | 34.36% | 45.41% | -11.09 | -0.04 |
| BTTS (over=Yes; under=No) over | 1.56 | 64.10% | 66.30% | 57.81% | +2.19 | -6.29 |
| BTTS (over=Yes; under=No) under | 2.30 | 43.48% | 33.70% | 42.19% | -9.78 | -1.29 |
| Total 2.5 goals over | 1.61 | 62.11% | 65.64% | 54.59% | +3.53 | -7.52 |
| Total 2.5 goals under | 2.23 | 44.84% | 34.36% | 45.41% | -10.48 | +0.57 |
| Total 3.5 goals over | 2.48 | 40.32% | 43.73% | 32.26% | +3.40 | -8.07 |
| Total 3.5 goals under | 1.50 | 66.67% | 56.27% | 67.74% | -10.39 | +1.08 |
| Sweden 0.5 goals over | 1.14 | 87.72% | 83.39% | 77.91% | -4.33 | -9.81 |
| Sweden 0.5 goals under | 4.70 | 21.28% | 16.61% | 22.09% | -4.66 | +0.81 |
| Sweden 1.5 goals over | 1.71 | 58.48% | 53.57% | 44.55% | -4.91 | -13.93 |
| Sweden 1.5 goals under | 1.97 | 50.76% | 46.43% | 55.45% | -4.33 | +4.69 |
| Sweden 2.5 goals over | 3.15 | 31.75% | 26.80% | 19.37% | -4.94 | -12.38 |
| Sweden 2.5 goals under | 1.30 | 76.92% | 73.20% | 80.63% | -3.73 | +3.71 |
| Poland 0.5 goals over | 1.32 | 75.76% | 79.51% | 74.21% | +3.75 | -1.55 |
| Poland 0.5 goals under | 3.00 | 33.33% | 20.49% | 25.79% | -12.84 | -7.54 |
| Poland 1.5 goals over | 2.49 | 40.16% | 47.02% | 39.25% | +6.86 | -0.91 |
| Poland 1.5 goals under | 1.45 | 68.97% | 52.98% | 60.75% | -15.99 | -8.22 |
| Poland 2.5 goals over | 5.40 | 18.52% | 21.28% | 15.57% | +2.76 | -2.94 |
| Poland 2.5 goals under | 1.10 | 90.91% | 78.72% | 84.43% | -12.19 | -6.48 |
| Sweden win | 1.92 | 52.08% | 43.07% | 41.04% | -9.01 | -11.04 |
| Draw | 3.80 | 26.32% | 22.59% | 24.87% | -3.72 | -1.45 |
| Poland win | 3.65 | 27.40% | 34.33% | 34.09% | +6.94 | +6.69 |

Cards diagnostics: no verified comparable prices.

| Market | Raw p | Diagnostic fair odds |
|---|---:|---:|
| Sweden under 1.5 cards | 51.53% | 1.941 |
| Sweden under 2.5 cards | 77.56% | 1.289 |
| Sweden under 3.5 cards | 91.70% | 1.091 |
| Poland under 1.5 cards | 40.60% | 2.463 |
| Poland under 2.5 cards | 67.67% | 1.478 |
| Poland under 3.5 cards | 85.71% | 1.167 |
| Total under 3.5 cards | 50.89% | 1.965 |
| Total under 4.5 cards | 70.07% | 1.427 |
| Total under 5.5 cards | 84.00% | 1.191 |

### Romania–Bosnia — corners

| Market | p lean | Odds | BE | No-vig ref | Gap BE pp | Other-window p |
|---|---:|---:|---:|---:|---:|---:|
| Romania over 4.5 corners | 49.27% | 1.8600 | 53.76% | 48.90% | -4.50 | 44.40% |
| Romania under 4.5 corners | 50.73% | 1.7800 | 56.18% | 51.10% | -5.45 | 55.60% |
| Bosnia over 3.5 corners | 55.55% | 1.6000 | 62.50% | 56.99% | -6.95 | 58.10% |
| Bosnia under 3.5 corners | 44.45% | 2.1200 | 47.17% | 43.01% | -2.72 | 41.90% |
| Total over 8.5 corners | 48.72% | 1.7100 | 58.48% | 53.66% | -9.76 | 47.00% |
| Total under 8.5 corners | 51.28% | 1.9800 | 50.51% | 46.34% | +0.77 | 53.00% |

Goals: GF/GA and xG/xGA diagnostics, not fitted model probabilities.

| Market | Odds | BE | p GF/GA | p xG/xGA | Gap BE GF/GA | Gap BE xG/xGA |
|---|---:|---:|---:|---:|---:|---:|
| Total 2.5 goals over | 2.00 | 50.00% | 58.35% | 42.51% | +8.35 | -7.49 |
| Total 2.5 goals under | 1.78 | 56.18% | 41.65% | 57.49% | -14.53 | +1.31 |
| BTTS (over=Yes; under=No) over | 1.75 | 57.14% | 59.65% | 47.48% | +2.51 | -9.67 |
| BTTS (over=Yes; under=No) under | 1.97 | 50.76% | 40.35% | 52.52% | -10.41 | +1.76 |
| Romania win | 2.32 | 43.10% | 48.48% | 44.84% | +5.37 | +1.74 |
| Draw | 3.25 | 30.77% | 23.45% | 27.27% | -7.31 | -3.50 |
| Bosnia win | 3.05 | 32.79% | 28.07% | 27.89% | -4.72 | -4.89 |

Cards diagnostics: no verified comparable prices.

| Market | Raw p | Diagnostic fair odds |
|---|---:|---:|
| Romania under 1.5 cards | 35.70% | 2.801 |
| Romania under 2.5 cards | 62.54% | 1.599 |
| Romania under 3.5 cards | 82.13% | 1.218 |
| Bosnia under 1.5 cards | 31.28% | 3.197 |
| Bosnia under 2.5 cards | 57.49% | 1.739 |
| Bosnia under 3.5 cards | 78.29% | 1.277 |
| Total under 3.5 cards | 33.06% | 3.025 |
| Total under 4.5 cards | 51.89% | 1.927 |
| Total under 5.5 cards | 69.09% | 1.447 |
