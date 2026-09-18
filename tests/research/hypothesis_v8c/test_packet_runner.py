"""Raw packet fidelity, packet purity (serial vs parallel), runner wiring and cache isolation."""
from __future__ import annotations

import concurrent.futures

import pytest

from src.research.hypothesis_v71 import engine as ENG
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v8c import cache as CACHE
from src.research.hypothesis_v8c import packet as PK
from src.research.hypothesis_v8c import runner as RUN
from src.research.hypothesis_v8c import universe as UNI

from .conftest import GRAMMAR_KW


def _recency():
    ir = IRM.build_ir({"target_metrics": ["goals"], "subject": "HOME_TEAM", "side": "FOR",
                       "comparison": "SUBJECT_RECENT_VS_LONG_BASELINE", "window": "ALL_PRIOR",
                       "conditions": [], "research_family": "T", "required_capabilities": []})
    return ENG.recency_family_for(ir)


@pytest.fixture(scope="module")
def pkt(golden_env, golden_ctx):
    return PK.build_packet(golden_env.index, golden_env.target_pos, golden_env.capability,
                           golden_ctx, _recency())


# ---- raw packet fidelity -----------------------------------------------------------------
def test_raw_rows_are_match_level_not_summaries(pkt):
    """The V8B.1 defect: `raw_rows` were per-metric aggregates."""
    rows = pkt["team_a"]["raw_rows"]
    assert rows, "no raw rows emitted"
    r = rows[0]
    assert set(r) >= {"kickoff_unix", "competition", "venue", "opponent_id", "metrics"}
    assert r["venue"] in ("HOME", "AWAY")
    assert r["opponent_id"]
    for _m, v in r["metrics"].items():
        assert set(v) == {"for", "against"}, "a raw row must carry both perspectives"


def test_raw_rows_are_bounded_and_deterministic(pkt):
    for side in ("team_a", "team_b"):
        assert len(pkt[side]["raw_rows"]) <= PK.MAX_RAW_ROWS_PER_TEAM
    ks = [r["kickoff_unix"] for r in pkt["team_a"]["raw_rows"]]
    assert ks == sorted(ks, reverse=True), "raw rows must be most-recent-first"


def test_raw_rows_are_strictly_pit(golden_env, pkt):
    tk = int(golden_env.index.kick[golden_env.target_pos])
    PK.assert_no_target_leak(pkt, golden_env.target_fixture_id, tk)
    for side in ("team_a", "team_b"):
        for r in pkt[side]["raw_rows"]:
            assert r["kickoff_unix"] < tk


def test_navigation_summaries_retained_separately(pkt):
    assert pkt["team_a"]["navigation_summaries"]
    row = pkt["team_a"]["navigation_summaries"][0]
    assert "metric" in row and "for" in row and "against" in row


def test_recent_vs_long_covers_both_perspectives(pkt):
    """V8B.1 computed FOR only, so every defensive question read attacking form."""
    rvl = pkt["team_a"]["recent_vs_long"]
    assert rvl
    for _m, block in rvl.items():
        assert set(block) == {"for", "against"}


def test_packet_carries_no_target_statistics(pkt, golden_env):
    assert pkt["reads_target_outcome"] is False
    assert pkt["target_formation"] == "FORMATION_UNKNOWN"
    assert pkt["information_cutoff_unix"] == int(golden_env.index.kick[golden_env.target_pos])


# ---- purity: the _REF_POS global is gone --------------------------------------------------
def test_packet_module_has_no_mutable_global():
    assert not hasattr(PK, "_REF_POS"), "the mutable module-level reference cell survives"
    assert PK.version_stamp()["mutable_module_global"] is False


def test_serial_and_parallel_builds_are_identical(golden_env, golden_ctx):
    """The V8B.1 `_REF_POS` race: two interleaved builds could stamp each other's position."""
    rec = _recency()
    positions = [golden_env.target_pos] * 6

    serial = [PK.build_packet(golden_env.index, p, golden_env.capability, golden_ctx, rec)
              ["packet_hash"] for p in positions]

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        parallel = list(ex.map(
            lambda p: PK.build_packet(golden_env.index, p, golden_env.capability,
                                      golden_ctx, rec)["packet_hash"], positions))

    assert len(set(serial)) == 1, "serial builds of the same fixture disagree"
    assert serial == parallel, "parallel packet builds diverge -- construction is not pure"


# ---- runner wiring -------------------------------------------------------------------------
def test_runner_search_answers_from_the_v8c_universe(golden_universe, golden_env):
    def selector(session):
        page = session.search({"max_results": 10})
        return [c["hypothesis_id"] for c in page["results"][:3]]

    res = RUN.run_fixture(golden_universe, golden_env.capability, selector=selector,
                          grammar_kwargs=GRAMMAR_KW)
    assert res["status"] == RUN.OK
    assert len(res["valid"]) == 3
    universe_ids = set(golden_universe.evaluable_ids())
    for hid in res["valid"]:
        assert hid in universe_ids


def test_runner_does_not_use_v8b1_search():
    assert RUN.version_stamp()["uses_v8b1_search"] is False
    assert RUN.version_stamp()["search_tool_source"].startswith("hypothesis_v8c")


def test_runner_search_results_hide_support_statistics(golden_universe, golden_env):
    seen = []

    def selector(session):
        page = session.search({"max_results": 10})
        seen.extend(page["results"])
        return []

    RUN.run_fixture(golden_universe, golden_env.capability, selector=selector,
                    grammar_kwargs=GRAMMAR_KW)
    assert seen
    for c in seen:
        for k in UNI.SUPPORT_KEYS:
            assert k not in c


