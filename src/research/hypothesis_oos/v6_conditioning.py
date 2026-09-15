"""Conditioning quality and multi-condition classification (`v6_conditioning_v1`). §11, §12.

    "Arm B gets no credit merely for having more available dimensions. It only gets credit
     for correct use." (§18)
    "Do not reward gratuitous complexity." (§11)
    "V6 should observe, not force. Do NOT require a quota." (§12)

So nothing in this module is a gate. Every function here CLASSIFIES; none of them rejects a
hypothesis. Rejection belongs to the contract gates -- availability, comparator, degeneracy
-- and a hypothesis that is merely SHALLOW is not a hypothesis that is WRONG. A good single
-condition question may be better than a fake interaction, and the only way to find that out
is to count both honestly rather than to score one of them out of existence.

WHAT §11 ASKS TO BE CHECKED, AND WHERE EACH CHECK ACTUALLY LIVES
-----------------------------------------------------------------
    evidence actually exposed                 `v5a2_admissibility` (a REJECTION gate)
    evidence references support the condition  here -- `condition_support`
    condition does not duplicate baseline      `v6_baseline` (a REJECTION gate)
    condition materially changes the cohort    here -- `contrast_class`
    deterministic compiler can execute it      `query_plan` (a REJECTION gate)

Only the two middle ones are judgements about QUALITY rather than legality, and only those
two are made here.

THE MULTI-CONDITION CLASSES (§12), EACH WITH A DETERMINISTIC TEST
------------------------------------------------------------------
    MEANINGFUL_INTERACTION   >= 2 distinct dimensions, none degenerate, each supported by
                             a cited valid reference, and the cohort is genuinely narrowed
    REDUNDANT                two conditions on the SAME dimension, or a condition whose
                             restriction the other already implies
    CONTRADICTORY            two conditions on the same dimension with different values --
                             an empty cohort, which no measurement can rescue
    LOW_CONTRAST             a condition whose value is `ANY`, which restricts nothing
    BASELINE_ABSORBED        the comparator removes the restriction (`v6_baseline`)
    UNRESOLVABLE             a dimension this packet does not expose, so no cohort exists
    SINGLE_CONDITION         exactly one condition. Not a failure and not a lesser class.
    UNCONDITIONED            no conditions at all. The base arm's only shape.

ZERO SPEND.
"""
from __future__ import annotations

from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_ontology as O
from src.research.hypothesis_oos import v6_baseline as BL

CONDITIONING_VERSION = "v6_conditioning_v1"

UNCONDITIONED = "UNCONDITIONED"
SINGLE_CONDITION = "SINGLE_CONDITION"
MEANINGFUL_INTERACTION = "MEANINGFUL_INTERACTION"
REDUNDANT = "REDUNDANT"
CONTRADICTORY = "CONTRADICTORY"
LOW_CONTRAST = "LOW_CONTRAST"
BASELINE_ABSORBED = "BASELINE_ABSORBED"
UNRESOLVABLE = "UNRESOLVABLE"

CONDITIONING_CLASSES = (UNCONDITIONED, SINGLE_CONDITION, MEANINGFUL_INTERACTION,
                        REDUNDANT, CONTRADICTORY, LOW_CONTRAST, BASELINE_ABSORBED,
                        UNRESOLVABLE)

#: §11's named dimensions of conditioning quality, each keyed to the ontology term or the
#: response field that expresses it. Evaluated SEPARATELY, per §11, and never summed into
#: one "richness" number -- a single score would let volume stand in for correctness, which
#: is the substitution §10 and §18 both forbid.
USE_DIMENSIONS = {
    "opponent_profile_use": "opponent_profile",
    "venue_use": O.HISTORICAL_VENUE_CONDITIONING,
    "recent_vs_long_use": "recent_window_summaries",
    "formation_use": "formation_recorded_history",
    "competition_use": "competition",
}

#: Which evidence-id prefixes or infixes can SUPPORT a use of each dimension. A use whose
#: citations contain none of these is unsupported: the model named a dimension without
#: pointing at any evidence of it (§11, "evidence references support the condition").
_SUPPORTING_REF_TESTS = {
    "opponent_profile": lambda r: r.startswith("PROFILE:"),
    O.HISTORICAL_VENUE_CONDITIONING: lambda r: ":HOME_ONLY:" in r or ":AWAY_ONLY:" in r,
    "recent_window_summaries": lambda r: ":W5:" in r or ":W10:" in r,
    "own_formation_family": lambda r: r.startswith("FORMATION:") or r.startswith("MATCH:"),
    "opponent_formation_family": lambda r: (r.startswith("FORMATION:")
                                            or r.startswith("MATCH:")),
    "formation_recorded_history": lambda r: (r.startswith("FORMATION:")
                                             or r.startswith("MATCH:")),
    # Competition is a LABEL on each match row, never an aggregate, so only a match-level
    # citation can evidence it. `v5a2_packet` makes exactly that point when it declares the
    # term unexposed for a summary-only packet.
    "competition": lambda r: r.startswith("MATCH:"),
}


def _conditions(h) -> list:
    c = h.get("conditions")
    return [x for x in c if isinstance(x, dict)] if isinstance(c, list) else []


def valid_refs(h, valid_ids) -> list:
    return [r for r in (h.get("evidence_refs") or []) if r in valid_ids]


