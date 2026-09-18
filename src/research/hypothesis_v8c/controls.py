"""V8C control arms (`v8c_controls_v2`) -- repairs P1 R CONTROL, P1 R PAIRING, P1 H.

ARM R -- a genuine distinct matched blind counterfactual
-------------------------------------------------------
Two defects, not one:

  1. V8B.1 seeded its exclusion set only with already-used control ids, so `R_ID == S_ID` was
     permitted (5/5 identity collapse measured on the exposed 50).
  2. V8C v1 excluded only the PAIRED Sonnet id. R could therefore return a DIFFERENT
     hypothesis that Sonnet had also selected at the same fixture -- still treatment, wearing
     a control label. V8C v2 excludes ALL Sonnet-selected ids at that fixture, so
     cross-treatment overlap is structurally 0 and is ASSERTED, not merely reported.

Nuisance matching is widened to everything the mission names: metric, subject, perspective,
comparator, WINDOW, condition count, CONDITION FAMILY, similarity usage and capability class.
V8B.1 matched six of those; `window` and `condition_family` are new because the V8C grammar
now varies them, and an unmatched nuisance dimension is a confound in the paired difference.

Relaxation tiers stay EXPLICIT and ORDERED, and the arm fails `UNMATCHED_DISTINCT_CONTROL`
rather than fabricating a control.

R REMAINS BLIND. It reads no Sonnet prose, no mechanism summary, no research reason, no
outcome, no observed effect and no scorer output -- only the structural shape and the set of
ids to exclude.

ARM H -- unchanged formula, whole universe, NOT pair-matched
------------------------------------------------------------
`heuristic_score` and all five coefficients are imported byte-identically from
`hypothesis_v8b1.controls`. H ranks over the ENTIRE pre-T evaluable universe. H is deliberately
NOT pair-matched: it is a policy baseline ("what would a fixed deterministic ranker pick?"),
so its endpoint keeps arm-mean semantics while S-v-R is pair-level. The two estimands are
DIFFERENT and are named differently everywhere so they are never read as comparable.

ZERO SPEND. Reads no target outcome, ever.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.research.hypothesis_v8b1 import controls as V8B1C
from src.research.hypothesis_v8c import universe as UNI

CONTROLS_VERSION = "v8c_controls_v2"

#: Frozen, imported unchanged -- the heuristic formula is NOT redesigned.
heuristic_score = V8B1C.heuristic_score

MATCHED = "MATCHED"
UNMATCHED_DISTINCT_CONTROL = "UNMATCHED_DISTINCT_CONTROL"
H_UNAVAILABLE_EMPTY_UNIVERSE = "H_UNAVAILABLE_EMPTY_UNIVERSE"

#: Every nuisance dimension R matches on. Widened from V8B.1's six.
MATCH_DIMENSIONS = ("target_metric", "subject", "perspective", "comparator", "window",
                    "n_conditions", "condition_family", "uses_similarity",
                    "capability_status")

#: Ordered relaxation. Each tier drops exactly ONE nuisance constraint, so what was traded
#: away to obtain a match is always legible in the frozen record.
RELAXATION_TIERS = (
    "EXACT",                  # every dimension matches
    "CONDITION_FAMILY_ANY",   # drop condition_family
    "CONDITIONS_PM1",         # ...and allow n_conditions +/- 1
    "WINDOW_ANY",             # ...and allow any window
    "CAPABILITY_EITHER",      # ...and allow either capability class
    "PERSPECTIVE_EITHER",     # ...and allow either perspective
    "UNMATCHED",
)


@dataclass(frozen=True)
class SonnetShape:
    """The ONLY view of a Sonnet selection either control arm may see. There is deliberately
    NO prose field on this type -- there is nothing to accidentally read."""
    hypothesis_id: str
    target_metric: str
    subject: str
    perspective: str
    comparator: str
    window: str
    n_conditions: int
    condition_family: str
    uses_similarity: bool
    capability_status: str


def condition_family(conditions) -> str:
    """A canonical, order-independent label for the condition SHAPE (not its values).

    `venue+opponent_profile` and `opponent_profile+venue` are the same family; HOME vs AWAY is
    not part of the family, because matching on the VALUE would leave R almost no candidates
    while matching on the SHAPE controls the structural nuisance that matters.
    """
    if not conditions:
        return "NONE"
    return "+".join(sorted({c["dimension"] for c in conditions}))


def shape_of(candidate: dict) -> SonnetShape:
    return SonnetShape(
        hypothesis_id=candidate["hypothesis_id"],
        target_metric=candidate["target_metrics"][0],
        subject=candidate["subject"],
        perspective=candidate["side"],
        comparator=candidate["comparator"],
        window=candidate["window"],
        n_conditions=candidate["complexity"]["n_conditions"],
        condition_family=condition_family(candidate["conditions"]),
        uses_similarity=bool(candidate["complexity"]["uses_similarity"]),
        capability_status=candidate["capability_status"],
    )


def _tier_predicate(shape: SonnetShape, tier: str):
    """The match predicate for one tier. Dimensions are dropped CUMULATIVELY down the order,
    so a later tier is always strictly more permissive than an earlier one."""
    drop = {
        "EXACT": set(),
        "CONDITION_FAMILY_ANY": {"condition_family"},
        "CONDITIONS_PM1": {"condition_family", "n_conditions_exact"},
        "WINDOW_ANY": {"condition_family", "n_conditions_exact", "window"},
        "CAPABILITY_EITHER": {"condition_family", "n_conditions_exact", "window",
                              "capability_status"},
        "PERSPECTIVE_EITHER": {"condition_family", "n_conditions_exact", "window",
                               "capability_status", "perspective"},
    }[tier]

    def ok(c: dict) -> bool:
        # Never relaxed: these define the question being asked.
        if c["target_metrics"][0] != shape.target_metric:
            return False
        if c["subject"] != shape.subject:
            return False
        if c["comparator"] != shape.comparator:
            return False
        if bool(c["complexity"]["uses_similarity"]) != shape.uses_similarity:
            return False
        if "perspective" not in drop and c["side"] != shape.perspective:
            return False
        if "window" not in drop and c["window"] != shape.window:
            return False
        if "capability_status" not in drop and c["capability_status"] != shape.capability_status:
            return False
        if "condition_family" not in drop and \
                condition_family(c["conditions"]) != shape.condition_family:
            return False
        n = c["complexity"]["n_conditions"]
        if "n_conditions_exact" in drop:
            if abs(n - shape.n_conditions) > 1:
                return False
        elif n != shape.n_conditions:
            return False
        return True

    return ok


def match_distinct_blind_control(shape: SonnetShape, fixture_universe, exclude_ids) -> dict | None:
    """One DISTINCT blind control for one Sonnet selection.

    `exclude_ids` MUST already contain every Sonnet-selected id at this fixture plus every
    control already used here. Returns None (UNMATCHED) when the ordered relaxation is
    exhausted without a distinct candidate -- never a fabricated or duplicated one.
    """
    blocked = set(exclude_ids)
    for tier in RELAXATION_TIERS:
        if tier == "UNMATCHED":
            return None
        pred = _tier_predicate(shape, tier)
        cands = [c for c in fixture_universe.evaluable
                 if c["hypothesis_id"] not in blocked and pred(c)]
        if cands:
            cands.sort(key=lambda c: c["hypothesis_id"])
            picked = dict(cands[0], matched_tier=tier)
            assert picked["hypothesis_id"] != shape.hypothesis_id, (
                "R identity collapse: the distinct-control exclusion failed")
            return picked
    return None


def blind_selections_for_fixture(sonnet_shapes, fixture_universe) -> dict:
    """Arm R for one fixture: one DISTINCT control per Sonnet selection, in Sonnet's own order.

    The exclusion set is seeded with ALL Sonnet ids at this fixture, so a control can never be
    another arm-S selection. Emits the `(S_ID, R_ID, tier)` triple that must survive freeze,
    scoring and aggregation (P1 R PAIRING).
    """
    sonnet_ids = {s.hypothesis_id for s in sonnet_shapes}
    used, pairs = set(), []
    for shape in sonnet_shapes:
        m = match_distinct_blind_control(shape, fixture_universe, sonnet_ids | used)
        if m is not None:
            used.add(m["hypothesis_id"])
            pairs.append({"status": MATCHED, "s_id": shape.hypothesis_id,
                          "r_id": m["hypothesis_id"], "tier": m["matched_tier"],
                          "candidate": m})
        else:
            pairs.append({"status": UNMATCHED_DISTINCT_CONTROL, "s_id": shape.hypothesis_id,
                          "r_id": None, "tier": "UNMATCHED", "candidate": None})

    identity = sum(1 for p in pairs if p["r_id"] is not None and p["r_id"] == p["s_id"])
    cross = sum(1 for p in pairs if p["r_id"] in sonnet_ids and p["r_id"] is not None)
    # Structural, not aspirational: the exclusion seed makes both zero by construction.
    assert identity == 0, f"R identity collapse: {identity}"
    assert cross == 0, f"R selected a Sonnet-treated hypothesis: {cross}"

    tiers = {}
    for p in pairs:
        tiers[p["tier"]] = tiers.get(p["tier"], 0) + 1
    return {"k_valid": len(sonnet_shapes),
            "n_matched": sum(1 for p in pairs if p["status"] == MATCHED),
            "n_unmatched": sum(1 for p in pairs if p["status"] != MATCHED),
            "identity_count": identity, "cross_treatment_overlap_count": cross,
            "tiers": dict(sorted(tiers.items())), "pairs": pairs}


# ============================== Arm H: deterministic heuristic ===========================
def heuristic_selections_for_fixture(k_valid: int, fixture_universe) -> dict:
    """Top-`k_valid` by the FROZEN `heuristic_score` over the ENTIRE evaluable universe.

    Not pair-matched by design: H is a policy baseline, so S-v-H keeps arm-mean semantics.
    """
    candidates = list(fixture_universe.evaluable)
    if not candidates or k_valid <= 0:
        return {"k_valid": k_valid, "n_selected": 0,
                "status": H_UNAVAILABLE_EMPTY_UNIVERSE if not candidates else MATCHED,
                "n_ranked_over": len(candidates), "selections": []}
    scored = [(heuristic_score(c), c["hypothesis_id"], c) for c in candidates]
    scored.sort(key=lambda t: (-t[0], t[1]))
    top = scored[:k_valid]
    return {"k_valid": k_valid, "n_selected": len(top), "status": MATCHED,
            "n_ranked_over": len(candidates),
            "selections": [dict(c, heuristic_score=s) for s, _id, c in top]}


def version_stamp() -> dict:
    return {"controls_version": CONTROLS_VERSION,
            "successor_to": V8B1C.CONTROLS_VERSION,
            "repairs": ["P1-R-CONTROL", "P1-R-PAIRING", "P1-H"],
            "match_dimensions": list(MATCH_DIMENSIONS),
            "match_dimensions_added_vs_v8b1": ["perspective", "window", "condition_family",
                                               "uses_similarity"],
            "relaxation_tiers": list(RELAXATION_TIERS),
            "r_excludes": "ALL Sonnet-selected ids at the fixture, plus used controls",
            "r_identity_permitted": False,
            "r_cross_treatment_overlap_permitted": False,
            "r_exclusion_is_asserted_not_reported": True,
            "r_unmatched_status": UNMATCHED_DISTINCT_CONTROL,
            "r_emits_pair_triple": "(s_id, r_id, tier)",
            "h_pair_matched": False,
            "h_ranks_over": "the entire PRE_T_EVALUABLE universe",
            "h_formula_changed": False,
            "h_coefficients": V8B1C.version_stamp()["heuristic_coefficients"],
            "estimands": {"S_vs_R": "matched-pair level", "S_vs_H": "arm-mean level"},
            "reads_outcomes": False, "reads_llm_prose": False,
            "tuned_against_sonnet_result": False}
