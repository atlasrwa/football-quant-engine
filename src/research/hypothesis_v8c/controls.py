"""V8C control arms (`v8c_controls_v1`) -- repairs P1 `D-V8C-P1-RIDENT` and
`D-V8C-P1-HUNIVERSE`. See V8C_DISTINCT_BLIND_CONTROL_SPEC.md.

ARM R -- matched blind control, now a TRUE COUNTERFACTUAL
--------------------------------------------------------
V8B.1's `controls.match_blind_control(shape, capability, exclude_ids)` seeded `exclude_ids`
only with control ids ALREADY USED at that fixture. Sonnet's own id was never excluded, so the
EXACT tier -- which matches on metric/subject/side/comparator/n_conditions/capability_status
and then sorts by `hypothesis_id` -- would happily return Sonnet's own hypothesis. On the
exposed 50 this happened at ALL FOUR paired fixtures: `R_ID == S_ID`, so `D_SR(T) == 0` by
construction and the S-v-R endpoint measured nothing.

V8C's ONLY new hard condition is the one §11 names:

    candidate_id != Sonnet_id

implemented literally, per pair, by seeding the exclusion set with `shape.hypothesis_id`. The
frozen tier hierarchy is otherwise untouched and still walked in order:

    EXACT -> CONDITIONS_PM1 -> CAPABILITY_EITHER -> MECHANISM_FAMILY -> SIDE_EITHER -> UNMATCHED

If no legitimate DISTINCT control exists, the arm reports `UNMATCHED_DISTINCT_CONTROL`. It
does not fabricate one and it does not duplicate Sonnet (§10).

R REMAINS BLIND (§11). It reads no Sonnet prose, no mechanism summary, no research reason, no
outcome, no observed effect and no scorer output -- only the six structural fields on
`SonnetShape` (frozen type, imported unchanged: there is no prose field on it to read).

ARM H -- same universe as S and R
---------------------------------
`heuristic_score` and all five coefficients are imported BYTE-IDENTICALLY from
`hypothesis_v8b1.controls`; the ranking formula is NOT redesigned and is not tuned against any
outcome (§13). What changes is only the CANDIDATE SET: H now ranks over the whole
PRE_T_EVALUABLE universe, the same set S searched and R matched within, instead of over the 50
structurally-lowest ir_ids that survived the presentation cap.

ZERO SPEND. No network. No CHAMPION. Reads no target outcome, ever.
"""
from __future__ import annotations

from src.research.hypothesis_v8b1 import controls as V8B1C
from src.research.hypothesis_v8b1 import search as SE
from src.research.hypothesis_v8c import universe as UNI

CONTROLS_VERSION = "v8c_controls_v1"

#: Frozen, imported unchanged (§13) -- not restated, so they cannot drift.
SonnetShape = V8B1C.SonnetShape
shape_of = V8B1C.shape_of
heuristic_score = V8B1C.heuristic_score
MATCH_DIMENSIONS = V8B1C.MATCH_DIMENSIONS
RELAXATION_TIERS = V8B1C._RELAXATION_TIERS

MATCHED = "MATCHED"
UNMATCHED_DISTINCT_CONTROL = "UNMATCHED_DISTINCT_CONTROL"
H_UNAVAILABLE_EMPTY_UNIVERSE = "H_UNAVAILABLE_EMPTY_UNIVERSE"


# ============================ Arm R: distinct matched blind =============================
def match_distinct_blind_control(shape: SonnetShape, fixture_universe, exclude_ids) -> dict | None:
    """One DISTINCT blind control for one Sonnet selection, from the pre-T evaluable universe.

    `exclude_ids` carries the controls already used at this fixture. Sonnet's own id is added
    to it unconditionally here -- that is the whole repair. Returns None only when the frozen
    tier hierarchy is exhausted without a distinct candidate.
    """
    blocked = set(exclude_ids) | {shape.hypothesis_id}       # <-- the one new hard condition
    for tier in RELAXATION_TIERS:
        if tier == "UNMATCHED":
            return None
        kwargs = V8B1C._tier_query_kwargs(shape, tier)
        if kwargs is None:
            continue
        q = SE.SearchQuery(max_results=UNI.PRESENTATION_CAP, **kwargs)
        candidates = [c for c in UNI.search_evaluable(q, fixture_universe)
                      if c["hypothesis_id"] not in blocked]
        filtered = V8B1C._tier_filter(shape, tier, candidates)
        if filtered:
            filtered.sort(key=lambda c: c["hypothesis_id"])
            picked = dict(filtered[0], matched_tier=tier)
            assert picked["hypothesis_id"] != shape.hypothesis_id, (
                "R identity collapse: the distinct-control exclusion failed")
            return picked
    return None


