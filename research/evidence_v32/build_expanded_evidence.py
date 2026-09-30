"""Build V3.2.2 expanded offline evidence from two TheStatsAPI caches.

No network. Same-provider caches stay provenance-scoped. Conflicting finished
fixture identities/outcomes or conflicting raw stat payloads are quarantined.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
V321 = ROOT / "out/evidence_v1/evidence.jsonl"
LEGACY = Path("/home/ubuntu/data/thestatsapi/championship")
OUT = ROOT / "out/evidence_v2"
BUILDER_PATH = ROOT.parent / "three_family_evidence/build_evidence.py"

spec = importlib.util.spec_from_file_location("three_family_builder", BUILDER_PATH)
builder = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(builder)
def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def canonical(value: Any) -> str:
    return hashlib.sha256(json.dumps(
        value, sort_keys=True, separators=(",", ":"), default=str
    ).encode()).hexdigest()

def fixture_signature(fixture: dict) -> tuple:
    score = fixture.get("score") or {}
    reg = score.get("regulation") or {}
    return (
        str(fixture.get("competition_id")), str(fixture.get("season_id")),
        str(fixture.get("utc_date")),
        str((fixture.get("home_team") or {}).get("id")),
        str((fixture.get("away_team") or {}).get("id")),
        reg.get("home"), reg.get("away"),
        score.get("went_to_extra_time"), score.get("went_to_penalties"),
    )

def row_signature(row: dict) -> tuple:
    return (
        str(row.get("competition_id")), str(row.get("season_id")),
        str(row.get("kickoff")), str(row.get("home_id")), str(row.get("away_id")),
        (row.get("targets") or {}).get("goals.home", {}).get("value"),
        (row.get("targets") or {}).get("goals.away", {}).get("value"),
    )
def legacy_fixture_index():
    versions = defaultdict(list)
    scanned = 0
    for path in sorted(LEGACY.glob("*.json")):
        name = path.name
        if "matches_" not in name and not name.startswith("research_matches_"):
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        rows = obj.get("data", []) if isinstance(obj, dict) else []
        if not isinstance(rows, list):
            continue
        scanned += 1
        source = {
            "source_id": "LEGACY_THESTATSAPI_CACHE",
            "path": str(path),
            "sha256": sha(path),
            "availability": "RETROSPECTIVE_LEGACY_CACHE",
        }
        for fixture in rows:
            if not isinstance(fixture, dict) or fixture.get("status") != "finished":
                continue
            mid = str(fixture.get("id") or "")
            if mid:
                versions[mid].append((fixture, source))
    return versions, scanned

def canonical_legacy_fixtures():
    versions, scanned = legacy_fixture_index()
    fixtures = {}
    conflicts = []
    for mid, rows in versions.items():
        groups = defaultdict(list)
        for fixture, source in rows:
            groups[fixture_signature(fixture)].append((fixture, source))
        if len(groups) != 1:
            conflicts.append({"match_id": mid, "reason": "FINISHED_FIXTURE_CONFLICT"})
            continue
        fixture, source = next(iter(groups.values()))[-1]
        fixtures[mid] = (fixture, source)
    return fixtures, conflicts, scanned

def legacy_stats_index():
    versions = defaultdict(list)
    for path in sorted(LEGACY.glob("*_stats_mt_*.json")):
        match = re.search(r"(mt_\d+)", path.name)
        if not match:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        mid = match.group(1)
        data_mid = str(((payload or {}).get("data") or {}).get("match_id") or "")
        if data_mid and data_mid != mid:
            continue
        versions[mid].append((payload, path))
    selected = {}
    conflicts = []
    for mid, rows in versions.items():
        groups = defaultdict(list)
        for payload, path in rows:
            groups[canonical(payload)].append((payload, path))
        if len(groups) != 1:
            conflicts.append({"match_id": mid, "reason": "RAW_STATS_CONFLICT"})
            continue
        payload, path = next(iter(groups.values()))[-1]
        selected[mid] = (
            payload,
            {
                "source_id": "LEGACY_THESTATSAPI_CACHE",
                "path": str(path),
                "sha256": sha(path),
                "payload_sha256": canonical(payload),
                "availability": "RETROSPECTIVE_LEGACY_CACHE",
            },
        )
    return selected, conflicts

def build_legacy_rows():
    fixtures, fixture_conflicts, scanned = canonical_legacy_fixtures()
    stats, stats_conflicts = legacy_stats_index()
    blocked = {x["match_id"] for x in fixture_conflicts + stats_conflicts}
    rows = []
    for mid, (fixture, fixture_source) in sorted(fixtures.items()):
        if mid in blocked:
            continue
        stats_payload = None
        stats_source = None
        if mid in stats:
            stats_payload, stats_source = stats[mid]
        provenance = {
            "fixture": fixture_source,
            "stats": stats_source,
            "source_scope": "LEGACY_THESTATSAPI_CACHE",
        }
        try:
            row = builder.normalize(fixture, stats_payload, provenance)
        except ValueError:
            continue
        rows.append(row)
    return rows, fixture_conflicts + stats_conflicts, {
        "match_files_scanned": scanned,
        "finished_fixtures": len(fixtures),
        "stats_payloads": len(stats),
    }

def read_v321_rows():
    return [
        json.loads(line) for line in V321.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
def merge_rows(primary_rows, legacy_rows):
    primary = {str(r["match_id"]): r for r in primary_rows}
    merged = dict(primary)
    conflicts = []
    duplicate_same = 0
    upgraded_stats = 0
    for row in legacy_rows:
        mid = str(row["match_id"])
        existing = merged.get(mid)
        if existing is None:
            merged[mid] = row
            continue
        if row_signature(existing) != row_signature(row):
            conflicts.append({"match_id": mid, "reason": "CROSS_CACHE_FIXTURE_CONFLICT"})
            merged.pop(mid, None)
            continue
        old_stats = existing.get("raw_stats") or {}
        new_stats = row.get("raw_stats") or {}
        if old_stats and new_stats and canonical(old_stats) != canonical(new_stats):
            conflicts.append({"match_id": mid, "reason": "CROSS_CACHE_STATS_CONFLICT"})
            merged.pop(mid, None)
            continue
        if not old_stats and new_stats:
            merged[mid] = row
            upgraded_stats += 1
        else:
            duplicate_same += 1
    rows = sorted(merged.values(), key=lambda r: (r["kickoff_ts"], r["match_id"]))
    return rows, conflicts, duplicate_same, upgraded_stats

def coverage(rows):
    targets = {}
    if rows:
        for key in rows[0]["targets"]:
            values = [r["targets"][key] for r in rows]
            targets[key] = {
                "fixtures": len(rows),
                "available_raw": sum(v.get("value") is not None for v in values),
                "period_resolved_raw": sum(
                    v.get("value") is not None
                    and v.get("period_status") != "PERIOD_UNRESOLVED" for v in values
                ),
            }
    return {
        "version": "V32_2_EXPANDED_EVIDENCE_1",
        "mode": "OFFLINE_RETROSPECTIVE_RECONSTRUCTION",
        "fixtures": len(rows),
        "stats_payloads": sum(bool(r.get("raw_stats")) for r in rows),
        "competitions": dict(Counter(str(r["competition_id"]) for r in rows)),
        "targets": targets,
        "period_mismatch_fixtures": sum(bool(r.get("period_checks")) for r in rows),
        "corpus_sha256": canonical(rows),
        "prediction_input_eligible": False,
        "live_calls": 0,
    }

def main():
    if OUT.exists():
        raise RuntimeError("immutable V32.2 evidence output already exists")
    primary_rows = read_v321_rows()
    legacy_rows, legacy_conflicts, legacy_summary = build_legacy_rows()
    rows, cross_conflicts, duplicate_same, upgraded_stats = merge_rows(
        primary_rows, legacy_rows
    )
    OUT.mkdir(parents=True)
    evidence_path = OUT / "evidence.jsonl"
    evidence_path.write_text(
        "".join(json.dumps(r, sort_keys=True) + "\n" for r in rows),
        encoding="utf-8",
    )
    report = coverage(rows)
    report.update({
        "primary_v321_rows": len(primary_rows),
        "legacy_normalized_rows": len(legacy_rows),
        "legacy_summary": legacy_summary,
        "legacy_conflicts": legacy_conflicts,
        "cross_cache_conflicts": cross_conflicts,
        "duplicate_same_identity": duplicate_same,
        "upgraded_stats_from_legacy": upgraded_stats,
    })
    (OUT / "coverage.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    manifest = {
        "version": report["version"],
        "spec_sha256": sha(ROOT / "SPEC_V32_2.json"),
        "builder_sha256": sha(Path(__file__)),
        "v321_evidence_sha256": sha(V321),
        "evidence_sha256": sha(evidence_path),
        "coverage_sha256": sha(OUT / "coverage.json"),
        "live_calls": 0,
        "quarantined_matches": len(legacy_conflicts) + len(cross_conflicts),
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "fixtures": report["fixtures"],
        "stats_payloads": report["stats_payloads"],
        "competitions": report["competitions"],
        "legacy_summary": legacy_summary,
        "quarantined_matches": manifest["quarantined_matches"],
        "duplicate_same_identity": duplicate_same,
        "upgraded_stats_from_legacy": upgraded_stats,
    }, indent=2, sort_keys=True))

if __name__ == "__main__":
    main()
