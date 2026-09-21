"""ITEM 6 Stage-1 execution-status taxonomy + one-attempt-per-fixture policy (B3).

`item6_execution_status_v1`. ZERO SPEND. Importing this module makes no network call.

SCIENTIFIC PRINCIPLE (the same discipline that protected V1/V2/V3)

    ONE FIXTURE -> AT MOST ONE PAID TREATMENT.

A durable attempt marker is written BEFORE any possible network transmission. If the
process dies after the marker but before a trustworthy receipt, the fixture's transmission
state is UNCERTAIN and the fixture is NOT retried: its treatment is simply unavailable.
`MAX_RETRIES_PER_FIXTURE = 0` is absolute.

CLOSED STATUS TAXONOMY
Every terminal per-fixture execution outcome maps to exactly one of these. There is no
"other" bucket; an unrecognised condition maps to UNKNOWN_EXECUTION_STATUS which FAILS
CLOSED (stops the active runner) rather than being silently treated as a transport or a
scientific failure.

RECEIVED-RESPONSE RULE
Once a trustworthy raw model response exists, the fixture HAS RECEIVED ITS TREATMENT. The
runner never retries because the response has < K mechanisms, duplicates, baseline-equivalent
or unmeasurable mechanisms, an abstention, or later fails formalization/looks low quality.
Those are Stage-1 scientific OBSERVATIONS, recorded, never retried.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Tuple

EXECUTION_STATUS_VERSION = "item6_execution_status_v1"

# Frozen retry / attempt caps (B3).
MAX_RETRIES_PER_FIXTURE = 0
MAX_PAID_TREATMENTS_PER_FIXTURE = 1
ABSOLUTE_MAX_PAID_CALLS = 120
ABSOLUTE_MAX_MODEL_ATTEMPTS = 120
MODEL_CALLS_PER_FIXTURE = 1

# ---- the closed status set -----------------------------------------------------------
TRANSPORT_OK = "TRANSPORT_OK"
MODEL_TRANSPORT_FAILURE = "MODEL_TRANSPORT_FAILURE"
MODEL_TIMEOUT = "MODEL_TIMEOUT"
MODEL_PROVIDER_ERROR = "MODEL_PROVIDER_ERROR"
UNCERTAIN_ATTEMPT_NOT_RETRIED = "UNCERTAIN_ATTEMPT_NOT_RETRIED"
CALL_BLOCKED_BY_CALL_CAP = "CALL_BLOCKED_BY_CALL_CAP"
CALL_BLOCKED_BY_SPEND_CAP = "CALL_BLOCKED_BY_SPEND_CAP"
RECEIPT_VERIFICATION_FAILED = "RECEIPT_VERIFICATION_FAILED"
REQUEST_INTEGRITY_FAILURE = "REQUEST_INTEGRITY_FAILURE"
UNKNOWN_EXECUTION_STATUS = "UNKNOWN_EXECUTION_STATUS"

# v2 execution amendment: authoritative pre-call provider token counting. When the
# CountTokens control operation cannot authoritatively count the exact inference request, the
# paid inference is BLOCKED BEFORE TRANSMISSION (no attempt consumed, no spend). These are
# distinct pre-call block statuses so a report can tell WHY the call never transmitted.
CALL_BLOCKED_BY_TOKEN_COUNT = "CALL_BLOCKED_BY_TOKEN_COUNT"

ALL_STATUSES: Tuple[str, ...] = (
    TRANSPORT_OK,
    MODEL_TRANSPORT_FAILURE,
    MODEL_TIMEOUT,
    MODEL_PROVIDER_ERROR,
    UNCERTAIN_ATTEMPT_NOT_RETRIED,
    CALL_BLOCKED_BY_CALL_CAP,
    CALL_BLOCKED_BY_SPEND_CAP,
    CALL_BLOCKED_BY_TOKEN_COUNT,
    RECEIPT_VERIFICATION_FAILED,
    REQUEST_INTEGRITY_FAILURE,
    UNKNOWN_EXECUTION_STATUS,
)

# A status is TERMINAL_TREATED when the fixture received its one treatment (a trustworthy
# response exists) -> never retried, contributes to Stage-1 evidence.
# A status is TERMINAL_UNAVAILABLE when no trustworthy response exists AND the fixture must
# not be retried (its one attempt is spent or its transmission state is uncertain).
# A status is BLOCKED_PRECALL when the call never transmitted (no attempt consumed): the
# runner stops but no paid treatment occurred.
# A status is FAIL_CLOSED when classification integrity is uncertain: STOP the runner.
TERMINAL_TREATED = frozenset({TRANSPORT_OK})
TERMINAL_UNAVAILABLE = frozenset({
    MODEL_TRANSPORT_FAILURE, MODEL_TIMEOUT, MODEL_PROVIDER_ERROR,
    UNCERTAIN_ATTEMPT_NOT_RETRIED, RECEIPT_VERIFICATION_FAILED,
})
BLOCKED_PRECALL = frozenset({CALL_BLOCKED_BY_CALL_CAP, CALL_BLOCKED_BY_SPEND_CAP,
                             CALL_BLOCKED_BY_TOKEN_COUNT})
FAIL_CLOSED = frozenset({REQUEST_INTEGRITY_FAILURE, UNKNOWN_EXECUTION_STATUS})

# No status ever permits a retry.
RETRYABLE: frozenset = frozenset()

# Abstention policy (schema already permits abstention).
ABSTENTION_IS_VALID_TREATMENT = True
ABSTENTION_TRIGGERS_RETRY = False


def is_retryable(status: str) -> bool:
    """Frozen answer: nothing is retryable. MAX_RETRIES_PER_FIXTURE == 0."""
    return status in RETRYABLE  # always False


def fail_closed(status: str) -> bool:
    """True if this status must STOP the active runner (integrity uncertain)."""
    return status in FAIL_CLOSED


def consumed_paid_attempt(status: str) -> bool:
    """True if reaching this status means the fixture's single paid attempt is spent.

    A trustworthy response (TRANSPORT_OK) obviously consumes it. So does any state where
    transmission MAY have reached the provider (transport failure / timeout / provider error
    after send / uncertain / receipt-verification-failed): under one-attempt semantics we
    conservatively treat these as having consumed the fixture's attempt and never retry.
    BLOCKED_PRECALL statuses did NOT transmit, so they do not consume an attempt.
    """
    return status in (TERMINAL_TREATED | TERMINAL_UNAVAILABLE)


def normalize(status: str) -> str:
    """Map any string to a known status; unknown -> UNKNOWN_EXECUTION_STATUS (fail closed)."""
    return status if status in ALL_STATUSES else UNKNOWN_EXECUTION_STATUS


@dataclass
class AttemptRecord:
    """One durable per-fixture attempt record. Written to the attempt ledger BEFORE any
    network transmission (marker), then updated with the terminal status after."""
    fixture_id: str
    request_sha256: str
    attempt_marker_written: bool          # True once the pre-transmission marker is durable
    transmitted: bool                     # True once transmission was actually initiated
    status: str                           # one of ALL_STATUSES (or UNKNOWN before terminal)
    receipt_present: bool
    seq: int                              # 1-based paid-call sequence index

    def to_dict(self) -> Dict[str, object]:
        return {
            "fixture_id": self.fixture_id,
            "request_sha256": self.request_sha256,
            "attempt_marker_written": self.attempt_marker_written,
            "transmitted": self.transmitted,
            "status": self.status,
            "receipt_present": self.receipt_present,
            "seq": self.seq,
            "execution_status_version": EXECUTION_STATUS_VERSION,
        }


def classify_marker_without_receipt(marker_written: bool, receipt_present: bool) -> str:
    """The crash-recovery rule: a durable attempt marker with no trustworthy receipt is
    UNCERTAIN_ATTEMPT_NOT_RETRIED. It is never automatically retried."""
    if marker_written and not receipt_present:
        return UNCERTAIN_ATTEMPT_NOT_RETRIED
    return UNKNOWN_EXECUTION_STATUS


def version_stamp() -> Dict[str, object]:
    return {
        "execution_status_version": EXECUTION_STATUS_VERSION,
        "max_retries_per_fixture": MAX_RETRIES_PER_FIXTURE,
        "max_paid_treatments_per_fixture": MAX_PAID_TREATMENTS_PER_FIXTURE,
        "absolute_max_paid_calls": ABSOLUTE_MAX_PAID_CALLS,
        "absolute_max_model_attempts": ABSOLUTE_MAX_MODEL_ATTEMPTS,
        "model_calls_per_fixture": MODEL_CALLS_PER_FIXTURE,
        "abstention_is_valid_treatment": ABSTENTION_IS_VALID_TREATMENT,
        "abstention_triggers_retry": ABSTENTION_TRIGGERS_RETRY,
        "statuses": list(ALL_STATUSES),
        "retryable_statuses": [],
        "unknown_status_fails_closed": True,
        "received_response_is_treatment": True,
        "token_count_failure_blocks_inference": True,
    }
