"""Grammar completeness, search reachability, competition admissibility and the MEASSPACE
projection."""
from __future__ import annotations

import pytest

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v8c import grammar as GR
from src.research.hypothesis_v8c import pre_t as PT
from src.research.hypothesis_v8c import universe as UNI

from .conftest import GRAMMAR_KW


def test_grammar_contains_every_declared_dimension(golden_env):
    size = GR.grammar_size(golden_env.capability)
    assert size["n_windows"] == 3, "W5/W10 must be in the grammar"
    assert size["n_comparators"] == 10
    assert size["n_condition_shapes"] == 76
    assert size["n_condition_shapes_by_arity"] == {"0": 1, "1": 21, "2": 54}
    assert size["n_enumerated_shapes"] == 218880


def test_windows_and_interactions_actually_appear():
    seen_windows, seen_arities = set(), set()
    for c in GR.CONDITION_SHAPES:
        seen_arities.add(len(c))
    assert seen_arities == {0, 1, 2}
    assert set(GR.WINDOWS) == {"ALL_PRIOR", "W5", "W10"}
    two = [c for c in GR.CONDITION_SHAPES if len(c) == 2]
    fams = {"+".join(sorted(x["dimension"] for x in c)) for c in two}
    assert fams == {"historical_venue_conditioning+opponent_profile",
                    "competition+opponent_profile"}


def test_single_target_metric_preserved(golden_env):
    for spec, ir in GR.build_valid_irs(golden_env.capability, metrics=["goals"]):
        assert len(ir.target_metrics) == 1


def test_research_family_is_total_and_prose_free():
    fams = set()
    for m in ("goals", "corner_kicks", "yellow_cards", "possession", "tackles", "xg"):
        for p in ("FOR", "AGAINST"):
            for c in ("SUBJECT_OVERALL_BASELINE", "SIMILAR_OPPONENT_COHORT",
                      "LEAGUE_ENVIRONMENT_BASELINE", "OPPONENT_OVERALL_BASELINE"):
                for w in GR.WINDOWS:
                    f = GR.research_family(m, p, c, w)
                    assert f in GR.RESEARCH_FAMILIES
                    fams.add(f)
    assert len(fams) >= 5, "the family map collapses everything into too few families"
    assert "V8B1_SEARCH" not in fams


def test_resolver_key_does_not_collide_on_equal_length(golden_env):
    """P1-L: the key hashed `len(condition_set)`, so two DIFFERENT sets of EQUAL length
    collided and the second caller silently received the first caller's resolution map."""
    cap = golden_env.capability
    a = [[{"dimension": "historical_venue_conditioning", "value": "HOME"}]]
    b = [[{"dimension": "historical_venue_conditioning", "value": "AWAY"}]]
    assert len(a) == len(b) == 1

    ka = GR._resolver_key(cap, {"condition_set": a})
    kb = GR._resolver_key(cap, {"condition_set": b})
    assert ka != kb, "equal-length different condition sets still collide"

    ma = GR.resolution_map(cap, metrics=["goals"], condition_set=a)
    mb = GR.resolution_map(cap, metrics=["goals"], condition_set=b)
    assert ma is not mb
    assert set(ma) != set(mb), "the two maps hold identical ids -- the key is not separating"

    # canonical: reordering a condition dict's KEYS must NOT change the fingerprint
    c = [[{"value": "HOME", "dimension": "historical_venue_conditioning"}]]
    assert GR._resolver_key(cap, {"condition_set": c}) == ka

    # and metrics order must not matter either
    k1 = GR._resolver_key(cap, {"metrics": ["goals", "yellow_cards"]})
    k2 = GR._resolver_key(cap, {"metrics": ["yellow_cards", "goals"]})
    assert k1 == k2


def test_search_reachability_is_total(golden_universe):
    """P1 SEARCH-REACHABILITY: every evaluable candidate must be reachable by paginating."""
    rep = UNI.reachability_report(golden_universe)
    assert rep["unreachable_candidate_count"] == 0, rep["unreachable_sample"]
    assert rep["n_reachable"] == rep["n_evaluable"] == golden_universe.n_evaluable


