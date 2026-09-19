"""V8C R action-space coverage audit (`v8c_control_coverage_v1`) -- Gate A Phase 6.

Closes the open R-coverage question with two DIFFERENT measurements, because they answer two
different questions and only one of them is the experiment's actual requirement.

1. SINGLE-CANDIDATE COVERAGE
   For ONE S candidate in isolation, does a distinct matched R exist at all? Reported per
   relaxation tier, so what had to be traded away to obtain a match is legible.

2. SET-LEVEL FEASIBILITY UP TO K = MAX_SELECTIONS
   The experiment never matches one selection in isolation. S submits up to 8 ids AT ONCE, and
   `controls.blind_selections_for_fixture` must find a distinct control for EVERY one of them,
   where no control may be reused and no control may be any S id. That is a bipartite matching
   problem, and single-candidate coverage does not imply it.

WHY GREEDY IS NOT THE ANSWER
----------------------------
`blind_selections_for_fixture` assigns controls one at a time against an accumulating `used`
set. Greedy assignment can fail on a set for which a perfect matching exists: an early S id
takes the only candidate a later S id could have used. Reporting greedy failure as set-level
infeasibility would UNDERSTATE the control arm, and reporting greedy success as proof would be
luck rather than structure.

So feasibility is computed with an actual maximum bipartite matching (Kuhn's augmenting-path
algorithm -- the candidate lists here are small). `R_SET_LEVEL_K8_FEASIBLE` is a statement
about the STRUCTURE of the action space. `greedy_achieves_maximum` is reported alongside it, so
a gap between what is possible and what the production greedy path actually attains is visible
rather than hidden.

NOT A PROXY. The audit does not sample "the first four candidates" and extrapolate. Every
evaluable candidate is classified, and the S-sets tested are stated explicitly in the output.

ZERO SPEND. Reads no target outcome, no model output and no Sonnet prose.
"""
from __future__ import annotations

from src.research.hypothesis_v8c import controls as CTL

CONTROL_COVERAGE_VERSION = "v8c_control_coverage_v1"

MAX_SELECTIONS = 8


def admissible_controls(shape, fixture_universe, *, exclude_ids=frozenset()):
    """Every candidate that could serve as a distinct control for `shape`, with the EARLIEST
    tier at which it qualifies. Ordered by (tier index, id) so the result is deterministic."""
    out = []
    blocked = set(exclude_ids) | {shape.hypothesis_id}
    for ti, tier in enumerate(CTL.RELAXATION_TIERS):
        if tier == "UNMATCHED":
            break
        pred = CTL._tier_predicate(shape, tier)
        for c in fixture_universe.evaluable:
            hid = c["hypothesis_id"]
            if hid in blocked or any(o[0] == hid for o in out):
                continue
            if pred(c):
                out.append((hid, tier, ti))
    out.sort(key=lambda t: (t[2], t[0]))
    return out


def single_candidate_coverage(fixture_universe) -> dict:
    """Question 1: in isolation, does each S-addressable candidate have a distinct R?"""
    n_total = 0
    n_with_control = 0
    by_tier = {}
    unmatched_classes = {}
    for cand in fixture_universe.evaluable:
        n_total += 1
        shape = CTL.shape_of(cand)
        adm = admissible_controls(shape, fixture_universe)
        if adm:
            n_with_control += 1
            tier = adm[0][1]
            by_tier[tier] = by_tier.get(tier, 0) + 1
        else:
            cls = (shape.target_metric, shape.comparator, shape.window,
                   shape.condition_family)
            unmatched_classes[str(cls)] = unmatched_classes.get(str(cls), 0) + 1
    return {
        "n_s_addressable_candidates": n_total,
        "n_with_distinct_control": n_with_control,
        "n_without_distinct_control": n_total - n_with_control,
        "coverage_rate": (n_with_control / n_total) if n_total else None,
        "earliest_tier_histogram": dict(sorted(by_tier.items())),
        "exact_tier_coverage": by_tier.get("EXACT", 0),
        "relaxed_tier_coverage": sum(v for k, v in by_tier.items() if k != "EXACT"),
        "unmatched_candidate_classes": dict(sorted(unmatched_classes.items())),
    }


