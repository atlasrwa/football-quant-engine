# FIX 3 — CountRegressionModel consumer audit (same-match feature leakage)

Every live-tree reference to `CountRegressionModel` / `create_corners_model` /
`create_cards_model`, classified by whether it feeds the model **same-match**
(post-match) statistics of the fixture being predicted (LEAKING) or only
prior/identity information (CLEAN). Excludes `.kiro/sessions/` snapshots.

The leak is a **feature-construction** fault in the caller, not in the model math.

| Consumer | Class | Feature source | Published result | Invalidated? |
|---|---|---|---|---|
| `run_benchmark.py` | **LEAKING** | `ResearchMatch.to_dict()` → same-match `shots/attacks/possession/fouls` of the fixture | Original +9.6%/+9.0% BSS (stdout only) | **YES** — figures withdrawn (now PROVISIONAL in scope.py) |
| `run_robustness_check.py` | **LEAKING** | `load_season_features` → same-match stats | Cross-league +6.8%/+6.1% BSS, 91%/96% positive; `robustness_results.json` (75 rows) | **YES** — figures withdrawn; the JSON rows are leak-inflated |
| `scripts/samegame_step2_joint.py` | **LEAKING (marginals only)** | `feat_dict` → same-match stats ("All values are realized match stats") | `data/results/samegame_step2_joint.json`, `docs/samegame_joint_correlation_report.md` | **PARTIAL** — headline verdict rests on MODEL-FREE realized-outcome correlations (cards×corners within-league −0.033) and is a NEGATIVE result, NOT overturned. Only the secondary CountRegressionModel marginal-PMF cross-check inherits the leak; flag those sub-figures. |
| `scripts/quarantine_forward_loop.py` (Pipeline A — not modified) | **MIXED** | `build_training_features` leaks (same-match) at TRAIN; `build_prediction_features` passes ONLY team ids at PREDICT | Forward ledger (not touched) | Prediction-time features carry no same-match stats (collapse to intercept+team-effects), so live forward predictions are not driven by the fixture's own stats; the training fit is on leaked features. Flag: retrain on prior-only features when Pipeline A is next revised. Ledger NOT modified this pass. |
| `scripts/market_first_scanner.py` (scanner — not modified) | **CLEAN** | prediction passes only `home_team_id`/`away_team_id` (team names) | scanner ledger (not touched) | No — no same-match stats reach the model. |
| `src/research/models/factory.py` | **N/A (constructor)** | only builds models; leakage depends on caller's features | none | No — inert. |
| `src/research/governance/enroll_quarantine.py` | **N/A (metadata)** | records the string `"model_class": "CountRegressionModel"` | none | No — no feature construction. |
| `src/research/asymmetric/directional_model.py` (`DirectionalCountModel`) | **SEPARATE MODEL** | a different class; asymmetric interaction features are prior-only ("reads the relevant prior rate from matches strictly BEFORE the current one, then folds the current match in afterwards") | asymmetric-engine outputs | Not a `CountRegressionModel` consumer; the same-match leak does not apply. (A dedicated review of the asymmetric path is out of scope for this pass, but its documented compute-before-update discipline is the correct pattern.) |
| `scripts/audit_reproduce_validation.py`, `scripts/rederive_leakfree_figures.py` | audit tooling | rederive uses the leak-free `prior_only_features` builder + guard | audit/rederivation JSON | Clean by construction (guard runs before every fit). |
| `src/research/models/count_regression.py` | the model | math sound (audit); default feature *docstrings* still describe same-match fields | none | Model math not invalidated. Its default feature schema is what callers wrongly populated with same-match values; the fix is the `prior_only_features` builder + guard. |
| `src/research/models/prior_only_features.py` | **the fix** | strictly-prior rolling means; structural anti-leakage guard | — | — |

## Summary
- **Leaking (invalidates a published figure):** `run_benchmark.py`, `run_robustness_check.py` — the withdrawn corners/cards BSS figures.
- **Leaking, partial scope:** `samegame_step2_joint.py` — only the secondary marginal cross-check; its negative headline verdict stands (model-free).
- **Mixed:** `quarantine_forward_loop.py` (Pipeline A) — leaks at train, clean at predict; ledger untouched, flagged for its next revision.
- **Clean:** `market_first_scanner.py`.
- **Not applicable / separate:** `factory.py`, `enroll_quarantine.py`, `DirectionalCountModel`.

Leak-free replacement: `src/research/models/prior_only_features.py` +
`assert_no_same_match_leakage` (tested in `tests/test_prior_only_features.py`, incl. a
decisive test that the guard RAISES on injected same-match leakage).
