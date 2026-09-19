"""REPAIR 2: validate the ACTUAL data source, against an external pin, before parsing.

Every forbidden row here is SYNTHETIC. No real reserve outcome is used to demonstrate a
failure -- doing so would be the leak the gate exists to prevent.
"""
from __future__ import annotations

import hashlib
import json
import os
import tarfile

import pytest

from src.research.hypothesis_v8c import bundle_gate as BG

CACHE = BG.CACHE_RELDIR
SEALED_ID = "mt_SYNTHETIC_SEALED_0001"          # invented; not a real reserve fixture


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _make_bundle(tmp_path, *, season_rows=None, stats_ids=("mt_OK_1",),
                 sealed=(SEALED_ID,), extra_file=None):
    """A minimal, well-formed bundle, then optionally spoiled one way."""
    root = tmp_path / "src_tree" / "BUNDLE"
    (root / CACHE).mkdir(parents=True)
    (root / "research/hypothesis_engine").mkdir(parents=True)
    (root / "loader_adapter").mkdir(parents=True)

    rows = season_rows if season_rows is not None else [
        {"id": "mt_OK_1", "utc_date": "2024-01-01T12:00:00.000Z", "score": {"home": 1, "away": 0}}]
    (root / CACHE / "_all_fixtures_sn_1.json").write_text(
        json.dumps({"season_id": "sn_1", "n": len(rows), "fixtures": rows}))
    for sid in stats_ids:
        (root / CACHE / f"stats_{sid}.json").write_text(json.dumps({"data": {}}))
    (root / "research/hypothesis_engine/V8C_SEALED947_EXCLUSION_IDS.json").write_text(
        json.dumps({"sealed_fixture_ids": list(sealed)}))
    (root / "loader_adapter" / "v8c_dev_paths.py").write_text("CACHE_ROOT=''\n")
    if extra_file:
        (root / extra_file).write_text("unexpected")

    files = {}
    for dp, _dn, fn in os.walk(root):
        for f in fn:
            p = os.path.join(dp, f)
            rel = os.path.relpath(p, root)
            files[rel] = {"sha256": _sha(open(p, "rb").read()),
                          "size_bytes": os.path.getsize(p)}
    (root / BG.MANIFEST_NAME).write_text(json.dumps({"files": files}))

    arc = tmp_path / "bundle.tar.gz"
    with tarfile.open(arc, "w:gz") as tf:
        tf.add(root, arcname="BUNDLE")
    return str(arc), str(root)


# ---------------------------------------------------------------- the external pin
def test_wrong_archive_digest_is_refused(tmp_path):
    arc, _ = _make_bundle(tmp_path)
    with pytest.raises(BG.BundleGateError, match="not the approved bundle"):
        BG.verify_archive(arc, expected_sha256="0" * 64)


def test_correct_digest_passes(tmp_path):
    arc, _ = _make_bundle(tmp_path)
    out = BG.verify_archive(arc, expected_sha256=_sha(open(arc, "rb").read()))
    assert out["unsafe_members"] == 0


def test_real_approved_archive_matches_its_pin():
    """The pin is a constant in code, not read from the data it validates."""
    p = "/home/ubuntu/handoff_out/V8C_DEV_EXPOSED50_HANDOFF_CORRECTED.tar.gz"
    if not os.path.exists(p):
        pytest.skip("approved archive not present in this checkout")
    assert BG._sha_file(p) == BG.APPROVED_ARCHIVE_SHA256


# ---------------------------------------------------------------- THE season-file hole
def test_sealed_row_in_a_season_file_is_caught_even_with_no_stats_file(tmp_path):
    """THE defect: filename-only checking passed a sealed SCORE in a season file."""
    rows = [{"id": "mt_OK_1", "utc_date": "2024-01-01T12:00:00.000Z",
             "score": {"home": 1, "away": 0}},
            {"id": SEALED_ID, "utc_date": "2024-06-01T12:00:00.000Z",
             "score": {"home": 3, "away": 2}}]          # synthetic, no stats file
    arc, root = _make_bundle(tmp_path, season_rows=rows, stats_ids=("mt_OK_1",))
    ids = BG.approved_fixture_ids(root)
    assert SEALED_ID in ids["season_ids"]
    assert SEALED_ID not in ids["stats_ids"], "the old check looked only here"
    with pytest.raises(BG.BundleGateError, match="season-file row"):
        BG.assert_no_sealed(root, ids)


