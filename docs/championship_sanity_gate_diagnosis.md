# Diagnosis — Championship Sanity-Gate Failure

**Date:** 2026-08-29
**Question:** Is the Championship sanity-gate failure (Spearman predicted-λ vs realized cards
= −0.105) a **pipeline bug** or a **genuine finding** that the metrics don't transfer?
**Verdict:** **Genuine finding — not a pipeline bug.** The card/foul signals that are strongly
positive on the validated corpus are flat-to-slightly-negative on Championship 25/26, and this
holds *before* the model touches the data (at the raw-feature level), with the adapter verified
correct on orientation, scale, and target definition.
**Zero API calls.** No model/metric/definition changes. No re-run of the Championship analysis
with adjustments. Held-out set untouched.

---

## Headline evidence (the decisive test)

Bypassing the GLM, shrinkage, walk-forward, and everything downstream — the **raw rolling
feature vs the realized outcome** (Spearman):

| Predictor (rolling w5, home+away) → total cards | FootyStats corpus | Championship 25/26 |
|---|---|---|
| team **yellow-card** rate | **+0.177** (p≈1e-98, n=13,992) | **−0.044** (p=0.47, n=275) |
| team **foul** rate | **+0.170** (n=13,700) | **−0.012** (n=405) |
| yellow-card rate, **w10** | **+0.198** (n=12,642) | **−0.014** (n=132) |

Two independent, mechanism-distinct card predictors (a team's own recent cards, and its own
recent fouls) are both strongly positive on the corpus and both vanish on Championship. A wiring
bug in a shared code path would not selectively neutralise *two* predictors while leaving their
means and variance intact — and it would not appear *before* the model, at the raw-feature level
that uses no adapter-specific logic beyond field extraction. This is a property of the data, not
the pipeline.

The model-level −0.105 the sanity gate reported is simply this flat raw relationship, made
slightly more negative by the GLM/shrinkage amplifying a non-signal. Restricting to
larger training windows pulls it back toward zero (−0.023 at n_train≥200), never positive —
consistent with "no signal to fit," not "signal fit incorrectly."

---

## Diagnostic 1 — Schema adapter verification

Traced raw API → adapter → model input on multiple cached matches.

- **Orientation is correct.** Raw `overview.<stat>.all.home` → `team_a_<stat>`,
  `.away` → `team_b_<stat>`. FootyStats convention is `team_a` = home, so this matches. Example
  (Stoke 3–1 Derby): raw `yellow_cards.all = {home:1, away:2}` → `team_a_yellow_cards=1,
  team_b_yellow_cards=2`. Correct.
- **Rolling feature reads each team's OWN cards, not the opponent's.** Traced Stoke City's
  history rows through `ev.extract_stat(match, role, 'yellow_cards')`: every value equals the
  team's own stored card count for that match (home rows read `team_a`, away rows read `team_b`).
  No home/away swap. **The specific bug that would produce a small negative correlation (a
  systematic orientation flip) is ruled out.**
- **Scale is correct.** Championship mean yellows/match = 3.96 vs FootyStats 4.04; adapted
  total-cards mean 4.04 vs corpus 4.24. No units/scaling distortion.

**Conclusion: adapter is not the bug.**

## Diagnostic 2 — Known-good pipeline on known-good data

Intended A/B (same fixture through both the FootyStats path and the TheStatsAPI-adapter path)
**could not be run on identical fixtures**: the 99 legacy `/stats` files in
`data/thestatsapi/cache/` use a match-ID namespace (`mt_0102…`) that has **zero overlap** with
the 1,140 matches in the cached match-lists, so they cannot be reliably joined to the FootyStats
corpus. Reported here so the gap is visible, not hidden.

The equivalent decisive test was run instead (Headline table): the **identical feature-extraction
code** (`ev.get_team_rolling_stat` / `ev.extract_stat`) applied to (a) FootyStats corpus and
(b) adapter output. Same code, same metric, only the data source differs → +0.177 vs −0.044.
Because the code is shared and verified, the divergence is attributable to the **data**, not the
adapter.

