"""Build PILOT_FIXTURE_PACKET_V1.json from the local TheStatsAPI cache.

Exploratory research only. No model fit, no outcome evaluation, no LLM call, no network: reads
only files already in the cache (the two history gaps for the selected fixture were fetched
beforehand into dpl_match_* / dpl_stats_* by scripts/thestatsapi_client.get_json).

Usage:  python research/dual_provider_llm/build_pilot_packet.py [--as-of-unix N]
"""
from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.research.dual_provider_llm import packet as P  # noqa: E402
from src.research.thestatsapi.normalizer import parse_iso_to_unix  # noqa: E402

CACHE = Path(os.environ.get("THESTATSAPI_CACHE_DIR", "/home/ubuntu/data/thestatsapi/championship"))
OUT = ROOT / "research" / "dual_provider_llm" / "out" / "direct_pilot"
PACKET_NAME = "PILOT_FIXTURE_PACKET_V1.json"
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
CHAMPION_SHA256 = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def fsha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def load(p: Path):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--as-of-unix", type=int, default=int(time.time()))
    a = ap.parse_args()
    as_of = a.as_of_unix
    champion_before = fsha(CHAMPION)
    assert champion_before == CHAMPION_SHA256, "CHAMPION changed before build"

    # ---- finished fixtures (all cached sources); conflicting duplicates are EXCLUDED ----
    fixture_files = (sorted(CACHE.glob("_all_fixtures*.json"))
                     + sorted(CACHE.glob("fixtures_sn_*_finished_*.json"))
                     + sorted(CACHE.glob("*_matches_sn_*.json")))
    versions: dict = {}
    for f in fixture_files:
        d = load(f) or {}
        for x in (d.get("fixtures") or d.get("data") or []):
            if isinstance(x, dict) and str(x.get("status")).lower() == "finished" and x.get("id"):
                versions.setdefault(x["id"], {}).setdefault(P.fixture_identity(x), x)
    fetched = []
    for f in sorted(CACHE.glob("dpl_match_mt_*.json")):
        d = load(f) or {}
        x = d.get("data") if isinstance(d.get("data"), dict) else None
        assert x and x.get("id") and x.get("home_team") and x.get("away_team") and \
            "score" in x and x.get("utc_date"), f"unexpected shape in {f.name}"
        assert str(x.get("status")).lower() == "finished", f"{f.name} not finished"
        fetched.append((f, x))
        versions.setdefault(x["id"], {}).setdefault(P.fixture_identity(x), x)
    fixtures = {i: next(iter(v.values())) for i, v in versions.items() if len(v) == 1}
    fixture_conflicts = sorted(i for i, v in versions.items() if len(v) > 1)

    # ---- stats payloads; conflicting payloads are NOT resolved ----
    stats_files = sorted(CACHE.glob("*stats_mt_*.json"))
    stats_ok, stats_conflicts = P.build_stats_map((f.name, load(f)) for f in stats_files)

    # ---- scheduled snapshot (latest date only) ----
    snaps = sorted(CACHE.glob("discovery_comp_*_scheduled_*_p*.json"))
    dated = [(re.search(r"_(20\d{6})_p", s.name).group(1), s) for s in snaps]
    latest = max(d for d, _ in dated)
    latest_files = [s for d, s in dated if d == latest]
    scheduled = {}
    for s in latest_files:
        for x in (load(s) or {}).get("data", []):
            scheduled.setdefault(x["id"], x)
    # every snapshot occurrence, for orientation checks of fetched records
    snap_orient = {}
    for _, s in dated:
        for x in (load(s) or {}).get("data", []):
            snap_orient[x["id"]] = ((x.get("home_team") or {}).get("id"),
                                    (x.get("away_team") or {}).get("id"), x.get("utc_date"))
    for f, x in fetched:
        o = snap_orient.get(x["id"])
        assert o is None or o == ((x["home_team"]).get("id"), (x["away_team"]).get("id"),
                                  x.get("utc_date")), f"orientation mismatch for {x['id']}"

    history = P.normalize_history(fixtures, stats_ok, stats_conflicts)
    target, sel_audit = P.select_fixture(sorted(scheduled.values(), key=lambda x: x["id"]),
                                         history, as_of)
    assert target is not None, "no eligible upcoming fixture: use the historical fallback"
    tid = target["id"]
    T = parse_iso_to_unix(target["utc_date"])
    assert T > as_of
    assert tid not in history and tid not in stats_ok and tid not in stats_conflicts
    assert not list(CACHE.glob(f"*{tid}*stats*")) and not list(CACHE.glob(f"*stats*{tid}*")), \
        "a stats file exists for the target fixture"

    comp_name = None
    for f in sorted(CACHE.glob("league_sync_competitions_*_p*.json"), reverse=True):
        for c in (load(f) or {}).get("data", []):
            if c.get("id") == target.get("competition_id"):
                comp_name = {"name": c.get("name"), "country": c.get("country")}
        if comp_name:
            break

    norm_ver = "git-blob:" + subprocess.run(
        ["git", "-C", str(ROOT), "hash-object", "src/research/thestatsapi/normalizer.py"],
        capture_output=True, text=True, check=True).stdout.strip()
    teams = {"HOME_TEAM": target["home_team"], "AWAY_TEAM": target["away_team"]}
    blocks = {r: P.build_team_block(history, t["id"], r, T, norm_ver) for r, t in teams.items()}

    # ---- team-id continuity: same name under a different provider team id? ----
    continuity = {}
    for r, t in teams.items():
        names = set(blocks[r]["coverage"]["team_names_seen_for_team_id"])
        other_ids = sorted({side.get("id") for fx in fixtures.values()
                            for side in (fx.get("home_team") or {}, fx.get("away_team") or {})
                            if side.get("name") in names and side.get("id") != t["id"]})
        continuity[r] = {"team_id": t["id"], "names_seen": sorted(names),
                         "other_ids_with_same_name": other_ids}

    aggregate = [x for r in P.ROLES for x in blocks[r]["aggregate_evidence"]]
    raw = {r: blocks[r]["raw_recent_matches"] for r in P.ROLES}
    agg_refs = [x["evidence_ref"] for x in aggregate]
    raw_refs = [k for r in P.ROLES for row in raw[r] for k in row["values"]]
    index = {
        "ref_grammar": {
            "aggregate": "tsa.<TEAM_ROLE>.<canonical_concept>.<FOR|AGAINST>.<window>.<venue_scope>"
                         " -> an item in aggregate_evidence",
            "raw": "tsa.<TEAM_ROLE>.raw.<provider_match_id>.<canonical_concept>.<FOR|AGAINST> -> "
                   "a key in raw_recent_matches.<TEAM_ROLE>[i].values"},
        "n_aggregate_refs": len(agg_refs), "n_raw_refs": len(raw_refs),
        "n_refs_total": len(agg_refs) + len(raw_refs),
        "aggregate_refs": sorted(agg_refs), "raw_refs": sorted(raw_refs)}
    cov = {r: blocks[r]["coverage"] for r in P.ROLES}
    hist_conf = {r: sorted({h.match_id for h in blocks[r]["_rows"]
                            if h.match_id in stats_conflicts}) for r in P.ROLES}

    packet = {
        "contract_version": P.CONTRACT_VERSION,
        "builder_version": P.PACKET_BUILDER_VERSION,
        "created_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(as_of)),
        "as_of_unix": as_of,
        "purpose": "Exploratory direct-LLM hypothesis generation only; no prediction and no "
                   "outcome evaluation.",
        "fixture": {
            "fixture_id": f"thestatsapi:{tid}", "provider_fixture_id": tid,
            "kickoff_unix": T, "kickoff_utc": target["utc_date"],
            "competition": {"provider_competition_id": target.get("competition_id"),
                            **(comp_name or {})},
            "season_id": target.get("season_id"),
            "home_team": {"provider_team_id": teams["HOME_TEAM"]["id"],
                          "name": teams["HOME_TEAM"]["name"]},
            "away_team": {"provider_team_id": teams["AWAY_TEAM"]["id"],
                          "name": teams["AWAY_TEAM"]["name"]},
            "target_outcome_included": False,
        },
        "cutoff_unix": T,
        "selection_rule": {
            "rule": "Upcoming TheStatsAPI fixtures from the latest cached scheduled snapshot "
                    f"({latest}); keep kickoff > as_of; require both teams to have >= "
                    f"{P.MIN_RICH_PRIOR_MATCHES} completed prior TheStatsAPI matches with at least "
                    "one populated rich field; sort by (kickoff, provider fixture id); first.",
            "as_of_unix": as_of, "snapshot_date": latest,
            "first_candidates_in_order": sel_audit,
        },
        "providers_used": [P.PROVIDER],
        "target_outcome_included": False,
        "market_data_included": False,
        "p_model_included": False,
        "field_scope": {
            "concepts": P.concept_semantics(),
            "normalization_version": norm_ver,
            "reliability_label": "ADEQUATE sample_n>=10; LIMITED 5-9; SPARSE 1-4",
            "periods_available": ["FULL_MATCH"],
            "reading_guide": "Values are per-match means over the stated window of completed "
                             "matches strictly before cutoff_unix. sample_n counts matches with "
                             "a non-null value; missing values are omitted, never zero. History "
                             "covers only the competitions present in the local cache.",
        },
        "raw_recent_matches": raw,
        "aggregate_evidence": aggregate,
        "windows": {r: blocks[r]["windows"] for r in P.ROLES},
        "evidence_ref_index": index,
        "coverage_summary": {
            "HOME_TEAM": cov["HOME_TEAM"], "AWAY_TEAM": cov["AWAY_TEAM"],
            "N_DISTINCT_RICH_CONCEPTS_TEAM_A": cov["HOME_TEAM"]["N_DISTINCT_RICH_CONCEPTS"],
            "N_DISTINCT_RICH_CONCEPTS_TEAM_B": cov["AWAY_TEAM"]["N_DISTINCT_RICH_CONCEPTS"],
            "N_EVIDENCE_REFS_TOTAL": index["n_refs_total"],
            "history_scope": "most recent matches WITHIN CACHED COMPETITIONS (league fixture lists "
                             "for the cached seasons plus two explicitly fetched league matches); "
                             "cup and other competitions are not enumerated",
        },
        "provenance": {
            "provider": P.PROVIDER, "cache_dir": str(CACHE),
            "normalizer": "src/research/thestatsapi/normalizer.py", "normalization_version": norm_ver,
            "n_fixture_files": len(fixture_files), "n_stats_files": len(stats_files),
            "n_finished_fixtures_loaded": len(fixtures),
            "n_fixture_conflicts_excluded": len(fixture_conflicts),
            "n_stats_payload_conflicts_total": len(stats_conflicts),
            "stats_payload_conflicts_in_team_histories": hist_conf,
            "scheduled_snapshot_files": {s.name: fsha(s) for s in latest_files},
            "fetched_gap_files": {f.name: fsha(f) for f in sorted(CACHE.glob("dpl_*_mt_*.json"))},
            "team_id_continuity": continuity,
            "identity_policy": "teams keyed by TheStatsAPI provider team id; no name joins; no "
                               "FootyStats evidence (no reviewed cross-provider team mapping)",
        },
    }
    checks = P.leakage_checks(packet, history, tid)
    packet["leakage_checks"] = checks
    if not P.leakage_ok(checks):
        print(json.dumps(checks, indent=1))
        raise SystemExit("LEAKAGE CHECK FAILED: packet not written")
    OUT.mkdir(parents=True, exist_ok=True)
    body = json.dumps(packet, indent=1, sort_keys=True, ensure_ascii=False)
    (OUT / PACKET_NAME).write_text(body + "\n")
    compact = json.dumps(packet, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    champion_after = fsha(CHAMPION)
    summary = {
        "packet_path": str((OUT / PACKET_NAME).relative_to(ROOT)),
        "packet_sha256": fsha(OUT / PACKET_NAME),
        "packet_bytes": len(body.encode()), "compact_bytes": len(compact.encode()),
        "approx_tokens_compact": len(compact) // 4,
        "fixture": packet["fixture"], "coverage": {r: {k: v for k, v in cov[r].items()
                                                       if k != "per_metric_FOR"}
                                                   for r in P.ROLES},
        "per_metric_FOR": {r: cov[r]["per_metric_FOR"] for r in P.ROLES},
        "n_evidence_refs": index["n_refs_total"], "leakage_checks": checks,
        "team_id_continuity": continuity, "stats_conflicts_in_histories": hist_conf,
        "fixture_conflicts_excluded": len(fixture_conflicts),
        "champion_before": champion_before, "champion_after": champion_after,
    }
    (OUT / "_build_summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    print(json.dumps(summary, indent=1, sort_keys=True, ensure_ascii=False))


if __name__ == "__main__":
    main()
