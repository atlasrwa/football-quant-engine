"""Hypothesis lifecycle states and provenance (`hypothesis_lifecycle_v1`).

    The LLM proposes what to measure.
    The deterministic engine measures it.
    Statistical validation determines whether it generalizes.
    The quantitative model produces the probability.
    The market and prospective outcomes determine whether the resulting model adds value.

THE FEATURE-ADMISSION FIREWALL
------------------------------
A hypothesis is NEVER a model feature. It is a proposal that must survive an ordered
funnel, each stage of which can only be entered from the one before it. There is no edge
from any LLM output directly to a model feature, and none is provided by this module --
the terminal state `PROSPECTIVELY_SUPPORTED` is explicitly NOT "promoted"; promotion is a
separate human decision recorded outside this state machine.

The forbidden shortcut this replaces:

    LLM says context matters  ->  probability adjustment

is unrepresentable here: no state maps to a probability, and `advance()` refuses any
transition that is not an edge of the declared graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Optional
import hashlib
import json
import time

LIFECYCLE_VERSION = "hypothesis_lifecycle_v1"


# --------------------------------------------------------------------------------------
# Progress states (mandate §19)
# --------------------------------------------------------------------------------------
LLM_PROPOSED = "LLM_PROPOSED"
QUERY_VALID = "QUERY_VALID"
DATA_SUFFICIENT = "DATA_SUFFICIENT"
HISTORICAL_RESULT = "HISTORICAL_RESULT"
CONFOUNDER_REVIEW = "CONFOUNDER_REVIEW"
WALK_FORWARD_CANDIDATE = "WALK_FORWARD_CANDIDATE"
OOS_SUPPORTED = "OOS_SUPPORTED"
PROSPECTIVE_CANDIDATE = "PROSPECTIVE_CANDIDATE"
PROSPECTIVELY_SUPPORTED = "PROSPECTIVELY_SUPPORTED"

PROGRESS_STATES = (
    LLM_PROPOSED,
    QUERY_VALID,
    DATA_SUFFICIENT,
    HISTORICAL_RESULT,
    CONFOUNDER_REVIEW,
    WALK_FORWARD_CANDIDATE,
    OOS_SUPPORTED,
    PROSPECTIVE_CANDIDATE,
    PROSPECTIVELY_SUPPORTED,
)


# --------------------------------------------------------------------------------------
# Terminal failure states. Each names EXACTLY why the hypothesis stopped, so a research
# record never has to be reconstructed from a generic rejection.
# --------------------------------------------------------------------------------------
SCHEMA_INVALID = "SCHEMA_INVALID"
NUMERICAL_AUTHORITY_VIOLATION = "NUMERICAL_AUTHORITY_VIOLATION"
LATENT_GRADING_VIOLATION = "LATENT_GRADING_VIOLATION"
QUERY_INVALID = "QUERY_INVALID"
UNSUPPORTED_METRIC = "UNSUPPORTED_METRIC"
UNSUPPORTED_DIMENSION = "UNSUPPORTED_DIMENSION"
UNSUPPORTED_CONTEXT_SOURCE = "UNSUPPORTED_CONTEXT_SOURCE"
UNSUPPORTED_GRANULARITY = "UNSUPPORTED_GRANULARITY"
INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
PROVIDER_SEMANTICS_CONFLICT = "PROVIDER_SEMANTICS_CONFLICT"
LEAKAGE_REJECTED = "LEAKAGE_REJECTED"
HISTORICALLY_UNSUPPORTED = "HISTORICALLY_UNSUPPORTED"
OOS_FAILED = "OOS_FAILED"
PROSPECTIVELY_FAILED = "PROSPECTIVELY_FAILED"

FAILURE_STATES = (
    SCHEMA_INVALID,
    NUMERICAL_AUTHORITY_VIOLATION,
    LATENT_GRADING_VIOLATION,
    QUERY_INVALID,
    UNSUPPORTED_METRIC,
    UNSUPPORTED_DIMENSION,
    UNSUPPORTED_CONTEXT_SOURCE,
    UNSUPPORTED_GRANULARITY,
    INSUFFICIENT_EVIDENCE,
    INSUFFICIENT_DATA,
    PROVIDER_SEMANTICS_CONFLICT,
    LEAKAGE_REJECTED,
    HISTORICALLY_UNSUPPORTED,
    OOS_FAILED,
    PROSPECTIVELY_FAILED,
)

ALL_STATES = PROGRESS_STATES + FAILURE_STATES


#: Which failures may terminate which stage. A failure raised out of the wrong stage is a
#: bug in the caller, not a research finding, so `advance()` rejects it.
_ALLOWED_FAILURES: dict[str, frozenset[str]] = {
    LLM_PROPOSED: frozenset({
        SCHEMA_INVALID, NUMERICAL_AUTHORITY_VIOLATION, LATENT_GRADING_VIOLATION,
        INSUFFICIENT_EVIDENCE, LEAKAGE_REJECTED, QUERY_INVALID,
        UNSUPPORTED_METRIC, UNSUPPORTED_DIMENSION, UNSUPPORTED_CONTEXT_SOURCE,
        UNSUPPORTED_GRANULARITY, PROVIDER_SEMANTICS_CONFLICT,
    }),
    QUERY_VALID: frozenset({INSUFFICIENT_DATA, LEAKAGE_REJECTED}),
    DATA_SUFFICIENT: frozenset({INSUFFICIENT_DATA, LEAKAGE_REJECTED}),
    HISTORICAL_RESULT: frozenset({HISTORICALLY_UNSUPPORTED}),
    CONFOUNDER_REVIEW: frozenset({HISTORICALLY_UNSUPPORTED}),
    WALK_FORWARD_CANDIDATE: frozenset({OOS_FAILED}),
    OOS_SUPPORTED: frozenset({OOS_FAILED}),
    PROSPECTIVE_CANDIDATE: frozenset({PROSPECTIVELY_FAILED}),
}

#: The ONLY legal forward edges.
_NEXT: dict[str, str] = {
    LLM_PROPOSED: QUERY_VALID,
    QUERY_VALID: DATA_SUFFICIENT,
    DATA_SUFFICIENT: HISTORICAL_RESULT,
    HISTORICAL_RESULT: CONFOUNDER_REVIEW,
    CONFOUNDER_REVIEW: WALK_FORWARD_CANDIDATE,
    WALK_FORWARD_CANDIDATE: OOS_SUPPORTED,
    OOS_SUPPORTED: PROSPECTIVE_CANDIDATE,
    PROSPECTIVE_CANDIDATE: PROSPECTIVELY_SUPPORTED,
}


class LifecycleError(RuntimeError):
    """An illegal state transition was attempted."""


def is_terminal(state: str) -> bool:
    return state in FAILURE_STATES or state == PROSPECTIVELY_SUPPORTED


def next_state(state: str) -> Optional[str]:
    return _NEXT.get(state)


def advance(current: str, to: str) -> str:
    """Return ``to`` if the transition is legal, else raise.

    Legal transitions are exactly: the single declared forward edge, or a failure state
    allowed at the current stage. Skipping stages is refused -- that is what makes
    "LLM output -> model feature" unrepresentable rather than merely discouraged.
    """
    if current not in ALL_STATES:
        raise LifecycleError(f"unknown current state {current!r}")
    if to not in ALL_STATES:
        raise LifecycleError(f"unknown target state {to!r}")
    if is_terminal(current):
        raise LifecycleError(f"{current} is terminal; no transition out of it")
    if to == _NEXT.get(current):
        return to
    if to in _ALLOWED_FAILURES.get(current, frozenset()):
        return to
    raise LifecycleError(
        f"illegal transition {current} -> {to}. Legal: forward={_NEXT.get(current)!r}, "
        f"failures={sorted(_ALLOWED_FAILURES.get(current, ()))}"
    )


# --------------------------------------------------------------------------------------
# Append-only provenance record (mandate §29)
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class LifecycleEvent:
    state: str
    at_unix: float
    detail: Optional[str] = None
    #: sha256 of the artifact produced at this stage, when one was produced
    artifact_hash: Optional[str] = None


@dataclass
class HypothesisProvenance:
    """Immutable-by-convention trace: fixture -> packet -> model -> prompt -> hypothesis
    -> normalized -> compiled plan -> historical -> OOS -> prospective.

    Earlier stages are never mutated; `record()` only appends.
    """

    hypothesis_id: str
    fixture_id: str
    evidence_packet_hash: str
    model_id: str
    prompt_version: str
    schema_version: str
    vocabulary_version: str
    capability_inventory_version: str
    generation_id: str
    raw_hypothesis_hash: Optional[str] = None
    normalized_intent_hash: Optional[str] = None
    query_plan_hash: Optional[str] = None
    historical_result_hash: Optional[str] = None
    oos_result_hash: Optional[str] = None
    prospective_result_hash: Optional[str] = None
    state: str = LLM_PROPOSED
    events: list[LifecycleEvent] = field(default_factory=list)

    def __post_init__(self):
        if not self.events:
            self.events.append(LifecycleEvent(self.state, time.time(), "created"))

    def record(self, to: str, detail: str | None = None,
               artifact_hash: str | None = None) -> "HypothesisProvenance":
        """Append a validated transition. Raises LifecycleError on an illegal edge."""
        self.state = advance(self.state, to)
        self.events.append(LifecycleEvent(self.state, time.time(), detail, artifact_hash))
        return self

    def fail(self, failure: str, detail: str | None = None) -> "HypothesisProvenance":
        if failure not in FAILURE_STATES:
            raise LifecycleError(f"{failure!r} is not a failure state")
        return self.record(failure, detail)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["lifecycle_version"] = LIFECYCLE_VERSION
        return d


def stable_hash(obj) -> str:
    """Deterministic sha256 over a JSON-serializable object, used for every stage hash."""
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()
