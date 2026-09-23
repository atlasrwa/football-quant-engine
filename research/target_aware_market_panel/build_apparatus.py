"""Build every frozen artifact of the target-aware market panel apparatus.

No outcome of the cohort is read, no model is fit, no LLM or network call is made. Reads only
the local provider cache. Deterministic: AS_OF is frozen, so a rebuild is byte-identical.
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.research.dual_provider_llm import packet as P  # noqa: E402
from src.research.target_aware_market_panel import cohort_packets as CP  # noqa: E402
from src.research.target_aware_market_panel import policy as POL  # noqa: E402
from src.research.target_aware_market_panel import registry as R  # noqa: E402
from src.research.target_aware_market_panel import templates as TM  # noqa: E402

CACHE = "/home/ubuntu/data/thestatsapi/championship"
OUT = ROOT / "research/target_aware_market_panel"
REQ = OUT / "out/sol_requests"
AS_OF_UNIX = 1790143200            # 2026-09-23T06:00:00Z, the frozen cohort-selection time
PANEL_END_UTC = "2026-09-14T23:59:59Z"
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
BASE_HEAD = "13f10bc1762212bf3ee35e6383019205a8005fd3"


def fsha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def dump(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return fsha(path)


def audit_md(reg):
    L = ["# Market Capability Audit V1", "",
         "Generated from `MARKET_CAPABILITY_REGISTRY_V1.json`, which is itself derived by "
         "scanning the TheStatsAPI cache (`src/research/target_aware_market_panel/registry.py`). "
         "Label capability and price capability are separate columns.", "",
         f"Finished fixtures: {reg['n_finished_fixtures']}. Stats payloads (unambiguous): "
         f"{reg['n_stats_payloads_unambiguous']}. Conflicting payloads excluded: "
         f"{reg['n_stats_payload_conflicts_excluded']}.", "",
         "| Market | Label | Coverage | Priced (validated) | Timestamped pre-KO | Genuine close | "
         "Raw price present | Gen | Model | Market cmp | Reason |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    yn = lambda b: "yes" if b else "no"  # noqa: E731
    for m in reg["markets"]:
        L.append(f"| {m['market_id']} | {yn(m['historical_label_supported'])} | "
                 f"{m['coverage']} | {yn(m['market_odds_supported'])} | "
                 f"{yn(m['timestamped_pre_match_supported'])} | "
                 f"{yn(m['genuine_last_before_kickoff_supported'])} | "
                 f"{yn(m['raw_price_present'])} | {yn(m['eligible_for_hypothesis_generation'])} | "
                 f"{yn(m['eligible_for_oos_modeling'])} | "
                 f"{yn(m['eligible_for_market_comparison'])} | "
                 f"{(m['failure_reason'] or m.get('odds_failure_reason') or '')[:140]} |")
    L += ["", "## Rules", ""] + [f"- **{k}**: {v}" for k, v in reg["eligibility_rules"].items()]
    L += ["", "## Semantic notes", "",
          "- Half-time GOALS cannot be settled: bulk fixture lists carry no half-time score.",
          "- Red cards are mostly null and mixed-zero, so any yellow+red 'cards' label fails "
          "closed. TOTAL_YELLOW_CARDS is a provider-native proxy of the 'total_cards' market "
          "and is never compared with it.",
          "- Half-level corners and yellows are label-supported (halves sum to the full match) "
          "but have no provider market, so they are not generation targets. They are still "
          "exposed as half-level context.",
          "- `cma` `last_seen` prices carry no capture time and are never a close. Genuine "
          "close = latest `research_odds` capture strictly before kickoff, for markets with a "
          "validated closing adapter only.", ""]
    return "\n".join(L)


def main():
    champ_before = fsha(CHAMPION)
    reg = R.build_registry(CACHE)
    arts = {"MARKET_CAPABILITY_REGISTRY_V1.json": dump(OUT / "MARKET_CAPABILITY_REGISTRY_V1.json",
                                                       reg)}
    (OUT / "MARKET_CAPABILITY_AUDIT_V1.md").write_text(audit_md(reg))
    arts["MARKET_CAPABILITY_AUDIT_V1.md"] = fsha(OUT / "MARKET_CAPABILITY_AUDIT_V1.md")
    data = R.load_cache(CACHE)
    lines = POL.line_policy(data)
    arts["MARKET_LINE_POLICY_V1.json"] = dump(OUT / "MARKET_LINE_POLICY_V1.json", lines)
    uni = POL.target_universe(reg, lines)
    arts["TARGET_UNIVERSE_V1.json"] = dump(OUT / "TARGET_UNIVERSE_V1.json", uni)
    base = POL.baseline_semantic_coverage()
    arts["BASELINE_SEMANTIC_COVERAGE_V1.json"] = dump(OUT / "BASELINE_SEMANTIC_COVERAGE_V1.json",
                                                      base)
    ctx = POL.context_policy()
    arts["TARGET_FAMILY_CONTEXT_POLICY_V1.json"] = dump(
        OUT / "TARGET_FAMILY_CONTEXT_POLICY_V1.json", ctx)
    schema = TM.output_schema()
    arts["TARGET_AWARE_OUTPUT_SCHEMA_V1.json"] = dump(OUT / "TARGET_AWARE_OUTPUT_SCHEMA_V1.json",
                                                      schema)
    # ---- cohort (selected on the panel cache only; gap fetches play no part) ----
    panel_hist, panel_meta = CP.load_history(CACHE, include_gap_fetches=False)
    snap_date, sched, snap_hashes = CP.latest_scheduled(CACHE)
    cohort, cmeta = CP.select_cohort(panel_hist, sched, AS_OF_UNIX)
    comps = sorted({c["competition_id"] for c in cohort})
    cohort_doc = {"cohort_version": CP.COHORT_VERSION, "as_of_unix": AS_OF_UNIX,
                  "selection_rule": "latest cached scheduled snapshot; kickoff > as_of; both "
                                    "teams >= 10 prior rich TheStatsAPI matches (panel cache); "
                                    "exclude earlier-pilot fixtures; per competition sort "
                                    "(kickoff, id); round-robin over competitions sorted by id "
                                    f"until {CP.COHORT_SIZE}. Never uses odds, stats values, "
                                    "outcomes or hypothesis quality.",
                  "scheduled_snapshot_date": snap_date, "scheduled_snapshot_files": snap_hashes,
                  "excluded_fixtures": list(CP.EXCLUDED_FIXTURES), "fixtures": cohort,
                  "n_competitions": len(comps), "competitions": comps, **cmeta,
                  "data_cutoff": "packet history = completed matches strictly before kickoff "
                                 "that exist in the cache at as_of; matches played between "
                                 "as_of and kickoff are not in the packet",
                  "target_outcomes_read": False}
    arts["TARGET_AWARE_COHORT_V1.json"] = dump(OUT / "TARGET_AWARE_COHORT_V1.json", cohort_doc)
    # ---- packets + Sol requests (gap fetches included, packet-only) ----
    hist, hmeta = CP.load_history(CACHE, include_gap_fetches=True)
    norm_ver = "git-blob:" + subprocess.run(
        ["git", "-C", str(ROOT), "hash-object", "src/research/thestatsapi/normalizer.py"],
        capture_output=True, text=True, check=True).stdout.strip()
    from src.research.target_aware_market_panel import panel as PN
    rows_by_team = {}
    for r in PN.rows_from_history(hist):
        rows_by_team.setdefault(r.team_id, []).append(r)
    half_mismatches = 0
    prompt = (OUT / "TARGET_AWARE_HYPOTHESIS_PROMPT_V2.md").read_text()
    earliest = min(c["kickoff_unix"] for c in cohort)
    req_index = {}
    for fx in cohort:
        pk = CP.build_fixture_packet(hist, fx, AS_OF_UNIX, norm_ver)
        for fam in ("GOALS", "CORNERS", "TEAM_TOTALS", "BOOKINGS"):
            sl = CP.family_slice(pk, hist, fam)
            half_mismatches += CP.verify_half_evidence(sl, rows_by_team)
            targets = [{k: t[k] for k in ("target_id", "market_id", "line", "line_role",
                                          "settlement_rule", "proxy", "scope", "period")}
                       for t in uni["targets"] if t["family"] == fam
                       and t["line_role"] == "PRIMARY"]
            req = {"request_version": "target_aware_sol_request_v1", "family": fam,
                   "fixture": pk["fixture"], "targets": targets, "evidence_packet": sl,
                   "baseline_semantic_coverage": base, "output_schema": schema,
                   "prompt": prompt,
                   "handoff_rules": {
                       "evidence_only": "use only this request; no web search, no knowledge "
                                        "of results, lineups, injuries, news or odds",
                       "build_as_of_unix": AS_OF_UNIX,
                       "generate_before_unix": earliest,
                       "late_handoff_flag": "if generated after generate_before_unix, record "
                                            "LATE_HANDOFF=true (some cohort kickoffs passed)"},
                   "market_prices_included": False, "p_model_included": False,
                   "target_outcome_included": False}
            p = REQ / fx["provider_fixture_id"] / f"{fam}.json"
            req_index[f"{fx['provider_fixture_id']}/{fam}.json"] = {
                "sha256": dump(p, req), "bytes": p.stat().st_size,
                "approx_tokens": p.stat().st_size // 4, "n_evidence_refs": sl["n_evidence_refs"]}
    arts["out/sol_requests/INDEX"] = dump(REQ / "INDEX.json", req_index)
    if half_mismatches:
        raise SystemExit(f"half-level evidence re-derivation failed: {half_mismatches}")
    # ---- frozen folds over the panel (ids/dates/teams only) ----
    import calendar
    import time as _t
    panel_end = calendar.timegm(_t.strptime(PANEL_END_UTC, "%Y-%m-%dT%H:%M:%SZ"))
    panel_fx = [{"match_id": h.match_id, "kickoff": h.kickoff_unix,
                 "competition_id": str(h.fixture.get("competition_id")),
                 "home_team_id": (h.fixture.get("home_team") or {}).get("id"),
                 "away_team_id": (h.fixture.get("away_team") or {}).get("id")}
                for h in panel_hist.values() if h.kickoff_unix <= panel_end and h.stats]
    cohort_teams = sorted({c[s]["provider_team_id"] for c in cohort
                           for s in ("home_team", "away_team")})
    folds = PN.build_fold_manifest(panel_fx, cohort_teams)
    arts["TARGET_AWARE_FOLD_MANIFEST_V1.json"] = dump(OUT / "TARGET_AWARE_FOLD_MANIFEST_V1.json",
                                                      folds)
    # ---- market-comparison coverage INSIDE the panel ----
    panel_ids = {f["match_id"] for f in panel_fx}
    mkt_cov = {}
    for mkey, reg_id in (("total_goals", "TOTAL_GOALS"), ("btts", "BTTS")):
        ids = {mid for mid, cts, bks in data["captures"]
               if mid in panel_ids and cts is not None and data["kickoffs"].get(mid)
               and cts < data["kickoffs"][mid]
               and any((b.get("markets") or {}).get(mkey) for b in bks)}
        mkt_cov[reg_id] = {"n_panel_matches_with_validated_pre_kickoff_capture": len(ids),
                           "n_panel_matches": len(panel_ids)}
    for n in ("TARGET_AWARE_HYPOTHESIS_PROMPT_V2.md", "TARGET_AWARE_PANEL_PROTOCOL_V1.md"):
        arts[n] = fsha(OUT / n)
    untouched = subprocess.run(["git", "-C", str(ROOT), "diff", "--name-only", BASE_HEAD, "--",
                                "research/item6", "src/research/item6",
                                "research/dual_provider_llm", "src/research/dual_provider_llm",
                                "research/target_aware_sol"],
                               capture_output=True, text=True, check=True).stdout.split()
    mods = sorted((ROOT / "src/research/target_aware_market_panel").glob("*.py"))
    manifest = {
        "manifest_version": "target_aware_panel_manifest_v1",
        "status": "APPARATUS_FROZEN_AWAITING_SOL_HYPOTHESIS_GENERATION",
        "base_head": BASE_HEAD, "as_of_unix": AS_OF_UNIX, "panel_end_utc": PANEL_END_UTC,
        "artifacts": arts, "modules": {str(m.relative_to(ROOT)): fsha(m) for m in mods},
        "n_sol_requests": len(req_index), "sol_request_directory":
            "research/target_aware_market_panel/out/sol_requests/",
        "gap_fetch_files_used_in_packets_only": hmeta["gap_fetch_files"],
        "prior_artifacts_modified_vs_base": untouched,
        "fold_manifest_rows_sha256": folds["rows_sha256"],
        "panel": {"n_panel_rows": folds["n_panel_rows"], "n_oos_all": folds["n_oos_all"],
                  "n_oos_primary_excluding_cohort_teams":
                      folds["n_oos_primary_excluding_cohort_teams"],
                  "per_fold": {k: {x: v[x] for x in ("n_train", "n_test_all", "n_test_primary")}
                               for k, v in folds["folds"].items()}},
        "market_comparison_coverage_inside_panel": mkt_cov,
        "half_level_evidence_rederivation_mismatches": half_mismatches,
        "target_outcomes_read": False, "market_results_read": False, "model_fit": False,
        "oos_executed": False, "llm_calls": 0,
        "champion_sha256_before": champ_before, "champion_sha256_after": fsha(CHAMPION)}
    dump(OUT / "TARGET_AWARE_PANEL_MANIFEST_V1.json", manifest)
    print(json.dumps({"n_requests": len(req_index), "cohort": [c["provider_fixture_id"]
                                                               for c in cohort],
                      "max_request_tokens": max(v["approx_tokens"] for v in req_index.values()),
                      "universe_targets": len(uni["targets"]),
                      "panel": manifest["panel"], "market_cov": mkt_cov}, indent=1))


if __name__ == "__main__":
    main()
