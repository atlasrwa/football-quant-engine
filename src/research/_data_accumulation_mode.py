"""DATA ACCUMULATION MODE switch — suppress unvalidated publication cleanly.

During data accumulation the engine collects prospective evidence but must NOT
publish prediction/signal output to the audience. This module is the single,
documented, reversible switch that the publishing paths consult.

When the mode is ON:
- the forecast broadcaster still COMPUTES probabilities, COMMITS them to the
  append-only ledger, and captures prices — but it does NOT transmit to the
  public Telegram channel (delivery is routed to SUPPRESSED_RESEARCH_ONLY);
- the live-signals Telegram bot does not publish tips.

The underlying forecast/signal capability is preserved; only external
publication is withheld until a future explicit promotion decision.

Enabled by default (fail-safe: suppress unless explicitly turned off), and can
be toggled with the ``DATA_ACCUMULATION_MODE`` environment variable:
    DATA_ACCUMULATION_MODE=1/true/on   -> suppress publication (default)
    DATA_ACCUMULATION_MODE=0/false/off -> allow publication (future promotion)
"""

from __future__ import annotations

import os

#: The reason string recorded when a message is withheld.
SUPPRESSED_RESEARCH_ONLY = "SUPPRESSED_RESEARCH_ONLY"

_TRUE = {"1", "true", "on", "yes"}
_FALSE = {"0", "false", "off", "no"}


def is_data_accumulation_mode() -> bool:
    """Whether publication is suppressed. Defaults to True (fail-safe).

    Unset or unrecognized values => True (suppress), so a forgotten env var can
    never accidentally start publishing unvalidated output.
    """
    raw = os.environ.get("DATA_ACCUMULATION_MODE")
    if raw is None:
        return True
    val = raw.strip().lower()
    if val in _FALSE:
        return False
    if val in _TRUE:
        return True
    return True  # unrecognized -> suppress
