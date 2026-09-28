# Lean Market Hypothesis Ledger V1

Purpose: preserve simple, market-facing football hypotheses exactly as discussed before settlement, without turning the LLM into a predictor.

## Scientific role

This ledger tests whether focused pre-match summary statistics (including 365Scores-style aggregates), shrinkage, and explicit conditional hypotheses can identify useful market disagreements before richer infrastructure is added.

The deterministic engine remains responsible for any probability, calibration, no-vig comparison, edge estimate, or promotion decision.

## Rules

1. Append-only event log: declarations and settlements are separate JSONL events.
2. Never edit a declared market, threshold, side, price, or rationale after settlement is known.
3. Exact market hypotheses count only when direction and threshold were explicit before settlement.
4. Prices are stored only when captured; missing prices remain null.
5. Chat-derived historical entries are labeled `CHAT_BACKFILL` and are not equivalent to repository-time preregistration.
6. A live/pending hypothesis backfilled from an earlier pre-match chat is labeled accordingly; the repository commit time is later than the original chat claim.
7. Settlement is recorded separately and never used to rewrite the declaration rationale.
8. Correlated hypotheses are kept as separate observations and must not be treated as independent trials.
9. Hit rate is descriptive only; promotion requires OOS Log Loss/Brier/calibration, market comparison, CLV and prospective settlement evidence.
10. No football API calls, model changes, CHAMPION changes, or production-path dependencies belong in this ledger.

## Current experiment question

Can a lean evidence layer using focused team/market statistics plus deterministic shrinkage and conditional state features perform competitively enough that parts of the heavier research apparatus can be removed?

This file deliberately does not answer that question. The ledger exists to prevent hindsight and cherry-picking while the evidence accumulates.

## Market benchmark rule

For every new hypothesis, capture both sides of the same bookmaker market when available. Store reciprocal implied probabilities, the two-way overround, and the proportional no-vig market probabilities. The no-vig probability is the market benchmark; it is not `p_model`. A model edge may only be calculated later from a deterministic/statistical probability produced outside the LLM.
