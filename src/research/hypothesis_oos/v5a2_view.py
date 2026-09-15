"""Project a V5A.2 packet into the view `availability.build_ontology` consults.

Identical in purpose to `v5a1_ontology`, and it reuses that module's scope/formation
extraction verbatim. Only the availability lookup differs: V5A.1 keyed `offered` off
`venue_splits` / `opponent_profile_response` / `formation_recorded_history`, which are no
longer the names the packet uses. Here `offered` is read off ONTOLOGY TERMS and translated
to internal dimension names by `v5a2_ontology.to_internal_dimension`, so there is no third
place where "which dimensions does this packet offer" is decided.

The `competition` difference is substantive, not cosmetic. `v5a1_ontology` appended
`"competition"` unconditionally; this reads the packet's own declaration, which for a
summary-only packet is NOT_EXPOSED_IN_PACKET because no competition data exists there.

ZERO SPEND.
"""
from __future__ import annotations

from typing import Optional

from src.research.hypothesis_engine import availability, capability, context_packet as CP
from src.research.hypothesis_oos import v5a1_ontology as VIEW1
from src.research.hypothesis_oos import v5a1_semantics as S
from src.research.hypothesis_oos import v5a2_admissibility as ADM
from src.research.hypothesis_oos import v5a2_ontology as O

VIEW_VERSION = "v5a2_view_v1"


def offered_internal_dimensions(packet: dict) -> list:
    """Internal dimension names this packet offers, derived from its availability map."""
    states = ADM.exposure_states(packet)
    out = set()
    for term in O.condition_dimension_terms():
        if states.get(term) in (ADM._EXPOSED_STATES):
            internal = O.to_internal_dimension(term)
            if internal:
                out.add(internal)
    return sorted(out)


def _formation_coverage(packet: dict) -> dict:
    cov = {}
    for sec in packet.get("sections") or []:
        if sec.get("section_type") != "AVAILABILITY_MAP":
            continue
        for rec in sec.get("records") or []:
            if rec.get("dimension") == "formation_recorded_history":
                c = rec.get("coverage")
                if c is not None:
                    cov["own_formation_family"] = {"coverage_rate": c}
                    cov["opponent_formation_family"] = {"coverage_rate": c}
    return cov


def build_ontology_view(packet: dict,
                        manifest: Optional[capability.FixtureCapabilityManifest] = None):
    windows, venues, subjects, formations = VIEW1._scopes_and_formations(packet)
    offered = offered_internal_dimensions(packet)

    view = {
        "fixture_id": packet.get("fixture_id", ""),
        "capability_manifest": {
            "fixture_id": packet.get("fixture_id", ""),
            "available_dimensions": offered,
            "available_metrics": list(S.CANONICAL_METRICS),
            "coverage": _formation_coverage(packet),
            "notes": ["dimensions reflect what THIS packet declares exposed, not what the "
                      "upstream corpus could derive"],
        },
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
        man = VIEW1._restrict(man, offered)
    return availability.build_ontology(view, man)
