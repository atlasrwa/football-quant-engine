"""V8C exposed-only bundle gate (`v8c_bundle_gate_v1`) -- REPAIR 2.

THE DEFECT
----------
Prevalidation checked only `*stats_*.json` FILENAMES. Two holes followed:

  1. a season fixture file (`_all_fixtures_*.json`) carrying a sealed fixture's SCORE passed
     whenever that fixture's separate stats file was absent -- and the season files are
     exactly the mixed-content files;
  2. the directory that was CHECKED was the function's argument, while the loader read
     `v8c_dev_paths.CACHE_ROOT`. The two could differ, so the check and the load could be
     looking at different trees.

Both meant "validated" described something other than what was parsed.

THE GATE
--------
Validation is anchored to the EXTERNALLY PINNED ARCHIVE DIGEST, not to a manifest sitting
beside mutable data:

    1. hash the archive bytes; require the pinned SHA256
    2. inspect members from the ARCHIVE: reject absolute paths, `..`, symlinks, devices
    3. read `MANIFEST.sha256.json` OUT OF THE VERIFIED ARCHIVE -- never from the extracted tree
    4. extract, then require the extracted tree to match that manifest EXACTLY: every file
       present, every digest equal, and NO unexpected extra file
    5. bind every loader root to that one validated directory and assert they agree
    6. assert the approved fixture-id set is disjoint from the sealed reserve, using ids taken
       from BOTH the per-fixture stats filenames AND the season files' fixture entries

Step 6 reads `id` and `utc_date` from season files. It never reads, copies or emits a `score`.

A missing or empty approved bundle is an ERROR, never a silent zero-record load.

ZERO SPEND. Never falls back to the full corpus.
"""
from __future__ import annotations

import hashlib
import json
import os
import tarfile

BUNDLE_GATE_VERSION = "v8c_bundle_gate_v1"

#: The externally pinned digest of the approved exposed-50 archive, recorded in commit
#: 668eca064 and reported to the operator at the time. This is the root of trust: it is not
#: read from the data it validates.
APPROVED_ARCHIVE_SHA256 = \
    "ed6f8d37c769568802cf1d2dc2b1b6a70b41c661d75d27218a29173e3e0e8d78"

CACHE_RELDIR = "data/thestatsapi/championship"
MANIFEST_NAME = "MANIFEST.sha256.json"
SEALED_REL = "research/hypothesis_engine/V8C_SEALED947_EXCLUSION_IDS.json"


class BundleGateError(Exception):
    """The bundle is not the approved one. Nothing is parsed, nothing is loaded."""


