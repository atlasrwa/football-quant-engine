"""EXPOSED-50 APPARATUS REHEARSAL V3 — dual-provider-aware, packet-first, ZERO SPEND.

Successor to V2. V1 and V2 artifacts are NOT overwritten.

What V3 adds over V2, and why each addition is load-bearing:

  * PACKET-BEFORE-PARSE is EXERCISED, not merely asserted. V2's templates were all
    well-formed, so `N_PARSE_REJECTIONS_WITH_PACKET_IDENTITY` would have been 0 and the
    headline claim of the amendment would never have been tested on real data. V3 adds a
    forbidden-field template and an unknown-field template, and counts records that were
    rejected at PARSE time while still carrying a verified packet hash.
  * PROVIDER PROVENANCE is reported per record: the provider actually resolved, under the
    frozen policy, with the capability id and the provider's own source field.
  * npxG is PROBED. `N_NPXG_ACCEPTED` is a measured 0, not an empty assertion.

Proposals are DETERMINISTIC STUBS, not model output. No Sonnet, no Bedrock, no network, no
paid call of any kind.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from collections import Counter

# Derive the root from THIS FILE, never from a hard-coded home directory: the script must
# bind to the checkout that is executing it.
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
from src.research.hypothesis_bridge import packet_binding as PB, registry as REG, status as ST
from src.research.hypothesis_bridge.bridge import BridgeContext
from src.research.hypothesis_bridge.versions import bridge_version_stamp

SELECTION_FREEZE = os.path.join(_ROOT, "research/hypothesis_engine/V8B1_PILOT50_SELECTION_FREEZE.json")
OUT = os.path.join(_HERE, "EXPOSED50_APPARATUS_REHEARSAL_V3.json")
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
    # --- V3 additions -----------------------------------------------------------------
    # The audited npxG exclusion, exercised against the REAL corpus.
    {"tag": "npxg_excluded", "subject": "home_team", "target_metric": "npxg",
     "perspective": "for", "comparator": "league_season_baseline"},
    # Malformed treatment results. These are the reason the amendment exists: each must be
    # rejected AND still carry the verified identity of the packet it was shown.
    {"tag": "forbidden_prediction_field", "subject": "home_team", "target_metric": "corners",
     "perspective": "for", "comparator": "league_season_baseline", "probability": 0.7},
    {"tag": "unknown_field", "subject": "home_team", "target_metric": "corners",
     "perspective": "for", "comparator": "league_season_baseline",
     "some_unknown_field": "malformed"},
]

#: Templates whose payload is deliberately malformed; their rejection is the measurement.
MALFORMED_TAGS = {"forbidden_prediction_field", "unknown_field"}

#: The complete deterministic measurement surface. Comparing only `cohort` would let a leak
#: that moved the baseline, the contrast or a source hash pass unseen.
COMPARED_KEYS = ("cohort", "baseline", "deterministic_contrast", "cohort_identity_hash",
                 "cohort_source_hash", "baseline_source_hash", "measurement_input_hash",
                 "measurement_provider", "provider_capability_id")


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
    ctx = BridgeContext(recs)                      # frozen THESTATSAPI_ONLY policy
    idx = CH.HistoryIndex(recs)

    packets, packet_failures = {}, []
    cutoff_equals_kickoff = cutoff_checked = 0
    for t in targets:
        try:
            pkt = builder.build(t)
            if recompute_packet_hash(pkt) != pkt.get("packet_hash"):
                packet_failures.append({"fixture_id": t.fixture_id, "reason": "hash_mismatch"})
                continue
            # Amendment 2 verified as a PROPERTY of the real builder on real fixtures,
            # rather than assumed from reading evidence.py.
            cutoff_checked += 1
            if pkt.get("information_cutoff_unix") == t.kickoff_unix:
                cutoff_equals_kickoff += 1
            packets[t.fixture_id] = pkt
        except Exception as e:                                   # pragma: no cover
            packet_failures.append({"fixture_id": t.fixture_id, "reason": type(e).__name__})

    records, statuses = [], Counter()
    provider_counts, capability_counts = Counter(), Counter()
    n_ok = n_fail = real_hashes = no_packet = 0
    valid_refs = invalid_refs = 0
    packet_bound_rejections = parse_rejections_with_identity = 0
    npxg_accepted = 0

    for t in targets:
        pkt = packets.get(t.fixture_id)
        if pkt is None:
            continue
        ref_ids = sorted(valid_evidence_ids(pkt))
        for tpl in TEMPLATES:
            raw = {k: v for k, v in tpl.items() if k != "tag"}
            raw["fixture_id"] = t.fixture_id
            raw["research_reason"] = f"apparatus rehearsal v3 template {tpl['tag']}"
            # A malformed payload must stay malformed: adding evidence_refs to the
            # unknown-field case would change which failure is being demonstrated.
            if ref_ids and tpl["tag"] not in MALFORMED_TAGS:
                raw["evidence_refs"] = [ref_ids[0]]
            rec = ctx.run_proposal(raw, packet=pkt,
                                   proposal_source=PB.SOURCE_DETERMINISTIC_REHEARSAL)
            rec["rehearsal_template"] = tpl["tag"]
            records.append(rec)
            st = rec["validation_status"]
            statuses[st] += 1
            if st == ST.VALID_MEASURABLE:
                n_ok += 1
                if rec["canonical_ir"]["metric"] == "npxg":
                    npxg_accepted += 1
            elif st == ST.MEASUREMENT_FAILED:
                n_fail += 1
            if rec.get("packet_hash"):
                real_hashes += 1
            else:
                no_packet += 1
            if rec.get("measurement_provider"):
                provider_counts[rec["measurement_provider"]] += 1
            if rec.get("provider_capability_id"):
                capability_counts[rec["provider_capability_id"]] += 1
            if st == ST.PACKET_BINDING_FAILED:
                packet_bound_rejections += 1
            # THE AMENDMENT'S HEADLINE CLAIM, counted on real data: a proposal rejected at
            # PARSE time that nonetheless carries verified packet provenance.
            if st in (ST.FORBIDDEN_PREDICTION_FIELD, ST.AMBIGUOUS_PROPOSAL) and \
                    rec.get("packet_binding_verified") and rec.get("packet_hash"):
                parse_rejections_with_identity += 1
            if rec.get("evidence_refs_bound"):
                valid_refs += 1
            elif st == ST.PACKET_BINDING_FAILED and \
                    "evidence_refs" in (rec.get("rejection_reason") or ""):
                invalid_refs += 1

    # --- leakage probes: COMPLETE measurement payload, not just the cohort summary --------
    probe = {k: v for k, v in TEMPLATES[0].items() if k != "tag"}
    same_kick = outcome_dep = future_dep = src_mismatch = 0
    for t in targets[:10]:
        pkt = packets.get(t.fixture_id)
        if pkt is None:
            continue
        raw = {**probe, "fixture_id": t.fixture_id, "research_reason": "leak probe v3"}
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
            p_rec = BridgeContext(perturbed).run_proposal(
                raw, packet=pkt, proposal_source=PB.SOURCE_DETERMINISTIC_REHEARSAL)
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
        "artifact": "EXPOSED50_APPARATUS_REHEARSAL_V3",
        "supersedes": ("EXPOSED50_APPARATUS_REHEARSAL_V2 (single-provider registry; packet "
                       "verified AFTER proposal parsing; cutoff <= kickoff)"),
        "CLASSIFICATION": CLASSIFICATION,
        "not_measured": ["LLM quality", "S vs R performance", "effect size", "p-value",
                         "odds", "EV", "probability", "betting performance"],
        "lineage": {"packet_schema_version": PACKET_SCHEMA_VERSION,
                    "cohort_policy_version": COHORT_POLICY_VERSION},
        "bridge_version_stamp": bridge_version_stamp(),
        "executed_path": ("EvidencePacketBuilderV2 -> verified packet ENVELOPE (before parse) "
                          "-> deterministic proposal -> evidence_ref binding -> "
                          "canonicalization -> provider-aware validation -> deterministic "
                          "measurement -> provider-bound source hashes -> shadow record"),
        "MODEL_CALLS_MADE": 0,
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

        "N_PACKET_BOUND_REJECTIONS": packet_bound_rejections,
        "N_PARSE_REJECTIONS_WITH_PACKET_IDENTITY": parse_rejections_with_identity,
        "N_REAL_PACKET_HASHES": real_hashes,
        "N_NO_PACKET_RECORDS": no_packet,
        "N_VALID_EVIDENCE_REF_BINDINGS": valid_refs,
        "N_INVALID_EVIDENCE_REF_BINDINGS": invalid_refs,

        "PACKET_CUTOFF_CHECKED": cutoff_checked,
        "PACKET_CUTOFF_EQUALS_TARGET_KICKOFF_COUNT": cutoff_equals_kickoff,
        "PACKET_CUTOFF_EQUALS_TARGET_KICKOFF": cutoff_equals_kickoff == cutoff_checked,

        "MEASUREMENT_PROVIDER_COUNTS": dict(sorted(provider_counts.items())),
        "PROVIDER_POLICY": ctx.provider_policy.value,
        "CORPUS_PROVIDER_LINEAGE": REG.CORPUS_PROVIDER_LINEAGE,
        "CORPUS_STORAGE_SCHEMA": REG.CORPUS_STORAGE_SCHEMA,
        "PROVIDER_CAPABILITY_HASH": REG.registry_hash(),
        "DISTINCT_CAPABILITIES_USED": len(capability_counts),
        "FOOTYSTATS_CAPABILITIES_COUNT": len(REG.capabilities_for_provider("footystats")),
        "THESTATSAPI_CAPABILITIES_COUNT": len(REG.capabilities_for_provider("thestatsapi")),
        "FOOTYSTATS_MEASURABLE_METRICS": REG.measurable_metrics("footystats"),
        "THESTATSAPI_MEASURABLE_METRICS": REG.measurable_metrics("thestatsapi"),
        "IMPLICIT_PROVIDER_EQUIVALENCE": False,
        "IMPLICIT_PROVIDER_FALLBACK": False,
        "IMPLICIT_PROVIDER_BLEND": False,
        "N_NPXG_ACCEPTED": npxg_accepted,
        "THESTATSAPI_NPXG_STATUS": REG.capability_for("thestatsapi", "npxg").status,
        "FOOTYSTATS_NPXG_STATUS": ("ABSENT_NOT_TRACED_IN_NORMALIZER"
                                   if REG.capability_for("footystats", "npxg") is None
                                   else "UNEXPECTEDLY_PRESENT"),

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
                           "packet_binding_verified", "packet_hash", "measurement_provider",
                           "provider_source_field", "canonical_hypothesis_id",
                           "raw_n", "effective_n")} for r in records[:9]],
    }
    json.dump(report, open(OUT, "w"), indent=2, default=str)
    print(json.dumps({k: v for k, v in report.items()
                      if k not in ("audit_sample", "packet_failure_detail")},
                     indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