def test_sealed_stats_file_is_still_caught(tmp_path):
    arc, root = _make_bundle(tmp_path, stats_ids=("mt_OK_1", SEALED_ID))
    with pytest.raises(BG.BundleGateError, match="SEALED RESERVE PRESENT"):
        BG.assert_no_sealed(root, BG.approved_fixture_ids(root))


def test_clean_bundle_passes_the_seal_check(tmp_path):
    arc, root = _make_bundle(tmp_path)
    out = BG.assert_no_sealed(root, BG.approved_fixture_ids(root))
    assert out["sealed_in_season_files"] == 0 and out["sealed_in_stats_files"] == 0


# ---------------------------------------------------------------- tree integrity
def test_tampered_file_after_extraction_is_refused(tmp_path):
    arc, root = _make_bundle(tmp_path)
    _rn, files = BG.manifest_from_archive(arc)
    with open(os.path.join(root, CACHE, "stats_mt_OK_1.json"), "w") as f:
        f.write('{"data": {"tampered": true}}')
    with pytest.raises(BG.BundleGateError, match="digest mismatch"):
        BG.verify_extracted_tree(root, files)


def test_unexpected_extra_file_is_refused(tmp_path):
    arc, root = _make_bundle(tmp_path)
    _rn, files = BG.manifest_from_archive(arc)
    with open(os.path.join(root, CACHE, "SMUGGLED.json"), "w") as f:
        f.write("{}")
    with pytest.raises(BG.BundleGateError, match="unexpected"):
        BG.verify_extracted_tree(root, files)


def test_missing_file_is_refused(tmp_path):
    arc, root = _make_bundle(tmp_path)
    _rn, files = BG.manifest_from_archive(arc)
    os.remove(os.path.join(root, CACHE, "stats_mt_OK_1.json"))
    with pytest.raises(BG.BundleGateError, match="missing"):
        BG.verify_extracted_tree(root, files)


def test_manifest_is_read_from_inside_the_archive(tmp_path):
    """A manifest edited on disk beside the data must not be what is trusted."""
    arc, root = _make_bundle(tmp_path)
    with open(os.path.join(root, BG.MANIFEST_NAME), "w") as f:
        json.dump({"files": {}}, f)                     # spoil the on-disk copy
    _rn, files = BG.manifest_from_archive(arc)
    assert files, "the gate trusted the mutable on-disk manifest"


# ---------------------------------------------------------------- unsafe members
@pytest.mark.parametrize("name,kind", [("/etc/passwd", "ABSOLUTE"),
                                       ("BUNDLE/../escape.json", "TRAVERSAL")])
def test_unsafe_member_paths_are_refused(tmp_path, name, kind):
    """`tf.add(arcname=...)` normalises a leading slash away, so the member is built by hand
    -- otherwise the test would silently stop exercising the absolute-path branch."""
    import io
    arc = tmp_path / "bad.tar.gz"
    data = b"{}"
    with tarfile.open(arc, "w:gz") as tf:
        ti = tarfile.TarInfo(name)
        ti.size = len(data)
        tf.addfile(ti, io.BytesIO(data))
    with pytest.raises(BG.BundleGateError, match="unsafe archive members"):
        BG.verify_archive(str(arc), expected_sha256=_sha(open(arc, "rb").read()))


def test_symlink_member_is_refused(tmp_path):
    arc = tmp_path / "link.tar.gz"
    link = tmp_path / "evil"
    os.symlink("/etc/passwd", link)
    with tarfile.open(arc, "w:gz") as tf:
        tf.add(link, arcname="BUNDLE/evil")
    with pytest.raises(BG.BundleGateError, match="unsafe archive members"):
        BG.verify_archive(str(arc), expected_sha256=_sha(open(arc, "rb").read()))


# ---------------------------------------------------------------- loader binding
def test_empty_cache_is_an_error_not_a_silent_zero_load(tmp_path):
    root = tmp_path / "EMPTY"
    (root / CACHE).mkdir(parents=True)
    (root / "loader_adapter").mkdir(parents=True)
    with pytest.raises(BG.BundleGateError):
        BG.bind_loader_roots(str(root))


def test_version_stamp_records_the_repair():
    v = BG.version_stamp()
    assert v["checks_season_files"] is True
    assert v["trusts_manifest_beside_data"] is False
    assert v["falls_back_to_full_corpus"] is False
    assert v["empty_cache_is_an_error"] is True
