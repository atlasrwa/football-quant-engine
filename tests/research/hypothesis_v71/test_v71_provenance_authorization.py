"""V7.1 execution-closure mission -- provenance & authorization (items 2, 5, 6, 7).

Negative-control mutation tests: each guard must FIRE on a load-bearing mutation and must NOT
fire on the unchanged apparatus (a guard that rejects everything is vacuous). Nothing here
reads a confirmatory outcome; the fresh corpus is never opened for an effect.
"""
from __future__ import annotations

import copy
import json
import os
import tempfile

from src.research.hypothesis_v71 import authorization as AUTH
from src.research.hypothesis_v71 import provenance as PV

OUT = "/home/ubuntu/research/hypothesis_oos/out/v7_1"
ENTRY = ("research/hypothesis_engine/_v71_execute.py",
         "src/research/hypothesis_v71/execution.py")


# ---- source graph --------------------------------------------------------------------
def test_06_source_graph_matches_the_frozen_commitment():
    prov = json.load(open(f"{OUT}/V7_1_PROVENANCE.json"))
    ok, problems, _live = PV.verify_source_graph(prov["source_graph"])
    assert ok, problems


def test_06_source_graph_includes_the_executor_and_execution_module():
    sg = PV.source_graph_commitment(list(ENTRY))
    files = set(sg["source_file_hashes"])
    assert "research/hypothesis_engine/_v71_execute.py" in files
    assert "src/research/hypothesis_v71/execution.py" in files
    # reused V7 primitives on the closure are bound too
    assert "src/research/hypothesis_v7/pit.py" in files
    assert sg["n_source_files"] >= 15


def test_06_a_source_change_after_freeze_refuses_even_without_a_version_bump():
    """The negative control for the source-graph guard: mutate one file's bytes and prove the
    verification fails, WITHOUT touching any version constant."""
    prov = json.load(open(f"{OUT}/V7_1_PROVENANCE.json"))["source_graph"]
    mutated = copy.deepcopy(prov)
    # flip one hash as if execution.py's bytes changed while its version string did not
    key = "src/research/hypothesis_v71/execution.py"
    mutated["source_file_hashes"][key] = "0" * 64
    ok, problems, _live = PV.verify_source_graph(mutated)
    assert not ok
    assert any("execution.py" in p for p in problems)


def test_06_a_new_module_on_the_closure_is_detected():
    prov = json.load(open(f"{OUT}/V7_1_PROVENANCE.json"))["source_graph"]
    mutated = copy.deepcopy(prov)
    del mutated["source_file_hashes"]["src/research/hypothesis_v71/execution.py"]
    ok, problems, _live = PV.verify_source_graph(mutated)
    assert not ok
    assert any("added to the executable closure" in p for p in problems)


# ---- upstream V7 ---------------------------------------------------------------------
def test_07_upstream_v7_matches_the_frozen_commitment():
    prov = json.load(open(f"{OUT}/V7_1_PROVENANCE.json"))
    ok, problems, _live = PV.verify_upstream_v7(prov["upstream_v7"])
    assert ok, problems


def test_07_upstream_change_refuses_even_if_the_proof_file_is_unchanged():
    """The exact D-class this guard exists for: the immutability PROOF summary can be identical
    while a file it references changed. We hash the referenced files, so a changed input fails
    regardless of the proof."""
    prov = json.load(open(f"{OUT}/V7_1_PROVENANCE.json"))["upstream_v7"]
    mutated = copy.deepcopy(prov)
    some = next(iter(mutated["upstream_input_hashes"]))
    mutated["upstream_input_hashes"][some] = "0" * 64
    ok, problems, _live = PV.verify_upstream_v7(mutated)
    assert not ok
    assert any(some in p for p in problems)


# ---- fresh content -------------------------------------------------------------------
def test_07_fresh_content_same_ids_different_values_is_refused():
    """A fixture-id-only freeze would pass this; the content commitment must not. We commit the
    real fresh set, then mutate ONE record's provider payload (same fixture id, different
    values) and prove verify_content refuses while the id set is unchanged."""
    import dataclasses

    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import freshsample as FS

    recs = CI.load_records(include_fresh=True)
    _dev, conf = FS.partition(recs)
    frozen = PV.content_commitment(conf, CAP.METRIC_SEMANTICS)

    # mutate a consumable provider field on exactly one record, keeping its fixture id
    mutated_conf = list(conf)
    target = mutated_conf[0]
    new_base = dict(target.base or {})
    # pick any base metric field and perturb it
    fld = next((r["field"] for r in CAP.METRIC_SEMANTICS.values()
                if r.get("block") == "base" and r.get("field") in new_base), None)
    assert fld is not None, "no base field to perturb: test would be vacuous"
    old = new_base[fld]
    new_base[fld] = (old or 0) + 999.0
    mutated_conf[0] = dataclasses.replace(target, base=new_base)

    ok, problems, _live = PV.verify_content(frozen, mutated_conf, CAP.METRIC_SEMANTICS)
    assert not ok, "same ids with different values passed content verification"
    assert any("different content" in p for p in problems), problems
    # and the id set really is identical, so a fixture-id-only freeze WOULD have passed
    assert {str(r.fixture_id) for r in conf} == {str(r.fixture_id) for r in mutated_conf}