def condition_support(h, valid_ids) -> dict:
    """term -> whether the citations contain evidence OF that term. §11.

    A term with no declared test (`competition` aside, the non-conditionable evidence
    terms) is reported as `None` -- unmeasured, never silently `True`. §19 and §20 both
    turn on never letting "not measured" read as a value.
    """
    good = valid_refs(h, valid_ids)
    out = {}
    for c in _conditions(h):
        dim = c.get("dimension")
        test = _SUPPORTING_REF_TESTS.get(dim)
        out[dim] = None if test is None else any(test(r) for r in good)
    return out


def dimension_uses(h, packet, valid_ids) -> dict:
    """§11's five conditioning dimensions, each as (used, supported, exposed).

    `used` is read off the hypothesis's own fields, never off its prose: a window of W5 IS
    a use of recent-window evidence whether or not the question says so.
    """
    states = ADM.exposure_states(packet) if packet else {}
    conds = _conditions(h)
    dims = {c.get("dimension") for c in conds}
    good = valid_refs(h, valid_ids)
    comp, window = h.get("comparison"), h.get("window")

    used = {
        "opponent_profile_use": "opponent_profile" in dims,
        "venue_use": (O.HISTORICAL_VENUE_CONDITIONING in dims
                      or comp == "SUBJECT_VENUE_BASELINE"),
        "recent_vs_long_use": (window in ("W5", "W10")
                               or comp == "SUBJECT_RECENT_VS_LONG_BASELINE"),
        "formation_use": any(str(d or "").endswith("formation_family") for d in dims),
        "competition_use": "competition" in dims,
    }
    out = {}
    for name, term in USE_DIMENSIONS.items():
        test = _SUPPORTING_REF_TESTS.get(term)
        out[name] = {
            "used": used[name],
            "exposed": states.get(term) in (ADM._EXPOSED_STATES),
            "supported_by_refs": (None if test is None
                                  else (any(test(r) for r in good) if used[name] else None)),
        }
    return out


def contrast_class(h, packet) -> str:
    """Does the condition set MATERIALLY change the cohort? §11.

    Deliberately structural rather than statistical: a cohort-size estimate would need the
    measurement layer, and V6 stops before measurement. A condition restricts materially
    when it names a proper subset -- which for these closed enums means "a value other than
    ANY on a dimension the packet exposes".
    """
    conds = _conditions(h)
    if not conds:
        return UNCONDITIONED
    if any(str(c.get("value")) == "ANY" for c in conds):
        return LOW_CONTRAST
    # The cohort slot a condition occupies is (dimension, axis), not dimension alone.
    # `opponent_profile` REQUIRES an axis (`v5a2_ontology.axis_required_terms`), and two
    # bands on two DIFFERENT axes -- HIGH shots_for and LOW corners_against -- are a
    # legitimate two-axis interaction, not a contradiction. Keying on dimension alone would
    # have called the most substantive interaction the research arm can express an empty
    # cohort.
    slots = [(c.get("dimension"), c.get("axis")) for c in conds]
    if len(set(slots)) != len(slots):
        vals = {}
        for c, slot in zip(conds, slots):
            vals.setdefault(slot, set()).add(str(c.get("value")))
        if any(len(v) > 1 for v in vals.values()):
            return CONTRADICTORY
        return REDUNDANT
    return SINGLE_CONDITION if len(conds) == 1 else MEANINGFUL_INTERACTION


def classify(h, packet, valid_ids) -> dict:
    """The conditioning scorecard for one hypothesis. Classification only; never a verdict.

    The class is decided in a frozen precedence: an UNRESOLVABLE or BASELINE_ABSORBED
    condition set is described as such even when it is also, say, a two-dimension set,
    because naming it MEANINGFUL_INTERACTION would credit the shape of something that
    cannot be measured at all.
    """
    conds = _conditions(h)
    support = condition_support(h, valid_ids)
    base = contrast_class(h, packet)

    if packet is not None and conds:
        states = ADM.exposure_states(packet)
        if any(states.get(c.get("dimension")) not in ADM._EXPOSED_STATES for c in conds):
            cls = UNRESOLVABLE
        elif BL.absorption(h)["absorbed"]:
            cls = BASELINE_ABSORBED
        else:
            cls = base
    elif BL.absorption(h)["absorbed"]:
        cls = BASELINE_ABSORBED
    else:
        cls = base

    # A multi-condition set only counts as a genuine interaction when EVERY condition is
    # backed by a citation of evidence for that dimension. §12: a good single-condition
    # hypothesis may be superior to a fake interaction, so an unsupported pair is demoted
    # rather than credited.
    if cls == MEANINGFUL_INTERACTION:
        if any(support.get(c.get("dimension")) is False for c in conds):
            cls = REDUNDANT

    return {
        "conditioning_class": cls,
        "n_conditions": len(conds),
        "dimensions": sorted(str(c.get("dimension")) for c in conds),
        "condition_support": {k: support[k] for k in sorted(support, key=str)},
        "all_conditions_supported": (
            None if not conds
            else all(support.get(c.get("dimension")) is not False for c in conds)),
        "is_interaction": len(conds) >= 2,
        "is_meaningful_interaction": cls == MEANINGFUL_INTERACTION,
        "dimension_uses": dimension_uses(h, packet, valid_ids),
    }


def version_stamp() -> dict:
    return {"conditioning_version": CONDITIONING_VERSION,
            "conditioning_classes": list(CONDITIONING_CLASSES),
            "use_dimensions": dict(sorted(USE_DIMENSIONS.items())),
            "is_a_gate": False,
            "quota_required": False}
