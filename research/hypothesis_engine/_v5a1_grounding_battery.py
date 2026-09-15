"""V5A.1 end-to-end evidence-grounding battery (task §19). ZERO SPEND.

Deterministic synthetic hypotheses are pushed through schema -> validator -> firewall ->
compiler against REAL frozen packets from BOTH arms. This is the regression that the
aborted V5A failed silently: its treatment arm could not accept a single grounded
hypothesis, and nothing checked before the money was committed.
"""
from __future__ import annotations

import sys

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import query_plan as QP, validator_v3 as V3
from src.research.hypothesis_oos import v5a1_evidence as E


def hyp(hid, *, refs, family="SET_PIECE_GENERATION", subject="HOME_TEAM",
        metrics=("corners",), side="FOR", window="ALL_PRIOR", conditions=(),
        comparison="SUBJECT_OVERALL_BASELINE", caps=(), sufficiency="SUFFICIENT",
        question=None):
    return {
        "hypothesis_id": hid,
        "research_family": family,
        "subject": subject,
        "question": question or ("Does HOME_TEAM's corner production differ from its own "
                                 "overall prior baseline across the matches recorded here?"),
        "target_metrics": list(metrics),
        "side": side,
        "window": window,
        "conditions": [dict(c) for c in conditions],
        "comparison": comparison,
        "evidence_refs": list(refs),
        "candidate_confounders": ["competition"],
        "required_capabilities": list(caps),
        "sufficiency": sufficiency,
        "priority": "MEDIUM",
    }


def payload(packet, hypotheses):
    return {"fixture_id": packet["fixture_id"], "packet_hash": packet["packet_hash"],
            "hypotheses": hypotheses}


def run_one(packet, h, *, compile_too=True):
    res = V3.validate(payload(packet, [h]), packet=packet,
                      expected_packet_hash=packet["packet_hash"],
                      expected_fixture_id=packet["fixture_id"])
    out = {"schema_ok": res.accepted, "reasons": list(res.reasons),
           "verdicts": [(v.hypothesis_id, v.accepted, v.failure, list(v.reasons))
                        for v in res.verdicts],
           "accepted_n": len(res.accepted_hypotheses), "compiled": None}
    if compile_too and res.accepted_hypotheses:
        plans = QP.compile_hypothesis(res.accepted_hypotheses[0],
                                      fixture_id=packet["fixture_id"],
                                      cutoff_unix=packet["information_cutoff_unix"])
        out["compiled"] = [(p.status if hasattr(p, "status") else None,
                            getattr(p, "reasons", None)) for p in plans]
        out["compile_ok"] = all(getattr(p, "plan", None) is not None for p in plans)
    return out


def pick(packet):
    """Real ids of each kind from this packet (or None when the arm lacks that kind)."""
    ids = E.resolve_evidence_ids(packet)
    def first(pref, contains=None):
        c = sorted(i for i in ids if i.startswith(pref) and (contains is None or contains in i))
        return c[0] if c else None
    return {
        "match_row": first("MATCH:HOME:M0"),
        "match_cells": sorted(i for i in ids if i.startswith("MATCH:HOME:M01:corners"))[:2],
        "summary_all": first("SUMMARY:HOME:ALL_PRIOR:ANY:corners_for"),
        "summary_venue": first("SUMMARY:HOME:ALL_PRIOR:HOME_ONLY:corners_for"),
        "summary_recent": first("SUMMARY:HOME:W5:ANY:corners_for"),
        "profile": first("PROFILE:HOME:"),
        "formation": first("FORMATION:HOME"),
        "all_ids": ids,
    }
