"""Outcome-safe integrity check for the V8C exposed-50 development bundle.

Verifies packaging, not scientific performance. Invokes no scorer, no aggregation, no
model, and no reserve preflight. Reads no `score` field of any fixture row.

    python3 verify_bundle.py [bundle_dir]     # default: this file's directory
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import sys

BUNDLE = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(__file__))
MAN = os.path.join(BUNDLE, "MANIFEST.sha256.json")

fails, warns = [], []


def check(ok, msg):
    print(("  PASS  " if ok else "  FAIL  ") + msg)
    if not ok:
        fails.append(msg)


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


m = json.load(open(MAN))
print(f"bundle   {BUNDLE}\nmanifest {m['bundle_version']}  built {m['export_timestamp_utc']}\n")

# ---------------------------------------------------------------- 1. checksums
print("[1] checksums + sizes")
bad_sha = bad_size = missing = 0
for rel, e in sorted(m["files"].items()):
    p = os.path.join(BUNDLE, rel)
    if not os.path.exists(p):
        missing += 1
        continue
    if sha(p) != e["sha256"]:
        bad_sha += 1
    if os.path.getsize(p) != e["size_bytes"]:
        bad_size += 1
check(missing == 0, f"all {len(m['files'])} manifest files present (missing={missing})")
check(bad_sha == 0, f"sha256 matches for every file (mismatches={bad_sha})")
check(bad_size == 0, f"size matches for every file (mismatches={bad_size})")

extra = []
for dirpath, _dn, fn in os.walk(BUNDLE):
    for f in fn:
        rel = os.path.relpath(os.path.join(dirpath, f), BUNDLE)
        if rel not in m["files"] and rel != "MANIFEST.sha256.json":
            extra.append(rel)
check(not extra, f"no unmanifested files on disk ({len(extra)} extra)")
for x in extra[:10]:
    print(f"          extra: {x}")

# ---------------------------------------------------------------- 2. no absolute paths
print("\n[2] path hygiene")
abs_p = [r for r in m["files"] if os.path.isabs(r) or r.startswith("/")]
trav = [r for r in m["files"] if ".." in r.split("/")]
links = []
for dirpath, dn, fn in os.walk(BUNDLE):
    for f in list(dn) + fn:
        if os.path.islink(os.path.join(dirpath, f)):
            links.append(os.path.join(dirpath, f))
check(not abs_p, "no absolute paths in manifest")
check(not trav, "no `..` traversal in manifest")
check(not links, f"no symlinks on disk ({len(links)} found)")

# ---------------------------------------------------------------- 3. cohort accounting
print("\n[3] exposed-50 accounting")
ENG = os.path.join(BUNDLE, "research", "hypothesis_engine")
freeze = json.load(open(os.path.join(ENG, "V8B1_PILOT50_SELECTION_FREEZE.json")))
exposed = list(freeze["pilot_fixture_ids_ordered"])
check(len(exposed) == 50, f"selection freeze declares exactly 50 fixtures ({len(exposed)})")
check(sorted(exposed) == sorted(m["exposed_50_fixture_ids"]),
      "manifest fixture ids == selection-freeze fixture ids")

CACHE = os.path.join(BUNDLE, "data", "thestatsapi", "championship")
present_ids, cutoff = set(), int(m["pit_cutoff"]["cutoff_unix_inclusive"])
late = []
for f in sorted(os.listdir(CACHE)):
    if not f.startswith("_all_fixtures_"):
        continue
    for fx in json.load(open(os.path.join(CACHE, f)))["fixtures"]:   # id + utc_date only
        fid = str(fx["id"])
        present_ids.add(fid)
        u = int(dt.datetime.fromisoformat(fx["utc_date"].replace("Z", "+00:00")).timestamp())
        if u > cutoff:
            late.append(fid)
check(not late, f"no fixture row kicks off after the cutoff ({len(late)} late rows)")

missing_row = [f for f in exposed if f not in present_ids]
check(not missing_row, f"all 50 exposed fixtures have a fixture row ({len(missing_row)} missing)")

no_stats = [f for f in exposed
            if not (os.path.exists(os.path.join(CACHE, f"stats_{f}.json"))
                    or any(os.path.exists(os.path.join(CACHE, f"{p}_stats_{f}.json"))
                           for p in ("epl", "laliga", "laliga2", "ligue1", "ligue2")))]
check(not no_stats, f"all 50 exposed fixtures have a stats file ({len(no_stats)} missing)")

# ---------------------------------------------------------------- 4. reserve boundary
print("\n[4] sealed-reserve boundary")
sealed = set(json.load(open(os.path.join(ENG, "V8C_SEALED947_EXCLUSION_IDS.json")))
             ["sealed_fixture_ids"])
check(len(sealed) == 947, f"exclusion list holds 947 ids ({len(sealed)})")
inter = present_ids & sealed
check(not inter, f"bundle fixture ids INTERSECT sealed reserve == {{}} ({len(inter)} leaked)")

stats_ids = {fn.split("stats_")[-1][:-5] for fn in os.listdir(CACHE) if "stats_" in fn}
inter2 = stats_ids & sealed
check(not inter2, f"no sealed fixture has a stats file in the bundle ({len(inter2)} leaked)")
check(int(m["pit_cutoff"]["min_sealed_kickoff_unix"]) > cutoff,
      "earliest sealed kickoff is strictly after the cutoff")

# ---------------------------------------------------------------- 5. secrets
print("\n[5] excluded-material sweep")
bad = [r for r in m["files"] if any(t in r.lower() for t in
       (".env", ".ssh", ".aws", "credential", "id_rsa", "bash_history", ".git-credentials",
        "secret", "token"))]
check(not bad, f"no credential/secret-shaped path in the manifest ({len(bad)})")

print("\n" + ("BUNDLE VERIFY: PASS" if not fails else
             f"BUNDLE VERIFY: FAIL ({len(fails)} checks)"))
print("NOTE: packaging only. No scorer, no aggregation, no model call, no reserve preflight.")
print("NOTE: CHAMPION is NOT shipped here -- verify it in the receiving checkout:")
print("      sha256sum data/discovery/pilotC_stat_mixer.json  ->")
print(f"      {m['champion']['expected_sha256']}")
sys.exit(1 if fails else 0)
