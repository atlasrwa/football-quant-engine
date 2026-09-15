"""Packet-scoped admissibility over the ontology (`v5a2_admissibility_v1`).

V5A.1's gate needed a private indirection table:

    _DIMENSION_REQUIRES = {"venue": "venue_splits",
                           "opponent_profile": "opponent_profile_response"}

because the dimension the model wrote and the availability key the packet declared were
different strings. That table was a fourth hand-maintained vocabulary, and it is exactly
the kind of thing this iteration exists to delete: when `competition` was left out of it,
`packet_capability_summary` advertised competition conditioning against a base-arm packet
that carried no competition data at all.

Here the availability map is keyed by the SAME ontology terms the model conditions on, so
the gate is a direct lookup with no mapping layer to get wrong:

    a condition on term T is admissible  <=>  the packet declares T exposed.

Metrics, windows and comparisons still need their own rules -- they are not terms -- and
those are unchanged in substance from V5A.1.

ZERO SPEND.
"""
from __future__ import annotations

from typing import Optional

from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_semantics as S
from src.research.hypothesis_oos import v5a2_ontology as O

ADMISSIBILITY_VERSION = "v5a2_admissibility_v1"

_EXPOSED_STATES = (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)

#: Comparison -> the ontology term whose evidence it needs. Absent = always supported.
COMPARISON_REQUIRES_TERM = {
    "SUBJECT_VENUE_BASELINE": O.HISTORICAL_VENUE_CONDITIONING,
    "SUBJECT_RECENT_VS_LONG_BASELINE": "recent_window_summaries",
}

#: Comparisons no packet in this corpus can support, with the reason the model is shown.
COMPARISON_UNSUPPORTED = {
    "SUBJECT_COMPETITION_BASELINE":
        "this packet carries no per-competition aggregate; the competition is a label on "
        "each match row, not a baseline you can compare against",
    "LEAGUE_ENVIRONMENT_BASELINE":
        "this packet carries no league-environment aggregate of any kind",
}


def exposure_states(packet: Optional[dict]) -> dict:
    """term -> EXPOSED_TO_LLM, read off the packet's own availability map."""
    out: dict = {}
    for sec in (packet or {}).get("sections") or []:
        if sec.get("section_type") != "AVAILABILITY_MAP":
            continue
        for rec in sec.get("records") or []:
            dim = rec.get("dimension") or (rec.get("extra") or {}).get("dimension")
            if dim:
                out[dim] = rec.get("EXPOSED_TO_LLM") or \
                    (rec.get("extra") or {}).get("EXPOSED_TO_LLM")
    return out


def is_exposed(packet: Optional[dict], term: str) -> bool:
    return exposure_states(packet).get(term) in _EXPOSED_STATES


def exposed_windows(packet: Optional[dict]) -> set:
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
    """Why this hypothesis is not answerable from THIS packet. Empty list = admissible.

    `hypothesis` is in MODEL LANGUAGE (ontology terms). This gate runs before translation
    precisely so its reasons quote the terms the model actually wrote.
    """
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
                           f"({excl['excluded_because']}); the METRIC_SEMANTICS section "
                           f"lists it as excluded and says why")
        else:
            reasons.append(f"target metric {m!r} is not exposed by this packet")

    window = hypothesis.get("window")
    wins = exposed_windows(packet)
    if window and window not in wins:
        reasons.append(f"window {window!r} has no summary in this packet "
                       f"(exposed windows: {sorted(wins)})")

    for cond in (hypothesis.get("conditions") or []):
        term = cond.get("dimension")
        spec = O.term(term) if isinstance(term, str) else None
        if spec is None:
            reasons.append(f"condition dimension {term!r} is not a declared term")
            continue
        state = states.get(term)
        if state in _EXPOSED_STATES:
            continue
        if not spec["corpus_supported"]:
            reasons.append(f"term {term!r} is not available anywhere in this corpus: "
                           f"{spec['desc']}")
        else:
            reasons.append(f"term {term!r} is declared {state!r} in this packet's "
                           f"availability map, so a cohort cannot be split on it here")

    # `required_capabilities` is a CLAIM about what the hypothesis leans on, and a claim
    # about evidence the packet does not carry is a real contract failure -- not a
    # translation problem. Checked in model language, before translation, for the same
    # reason the conditions are.
    for term in (hypothesis.get("required_capabilities") or []):
        spec = O.term(term) if isinstance(term, str) else None
        if spec is None:
            reasons.append(f"required capability {term!r} is not a declared term")
            continue
        if states.get(term) not in _EXPOSED_STATES:
            reasons.append(f"this hypothesis declares it requires {term!r}, which this "
                           f"packet declares {states.get(term)!r}")

    comp = hypothesis.get("comparison")
    if comp in COMPARISON_UNSUPPORTED:
        reasons.append(f"comparison {comp!r} cannot be evaluated against this packet: "
                       f"{COMPARISON_UNSUPPORTED[comp]}")
    else:
        need = COMPARISON_REQUIRES_TERM.get(comp)
        if need and states.get(need) not in _EXPOSED_STATES:
            reasons.append(f"comparison {comp!r} requires {need!r}, which this packet "
                           f"declares {states.get(need)!r}")
    return reasons


def packet_capability_summary(packet: Optional[dict]) -> dict:
    """The exact admissible surface of this packet, in model language.

    Derived wholly from the availability map, so it cannot disagree with what the model
    was shown -- the disagreement that let V5A.1 advertise competition conditioning in an
    arm with no competition data.
    """
    states = exposure_states(packet)
    exposed = sorted(t for t in O.all_terms() if states.get(t) in _EXPOSED_STATES)
    return {
        "ontology_version": O.ONTOLOGY_VERSION,
        "metrics": sorted(exposed_metrics(packet)),
        "excluded_metrics": sorted(S.EXCLUDED_METRICS),
        "windows": sorted(exposed_windows(packet)),
        "exposed_terms": exposed,
        "conditionable_terms": sorted(t for t in exposed
                                      if t in O.condition_dimension_terms()),
        "unexposed_terms": sorted(t for t in O.all_terms() if t not in exposed),
        "comparisons": sorted(
            ["SUBJECT_OVERALL_BASELINE"]
            + [c for c, need in COMPARISON_REQUIRES_TERM.items()
               if states.get(need) in _EXPOSED_STATES]),
        "unsupported_comparisons": sorted(COMPARISON_UNSUPPORTED),
    }