def blind_selections_for_fixture(sonnet_shapes, fixture_universe) -> dict:
    """Arm R's full output for one fixture: one DISTINCT control per Sonnet selection, in
    Sonnet's own order, sized to exactly `K_valid(T)`. UNMATCHED entries are included and
    counted, never silently dropped (§10)."""
    used, out = set(), []
    for shape in sonnet_shapes:
        m = match_distinct_blind_control(shape, fixture_universe, used)
        if m is not None:
            used.add(m["hypothesis_id"])
            out.append({"status": MATCHED, "sonnet_hypothesis_id": shape.hypothesis_id, **m})
        else:
            out.append({"status": UNMATCHED_DISTINCT_CONTROL,
                        "sonnet_hypothesis_id": shape.hypothesis_id})
    identity = sum(1 for o in out
                   if o.get("hypothesis_id") == o.get("sonnet_hypothesis_id"))
    # Reported separately because a reviewer will ask: R's pick may legitimately coincide with
    # a DIFFERENT Sonnet selection at the same fixture. That is not identity collapse -- the
    # pair (S_i, R_i) is still distinct -- but it must be visible, not buried.
    sonnet_ids = {s.hypothesis_id for s in sonnet_shapes}
    cross = sum(1 for o in out
                if o["status"] == MATCHED and o["hypothesis_id"] in sonnet_ids)
    return {"k_valid": len(sonnet_shapes),
            "n_matched": sum(1 for o in out if o["status"] == MATCHED),
            "n_unmatched": sum(1 for o in out if o["status"] == UNMATCHED_DISTINCT_CONTROL),
            "identity_count": identity,
            "cross_pair_overlap_count": cross,
            "selections": out}


# ============================== Arm H: deterministic heuristic ===========================
def heuristic_selections_for_fixture(k_valid: int, fixture_universe) -> dict:
    """Arm H's full output for one fixture: top-`k_valid` by the FROZEN `heuristic_score` over
    the ENTIRE pre-T evaluable universe, tie-broken by hypothesis_id.

    The formula and its coefficients are V8B.1's, unchanged. Only the candidate set is
    corrected, so that H answers the same question S and R answer."""
    candidates = list(fixture_universe.evaluable)
    if not candidates:
        return {"k_valid": k_valid, "n_selected": 0, "status": H_UNAVAILABLE_EMPTY_UNIVERSE,
                "selections": []}
    scored = [(heuristic_score(c), c["hypothesis_id"], c) for c in candidates]
    scored.sort(key=lambda t: (-t[0], t[1]))
    return {"k_valid": k_valid, "n_selected": len(scored[:k_valid]), "status": MATCHED,
            "n_ranked_over": len(candidates),
            "selections": [dict(c, heuristic_score=s) for s, _id, c in scored[:k_valid]]}


def version_stamp() -> dict:
    return {"controls_version": CONTROLS_VERSION,
            "successor_to": V8B1C.CONTROLS_VERSION,
            "repairs": ["D-V8C-P1-RIDENT", "D-V8C-P1-HUNIVERSE"],
            "match_dimensions": list(MATCH_DIMENSIONS),
            "relaxation_tiers": list(RELAXATION_TIERS),
            "r_only_new_hard_condition": "candidate_id != sonnet_id, applied per pair",
            "r_identity_permitted": False,
            "r_unmatched_status": UNMATCHED_DISTINCT_CONTROL,
            "h_ranks_over": "the entire PRE_T_EVALUABLE universe",
            "h_formula_changed": False,
            "h_coefficients": V8B1C.version_stamp()["heuristic_coefficients"],
            "all_arms_share_one_universe": True,
            "reads_outcomes": False, "reads_llm_prose": False,
            "tuned_against_sonnet_result": False}
