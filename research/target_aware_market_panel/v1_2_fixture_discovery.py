"""Bounded V1.2 fixture-list discovery for the frozen two-season backfill plan.

This stage calls ONLY TheStatsAPI MATCHES. It fetches no per-match stats, odds,
lineups, injuries, target labels, model outputs or market results.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.discovery.corpus import _load_env_for_thestats  # noqa: E402
from src.research.prospective.api_contract import Endpoint, ProspectiveClientConfig  # noqa: E402
from src.research.prospective.capture import ProspectiveApiClient  # noqa: E402
from src.research.thestatsapi.normalizer import parse_iso_to_unix  # noqa: E402

OUT = ROOT / "research/target_aware_market_panel"
PLAN = OUT / "V1_2_BACKFILL_DISCOVERY_PLAN_V1.json"
INVENTORY = OUT / "V1_2_PREHISTORY_INVENTORY.json"
OUTPUT = OUT / "V1_2_BACKFILL_FIXTURE_DISCOVERY_V1.json"
RAW_ROOT = Path("/home/ubuntu/data/thestatsapi/v1_2_prehistory/discovery_v1")
STAGE_ROOT = Path("/home/ubuntu/data/thestatsapi/v1_2_prehistory/.discovery_v1_staging")
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
PLAN_SHA256 = "cd841da6325173bf373ea1f104756be9908e2530c9e6343fceba81e337dc63db"
INVENTORY_SHA256 = "bc15255ddc068f947c1e427b13aafa72ccdbd164c615456b9e48b8e3cbd8e450"
CHAMPION_SHA256 = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
def fsha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True, capture_output=True, text=True
    ).stdout.strip()


def dump(path: Path, obj) -> str:
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return fsha(path)


def _utc(ts: float) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).isoformat().replace("+00:00", "Z")


def _page_count(payload: dict) -> int:
    meta = payload.get("metadata") or payload.get("meta") or {}
    raw = meta.get("total_pages") or meta.get("last_page") or 1
    n = int(raw)
    if n < 1:
        raise ValueError("invalid provider total_pages")
    return n


def _validate_fixture(fx: dict, *, comp: str, season: str, cutoff: int) -> tuple[str, int]:
    if not isinstance(fx, dict) or not fx.get("id"):
        raise ValueError("fixture missing id")
    if str(fx.get("status", "")).lower() != "finished":
        raise ValueError(f"non-finished fixture {fx.get('id')}")
    if str(fx.get("competition_id")) != comp:
        raise ValueError(f"competition mismatch {fx.get('id')}")
    if fx.get("season_id") is not None and str(fx.get("season_id")) != season:
        raise ValueError(f"season mismatch {fx.get('id')}")
    ko = parse_iso_to_unix(fx.get("utc_date"))
    if ko is None or int(ko) >= int(cutoff):
        raise ValueError(f"kickoff outside frozen prehistory {fx.get('id')}")
    return str(fx["id"]), int(ko)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorized-head", required=True)
    args = ap.parse_args()
    head = git("rev-parse", "HEAD")
    if head != args.authorized_head:
        raise SystemExit(f"HEAD_MISMATCH expected={args.authorized_head} actual={head}")
    if git("status", "--porcelain"):
        raise SystemExit("WORKTREE_NOT_CLEAN")
    if fsha(PLAN) != PLAN_SHA256:
        raise SystemExit("DISCOVERY_PLAN_HASH_MISMATCH")
    if fsha(INVENTORY) != INVENTORY_SHA256:
        raise SystemExit("INVENTORY_HASH_MISMATCH")
    if fsha(CHAMPION) != CHAMPION_SHA256:
        raise SystemExit("CHAMPION_HASH_MISMATCH")
    if OUTPUT.exists() or RAW_ROOT.exists() or STAGE_ROOT.exists():
        raise SystemExit("DISCOVERY_OUTPUT_ALREADY_EXISTS")

    plan = json.loads(PLAN.read_text())
    inventory = json.loads(INVENTORY.read_text())
    cutoffs = {x["competition_id"]: int(x["first_frozen_kickoff_unix"])
               for x in inventory["competitions"]}
    cap = int(plan["fixture_discovery"]["hard_global_request_cap"])
    if plan["n_selected_seasons"] != 12 or plan["stats_requests_this_stage"] != 0:
        raise SystemExit("PLAN_SCOPE_MISMATCH")

    _load_env_for_thestats()
    client = ProspectiveApiClient(
        ProspectiveClientConfig(max_retries=1, rate_limit_seconds=1.0)
    )
    if not client.is_configured:
        raise SystemExit("THESTATSAPI_KEY_UNAVAILABLE")

    STAGE_ROOT.mkdir(parents=True, exist_ok=False)
    logical_calls = 0
    raw_pages = []
    season_results = []
    all_ids = set()
    try:
        for comp_rec in plan["competitions"]:
            comp = comp_rec["competition_id"]
            cutoff = cutoffs[comp]
            for srec in comp_rec["selected_prior_seasons"]:
                season = srec["season_id"]
                page = 1
                total_pages = None
                fixtures = {}
                while total_pages is None or page <= total_pages:
                    if logical_calls >= cap:
                        raise RuntimeError("DISCOVERY_REQUEST_CAP_EXHAUSTED")
                    params = {
                        "competition_id": comp,
                        "season_id": season,
                        "stage": "regular",
                        "status": "finished",
                        "per_page": 100,
                        "page": page,
                    }
                    retrieved = time.time()
                    payload = client.get(Endpoint.MATCHES, params=params)
                    logical_calls += 1
                    if not isinstance(payload, dict):
                        raise ValueError("provider payload is not an object")
                    total_pages = _page_count(payload)
                    rows = payload.get("data") or []
                    if not isinstance(rows, list):
                        raise ValueError("provider data is not a list")
                    wrapper = {
                        "provider": "thestatsapi",
                        "endpoint": Endpoint.MATCHES.value,
                        "params": params,
                        "retrieved_at_unix": retrieved,
                        "retrieved_at_utc": _utc(retrieved),
                        "payload": payload,
                    }
                    raw_path = STAGE_ROOT / f"{comp}__{season}__p{page}.json"
                    raw_sha = dump(raw_path, wrapper)
                    raw_pages.append({
                        "competition_id": comp, "season_id": season, "page": page,
                        "path": str(RAW_ROOT / raw_path.name),
                        "sha256": raw_sha, "n_rows": len(rows),
                    })
                    for fx in rows:
                        mid, ko = _validate_fixture(fx, comp=comp, season=season, cutoff=cutoff)
                        if mid in fixtures:
                            raise ValueError(f"duplicate fixture across pages {mid}")
                        fixtures[mid] = {"match_id": mid, "kickoff_unix": ko}
                    page += 1
                season_ids = sorted(fixtures)
                overlap = all_ids.intersection(season_ids)
                if overlap:
                    raise ValueError(f"fixture appears in multiple frozen seasons: {sorted(overlap)[:3]}")
                all_ids.update(season_ids)
                season_results.append({
                    "competition_id": comp,
                    "season_id": season,
                    "season_name": srec["name"],
                    "n_pages": total_pages,
                    "n_finished_fixtures": len(season_ids),
                    "fixture_ids": season_ids,
                })
    finally:
        client.close()

    RAW_ROOT.parent.mkdir(parents=True, exist_ok=True)
    os.replace(STAGE_ROOT, RAW_ROOT)

    quota = None
    if client.last_rate_limit is not None:
        quota = json.loads(json.dumps(vars(client.last_rate_limit), default=str))
    doc = {
        "artifact_version": "target_aware_v1_2_backfill_fixture_discovery_v1",
        "authorized_execution_head": head,
        "source_plan_sha256": PLAN_SHA256,
        "source_inventory_sha256": INVENTORY_SHA256,
        "provider": "TheStatsAPI",
        "endpoint_used": Endpoint.MATCHES.value,
        "logical_requests_used": logical_calls,
        "client_max_retries": 1,
        "hard_global_request_cap": cap,
        "n_seasons": len(season_results),
        "n_finished_fixtures": len(all_ids),
        "planned_stats_requests": len(all_ids),
        "raw_page_count": len(raw_pages),
        "raw_pages": sorted(raw_pages, key=lambda x: (x["competition_id"], x["season_id"], x["page"])),
        "seasons": sorted(season_results, key=lambda x: (x["competition_id"], x["season_id"])),
        "last_rate_limit": quota,
        "stats_requests_made": 0,
        "odds_requests_made": 0,
        "lineup_requests_made": 0,
        "injury_requests_made": 0,
        "target_outcomes_read": False,
        "market_results_read": False,
        "model_fit": False,
        "oos_executed": False,
        "champion_sha256": fsha(CHAMPION),
        "next_gate": "FREEZE_EXACT_FIXTURE_DISCOVERY_THEN_AUTHORIZE_STATS_BACKFILL",
    }
    out_sha = dump(OUTPUT, doc)
    print(json.dumps({
        "status": "V1_2_FIXTURE_DISCOVERY_COMPLETE",
        "authorized_execution_head": head,
        "logical_requests_used": logical_calls,
        "n_seasons": len(season_results),
        "n_finished_fixtures": len(all_ids),
        "planned_stats_requests": len(all_ids),
        "output_sha256": out_sha,
        "target_outcomes_read": False,
        "stats_requests_made": 0,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
