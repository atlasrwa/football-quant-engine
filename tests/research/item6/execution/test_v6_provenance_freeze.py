"""ITEM 6 Stage-1 V6 PROVENANCE freeze: execution-head externalization, scheme-aware hash
verification, and scientific-immutability tests (mission checks 1-20).

ZERO PAID INFERENCE. The execution conftest installs a network kill-switch; nothing here
constructs a live transport, counts tokens or calls Converse. Every check is local.

The execution-head tests pass `actual_head` explicitly wherever the assertion is about the
COMPARISON rule, so they stay deterministic no matter which commit the repository is on --
including after the V6 commit itself lands, which is precisely the staleness the amendment
exists to rule out.
"""
from __future__ import annotations

import json
import os

import pytest

from src.research.item6.execution import live_driver as LD
from src.research.item6.execution import provenance as PROV
from src.research.item6.execution import request_builder as RB
from src.research.item6.execution import live_transport as LT

ROOT = os.environ.get("ITEM6_CODE_ROOT", "/home/ubuntu")
MANIFEST_V5_REL = "research/item6/ITEM6_STAGE1_RUN_MANIFEST_V5.json"
MANIFEST_V6_REL = "research/item6/ITEM6_STAGE1_RUN_MANIFEST_V6.json"
PACKET_SET_REL = "research/item6/out/execution/ITEM6_STAGE1_EVIDENCE_PACKET_SET_V1.json"
REQ_SET_REL = "research/item6/out/execution/ITEM6_STAGE1_MATERIALIZED_REQUEST_SET_V1.json"

SHA_A = "1111111111111111111111111111111111111111"
SHA_B = "2222222222222222222222222222222222222222"


