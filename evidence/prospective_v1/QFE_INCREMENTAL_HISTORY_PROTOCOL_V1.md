# QFE Prospective V1 — Incremental History Protocol

Protocol hash: 3cb61328740d2d9bc3af93a097c2f04358fda2f9878ad1eb3da04d6c38ab663a

Status: **FROZEN BEFORE LIVE INCREMENTAL-HISTORY CALLS**

The canonical audited corpus ends on September 13–14, 2026 depending on competition. Prospective V1 therefore requires a separate immutable football-only refresh before any October cohort is selected.

The refresh is deterministic across the six frozen model competitions:
- query all pages of the frozen current season with stage=regular and status=finished;
- retain every fixture after that competition's audited base boundary;
- fetch exactly one /stats payload per retained fixture;
- retain raw payload bytes/hashes and actual retrieval timestamps;
- no odds, lineups, market prices, cohort outcomes or target-based filtering.

A partial or quota-truncated refresh is never prediction-eligible.
