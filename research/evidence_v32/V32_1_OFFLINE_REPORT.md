# QFE V3.2.1 — offline integrity and model comparison report

Status: DEVELOPMENT_ONLY / MARKET_UNTESTED / NOT PROMOTED

Frozen apparatus commit: 682397a1f7e26e81ef4e20eb7375086cd45eea9c
Evidence corpus: 3527 fixtures; 514 raw-stat payloads; competitions {'comp_574977': 562, 'comp_720692': 979, 'comp_9799': 1986}.
No live provider, bookmaker, LLM, Telegram publication, or corner-model refit occurred in this experiment.

## Integrity repairs

- Settlement no longer trusts a single provider finished snapshot. Regulation score requires a four-hour completion buffer, two coherent cached finished snapshots at least five minutes apart, and fail-closed conflict handling.
- The Medellín–Millonarios transient 0-0 settlement would be rejected by the new gate; the append-only effective ledger result is LOSS at 2-2.
- V3.2 model output was formally ABORTED because venue was omitted from the registered design vector and registered week-block uncertainty was not emitted. No V3.2 result is used below.
- V3.2.1 encodes venue explicitly and delays Elo updates until the same 24h feature horizon + 4h completion buffer is satisfied.
- All model inputs come from earlier eligible matches; target-match raw stats never enter its own pre-match feature vector.

## Evidence / feature contract

- Goals primary bundle: prior goals for/against; shots; SoT; box shots; big chances; blocked shots; accurate crosses; final-third entries; possession; saves; clearances; corners; lagged competition-local Elo; venue.
- xG is exact provider field overview.expected_goals and is tested only in a separate support-matched arm. npxG remains excluded.
- Cards target is provider-native yellow cards, with fouls, tackles, interceptions, possession and duels_won_percentage. The percentage is not treated as a count.
- Missing is not zero. Period conflicts and unsupported feature columns fail closed. Referee, weather, lineup and other unverified context are not invented.

## Model arms

- BASE_POISSON: regularized side-count model using target history, opponent concession, Elo and venue.
- RICH_POISSON: BASE plus the registered raw-stat bundle.
- RICH_NB: same rich mean model with train-only negative-binomial dispersion.
- RICH_DC_GOALS_ONLY: rich Poisson means plus train-only Dixon–Coles low-score dependence.
- RICH_POISSON_XG: separate support-matched xG supplement; it does not contaminate the primary comparison.
- Side means receive regularized multiplicative calibration fitted only on the chronological calibration segment; test-set calibration intercept/slope remain diagnostics, not fitted inputs.

## Support

- Goals: 295 rich-supported fixtures; xG-matched 144.
- Provider-yellow cards: 179 rich-supported fixtures.
- Colombia appears in training, calibration and test data; no competition-specific promotion is inferred from these small cells.

## Goals and BTTS — RICH_POISSON versus BASE_POISSON

| Target | Primary n | Primary LL gain | Primary Brier delta | Primary week blocks | Secondary n | Secondary LL gain | Secondary Brier delta |
|---|---:|---:|---:|---:|---:|---:|---:|
| BTTS | 72 | +0.011365 | -0.005454 | 3 | 58 | +0.009461 | -0.004328 |
| home>1.5 | 72 | +0.024184 | -0.012482 | 3 | 58 | +0.006805 | -0.002451 |
| away>1.5 | 72 | +0.011656 | -0.005549 | 3 | 58 | +0.016695 | -0.008324 |
| total>2.5 | 72 | +0.010629 | -0.004633 | 3 | 58 | +0.003488 | -0.000905 |
| total>3.5 | 72 | +0.039818 | -0.016845 | 3 | 58 | +0.028716 | -0.012760 |

Positive log-loss gain means the rich model improved on the matched base. Negative Brier delta is better. These are development effects, not confirmation; the primary/secondary test windows contain only 3 and 2 ISO-week blocks respectively.

NB dispersion fitted to the lower boundary (1e-6), making RICH_NB effectively Poisson on this corpus. Dixon–Coles slightly improved joint count likelihood but did not outperform rich Poisson on BTTS; added complexity is therefore not earned by this development evidence.

## Provider-yellow cards — primary fold

| Target | n | RICH_POISSON LL gain | Brier delta | Week blocks |
|---|---:|---:|---:|---:|
| home_yellow>1.5 | 50 | -0.004774 | +0.001646 | 2 |
| away_yellow>1.5 | 50 | +0.007234 | -0.002546 | 2 |
| total_yellow>3.5 | 50 | -0.001559 | +0.000853 | 2 |

The secondary cards fold is INSUFFICIENT_SUPPORT (calibration n=16 < registered minimum 25). Provider-yellow results cannot be promoted to bookmaker bookings until settlement semantics are verified.

## xG support-matched supplement

| Target | n | xG-minus-rich LL gain |
|---|---:|---:|
| BTTS | 30 | -0.002194 |
| home>1.5 | 30 | -0.006225 |
| away>1.5 | 30 | +0.003290 |
| total>2.5 | 30 | -0.002536 |
| total>3.5 | 30 | -0.002102 |

The xG supplement is mixed and does not justify automatic inclusion. It remains a separate candidate.

## Calibration and decision

Primary-fold RICH_POISSON test calibration diagnostics:

| Target | Intercept | Slope |
|---|---:|---:|
| BTTS | -0.2928 | 1.7085 |
| home>1.5 | -0.0722 | 0.6919 |
| away>1.5 | -0.3386 | 0.5630 |
| total>2.5 | -0.2474 | 1.3920 |
| total>3.5 | +1.1938 | 2.8949 |

The count-scale calibration is not sufficient evidence of market-ready calibration. Several test calibration slopes remain materially away from 1, and the chronological development test windows have too few independent week blocks. Calibration preservation/noninferiority is therefore NOT ESTABLISHED.

No model is promoted. No probability from this experiment is wired to Telegram or the live V3 disagreement path. Historical market comparison is MARKET_UNTESTED because trustworthy matched cached odds are not available for this research cohort.

The next scientifically valid step is more chronological/prospective evidence, then a preregistered distribution-preserving calibration comparison. Existing results stay frozen; they are development data forever.
