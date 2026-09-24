"""Freeze the completed Target-Aware V1.2 historical stats backfill.

Outcome-blind: validates only frozen provider discovery, historical fixture/stat payloads,
request provenance, PIT cutoffs, and CHAMPION integrity. No target settlement, market data,
model fitting, calibration, or OOS scoring is imported or executed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any

from src.research.thestatsapi.normalizer import parse_iso_to_unix

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/target_aware_market_panel"
DISCOVERY = OUT / "V1_2_BACKFILL_FIXTURE_DISCOVERY_V1.json"
PLAN = OUT / "V1_2_STATS_BACKFILL_PLAN_V1.json"
INVENTORY = OUT / "V1_2_PREHISTORY_INVENTORY.json"
MANIFEST = OUT / "V1_2_PREHISTORY_RAW_MANIFEST_V1.json"
RAW_ROOT = Path("/home/ubuntu/data/thestatsapi/v1_2_prehistory/stats_v1")
LEDGER = Path("/home/ubuntu/data/thestatsapi/v1_2_prehistory/stats_v1_attempts.jsonl")
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")

DISCOVERY_SHA256 = "219d95d9a4c14a2bef4aaa8fa5b25ff9b2b52698343fd469b2967b8e0a94a4ac"
PLAN_SHA256 = "751fde682b03ad568cd77925e2a87021ad0639f0a56b89a3f0e0b49202f0d03a"
CHAMPION_SHA256 = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
TERMINAL_STATUSES = {200, 404}


def fsha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout.strip()


def payload_sha(obj: Any) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def exact_fixture_index(discovery: dict[str, Any]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for season in discovery["seasons"]:
        comp = str(season["competition_id"])
        sid = str(season["season_id"])
        for mid in season["fixture_ids"]:
            if mid in out:
                raise RuntimeError(f"DUPLICATE_EXACT_FIXTURE_ID:{mid}")
            out[mid] = {"competition_id": comp, "season_id": sid}
    if len(out) != 4994 or len(out) != int(discovery["n_finished_fixtures"]):
        raise RuntimeError(f"EXACT_FIXTURE_SET_MISMATCH:{len(out)}")
    return out


def fixture_identity(fx: dict[str, Any]) -> tuple[Any, ...]:
    score = fx.get("score") or {}
    return (
        fx.get("utc_date"), (fx.get("home_team") or {}).get("id"),
        (fx.get("away_team") or {}).get("id"), score.get("home"), score.get("away"),
        fx.get("status"), bool(fx.get("is_neutral")), fx.get("competition_id"),
        fx.get("season_id"),
    )


def load_fixtures(discovery: dict[str, Any], exact: dict[str, dict[str, str]]) -> dict[str, Any]:
    versions: dict[str, dict[tuple[Any, ...], dict[str, Any]]] = defaultdict(dict)
    for page in discovery["raw_pages"]:
        path = Path(page["path"])
        if not path.exists() or fsha(path) != page["sha256"]:
            raise RuntimeError(f"DISCOVERY_PAGE_HASH_MISMATCH:{path}")
        wrapper = json.loads(path.read_text())
        params = wrapper.get("params") or {}
        if wrapper.get("endpoint") != "/football/matches":
            raise RuntimeError(f"DISCOVERY_ENDPOINT_MISMATCH:{path}")
        if str(params.get("competition_id")) != str(page["competition_id"]) or \
                str(params.get("season_id")) != str(page["season_id"]):
            raise RuntimeError(f"DISCOVERY_PAGE_SCOPE_MISMATCH:{path}")
        rows = ((wrapper.get("payload") or {}).get("data") or [])
        if len(rows) != int(page["n_rows"]):
            raise RuntimeError(f"DISCOVERY_PAGE_COUNT_MISMATCH:{path}")
        for fx in rows:
            if str(fx.get("status")).lower() != "finished":
                raise RuntimeError(f"NONFINISHED_DISCOVERY_FIXTURE:{fx.get('id')}")
            mid = str(fx.get("id"))
            versions[mid][fixture_identity(fx)] = fx
    fixtures: dict[str, Any] = {}
    for mid, vv in versions.items():
        if len(vv) != 1:
            raise RuntimeError(f"DISCOVERY_FIXTURE_CONFLICT:{mid}")
        fixtures[mid] = next(iter(vv.values()))
    if set(fixtures) != set(exact):
        missing = sorted(set(exact) - set(fixtures))[:5]
        extra = sorted(set(fixtures) - set(exact))[:5]
        raise RuntimeError(f"DISCOVERY_EXACT_SET_MISMATCH:missing={missing}:extra={extra}")
    for mid, fx in fixtures.items():
        e = exact[mid]
        if str(fx.get("competition_id")) != e["competition_id"] or \
                str(fx.get("season_id")) != e["season_id"]:
            raise RuntimeError(f"FIXTURE_SCOPE_MISMATCH:{mid}")
    return fixtures


def load_terminal(mid: str) -> dict[str, Any]:
    path = RAW_ROOT / f"{mid}.json"
    if not path.exists():
        raise RuntimeError(f"MISSING_TERMINAL_WRAPPER:{mid}")
    obj = json.loads(path.read_text())
    if obj.get("match_id") != mid or obj.get("endpoint") != f"/football/matches/{mid}/stats":
        raise RuntimeError(f"TERMINAL_ID_OR_ENDPOINT_MISMATCH:{mid}")
    status = int(obj.get("http_status", -1))
    if status not in TERMINAL_STATUSES:
        raise RuntimeError(f"NONTERMINAL_WRAPPER:{mid}:{status}")
    if status == 200:
        payload = obj.get("payload")
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), dict):
            raise RuntimeError(f"INVALID_200_PAYLOAD:{mid}")
        if str(payload["data"].get("match_id")) != mid:
            raise RuntimeError(f"STATS_PAYLOAD_MATCH_ID_MISMATCH:{mid}")
    elif obj.get("payload") is not None:
        raise RuntimeError(f"HTTP_404_WITH_PAYLOAD:{mid}")
    return obj


def audit_ledger(exact_ids: set[str], raw_hashes: dict[str, str]) -> dict[str, Any]:
    if not LEDGER.exists():
        raise RuntimeError("ATTEMPT_LEDGER_MISSING")
    starts: dict[str, int] = defaultdict(int)
    terminals: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors = 0
    for line in LEDGER.read_text().splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        mid = str(rec.get("match_id"))
        if mid not in exact_ids:
            raise RuntimeError(f"LEDGER_FOREIGN_FIXTURE:{mid}")
        event = rec.get("event")
        if event == "REQUEST_START":
            starts[mid] += 1
            if rec.get("endpoint") != f"/football/matches/{mid}/stats":
                raise RuntimeError(f"LEDGER_ENDPOINT_MISMATCH:{mid}")
        elif event == "REQUEST_TERMINAL":
            terminals[mid].append(rec)
        elif event == "REQUEST_ERROR":
            errors += 1
        else:
            raise RuntimeError(f"UNKNOWN_LEDGER_EVENT:{event}")
    if any(n > 2 for n in starts.values()):
        bad = sorted((m, n) for m, n in starts.items() if n > 2)[:5]
        raise RuntimeError(f"ATTEMPT_CAP_EXCEEDED:{bad}")
    for mid in exact_ids:
        if starts.get(mid, 0) < 1 or not terminals.get(mid):
            raise RuntimeError(f"LEDGER_TERMINAL_MISSING:{mid}")
        if not any(t.get("raw_sha256") == raw_hashes[mid] for t in terminals[mid]):
            raise RuntimeError(f"LEDGER_RAW_SHA_MISMATCH:{mid}")
    return {
        "sha256": fsha(LEDGER), "n_request_starts": sum(starts.values()),
        "n_request_errors": errors, "n_request_terminal_records": sum(map(len, terminals.values())),
        "max_attempts_for_any_fixture": max(starts.values()) if starts else 0,
    }


def build_manifest(authorized_head: str) -> dict[str, Any]:
    if git("rev-parse", "HEAD") != authorized_head:
        raise RuntimeError("HEAD_MISMATCH")
    if git("status", "--porcelain"):
        raise RuntimeError("WORKTREE_NOT_CLEAN")
    if fsha(DISCOVERY) != DISCOVERY_SHA256 or fsha(PLAN) != PLAN_SHA256:
        raise RuntimeError("FROZEN_INPUT_HASH_MISMATCH")
    if fsha(CHAMPION) != CHAMPION_SHA256:
        raise RuntimeError("CHAMPION_HASH_MISMATCH")
    discovery = json.loads(DISCOVERY.read_text())
    inventory = json.loads(INVENTORY.read_text())
    exact = exact_fixture_index(discovery)
    fixtures = load_fixtures(discovery, exact)
    cutoffs = {str(c["competition_id"]): int(c["first_frozen_kickoff_unix"])
               for c in inventory["competitions"]}

    raw_files: dict[str, Any] = {}
    per_season: dict[tuple[str, str], dict[str, Any]] = {}
    n200 = n404 = 0
    for mid in sorted(exact):
        fx = fixtures[mid]
        kickoff = parse_iso_to_unix(fx.get("utc_date"))
        comp, sid = exact[mid]["competition_id"], exact[mid]["season_id"]
        if kickoff is None or kickoff >= cutoffs[comp]:
            raise RuntimeError(f"BACKFILL_PIT_CUTOFF_VIOLATION:{mid}")
        wrapper = load_terminal(mid)
        status = int(wrapper["http_status"])
        sha = fsha(RAW_ROOT / f"{mid}.json")
        raw_files[mid] = {"sha256": sha, "http_status": status,
                          "competition_id": comp, "season_id": sid, "kickoff_unix": kickoff}
        key = (comp, sid)
        rec = per_season.setdefault(key, {"competition_id": comp, "season_id": sid,
                                          "n_fixtures": 0, "n_http_200": 0, "n_http_404": 0,
                                          "min_kickoff_unix": kickoff, "max_kickoff_unix": kickoff})
        rec["n_fixtures"] += 1
        rec["n_http_200"] += status == 200
        rec["n_http_404"] += status == 404
        rec["min_kickoff_unix"] = min(rec["min_kickoff_unix"], kickoff)
        rec["max_kickoff_unix"] = max(rec["max_kickoff_unix"], kickoff)
        n200 += status == 200
        n404 += status == 404
    extras = sorted(p.stem for p in RAW_ROOT.glob("*.json") if p.stem not in exact)
    if extras:
        raise RuntimeError(f"FOREIGN_RAW_FILES_PRESENT:{extras[:5]}")
    raw_hashes = {mid: rec["sha256"] for mid, rec in raw_files.items()}
    ledger = audit_ledger(set(exact), raw_hashes)
    aggregate = payload_sha([[mid, raw_files[mid]["sha256"], raw_files[mid]["http_status"]]
                             for mid in sorted(raw_files)])
    return {
        "artifact_version": "target_aware_v1_2_prehistory_raw_manifest_v1",
        "authorized_execution_head": authorized_head,
        "source_fixture_discovery_sha256": DISCOVERY_SHA256,
        "source_stats_backfill_plan_sha256": PLAN_SHA256,
        "source_inventory_sha256": fsha(INVENTORY),
        "champion_sha256": fsha(CHAMPION),
        "n_exact_fixture_ids": len(exact), "n_terminal": n200 + n404,
        "n_http_200": n200, "n_http_404": n404,
        "raw_root": str(RAW_ROOT), "attempt_ledger": ledger,
        "raw_files_aggregate_sha256": aggregate,
        "raw_files": raw_files,
        "per_season": [per_season[k] for k in sorted(per_season)],
        "target_outcomes_read": False, "market_results_read": False,
        "model_fit": False, "oos_executed": False, "champion_changed": False,
        "next_gate": "FREEZE_SUPPORT_EXECUTION_PLAN_THEN_RUN_OUTCOME_BLIND_V1_2_SUPPORT",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorized-head", required=True)
    args = ap.parse_args()
    if MANIFEST.exists():
        raise SystemExit(f"OUTPUT_ALREADY_EXISTS:{MANIFEST}")
    doc = build_manifest(args.authorized_head)
    MANIFEST.write_text(json.dumps(doc, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    print(json.dumps({
        "status": "V1_2_PREHISTORY_RAW_MANIFEST_FROZEN",
        "manifest_sha256": fsha(MANIFEST),
        "n_terminal": doc["n_terminal"], "n_http_200": doc["n_http_200"],
        "n_http_404": doc["n_http_404"], "raw_files_aggregate_sha256": doc["raw_files_aggregate_sha256"],
        "target_outcomes_read": False, "model_fit": False, "oos_executed": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
