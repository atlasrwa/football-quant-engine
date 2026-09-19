"""LLM_MATCHUP_V3_SONNET46 arm: isolation, cache-separation and audit-sensitivity tests.

OFFLINE. Every test here is deterministic and makes ZERO Bedrock calls -- the adapter is
exercised with a monkeypatched `_invoke_converse`, never the real network. Running this file
must never spend tokens and must never touch a Sonnet 4.5 artifact.

Coverage:
  * the 4.6 manifest inherits the 4.5 fixture selection verbatim (same fixture_manifest_hash);
  * the 4.6 generation fingerprint differs from 4.5 in EXACTLY {bedrock_model_id, version_stamp};
  * CACHE SEPARATION (mandate SS8): a 4.6 call for a fixture already cached under 4.5 performs
    a genuine 4.6 inference and never returns the 4.5 cached response;
  * the cache key binds model identity, and a mislabelled cache entry is refused;
  * the 4.5 resume harness refuses a 4.6 manifest (fail-closed cross-generation guard);
  * PRE-SPEND AUDIT SENSITIVITY: each of the seven zero-tolerance categories actually FIRES on
    a deliberately poisoned packet -- a gate that cannot fail proves nothing.

Run: .venv/bin/python -m pytest tests/research/test_golden_v3_sonnet46.py -q
"""
import copy
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu")
import pytest

from src.research.llm_matchup.hardening import adapter_v4 as A4
from src.research.llm_matchup.hardening import audit_prespend as AP
from src.research.llm_matchup.hardening import golden_manifest as GM
from src.research.llm_matchup.hardening import golden_v3_sonnet46 as G46
from src.research.llm_matchup.hardening import neutralize_v3 as NZ3
from src.research.llm_matchup.hardening import resume_golden_v3 as RG
from src.research.llm_matchup.hardening import versions_v3 as V45
from src.research.llm_matchup.hardening import versions_v3_sonnet46 as V46


# --------------------------------------------------------------- tiny synthetic packet
def _minimal_neutral_packet(fixture_id="mt_test_1"):
    """A minimal packet that satisfies neutralize_v3.is_neutralized, for adapter-level tests
    that never reach the network. Not a scientific packet -- a plumbing fixture."""
    return {
        "packet_kind": NZ3.PACKET_KIND,
        "packet_schema_version": V45.PACKET_SCHEMA_VERSION,
        "source_evidence_packet_hash": "src" + "0" * 61,
        "neutral_llm_packet_hash": "neu" + "0" * 61,
        "packet_hash": "neu" + "0" * 61,
        "fixture": {"fixture_id": fixture_id, "home": "TEAM_A", "away": "TEAM_B",
                    "competition": "COMP_NEUTRAL", "season": "SEASON_NEUTRAL",
                    "kickoff_unix": 1711980000},
        "information_cutoff_unix": 1711980000,
        "evidence": [{"id": "A_ATK_crosses_for_aaa111", "metric": "crosses_for",
                      "value": 5.0, "sample_n": 19,
                      "scope": {"team": "TEAM_A", "opponent": "TEAM_B", "venue": "home",
                                "side": "for"},
                      "reliability": "HIGH", "shrinkage_level": "DIRECT",
                      "evidence_level": "VENUE_OVERALL", "source_provider": "thestatsapi",
                      "source_field": "crosses", "cutoff_unix": 1711980000,
                      "temporal_status": "PIT_SAFE", "max_source_time_unix": None}],
        "unsupported_context": {}, "formation_context": {}, "data_quality": {},
        "provider_provenance": {"primary": "thestatsapi"},
    }


# --------------------------------------------------------------- manifest inheritance
def test_46_manifest_inherits_45_fixture_selection_verbatim():
    frozen45 = GM.load_manifest(G46.SONNET45_MANIFEST_PATH)
    assert frozen45 is not None, "frozen 4.5 manifest must exist"
    m46 = G46.build_or_load_manifest()
    assert m46["generation_id"] == V46.GENERATION_ID
    assert m46["fixture_ids"] == frozen45["fixture_ids"]          # same ids, same ORDER
    assert m46["fixture_manifest_hash"] == frozen45["fixture_manifest_hash"]
    assert m46["n_fixtures"] == frozen45["n_fixtures"] == 20


