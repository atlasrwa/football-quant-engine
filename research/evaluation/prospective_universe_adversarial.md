# Adversarial review — data-driven competition universe

Branch: `research/prospective-live-capture` (PR #7 continuation) · Baseline main `ab883da64`.

Independent skeptical pass over the 30 mission attack vectors for the full
FootyStats->TheStatsAPI crosswalk, coverage matrix, activation, and quota.

| # | Attack | Finding | Guard / test |
|---|--------|---------|--------------|
| 1 | Wrong league mapped because names similar | Identity comes from the registry's reviewed MATCHED mapping + a canonical-registry link check; names are diagnostic only. | `crosswalk.build_crosswalk`; `test_split_season_stays_ambiguous_and_unjoined`. |
| 2 | Same competition in different countries | Registry mapping is by stable ids; country carried for diagnostics. | crosswalk retains country. |
| 3 | Cup mistaken for league | Registry-level distinction preserved; no name approval. | identity from registry only. |
| 4 | Women's mistaken for men's | Same — stable-id mapping, no fuzzy approval. | no fuzzy in prod. |
| 5 | Reserve/youth collision | Same. | no fuzzy in prod. |
| 6 | Current season mismatch | Season resolved live via `is_current`; recon records it per comp. | recon `season_is_current`. |
| 7 | Split-season mismatch | Multi-id / SPLIT_OR_PARTIAL => AMBIGUOUS, never auto-joined (Mexico Liga MX). | `test_split_season_stays_ambiguous_and_unjoined`. |
| 8 | Stale provider competition id | VERIFIED requires the canonical link to agree with the registry id; a mismatch downgrades to AMBIGUOUS (`level_a_link_mismatch`). | crosswalk link check. |
| 9 | Team overlap misleading (promotion/relegation) | We rely on the reviewed registry mapping (Level A), not raw current-season overlap, so promotion churn cannot flip identity. | identity from registry. |
| 10 | No upcoming fixtures => unsupported | A VERIFIED league with 0 fixtures in scan stays CAPTURE_PARTIAL. | `test_no_fixtures_not_treated_as_unsupported`. |
| 11 | Odds absent on one fixture => league unsupported | odds 404 on the probe => PARTIAL, using registry `odds_available` as the durable signal. | `test_odds_absent_on_one_fixture_not_unsupported`. |
| 12 | Pinnacle absent once => never available | Bookmaker presence recorded per probe; absence lowers priority, never marks the league unsupported; registry odds still drives classification. | classify priority tiers. |
| 13 | Display-name join sneaks into production | Activation keys off `thestatsapi_competition_id` (stable). Names never used to join. | `activation.active_universe`. |
| 14 | Global fixture query returns unrelated comps | Discovery is per-competition scoped (`competition_id`). | `test_discover_upcoming_scoped_to_window_and_universe`; probe. |
| 15 | Pagination hides nearby fixtures | Discovery uses `date_from`/`date_to` + `per_page` and a local horizon filter, not page order. | discovery probe. |
| 16 | Horizon filtering wrong | Local `now <= kickoff <= horizon` enforced after the API date filter. | probe: far fixture excluded. |
| 17 | Timezone/date boundary error | All timestamps parsed to UTC; date filters derived in UTC. | `test_parse_utc_z_and_offset`. |
| 18 | Duplicate fixture | Dedup by stable fixture id during discovery. | probe: dup removed. |
| 19 | Partial universe reported healthy | Health separates NO_UPCOMING_FIXTURES / HEALTHY_WAITING_FOR_VINTAGE / QUOTA_LIMITED / HEALTHY. | `test_capture_due_reports_waiting_for_vintage`. |
| 20 | Quota estimate excludes discovery | `FixtureCostModel` includes amortised discovery + monitoring. | `test_allocation_excludes_naive_division`. |
| 21 | Quota estimate excludes retries | 10% retry overhead in the cost model. | cost model. |
| 22 | Polling explodes request count | Lineup polls bounded (4); scheduler only polls in the LATE window until first observed. | cost model + scheduler windows. |
| 23 | Low-quality leagues dilute usable sample | Analysis-support strata report usable N per stratum, not raw captures. | `test_analysis_support_strata_are_nested`. |
| 24 | Huge league dominates future inference | league + country retained on every row for clustered/block analysis. | `test_dilution_structure_preserved_country_and_league`. |
| 25 | Unknown converted to zero/false | Explicit `is True` / `is False` checks; UNKNOWN preserved. | `test_unknown_odds_stays_unknown_not_false`. |
| 26 | API key leaks | Key via env alias only; never in artifacts; log redaction. | `test_no_key_material_in_artifacts`. |
| 27 | Live corpus staged | `data/prospective/*` git-ignored; recon writes no capture data. | git check-ignore (prior). |
| 28 | Unrelated working-tree files staged | Per-file `git add`; preserved edits remain `M` throughout. | `git status` each commit. |
| 29 | Champion modified | `git diff main -- src/research/models/` empty. | `test_champion_untouched_this_phase`. |
| 30 | Activation tuned on predictive performance | classify()/activation reference NO outcome/prediction/profit; only identity + coverage. | grep: only docstrings mention "performance" (to forbid it). |

## Reproduced issue and fix

**Odds bookmaker attribution & market filtering.** Earlier the collector could
request/normalize markets a league does not price and could not attribute a
bookmaker. Fixed in the prior commit (odds concept carries the bookmaker) and
this phase (per-league eligible-markets filter in `capture_odds` +
`capture_due`), so quota is not wasted on nonexistent markets. Regression:
`test_market_specific_eligibility_retained`, activation eligible-markets tests.

## Live-data limitation

Coverage classification reflects a single point-in-time recon (137 requests).
36/37 CAPTURE_PARTIAL leagues had odds 404 on the probed fixture purely because
their nearest fixtures were not yet priced — recorded as PARTIAL (odds expected),
never as unsupported. Re-running the coverage scan closer to matchdays will
promote many PARTIAL leagues to CAPTURE_READY.
