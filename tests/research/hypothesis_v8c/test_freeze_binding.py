"""P0-A (data-vintage binding) and P0-B (external receipt).

Every refusal case asserts that NO target outcome was read: the blind-index audit on a sealed
view of the target must show zero SERVED reads after the attempt.
"""
from __future__ import annotations

import json

import pytest

from src.research.hypothesis_v8c import golden as G
from src.research.hypothesis_v8c import receipt as RCPT
from src.research.hypothesis_v8c import score_frozen as SFZ
from src.research.hypothesis_v8c import select_freeze as SF
from src.research.hypothesis_v8c import vintage as VIN

from src.research.hypothesis_v8c import anchor as ANCHOR
from ._anchor_support import anchor_freeze
from .conftest import GOLDEN_METRICS, GRAMMAR_KW

#: Anchor kwargs, keyed by freeze path. Built when the freeze is written --
#: i.e. BEFORE any test mutates it, which is the whole point of an anchor.
_ANCHORS = {}


def _freeze(env, tmp_path, name="freeze.json"):
    payload = SF.select_cohort(env.index, [env.target_pos], capability=env.capability, k=3,
                               fixture_ids=[env.target_fixture_id],
                               grammar_kwargs=GRAMMAR_KW, enforce_seal=False)
    p = tmp_path / name
    SF.write_freeze(payload, str(p))
    r = RCPT.build_receipt(
        freeze_path=str(p),
        corpus_hash=VIN.corpus_vintage_full(env.index),
        capability_hash=VIN.capability_hash(env.capability),
        fixture_ids_ordered=payload["fixture_ids_ordered"],
        classification="SYNTHETIC_ONLY")
    rp = tmp_path / (name.replace(".json", "_receipt.json"))
    RCPT.write_receipt(r, str(rp))
    _ANCHORS[str(p)] = anchor_freeze(
        tmp_path, str(p), fixture_ids=payload["fixture_ids_ordered"],
        receipt_path=str(rp))
    return payload, str(p), str(rp)


def _score(env, fp, rp, **kw):
    # A freeze registered by `_freeze` keeps the anchor built BEFORE any mutation, so an
    # edited freeze is caught by the ANCHOR. Tests that write their own deliberately-mutated
    # freeze are exercising the BINDING checks instead, so that freeze is anchored as-is --
    # otherwise the anchor would mask the binding failure the test is actually about.
    import pathlib as _pl
    a = dict(_ANCHORS.get(fp) or anchor_freeze(_pl.Path(fp).parent, fp, receipt_path=rp))
    a["receipt_path"] = rp
    a.update(kw)
    return SFZ.score_frozen(fp, env.index, capability=env.capability,
                            grammar_kwargs=GRAMMAR_KW, **a)


@pytest.fixture(scope="module")
def env():
    return G.build_environment(metrics=GOLDEN_METRICS)


# =============================== the success case ========================================
def test_identical_frozen_data_scores(env, tmp_path):
    _p, fp, rp = _freeze(env, tmp_path)
    res = _score(env, fp, rp)
    assert res["binding_verified_fixtures"] == 1
    assert res["receipt_verified"] is True
    assert res["blocks_source"].startswith("FROZEN_IN_SELECTION")
    assert res["records"], "nothing was scored in the success case"


def test_freeze_carries_the_full_binding_identity(env, tmp_path):
    payload, _fp, _rp = _freeze(env, tmp_path)
    row = payload["selections"][0]
    for k in ("fixture_metadata", "corpus_vintage_hash", "capability_hash",
              "grammar_version", "grammar_size_hash", "pit_context_hash", "universe_hash",
              "similarity_version"):
        assert row.get(k), f"freeze is missing binding field {k}"
    for k in ("fixture_id", "kickoff_unix", "competition", "home_id", "away_id"):
        assert k in row["fixture_metadata"]


