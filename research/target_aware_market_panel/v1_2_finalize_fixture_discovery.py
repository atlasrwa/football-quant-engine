"""Zero-network recovery for the completed V1.2 fixture discovery first pass.

The live runner at 5a79c8aff fetched all pages successfully but raised only after
completion because ProspectiveApiClient has no close() method. This recovery
validates and freezes the staged first-pass payloads without any network call.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from research.target_aware_market_panel.v1_2_fixture_discovery import (  # noqa: E402
    PLAN, INVENTORY, PLAN_SHA256, INVENTORY_SHA256, CHAMPION, CHAMPION_SHA256,
    RAW_ROOT, STAGE_ROOT, OUTPUT, _validate_fixture, dump, fsha,
)

SOURCE_FAILED_HEAD = "5a79c8aff17e4c5dc18d9b944116019a3a5ac986"
EXPECTED_RAW_PAGES = 54
EXPECTED_FINISHED_FIXTURES = 4994


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True, capture_output=True, text=True
    ).stdout.strip()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorized-head", required=True)
    args = ap.parse_args()
    head = git("rev-parse", "HEAD")
    if head != args.authorized_head:
        raise SystemExit(f"HEAD_MISMATCH expected={args.authorized_head} actual={head}")
    if git("status", "--porcelain"):
        raise SystemExit("WORKTREE_NOT_CLEAN")
    if fsha(PLAN) != PLAN_SHA256 or fsha(INVENTORY) != INVENTORY_SHA256:
        raise SystemExit("UPSTREAM_HASH_MISMATCH")
    if fsha(CHAMPION) != CHAMPION_SHA256:
        raise SystemExit("CHAMPION_HASH_MISMATCH")
    if not STAGE_ROOT.is_dir() or RAW_ROOT.exists() or OUTPUT.exists():
        raise SystemExit("RECOVERY_PATH_STATE_INVALID")
    plan = json.loads(PLAN.read_text())
    inventory = json.loads(INVENTORY.read_text())
    cutoffs = {x["competition_id"]: int(x["first_frozen_kickoff_unix"])
               for x in inventory["competitions"]}
    expected_pairs = {
        (c["competition_id"], s["season_id"])
        for c in plan["competitions"] for s in c["selected_prior_seasons"]
    }
    season_names = {
        (c["competition_id"], s["season_id"]): s["name"]
        for c in plan["competitions"] for s in c["selected_prior_seasons"]
    }

    files = sorted(STAGE_ROOT.glob("*.json"))
    if len(files) != EXPECTED_RAW_PAGES:
        raise SystemExit(f"RAW_PAGE_COUNT_MISMATCH:{len(files)}")

    pages = defaultdict(dict)
    raw_pages = []
    all_ids = set()
    for path in files:
        wrapper = json.loads(path.read_text())
        if wrapper.get("provider") != "thestatsapi":
            raise SystemExit(f"PROVIDER_MISMATCH:{path.name}")
        if wrapper.get("endpoint") != "/football/matches":
            raise SystemExit(f"ENDPOINT_MISMATCH:{path.name}")
        params = wrapper.get("params") or {}
        comp, season = str(params.get("competition_id")), str(params.get("season_id"))
        pair = (comp, season)
        if pair not in expected_pairs:
            raise SystemExit(f"UNPLANNED_SEASON:{pair}")
        if params.get("stage") != "regular" or params.get("status") != "finished" \
                or int(params.get("per_page", 0)) != 100:
            raise SystemExit(f"PARAM_SCOPE_MISMATCH:{path.name}")
        page = int(params.get("page"))
        if page in pages[pair]:
            raise SystemExit(f"DUPLICATE_PAGE:{pair}:{page}")
        payload = wrapper.get("payload")
        if not isinstance(payload, dict):
            raise SystemExit(f"INVALID_PAYLOAD:{path.name}")
        meta = payload.get("metadata") or payload.get("meta") or {}
        total_pages = int(meta.get("total_pages") or meta.get("last_page") or 1)
        rows = payload.get("data") or []
        if not isinstance(rows, list):
            raise SystemExit(f"INVALID_DATA_LIST:{path.name}")
        fixture_map = {}
        for fx in rows:
            mid, ko = _validate_fixture(fx, comp=comp, season=season, cutoff=cutoffs[comp])
            if mid in fixture_map or mid in all_ids:
                raise SystemExit(f"DUPLICATE_FIXTURE:{mid}")
            fixture_map[mid] = {"match_id": mid, "kickoff_unix": ko}
            all_ids.add(mid)
        pages[pair][page] = {
            "total_pages": total_pages,
            "fixture_map": fixture_map,
            "raw_path": path,
        }
        raw_pages.append({
            "competition_id": comp,
            "season_id": season,
            "page": page,
            "path": str(RAW_ROOT / path.name),
            "sha256": fsha(path),
            "n_rows": len(rows),
            "retrieved_at_unix": wrapper.get("retrieved_at_unix"),
            "retrieved_at_utc": wrapper.get("retrieved_at_utc"),
        })
    if set(pages) != expected_pairs:
        raise SystemExit("PLANNED_SEASON_SET_MISMATCH")

    seasons = []
    for pair in sorted(expected_pairs):
        comp, season = pair
        pmap = pages[pair]
        totals = {x["total_pages"] for x in pmap.values()}
        if len(totals) != 1:
            raise SystemExit(f"TOTAL_PAGES_CONFLICT:{pair}")
        total_pages = next(iter(totals))
        if sorted(pmap) != list(range(1, total_pages + 1)):
            raise SystemExit(f"INCOMPLETE_PAGINATION:{pair}")
        ids = sorted(mid for x in pmap.values() for mid in x["fixture_map"])
        seasons.append({
            "competition_id": comp,
            "season_id": season,
            "season_name": season_names[pair],
            "n_pages": total_pages,
            "n_finished_fixtures": len(ids),
            "fixture_ids": ids,
        })

    if len(all_ids) != EXPECTED_FINISHED_FIXTURES:
        raise SystemExit(f"FIXTURE_COUNT_MISMATCH:{len(all_ids)}")

    RAW_ROOT.parent.mkdir(parents=True, exist_ok=True)
    os.replace(STAGE_ROOT, RAW_ROOT)

    doc = {
        "artifact_version": "target_aware_v1_2_backfill_fixture_discovery_v1",
        "authorized_recovery_head": head,
        "source_failed_live_head": SOURCE_FAILED_HEAD,
        "recovered_from_staged_first_pass": True,
        "recovery_network_calls": 0,
        "source_plan_sha256": PLAN_SHA256,
        "source_inventory_sha256": INVENTORY_SHA256,
        "provider": "TheStatsAPI",
        "endpoint_used": "/football/matches",
        "logical_requests_used": EXPECTED_RAW_PAGES,
        "actual_first_pass_page_payloads": EXPECTED_RAW_PAGES,
        "client_max_retries": 1,
        "hard_global_request_cap": int(plan["fixture_discovery"]["hard_global_request_cap"]),
        "n_seasons": len(seasons),
        "n_finished_fixtures": len(all_ids),
        "planned_stats_requests": len(all_ids),
        "raw_page_count": len(raw_pages),
        "raw_pages": sorted(raw_pages, key=lambda x: (x["competition_id"], x["season_id"], x["page"])),
        "seasons": seasons,
        "last_rate_limit": None,
        "last_rate_limit_note": "not frozen because the completed first-pass runner failed during nonexistent client.close() cleanup before manifest serialization",
        "stats_requests_made": 0,
        "odds_requests_made": 0,
        "lineup_requests_made": 0,
        "injury_requests_made": 0,
        "target_outcomes_read": False,
        "market_results_read": False,
        "model_fit": False,
        "oos_executed": False,
        "champion_sha256": fsha(CHAMPION),
        "defect": {
            "type": "POST_FETCH_CLEANUP_ATTRIBUTE_ERROR",
            "message": "ProspectiveApiClient has no close() method",
            "scientific_inputs_changed": False,
            "provider_calls_retried": False,
        },
        "next_gate": "FREEZE_EXACT_FIXTURE_DISCOVERY_THEN_AUTHORIZE_STATS_BACKFILL",
    }
    out_sha = dump(OUTPUT, doc)
    print(json.dumps({
        "status": "V1_2_FIXTURE_DISCOVERY_RECOVERED_AND_FROZEN",
        "authorized_recovery_head": head,
        "recovery_network_calls": 0,
        "raw_pages": len(raw_pages),
        "n_finished_fixtures": len(all_ids),
        "planned_stats_requests": len(all_ids),
        "output_sha256": out_sha,
        "target_outcomes_read": False,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
