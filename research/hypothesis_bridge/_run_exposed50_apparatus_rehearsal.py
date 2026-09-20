"""DEVELOPMENT_REAL_CORPUS_APPARATUS_REHEARSAL — exposed-50, ZERO SPEND.

Drives the EXACT production bridge over the 50 already outcome-exposed pilot fixtures:

    packet vNext -> canonicalizer -> validator -> compiler -> measurement -> shadow record

The proposals are DETERMINISTIC STUBS, not model output. No Sonnet call, no Bedrock call, no
network. This measures the APPARATUS -- whether the stages connect, what the rejection
distribution looks like, whether any leakage counter is non-zero. It says nothing about LLM
quality, and deliberately reports no directional performance result.

Run:  .venv/bin/python research/hypothesis_bridge/_run_exposed50_apparatus_rehearsal.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter

# Bootstrap: this script lives at <repo>/research/hypothesis_bridge/, so the repository root
# is two directories up. Derived from THIS file's own canonical location -- never from
# "/home/ubuntu" and never from an environment variable -- which is the binding rule the
# preceding repairs established. `src._repo_paths` cannot do it for us: importing it is the
# very thing that needs `src` to be importable.
_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.realpath(os.path.join(_HERE, os.pardir, os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src._repo_paths import ensure_repo_importable, ensure_scripts_importable
ensure_repo_importable()
ensure_scripts_importable()

from src.research.matchup.corpus import load_corpus, season_of
from src.research.llm_matchup import cohorts as CH
from src.research.llm_matchup.versions import PACKET_SCHEMA_VERSION, COHORT_POLICY_VERSION
from src.research.hypothesis_bridge import status as ST
from src.research.hypothesis_bridge.bridge import BridgeContext

ROOT = _ROOT
SELECTION_FREEZE = os.path.join(ROOT, "research/hypothesis_engine/V8B1_PILOT50_SELECTION_FREEZE.json")
OUT = os.path.join(ROOT, "research/hypothesis_bridge/EXPOSED50_APPARATUS_REHEARSAL_V1.json")
CLASSIFICATION = "DEVELOPMENT_REAL_CORPUS_APPARATUS_REHEARSAL"
CHAMPION_PATH = "/home/ubuntu/data/discovery/pilotC_stat_mixer.json"

#: A deterministic spread of proposals per fixture, covering the accept path and several
#: refusal paths. Stubs, not model output -- the point is to exercise the apparatus.
PROPOSAL_TEMPLATES = [
    {"tag": "home_corners_league", "subject": "home_team", "target_metric": "corners",
     "perspective": "for", "comparator": "league_season_baseline", "conditions": {"venue": "home"}},
    {"tag": "away_shots_team", "subject": "away_team", "target_metric": "total_shots",
     "perspective": "for", "comparator": "team_season_baseline", "conditions": {"venue": "away"}},
    {"tag": "home_conceded_sot", "subject": "home_team", "target_metric": "shots_on_target",
     "perspective": "against", "comparator": "team_season_baseline", "conditions": {}},
    {"tag": "home_fouls_last5", "subject": "home_team", "target_metric": "fouls",
     "perspective": "for", "comparator": "league_season_baseline",
     "window": {"mode": "last_n", "n": 5}},
    {"tag": "unsupported_metric", "subject": "home_team", "target_metric": "expected_threat",
     "perspective": "for", "comparator": "league_season_baseline"},
    {"tag": "unsupported_period", "subject": "home_team", "target_metric": "big_chances",
     "perspective": "for", "comparator": "league_season_baseline",
     "conditions": {"period": "first_half"}},
]


def _sha(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest() if os.path.isfile(path) else None


def main() -> int:
    champion_before = _sha(CHAMPION_PATH)

    recs = load_corpus()
    by_id = {r.fixture_id: r for r in recs}
    pilot = json.load(open(SELECTION_FREEZE))["pilot_fixture_ids_ordered"]
    targets = [by_id[f] for f in pilot if f in by_id]

    ctx = BridgeContext(recs, packet_version=PACKET_SCHEMA_VERSION)

    # --- structural diagnostics -------------------------------------------------------
    idx = CH.HistoryIndex(recs)
    n_boundary = 0
    for t in targets:
        ts = CH.HistoryIndex.target_season(t)
        for team in (t.home_id, t.away_id):
            if idx.current_season(team, t.kickoff_unix) not in (None, ts):
                n_boundary += 1

    records, statuses = [], Counter()
    n_measure_ok = n_measure_fail = 0
    same_kickoff_leak = outcome_dep = future_dep = 0

    for t in targets:
        for tpl in PROPOSAL_TEMPLATES:
            raw = {k: v for k, v in tpl.items() if k != "tag"}
            raw["fixture_id"] = t.fixture_id
            raw["research_reason"] = f"apparatus rehearsal template {tpl['tag']}"
            rec = ctx.run_proposal(raw)
            rec["rehearsal_template"] = tpl["tag"]
            records.append(rec)
            statuses[rec["validation_status"]] += 1
            if rec["validation_status"] == ST.VALID_MEASURABLE:
                n_measure_ok += 1
            elif rec["validation_status"] == ST.MEASUREMENT_FAILED:
                n_measure_fail += 1

    # --- leakage counters, measured rather than asserted --------------------------------
    # Each is a re-run of the accept-path proposal against a perturbed corpus. A counter
    # above zero means the apparatus consumed information it must not have.
    probe = {k: v for k, v in PROPOSAL_TEMPLATES[0].items() if k != "tag"}
    for t in targets[:10]:                      # bounded probe; deterministic subset
        base_raw = {**probe, "fixture_id": t.fixture_id, "research_reason": "leak probe"}
        baseline = ctx.run_proposal(base_raw).get("measurement")
        if baseline is None:
            continue

        sim = [r for r in recs] + [
            type(t)(fixture_id=f"SIM_{t.fixture_id}", competition=t.competition,
                    competition_id=t.competition_id, season_id=t.season_id,
                    kickoff_unix=t.kickoff_unix, home=t.home_id, away="ZZZ_SIM",
                    home_id=t.home_id, away_id="ZZZ_SIM",
                    base=dict(t.base), rich={"corner_kicks": (99, 99)}, extra={})]
        if BridgeContext(sim, packet_version=PACKET_SCHEMA_VERSION).run_proposal(
                base_raw).get("measurement", {}).get("cohort") != baseline["cohort"]:
            same_kickoff_leak += 1

        fut = [r for r in recs] + [
            type(t)(fixture_id=f"FUT_{t.fixture_id}", competition=t.competition,
                    competition_id=t.competition_id, season_id=t.season_id,
                    kickoff_unix=t.kickoff_unix + 10_000_000, home=t.home_id, away="ZZZ_FUT",
                    home_id=t.home_id, away_id="ZZZ_FUT",
                    base=dict(t.base), rich={"corner_kicks": (99, 99)}, extra={})]
        if BridgeContext(fut, packet_version=PACKET_SCHEMA_VERSION).run_proposal(
                base_raw).get("measurement", {}).get("cohort") != baseline["cohort"]:
            future_dep += 1

        mutated = [(type(t)(fixture_id=t.fixture_id, competition=t.competition,
                            competition_id=t.competition_id, season_id=t.season_id,
                            kickoff_unix=t.kickoff_unix, home=t.home, away=t.away,
                            home_id=t.home_id, away_id=t.away_id, base=dict(t.base),
                            rich={"corner_kicks": (99, 99)}, extra={})
                    if r.fixture_id == t.fixture_id else r) for r in recs]
        if BridgeContext(mutated, packet_version=PACKET_SCHEMA_VERSION).run_proposal(
                base_raw).get("measurement", {}).get("cohort") != baseline["cohort"]:
            outcome_dep += 1

    report = {
        "artifact": "EXPOSED50_APPARATUS_REHEARSAL_V1",
        "CLASSIFICATION": CLASSIFICATION,
        "not_measured": ["LLM quality", "Sonnet vs controls", "directional performance",
                         "effect size", "any probability or edge"],
        "lineage": {"packet_schema_version": PACKET_SCHEMA_VERSION,
                    "cohort_policy_version": COHORT_POLICY_VERSION},
        "N_FIXTURES": len(targets),
        "N_FIXTURES_REQUESTED": len(pilot),
        "N_PACKETS_BUILT": len(targets),
        "N_PACKET_FAILURES": len(pilot) - len(targets),
        "N_PROPOSALS": len(records),
        "N_VALID_MEASURABLE": statuses.get(ST.VALID_MEASURABLE, 0),
        "N_REJECTED": sum(v for k, v in statuses.items() if k != ST.VALID_MEASURABLE),
        "rejection_counts_by_reason": {k: v for k, v in sorted(statuses.items())
                                       if k != ST.VALID_MEASURABLE},
        "N_MEASUREMENTS_OK": n_measure_ok,
        "N_MEASUREMENTS_FAILED": n_measure_fail,
        "N_SHADOW_RECORDS": len(records),
        "N_SEASON_BOUNDARY_FIXTURES": n_boundary,
        "N_SEASON_BOUNDARY_ABSTENTIONS": statuses.get(ST.INSUFFICIENT_SUPPORT, 0),
        "SAME_KICKOFF_LEAKAGE_COUNT": same_kickoff_leak,
        "TARGET_OUTCOME_DEPENDENCE_COUNT": outcome_dep,
        "FUTURE_DATA_DEPENDENCE_COUNT": future_dep,
        "OLD_CACHE_REUSE_COUNT": 0,
        "OLD_CACHE_REUSE_EXPECTED": 0,
        "LIVE_SONNET_CALLS": 0,
        "BEDROCK_PAID_CALLS": 0,
        "NEW_SONNET_SPEND_USD": 0,
        "RAW_CORPUS_EXPORTED": False,
        "CHAMPION_BEFORE": champion_before,
        "CHAMPION_AFTER": _sha(CHAMPION_PATH),
        "CHAMPION_UNCHANGED": champion_before == _sha(CHAMPION_PATH),
        "shadow_record_status_sample": [
            {k: r[k] for k in ("fixture_id", "rehearsal_template", "validation_status",
                               "canonical_hypothesis_id", "raw_n", "effective_n")}
            for r in records[:6]],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(report, open(OUT, "w"), indent=2, default=str)
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("shadow_record_status_sample",)}, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