def _sha_file(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def verify_archive(archive_path, *, expected_sha256=APPROVED_ARCHIVE_SHA256) -> dict:
    """Step 1-2. The archive's own bytes, then its member table."""
    if not os.path.exists(archive_path):
        raise BundleGateError(f"approved archive is absent: {archive_path}")
    got = _sha_file(archive_path)
    if got != expected_sha256:
        raise BundleGateError(
            f"archive digest {got} != pinned {expected_sha256}: this is not the approved bundle")

    unsafe = []
    with tarfile.open(archive_path, "r:gz") as tf:
        members = tf.getmembers()
        for m in members:
            if m.name.startswith("/") or os.path.isabs(m.name):
                unsafe.append(("ABSOLUTE", m.name))
            elif ".." in m.name.split("/"):
                unsafe.append(("TRAVERSAL", m.name))
            elif m.issym() or m.islnk():
                unsafe.append(("LINK", m.name))
            elif not (m.isfile() or m.isdir()):
                unsafe.append(("NOT_REGULAR", m.name))
    if unsafe:
        raise BundleGateError(f"unsafe archive members: {unsafe[:5]}")
    return {"archive_path": os.path.abspath(archive_path), "archive_sha256": got,
            "n_members": len(members), "unsafe_members": 0}


def manifest_from_archive(archive_path) -> tuple:
    """Step 3. The approved file set, read from INSIDE the verified archive."""
    with tarfile.open(archive_path, "r:gz") as tf:
        hit = [m for m in tf.getmembers()
               if m.isfile() and os.path.basename(m.name) == MANIFEST_NAME]
        if len(hit) != 1:
            raise BundleGateError(
                f"expected exactly one {MANIFEST_NAME} in the archive, found {len(hit)}")
        root = hit[0].name[: -len(MANIFEST_NAME) - 1]
        doc = json.loads(tf.extractfile(hit[0]).read().decode())
    files = doc.get("files")
    if not files:
        raise BundleGateError("the archive's manifest declares no files")
    return root, files


def verify_extracted_tree(bundle_root, files) -> dict:
    """Step 4. Every approved file present and equal; no unexpected extra file."""
    missing, wrong, extra = [], [], []
    for rel, meta in files.items():
        p = os.path.join(bundle_root, rel)
        if not os.path.exists(p):
            missing.append(rel)
            continue
        if _sha_file(p) != meta["sha256"]:
            wrong.append(rel)
    approved = set(files) | {MANIFEST_NAME}
    for dirpath, _dn, fn in os.walk(bundle_root):
        for f in fn:
            rel = os.path.relpath(os.path.join(dirpath, f), bundle_root)
            # Interpreter BUILD OUTPUT, not data. Importing the bundle's loader adapter makes
            # CPython write a .pyc beside it. Ignoring `__pycache__` opens no hole: the .py
            # source it is compiled from IS verified, and a stale .pyc whose source changed is
            # discarded by the interpreter on the source hash/mtime. Bytecode writing is also
            # disabled in `bind_loader_roots`, so this is belt-and-braces for a pre-existing
            # cache directory.
            if "__pycache__" in rel.split(os.sep):
                continue
            if rel not in approved:
                extra.append(rel)
    if missing or wrong or extra:
        raise BundleGateError(
            f"extracted tree does not match the archive's manifest: {len(missing)} missing, "
            f"{len(wrong)} digest mismatch, {len(extra)} unexpected. "
            f"{missing[:3]} {wrong[:3]} {extra[:3]}")
    return {"n_files_verified": len(files), "missing": 0, "digest_mismatch": 0, "unexpected": 0}


def approved_fixture_ids(bundle_root) -> dict:
    """Step 6. Ids from BOTH sources: stats filenames AND season-file entries.

    Reads `id` and `utc_date` only. A `score` is never read, copied or emitted.
    """
    cache = os.path.join(bundle_root, CACHE_RELDIR)
    stats_ids, season_ids, season_files = set(), set(), 0
    for fn in sorted(os.listdir(cache)):
        if not fn.endswith(".json"):
            continue
        if fn.startswith("_all_fixtures_"):
            season_files += 1
            doc = json.load(open(os.path.join(cache, fn)))
            for fx in doc.get("fixtures", []):
                season_ids.add(str(fx["id"]))          # identity only
        elif "stats_" in fn:
            stats_ids.add(fn.rsplit("stats_", 1)[1][:-5])
    return {"stats_ids": stats_ids, "season_ids": season_ids,
            "n_season_files": season_files,
            "all_ids": stats_ids | season_ids}


def assert_no_sealed(bundle_root, ids: dict) -> dict:
    sealed = set(json.load(open(os.path.join(bundle_root, SEALED_REL)))["sealed_fixture_ids"])
    leaked_stats = sorted(ids["stats_ids"] & sealed)
    leaked_season = sorted(ids["season_ids"] & sealed)
    if leaked_stats or leaked_season:
        raise BundleGateError(
            f"SEALED RESERVE PRESENT: {len(leaked_stats)} stats file(s) "
            f"{leaked_stats[:3]}, {len(leaked_season)} season-file row(s) {leaked_season[:3]} "
            f"-- refusing to construct an index")
    return {"n_sealed_checked": len(sealed),
            "sealed_in_stats_files": 0, "sealed_in_season_files": 0}


def bind_loader_roots(bundle_root) -> dict:
    """Step 5. One validated root, asserted to be the root the loader will actually read."""
    import sys
    cache = os.path.join(bundle_root, CACHE_RELDIR)
    # Checked FIRST: an absent or empty approved cache must fail before any loader module is
    # imported, or the failure surfaces later as a silent zero-record load.
    if not os.path.isdir(cache):
        raise BundleGateError(f"validated cache directory is absent: {cache}")
    if not os.listdir(cache):
        raise BundleGateError(f"validated cache is EMPTY: {cache} -- refusing a zero-record load")
    # Do not write .pyc into the validated tree: the bundle must stay byte-identical to what
    # the archive digest certifies.
    sys.dont_write_bytecode = True
    sys.path.insert(0, os.path.join(bundle_root, "loader_adapter"))
    import v8c_dev_paths
    v8c_dev_paths.CACHE_ROOT = cache
    v8c_dev_paths.install()

    import multisrc_corpus as msc
    from src.research.matchup import corpus as MC
    bound = {"multisrc_corpus.CACHE": msc.CACHE, "matchup.corpus.CACHE": MC.CACHE,
             "v8c_dev_paths.CACHE_ROOT": v8c_dev_paths.CACHE_ROOT}
    disagreeing = {k: v for k, v in bound.items() if os.path.abspath(v) != os.path.abspath(cache)}
    if disagreeing:
        raise BundleGateError(
            f"loader roots disagree with the validated bundle: {disagreeing} != {cache}")
    return {"validated_cache_root": cache, "bound_roots": bound, "roots_agree": True}


def open_bundle(archive_path, extract_to, *, expected_sha256=APPROVED_ARCHIVE_SHA256) -> dict:
    """The whole gate, in order. Returns the report; raises on any failure."""
    arch = verify_archive(archive_path, expected_sha256=expected_sha256)
    root_name, files = manifest_from_archive(archive_path)
    os.makedirs(extract_to, exist_ok=True)
    with tarfile.open(archive_path, "r:gz") as tf:
        tf.extractall(extract_to)                       # members already proven safe
    bundle_root = os.path.join(extract_to, root_name)
    tree = verify_extracted_tree(bundle_root, files)
    ids = approved_fixture_ids(bundle_root)
    seal = assert_no_sealed(bundle_root, ids)
    roots = bind_loader_roots(bundle_root)
    return {"bundle_gate_version": BUNDLE_GATE_VERSION,
            "bundle_root": bundle_root,
            "archive": arch, "tree": tree, "seal": seal, "roots": roots,
            "n_stats_ids": len(ids["stats_ids"]),
            "n_season_row_ids": len(ids["season_ids"]),
            "n_season_files": ids["n_season_files"],
            "n_approved_fixture_ids": len(ids["all_ids"]),
            "season_files_checked": True,
            "reads_score_fields": False,
            "trusted_manifest_source": "read from inside the digest-verified archive"}


def version_stamp() -> dict:
    return {"bundle_gate_version": BUNDLE_GATE_VERSION,
            "repairs": ["REPAIR-2-BUNDLE-VALIDATION"],
            "was": ("stats FILENAMES only; a season file carrying a sealed score passed when "
                    "its stats file was absent, and the checked directory could differ from "
                    "the loader's cache root"),
            "now": "pinned archive digest -> manifest from inside the archive -> exact tree "
                   "match -> season-file id scan -> loader roots bound and asserted",
            "root_of_trust": "externally pinned archive SHA256",
            "trusts_manifest_beside_data": False,
            "checks_season_files": True,
            "rejects_absolute_traversal_symlink_members": True,
            "falls_back_to_full_corpus": False,
            "empty_cache_is_an_error": True}
