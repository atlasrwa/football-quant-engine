# Quant Football Engine

Quant Football Engine (QFE) is a deterministic probabilistic football
forecasting and market-disagreement research engine.

The governing architecture is
[QUANT_FOOTBALL_SOURCE_OF_TRUTH.md](QUANT_FOOTBALL_SOURCE_OF_TRUTH.md).

## Reboot objective

QFE builds an odds-blind football probability first, validates its
point-in-time integrity and probability quality, calibrates it, and only then
compares it with timestamp-matched no-vig market probability.

The operational discovery target is **credible market disagreement**.
Disagreement magnitude is not a model-training objective.

## Single active product

**QFE V2 is the only active product and forward development path on `main`.**
The legacy CHAMPION is deprecated and is not a fallback, parallel product, or
production probability path. Historical CHAMPION commits and isolated frozen
pilot worktrees remain available only for audit, settlement, and preservation
of already-running prospective evidence.

## Reboot core retained on main

- TheStatsAPI provider, normalization and provenance primitives.
- Canonical identity and point-in-time observation storage.
- Immutable fixture, odds and forecast-vintage contracts.
- No-vig reconciliation and closing-line/CLV primitives.
- Deterministic count, hierarchical, latent-state and calibration models.
- Prospective capture, quality, vintage and genuine-close infrastructure.
- Focused tests for the retained primitives.

Historical LLM, hypothesis-discovery, Pilot C, in-play, same-game, legacy
broadcast and one-off experiment apparatus were removed from the main tree.
They remain available in Git history.

## Protected live experiments

The currently running V3.7 Future50 and V3.8 Paired50 experiments execute from
isolated worktrees under `/home/ubuntu/handoff_out/`. Their code and schedules
are not controlled by the reboot branch and must remain unchanged until their
prospective experiments finish.
