# Adversarial review — prospective live-capture phase

Branch: `research/prospective-live-capture` · Baseline: `ab883da64` (PR #6 merge)

Independent skeptical pass over the 28 mission attack vectors. No API key is
present in this environment, so items requiring live payloads are validated at
the contract/code level; that limitation is stated, not hidden.

| # | Attack | Finding | Guard / test |
|---|--------|---------|--------------|
| 1 | Secret leakage | Key read from env only; never stored/serialized; log redaction filter; `to_dict` has no key. | PR#6 `test_no_api_key_in_capture_serialization`; `test_client_base_url_and_bearer` asserts header built, not stored. |
| 2 | Wrong API base URL | Uses `LIVE_BASE_URL` = `…/api`; re-verified vs live docs (unchanged). | `test_client_base_url_and_bearer`. |
| 3 | Wrong auth scheme | Bearer `Authorization` header. | `test_client_base_url_and_bearer`. |
| 4 | Schema drift | Critical-field validators raise `SchemaDriftError`; noncritical new keys ignored. | `test_schema_drift_missing_field`, `test_schema_drift_wrong_type`. |
| 5 | Quota exhaustion | `should_pause` pauses at/below remaining threshold; unknown headers => pause. | `test_rate_limit_pause_on_exhaustion_and_unknown`. |
| 6 | 429 loops | Client honours `Retry-After`; collector bounded by `max_requests`. | client 429 branch; `capture_due(max_requests=...)`. |
| 7 | Duplicate captures | Store idempotent on observation id. | `test_capture_due_restart_safe` (rerun => 0). |
| 8 | Overwrite earlier observation | Append-only; never rewrites a line. | probe: file unchanged after reschedule; `test_scheduler_rescheduled_kickoff_does_not_rewrite`. |
| 9 | Future snapshot leakage | Scheduler reads only persisted store; observed_at is real retrieval time. | scheduler reads store only. |
| 10 | Post-kickoff close | `resolve_genuine_close` requires observed_at < kickoff. | `test_genuine_close_post_kickoff_excluded`. |
| 11 | `last_seen` mislabeled as close | Only PROSPECTIVE snapshots qualify; last_seen refused. | `test_genuine_close_never_last_seen`. |
| 12 | Cross-bookmaker fake movement | `price_movement_logit` requires same book. | `test_cross_bookmaker_movement_refused`. |
| 13 | Cross-line fake movement | Same movement fn requires same line; line change tracked separately. | `test_cross_line_movement_refused_but_line_move_tracked`. |
| 14 | Lineup availability fabricated historically | Trustworthy timestamp is our first observed_at; historical payloads without it are not PIT-usable (PR#6). | PR#6 `test_historical_lineup_without_capture_time_not_pit_usable`. |
| 15 | First lineup timestamp overwritten | Scheduler takes MIN observed_at; snapshots append-only. | `CaptureScheduler.lineup_observed` (min). |
| 16 | Injury inferred from absence | `player_status` returns None for unlisted players; reason only from explicit records. | `test_absence_not_inferred_as_injury`. |
| 17 | Player future-match leakage | PR#6 `build_player_state` strict kickoff < cutoff. | PR#6 `test_future_and_current_matches_excluded`. |
| 18 | Kickoff reschedule corruption | Old records untouched; classification uses kickoff supplied at query time. | `test_scheduler_rescheduled_kickoff_does_not_rewrite`. |
| 19 | DST / timezone error | Everything parsed to UTC; offset timestamps normalized; naive treated as UTC. | `test_parse_utc_z_and_offset` + probe (`+02:00` == `Z`). |
| 20 | Identity collision | Stable ids only; no name joins (PR#6). | PR#6 `test_stable_player_ids_required`. |
| 21 | Home/away inversion | Preserved by team id through normalization (PR#6). | PR#6 `test_home_away_not_inverted`. |
| 22 | Restart losing scheduler state | A fresh scheduler reconstructs 'captured' from disk. | `test_scheduler_skips_already_captured_vintage`; restart probe. |
| 23 | Missed vintage silently omitted | `best_capture_for_vintage` returns explicit `MISSED`. | `test_missed_vintage_represented`. |
| 24 | Partial API failure presented as complete | Schema drift raises; health states surface DEGRADED/QUOTA_LIMITED/etc. | `test_schema_drift_*`; `HealthState`. |
| 25 | Live data accidentally staged | `data/prospective/*` git-ignored; verified via `git check-ignore`. | probe: `data/prospective ignored: True`. |
| 26 | Unrelated working-tree edits touched | The 4 preserved edits remain ` M` (unstaged) throughout. | `git status` verified each commit. |
| 27 | Production champion modified | `git diff main -- src/research/models/` empty. | verified; `test_champion_untouched_vs_main` (PR#6). |
| 28 | Tiny sample presented as alpha | Diagnostics always report sample size; readiness gate PRICE_DISCOVERY_NOT_ENOUGH_DATA with pre-registered minimums; no model fitted. | readiness classification in the report. |

## Reproduced issue and fix

**Odds captures could not attribute a bookmaker.** The PR#6 collector stored
the odds concept as `odds:market:selection:line`, dropping the bookmaker, so
per-book coverage and same-book movement could not be reconstructed from the
store — a latent correctness gap for checks 12 and the quality report. **Fix:**
the collector now stores `odds:market:selection:line:bookmaker`, and the
quality report / movement logic key on the bookmaker. Regression:
`test_scheduler_skips_already_captured_vintage` and the capture-due path exercise
the bookmaker-tagged concept.

## Live-validation limitation (stated, not hidden)

`THESTATSAPI_API_KEY` is not set in this environment, so no live requests were
issued. Items 2/3/4 (base URL, auth, live schema) are validated against the
verified contract and the injected-transport tests; no claim is made about live
payload compatibility. Status: **LIVE_VALIDATION_BLOCKED_NO_API_KEY**.