## Diagnostic 3 — Within-season walk-forward split (thin history)

**Ruled out.** Every sanity-gate prediction already had **≥19 prior matches for both teams**
(median 32; the split requires ≥60 training rows before the first prediction). There are *no*
1–3-match-history predictions in the set. Breaking the correlation down by available history:

| Restriction | n | Spearman(λ, actual) |
|---|---|---|
| all predictions | 215 | −0.105 |
| min team history ≥ 8 / ≥10 / ≥12 / ≥15 | 215 | −0.105 (unchanged — all already qualify) |
| n_train ≥ 100 | 175 | −0.059 |
| n_train ≥ 150 | 125 | −0.063 |
| n_train ≥ 200 | 75 | −0.023 |

More history/training moves the correlation *toward zero*, never positive. The failure is not a
thin-history artifact.

## Diagnostic 4 — Target-variable sanity check

- **Definition matches.** Both sources define total cards as yellows + reds, both teams; the
  adapter sums the same way. Championship yellow means (3.96) ≈ FootyStats (4.04).
- **Reds are under-recorded on Championship** (`red_cards.all` is null on 91% of matches; reds
  appear in only 9% of matches vs 17% on FootyStats) — the adapter coerces null→0, so
  Championship total-cards is effectively yellows-only. **This does not explain the failure:** on
  FootyStats, using yellows-only vs yellows+reds changes the correlation by only 0.005 (0.172 vs
  0.177). Card counts are otherwise plausible; no evidence of double-counting second-yellows
  distorting the signal.

---

## Why the signal genuinely doesn't transfer (interpretation, hypothesis-level)

The corpus validating the cards metrics is EPL/La Liga/Serie A-era top-flight data. The
mechanism — *a team's recent card rate persists into its next match* — depends on stable,
persistent team-level disciplinary tendencies. Championship 25/26 is a different regime:
promotion/relegation churn (Wrexham, Charlton, Oxford newly up), higher roster turnover, and a
more homogeneous, high-tempo division may compress team-to-team persistence in cards, so recent
card rate carries little forward information within the season. The near-zero raw correlation for
*both* cards and fouls is consistent with genuinely low disciplinary persistence in this
division/season, not a broken instrument.

This is a **generalization finding**: a signal validated across ~25 leagues shows near-zero
within-season persistence on this 26th (Championship 25/26). It is measured on a single season
(n=275 usable), so it is a hypothesis about transferability, not a settled law — the confirmatory
test is to repeat the raw-feature correlation on other Championship seasons (24/25 `sn_2930227`,
23/24), which is cheap and within the existing trial budget.

---

## Verdict

**Not a pipeline bug. The sanity gate correctly reported that the known-good card signal is
absent on Championship 25/26.** All four suspected failure modes were checked and cleared:
adapter orientation (correct), scale/target definition (correct), reds coercion (immaterial),
thin history (absent). The signal is flat at the raw-feature level, before the model, for two
independent predictors — the strongest possible evidence that this is data, not wiring.

The earlier "five sanity-gate failures, four were mis-specification" base rate did make a bug the
prior favourite; this is the case that breaks the streak. The gate did its job: it stopped us
from trusting model-side numbers on a slice where the signal genuinely does not hold.

**No changes made.** Per the ground rules, this pass diagnoses only — no fix, no re-run. A
failure-ledger entry (F016) records this as a generalization finding with the evidence above.

## Reproduction (offline, zero API)

All checks are one-off scripts run against cache; intermediate values shown above are the
evidence. Key comparison reproduces from `scripts/championship_step34_analysis.load_full_history()`
+ `ev_test_metrics_vs_bet365` feature helpers vs `ev.load_footystats_corpus()`.
No shared/global config changed.
