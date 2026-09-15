"""V6 failure taxonomy (`v6_classes_v1`). Explicit enums, never inferred from prose (§8).

WHY THIS MODULE EXISTS
----------------------
V5A.2 halted on a rule named `V5A2_STOP_MODEL_SCHEMA_INVALID_RATE` fired by two events
that were not schema invalidity at all. `validator_v4.validate` stamps
`failure_class = MODEL_SCHEMA_INVALID` on a firewall rejection:

    if numeric:
        return ValidationResultV4(False, lifecycle.NUMERICAL_AUTHORITY_VIOLATION, ...,
                                  failure_class=MODEL_SCHEMA_INVALID)

Both classes describe model behaviour, so the halt was attributable either way and no
conclusion changed -- but the run's own report had to carry a paragraph explaining that the
field does not mean what its name says. A category that has to be corrected in prose is not
a category. §8 forbids it.

Here every outcome is a declared constant, each one is produced by exactly one gate, and
`classify_stop` keys on specific members rather than on a single catch-all. Nothing in the
evaluator reads a reason string to decide what happened.

TWO LEVELS, AND THE BOUNDARY BETWEEN THEM (§3)
----------------------------------------------
RESPONSE_FATAL is reserved for structures from which individual hypotheses cannot be
recovered RELIABLY. That is a statement about recoverability, not about severity: a
response carrying eleven good hypotheses and one probability claim is perfectly
recoverable, so it is not fatal, however badly the twelfth behaved.

    RESPONSE_PARSE_FATAL      the outer payload is not an object, `hypotheses` is missing
                              or is not an array, or an element is not an object.
    everything else           adjudicated per hypothesis; siblings are unaffected.

`INFRASTRUCTURE_FAILURE` is OURS. It is never a measurement of the model and it has its
own stop rule, because the correct response to our own defect is to halt, not to average
it into a model failure rate.

ZERO SPEND. This module declares strings.
"""
from __future__ import annotations

CLASSES_VERSION = "v6_classes_v1"

# ----------------------------------------------------------------------------------------
# RESPONSE-LEVEL outcomes. Exactly one is assigned to every attempted call.
# ----------------------------------------------------------------------------------------
#: The outer structure cannot be decomposed into hypotheses. The ONLY fatal class.
RESPONSE_PARSE_FATAL = "RESPONSE_PARSE_FATAL"
#: The response was decomposed and every hypothesis was adjudicated on its own merits.
#: Says NOTHING about how many of them were any good.
VALID_MODEL_RESPONSE = "VALID_MODEL_RESPONSE"
#: The call never produced a payload (transport, credentials, throttling, our own driver).
INFRASTRUCTURE_FAILURE = "INFRASTRUCTURE_FAILURE"

RESPONSE_CLASSES = (RESPONSE_PARSE_FATAL, VALID_MODEL_RESPONSE, INFRASTRUCTURE_FAILURE)

#: Only these two response classes are RESPONSE_FATAL. A response that is fatal yields no
#: measurable hypotheses; a response that is not fatal yields a verdict for every element.
RESPONSE_FATAL_CLASSES = (RESPONSE_PARSE_FATAL, INFRASTRUCTURE_FAILURE)

# ----------------------------------------------------------------------------------------
# HYPOTHESIS-LEVEL outcomes. Exactly one is assigned to every recovered hypothesis.
# ----------------------------------------------------------------------------------------
#: Passed every gate and asserted SUFFICIENT. Candidate for QUALIFIED (§10), which is a
#: strictly stronger property evaluated separately -- acceptance is necessary, not enough.
VALID_HYPOTHESIS = "VALID_HYPOTHESIS"
#: Passed every gate and declared INSUFFICIENT_EVIDENCE. A CORRECT outcome (§17), counted
#: on its own axis and never as a failure.
VALID_ABSTENTION = "VALID_ABSTENTION"