def test_runner_rejects_an_id_never_returned_this_session(golden_universe, golden_env):
    """An id the model invented -- or remembered -- must be an explicit terminal state."""
    real = golden_universe.evaluable[0]["hypothesis_id"]

    def selector(session):
        session.search({"max_results": 5})
        return [real]          # real id, but NOT necessarily returned by that 5-result page

    res = RUN.run_fixture(golden_universe, golden_env.capability, selector=selector,
                          grammar_kwargs=GRAMMAR_KW)
    if real not in {c["hypothesis_id"] for c in
                    UNI.search_evaluable(UNI.SearchQuery(max_results=5),
                                         golden_universe)["results"]}:
        assert res["status"] == RUN.INVALID_ID_NOT_RETURNED_THIS_SESSION
        assert res["invalid"][0]["status"] == RUN.INVALID_ID_NOT_RETURNED_THIS_SESSION


def test_runner_rejects_a_fabricated_id(golden_universe, golden_env):
    def selector(session):
        session.search({"max_results": 10})
        return ["mt_COMPLETELY_INVENTED"]

    res = RUN.run_fixture(golden_universe, golden_env.capability, selector=selector,
                          grammar_kwargs=GRAMMAR_KW)
    assert res["status"] == RUN.INVALID_ID_NOT_RETURNED_THIS_SESSION
    assert res["research_yield"] == {"submitted": 1, "valid": 0, "invalid": 1}
    assert res["valid"] == []


def test_runner_abstention_is_valid(golden_universe, golden_env):
    res = RUN.run_fixture(golden_universe, golden_env.capability,
                          selector=lambda s: [], grammar_kwargs=GRAMMAR_KW)
    assert res["status"] == RUN.OK_ABSTAIN
    assert res["research_yield"]["submitted"] == 0


def test_runner_search_budget_is_a_true_cap(golden_universe, golden_env):
    def selector(session):
        for _ in range(RUN.MAX_SEARCH_CALLS + 4):
            session.search({"max_results": 5})
        return []

    res = RUN.run_fixture(golden_universe, golden_env.capability, selector=selector,
                          grammar_kwargs=GRAMMAR_KW)
    assert res["search_calls_used"] == RUN.MAX_SEARCH_CALLS
    exhausted = [c for c in res["search_trace"] if c["status"] == RUN.SEARCH_BUDGET_EXHAUSTED]
    assert len(exhausted) == 4


# ---- cache isolation ------------------------------------------------------------------------
def test_v8c_cache_namespace_is_separate_from_v8b1():
    ev = CACHE.assert_isolated_from_v8b1()
    assert ev["directories_distinct"] is True
    assert ev["namespace"] == "v8c"


def test_cache_identity_binds_every_task_determining_input(golden_universe):
    ident = RUN.cache_identity_for(
        fixture_universe=golden_universe, pit_context_hash="ctx", packet_hash="pkt",
        prompt_hash="pr", model_id="m", resolved_model_id="m-resolved",
        model_config_stamp={"temperature": 1.0})
    for f in CACHE.IDENTITY_FIELDS:
        assert ident.get(f), f"cache identity is missing {f}"
    assert ident["cache_namespace"] == "v8c"


def test_v8b1_style_cache_entry_is_refused(golden_universe, tmp_path, monkeypatch):
    """A V8B.1 entry must be incapable of satisfying a V8C request."""
    monkeypatch.setattr(CACHE, "CACHE_DIR", str(tmp_path))
    ident = RUN.cache_identity_for(
        fixture_universe=golden_universe, pit_context_hash="ctx", packet_hash="pkt",
        prompt_hash="pr", model_id="m", resolved_model_id="m-resolved",
        model_config_stamp={"temperature": 1.0})
    CACHE.save(ident, {"final_selections": ["a"]})
    assert CACHE.load(ident) is not None          # same identity -> served

    # a V8B.1-era entry: same model/prompt/packet, but a different universe
    poisoned = dict(ident)
    poisoned["fixture_universe_hash"] = "v8b1-era-universe"
    assert CACHE.load(poisoned) is None           # different key -> simply absent

    # and an entry whose stored identity disagrees is REFUSED, not served
    key = CACHE.cache_key(ident)
    import json
    body = json.load(open(CACHE.cache_path(key)))
    body["cache_identity"]["search_version"] = "v8b1_search_v1"
    json.dump(body, open(CACHE.cache_path(key), "w"), indent=1, sort_keys=True)
    with pytest.raises(CACHE.CacheIdentityError):
        CACHE.load(ident)


def test_cache_refuses_a_foreign_namespace(golden_universe, tmp_path, monkeypatch):
    monkeypatch.setattr(CACHE, "CACHE_DIR", str(tmp_path))
    ident = RUN.cache_identity_for(
        fixture_universe=golden_universe, pit_context_hash="c", packet_hash="p",
        prompt_hash="pr", model_id="m", resolved_model_id="mr",
        model_config_stamp={})
    CACHE.save(ident, {"x": 1})
    import json
    key = CACHE.cache_key(ident)
    body = json.load(open(CACHE.cache_path(key)))
    body["cache_identity"]["cache_namespace"] = "v8b1"
    json.dump(body, open(CACHE.cache_path(key), "w"), indent=1, sort_keys=True)
    with pytest.raises(CACHE.CacheIdentityError):
        CACHE.load(ident)
