"""Validation status taxonomy. Fail closed; never collapse distinct causes into INVALID."""
from __future__ import annotations

VALID_MEASURABLE = "VALID_MEASURABLE"
UNSUPPORTED_METRIC = "UNSUPPORTED_METRIC"
UNSUPPORTED_PROVIDER_SEMANTICS = "UNSUPPORTED_PROVIDER_SEMANTICS"
AMBIGUOUS_PROPOSAL = "AMBIGUOUS_PROPOSAL"
FORBIDDEN_PREDICTION_FIELD = "FORBIDDEN_PREDICTION_FIELD"
PIT_VIOLATION = "PIT_VIOLATION"
INSUFFICIENT_SUPPORT = "INSUFFICIENT_SUPPORT"
MISSING_DATA = "MISSING_DATA"
COMPILER_REFUSED = "COMPILER_REFUSED"
MEASUREMENT_FAILED = "MEASUREMENT_FAILED"
PACKET_BINDING_FAILED = "PACKET_BINDING_FAILED"

#: `PACKET_BINDING_FAILED` is its own status rather than MISSING_DATA or AMBIGUOUS: the
#: proposal and the corpus may both be fine while the packet handed in does not bind to
#: them, and folding that into another cause would hide the only signal that a hypothesis
#: was measured against evidence it was not grounded in.
#:
#: `FORBIDDEN_PREDICTION_FIELD` is the other addition to the mandated taxonomy. It is genuinely
#: distinct from AMBIGUOUS_PROPOSAL: the proposal was perfectly well-formed, and was refused
#: because it tried to carry a prediction across the boundary. Collapsing the two would hide
#: the only failure mode that indicates the LLM is being used as a predictor.
ALL_STATUSES = frozenset({
    VALID_MEASURABLE, UNSUPPORTED_METRIC, UNSUPPORTED_PROVIDER_SEMANTICS,
    AMBIGUOUS_PROPOSAL, FORBIDDEN_PREDICTION_FIELD, PIT_VIOLATION, INSUFFICIENT_SUPPORT,
    MISSING_DATA, COMPILER_REFUSED, MEASUREMENT_FAILED, PACKET_BINDING_FAILED,
})

TERMINAL_REJECTIONS = ALL_STATUSES - {VALID_MEASURABLE}
