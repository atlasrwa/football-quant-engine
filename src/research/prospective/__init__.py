"""Prospective research plane: MARKET PRIOR + INDEPENDENT FUNDAMENTAL + INFO DELTA.

This package builds *leakage-safe* infrastructure to answer a single research
question:

    Does the engine contain repeatable information that improves upon the
    market prior, and can confirmed lineup / player-state information create
    additional predictive value?

It is a research / data-plane layer. It does NOT modify the champion model
(``src/research/models/hierarchical_market_model.py``); it only *wraps* the
champion's output as a neutral :class:`~src.research.prospective.fundamental.FundamentalForecast`.

Design pillars (enforced across every module):

- The MARKET is the prior. The statistical engine is the challenger.
- Odds honesty: ``last_seen`` is NOT a genuine closing line. A genuine research
  close is derived only from our OWN timestamped snapshots with
  ``observed_at < kickoff``.
- Missing != zero != None. We reuse the ``MISSING`` sentinel from the
  observation layer and never coerce absence into a numeric zero.
- Point-in-time: an observation is only consultable for a forecast when
  ``observed_at <= forecast_cutoff``.  Observations lacking ``observed_at`` are
  never consultable for a finite cutoff (fail closed).
- No injury fabrication: absence from a starting XI is NEVER interpreted as an
  injury. ``availability_reason`` defaults to ``UNKNOWN`` unless the provider
  states a reason explicitly.
- Residual shrinks toward the MARKET (not 0.5, not climatology) when evidence
  is weak.

All network access is guarded and fails closed when no API key is configured.
The API key is never printed, logged, committed, or serialized.
"""

from __future__ import annotations

__all__ = [
    "api_contract",
]
