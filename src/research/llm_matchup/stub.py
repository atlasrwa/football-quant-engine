"""Deterministic offline STUB analyst — for golden tests / contract exercise ONLY.

This is NOT an LLM and MUST NOT be used to manufacture research features (that would be
fabrication). It exists so the validator, schema, evidence-id and abstention contracts can
be tested without live Bedrock, and so golden cases have a reference producer that behaves
like a well-behaved analyst (honest UNKNOWN, evidence citation, injection-inert).

It reads only the packet, follows the closed-world rules mechanically, and never invents
facts. Any test asserting behavior on malicious/future/tiny data uses this producer.
"""
from __future__ import annotations
from src.research.llm_matchup import ontology as ONT


def _pit_items(packet, prefix, allow):
    out = []
    for e in packet["evidence"]:
        if e["temporal_status"] != "PIT_SAFE" or e["value"] is None:
            continue
        if not e["id"].startswith(prefix):
            continue
        base = e["metric"]
        if any(a in base for a in allow):
            out.append(e)
    return out


def _level_from_reliability(items):
    if not items:
        return "UNKNOWN", "LOW", ["SMALL_SAMPLE"]
    best = max(items, key=lambda e: e["sample_n"])
    if best["reliability"] == "HIGH":
        return "MEDIUM", "MEDIUM", []
    if best["reliability"] == "MEDIUM":
        return "MEDIUM", "MEDIUM_LOW", ["SMALL_SAMPLE"]
    return "LOW", "LOW", ["SMALL_SAMPLE", "SHRUNK_TO_PRIOR"]


def stub_analyze(packet: dict) -> dict:
    """Produce a schema-valid, evidence-cited, honestly-abstaining football state."""
    cf = {
        "formation_status": packet["unsupported_context"].get("formation_status", "FORMATION_UNKNOWN"),
        "formation_resolution_status": (packet.get("formation_context", {}) or {}).get(
            "resolution_status", "RESOLVED_UNAVAILABLE"),
        "prematch_formation_status": (packet.get("formation_context", {}) or {}).get(
            "prematch_status", "PREMATCH_UNKNOWN"),
        "injury_status": packet["unsupported_context"].get("injury_status", "INJURY_STATUS_UNKNOWN"),
        "neutral_venue": packet["unsupported_context"].get("neutral_venue", "UNKNOWN"),
        "score_state_conditioning": "UNAVAILABLE",
        "provider_agreement": "SINGLE_PROVIDER",
    }

    def team_states(prefix):
        states = []
        for mech in ("WIDTH_PRESSURE", "BOX_PRESSURE", "CONTACT_INTENSITY"):
            allow = ONT.allowed_metric_prefixes(mech)
            items = _pit_items(packet, prefix, allow)
            level, conf, unc = _level_from_reliability(items)
            states.append({
                "mechanism": mech, "level": level, "confidence": conf,
                "evidence_ids": [e["id"] for e in items[:4]],
                "counter_evidence_ids": [],
                "uncertainty_factors": unc,
                "preferred_evidence_level": (items[0]["evidence_level"] if items else "NONE"),
            })
        return states

    # a matchup state: A width pressure vs B (cite from both sides where allowed)
    allow = ONT.allowed_metric_prefixes("WIDE_PRESSURE_MATCHUP")
    a_side = _pit_items(packet, "A_", allow)
    b_side = _pit_items(packet, "B_", allow)
    sup = [e["id"] for e in a_side[:2]] + [e["id"] for e in b_side[:2]]
    if sup:
        assessment, conf = "A_ADVANTAGE", "MEDIUM_LOW"
        unc = ["SMALL_SAMPLE"] if any(e["reliability"] == "LOW" for e in a_side + b_side) else []
    else:
        assessment, conf, unc = "UNKNOWN", "UNKNOWN", ["WIDE_COHORT_ONLY"]
    matchup = [{
        "mechanism": "WIDE_PRESSURE_MATCHUP", "assessment": assessment, "confidence": conf,
        "supporting_evidence_ids": sup, "counter_evidence_ids": [], "uncertainty_factors": unc,
    }]

    return {
        "fixture_id": str(packet["fixture"]["fixture_id"]),
        "information_cutoff_unix": int(packet["information_cutoff_unix"]),
        "context_flags": cf,
        "team_a_states": team_states("A_"),
        "team_b_states": team_states("B_"),
        "matchup_states": matchup,
    }
