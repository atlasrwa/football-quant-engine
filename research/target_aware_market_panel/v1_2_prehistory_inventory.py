"""Outcome-blind prehistory inventory for Target-Aware Market Panel V1.2.

This step makes no network calls, settles no targets and fits no model. It inventories the
existing TheStatsAPI cache so the exact two-prior-season backfill can be frozen separately.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.research.target_aware_market_panel import cohort_packets as CP  # noqa: E402

PANEL_DIR = ROOT / "research/target_aware_market_panel"
CACHE = "/home/ubuntu/data/thestatsapi/championship"
FOLD_MANIFEST = PANEL_DIR / "TARGET_AWARE_FOLD_MANIFEST_V1.json"
SUPPORT_MANIFEST = PANEL_DIR / "SOL_PANEL_SUPPORT_FREEZE_MANIFEST_V1.json"
GATE_DECISION = PANEL_DIR / "V1_OOS_GATE_DECISION_V1.json"
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")

SOURCE_V1_GATE_HEAD = "773b851650410cfeb4a3bff2f08ce3e722017ade"
EXPECTED_FOLD_ROWS_SHA256 = "9fca0ec2860ed13cda0368502978445b9444419eece690cba685449c26bf3270"
EXPECTED_SUPPORT_DIAGNOSTICS_SHA256 = "2c77a3df577e5b0767ed9002b899f83fd2c77fa3287b20dc8af6200a86f886b2"
EXPECTED_CHAMPION_SHA256 = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
OUTPUT = PANEL_DIR / "V1_2_PREHISTORY_INVENTORY.json"


def fsha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args],
        check=True,
        capture_output=True,
        text=True,
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
    anc = subprocess.run(
        ["git", "-C", str(ROOT), "merge-base", "--is-ancestor", SOURCE_V1_GATE_HEAD, head]
    )
    if anc.returncode != 0:
        raise SystemExit("V1_GATE_HEAD_NOT_ANCESTOR")
    if fsha(CHAMPION) != EXPECTED_CHAMPION_SHA256:
        raise SystemExit("CHAMPION_HASH_MISMATCH")
    if OUTPUT.exists():
        raise SystemExit(f"OUTPUT_ALREADY_EXISTS:{OUTPUT.name}")

    folds = json.loads(FOLD_MANIFEST.read_text())
    if folds["n_panel_rows"] != 5620 or folds["rows_sha256"] != EXPECTED_FOLD_ROWS_SHA256:
        raise SystemExit("FOLD_MANIFEST_MISMATCH")

    support = json.loads(SUPPORT_MANIFEST.read_text())
    if support["diagnostics_sha256"] != EXPECTED_SUPPORT_DIAGNOSTICS_SHA256:
        raise SystemExit("SUPPORT_MANIFEST_MISMATCH")
    if support["target_outcomes_read"] or support["model_fit"] or support["oos_executed"]:
        raise SystemExit("SUPPORT_FIREWALL_STATE_INVALID")

    gate = json.loads(GATE_DECISION.read_text())
    if gate.get("decision") != "ABORT_V1_PREDICTIVE_OOS_BEFORE_OUTCOME_ACCESS":
        raise SystemExit("V1_GATE_DECISION_MISMATCH")
    if gate.get("target_outcomes_read") or gate.get("model_fit") or gate.get("oos_executed"):
        raise SystemExit("V1_GATE_FIREWALL_STATE_INVALID")

    history, hmeta = CP.load_history(CACHE, include_gap_fetches=False)
    panel_rows = folds["rows"]

    by_comp_panel = defaultdict(list)
    for r in panel_rows:
        by_comp_panel[str(r["competition_id"])].append(r)

    competitions = []
    all_missing_panel_fixtures = []
    for comp, rows in sorted(by_comp_panel.items()):
        rows = sorted(rows, key=lambda r: (r["kickoff"], r["match_id"]))
        first = rows[0]
        first_hm = history.get(first["match_id"])
        if first_hm is None:
            all_missing_panel_fixtures.append(first["match_id"])
            first_season = None
        else:
            first_season = str(first_hm.fixture.get("season_id"))

        cached = [
            h for h in history.values()
            if str(h.fixture.get("competition_id")) == comp and h.stats
        ]
        cached.sort(key=lambda h: (h.kickoff_unix, h.match_id))
        before = [h for h in cached if h.kickoff_unix < int(first["kickoff"])]

        seasons = defaultdict(list)
        for h in before:
            seasons[str(h.fixture.get("season_id"))].append(h)

        pre_seasons = []
        for season_id, hs in seasons.items():
            hs.sort(key=lambda h: (h.kickoff_unix, h.match_id))
            pre_seasons.append({
                "season_id": season_id,
                "n_finished_stats_matches": len(hs),
                "min_kickoff_unix": int(hs[0].kickoff_unix),
                "max_kickoff_unix": int(hs[-1].kickoff_unix),
            })
        pre_seasons.sort(key=lambda x: (x["max_kickoff_unix"], x["season_id"]))

        competitions.append({
            "competition_id": comp,
            "n_frozen_panel_rows": len(rows),
            "first_frozen_match_id": first["match_id"],
            "first_frozen_kickoff_unix": int(first["kickoff"]),
            "first_frozen_season_id": first_season,
            "n_cached_stats_matches_before_first_frozen_fixture": len(before),
            "cached_pre_frozen_seasons": pre_seasons,
            "n_distinct_cached_pre_frozen_seasons": len(pre_seasons),
            "backfill_rule": "exactly two complete provider seasons immediately preceding first_frozen_season_id",
        })

    if all_missing_panel_fixtures:
        raise SystemExit("PANEL_FIXTURE_MISSING_IN_HISTORY:" + ",".join(all_missing_panel_fixtures))

    doc = {
        "artifact_version": "target_aware_v1_2_prehistory_inventory_v1",
        "authorized_execution_head": head,
        "source_v1_gate_head": SOURCE_V1_GATE_HEAD,
        "cache": CACHE,
        "include_gap_fetches": False,
        "n_frozen_panel_rows": folds["n_panel_rows"],
        "fold_rows_sha256": folds["rows_sha256"],
        "n_competitions": len(competitions),
        "n_history_matches_loaded": len(history),
        "n_stats_conflicts": hmeta["n_stats_conflicts"],
        "competitions": competitions,
        "repair_rule": {
            "provider": "TheStatsAPI",
            "n_prior_complete_seasons_per_competition": 2,
            "adaptive_third_season_allowed": False,
            "scored_rows_changed": False,
            "folds_changed": False,
            "coverage_threshold_changed": False,
            "similarity_semantics_changed": False,
        },
        "target_outcomes_read": False,
        "market_results_read": False,
        "model_fit": False,
        "oos_executed": False,
        "network_calls": 0,
        "champion_sha256": fsha(CHAMPION),
        "next_gate": "FREEZE_EXACT_PROVIDER_SEASON_IDS_AND_BACKFILL_REQUEST_PLAN_BEFORE_ANY_BACKFILL_CALL",
    }
    OUTPUT.write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "status": "V1_2_PREHISTORY_INVENTORY_COMPLETE",
        "authorized_execution_head": head,
        "output": str(OUTPUT),
        "output_sha256": fsha(OUTPUT),
        "n_competitions": len(competitions),
        "target_outcomes_read": False,
        "network_calls": 0,
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
