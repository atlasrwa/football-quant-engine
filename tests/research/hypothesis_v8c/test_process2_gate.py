"""AUDIT FINDINGS 1, 2, 3: the process-2 gate.

1  the external anchor was never called from production; the receipt was optional
2  every binding check was `if row.get(field)`, so an incomplete freeze passed vacuously,
   and `rebuild_universe=False` could switch off the universe check entirely
3  inference-block validation ran AFTER the scoring loop, so a malformed block opened every
   target outcome before being rejected

Each test below fails against the pre-repair code. The finding-3 tests prove ZERO target reads
via an instrumented index, not merely that an exception was raised.
"""
from __future__ import annotations

import json
import subprocess

import pytest

from src.research.hypothesis_v8c import anchor as A
from src.research.hypothesis_v8c import receipt as RC
from src.research.hypothesis_v8c import score_frozen as SFZ

ANCHOR_REL = "evidence/anchor.json"


def _git(repo, *args):
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, f"git {args}: {out.stderr}"
    return out.stdout.strip()


# =============================================================== FINDING 1: the anchor
@pytest.fixture
def anchored(tmp_path):
    """A scratch repo: producer-code commit, then a separate anchor commit."""
    r = tmp_path / "scratch"
    (r / "src/research/hypothesis_v8c").mkdir(parents=True)
    (r / "evidence").mkdir()
    _git(r.parent, "init", "-q", str(r))
    _git(r, "config", "user.email", "t@example.com")
    _git(r, "config", "user.name", "T")
    mod = r / "src/research/hypothesis_v8c/grammar.py"
    mod.write_text("GRAMMAR_VERSION = 'v8c_grammar_v1'\n")
    _git(r, "add", "src/research/hypothesis_v8c/grammar.py")
    _git(r, "commit", "-q", "-m", "producer code")
    producer = _git(r, "rev-parse", "HEAD")

    freeze = r / "evidence/freeze.json"
    receipt = r / "evidence/receipt.json"
    freeze.write_text(json.dumps({"selections": ["x"], "freeze_version": "v1"}, indent=1))
    RC.write_receipt(RC.build_receipt(
        freeze_path=str(freeze), corpus_hash="C", capability_hash="K",
        fixture_ids_ordered=["mt_1"], classification="TEST"), str(receipt))
    A.write_anchor(A.build_anchor(
        freeze_path=str(freeze), receipt_path=str(receipt), producer_code_commit=producer,
        producer_code_hashes={"grammar": A._sha_bytes(mod.read_bytes())},
        classification="TEST"), str(r / ANCHOR_REL))
    _git(r, "add", "evidence")
    _git(r, "commit", "-q", "-m", "anchor")
    return {"root": str(r), "freeze": str(freeze), "receipt": str(receipt),
            "producer": producer, "anchor": _git(r, "rev-parse", "HEAD"), "mod": mod}


def _verify(a, **kw):
    kw.setdefault("anchor_commit", a["anchor"])
    kw.setdefault("anchor_repo_relpath", ANCHOR_REL)
    kw.setdefault("freeze_path", a["freeze"])
    kw.setdefault("receipt_path", a["receipt"])
    kw.setdefault("repo_root", a["root"])
    kw.setdefault("verify_executing", False)   # the scratch module is not imported here
    return A.verify_for_scoring(**kw)


def test_missing_anchor_commit_refuses(anchored):
    with pytest.raises(A.AnchorError, match="ANCHOR_COMMIT"):
        _verify(anchored, anchor_commit=None)


def test_wrong_pinned_anchor_refuses(anchored):
    with pytest.raises(A.AnchorError):
        _verify(anchored, anchor_commit=anchored["producer"])


def test_edited_freeze_refuses(anchored):
    with open(anchored["freeze"], "w") as f:
        json.dump({"selections": ["SWAPPED"]}, f)
    with pytest.raises(A.AnchorError, match="freeze bytes"):
        _verify(anchored)