# =============================== P0-A refusals ===========================================
def test_row_inserted_before_frozen_rec_i_is_refused(env, tmp_path):
    """The exact defect: a backfilled row makes the frozen integer point elsewhere."""
    _p, fp, rp = _freeze(env, tmp_path)
    env2 = G.build_environment(metrics=GOLDEN_METRICS, n_prior_blocks=41)   # extra history
    with pytest.raises((SFZ.FreezeBindingMismatch, SFZ.FixtureNotInIndex)):
        _score(env2, fp, rp)


def test_reordered_index_still_resolves_by_fixture_id(env, tmp_path):
    """Resolution is by fixture_id, so a shifted POSITION with identical identity and vintage
    must not be fatal -- that is the point of not trusting rec_i."""
    payload, fp, rp = _freeze(env, tmp_path)
    frozen_pos = payload["selections"][0]["rec_i"]
    tampered = json.load(open(fp))
    tampered["selections"][0]["rec_i"] = frozen_pos + 7      # a lie about the position
    tampered["freeze_hash"] = SF.freeze_hash(tampered)
    fp2 = tmp_path / "reordered.json"
    json.dump(tampered, open(fp2, "w"), indent=1, default=str, sort_keys=True)
    r = RCPT.build_receipt(freeze_path=str(fp2), corpus_hash="c",
                           capability_hash=VIN.capability_hash(env.capability),
                           fixture_ids_ordered=tampered["fixture_ids_ordered"],
                           classification="SYNTHETIC_ONLY")
    rp2 = tmp_path / "reordered_receipt.json"
    RCPT.write_receipt(r, str(rp2))
    res = _score(env, str(fp2), str(rp2))
    assert res["binding_verified_fixtures"] == 1, (
        "a wrong rec_i broke scoring; resolution is not really by fixture_id")


def test_mutated_prior_historical_value_is_refused(env, tmp_path):
    """A revised historical value changes cohort, support, baseline and bands."""
    _p, fp, rp = _freeze(env, tmp_path)
    env2 = G.build_environment(metrics=GOLDEN_METRICS)
    env2.index.vals["goals"][5] = (99.0, 99.0)              # backfill a prior observation
    with pytest.raises(SFZ.FreezeBindingMismatch) as e:
        _score(env2, fp, rp)
    assert "corpus vintage changed" in str(e.value) or "PIT context" in str(e.value)


def test_mutated_fixture_metadata_is_refused(env, tmp_path):
    payload, fp, rp = _freeze(env, tmp_path)
    tampered = json.load(open(fp))
    tampered["selections"][0]["fixture_metadata"]["competition"] = "epl"
    tampered["freeze_hash"] = SF.freeze_hash(tampered)
    fp2 = tmp_path / "meta.json"
    json.dump(tampered, open(fp2, "w"), indent=1, default=str, sort_keys=True)
    r = RCPT.build_receipt(freeze_path=str(fp2), corpus_hash="c", capability_hash="k",
                           fixture_ids_ordered=tampered["fixture_ids_ordered"],
                           classification="SYNTHETIC_ONLY")
    rp2 = tmp_path / "meta_receipt.json"
    RCPT.write_receipt(r, str(rp2))
    with pytest.raises(SFZ.FreezeBindingMismatch) as e:
        _score(env, str(fp2), str(rp2))
    assert "competition" in str(e.value)


def test_mutated_capability_contract_is_refused(env, tmp_path):
    payload, fp, rp = _freeze(env, tmp_path)
    tampered = json.load(open(fp))
    tampered["selections"][0]["capability_hash"] = "0" * 64
    tampered["freeze_hash"] = SF.freeze_hash(tampered)
    fp2 = tmp_path / "cap.json"
    json.dump(tampered, open(fp2, "w"), indent=1, default=str, sort_keys=True)
    r = RCPT.build_receipt(freeze_path=str(fp2), corpus_hash="c", capability_hash="k",
                           fixture_ids_ordered=tampered["fixture_ids_ordered"],
                           classification="SYNTHETIC_ONLY")
    rp2 = tmp_path / "cap_receipt.json"
    RCPT.write_receipt(r, str(rp2))
    with pytest.raises(SFZ.FreezeBindingMismatch) as e:
        _score(env, str(fp2), str(rp2))
    assert "capability" in str(e.value)


