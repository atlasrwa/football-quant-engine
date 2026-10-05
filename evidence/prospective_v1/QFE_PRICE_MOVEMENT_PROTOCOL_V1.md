# QFE Prospective V1 — Odds Price Movement Scanner Protocol

Protocol hash: b28a5f2bf08476de006633e1e13ce8065f6d9e168796a3ca668d0bb7d44314ae

Status: **FROZEN BEFORE IMPLEMENTATION OR LIVE PRICE-MOVEMENT CAPTURE**

This is a passive market-observation layer. It cannot call or modify the probability model.
It samples registered Goals O/U 2.5 prices every 5 minutes from T-6 until kickoff, only for fixtures with an already frozen prediction bundle.

Operational close is the latest structurally complete eligible bookmaker bundle strictly before kickoff, no more than 600 seconds old. Bookmaker hierarchy is frozen and price attractiveness cannot select a bookmaker or snapshot.

The T-6 entry comparator remains the already-frozen Layer 5 comparator. Post-T6 prices cannot rewrite the entry decision.
Closing-line movement and CLV are evaluation evidence only and never feed back into model, calibration, thresholds, cohort membership, or prediction selection.