# ----------------------------------------------------------------- maximum bipartite matching
def _max_matching(s_ids, options) -> dict:
    """Kuhn's augmenting-path maximum bipartite matching.

    `options[s_id]` is the list of control ids admissible for that S id. Returns
    {s_id: control_id} of maximum cardinality. Deterministic: options are consumed in the
    order given, which `admissible_controls` already sorts.
    """
    match_by_control = {}

    def try_assign(s, seen):
        for c in options.get(s, ()):
            if c in seen:
                continue
            seen.add(c)
            holder = match_by_control.get(c)
            if holder is None or try_assign(holder, seen):
                match_by_control[c] = s
                return True
        return False

    for s in s_ids:
        try_assign(s, set())
    return {s: c for c, s in match_by_control.items()}


def set_level_feasibility(fixture_universe, s_sets) -> dict:
    """Question 2: can EVERY member of an S-set of size k get its own distinct control?

    `s_sets` is an explicit list of id-lists. They are reported verbatim in the output so a
    reader knows exactly which sets the claim covers.
    """
    by_id = {c["hypothesis_id"]: c for c in fixture_universe.evaluable}
    rows = []
    for s_ids in s_sets:
        s_ids = [i for i in s_ids if i in by_id]
        if not s_ids:
            continue
        s_set = set(s_ids)
        options = {}
        for hid in s_ids:
            shape = CTL.shape_of(by_id[hid])
            # A control may never be ANY S id in the set (cross-treatment overlap), nor the
            # matched S id itself.
            options[hid] = [c for c, _tier, _ti in
                            admissible_controls(shape, fixture_universe, exclude_ids=s_set)]
        best = _max_matching(s_ids, options)

        greedy = CTL.blind_selections_for_fixture(
            [CTL.shape_of(by_id[h]) for h in s_ids], fixture_universe)
        rows.append({
            "k": len(s_ids),
            "s_ids": list(s_ids),
            "max_matching_size": len(best),
            "feasible": len(best) == len(s_ids),
            "greedy_matched": greedy["n_matched"],
            "greedy_achieves_maximum": greedy["n_matched"] == len(best),
            "greedy_identity_count": greedy["identity_count"],
            "greedy_cross_treatment_overlap_count": greedy["cross_treatment_overlap_count"],
            "min_options_across_set": min((len(v) for v in options.values()), default=0),
        })
    feasible = all(r["feasible"] for r in rows) if rows else None
    return {
        "max_selections": MAX_SELECTIONS,
        "n_sets_tested": len(rows),
        "all_sets_feasible": feasible,
        "sets": rows,
        "method": "maximum bipartite matching (Kuhn), not greedy assignment",
        "why_not_greedy": ("greedy can fail where a perfect matching exists, because an early "
                           "S id may consume the only control a later S id could use"),
    }


def audit_fixture(fixture_universe, *, s_sets=None, k=MAX_SELECTIONS) -> dict:
    """The full R action-space audit for ONE fixture.

    When `s_sets` is not supplied, a DEFAULT probe set of size `k` is constructed from the
    fixture's own evaluable universe in canonical id order. That is a structural probe, not a
    claim about any real S selection, and is labelled as such in the output.
    """
    single = single_candidate_coverage(fixture_universe)
    ids = list(fixture_universe.evaluable_ids())
    provenance = "caller-supplied"
    if s_sets is None:
        provenance = "default structural probe: first-k and last-k in canonical id order"
        s_sets = [ids[:k], ids[-k:]] if len(ids) >= k else ([ids] if ids else [])
    sets = set_level_feasibility(fixture_universe, s_sets)
    return {
        "control_coverage_version": CONTROL_COVERAGE_VERSION,
        "fixture_id": fixture_universe.fixture_id,
        "n_evaluable": fixture_universe.n_evaluable,
        "R_SINGLE_CANDIDATE_COVERAGE": single["coverage_rate"],
        "R_SET_LEVEL_K8_FEASIBLE": sets["all_sets_feasible"],
        "s_set_provenance": provenance,
        "single_candidate": single,
        "set_level": sets,
        "uses_first_four_proxy": False,
    }


def version_stamp() -> dict:
    return {"control_coverage_version": CONTROL_COVERAGE_VERSION,
            "max_selections": MAX_SELECTIONS,
            "measures": ["R_SINGLE_CANDIDATE_COVERAGE", "R_SET_LEVEL_K8_FEASIBLE"],
            "set_level_method": "maximum bipartite matching (Kuhn)",
            "greedy_reported_alongside": True,
            "uses_first_four_proxy": False,
            "controls_may_be_reused": False,
            "control_may_be_an_s_id": False,
            "reads_outcomes": False}
