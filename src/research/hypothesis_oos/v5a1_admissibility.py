"""Packet-scoped admissibility (`v5a1_admissibility_v1`).

`schema_v2` and `vocabulary` are frozen -- they are hashed into the V3 preregistration and
must not change. But their enums are WIDER than any one packet: they admit `dangerous_attacks`,
`attacks`, `total_bookings`, `SEASON_TO_DATE`, `LEAGUE_ENVIRONMENT_BASELINE`, `referee`,
`half_score_state` and seven opponent-profile axes that no V5A.1 packet backs. In the aborted
V5A that mismatch was defect M-3: the model was told the vocabulary was "the closed set of
metrics you may use" while the packet could not support a third of it.

Rather than edit the frozen enums, this gate narrows them PER PACKET: a hypothesis is
admissible only if every metric, window, dimension and comparison it uses is actually
exposed by the packet that was sent. The packet declares that set in its availability map
and metric-semantics sections, so the model can see the same boundary the gate enforces.

ZERO SPEND.
"""
from __future__ import annotations

from typing import Optional

from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_semantics as S

ADMISSIBILITY_VERSION = "v5a1_admissibility_v1"

#: Comparison -> the exposure dimension it requires. Absent = always supported.
_COMPARISON_REQUIRES = {
    "SUBJECT_VENUE_BASELINE": "venue_splits",
    "SUBJECT_RECENT_VS_LONG_BASELINE": "recent_vs_long",
}

#: Comparisons no V5A.1 packet can support, with the reason the model is shown.
_COMPARISON_UNSUPPORTED = {
    "SUBJECT_COMPETITION_BASELINE":
        "this packet carries no per-competition aggregate, only a competition alias on "
        "each match row",
    "LEAGUE_ENVIRONMENT_BASELINE":
        "this packet carries no league-environment aggregate of any kind",
}

_DIMENSION_REQUIRES = {
    "venue": "venue_splits",
    "opponent_profile": "opponent_profile_response",
}

#: Dimensions that can only be CONDITIONED on when the packet exposes the field on each
#: observation. A coverage summary tells you how much formation data exists; it does not
#: let anyone split a cohort by it. Both arms carry the formation coverage record, so
#: without this a formation-conditioned hypothesis would be admitted against a packet with
#: no per-match formation at all -- the V5A HS-3 failure mode returning by a side door.
_DIMENSION_REQUIRES_PER_OBSERVATION = {
    "own_formation_family": ("formation_recorded_history", "match_level_observations"),
    "opponent_formation_family": ("formation_recorded_history", "match_level_observations"),
}

_DIMENSION_UNSUPPORTED = {
    "half_score_state": "no half-level data exists in this corpus",
    "period": "no half-level split exists in this corpus",
    "referee": "no referee field is surfaced by the adapter for this corpus",
}


def exposure_states(packet: Optional[dict]) -> dict:
    if not packet:
        return {}
    out = {}
    for sec in packet.get("sections") or []:
        if sec.get("section_type") != "AVAILABILITY_MAP":
            continue
        for rec in sec.get("records") or []:
            if rec.get("dimension"):
                out[rec["dimension"]] = rec.get("EXPOSED_TO_LLM")
    return out


def _is_exposed(states, key) -> bool:
    return states.get(key) in (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)


def exposed_windows(packet: Optional[dict]) -> set:
    """Windows for which this packet actually carries a summary."""
    w = set()
    for sec in (packet or {}).get("sections") or []:
        if sec.get("section_type") != "DERIVED_SUMMARIES":
            continue
        cols = sec.get("columns") or []
        if "window" not in cols:
            continue
        i = cols.index("window")
        w.update(row[i] for row in (sec.get("rows") or []) if len(row) > i)
    return w


def exposed_metrics(packet: Optional[dict]) -> set:
    return set(S.CANONICAL_METRICS)


def packet_admissibility_reasons(hypothesis: dict, packet: Optional[dict]) -> list:
    """Why this hypothesis is not answerable from THIS packet. Empty list = admissible."""
    if not packet:
        return []
    states = exposure_states(packet)
    reasons: list = []

    metrics = exposed_metrics(packet)
    for m in (hypothesis.get("target_metrics") or []):
        if m in metrics:
            continue
        excl = S.EXCLUDED_METRICS.get(m)
        if excl:
            reasons.append(f"target metric {m!r} is deliberately excluded from this packet "
                           f"({excl['excluded_because']}); the packet's metric_semantics "
                           f"section lists it as excluded and says why")
        else:
            reasons.append(f"target metric {m!r} is not exposed by this packet")

    window = hypothesis.get("window")
    wins = exposed_windows(packet)
    if window and window not in wins:
        reasons.append(f"window {window!r} has no summary in this packet "
                       f"(exposed windows: {sorted(wins)})")

    for cond in (hypothesis.get("conditions") or []):
        dim = cond.get("dimension")
        if dim in _DIMENSION_UNSUPPORTED:
            reasons.append(f"dimension {dim!r} is not available in this corpus: "
                           f"{_DIMENSION_UNSUPPORTED[dim]}")
            continue
        req = _DIMENSION_REQUIRES.get(dim)
        if req and not _is_exposed(states, req):
            reasons.append(f"dimension {dim!r} requires evidence this packet does not "
                           f"expose ({req} = {states.get(req)!r})")
        for need in _DIMENSION_REQUIRES_PER_OBSERVATION.get(dim, ()):
            if not _is_exposed(states, need):
                reasons.append(f"dimension {dim!r} can only be conditioned on when the "
                               f"packet carries the value on each observation; this packet "
                               f"does not expose {need} ({states.get(need)!r})")

    comp = hypothesis.get("comparison")
    if comp in _COMPARISON_UNSUPPORTED:
        reasons.append(f"comparison {comp!r} cannot be evaluated against this packet: "
                       f"{_COMPARISON_UNSUPPORTED[comp]}")
    else:
        req = _COMPARISON_REQUIRES.get(comp)
        if req and not _is_exposed(states, req):
            reasons.append(f"comparison {comp!r} requires evidence this packet does not "
                           f"expose ({req} = {states.get(req)!r})")
    return reasons


def packet_capability_summary(packet: Optional[dict]) -> dict:
    """The exact admissible surface, for the prompt-vs-data support audit."""
    states = exposure_states(packet)
    return {
        "metrics": sorted(exposed_metrics(packet)),
        "excluded_metrics": sorted(S.EXCLUDED_METRICS),
        "windows": sorted(exposed_windows(packet)),
        "dimensions": sorted(
            [d for d, req in _DIMENSION_REQUIRES.items() if _is_exposed(states, req)]
            + [d for d, needs in _DIMENSION_REQUIRES_PER_OBSERVATION.items()
               if all(_is_exposed(states, n) for n in needs)]
            + ["competition"]),
        "comparisons": sorted(
            [c for c in ("SUBJECT_OVERALL_BASELINE",)] +
            [c for c, req in _COMPARISON_REQUIRES.items() if _is_exposed(states, req)]),
        "unsupported_comparisons": sorted(_COMPARISON_UNSUPPORTED),
        "unsupported_dimensions": sorted(_DIMENSION_UNSUPPORTED),
    }