def test_46_fingerprint_differs_from_45_in_exactly_model_and_generation_id():
    d = G46.manifest_vs_45_fingerprint_diff()
    assert set(d["differing_fields"]) == {"bedrock_model_id", "version_stamp"}
    # and within version_stamp, ONLY generation_id may differ
    a, b = V45.version_stamp(), V46.version_stamp()
    differing = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
    assert differing == {"generation_id"}
    # the scientific content inputs must be byte-identical
    for f in ("prompt_content_hash", "schema_content_hash", "ontology_content_hash",
              "neutralization_module_hash", "formation_structure_hash", "sampling_module_hash",
              "bedrock_region", "inference_config"):
        assert f in d["identical_fields"], f


def test_46_model_id_is_the_verified_sonnet46_profile():
    assert V46.DEFAULT_BEDROCK_MODEL_ID == "us.anthropic.claude-sonnet-4-6"
    assert V46.DEFAULT_BEDROCK_MODEL_ID != V45.DEFAULT_BEDROCK_MODEL_ID
    assert V46.GENERATION_ID == "LLM_MATCHUP_V3_SONNET46"


# --------------------------------------------------------------- cache separation (SS8)
def test_cache_key_binds_model_identity():
    """Same packet, same generation stamp, different model id => different cache key."""
    k45 = A4._cache_key(V45.DEFAULT_BEDROCK_MODEL_ID, "packethash", 0, gen=V45)
    k46_same_gen = A4._cache_key(V46.DEFAULT_BEDROCK_MODEL_ID, "packethash", 0, gen=V45)
    k46 = A4._cache_key(V46.DEFAULT_BEDROCK_MODEL_ID, "packethash", 0, gen=V46)
    assert k45 != k46_same_gen, "model id alone must change the cache key"
    assert k45 != k46 and k46_same_gen != k46


def test_46_call_does_not_return_45_cached_response(tmp_path, monkeypatch):
    """MANDATE SS8, THE CRITICAL TEST. Seed a 4.5 cache entry for a packet, then request the
    SAME packet as 4.6. The 4.6 call must perform a genuine inference and must NOT return the
    4.5 payload."""
    cache45 = tmp_path / "cache45"
    cache46 = tmp_path / "cache46"
    cache45.mkdir()
    cache46.mkdir()
    packet = _minimal_neutral_packet()

    invocations = []

    def fake_converse(client, model_id, system, user, tool_schema):
        invocations.append(model_id)
        return {
            "usage": {"inputTokens": 111, "outputTokens": 222},
            "output": {"message": {"content": [{"toolUse": {"input": {
                "MARKER": model_id}}}]}},
        }

    monkeypatch.setattr(A4, "_bedrock_client", lambda region: object())
    monkeypatch.setattr(A4, "_invoke_converse", fake_converse)
    # bypass the real validator so this test isolates CACHE behavior, not schema behavior
    monkeypatch.setattr(A4.VV3, "validate_v3", lambda raw, pkt, stamp: raw)

    r45 = A4.analyze_matchup_v4(packet, gen=V45, cache_dir=str(cache45))
    assert r45.status == "OK"
    assert r45.state["MARKER"] == V45.DEFAULT_BEDROCK_MODEL_ID
    assert invocations == [V45.DEFAULT_BEDROCK_MODEL_ID]

    # a repeat 4.5 call IS served from the 4.5 cache (no new inference)
    r45b = A4.analyze_matchup_v4(packet, gen=V45, cache_dir=str(cache45))
    assert r45b.manifest["cache_hit"] is True
    assert len(invocations) == 1, "4.5 repeat must be a cache hit"

    # now the SAME packet under 4.6 -> genuine NEW inference, 4.6 identity, no 4.5 payload
    r46 = A4.analyze_matchup_v4(packet, gen=V46, cache_dir=str(cache46))
    assert r46.status == "OK"
    assert r46.manifest["cache_hit"] is False, "4.6 must NOT be a cache hit"
    assert invocations == [V45.DEFAULT_BEDROCK_MODEL_ID, V46.DEFAULT_BEDROCK_MODEL_ID]
    assert r46.state["MARKER"] == V46.DEFAULT_BEDROCK_MODEL_ID
    assert r46.state["MARKER"] != r45.state["MARKER"]
    assert r46.manifest["model_id"] == V46.DEFAULT_BEDROCK_MODEL_ID
    assert r46.manifest["generation_id"] == V46.GENERATION_ID

    # and the two arms wrote to physically different namespaces
    assert len(list(cache45.glob("*.json"))) == 1
    assert len(list(cache46.glob("*.json"))) == 1
    k45 = json.load(open(next(iter(cache45.glob("*.json")))))
    k46 = json.load(open(next(iter(cache46.glob("*.json")))))
    assert k45["manifest"]["model_id"] == V45.DEFAULT_BEDROCK_MODEL_ID
    assert k46["manifest"]["model_id"] == V46.DEFAULT_BEDROCK_MODEL_ID