#: The hypothesis object violates the frozen item schema (enum, type, bound, unknown key).
MODEL_SCHEMA_INVALID = "MODEL_SCHEMA_INVALID"
#: The hypothesis carries a field the numerical-authority contract forbids by NAME
#: (`probability`, `effect_size`, `edge`, ...). §5. Assigned BEFORE the schema gate so a
#: model claiming numerical authority is never recorded as a generic malformed object.
MODEL_NUMERIC_CONTRACT_VIOLATION = "MODEL_NUMERIC_CONTRACT_VIOLATION"
#: Model-authored predictive quantification in prose, or an evidence value written into a
#: field whose contract does not permit one. §4.
MODEL_FIREWALL_VIOLATION = "MODEL_FIREWALL_VIOLATION"
#: Cites an evidence id the packet does not contain, or asserts SUFFICIENT with no
#: citation at all.
MODEL_GROUNDING_VIOLATION = "MODEL_GROUNDING_VIOLATION"
#: Conditions on, or declares it requires, evidence this packet declares unexposed.
MODEL_AVAILABILITY_VIOLATION = "MODEL_AVAILABILITY_VIOLATION"
#: The comparator is absent, unsupported, or absorbed by the hypothesis's own conditions
#: so that the two sides of the comparison name the same cohort. §15.
MODEL_COMPARATOR_INVALID = "MODEL_COMPARATOR_INVALID"
#: A condition that does not restrict anything (`ANY`), or a self-contradictory condition
#: set. The cohort is not a cohort.
MODEL_DEGENERATE_HYPOTHESIS = "MODEL_DEGENERATE_HYPOTHESIS"
#: Identical measurable intent to an EARLIER hypothesis in the same response. The first
#: occurrence is kept; only the repeat is rejected.
MODEL_REDUNDANT_HYPOTHESIS = "MODEL_REDUNDANT_HYPOTHESIS"
#: Survived every contract gate and still did not compile to an executable query plan.
MODEL_COMPILER_INVALID = "MODEL_COMPILER_INVALID"

HYPOTHESIS_CLASSES = (
    VALID_HYPOTHESIS,
    VALID_ABSTENTION,
    MODEL_NUMERIC_CONTRACT_VIOLATION,
    MODEL_SCHEMA_INVALID,
    MODEL_GROUNDING_VIOLATION,
    MODEL_AVAILABILITY_VIOLATION,
    MODEL_FIREWALL_VIOLATION,
    MODEL_COMPARATOR_INVALID,
    MODEL_DEGENERATE_HYPOTHESIS,
    MODEL_REDUNDANT_HYPOTHESIS,
    MODEL_COMPILER_INVALID,
    INFRASTRUCTURE_FAILURE,
)

#: Hypothesis outcomes that are NOT model failures. Everything else is.
HYPOTHESIS_OK_CLASSES = (VALID_HYPOTHESIS, VALID_ABSTENTION)

#: Model-attributable hypothesis failures. `INFRASTRUCTURE_FAILURE` is excluded on
#: purpose: our defect must never enter a model failure rate.
HYPOTHESIS_MODEL_FAILURE_CLASSES = tuple(
    c for c in HYPOTHESIS_CLASSES
    if c not in HYPOTHESIS_OK_CLASSES and c != INFRASTRUCTURE_FAILURE)

# ----------------------------------------------------------------------------------------
# Gate order. THE class of a rejected hypothesis is the FIRST gate it failed, and every
# other gate is still evaluated and still recorded (§19) so a later reader never has to
# re-derive why something was rejected from a single collapsed label.
# ----------------------------------------------------------------------------------------
GATE_ORDER = (
    ("numeric_contract_valid", MODEL_NUMERIC_CONTRACT_VIOLATION),
    ("schema_valid", MODEL_SCHEMA_INVALID),
    ("evidence_grounded", MODEL_GROUNDING_VIOLATION),
    ("availability_valid", MODEL_AVAILABILITY_VIOLATION),
    ("firewall_valid", MODEL_FIREWALL_VIOLATION),
    ("comparator_valid", MODEL_COMPARATOR_INVALID),
    ("nondegenerate", MODEL_DEGENERATE_HYPOTHESIS),
    ("nonredundant", MODEL_REDUNDANT_HYPOTHESIS),
    ("compiler_valid", MODEL_COMPILER_INVALID),
)

#: Boolean scorecard keys in `GATE_ORDER`, for tests that assert the two never drift.
GATE_KEYS = tuple(k for k, _ in GATE_ORDER)


def first_failed_gate(scorecard: dict):
    """(gate_key, class) of the first FALSE gate in frozen order, or None if all passed.

    `None` for a gate means NOT EVALUATED (the schema failed, so the field could not be
    read) and is never treated as a pass -- a gate that could not run is skipped here and
    reported as unmeasured in the scorecard, so a `False` and a `None` can never be
    confused downstream.
    """
    for key, cls in GATE_ORDER:
        if scorecard.get(key) is False:
            return key, cls
    return None


def version_stamp() -> dict:
    return {"classes_version": CLASSES_VERSION,
            "response_classes": list(RESPONSE_CLASSES),
            "response_fatal_classes": list(RESPONSE_FATAL_CLASSES),
            "hypothesis_classes": list(HYPOTHESIS_CLASSES),
            "hypothesis_ok_classes": list(HYPOTHESIS_OK_CLASSES),
            "hypothesis_model_failure_classes": list(HYPOTHESIS_MODEL_FAILURE_CLASSES),
            "gate_order": [list(g) for g in GATE_ORDER]}