def _j(rel):
    with open(f"{ROOT}/{rel}", "r", encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def v5():
    return _j(MANIFEST_V5_REL)


@pytest.fixture(scope="module")
def v6():
    return _j(MANIFEST_V6_REL)


# =========================================================================================
# PART A -- execution-head adversarial tests (mission checks 1-6)
# =========================================================================================
def test_01_authorized_head_equal_to_actual_head_may_proceed():
    """1. external authorized HEAD == actual HEAD -> startup may proceed."""
    assert PROV.require_authorized_execution_head(SHA_A, actual_head=SHA_A) == SHA_A
    # and against the real repository HEAD, whatever commit that is.
    head = PROV.resolve_git_head(ROOT)
    assert head and len(head) == 40
    assert PROV.require_authorized_execution_head(head, root=ROOT) == head
    # case-insensitive input is normalized, not rejected.
    assert PROV.require_authorized_execution_head(SHA_A.upper(), actual_head=SHA_A) == SHA_A


def test_02_wrong_authorized_head_fails_closed(v6):
    """2. external authorized HEAD != actual HEAD -> fail before CountTokens."""
    with pytest.raises(PROV.AuthorizedHeadError) as ei:
        PROV.require_authorized_execution_head(SHA_A, actual_head=SHA_B)
    assert "mismatch" in str(ei.value)
    # malformed values are refused too (never coerced).
    for bad in ("deadbeef", "not-a-sha", "z" * 40, ""):
        with pytest.raises(PROV.AuthorizedHeadError):
            PROV.require_authorized_execution_head(bad, actual_head=SHA_A)
    # the driver preflight surfaces it as a refusal.
    with pytest.raises(LD.LiveDriverRefused) as ei2:
        LD.preflight(MANIFEST_V6_REL, authorized_ceiling_usd=30.0,
                     authorized_execution_head=SHA_A, root=ROOT)
    assert "authorized execution head" in str(ei2.value)


def test_03_missing_authorized_head_fails_before_count_tokens(monkeypatch, tmp_path):
    """3. missing external authorized HEAD in LIVE mode -> fail before CountTokens."""
    with pytest.raises(PROV.AuthorizedHeadError) as ei:
        PROV.require_authorized_execution_head(None, actual_head=SHA_A)
    assert "not supplied" in str(ei.value)

    # ordering proof: refusal happens before the transport (and therefore any CountTokens
    # call) is ever constructed. Spies raise if reached.
    calls = {"transport": 0, "count": 0}

    def _boom_transport(*a, **k):
        calls["transport"] += 1
        raise AssertionError("transport constructed despite missing authorized head")

    def _boom_count(*a, **k):
        calls["count"] += 1
        raise AssertionError("CountTokens reached despite missing authorized head")

    monkeypatch.setattr(LT.BedrockStage1Transport, "from_frozen_config",
                        staticmethod(_boom_transport))
    monkeypatch.setattr(LT.BedrockStage1Transport, "count_tokens", _boom_count)

    with pytest.raises(LD.LiveDriverRefused) as ei2:
        LD.build_live_runner(MANIFEST_V6_REL, authorized_ceiling_usd=30.0,
                             authorized_execution_head=None,
                             out_dir=str(tmp_path / "o"), root=ROOT)
    assert "authorized execution head" in str(ei2.value)
    assert calls == {"transport": 0, "count": 0}


def test_04_apparatus_commit_does_not_substitute_for_authorization(v6):
    """4. a stale apparatus provenance commit does NOT substitute for human authorization."""
    apparatus = v6["apparatus_provenance_commit"]
    assert apparatus == PROV.APPARATUS_PROVENANCE_COMMIT
    # Even with the repository sitting exactly on the apparatus commit, supplying nothing is
    # still a refusal: the manifest field is never read as the authorized head.
    with pytest.raises(PROV.AuthorizedHeadError):
        PROV.require_authorized_execution_head(None, actual_head=apparatus)
    # And on any later commit the apparatus value is simply wrong as an execution head.
    with pytest.raises(PROV.AuthorizedHeadError) as ei:
        PROV.require_authorized_execution_head(apparatus, actual_head=SHA_B)
    assert "mismatch" in str(ei.value)
    assert v6["execution_head_policy"]["apparatus_commit_may_not_substitute"] is True


def test_05_manifest_binds_apparatus_commit_without_claiming_runtime_head(v5, v6):
    """5. manifest may bind the apparatus commit without claiming it is the runtime HEAD."""
    assert PROV.SELF_REFERENTIAL_HEAD_FIELD not in v6
    assert v6["self_referential_execution_head_field_present"] is False
    assert v6["exact_execution_head_source"] == "EXTERNAL_HUMAN_AUTHORIZATION"
    apparatus, source = PROV.assert_execution_head_policy(v6)
    assert apparatus == PROV.APPARATUS_PROVENANCE_COMMIT
    assert source == PROV.EXACT_EXECUTION_HEAD_SOURCE
    # the V5 defect is recorded, not silently dropped.
    assert v6["removed_field_from_v5"]["field"] == PROV.SELF_REFERENTIAL_HEAD_FIELD
    assert v6["removed_field_from_v5"]["v5_value"] == v5[PROV.SELF_REFERENTIAL_HEAD_FIELD]
    # a V5-style manifest is refused by the policy check.
    with pytest.raises(PROV.ProvenanceError) as ei:
        PROV.assert_execution_head_policy(v5)
    assert PROV.SELF_REFERENTIAL_HEAD_FIELD in str(ei.value)


def test_06_successor_commit_does_not_invalidate_apparatus_semantics(v6):
    """6. creating a successor manifest commit does not invalidate apparatus provenance."""
    future_head = SHA_B                      # pretend the V6 commit (or a later one) landed
    assert v6["apparatus_provenance_commit"] != future_head
    # the policy still holds at the later HEAD -- nothing in the manifest went stale...
    PROV.assert_execution_head_policy(v6)
    # ...and authorization at the later HEAD works, precisely because it is external.
    assert PROV.require_authorized_execution_head(future_head,
                                                  actual_head=future_head) == future_head
    assert v6["execution_head_policy"][
        "do_not_amend_this_manifest_to_embed_its_own_commit"] is True
    # a manifest that re-adds a self-referential head field is refused again.
    tampered = dict(v6)
    tampered[PROV.SELF_REFERENTIAL_HEAD_FIELD] = future_head
    with pytest.raises(PROV.ProvenanceError):
        PROV.assert_execution_head_policy(tampered)


# =========================================================================================
# PART B -- hash-scheme tests (mission checks 7-13)
# =========================================================================================
def test_07_raw_file_scheme_verifies(v6):
    """7. a RAW_FILE_SHA256 artifact verifies correctly."""
    entry = v6["artifact_hash_index"]["evidence_input.evidence_packet_contract"]
    assert entry["hash_scheme"] == PROV.HashScheme.RAW_FILE_SHA256
    assert PROV.verify_artifact("contract", entry, root=ROOT) == entry["sha256"]
    assert entry["sha256"] == PROV.raw_file_sha256(f"{ROOT}/{entry['path']}")
    report = PROV.verify_manifest_artifacts(v6, root=ROOT)
    assert report["ok"] and report["n_unknown_hash_schemes"] == 0
    assert report["n_by_scheme"][PROV.HashScheme.RAW_FILE_SHA256] >= 30


def test_08_canonical_self_hash_scheme_verifies(v6):
    """8. a CANONICAL_SELF_HASH artifact verifies correctly."""
    for name in ("evidence_input.evidence_packet_set",
                 "evidence_input.materialized_request_set"):
        entry = v6["artifact_hash_index"][name]
        assert entry["hash_scheme"] == PROV.HashScheme.CANONICAL_JSON_EXCLUDING_SELF_HASH
        assert entry["self_hash_field"]
        assert PROV.verify_artifact(name, entry, root=ROOT) == entry["sha256"]
        doc = _j(entry["path"])
        assert doc[entry["self_hash_field"]] == entry["sha256"]


def test_09_raw_verifier_on_canonical_artifact_fails(v6):
    """9. applying the raw-file verifier to a canonical artifact fails (the V5 false-DRIFT)."""
    entry = dict(v6["artifact_hash_index"]["evidence_input.evidence_packet_set"])
    raw_scheme_entry = {"path": entry["path"],
                        "hash_scheme": PROV.HashScheme.RAW_FILE_SHA256,
                        "sha256": entry["sha256"]}
    with pytest.raises(PROV.HashMismatchError):
        PROV.verify_artifact("packet_set_as_raw", raw_scheme_entry, root=ROOT)
    # the two digests genuinely differ -- this is why the scheme must be declared.
    assert PROV.raw_file_sha256(f"{ROOT}/{entry['path']}") != entry["sha256"]


def test_10_canonical_verifier_on_raw_artifact_fails(v6):
    """10. applying the canonical verifier to a raw-file artifact fails."""
    # a python source file cannot be canonical-JSON hashed at all.
    src = dict(v6["artifact_hash_index"]["evidence_input.evidence_packet_materializer_source"])
    bad = {"path": src["path"],
           "hash_scheme": PROV.HashScheme.CANONICAL_JSON_EXCLUDING_SELF_HASH,
           "self_hash_field": "packet_sha256", "sha256": src["sha256"]}
    with pytest.raises(PROV.HashSchemeError) as ei:
        PROV.verify_artifact("materializer_as_canonical", bad, root=ROOT)
    assert "inapplicable" in str(ei.value)
    # a JSON artifact with no declared self-hash field is refused rather than guessed.
    contract = dict(v6["artifact_hash_index"]["evidence_input.evidence_packet_contract"])
    bad2 = {"path": contract["path"],
            "hash_scheme": PROV.HashScheme.CANONICAL_JSON_EXCLUDING_SELF_HASH,
            "sha256": contract["sha256"]}
    with pytest.raises(PROV.HashSchemeError):
        PROV.verify_artifact("contract_as_canonical", bad2, root=ROOT)


def test_11_unknown_hash_scheme_fails_closed(v6):
    """11. an unknown hash scheme fails closed."""
    entry = dict(v6["artifact_hash_index"]["champion"])
    for scheme in ("MD5", "sha256", "RAW", None, ""):
        bad = {**entry, "hash_scheme": scheme}
        with pytest.raises(PROV.HashSchemeError):
            PROV.verify_artifact("champion_unknown_scheme", bad, root=ROOT)
    tampered = dict(v6)
    tampered["artifact_hash_index"] = {**v6["artifact_hash_index"],
                                       "champion": {**entry, "hash_scheme": "MD5"}}
    report = PROV.verify_manifest_artifacts(tampered, root=ROOT)
    assert report["ok"] is False and report["n_unknown_hash_schemes"] == 1
    # and a manifest with no index at all is refused (V6+ requirement).
    with pytest.raises(PROV.ProvenanceError):
        PROV.verify_manifest_artifacts({"run_manifest_version": "x"}, root=ROOT)


def test_12_modified_packet_set_triggers_drift(v6, tmp_path):
    """12. modifying the packet-set file triggers drift under the canonical scheme."""
    doc = _j(PACKET_SET_REL)
    doc["packets"][0]["n_evidence_items"] = 999_999
    p = tmp_path / "tampered_packet_set.json"
    p.write_text(json.dumps(doc))
    entry = dict(v6["artifact_hash_index"]["evidence_input.evidence_packet_set"])
    entry["path"] = str(p)
    with pytest.raises(PROV.HashMismatchError):
        PROV.verify_artifact("tampered_packet_set", entry, root=ROOT)
    # re-indentation alone must NOT look like drift under the canonical scheme.
    q = tmp_path / "reindented_packet_set.json"
    q.write_text(json.dumps(_j(PACKET_SET_REL), indent=4))
    ok_entry = dict(v6["artifact_hash_index"]["evidence_input.evidence_packet_set"])
    ok_entry["path"] = str(q)
    assert PROV.verify_artifact("reindented", ok_entry, root=ROOT) == ok_entry["sha256"]


def test_13_modified_request_set_triggers_drift(v6, tmp_path):
    """13. modifying request-set content triggers drift."""
    doc = _j(REQ_SET_REL)
    doc["entries"][0]["canonical_request_sha256"] = "0" * 64
    p = tmp_path / "tampered_request_set.json"
    p.write_text(json.dumps(doc))
    entry = dict(v6["artifact_hash_index"]["evidence_input.materialized_request_set"])
    entry["path"] = str(p)
    with pytest.raises(PROV.HashMismatchError):
        PROV.verify_artifact("tampered_request_set", entry, root=ROOT)
    # a document whose self-hash field disagrees with the manifest is refused even when the
    # manifest digest would otherwise match.
    doc2 = _j(REQ_SET_REL)
    doc2["materialized_request_set_sha256"] = "0" * 64
    p2 = tmp_path / "selfhash_disagree.json"
    p2.write_text(json.dumps(doc2))
    entry2 = dict(v6["artifact_hash_index"]["evidence_input.materialized_request_set"])
    entry2["path"] = str(p2)
    with pytest.raises(PROV.HashMismatchError):
        PROV.verify_artifact("selfhash_disagree", entry2, root=ROOT)


# =========================================================================================
# PART C -- scientific immutability tests (mission checks 14-20)
# =========================================================================================
def test_14_all_120_packet_hashes_identical_v5_to_v6(v5, v6):
    """14. all 120 packet hashes identical V5 -> V6."""
    packet_set = _j(PACKET_SET_REL)
    req_set = _j(REQ_SET_REL)
    from src.research.item6.evidence import packet_materializer as PM
    assert len(packet_set["packets"]) == 120
    bound = {e["fixture_id"]: e["packet_sha256"] for e in req_set["entries"]}
    n_mismatch = 0
    for p in packet_set["packets"]:
        if PM.packet_hash(p["packet"]) != p["packet_sha256"]:
            n_mismatch += 1
        elif bound[p["fixture_id"]] != p["packet_sha256"]:
            n_mismatch += 1
    assert n_mismatch == 0
    # the set identity V6 binds is the same value V5 bound.
    assert v6["evidence_input"]["evidence_packet_set_sha256"] == \
        v5["evidence_input"]["evidence_packet_set_sha256"]


def test_15_all_120_materialized_request_hashes_identical_v5_to_v6(v5, v6):
    """15. all 120 materialized request hashes identical V5 -> V6 (recomputed from the
    frozen packet bodies through the frozen request builder)."""
    packet_set = _j(PACKET_SET_REL)
    req_set = _j(REQ_SET_REL)
    system_text = RB.load_frozen_system_text(ROOT)
    packets = {p["fixture_id"]: p["packet"] for p in packet_set["packets"]}
    cohort = _j(v6["scientific_artifact_paths"]["cohort_manifest"])["fixtures"]
    by_id = {f["fixture_id"]: f for f in cohort}
    n_mismatch = 0
    for e in req_set["entries"]:
        req = RB.canonical_request(by_id[e["fixture_id"]], system_text,
                                   evidence_packet=packets[e["fixture_id"]])
        if RB.request_sha256(req) != e["canonical_request_sha256"]:
            n_mismatch += 1
        if RB.request_byte_len(req) != e["request_utf8_bytes"]:
            n_mismatch += 1
    assert n_mismatch == 0
    assert v6["evidence_input"]["materialized_request_set_sha256"] == \
        v5["evidence_input"]["materialized_request_set_sha256"]
    assert v6["model_visible_bytes_unchanged_vs_v5"] is True
    assert v6["scientific_model_visible_request_changed"] is False


@pytest.mark.parametrize("key", ["mechanism_prompt", "mechanism_schema_md",
                                 "stage1_gate_md", "stage1_gate_code", "cohort_manifest"])
def test_16_to_19_prompt_schema_gate_cohort_hashes_identical(v5, v6, key):
    """16-19. prompt / schema / gate / cohort hashes identical V5 -> V6."""
    assert v6["scientific_artifact_hashes"][key] == v5["scientific_artifact_hashes"][key]
    rel = v6["scientific_artifact_paths"][key]
    assert PROV.raw_file_sha256(f"{ROOT}/{rel}") == v6["scientific_artifact_hashes"][key]
    assert v6["artifact_hash_index"][f"scientific.{key}"]["sha256"] == \
        v5["scientific_artifact_hashes"][key]


def test_20_champion_identical(v5, v6):
    """20. CHAMPION identical."""
    assert v6["champion_sha256"] == v5["champion_sha256"]
    assert v6["champion_path"] == v5["champion_path"]
    assert PROV.raw_file_sha256(f"{ROOT}/{v6['champion_path']}") == v6["champion_sha256"]
    assert v6["champion_independent"] is True
    assert v6["stage2_activation"] == "BLOCKED_UNLESS_STAGE1_PASS"


# =========================================================================================
# PART D -- amendment-scope guards (provenance-only, zero spend)
# =========================================================================================
def test_21_v6_is_provenance_only_and_keeps_treatment_and_ceiling(v5, v6):
    """V6 changes provenance only: every scientific + evidence-input identity is carried
    over unchanged, the runner is untouched, and the ceiling stays unauthorized."""
    assert v6["scientific_artifact_hashes"] == v5["scientific_artifact_hashes"]
    for k in ("evidence_packet_contract_sha256", "evidence_packet_materializer_source_sha256",
              "frozen_packet_provider_source_sha256", "packet_compression_policy_sha256",
              "evidence_packet_set_sha256", "materialized_request_set_sha256"):
        assert v6["evidence_input"][k] == v5["evidence_input"][k]
    assert v6["execution_artifact_hashes"]["runner_code"] == \
        v5["execution_artifact_hashes"]["runner_code"]
    assert v6["execution_artifact_hashes"]["live_driver_code"] != \
        v5["execution_artifact_hashes"]["live_driver_code"]
    assert v6["live_driver_version"] == "item6_stage1_live_driver_v3"
    assert v6["spend_model"]["human_authorized_monetary_ceiling_usd"] is None
    assert v6["max_request_utf8_bytes"] == 32768
    assert v6["input_price_usd_per_mtok"] == 3.30
    assert v6["output_price_usd_per_mtok"] == 16.50
    assert v6["max_output_tokens_reserved"] == 8192
    assert (v6["live_sonnet_generation_calls"] == 0
            and v6["bedrock_paid_inference_calls"] == 0
            and v6["new_paid_inference_spend_usd"] == 0)


def test_22_v6_drops_the_ambiguous_mixed_scheme_dict(v5, v6):
    """The V5 mixed raw/canonical dict does not survive into V6: ambiguity is eliminated,
    not merely supplemented."""
    assert "new_scientific_input_artifact_hashes" in v5          # the defect existed
    assert "new_scientific_input_artifact_hashes" not in v6      # and is gone
    assert v6["v5_ambiguous_hash_dict_removed"] == "new_scientific_input_artifact_hashes"
    assert v6["hash_metadata_format"] == "PER_ARTIFACT_SCHEME_TAGGED_INDEX"
    assert v6["naive_hash_ambiguity_eliminated"] is True
    # every surviving hash container in V6 is unambiguous: the index is scheme-tagged, and
    # the legacy dicts are uniformly raw-file.
    for name, entry in v6["artifact_hash_index"].items():
        assert entry["hash_scheme"] in PROV.KNOWN_HASH_SCHEMES, name
    for key, rel in v6["scientific_artifact_paths"].items():
        assert PROV.raw_file_sha256(f"{ROOT}/{rel}") == v6["scientific_artifact_hashes"][key]
    for key, rel in v6["execution_artifact_paths"].items():
        assert PROV.raw_file_sha256(f"{ROOT}/{rel}") == v6["execution_artifact_hashes"][key]


def test_23_v6_manifest_self_hash_and_lineage(v5, v6):
    """V6 self-hash verifies, supersedes V5, and preserves the V5 identity as predecessor."""
    assert LD._verify_manifest_self_hash(v6)
    assert v6["supersedes_run_manifest_version"] == v5["run_manifest_version"]
    assert v6["predecessor_run_manifest_sha256"] == v5["run_manifest_sha256"]
    assert v6["amendment_scope"] == "PROVENANCE_ONLY_NO_SCIENTIFIC_TREATMENT_CHANGE"
    stamp = PROV.version_stamp()
    assert stamp["hash_verifier_scheme_aware"] is True
    assert stamp["self_referential_execution_head_supported"] is False
    assert LD.version_stamp()["requires_external_authorized_execution_head"] is True
    assert LD.version_stamp()["live_empty_evidence_packet_allowed"] is False