def test_46_call_would_not_hit_45_entry_even_in_a_shared_directory(tmp_path, monkeypatch):
    """Belt and braces: even if both arms were pointed at the SAME directory (which production
    code never does), the key binding alone keeps them separate."""
    shared = tmp_path / "shared"
    shared.mkdir()
    packet = _minimal_neutral_packet()
    calls = []

    def fake_converse(client, model_id, system, user, tool_schema):
        calls.append(model_id)
        return {"usage": {"inputTokens": 1, "outputTokens": 2},
                "output": {"message": {"content": [{"toolUse": {"input": {"M": model_id}}}]}}}

    monkeypatch.setattr(A4, "_bedrock_client", lambda region: object())
    monkeypatch.setattr(A4, "_invoke_converse", fake_converse)
    monkeypatch.setattr(A4.VV3, "validate_v3", lambda raw, pkt, stamp: raw)

    A4.analyze_matchup_v4(packet, gen=V45, cache_dir=str(shared))
    r46 = A4.analyze_matchup_v4(packet, gen=V46, cache_dir=str(shared))
    assert r46.manifest["cache_hit"] is False
    assert calls == [V45.DEFAULT_BEDROCK_MODEL_ID, V46.DEFAULT_BEDROCK_MODEL_ID]
    assert len(list(shared.glob("*.json"))) == 2, "two distinct entries, no overwrite"


def test_mislabelled_cache_entry_is_refused(tmp_path):
    """A hand-edited/misplaced cache file claiming another model must never be served."""
    d = tmp_path / "c"
    d.mkdir()
    key = A4._cache_key(V46.DEFAULT_BEDROCK_MODEL_ID, "ph", 0, gen=V46)
    A4._save_cache(key, {"status": "OK", "state": {},
                         "manifest": {"model_id": V45.DEFAULT_BEDROCK_MODEL_ID}}, str(d))
    with pytest.raises(A4.CacheModelIdentityError):
        A4._load_cache(key, str(d), expect_model_id=V46.DEFAULT_BEDROCK_MODEL_ID)
    # same file is fine when the requested model matches
    assert A4._load_cache(key, str(d),
                          expect_model_id=V45.DEFAULT_BEDROCK_MODEL_ID) is not None