def test_07_unchanged_fresh_content_passes_verification():
    """Positive control: the unchanged fresh set verifies, so the guard is not vacuous."""
    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import freshsample as FS
    recs = CI.load_records(include_fresh=True)
    _dev, conf = FS.partition(recs)
    frozen = PV.content_commitment(conf, CAP.METRIC_SEMANTICS)
    ok, problems, _live = PV.verify_content(frozen, conf, CAP.METRIC_SEMANTICS)
    assert ok, problems


def test_07_content_commitment_preserves_nulls_and_is_deterministic():
    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import freshsample as FS
    recs = CI.load_records(include_fresh=True)
    _dev, conf = FS.partition(recs)
    a = PV.content_commitment(conf, CAP.METRIC_SEMANTICS)
    b = PV.content_commitment(conf, CAP.METRIC_SEMANTICS)
    assert a["content_sha256"] == b["content_sha256"], "content commitment is not deterministic"
    assert a["n_records"] == len(conf)
    assert a["level"] == "NORMALIZED_RECORD_CONTENT"


# ---- authorization -------------------------------------------------------------------
def _expected():
    return AUTH.build_expected(experiment="V7_1_HARDENED_HYPOTHESIS_VALIDATION",
                               freeze_manifest_sha256="fm", source_graph_sha256="sg",
                               upstream_sha256="up", fresh_content_sha256="fc")


def _valid_token():
    return {"authorization_version": AUTH.AUTHORIZATION_VERSION,
            "authorize_confirmatory_oos": True,
            "bindings": {"experiment": "V7_1_HARDENED_HYPOTHESIS_VALIDATION",
                         "freeze_manifest_sha256": "fm", "source_graph_sha256": "sg",
                         "upstream_sha256": "up", "fresh_content_sha256": "fc"}}


def test_05_absent_token_is_not_authorized():
    v = AUTH.verify(None, _expected())
    assert v["authorized"] is False and v["present"] is False


def test_05_a_correctly_bound_token_authorizes():
    """Positive control: a token that binds exactly the live hashes IS accepted -- otherwise
    the gate could never be opened and the negative controls would be vacuous. (This token is
    synthetic and is never written to disk during the mission.)"""
    v = AUTH.verify(_valid_token(), _expected())
    assert v["authorized"] is True, v["problems"]


def test_05_token_bound_to_a_different_freeze_is_refused():
    t = _valid_token()
    t["bindings"]["freeze_manifest_sha256"] = "DIFFERENT"
    v = AUTH.verify(t, _expected())
    assert not v["authorized"]
    assert any("freeze_manifest_sha256" in p for p in v["problems"])


def test_05_token_bound_to_different_code_is_refused():
    t = _valid_token()
    t["bindings"]["source_graph_sha256"] = "DIFFERENT"
    v = AUTH.verify(t, _expected())
    assert not v["authorized"]
    assert any("source_graph_sha256" in p for p in v["problems"])


def test_05_token_without_explicit_authorization_flag_is_refused():
    t = _valid_token()
    t["authorize_confirmatory_oos"] = False
    v = AUTH.verify(t, _expected())
    assert not v["authorized"]
    assert any("does not explicitly authorize" in p for p in v["problems"])


def test_05_the_authorization_artifact_does_not_exist_during_the_mission():
    """The one-way door: the token file must be ABSENT at the end of this mission."""
    assert not os.path.exists(f"{OUT}/{AUTH.AUTHORIZATION_ARTIFACT}"), (
        "the confirmatory authorization artifact exists -- the one-way door is not shut")


def test_05_opening_the_door_later_needs_no_code_change():
    """A token minted against the LIVE bindings (whatever they are at that later time) is
    accepted by the same verify() with no code edit. Demonstrated with a synthetic freeze."""
    exp = AUTH.build_expected(experiment="E", freeze_manifest_sha256="1",
                              source_graph_sha256="2", upstream_sha256="3",
                              fresh_content_sha256="4")
    with tempfile.TemporaryDirectory() as d:
        token = {"authorization_version": AUTH.AUTHORIZATION_VERSION,
                 "authorize_confirmatory_oos": True,
                 "bindings": {"experiment": "E", "freeze_manifest_sha256": "1",
                              "source_graph_sha256": "2", "upstream_sha256": "3",
                              "fresh_content_sha256": "4"}}
        path = os.path.join(d, AUTH.AUTHORIZATION_ARTIFACT)
        json.dump(token, open(path, "w"))
        loaded = json.load(open(path))
    assert AUTH.verify(loaded, exp)["authorized"] is True
