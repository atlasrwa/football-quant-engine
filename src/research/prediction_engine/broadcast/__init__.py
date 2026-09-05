"""Forecast publication — broadcast calibrated probabilities at a fixed horizon.

This subpackage publishes *forecasts*, not tips. It exists to put a timestamped,
hashed, both-sided probability on the record before a fixture kicks off, so that
coverage and calibration can later be verified against what was actually said.

WHAT THIS IS
============
A publication layer. For every fixture in a scope that is **declared in config**,
at a **fixed pre-kickoff horizon**, it emits the engine's probability for each
in-scope market — *for both sides* — together with the provenance needed to check
it later (model version, data cutoff, generation time) and a commitment hash over
the exact payload. It then stores that payload append-only.

WHAT THIS IS NOT
================
It is not a signal service, a tip service, or a betting product. Per the permanent
constraint in :mod:`src.research._ev_deprecation`, no artifact here may contain:

* stake size, unit sizing, Kelly fractions, or bankroll guidance,
* expected value, edge, or any "value" figure,
* a recommended side or pick,
* a confidence label, unless the confidence rule is declared in config and applied
  identically to every fixture,
* language implying a bet should be placed.

:func:`~src.research.prediction_engine.broadcast.payload.assert_forecast_only`
enforces this on the rendered message and **fails closed** before anything is sent.
The deprecated ``CryptoSignalExporter`` / ``RiskUnitCalculator`` / ``KellyCalculator``
EV-and-stake path is not imported, reused, or reachable from here.

THE TWO LAYERS STAY SEPARATE
============================
The forecast layer (:mod:`.payload`) and the price layer (:mod:`.price_panel`) do
not import each other and share no state. Prices are captured at the same horizon
moment into the CLV panel store, are never included in the broadcast message, and
can never influence a forecast — the forecast builder takes no price argument at
all, so there is no path by which a price could reach it.

NOTHING IS FILTERED
===================
Every fixture in declared scope is published. There is deliberately no threshold on
probability, no confidence gate, no price band, and no expected-quality filter
anywhere in this subpackage. A forecast the model is unsure about is exactly as
publishable as a confident one; suppressing the unsure ones is what makes a
published record dishonest.
"""

from __future__ import annotations

__all__ = [
    "scope_config",
    "payload",
    "record",
    "delivery",
    "price_panel",
]