# --------------------------------------------------------------- cross-generation guard
def test_45_resume_refuses_a_46_manifest(tmp_path, monkeypatch):
    """Tomorrow's 4.5 resume must abort rather than consume a 4.6 manifest (mandate SS2)."""
    mpath = tmp_path / "m.json"
    # GM.OUT must be redirected too: resume() takes the live-runner lock (resolved from GM.OUT)
    # before it reaches the generation-id check, so without this the test writes a real lock
    # file into the production out/hardening_v3/ directory.
    monkeypatch.setattr(GM, "OUT", str(tmp_path))
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(mpath))
    monkeypatch.setattr(RG, "LEDGER_PATH", str(tmp_path / "ledger.json"))
    m46 = GM.build_manifest(["mt_1", "mt_2"], n=2, max_scan=50, gen=V46)
    json.dump(m46, open(mpath, "w"))

    calls = []
    out = RG.resume(call_fn=lambda *a, **k: calls.append(1))
    assert out["status"] == "ABORT_GENERATION_ID_MISMATCH"
    assert out["manifest_generation_id"] == V46.GENERATION_ID
    assert calls == [], "not a single call may be made against a foreign generation"


def test_45_resume_still_accepts_its_own_frozen_manifest():
    """The guard must not break the legitimate 4.5 resume path (which runs tomorrow)."""
    frozen45 = GM.load_manifest(G46.SONNET45_MANIFEST_PATH)
    sp = frozen45["generation_fingerprint"]["sampling_params"]
    cur = GM.current_generation_fingerprint(n=sp["n"], max_scan=sp["max_scan"], gen=V45)
    assert GM.check_compatible(frozen45, cur)["compatible"] is True
    assert frozen45["generation_id"] == V45.GENERATION_ID


def test_load_manifest_default_resolves_at_call_time(tmp_path, monkeypatch):
    """Regression guard for the bug that contaminated the real 4.5 ledger: monkeypatching
    GM.MANIFEST_PATH MUST affect load_manifest()."""
    monkeypatch.setattr(GM, "MANIFEST_PATH", str(tmp_path / "definitely_absent.json"))
    assert GM.load_manifest() is None


