"""V3 control-perturbation layer (`hypothesis_controls_v3`). FROZEN, ZERO-SPEND.

Adds the two controls V3 needs and V2 did not have, and reuses `controls.py` verbatim for
the four V2 controls that carry over unchanged (identity_alias, irrelevant_field,
evidence_starvation, unsupported_data_trap).

Same invariants as `controls.py`, and they are load-bearing for preregistration:
  * pure, deterministic packet -> packet; no corpus, network, clock or random source;
  * the input packet is never mutated (deep-copy first);
  * evidence ids stay identity-neutral, so intent comparison is never confounded;
  * `packet_hash` is recomputed after every transform, so a transformed packet is
    self-consistent and its hash can be pinned in the manifest BEFORE inference;
  * no Bedrock import anywhere, so this file cannot make a paid call.

NEW CONTROL 1 -- profile_axis_perturbation
------------------------------------------
V2's `profile_perturbation` moved a DEFENSIVE wide-play surface (`corners_against`,
`accurate_crosses_against`). It answered "does intent move at all?" but could not answer
the question the V2 diagnosis left open: does the model's choice of opponent-profile AXIS
track the evidence, or is a profile condition boilerplate?

So V3 perturbs a disjoint, OFFENSIVE surface -- `shots_on_target_for` and `total_shots_for`
moved together, because a side that takes more shots also hits the target more often, which
keeps the perturbed profile football-coherent rather than an arbitrary single-field jolt.
`shots_on_target_for` is a resolvable `opponent_profile` axis, so a model whose axis
selection is evidence-driven has a legal axis to move TO.

Two directions are frozen so the six cases split deterministically into raise/lower halves.

NEW CONTROL 2 -- availability_ablation
--------------------------------------
Withdraws a CAPABILITY, leaving the evidence untouched. The expected behaviour is that
hypotheses conditioned on the withdrawn dimension disappear or abstain, while every other
question survives.

Its "with the dimension" arm is the UNTOUCHED FROZEN REFERENCE packet, which is what makes
this the scientifically clean form of the task's "context addition" control: the addition
direction is measured against real data that already exists, so nothing is fabricated and
no synthetic football effect is created. See `CONTEXT_ADDITION_REJECTION` below.
"""
from __future__ import annotations

import copy
from typing import Iterable, Optional

from . import context_packet as CP

CONTROLS_V3_VERSION = "hypothesis_controls_v3"


# ======================================================================================
# Frozen parameters.
# ======================================================================================

#: profile_axis_perturbation -- the OFFENSIVE surface, disjoint from V2's defensive one.
#: Both move together and in the same direction, so the perturbed side stays coherent.
#: `shots_on_target_for` is a RESOLVABLE opponent_profile axis; `total_shots_for` is
#: evidence-only (its axis spelling `shots_for` has no inventory metric), and is moved to
#: keep the shot profile internally consistent rather than to be selected.
PROFILE_AXIS_PERTURBATION_METRICS = ("shots_on_target_for", "total_shots_for")
PROFILE_AXIS_PERTURBATION_SUBJECT = "AWAY"      # perturb the away side's attacking output
PROFILE_AXIS_RAISE_FACTOR = 1.60
PROFILE_AXIS_LOWER_FACTOR = 0.55
#: Indices (within the control's own fixture list) that receive RAISE; the rest LOWER.
PROFILE_AXIS_RAISE_INDICES = (0, 1, 2)

#: The opponent_profile axis a model with evidence-driven AXIS SELECTION would move to.
#: Frozen here so the sensitivity classifier cannot be chosen after seeing results.
PROFILE_AXIS_TARGET_AXES = frozenset({"shots_on_target_for", "shots_on_target_against"})

#: The metric family the perturbation moves. Used by the (gated) surface-sensitivity rule.
PROFILE_AXIS_TARGET_METRICS = frozenset({
    "shots_on_target", "total_shots", "shots_inside_box", "shots_outside_box",
    "shots_off_target", "big_chances", "blocked_shots",
})

PROFILE_AXIS_NOTE = None    # no note is added; the control must be invisible as a label