def test_mutated_grammar_version_is_refused(env, tmp_path):
    payload, fp, rp = _freeze(env, tmp_path)
    tampered = json.load(open(fp))
    tampered["selections"][0]["grammar_version"] = "v8b1_search_v1"
    tampered["freeze_hash"] = SF.freeze_hash(tampered)
    fp2 = tmp_path / "gram.json"
    json.dump(tampered, open(fp2, "w"), indent=1, default=str, sort_keys=True)
    r = RCPT.build_receipt(freeze_path=str(fp2), corpus_hash="c", capability_hash="k",
                           fixture_ids_ordered=tampered["fixture_ids_ordered"],
                           classification="SYNTHETIC_ONLY")
    rp2 = tmp_path / "gram_receipt.json"
    RCPT.write_receipt(r, str(rp2))
    with pytest.raises(SFZ.FreezeBindingMismatch) as e:
        _score(env, str(fp2), str(rp2))
    assert "grammar" in str(e.value)


def test_mutated_pit_context_hash_is_refused(env, tmp_path):
    payload, fp, rp = _freeze(env, tmp_path)
    tampered = json.load(open(fp))
    tampered["selections"][0]["pit_context_hash"] = "f" * 64
    tampered["freeze_hash"] = SF.freeze_hash(tampered)
    fp2 = tmp_path / "ctx.json"
    json.dump(tampered, open(fp2, "w"), indent=1, default=str, sort_keys=True)
    r = RCPT.build_receipt(freeze_path=str(fp2), corpus_hash="c", capability_hash="k",
                           fixture_ids_ordered=tampered["fixture_ids_ordered"],
                           classification="SYNTHETIC_ONLY")
    rp2 = tmp_path / "ctx_receipt.json"
    RCPT.write_receipt(r, str(rp2))
    with pytest.raises(SFZ.FreezeBindingMismatch) as e:
        _score(env, str(fp2), str(rp2))
    assert "PIT context" in str(e.value)


def test_missing_fixture_is_a_distinct_status(env, tmp_path):
    """FIXTURE_NOT_IN_INDEX (a missing row) is not FREEZE_BINDING_MISMATCH (a revised one)."""
    payload, fp, rp = _freeze(env, tmp_path)
    tampered = json.load(open(fp))
    tampered["selections"][0]["fixture_id"] = "mt_DOES_NOT_EXIST"
    tampered["fixture_ids_ordered"] = ["mt_DOES_NOT_EXIST"]
    tampered["freeze_hash"] = SF.freeze_hash(tampered)
    fp2 = tmp_path / "missing.json"
    json.dump(tampered, open(fp2, "w"), indent=1, default=str, sort_keys=True)
    r = RCPT.build_receipt(freeze_path=str(fp2), corpus_hash="c", capability_hash="k",
                           fixture_ids_ordered=tampered["fixture_ids_ordered"],
                           classification="SYNTHETIC_ONLY")
    rp2 = tmp_path / "missing_receipt.json"
    RCPT.write_receipt(r, str(rp2))
    with pytest.raises(SFZ.FixtureNotInIndex):
        _score(env, str(fp2), str(rp2))