def test_pagination_exceeds_the_page_cap(golden_universe):
    """The defect was a 50-cap with no cursor. Prove pagination genuinely goes past it."""
    assert golden_universe.n_evaluable > UNI.PAGE_SIZE_CAP, (
        "fixture too small to exercise pagination")
    first = UNI.search_evaluable(UNI.SearchQuery(max_results=UNI.PAGE_SIZE_CAP),
                                 golden_universe)
    assert len(first["results"]) == UNI.PAGE_SIZE_CAP
    assert first["cursor"] is not None and first["n_remaining"] > 0
    ids = UNI.paginate_all(UNI.SearchQuery(max_results=UNI.PAGE_SIZE_CAP), golden_universe)
    assert len(ids) == len(set(ids)) == golden_universe.n_evaluable


def test_pagination_is_deterministic(golden_universe):
    a = UNI.paginate_all(UNI.SearchQuery(max_results=UNI.PAGE_SIZE_CAP), golden_universe)
    b = UNI.paginate_all(UNI.SearchQuery(max_results=UNI.PAGE_SIZE_CAP), golden_universe)
    assert a == b


def test_llm_facing_projection_hides_support_statistics(golden_universe):
    """P1 MEASSPACE: Sonnet must not see raw_n/effective_n or the endpoint measures
    sample-size shopping instead of football reasoning."""
    for c in golden_universe.evaluable[:50]:
        assert "pre_t" in c, "the internal projection must carry support statistics"
        lf = UNI.llm_facing(c)
        for k in UNI.SUPPORT_KEYS:
            assert k not in lf, f"{k} leaked into the Sonnet-facing view"
        UNI.assert_llm_safe(lf)


def test_llm_facing_projection_RETAINS_every_structural_field(golden_universe):
    """THE LIVE CONTROL for MEASSPACE.

    The hiding test only asserts ABSENCE, so a projection that stripped everything would pass
    it. Sonnet must still receive every structural field the arms reason and match on --
    otherwise the treatment arm is answering a poorer question than R and H.
    """
    required = ("hypothesis_id", "structural_description", "target_metrics", "subject",
                "side", "comparator", "window", "conditions", "complexity",
                "research_family", "capability_status")
    for c in golden_universe.evaluable[:25]:
        lf = UNI.llm_facing(c)
        for k in required:
            assert k in lf, f"{k} was stripped from the Sonnet-facing view"
        assert lf["complexity"] == c["complexity"]
        assert lf["conditions"] == c["conditions"]
        assert lf["hypothesis_id"] == c["hypothesis_id"]


def test_search_results_are_llm_facing_by_default(golden_universe):
    page = UNI.search_evaluable(UNI.SearchQuery(max_results=5), golden_universe)
    for c in page["results"]:
        assert "pre_t" not in c
    page_i = UNI.search_evaluable(UNI.SearchQuery(max_results=5), golden_universe,
                                  internal=True)
    for c in page_i["results"]:
        assert "pre_t" in c


def test_competition_admissibility_is_enforced(golden_env):
    """A RESTRICTED metric must not enter the universe at a competition it does not cover."""
    cap = golden_env.capability
    # Must be a RESTRICTED metric the synthetic environment can actually populate, i.e. one
    # in the base block. `xg` is RESTRICTED (not admissible in laliga2/ligue2) and is base.
    from src.research.hypothesis_v8c import golden as GOLD
    restricted = [m for m in GOLD.GOLDEN_METRICS
                  if cap.classify_metric(m)[0] == CAP.RESTRICTED]
    assert restricted, "no RESTRICTED base-block metric available to test the gate"
    m = restricted[0]
    adm = set(cap.admissible_competitions(m))
    bad = [c for c in cap.competitions if c not in adm]
    assert bad, f"{m} is admissible everywhere; cannot test the gate"

    env = G_build(metrics=(m,), target_competition=bad[0])
    from src.research.hypothesis_v8c import pit_context as PC
    ctx = PC.build_pit_context(env.index, env.target_pos)
    fu = UNI.build_fixture_universe(env.index, env.target_pos, ctx=ctx,
                                    capability=env.capability,
                                    fixture_id=env.target_fixture_id,
                                    grammar_kwargs={"metrics": [m]})
    assert fu.n_evaluable == 0, (
        f"{m} entered the selectable universe at {bad[0]} where it is not admissible")
    assert fu.status_counts.get(PT.PRE_T_PROVIDER_UNSUPPORTED, 0) > 0


def G_build(**kw):
    from src.research.hypothesis_v8c import golden as G
    return G.build_environment(**kw)
