"""Shared deprecation notice for the EV / edge / market-comparison layer.

WHY THIS LAYER IS DEPRECATED
============================
The market-beating objective is **closed**. It was not abandoned on a hunch — it
was measured. Five hypotheses were tested and honestly killed (metric discovery,
down-tier inefficiency, same-game correlation, multi-feature regularization, and
matchup asymmetry), and the edge-gap measurement established the ceiling
*directly*: median edge 0-1pp against a required 2-4pp threshold, with the
market's realized rate inside the 95% CI of its price in every well-populated
bucket. The finding is documented in the failure ledger and the project reports.

WHAT THIS MEANS FOR THIS CODE
=============================
Everything in this layer — expected value, edge, de-vig / fair-probability,
Kelly, CLV, "beat the bookie" metrics — is **deprecated**. It is retained, NOT
deleted, for two reasons:

1. **Pilot C.** A pre-registered forward experiment is still running against
   Betfair. Its ledger, cron, pre-registration, and analysis path depend on some
   market-comparison building blocks and MUST NOT be disturbed. Deprecation is
   documentation, not removal.
2. **Internal research only.** The market-comparison *capability* stays available
   for research, clearly labelled as **not a product claim**. No user-facing or
   newly built artifact may present EV, edge, "value bet", "beats the market", or
   edge percentages.

THE PRODUCT IS CALIBRATION
==========================
The project's validated deliverable is a *calibrated prediction engine* — when
the model says 65%, the outcome happens about 65% of the time. See
:mod:`src.research.prediction_engine` for the supported, in-scope replacement.
Do not build new features on top of this deprecated EV layer.

NO STAKE SIZING, EVER
=====================
Do not add stake sizing, Kelly fractions, or bankroll recommendations anywhere,
now or later. The Kelly code that remains here is deprecated research scaffolding,
not a sanctioned sizing tool.
"""

from __future__ import annotations

import warnings

#: Canonical deprecation message reused across the EV layer.
EV_LAYER_DEPRECATION = (
    "The EV / edge / market-comparison layer is DEPRECATED. The market-beating "
    "objective was tested and closed (edge ceiling measured directly; see the "
    "failure ledger). This code is retained for Pilot C and internal research "
    "ONLY and is NOT a product claim. The supported deliverable is the calibrated "
    "prediction engine in src.research.prediction_engine. Do not present EV, "
    "edge, value, or 'beats the market' framing in any user-facing output, and "
    "never add stake sizing."
)


def warn_ev_layer_deprecated(detail: str = "") -> None:
    """Emit the standard EV-layer :class:`DeprecationWarning`.

    Call from the ``__init__`` / entry point of a deprecated EV construct. The
    warning is informational; it never blocks Pilot C, which knowingly consumes
    the retained market-comparison building blocks for its pre-registered
    forward experiment.

    Args:
        detail: optional extra context appended to the standard message.
    """
    message = EV_LAYER_DEPRECATION
    if detail:
        message = f"{message} — {detail}"
    warnings.warn(message, DeprecationWarning, stacklevel=3)