#: availability_ablation -- which dimension is withdrawn. `opponent_profile` is chosen
#: because it is AVAILABLE in all 12 frozen fixtures, so the control is informative
#: everywhere. (Formation would be informative in only 3, which is why V3 measures
#: formation but does not control it -- see the preregistration.)
AVAILABILITY_ABLATION_DIMENSIONS = ("opponent_profile",)
AVAILABILITY_ABLATION_NOTE = (
    "opponent-profile cohort conditioning is deliberately unavailable for this fixture; "
    "questions requiring it should be dropped or marked INSUFFICIENT_EVIDENCE, while "
    "every other question remains answerable")

#: Why a synthetic "context addition" control is NOT built. Recorded so the decision is
#: part of the preregistration rather than an omission.
CONTEXT_ADDITION_REJECTION = {
    "decision": "REJECTED_AS_SYNTHETIC",
    "reasons": [
        "no packet builder over the raw corpus exists in the frozen chain: the reference "
        "packets come from frozen_packets_v1.json, so a second horizon (W5) or a "
        "venue-split evidence item would have to be DERIVED by new code",
        "such derived evidence could not be shown point-in-time safe without rebuilding "
        "and re-auditing the corpus pipeline, which is out of scope pre-spend",
        "fabricating evidence values would create a synthetic football effect, which the "
        "experiment design forbids",
    ],
    "clean_substitute": (
        "availability_ablation is run as a PAIRED contrast whose 'with the dimension' arm "
        "is the untouched frozen reference packet. The addition direction is therefore "
        "measured against real data and nothing is fabricated."),
}


# ======================================================================================
# Helpers
# ======================================================================================
def _rehash(packet: dict) -> dict:
    packet.pop("packet_hash", None)
    packet["packet_hash"] = CP.packet_hash(packet)
    return packet


def _subject_of(evidence_id: str) -> str:
    return evidence_id.split("_", 1)[0]


# ======================================================================================
# Controls
# ======================================================================================
def profile_axis_perturbation(packet: dict, *, raise_band: bool
                              ) -> tuple[dict, list[dict]]:
    """Scale the away side's OFFENSIVE shot profile on two coherent, linked metrics.

    raise_band=True  -> multiply by PROFILE_AXIS_RAISE_FACTOR (high-volume attacker)
    raise_band=False -> multiply by PROFILE_AXIS_LOWER_FACTOR (low-volume attacker)

    Returns (perturbed_packet, before/after changes). The changes are manifest provenance
    and are deliberately NOT written into the packet the model sees -- a note saying "this
    was perturbed" would be an instruction, not evidence.
    """
    p = copy.deepcopy(packet)
    factor = PROFILE_AXIS_RAISE_FACTOR if raise_band else PROFILE_AXIS_LOWER_FACTOR
    changed: list[dict] = []
    for e in p.get("evidence") or []:
        if (_subject_of(e["id"]) == PROFILE_AXIS_PERTURBATION_SUBJECT
                and e.get("metric") in PROFILE_AXIS_PERTURBATION_METRICS
                and e.get("value") is not None):
            before = e["value"]
            after = round(before * factor, 4)
            changed.append({"id": e["id"], "metric": e["metric"],
                            "before": before, "after": after, "factor": factor})
            e["value"] = after
    return _rehash(p), changed


def availability_ablation(packet: dict,
                          dimensions: Iterable[str] = AVAILABILITY_ABLATION_DIMENSIONS
                          ) -> dict:
    """Withdraw a cohort CAPABILITY. Evidence is left completely intact.

    Only the manifest changes, which is the point: the question is whether the model
    respects a stated capability boundary when the underlying numbers are still in front
    of it. Fabricating or removing evidence would test something else.
    """
    p = copy.deepcopy(packet)
    dims = tuple(dimensions)
    man = p.get("capability_manifest") or {}
    man["available_dimensions"] = [d for d in (man.get("available_dimensions") or [])
                                   if d not in dims]
    cov = dict(man.get("coverage") or {})
    for d in dims:
        cov.pop(d, None)
    man["coverage"] = cov
    p["capability_manifest"] = man
    notes = list(p.get("notes") or [])
    notes.append(AVAILABILITY_ABLATION_NOTE)
    p["notes"] = notes
    return _rehash(p)