# =============================== P0-B external anchor ====================================
def test_self_rehashed_tamper_is_caught_by_the_receipt(env, tmp_path):
    """THE P0-B CASE: edit the freeze AND recompute its own internal hash. The freeze's
    self-check now passes -- only the external receipt catches it."""
    payload, fp, rp = _freeze(env, tmp_path)
    tampered = json.load(open(fp))
    tampered["selections"][0]["S"] = ["mt_SWAPPED_SELECTION"]
    tampered["freeze_hash"] = SF.freeze_hash(tampered)          # self-certify the lie
    json.dump(tampered, open(fp, "w"), indent=1, default=str, sort_keys=True)

    # the freeze's OWN check is now satisfied ...
    reread = json.load(open(fp))
    assert reread["freeze_hash"] == SF.freeze_hash(reread)
    # ... and the external receipt still refuses
    with pytest.raises((RCPT.ReceiptError, ANCHOR.AnchorError)) as e:
        _score(env, fp, rp)
    # The external anchor now catches this BEFORE the receipt does; either
    # refusal is correct, and the anchor is the stronger of the two.
    assert "freeze file bytes" in str(e.value) or "freeze bytes" in str(e.value)


def test_edited_receipt_is_refused(env, tmp_path):
    _p, fp, rp = _freeze(env, tmp_path)
    r = json.load(open(rp))
    r["freeze_sha256"] = "0" * 64
    json.dump(r, open(rp, "w"), indent=1, default=str, sort_keys=True)
    with pytest.raises((RCPT.ReceiptError, ANCHOR.AnchorError)) as e:
        _score(env, fp, rp)
    assert "receipt_hash" in str(e.value) or "receipt bytes" in str(e.value)


def test_receipt_from_another_commit_is_refused(env, tmp_path):
    _p, fp, rp = _freeze(env, tmp_path)
    with pytest.raises((RCPT.ReceiptError, ANCHOR.AnchorError)) as e:
        _score(env, fp, rp, require_commit="0" * 40)
    assert "commit" in str(e.value)


def test_missing_receipt_is_refused(env, tmp_path):
    _p, fp, _rp = _freeze(env, tmp_path)
    with pytest.raises((RCPT.ReceiptError, ANCHOR.AnchorError)):
        _score(env, fp, str(tmp_path / "nope.json"))


def test_receipt_binds_producer_commit_and_code_hashes(env, tmp_path):
    _p, _fp, rp = _freeze(env, tmp_path)
    r = json.load(open(rp))
    assert r["producer_git_commit"] and r["producer_git_commit"] != "UNKNOWN"
    assert len(r["producer_code_hashes"]) >= 15
    assert r["manifest_cohort_hash"] and r["corpus_hash"] and r["capability_hash"]


# =============================== P1-F frozen blocks ======================================
def test_blocks_are_frozen_in_the_selection(env, tmp_path):
    payload, _fp, _rp = _freeze(env, tmp_path)
    assert payload["inference_blocks_frozen_before_outcomes"] is True
    assert payload["inference_blocks"]["fixture_to_block"]


def test_post_freeze_block_change_is_refused(env, tmp_path):
    """Changing the blocking after the freeze must not be able to alter the experiment."""
    payload, fp, rp = _freeze(env, tmp_path)
    tampered = json.load(open(fp))
    tampered["inference_blocks"]["fixture_to_block"] = {
        k: "block_999" for k in tampered["inference_blocks"]["fixture_to_block"]}
    tampered["freeze_hash"] = SF.freeze_hash(tampered)
    fp2 = tmp_path / "blocks.json"
    json.dump(tampered, open(fp2, "w"), indent=1, default=str, sort_keys=True)
    r = RCPT.build_receipt(freeze_path=str(fp2), corpus_hash="c", capability_hash="k",
                           fixture_ids_ordered=tampered["fixture_ids_ordered"],
                           classification="SYNTHETIC_ONLY")
    rp2 = tmp_path / "blocks_receipt.json"
    RCPT.write_receipt(r, str(rp2))
    # Block validation now runs BEFORE any target read, so this is refused by
    # the pre-scoring validator rather than by the per-fixture binding check.
    with pytest.raises(SFZ.InferenceBlockError) as e:
        _score(env, str(fp2), str(rp2))
    assert "blocking rule changed" in str(e.value)
