# Adversarial review — prospective market-residual-lineup plane

Branch: `research/market-residual-lineup-alpha`  ·  Baseline: `184f09d`

An independent, skeptical pass attempting to break the results. Each check
states the attack, the finding, and the guard (with the regression test that
locks it in). Credible issues are reproduced, fixed, and regression-tested.

| # | Attack | Finding | Guard / regression test |
|---|--------|---------|-------------------------|
| 1 | Odds leakage into the fundamental | Champion (`hierarchical_market_model`) has no odds input; the residual consumes market as an OFFSET only, never as a champion feature. | `test_disagreement_sign`; champion diff empty vs main. |
| 2 | Lineup leakage (final XI into earlier vintage) | EARLY/MID suppress lineup concepts; confirmed XI observed ~T-90m is after the EARLY cutoff and a lineup concept. | `test_final_lineup_cannot_leak_into_early`, `test_late_may_consult_confirmed_lineup`. |
| 3 | Season-stat leakage | `player_state` only ingests per-match observations; there is no path that reads `/players/{id}/stats` season aggregates into historical features. | `player_state` API has no season-aggregate parameter; `test_usual_starting_probability_prior_only`. |
| 4 | Future player-match leakage | Strict `kickoff < cutoff`; equal timestamp (current fixture) excluded. | `test_future_and_current_matches_excluded`. |
| 5 | Post-kickoff snapshots | Genuine close requires `observed_at < kickoff`; post-kickoff snapshot rejected. | `test_genuine_close_requires_observed_before_kickoff`, `test_genuine_close_picks_latest_before_kickoff`. |
| 6 | `last_seen` mislabeled as close | `API_LAST_SEEN` semantics are excluded from `genuine_close`; only our `PROSPECTIVE_*` snapshots qualify. | `test_last_seen_is_not_genuine_close`. |
| 7 | Bookmaker cherry-picking | Benchmark chosen by a preregistered hierarchy (Pinnacle>Bet365>...), never by best price. | `test_bookmaker_hierarchy_deterministic_no_cherry_picking`. |
| 8 | Home/away inversion | `home`/`away` kept distinct by team id through normalization. | `test_lineup_home_away_and_bench`. |
| 9 | Player identity collision | Players keyed by stable `player_id`; empty id raises `LineupError`. | `test_stable_player_ids_required`. |
| 10 | Team transfer handling | Same `player_id` across different `team_id` keeps one identity. | probe: 2 apps across old/new team; identity preserved. |
| 11 | Missing lineup treated as empty XI | Missing lineup returns `None` (fails neutrally), never an empty XI. | `test_missing_lineup_fails_neutrally`. |
| 12 | Missing player stats treated as zero | All-`None` counts yield `None` per-90 (not 0); zero minutes → `None`. | `test_missing_stat_stays_missing`, `test_zero_minutes_denominator_is_none_not_zero`. |
| 13 | Residual trained against the evaluation set | Residual is fit on the earlier chronological TRAIN split only; eval fixtures never enter `fit`. | `historical_eval.run_historical_eval` splits by kickoff; `test_deterministic_fit`. |
| 14 | Scaling / regularization fit outside the training fold | Standardization mean/std frozen at `fit`; `predict` never refits. | `test_standardization_fit_inside_training_only`. |
| 15 | Repeated lines treated as independent | Paired bootstrap reused with `collapse_lines=True` collapses correlated lines per fixture. | reuse of `paired_block_bootstrap`; decomposition scored per single line. |
| 16 | Stale market observations used silently | Age vs cutoff reported; too-old / future / unknown → `STALE_MARKET`. | `test_stale_market_when_observed_after_cutoff`. |
| 17 | Duplicate API captures | Capture store idempotent on observation id; re-append returns False. | `test_capture_store_append_only_idempotent`. |
| 18 | Accidental champion modification | `git diff main -- src/research/models/` is empty. | CI-style check in report; verified empty. |
| 19 | API key exposure | Key read from env only, never stored/serialized; log filter redacts; `to_dict` has no key. | `test_client_uses_bearer_header` (asserts header built, not stored); grep shows single local header construction. |
| 20 | Hidden dependence on local cache state | Prospective client has no file cache; the collector's `transport` is injected in tests; capture store is explicit and file-scoped. | CLI tests run with injected transport and `tmp_path` store. |

## Reproduced issue and fix

**Residual over-shift (surfaced by check 13/14, not a leak).** In an early
build the ridge-logistic model fit a global intercept by default. With all
features missing this shifted every forecast away from the market
(`p != p_market`), violating "no forecast becomes more extreme merely because a
feature is missing" and "beta=0 ⇒ trust the market". **Fix:** `fit_intercept`
now defaults to `False`, so an all-missing / all-zero feature vector reproduces
the market prior exactly, and the intercept (when enabled) is L2-penalised
toward zero. Regression: `test_zero_features_reproduce_market_after_fit`,
`test_missing_feature_not_extreme`, `test_unfitted_reproduces_market`.

## Honest negative result (not a bug)

On the historical M0-M4 decomposition (goals n=3842, corners n=3583), the
MARKET layer (M3) is the best layer on both families and the fundamentals (M2)
do not beat it. The M4 residual, as configured with a single disagreement
feature, DEGRADES log loss/Brier and collapses calibration slope — evidence
that the fundamental-minus-market disagreement carries little exploitable
historical signal at these lines. This is reported as-is; it was NOT tuned on
the evaluation set to look favourable, and it is exactly the kind of outcome
the infrastructure exists to detect.