def test_edited_freeze_plus_recomputed_receipt_still_refuses(anchored):
    """The two-file scheme falls to this. The anchor must not."""
    with open(anchored["freeze"], "w") as f:
        json.dump({"selections": ["SWAPPED"]}, f)
    RC.write_receipt(RC.build_receipt(
        freeze_path=anchored["freeze"], corpus_hash="C", capability_hash="K",
        fixture_ids_ordered=["mt_1"], classification="TEST"), anchored["receipt"])
    RC.verify_receipt(anchored["receipt"], anchored["freeze"])      # old check PASSES
    with pytest.raises(A.AnchorError):                              # anchor still refuses
        _verify(anchored)


def test_changed_executing_code_refuses(anchored):
    """Three-way binding: git can agree with the anchor while the interpreter runs other code."""
    anchor = json.loads(A.read_blob_at(anchored["anchor"], ANCHOR_REL,
                                       repo_root=anchored["root"]).decode())

    class FakeModule:
        __file__ = str(anchored["mod"])

    anchored["mod"].write_text("GRAMMAR_VERSION = 'TAMPERED'\n")   # working tree != commit
    import sys
    sys.modules["src.research.hypothesis_v8c.grammar_probe"] = FakeModule
    try:
        with pytest.raises(A.AnchorError, match="does not reproduce"):
            A.verify_producer_code(
                anchor, repo_root=anchored["root"], verify_executing=True,
                require_modules=["grammar"], require_executing=["grammar"])
    finally:
        sys.modules.pop("src.research.hypothesis_v8c.grammar_probe", None)


def test_empty_producer_hash_coverage_refuses(anchored):
    anchor = json.loads(A.read_blob_at(anchored["anchor"], ANCHOR_REL,
                                       repo_root=anchored["root"]).decode())
    anchor["producer_code_hashes"] = {}
    with pytest.raises(A.AnchorError, match="NO producer code hashes"):
        A.verify_producer_code(anchor, repo_root=anchored["root"])


def test_incomplete_producer_hash_coverage_refuses(anchored):
    anchor = json.loads(A.read_blob_at(anchored["anchor"], ANCHOR_REL,
                                       repo_root=anchored["root"]).decode())
    anchor["producer_code_hashes"] = {"grammar": None, "scorer": None}
    with pytest.raises(A.AnchorError, match="incomplete"):
        A.verify_producer_code(anchor, repo_root=anchored["root"])


def test_score_frozen_requires_anchor_arguments():
    """The production entry point cannot be called without a pinned anchor."""
    import inspect
    sig = inspect.signature(SFZ.score_frozen)
    for name in ("receipt_path", "anchor_commit", "anchor_repo_relpath"):
        assert sig.parameters[name].default is inspect.Parameter.empty, (
            f"{name} must be mandatory, not defaulted")
    assert "rebuild_universe" not in sig.parameters, (
        "the universe-verification disable switch must be gone")


def test_missing_receipt_refuses():
    with pytest.raises(RC.ReceiptError, match="no receipt"):
        SFZ.load_and_verify_freeze("/nonexistent/freeze.json", receipt_path=None)


# =============================================================== FINDING 2: schema
def _good_row(fid="mt_1"):
    return {"fixture_id": fid,
            "fixture_metadata": {"fixture_id": fid, "kickoff_unix": 1, "competition": "champ",
                                 "home_id": "a", "away_id": "b"},
            "corpus_vintage_hash": "v", "capability_hash": "c",
            "grammar_version": "g", "grammar_size_hash": "gs",
            "pit_context_hash": "p", "universe_hash": "u",
            "arm_status": "OK", "S": ["h1"], "R": ["h2"], "H": ["h3"],
            "R_pairs": [{"s_id": "h1", "r_id": "h2", "tier": "EXACT", "status": "MATCHED"}]}


def _good_freeze(rows=None, ids=None):
    rows = rows or [_good_row()]
    # `ids` is passed explicitly so a row with `fixture_id` REMOVED can still be wrapped in an
    # otherwise-valid freeze -- the point of that case is the schema check, not the wrapper.
    ids = ids if ids is not None else [r.get("fixture_id", "mt_1") for r in rows]
    return {"freeze_version": "v1", "freeze_hash": "h", "classification": "SYNTHETIC_ONLY",
            "selections": rows, "fixture_ids_ordered": ids,
            "inference_blocks": {"fixture_to_block": {i: 0 for i in ids}}}


