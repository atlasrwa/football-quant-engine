"""V8C LIVE search reachability (`v8c_live_reachability_v1`) -- repairs P1-C.

THE DEFECT
----------
`unreachable_candidate_count == 0` was proven by paginating a single unfiltered query to
exhaustion. That establishes THEORETICAL API reachability. It does not establish TREATMENT
reachability, because the live protocol caps the model at

    MAX_SEARCH_CALLS = 6      PAGE_SIZE_CAP = 50

and ~900 evaluable candidates cannot be enumerated in six broad pages. Pretending otherwise
would silently replace the 6-call cap with unlimited search.

WHAT "S ACTION SPACE" MEANS UNDER THE LIVE PROTOCOL
--------------------------------------------------
A candidate is LIVE-ADDRESSABLE iff there exists at least one LEGAL structural query -- one the
model can actually express through the search tool's own parameters -- that returns it

    * within PAGE_SIZE_CAP results, on the FIRST page, and
    * therefore in ONE search call, not six.

This is a statement about ADDRESSABILITY, not enumeration. The model is not required to see
every candidate; it is required that no candidate is INVISIBLE to it -- that for any hypothesis
R or H could pick, S had a query that would have surfaced it.

The canonical addressing query is the candidate's own structural coordinates:

    target_metric, subject, side, comparator, window, max_conditions
    + the discriminating condition filter (opponent_profile axis / venue / competition)

These are exactly the fields `SearchQuery` already exposes, so every such query is legal.

`LIVE_UNREACHABLE_CANDIDATES` is COMPUTED by constructing each candidate's canonical query and
checking the candidate appears in the first page. If it cannot reach zero without changing the
experiment, that is reported as a DESIGN CONFLICT -- the definition is not weakened and the
call cap is not raised.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

from src.research.hypothesis_v8c import universe as UNI

LIVE_REACHABILITY_VERSION = "v8c_live_reachability_v1"

#: The live protocol's own limits. Imported conceptually from the runner; restated here as the
#: constraint being tested, and never relaxed by this module.
MAX_SEARCH_CALLS = 6
PAGE_SIZE_CAP = UNI.PAGE_SIZE_CAP


def canonical_query(candidate: dict) -> UNI.SearchQuery:
    """The most specific LEGAL query that names this candidate's structural coordinates.

    Every field used here is a real `SearchQuery` parameter, so the model can express it.
    """
    conds = candidate["conditions"]
    profile_axis = next((c.get("axis") for c in conds
                         if c.get("dimension") == "opponent_profile"), None)
    venue = next((c.get("value") for c in conds
                  if c.get("dimension") == "historical_venue_conditioning"), None)
    has_comp = any(c.get("dimension") == "competition" for c in conds)
    return UNI.SearchQuery(
        target_metric=candidate["target_metrics"][0],
        subject=candidate["subject"],
        side=candidate["side"],
        comparator=candidate["comparator"],
        window=candidate["window"],
        opponent_profile_dimension=profile_axis,
        venue=venue,
        competition_conditioned=has_comp,
        max_conditions=candidate["complexity"]["n_conditions"],
        max_results=PAGE_SIZE_CAP,
    )


def audit_fixture(fixture_universe) -> dict:
    """Is every evaluable candidate reachable in ONE live search call? COMPUTED, not asserted."""
    unreachable, needing_pagination, worst = [], [], 0
    by_class = {}

    for cand in fixture_universe.evaluable:
        q = canonical_query(cand)
        page = UNI.search_evaluable(q, fixture_universe)
        n_matching = page["n_matching"]
        worst = max(worst, n_matching)
        found = any(c["hypothesis_id"] == cand["hypothesis_id"] for c in page["results"])
        cls = (cand["comparator"], cand["window"],
               "+".join(sorted({c["dimension"] for c in cand["conditions"]})) or "NONE")
        rec = by_class.setdefault(cls, {"n": 0, "unreachable": 0, "max_result_set": 0})
        rec["n"] += 1
        rec["max_result_set"] = max(rec["max_result_set"], n_matching)
        if not found:
            unreachable.append({"hypothesis_id": cand["hypothesis_id"],
                                "n_matching": n_matching, "class": list(cls)})
            rec["unreachable"] += 1
        if n_matching > PAGE_SIZE_CAP:
            needing_pagination.append({"hypothesis_id": cand["hypothesis_id"],
                                       "n_matching": n_matching,
                                       "pages_required": -(-n_matching // PAGE_SIZE_CAP)})

    max_pages = max((x["pages_required"] for x in needing_pagination), default=1)
    failing_classes = {str(k): v for k, v in sorted(by_class.items()) if v["unreachable"]}
    return {
        "live_reachability_version": LIVE_REACHABILITY_VERSION,
        "fixture_id": fixture_universe.fixture_id,
        "n_evaluable": fixture_universe.n_evaluable,
        "n_live_addressable": fixture_universe.n_evaluable - len(unreachable),
        "n_live_unreachable": len(unreachable),
        "worst_canonical_result_set": worst,
        "page_size_cap": PAGE_SIZE_CAP,
        "max_search_calls": MAX_SEARCH_CALLS,
        "candidates_requiring_pagination": len(needing_pagination),
        "max_pages_required_for_any_candidate": max_pages,
        "pagination_within_call_budget": max_pages <= MAX_SEARCH_CALLS,
        "failing_candidate_classes": failing_classes,
        "unreachable_sample": unreachable[:10],
        "definition": ("a candidate is LIVE-ADDRESSABLE iff its canonical structural query "
                       "returns it on the FIRST page, i.e. in one search call"),
        "call_cap_relaxed": False,
    }


def version_stamp() -> dict:
    return {"live_reachability_version": LIVE_REACHABILITY_VERSION,
            "repairs": ["P1-C"],
            "max_search_calls": MAX_SEARCH_CALLS, "page_size_cap": PAGE_SIZE_CAP,
            "measures": "addressability under the LIVE bounded-search protocol",
            "not_measured": "exhaustive enumeration, which 6 calls cannot achieve",
            "call_cap_relaxed": False,
            "reports_design_conflict_rather_than_weakening_the_definition": True}