# ======================================================================================
# Frozen sensitivity / disappearance classifiers.
#
# Frozen BEFORE inference so no rule can be chosen after seeing the responses.
# ======================================================================================
def intent_touches_perturbed_offensive_surface(intent: dict) -> bool:
    """Does this normalized intent touch the surface `profile_axis_perturbation` moved?

    Arbitrary hypothesis churn is explicitly NOT sensitivity: a response that changes
    randomly under a perturbation has not responded to the evidence. The intent must touch
    the shot surface, or name an opponent-profile axis in the perturbed family.
    """
    if intent.get("metric") in PROFILE_AXIS_TARGET_METRICS:
        return True
    for c in intent.get("conditions") or []:
        if (c.get("dimension") == "opponent_profile"
                and c.get("axis") in PROFILE_AXIS_TARGET_AXES):
            return True
    return False


def profile_axes_used(intents: Iterable[dict]) -> set:
    """Every opponent_profile axis named across a response's intents."""
    out = set()
    for i in intents:
        for c in i.get("conditions") or []:
            if c.get("dimension") == "opponent_profile" and c.get("axis"):
                out.add(c["axis"])
    return out


def axis_selection_responded(reference_intents, perturbed_intents) -> Optional[bool]:
    """PRIMARY (reported, NOT gated): did the AXIS CHOICE move toward the perturbed axis?

    Returns None -- "not measurable" -- when neither arm used any opponent-profile axis:
    with no axis selected in either arm there is nothing for axis selection to respond
    with, and scoring that as False would penalise a model for a measurement we could not
    make. Fail-closed on N is handled by the caller, not by inventing a verdict here.
    """
    a = profile_axes_used(reference_intents)
    b = profile_axes_used(perturbed_intents)
    if not a and not b:
        return None
    moved = (a ^ b) & PROFILE_AXIS_TARGET_AXES
    return bool(moved)


def surface_sensitivity(reference_intents, perturbed_intents) -> bool:
    """GATED: did the intent delta touch the perturbed offensive surface at all?

    Mirrors V2's meaningful-sensitivity rule (`_analyze_v2.intent_touches_profile`) so the
    two generations' sensitivity readings remain comparable, but keyed on V3's surface.
    """
    def keyed(intents):
        return {(i.get("research_family"), i.get("subject"), i.get("metric"),
                 i.get("side"), i.get("window"), i.get("period"),
                 tuple(sorted((c.get("dimension"), c.get("value"), c.get("axis"))
                              for c in (i.get("conditions") or []))),
                 i.get("comparison")): i
                for i in intents}

    a, b = keyed(reference_intents), keyed(perturbed_intents)
    delta = [a[k] for k in set(a) - set(b)] + [b[k] for k in set(b) - set(a)]
    return any(intent_touches_perturbed_offensive_surface(i) for i in delta)


def ablated_dimension_disappeared(intents: Iterable[dict],
                                  dimension: str = "opponent_profile") -> bool:
    """Did every condition on the withdrawn dimension disappear from the ablated arm?"""
    return not any(c.get("dimension") == dimension
                   for i in intents for c in (i.get("conditions") or []))


def version_stamp() -> dict:
    return {
        "controls_v3_version": CONTROLS_V3_VERSION,
        "profile_axis_perturbation": {
            "metrics": list(PROFILE_AXIS_PERTURBATION_METRICS),
            "subject": PROFILE_AXIS_PERTURBATION_SUBJECT,
            "raise_factor": PROFILE_AXIS_RAISE_FACTOR,
            "lower_factor": PROFILE_AXIS_LOWER_FACTOR,
            "raise_indices": list(PROFILE_AXIS_RAISE_INDICES),
            "target_axes": sorted(PROFILE_AXIS_TARGET_AXES),
            "target_metrics": sorted(PROFILE_AXIS_TARGET_METRICS),
        },
        "availability_ablation": {
            "dimensions": list(AVAILABILITY_ABLATION_DIMENSIONS),
            "note": AVAILABILITY_ABLATION_NOTE,
        },
        "context_addition": CONTEXT_ADDITION_REJECTION,
    }
