"""The numerical-authority FIELD contract (`v6_numeric_contract_v1`). §5.

    The model names WHAT to measure. Every magnitude is the deterministic engine's.

`firewall.FORBIDDEN_FIELD_NAMES` already bans `probability`, `edge`, `ev`, `odds` and
their relatives. It does NOT contain `effect_size`, `expected_delta`, `confidence_score`
or `advantage_score` -- the four §5 names it misses. Under a closed schema all four are
rejected anyway, but as `additionalProperties` errors, which is to say as
MODEL_SCHEMA_INVALID. §8 forbids that conflation: a model that writes

    {"hypothesis_id": "H4", ..., "effect_size": 0.31}

has not malformed an object, it has claimed numerical authority, and the two must be
counted apart. This module is the gate that makes the distinction, and it runs BEFORE the
schema gate so the stronger, more specific class wins.

WHAT IS ALLOWED TO CARRY A NUMBER, AND WHAT IS NOT
--------------------------------------------------
Allowed, per hypothesis:

    evidence_refs[]     strings. An id is how the model points at a number without
                        authoring one -- the whole mechanism §16 asks to preserve.
    evidence_summary    bounded prose. A value the PACKET supplied may be reproduced here
                        under the frame contract in `v6_firewall`. Nothing else.

NOT allowed, and deliberately so: a model-authored `sample_n`.

§5 permits one "if deterministic", and it is not. The engine computes N when it builds the
cohort; a model-written N is either a copy (in which case `evidence_summary` already
carries it, under a frame rule that checks it against the packet's real sample counts) or
an invention (in which case we would have created a fabrication surface and then owed
ourselves a verifier for it). There is no third case in which the field buys anything, so
it does not exist. Recorded here rather than left silent, because a reader checking §5
against the schema needs to find the decision, not its absence.

ZERO SPEND.
"""
from __future__ import annotations

from src.research.hypothesis_engine import firewall

NUMERIC_CONTRACT_VERSION = "v6_numeric_contract_v1"

#: The four §5 names `firewall.FORBIDDEN_FIELD_NAMES` does not carry, plus the obvious
#: spellings of each. Additive only: the frozen set is reused, never edited.
V6_ADDITIONAL_FORBIDDEN_FIELD_NAMES = frozenset({
    "effect_size", "effect_sizes", "effectsize",
    "expected_delta", "expected_deltas", "expected_change", "expected_effect",
    "expected_difference", "delta", "deltas", "difference", "magnitude",
    "confidence_score", "confidence", "confidence_level", "certainty",
    "advantage_score", "advantage_scores", "matchup_score", "latent_advantage",
    "uplift", "lift", "coefficient", "weight", "weights", "importance",
    "estimate", "estimated_effect", "predicted_value", "p_value", "pvalue",
    "significance", "z_score", "t_stat", "correlation", "beta",
})

#: The full V6 ban. `firewall.FORBIDDEN_FIELD_NAMES` is the frozen base and is NOT edited.
FORBIDDEN_FIELD_NAMES = frozenset(firewall.FORBIDDEN_FIELD_NAMES) \
    | V6_ADDITIONAL_FORBIDDEN_FIELD_NAMES

#: Leaf names inside a hypothesis whose collision with a forbidden concept name is a
#: false positive. `conditions[].value` is the cohort BAND ("HIGH" on a profile axis), not
#: "value" in the betting sense. Carried over verbatim from `firewall._FIELD_NAME_EXEMPT_PATHS`
#: with the `$.hypotheses` prefix stripped, because this gate scans ONE hypothesis object.
EXEMPT_LEAF_PATHS = frozenset({"$.conditions.value"})

#: Fields inside a hypothesis whose STRING content may reproduce a packet-supplied value,
#: subject to the frame contract in `v6_firewall`. Nothing may carry a raw number.
EVIDENCE_BEARING_PROSE_FIELDS = ("evidence_summary",)

#: The free-text field that states the research question. A number here is discouraged by
#: the prompt and rejected by the firewall at HYPOTHESIS level -- never response level.
QUESTION_PROSE_FIELDS = ("question",)

PROSE_FIELDS = QUESTION_PROSE_FIELDS + EVIDENCE_BEARING_PROSE_FIELDS

#: No field of a hypothesis may carry a bare numeric literal. The envelope's provenance
#: timestamps are the engine's and live outside the hypothesis object entirely.
NUMERIC_ALLOWED_LEAVES = frozenset()


def _depath(path: str) -> str:
    import re
    return re.sub(r"\[\d+\]", "", path)


def scan_hypothesis(h) -> list:
    """Numerical-authority field violations in ONE hypothesis object.

    Returns a list of dicts; empty means the hypothesis claims no numerical authority
    through a field. Runs on the RAW object, before schema validation, so a forbidden name
    is reported as what it is rather than as an unknown property.
    """
    out: list = []
    if not isinstance(h, dict):
        return out
    nodes: list = []
    firewall._walk(h, "$", nodes)
    for path, key, value in nodes:
        if key is not None and key.lower() in FORBIDDEN_FIELD_NAMES \
                and _depath(path) not in EXEMPT_LEAF_PATHS:
            out.append({
                "path": path, "field": key, "kind": "forbidden_numeric_authority_field",
                "detail": f"field {key!r} names a quantity the deterministic engine owns. "
                          f"The model proposes what to measure and never supplies a "
                          f"magnitude, a probability, a confidence or an advantage."})
            continue
        if isinstance(value, bool):
            continue
        if isinstance(value, (int, float)):
            leaf = _depath(path)
            if leaf not in NUMERIC_ALLOWED_LEAVES:
                out.append({
                    "path": path, "field": key, "kind": "numeric_value_in_hypothesis",
                    "detail": f"numeric {value!r} at {path}: no field of a hypothesis may "
                              f"carry a number. Cite the evidence id instead."})
    return out


def contract_snapshot() -> dict:
    """Machine-readable contract, embedded in the prompt, the packet audit and the freeze."""
    return {
        "numeric_contract_version": NUMERIC_CONTRACT_VERSION,
        "numeric_allowed_hypothesis_fields": sorted(NUMERIC_ALLOWED_LEAVES),
        "evidence_bearing_prose_fields": list(EVIDENCE_BEARING_PROSE_FIELDS),
        "question_prose_fields": list(QUESTION_PROSE_FIELDS),
        "forbidden_field_names": sorted(FORBIDDEN_FIELD_NAMES),
        "v6_additional_forbidden_field_names": sorted(V6_ADDITIONAL_FORBIDDEN_FIELD_NAMES),
        "frozen_base_forbidden_field_names": sorted(firewall.FORBIDDEN_FIELD_NAMES),
        "sample_n_decision": (
            "NOT provided as a model-authored field. The engine computes N when it builds "
            "the cohort; a model-written N would be either a copy of a packet value "
            "(already expressible in evidence_summary, where the frame contract checks it "
            "against the packet's real sample counts) or an invention. §5 permits one "
            "only 'if deterministic', and a model-authored count is not."),
        "rule": ("A hypothesis may reference numbers only by evidence id, or reproduce a "
                 "packet-supplied value in evidence_summary under the frame contract. It "
                 "may never author one."),
    }


def version_stamp() -> dict:
    return {"numeric_contract_version": NUMERIC_CONTRACT_VERSION,
            "n_forbidden_field_names": len(FORBIDDEN_FIELD_NAMES),
            "n_added_over_frozen_firewall": len(V6_ADDITIONAL_FORBIDDEN_FIELD_NAMES
                                                - frozenset(firewall.FORBIDDEN_FIELD_NAMES))}
