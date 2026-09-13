# OOS Incremental Value (Phase C) — PENDING

**Status: NOT STARTED.** Defines the falsification protocol (brief §33, §34, §57) so the
decision rule is fixed before any numbers exist. No LLM states have been generated.

## The only question that matters
Do validated LLM football states **lower chronological OOS loss** beyond the deterministic
contextual challenger — on identical fixtures and common support?

## Three-way comparison (same folds, same fixtures, same support)
1. **BASE CHAMPION** — frozen Pilot-C elastic-net (`research/contextual_matchup/CHAMPION_FREEZE.json`).
2. **CONTEXTUAL QUANT CHALLENGER** — the matchup/count families already benchmarked in
   `research/contextual_matchup/` (goals PROMISING, cards+referee CLEAR, corners promising).
3. **CONTEXTUAL QUANT + LLM STATES** — (2) plus validated LLM state features (mechanism levels /
   matchup advantages encoded as ordinal/one-hot inputs to the quant layer).

## Protocol
- Chronological expanding walk-forward; all preprocessing train-only; no random split.
- Align folds with the existing PR#18 / contextual_matchup benchmark for direct comparison.
- LLM states generated with `information_cutoff = kickoff`; states for a test fixture are
  produced from prior-only evidence (guaranteed by the packet builder).
- Metrics: LogLoss, Brier, Brier Skill Score, ECE, calibration slope/intercept, AUC, dispersion,
  block-bootstrap CI over competition blocks; classify CLEAR/PROMISING/MARGINAL/INCONCLUSIVE/NEGATIVE.

## Decision rule (brief §34, §57)
- If (3) does **not** beat (2) with acceptable uncertainty → **discard LLM states**, keep the
  quant challenger. Eloquent football analysis is not evidence.
- If (3) beats (2) broadly (not one fold / one league), calibration preserved → freeze as a
  **CANDIDATE_WORTH_PROSPECTIVE_TEST** only.
- Prospective cohort remains untouched throughout (brief §58). No auto-promotion.

## Guard against a rigged comparison
The bar is the **contextual quant challenger**, not the base champion — because the matchup
research already proved that structure beats raw-stat dumps. The LLM must add value *on top of*
the best deterministic structure, or it is rejected.