# --------------------------------------------------------------- audit sensitivity
def test_prespend_audit_clean_on_correct_packet():
    p = _minimal_neutral_packet()
    src = {"fixture": {"fixture_id": "mt_test_1", "home": "Stoke City",
                       "away": "Huddersfield Town", "competition": "champ",
                       "season": "sn_343481"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is True, rep["categories"]
    assert rep["n_leaks_total"] == 0


def test_audit_fires_on_real_team_name():
    p = _minimal_neutral_packet()
    p["fixture"]["home"] = "Stoke City"                      # deliberate leak
    src = {"fixture": {"fixture_id": "mt_test_1", "home": "Stoke City", "away": "Huddersfield Town",
                       "competition": "champ", "season": "sn_343481"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["real_team_names"] >= 1


def test_audit_fires_on_real_competition_and_season():
    p = _minimal_neutral_packet()
    p["evidence"][0]["scope"]["season"] = "sn_343481"        # deliberate leak
    src = {"fixture": {"fixture_id": "mt_test_1", "home": "TEAM_ZZZ", "away": "TEAM_YYY",
                       "competition": "champ", "season": "sn_343481"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["real_competition_names"] >= 1


def test_audit_fires_on_human_readable_formation_label():
    p = _minimal_neutral_packet()
    p["evidence"][0]["scope"]["prematch_formation"] = "4-2-3-1"   # sums to 10 -> a real label
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["formation_labels"] >= 1


def test_audit_fires_on_family_label():
    p = _minimal_neutral_packet()
    p["evidence"][0]["scope"]["formation_family"] = "BACK4_1STRIKER"
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["formation_labels"] >= 1


def test_audit_does_not_false_positive_on_non_formation_hyphenated_numbers():
    """A hyphenated numeric whose digits do not sum to 10 is not a formation label."""
    p = _minimal_neutral_packet()
    p["evidence"][0]["source_field"] = "window_1-2"      # sums to 3, not a formation
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["counts"]["formation_labels"] == 0


def test_audit_fires_on_target_outcome_key():
    p = _minimal_neutral_packet()
    p["final_score"] = "2-1"
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["target_outcomes"] >= 1


def test_audit_fires_on_outcome_bearing_metric():
    p = _minimal_neutral_packet()
    p["evidence"][0]["metric"] = "actual_goals_scored"
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["target_outcomes"] >= 1


def test_audit_fires_on_future_information_value_on_unavailable_item():
    p = _minimal_neutral_packet()
    p["evidence"][0]["temporal_status"] = "UNAVAILABLE"
    p["evidence"][0]["value"] = 7.5                       # must not carry a measurement
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["future_information"] >= 1


def test_audit_fires_on_post_cutoff_source_time():
    p = _minimal_neutral_packet()
    p["evidence"][0]["max_source_time_unix"] = p["information_cutoff_unix"] + 3600
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["future_information"] >= 1


def test_audit_allows_declared_unavailable_item_with_null_value():
    """An UNAVAILABLE item may be DECLARED (that is honest closed-world reporting); it just
    must not carry a measurement."""
    p = _minimal_neutral_packet()
    p["evidence"][0]["temporal_status"] = "UNAVAILABLE"
    p["evidence"][0]["value"] = None
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["counts"]["future_information"] == 0


def test_audit_fires_on_credential_shape():
    p = _minimal_neutral_packet()
    p["evidence"][0]["source_field"] = "AKIAIOSFODNN7EXAMPLE"
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["credential_leakage"] >= 1
    # the report must NOT echo the secret value
    joined = json.dumps(rep["categories"]["credential_leakage"])
    assert "AKIAIOSFODNN7EXAMPLE" not in joined
    assert "redacted" in joined


def test_audit_fires_on_env_value_present_in_request(monkeypatch):
    monkeypatch.setenv("SOME_FAKE_SECRET", "z9y8x7w6v5u4t3s2r1q0")
    p = _minimal_neutral_packet()
    p["evidence"][0]["source_field"] = "z9y8x7w6v5u4t3s2r1q0"
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["credential_leakage"] >= 1
    assert "z9y8x7w6v5u4t3s2r1q0" not in json.dumps(rep["categories"]["credential_leakage"])


def test_audit_fires_on_arbitrary_provider_text():
    p = _minimal_neutral_packet()
    p["evidence"][0]["source_provider"] = (
        "Scraped from https://example.com/stats page 3. Note: values may be wrong!")
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["provider_text"] >= 1


def test_audit_fires_on_unknown_provider_slug():
    p = _minimal_neutral_packet()
    p["evidence"][0]["source_provider"] = "mystery_feed_v2"
    src = {"fixture": {"fixture_id": "mt_test_1"}, "evidence": []}
    rep = AP.audit_prespend(p, src)
    assert rep["clean"] is False
    assert rep["counts"]["provider_text"] >= 1


def test_audit_all_seven_categories_are_independently_reachable():
    """Every declared category must be provably firable; otherwise the 'all zero' result is
    not evidence of anything."""
    fired = set()
    src = {"fixture": {"fixture_id": "mt_test_1", "home": "Stoke City", "away": "Huddersfield Town",
                       "competition": "champ", "season": "sn_343481"}, "evidence": []}
    poisons = [
        ("real_team_names", lambda p: p["fixture"].__setitem__("home", "Stoke City")),
        ("real_competition_names",
         lambda p: p["evidence"][0]["scope"].__setitem__("competition", "champ")),
        ("formation_labels",
         lambda p: p["evidence"][0]["scope"].__setitem__("prematch_formation", "4-4-2")),
        ("target_outcomes", lambda p: p.__setitem__("winner", "TEAM_A")),
        ("future_information",
         lambda p: (p["evidence"][0].__setitem__("temporal_status", "UNAVAILABLE"),
                    p["evidence"][0].__setitem__("value", 1.0))),
        ("credential_leakage",
         lambda p: p["evidence"][0].__setitem__("source_field", "AKIAIOSFODNN7EXAMPLE")),
        ("provider_text",
         lambda p: p["evidence"][0].__setitem__("source_provider", "who knows where <weird>")),
    ]
    for cat, poison in poisons:
        p = _minimal_neutral_packet()
        poison(p)
        rep = AP.audit_prespend(p, src)
        assert rep["counts"][cat] >= 1, f"category {cat} failed to fire"
        fired.add(cat)
    assert fired == set(AP.audit_prespend(_minimal_neutral_packet(), src)["categories"])


# --------------------------------------------------------------- artifact separation
def test_46_paths_are_all_outside_the_45_namespace():
    forty_five_dir = "/home/ubuntu/research/llm_matchup/out/hardening_v3"
    for p in (G46.OUT, G46.CACHE_DIR, G46.MANIFEST_PATH, G46.LEDGER_PATH,
              G46.STATES_PATH, G46.SUMMARY_PATH, G46.PRESPEND_AUDIT_PATH):
        assert not os.path.abspath(p).startswith(forty_five_dir + os.sep), p
        assert "v3_sonnet46" in p, p
    # the ONLY 4.5 path the 4.6 arm may reference is the read-only manifest/states it inherits
    assert G46.SONNET45_MANIFEST_PATH.startswith(forty_five_dir)


def test_46_state_metrics_are_objective_and_have_no_smartness_score():
    state = {
        "team_a_states": [
            {"mechanism": "WIDTH_PRESSURE", "level": "MEDIUM",
             "evidence_ids": ["e1", "e2"], "counter_evidence_ids": ["e3"],
             "counter_evidence_search": "PERFORMED"},
            {"mechanism": "WIDTH_PRESSURE", "level": "UNKNOWN",
             "evidence_ids": [], "counter_evidence_ids": [],
             "counter_evidence_search": "SKIPPED"},
        ],
        "team_b_states": [],
        "matchup_states": [
            {"mechanism": "WIDE_PRESSURE_MATCHUP", "assessment": "CONFLICTED",
             "supporting_evidence_ids": ["e1"], "counter_evidence_ids": [],
             "counter_evidence_search": "PERFORMED"},
        ],
    }
    m = G46.state_metrics(state)
    assert m["n_mechanisms_total"] == 3
    assert m["n_unknown"] == 1 and m["n_conflicted"] == 1
    assert m["n_unsupported_mechanisms"] == 1          # the UNKNOWN one cites nothing
    assert m["n_redundant_mechanisms"] == 1            # WIDTH_PRESSURE twice in team_a
    assert m["support_evidence_total"] == 3
    assert m["counter_evidence_total"] == 1
    assert m["n_counter_evidence_search_performed"] == 2
    for banned in ("smartness", "score", "quality", "grade"):
        assert not any(banned in k for k in m), k


if __name__ == "__main__":
    import subprocess
    raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", __file__, "-q"]))



# --------------------------------------------------------------- eligibility gate
def test_failed_identity_gate_rejects_pending_surrogate():
    """A FAILED generation-level identity gate must force-reject everything otherwise usable,
    including the 4.6-only PENDING_SURROGATE class. Regression guard: the shared 4.5
    apply_identity_gate only knows PHASE_C_ELIGIBLE / REDUNDANT_WITH_DETERMINISTIC, so
    PENDING_SURROGATE silently escaped the gate until this was fixed."""
    from src.research.llm_matchup.hardening import eligibility_v3_sonnet46 as E46
    rows = [
        {"mechanism": "M1", "eligibility": "PENDING_SURROGATE"},
        {"mechanism": "M2", "eligibility": "PHASE_C_ELIGIBLE"},
        {"mechanism": "M3", "eligibility": "RESEARCH_ONLY_UNSTABLE"},
        {"mechanism": "M4", "eligibility": "INSUFFICIENT_COVERAGE"},
    ]
    gate = {"phase_c_eligible_generation": False, "reason": "NOT_PHASE_C_ELIGIBLE: test"}
    out = {r["mechanism"]: r for r in E46.apply_identity_gate(rows, gate)}
    assert out["M1"]["eligibility"] == "REJECTED"
    assert out["M1"]["pre_gate_eligibility"] == "PENDING_SURROGATE"   # preserved for audit
    assert out["M2"]["eligibility"] == "REJECTED"
    # classes that were never going to proceed are left untouched, so the cause stays legible
    assert out["M3"]["eligibility"] == "RESEARCH_ONLY_UNSTABLE"
    assert out["M4"]["eligibility"] == "INSUFFICIENT_COVERAGE"


def test_passing_identity_gate_is_a_noop():
    from src.research.llm_matchup.hardening import eligibility_v3_sonnet46 as E46
    rows = [{"mechanism": "M1", "eligibility": "PENDING_SURROGATE"}]
    out = E46.apply_identity_gate(rows, {"phase_c_eligible_generation": True})
    assert out[0]["eligibility"] == "PENDING_SURROGATE"
    assert "pre_gate_eligibility" not in out[0]


def test_no_sonnet46_mechanism_can_be_phase_c_eligible():
    """The surrogate ladder was not run for 4.6, so PHASE_C_ELIGIBLE must be unreachable."""
    from src.research.llm_matchup.hardening import eligibility_v3_sonnet46 as E46
    sig = {m: {"coverage": 99, "n_total": 10, "n_severe": 0, "n_stable": 10,
               "sensitivity_flag": "SENSITIVE_TO_EVIDENCE", "sensitivity_margin": 0.5,
               "surrogate_verdict": None, "surrogate_s1": None}
           for m in ("WIDTH_PRESSURE", "BOX_PRESSURE")}
    rows = E46.classify(sig)
    classes = {r["eligibility"] for r in rows}
    assert "PHASE_C_ELIGIBLE" not in classes
    assert "PENDING_SURROGATE" in classes
    for r in rows:
        if r["eligibility"] != "INSUFFICIENT_COVERAGE":
            assert r["surrogate_verdict"] == "NOT_RUN_FOR_SONNET46"


def test_eligibility_thresholds_are_imported_not_redefined():
    """The two arms must be judged by the SAME bar; the 4.6 module may not fork thresholds."""
    from src.research.llm_matchup.hardening import eligibility as EL
    from src.research.llm_matchup.hardening import eligibility_v3_sonnet46 as E46
    import inspect
    src = inspect.getsource(E46)
    for name in ("MIN_COVERAGE", "MAX_SEVERE_DISAGREE", "MIN_SEMANTIC_STABLE",
                 "MAX_IDENTITY_TRIP_RATE", "MIN_N_FOR_IDENTITY_GATE"):
        assert f"{name} =" not in src, f"{name} must not be redefined in the 4.6 module"
    assert EL.MAX_IDENTITY_TRIP_RATE == 0.20
    assert EL.MIN_N_FOR_IDENTITY_GATE == 5


# --------------------------------------------------------------- controls semantics
def test_control_verdict_inequality_is_strictly_greater():
    """The repo's implementation is authoritative: FAIL iff trip_rate > 0.20, so exactly 0.20
    PASSES. (The task prose said >=; the code says >. Code wins.)"""
    from src.research.llm_matchup.hardening import eligibility as EL
    assert EL._control_verdict({"n": 10, "trip_rate": 0.20})["status"] == "PASS"
    assert EL._control_verdict({"n": 10, "trip_rate": 0.2001})["status"] == "FAIL"


def test_control_verdict_fails_closed_on_thin_evidence():
    from src.research.llm_matchup.hardening import eligibility as EL
    v = EL._control_verdict({"n": 4, "trip_rate": 0.0})
    assert v["status"] == "INCONCLUSIVE", "n below MIN_N must never be reported as PASS"


def test_degenerate_near_constant_flag_logic():
    """Identity invariance with NO response to genuine evidence must be flagged, not praised."""
    import json as _json
    import os as _os
    from src.research.llm_matchup.hardening import controls_v3_sonnet46 as C46
    if not _os.path.exists(C46.CONTROLS_PATH):
        pytest.skip("controls artifact not present")
    c = _json.load(open(C46.CONTROLS_PATH))
    interp = c["interpretation"]
    abl = c["controls"]["D_behavior_sensitivity_formation_ablation"]
    team = c["controls"]["A_team_token_invariance"]
    expected = bool(abl["trip_rate"] == 0 and team["trip_rate"] == 0)
    assert interp["degenerate_near_constant"] == expected
