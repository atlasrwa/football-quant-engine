"""Publication policy — the single external signal-publication boundary.

Two INDEPENDENT conditions must BOTH hold before any prediction/signal output
may leave the research environment for a public audience:

1. DATA ACCUMULATION MODE must be OFF
   (``DATA_ACCUMULATION_MODE=0`` — the operational "we are no longer merely
   accumulating evidence" switch), AND
2. an explicit VALIDATED PUBLICATION AUTHORIZATION must be PROMOTED
   (``SIGNAL_PUBLICATION_STATE=PROMOTED`` — the research→validated-signal
   promotion boundary).

Either alone is insufficient. This makes a single accidental env change unable
to turn experimental output into public signals: flipping accumulation off
still leaves publication suppressed unless a separate, explicit promotion state
is set, and vice-versa.

Everything fails closed. Unset / malformed / unknown / empty values resolve to
the safe state (accumulation ON, publication RESEARCH_ONLY), so a forgotten or
corrupted variable can never open the boundary.

Design note — future promotion artifact
----------------------------------------
``SIGNAL_PUBLICATION_STATE`` is a TEMPORARY explicit control. The resolver is
written so the promotion decision can later be backed by a VERSIONED promotion
artifact (a signed/hashed record of who promoted what, when, and against which
evidence) without changing callers: :func:`resolve_publication_state` is the
single point that would consult that artifact. This PR does not invent that
artifact or any on-chain migration; it only centralizes the gate.
"""

from __future__ import annotations

import os
from enum import Enum

#: The reason string recorded when a message is withheld from publication.
SUPPRESSED_RESEARCH_ONLY = "SUPPRESSED_RESEARCH_ONLY"

#: How a research forecast is classified while publication is NOT promoted.
#: Recorded alongside the forecast so it is never mistaken for a validated
#: signal.
RESEARCH_FORECAST_CLASSIFICATION: tuple[str, ...] = (
    "RESEARCH_FORECAST",
    "NOT_PROMOTED",
    "NOT_ACTIONABLE",
)

_TRUE = {"1", "true", "on", "yes"}
_FALSE = {"0", "false", "off", "no"}


class PublicationState(str, Enum):
    """Explicit external-publication authorization states.

    ``RESEARCH_ONLY`` is the safe default for every unrecognized input.
    """

    RESEARCH_ONLY = "RESEARCH_ONLY"
    PROMOTED = "PROMOTED"


def is_data_accumulation_mode() -> bool:
    """Whether DATA ACCUMULATION MODE is ON (publication-suppressing).

    Defaults to True (fail-safe): unset or unrecognized => ON, so a forgotten
    env var can never accidentally start publishing unvalidated output.
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


def resolve_publication_state() -> PublicationState:
    """Resolve the explicit publication-authorization state (fail closed).

    Only the exact token ``PROMOTED`` (case-insensitive, trimmed) yields
    :attr:`PublicationState.PROMOTED`. Unset / empty / malformed / unknown =>
    :attr:`PublicationState.RESEARCH_ONLY`.

    This is the single seam a future versioned promotion artifact would plug
    into: callers ask the policy, not the environment.
    """
    raw = os.environ.get("SIGNAL_PUBLICATION_STATE")
    if raw is None:
        return PublicationState.RESEARCH_ONLY
    val = raw.strip().upper()
    if val == PublicationState.PROMOTED.value:
        return PublicationState.PROMOTED
    return PublicationState.RESEARCH_ONLY


def can_publish_validated_signals() -> bool:
    """Whether validated signals/predictions may be published externally.

    Requires BOTH independent conditions:
      * DATA ACCUMULATION MODE is OFF, AND
      * publication state is PROMOTED.

    Fails closed on anything else. This is the ONLY function the publication
    paths consult; there is no duplicated gate logic.

    Truth table:
        accumulation=ON,  state=RESEARCH_ONLY -> False (suppress)
        accumulation=ON,  state=PROMOTED      -> False (suppress)
        accumulation=OFF, state=RESEARCH_ONLY -> False (suppress)
        accumulation=OFF, state=PROMOTED      -> True  (allow)
    """
    accumulation_off = not is_data_accumulation_mode()
    promoted = resolve_publication_state() is PublicationState.PROMOTED
    return accumulation_off and promoted


def publication_suppressed() -> bool:
    """Convenience inverse of :func:`can_publish_validated_signals`."""
    return not can_publish_validated_signals()