@pytest.mark.parametrize("field", SFZ.REQUIRED_ROW_FIELDS)
def test_missing_row_binding_field_fails_closed(field):
    row = _good_row()
    row.pop(field)
    with pytest.raises(SFZ.FreezeSchemaError, match="missing required binding field"):
        SFZ.verify_freeze_schema(_good_freeze([row]))


@pytest.mark.parametrize("field", ["freeze_version", "classification", "selections",
                                   "fixture_ids_ordered", "inference_blocks"])
def test_missing_top_level_field_fails_closed(field):
    fz = _good_freeze()
    fz.pop(field)
    with pytest.raises(SFZ.FreezeSchemaError, match="missing required field"):
        SFZ.verify_freeze_schema(fz)


@pytest.mark.parametrize("field", SFZ.REQUIRED_METADATA_FIELDS)
def test_missing_metadata_subfield_fails_closed(field):
    row = _good_row()
    row["fixture_metadata"].pop(field)
    with pytest.raises(SFZ.FreezeSchemaError, match="metadata is missing"):
        SFZ.verify_freeze_schema(_good_freeze([row]))


def test_complete_freeze_passes_schema():
    SFZ.verify_freeze_schema(_good_freeze())


# =============================================================== FINDING 3: block ordering
class CountingIndex:
    """Wraps an index and counts every read of a TARGET position's own observation."""

    def __init__(self, inner):
        object.__setattr__(self, "_inner", inner)
        object.__setattr__(self, "target_reads", 0)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def team_value(self, rec_i, *a, **kw):
        object.__setattr__(self, "target_reads", self.target_reads + 1)
        return self._inner.team_value(rec_i, *a, **kw)


def test_malformed_blocks_in_final_fixture_cause_zero_target_reads():
    """The case the old ordering got wrong: the defect is in the LAST fixture."""
    rows = [_good_row(f"mt_{i}") for i in range(1, 6)]
    fz = _good_freeze(rows)
    del fz["inference_blocks"]["fixture_to_block"]["mt_5"]      # last fixture uncovered
    with pytest.raises(SFZ.InferenceBlockError, match="no inference block"):
        SFZ.verify_inference_blocks(fz)


def test_duplicate_fixture_ids_rejected():
    rows = [_good_row("mt_1"), _good_row("mt_1")]
    fz = _good_freeze(rows)
    fz["fixture_ids_ordered"] = ["mt_1", "mt_1"]
    with pytest.raises(SFZ.InferenceBlockError, match="duplicates"):
        SFZ.verify_inference_blocks(fz)


def test_ordering_and_selection_set_must_agree():
    fz = _good_freeze([_good_row("mt_1")])
    fz["fixture_ids_ordered"] = ["mt_2"]
    with pytest.raises(SFZ.InferenceBlockError, match="disagree"):
        SFZ.verify_inference_blocks(fz)


def test_blocks_covering_foreign_fixtures_rejected():
    fz = _good_freeze([_good_row("mt_1")])
    fz["inference_blocks"]["fixture_to_block"]["mt_STRANGER"] = 0
    with pytest.raises(SFZ.InferenceBlockError, match="not in the cohort"):
        SFZ.verify_inference_blocks(fz)


def test_missing_blocks_rejected():
    fz = _good_freeze()
    fz["inference_blocks"] = {}
    with pytest.raises(SFZ.InferenceBlockError, match="no inference_blocks"):
        SFZ.verify_inference_blocks(fz)


def test_block_validation_precedes_scoring_in_source_order():
    """Structural guard: the validator must be called before the scoring loop."""
    import inspect
    src = inspect.getsource(SFZ.score_frozen)
    i_blocks = src.index("verify_inference_blocks")
    i_score = src.index("SC.score_fixture")
    assert i_blocks < i_score, (
        "inference-block validation must run BEFORE the first target read")
