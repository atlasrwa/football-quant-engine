# QFE Foundation V1 — Frozen Capability & Coverage Audit

Frozen on: 2026-10-01
Bundle hash: `e3055bc0ed5afed16e2230d177f8ac4a641092c79d0511fcbba26d0efdb2cf52`

## Scope

Read-only audit of every canonical cached TheStatsAPI season discovered in the local historical corpus. No network calls, model fitting, market optimization, or protected-pilot tuning were performed.

## Corpus summary

- Canonical seasons discovered: **19**
- Seasons audit-usable: **19 / 19**
- Competitions: **6**
- Normalized finished matches: **5640**
- Canonical stats payloads selected: **5636**
- Canonical stats payloads missing: **4**
- Canonical stats conflicts: **0**
- Unique source files fingerprinted: **5655**

## Per-season audit summary

| Season | Matches | Stats join | Corner labels | xG coverage | Within-season history median |
|---|---:|---:|---:|---:|---:|
| comp_3039:sn_3057848 | 380 | 100.000% | 380 | 100.000% | 18.0 |
| comp_3039:sn_6125938 | 380 | 100.000% | 380 | 100.000% | 18.5 |
| comp_8321:sn_3014533 | 81 | 100.000% | 81 | 100.000% | 3.0 |
| comp_3039:sn_8406098 | 40 | 100.000% | 40 | 100.000% | 1.5 |
| comp_0976:sn_1368511 | 55 | 100.000% | 55 | 87.273% | 2.0 |
| comp_8814:sn_8407970 | 51 | 100.000% | 51 | 100.000% | 2.0 |
| comp_0256:sn_3011424 | 36 | 100.000% | 36 | 100.000% | 1.5 |
| comp_9777:sn_7255696 | 54 | 100.000% | 54 | 0.000% | 2.5 |
| comp_0976:sn_8425423 | 462 | 100.000% | 462 | 0.000% | 20.0 |
| comp_0976:sn_8437950 | 462 | 100.000% | 462 | 90.476% | 20.5 |
| comp_8814:sn_5761468 | 380 | 100.000% | 380 | 100.000% | 18.5 |
| comp_8814:sn_7246390 | 380 | 100.000% | 377 | 100.000% | 18.0 |
| comp_0256:sn_6120181 | 305 | 100.000% | 305 | 100.000% | 16.0 |
| comp_0256:sn_6184519 | 306 | 99.673% | 304 | 99.346% | 16.5 |
| comp_9777:sn_3057202 | 306 | 99.020% | 303 | 0.000% | 16.5 |
| comp_9777:sn_3064056 | 306 | 100.000% | 304 | 0.000% | 16.5 |
| comp_8321:sn_2930227 | 552 | 100.000% | 543 | 98.370% | 22.0 |
| comp_8321:sn_3064530 | 552 | 100.000% | 541 | 100.000% | 22.5 |
| comp_8321:sn_343481 | 552 | 100.000% | 551 | 100.000% | 22.5 |

## Aggregate target coverage

| Target | Available | Missing/blocked |
|---|---:|---:|
| bookings_away_regulation | 0 | 5640 |
| bookings_home_regulation | 0 | 5640 |
| bookings_total_regulation | 0 | 5640 |
| corners_away_regulation | 5609 | 31 |
| corners_home_regulation | 5609 | 31 |
| corners_total_regulation | 5609 | 31 |
| goals_away_regulation | 5640 | 0 |
| goals_home_regulation | 5640 | 0 |
| goals_total_regulation | 5640 | 0 |

## Selected provider-field coverage

| Field | Available | Missing | Coverage |
|---|---:|---:|---:|
| corners_home | 5609 | 31 | 99.4504% |
| shots_home | 5612 | 28 | 99.5035% |
| shots_on_target_home | 5611 | 29 | 99.4858% |
| yellow_cards_home | 5455 | 185 | 96.7199% |
| red_cards_home | 920 | 4720 | 16.3121% |
| home_xg | 4450 | 1190 | 78.9007% |

## Contract readiness

- Goals: modelable; Bet365/Pinnacle regulation-time comparison contracts are verified for current goal target definitions.
- Corners: modelable, but commercial bookmaker comparison remains blocked until provider `corner_kicks` is proven equivalent to bookmaker corners-taken settlement.
- Bookings: blocked. Aggregate yellow/red counts cannot reconstruct second-yellow and participant-eligibility settlement semantics.

## Anomalies reviewed

- **GLOBAL_LEGACY_STATS_ALIAS_CONFLICTS** [INFORMATIONAL_NONBLOCKING] — count 16
  - Conflicting duplicate stats payloads exist in legacy cache families. Canonical per-season audits do not use those aliases and reported zero canonical conflicts.
- **MISSING_CANONICAL_STATS_PAYLOADS** [COVERAGE] — count 4
  - Fixture/result rows remain usable for goals; stats-derived features and targets are unavailable for these matches.
- **MISSING_CORNER_TARGETS** [COVERAGE] — count 31
  - Four cases lack canonical stats files; remaining cases have provider corner_kicks.all = null. Missing labels must be excluded, never imputed.
- **XG_HETEROGENEOUS_COVERAGE** [CAPABILITY]
  - xG cannot be a mandatory universal feature. Models must use explicit capability/missingness handling or a target-specific optional branch.
  - Zero-coverage seasons: comp_9777:sn_7255696, comp_0976:sn_8425423, comp_9777:sn_3057202, comp_9777:sn_3064056
  - Partial-coverage seasons: comp_0976:sn_1368511=87.27%, comp_0976:sn_8437950=90.48%, comp_0256:sn_6184519=99.35%, comp_8321:sn_2930227=98.37%
- **RED_CARD_SPARSE_COVERAGE** [CAPABILITY]
  - Provider red-card nulls are preserved as missing, never zero. Any later use as historical evidence must be optional/missingness-aware; bookings targets remain blocked independently.
  - Aggregate side coverage: 16.31%
- **CANONICAL_SEASON_BLOCKERS** [NONE] — count 0

## History-support interpretation

History-support figures in this audit are **within each audited season only**. They intentionally reset at season boundaries and therefore understate the support available to the eventual multi-season point-in-time training corpus.

## Scientific interpretation

This audit validates data identity, semantics, coverage, target availability, point-in-time construction, and immutable provenance. It does **not** establish predictive superiority, calibration quality, market edge, or profitability.
