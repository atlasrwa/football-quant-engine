"""Project a V5A.1 packet into the view `availability.build_ontology` consults.

`availability.py` is frozen and reused unchanged. It reads exactly three things from a
packet: the capability manifest's offered dimensions/metrics/coverage, the SCOPES present
in the evidence (windows, venues, subjects), and the observed formation families per
subject. This module derives those three facts from a V5A.1 packet's exposure map and
evidence tables and hands them over in the shape the frozen function expects.

Crucially the scopes are derived from what the packet ACTUALLY EXPOSES, so an arm that does
not carry venue-split or short-window evidence yields an ontology in which those dimensions
are not offered -- which is the point of the exposure triple (task §8), and the reason a
venue question against a base-arm packet is rejected rather than silently accepted.

ZERO SPEND.
"""
from __future__ import annotations

from typing import Optional

from src.research.hypothesis_engine import availability, capability, context_packet as CP
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_semantics as S

#: V5A.1 exposure dimension -> the vocabulary dimension it gates.
_EXPOSURE_TO_DIMENSION = {
    "venue_splits": "venue",
    "opponent_profile_response": "opponent_profile",
    "formation_recorded_history": ("own_formation_family", "opponent_formation_family"),
}

_WINDOW_TO_V3 = {"ALL_PRIOR": "ALL_PRIOR", "W5": "W5", "W10": "W10"}
_VENUE_TO_V3 = {"ANY": "ALL", "HOME_ONLY": "HOME", "AWAY_ONLY": "AWAY"}


def exposure_states(packet: dict) -> dict:
    out = {}
    for sec in packet.get("sections") or []:
        if sec.get("section_type") != "AVAILABILITY_MAP":
            continue
        for rec in sec.get("records") or []:
            d = rec.get("dimension")
            if d:
                out[d] = rec.get("EXPOSED_TO_LLM")
    return out


def _exposed(state) -> bool:
    return state in (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)


def _scopes_and_formations(packet: dict):
    """Windows / venues / subjects actually present, and formation families per subject."""
    windows, venues, subjects = set(), set(), set()
    formations: dict = {}
    for sec in packet.get("sections") or []:
        st = sec.get("section_type")
        if st == "DERIVED_SUMMARIES":
            cols = sec.get("columns") or []
            iw = cols.index("window") if "window" in cols else None
            iv = cols.index("venue_scope") if "venue_scope" in cols else None
            isb = cols.index("subject") if "subject" in cols else None
            for row in sec.get("rows") or []:
                if iw is not None:
                    windows.add(_WINDOW_TO_V3.get(row[iw], row[iw]))
                if iv is not None:
                    venues.add(_VENUE_TO_V3.get(row[iv], row[iv]))
                if isb is not None:
                    subjects.add(row[isb])
        elif st == "MATCH_LEVEL_OBSERVATIONS":
            for blk in sec.get("blocks") or []:
                subjects.add(blk.get("subject"))
                for row in blk.get("rows") or []:
                    v = row.get("venue")
                    if v:
                        venues.add(v)
        elif st == "FORMATION_CONTEXT":
            for rec in sec.get("records") or []:
                subj = rec.get("subject")
                hist = rec.get("recorded_formation_histogram") or {}
                if subj:
                    formations[subj] = dict(hist)
    return (tuple(sorted(windows)), tuple(sorted(venues)), tuple(sorted(subjects)),
            formations)


def build_ontology_view(packet: dict,
                        manifest: Optional[capability.FixtureCapabilityManifest] = None):
    """Return `availability.ResearchOntology` for a V5A.1 packet, via the frozen builder."""
    states = exposure_states(packet)
    windows, venues, subjects, formations = _scopes_and_formations(packet)

    offered = ["competition"]
    if _exposed(states.get("venue_splits")):
        offered.append("venue")
    if _exposed(states.get("opponent_profile_response")):
        offered.append("opponent_profile")
    if _exposed(states.get("formation_recorded_history")):
        offered += ["own_formation_family", "opponent_formation_family"]

    coverage = {}
    for sec in packet.get("sections") or []:
        if sec.get("section_type") != "AVAILABILITY_MAP":
            continue
        for rec in sec.get("records") or []:
            if rec.get("dimension") == "formation_recorded_history":
                cov = rec.get("coverage")
                if cov is not None:
                    coverage["own_formation_family"] = {"coverage_rate": cov}
                    coverage["opponent_formation_family"] = {"coverage_rate": cov}

    view = {
        "fixture_id": packet.get("fixture_id", ""),
        "capability_manifest": {
            "fixture_id": packet.get("fixture_id", ""),
            "available_dimensions": sorted(set(offered)),
            "available_metrics": list(S.CANONICAL_METRICS),
            "coverage": coverage,
            "notes": ["dimensions reflect what THIS packet exposes, not what the upstream "
                      "corpus could derive"],
        },
        # `_evidence_scopes` reads scope dicts; supply one stub per observed scope triple.
        "evidence": [{"scope": {"window": w, "venue": v, "subject": s}}
                     for w in (windows or ("ALL_PRIOR",))
                     for v in (venues or ("ALL",))
                     for s in (subjects or ("HOME", "AWAY"))],
        "formation_distribution": formations,
    }
    man = manifest
    if man is None:
        man = CP.build_capability_manifest(
            fixture_id=view["fixture_id"],
            available_metrics=[m for m in S.CANONICAL_METRICS
                               if capability.is_supported_metric(m)],
            formation_coverage_report=None,
            half_level_available=False, referee_available=False)
        man = _restrict(man, view["capability_manifest"]["available_dimensions"])
    return availability.build_ontology(view, man)


def _restrict(manifest, dimensions):
    """Keep only the dimensions this packet actually exposes."""
    keep = tuple(d for d in manifest.available_dimensions if d in set(dimensions))
    try:
        return manifest.__class__(**{**manifest.__dict__, "available_dimensions": keep})
    except TypeError:
        object.__setattr__(manifest, "available_dimensions", keep)
        return manifest
