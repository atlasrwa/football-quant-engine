"""EXPOSED-50 APPARATUS REHEARSAL V2 — TRUE packet -> bridge path, ZERO SPEND.

V1 reported `N_PACKETS_BUILT=50` while invoking the bridge with `packet_hash="NO_PACKET"`, so
no packet was ever built or bound. V2 executes the real path for every fixture:

    EvidencePacketBuilderV2 -> corrected v4 packet -> packet_hash verified
      -> deterministic proposal -> evidence_ref binding -> canonicalization
      -> provider/PIT/support validation -> deterministic measurement -> shadow record

Proposals are DETERMINISTIC STUBS, not model output. No Sonnet, no Bedrock, no network.
V1's artifact is NOT overwritten.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.realpath(os.path.join(_HERE, os.pardir, os.pardir))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src._repo_paths import ensure_repo_importable, ensure_scripts_importable
ensure_repo_importable()
ensure_scripts_importable()

from src.research.matchup.corpus import load_corpus, MatchRecord
from src.research.llm_matchup import cohorts as CH
from src.research.llm_matchup.evidence import packet_hash as recompute_packet_hash, valid_evidence_ids
from src.research.llm_matchup.evidence_v2 import EvidencePacketBuilderV2
from src.research.llm_matchup.versions import PACKET_SCHEMA_VERSION, COHORT_POLICY_VERSION
from src.research.hypothesis_bridge import packet_binding as PB, status as ST
from src.research.hypothesis_bridge.bridge import BridgeContext

SELECTION_FREEZE = os.path.join(_ROOT, "research/hypothesis_engine/V8B1_PILOT50_SELECTION_FREEZE.json")
OUT = os.path.join(_HERE, "EXPOSED50_APPARATUS_REHEARSAL_V2.json")
CLASSIFICATION = "DEVELOPMENT_REAL_CORPUS_APPARATUS_REHEARSAL"
CHAMPION_PATH = "/home/ubuntu/data/discovery/pilotC_stat_mixer.json"

TEMPLATES = [
    {"tag": "home_corners_league", "subject": "home_team", "target_metric": "corners",
     "perspective": "for", "comparator": "league_season_baseline", "conditions": {"venue": "home"}},
    {"tag": "away_shots_team", "subject": "away_team", "target_metric": "total_shots",
     "perspective": "for", "comparator": "team_season_baseline", "conditions": {"venue": "away"}},
    {"tag": "home_conceded_sot", "subject": "home_team", "target_metric": "shots_on_target",
     "perspective": "against", "comparator": "team_season_baseline", "conditions": {}},
    {"tag": "home_cards_league", "subject": "home_team", "target_metric": "yellow_cards",
     "perspective": "for", "comparator": "league_season_baseline", "conditions": {}},
    {"tag": "unsupported_metric", "subject": "home_team", "target_metric": "expected_threat",
     "perspective": "for", "comparator": "league_season_baseline"},
    {"tag": "unsupported_period", "subject": "home_team", "target_metric": "big_chances",
     "perspective": "for", "comparator": "league_season_baseline",
     "conditions": {"period": "first_half"}},
]

#: The complete deterministic measurement surface. V1 compared only `cohort`, so a leak that
#: moved the baseline, the contrast or a source hash while leaving the cohort summary intact
#: would have been invisible.
COMPARED_KEYS = ("cohort", "baseline", "deterministic_contrast", "cohort_identity_hash",
                 "cohort_source_hash", "baseline_source_hash", "measurement_input_hash")


def _sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest() if os.path.isfile(p) else None


def _payload(rec):
    m = rec.get("measurement") or {}
    return {k: m.get(k) for k in COMPARED_KEYS}


def _clone(t: MatchRecord, fid, kickoff, away, ck):
    return MatchRecord(fixture_id=fid, competition=t.competition,
                       competition_id=t.competition_id, season_id=t.season_id,
                       kickoff_unix=kickoff, home=t.home_id, away=away,
                       home_id=t.home_id, away_id=away, base=dict(t.base),
                       rich={"corner_kicks": ck}, extra={})


def main() -> int:
    champion_before = _sha(CHAMPION_PATH)
    recs = load_corpus()
    by_id = {r.fixture_id: r for r in recs}
    pilot = json.load(open(SELECTION_FREEZE))["pilot_fixture_ids_ordered"]
    targets = [by_id[f] for f in pilot if f in by_id]

    builder = EvidencePacketBuilderV2(recs, enrich_halves=False)
    ctx = BridgeContext(recs)
    idx = CH.HistoryIndex(recs)

    packets, packet_failures = {}, []
    for t in targets:
        try:
            pkt = builder.build(t)
            if recompute_packet_hash(pkt) != pkt.get("packet_hash"):
                packet_failures.append({"fixture_id": t.fixture_id, "reason": "hash_mismatch"})
                continue
            packets[t.fixture_id] = pkt
        except Exception as e:                                   # pragma: no cover
            packet_failures.append({"fixture_id": t.fixture_id, "reason": type(e).__name__})

    records, statuses = [], Counter()
    n_ok = n_fail = real_hashes = no_packet = 0
    valid_refs = invalid_refs = 0

    for t in targets:
        pkt = packets.get(t.fixture_id)
        if pkt is None:
            continue
        ref_ids = sorted(valid_evidence_ids(pkt))
        for tpl in TEMPLATES:
            raw = {k: v for k, v in tpl.items() if k != "tag"}
            raw["fixture_id"] = t.fixture_id
            raw["research_reason"] = f"apparatus rehearsal v2 template {tpl['tag']}"
            if ref_ids:
                raw["evidence_refs"] = [ref_ids[0]]
            rec = ctx.run_proposal(raw, packet=pkt,
                                   proposal_source=PB.SOURCE_DETERMINISTIC_REHEARSAL)
            rec["rehearsal_template"] = tpl["tag"]
            records.append(rec)
            statuses[rec["validation_status"]] += 1
            if rec["validation_status"] == ST.VALID_MEASURABLE:
                n_ok += 1
            elif rec["validation_status"] == ST.MEASUREMENT_FAILED:
                n_fail += 1
            if rec.get("packet_hash"):
                real_hashes += 1
            else:
                no_packet += 1
            if rec.get("evidence_refs_bound"):
                valid_refs += 1
            elif rec["validation_status"] == ST.PACKET_BINDING_FAILED and \
                    "evidence_refs" in (rec.get("rejection_reason") or ""):
                invalid_refs += 1

    # --- leakage probes: COMPLETE measurement payload, not just the cohort summary --------
    probe = {k: v for k, v in TEMPLATES[0].items() if k != "tag"}
    same_kick = outcome_dep = future_dep = src_mismatch = 0
    for t in targets[:10]:
        pkt = packets.get(t.fixture_id)
        if pkt is None:
            continue
        raw = {**probe, "fixture_id": t.fixture_id, "research_reason": "leak probe v2"}
        base_rec = ctx.run_proposal(raw, packet=pkt,
                                    proposal_source=PB.SOURCE_DETERMINISTIC_REHEARSAL)
        if base_rec["validation_status"] != ST.VALID_MEASURABLE:
            continue
        baseline_payload = _payload(base_rec)

        perturbations = {
            "same_kickoff": recs + [_clone(t, f"SIM_{t.fixture_id}", t.kickoff_unix, "ZZZ_SIM", (99, 99))],
            "future": recs + [_clone(t, f"FUT_{t.fixture_id}", t.kickoff_unix + 10_000_000, "ZZZ_FUT", (99, 99))],
            "target_outcome": [(_clone(t, t.fixture_id, t.kickoff_unix, t.away_id, (99, 99))
                                if r.fixture_id == t.fixture_id else r) for r in recs],
        }
        for name, perturbed in perturbations.items():
            p_ctx = BridgeContext(perturbed)
            p_rec = p_ctx.run_proposal(raw, packet=pkt,
                                       proposal_source=PB.SOURCE_DETERMINISTIC_REHEARSAL)
            if _payload(p_rec) != baseline_payload:
                if name == "same_kickoff":
                    same_kick += 1
                elif name == "future":
                    future_dep += 1
                else:
                    outcome_dep += 1
                src_mismatch += 1

    n_boundary = 0
    for t in targets:
        ts = CH.HistoryIndex.target_season(t)
        for team in (t.home_id, t.away_id):
            if idx.current_season(team, t.kickoff_unix) not in (None, ts):
                n_boundary += 1

    report = {
        "artifact": "EXPOSED50_APPARATUS_REHEARSAL_V2",
        "supersedes": "EXPOSED50_APPARATUS_REHEARSAL_V1 (which used packet_hash='NO_PACKET')",
        "CLASSIFICATION": CLASSIFICATION,
        "not_measured": ["LLM quality", "S vs R performance", "effect size", "p-value",
                         "odds", "EV", "probability", "betting performance"],
        "lineage": {"packet_schema_version": PACKET_SCHEMA_VERSION,
                    "cohort_policy_version": COHORT_POLICY_VERSION},
        "executed_path": ("EvidencePacketBuilderV2 -> packet_hash verified -> proposal -> "
                          "evidence_ref binding -> canonicalization -> validation -> "
                          "deterministic measurement -> shadow record"),
        "leakage_comparison_keys": list(COMPARED_KEYS),
        "N_FIXTURES": len(targets),
        "N_PACKETS_BUILT": len(packets),
        "N_PACKET_FAILURES": len(packet_failures),
        "packet_failure_detail": packet_failures[:10],
        "N_PROPOSALS": len(records),
        "N_VALID_MEASURABLE": statuses.get(ST.VALID_MEASURABLE, 0),
        "N_REJECTED": sum(v for k, v in statuses.items() if k != ST.VALID_MEASURABLE),
        "rejection_counts_by_reason": {k: v for k, v in sorted(statuses.items())
                                       if k != ST.VALID_MEASURABLE},
        "N_MEASUREMENTS_OK": n_ok,
        "N_MEASUREMENTS_FAILED": n_fail,
        "N_SHADOW_RECORDS": len(records),
        "N_REAL_PACKET_HASHES": real_hashes,
        "N_NO_PACKET_RECORDS": no_packet,
        "N_VALID_EVIDENCE_REF_BINDINGS": valid_refs,
        "N_INVALID_EVIDENCE_REF_BINDINGS": invalid_refs,
        "N_SEASON_BOUNDARY_FIXTURES": n_boundary,
        "SAME_KICKOFF_LEAKAGE_COUNT": same_kick,
        "TARGET_OUTCOME_DEPENDENCE_COUNT": outcome_dep,
        "FUTURE_DATA_DEPENDENCE_COUNT": future_dep,
        "SOURCE_HASH_MISMATCH_COUNT": src_mismatch,
        "OLD_CACHE_REUSE_COUNT": 0,
        "LIVE_SONNET_CALLS": 0,
        "BEDROCK_PAID_CALLS": 0,
        "NEW_SONNET_SPEND_USD": 0,
        "RAW_CORPUS_EXPORTED": False,
        "CHAMPION_BEFORE": champion_before,
        "CHAMPION_AFTER": _sha(CHAMPION_PATH),
        "CHAMPION_UNCHANGED": champion_before == _sha(CHAMPION_PATH),
        "audit_sample": [{k: r.get(k) for k in
                          ("fixture_id", "rehearsal_template", "validation_status",
                           "packet_binding_verified", "canonical_hypothesis_id",
                           "raw_n", "effective_n")} for r in records[:6]],
    }
    json.dump(report, open(OUT, "w"), indent=2, default=str)
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("audit_sample", "packet_failure_detail")},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
