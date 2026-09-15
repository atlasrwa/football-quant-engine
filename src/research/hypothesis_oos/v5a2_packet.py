"""V5A.2 packet surface (`v5a2_packet_v1`) -- one language, truthfully declared.

WHAT IS AND IS NOT CHANGED
--------------------------
The EVIDENCE is V5A.1's, untouched (task S2). Every match row, every summary, every
opponent-profile cohort, every formation record, the section order, the estimator, the
baseline universe and the raw-cell fidelity are exactly what `v5a1_packet` produced. This
module does not compute a single new number.

What changes is the SURFACE the model reads:

1. The availability map is re-keyed onto `v5a2_ontology` terms, and it now declares EVERY
   term in the model's enums rather than a private list of its own. Under V5A.1 the map
   said `venue_splits` / `opponent_profile_response` while the schema said `venue` /
   `opponent_profile` and the capability field said `venue` / `competition`. Three
   vocabularies, no stated relationship between them, and D1 was the result.

2. `target_fixture_venue_context` is declared SEPARATELY from
   `historical_venue_conditioning` (task S6), so the base arm can state truthfully that it
   knows which side is at home while withholding venue-split history.

3. Three terms are newly declared that V5A.1 left implicit, and declaring them exposed a
   real defect in the process:

     competition                 V5A.1's `packet_capability_summary` listed `competition`
                                 as an available dimension for BOTH arms unconditionally.
                                 The base arm carries no competition information anywhere
                                 -- no match rows, and no competition column on the
                                 summaries -- so a competition-conditioned hypothesis was
                                 admissible against a packet that could not answer it.
                                 Here it is exposed only when the match rows are.
     own_formation_family        Conditionable only when a recorded formation exists on
     opponent_formation_family   each observation, which needs the match rows. This is the
                                 same rule `v5a1_admissibility` enforced internally; it is
                                 now VISIBLE to the model rather than enforced silently
                                 after the fact.

4. The ontology snapshot itself is embedded, so the single-language rule is something the
   model is told rather than something we hope it infers.

ZERO SPEND.
"""
from __future__ import annotations

import copy

from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_packet as P1
from src.research.hypothesis_oos import v5a2_ontology as O

PACKET_SURFACE_VERSION = "v5a2_packet_v1"

#: Model-visible term -> the V5A.1 availability key carrying the same fact. Terms absent
#: from this map are newly declared and derived below.
_RENAMED_FROM_V5A1 = {
    "match_level_observations": "match_level_observations",
    O.HISTORICAL_VENUE_CONDITIONING: "venue_splits",
    "recent_window_summaries": "recent_vs_long",
    "opponent_profile": "opponent_profile_response",
    "formation_recorded_history": "formation_recorded_history",
    "xg": "xg",
    "expected_formation": "expected_formation",
    "lineup": "lineup",
    "injuries": "injuries",
    "weather": "weather",
    "referee": "referee",
    "half_time_score_state": "half_time_state",
    "minute_level_events": "minute_level_events",
    "player_ratings": "player_ratings",
    "market_prices": "market_prices",
}

_EXPOSED_STATES = (E.EXPOSED, E.EXPOSED_LOW_COVERAGE)


def _v5a1_records(packet: dict) -> dict:
    out = {}
    for sec in packet.get("sections") or []:
        if sec.get("section_type") == "AVAILABILITY_MAP":
            for rec in sec.get("records") or []:
                dim = (rec.get("extra") or rec).get("dimension")
                if dim:
                    out[dim] = rec
    return out


def _state_of(rec) -> str:
    return ((rec.get("extra") or {}).get("EXPOSED_TO_LLM")
            or rec.get("EXPOSED_TO_LLM") or E.NOT_EXPOSED_IN_PACKET)


def _triple_from(rec, term, extra_note="") -> E.ExposureTriple:
    x = rec.get("extra") or rec
    note = x.get("note", "")
    if extra_note:
        note = f"{note} {extra_note}".strip()
    return E.ExposureTriple(
        term, bool(x.get("PROVIDER_AVAILABLE")), bool(x.get("DERIVABLE_PIT_SAFE")),
        _state_of(rec), note, coverage=rec.get("coverage"))


def build_exposure_v2(packet: dict) -> list:
    """The full ontology-keyed availability map for one V5A.1 packet.

    Returns one `ExposureTriple` per ontology term, in sorted term order, so the map is
    byte-stable and so `test_availability_map_declares_every_model_visible_term` can
    compare it against `O.all_terms()` directly.
    """
    old = _v5a1_records(packet)
    rows = has_rows = _state_of(old["match_level_observations"]) in _EXPOSED_STATES
    form_state = _state_of(old["formation_recorded_history"])
    form_ok = form_state in _EXPOSED_STATES

    triples: dict = {}
    for term, old_key in _RENAMED_FROM_V5A1.items():
        rec = old.get(old_key)
        if rec is None:
            raise KeyError(f"V5A.1 packet has no availability record {old_key!r} for "
                           f"term {term!r}")
        extra = ""
        if term == O.HISTORICAL_VENUE_CONDITIONING:
            extra = ("This is about WHERE PRIOR MATCHES WERE PLAYED. Knowing which side is "
                     f"at home in the upcoming fixture is a different term, "
                     f"`{O.TARGET_FIXTURE_VENUE_CONTEXT}`, and does not license this split.")
        triples[term] = _triple_from(rec, term, extra)

    # ---- newly declared terms --------------------------------------------------------
    triples[O.TARGET_FIXTURE_VENUE_CONTEXT] = E.ExposureTriple(
        O.TARGET_FIXTURE_VENUE_CONTEXT, True, True, E.EXPOSED,
        "Which side of the UPCOMING fixture is at home is stated in "
        "TARGET_FIXTURE_CONTEXT and is always available. It is a fact about the fixture, "
        "not evidence about prior matches, so it is not something you can condition a "
        f"cohort on; for that see `{O.HISTORICAL_VENUE_CONDITIONING}`.")

    triples["competition"] = E.ExposureTriple(
        "competition", True, True,
        E.EXPOSED if has_rows else E.NOT_EXPOSED_IN_PACKET,
        "Each historical match row carries the competition it was played in, so a cohort "
        "can be restricted to the upcoming fixture's competition."
        if has_rows else
        "No competition information is present in this packet: there are no match rows, "
        "and the summaries are not split by competition. Do not condition on competition "
        "against this packet.")

    for term, who in (("own_formation_family", "the subject's"),
                      ("opponent_formation_family", "the opponent's")):
        if form_ok and has_rows:
            state = (E.EXPOSED_LOW_COVERAGE if form_state == E.EXPOSED_LOW_COVERAGE
                     else E.EXPOSED)
            note = (f"Structural family of {who} recorded formation is available on each "
                    f"match row.")
            if state == E.EXPOSED_LOW_COVERAGE:
                note += (" Coverage is low -- see formation_recorded_history for the "
                         "exact fraction before relying on it.")
        else:
            state = E.NOT_EXPOSED_IN_PACKET
            note = (f"Splitting a cohort by {who} formation needs the formation recorded "
                    f"on EACH observation. This packet has no match rows, so a coverage "
                    f"figure is all that exists and it is not enough to condition on.")
        triples[term] = E.ExposureTriple(
            term, True, True, state, note,
            coverage=(old["formation_recorded_history"].get("coverage")))

    triples["match_period"] = E.ExposureTriple(
        "match_period", False, False, E.NOT_PROVIDED_BY_SOURCE,
        "No half-level or period-level split exists anywhere in this corpus.")

    missing = set(O.all_terms()) - set(triples)
    if missing:
        raise AssertionError(f"availability map does not declare every model-visible "
                             f"term; missing: {sorted(missing)}")
    return [triples[t] for t in O.all_terms()]


def _availability_section(exposure, section_no: int) -> dict:
    return {
        "section": section_no,
        "section_type": "AVAILABILITY_MAP",
        "content": {
            "note": "Three different things, kept separate. Act ONLY on EXPOSED_TO_LLM: it "
                    "says whether the evidence is in THIS packet. PROVIDER_AVAILABLE and "
                    "DERIVABLE_PIT_SAFE describe the upstream corpus and are given for "
                    "transparency only -- a dimension can be derivable and still absent "
                    "here.",
            "states": list(E.EXPOSURE_STATES),
            "term_rule": "Every term listed here is spelled exactly the same way in your "
                         "response: in `conditions[].dimension` when it is conditionable, "
                         "and in `required_capabilities` always. There is no second "
                         "vocabulary and nothing for you to translate.",
            "ontology": O.ontology_snapshot(),
        },
        "records": [t.as_record().to_dict() for t in exposure],
    }


def upgrade_packet(packet: dict) -> dict:
    """V5A.1 packet -> V5A.2 packet. Evidence identical; surface re-keyed.

    The packet hash is recomputed because the bytes changed, and the V5A.1 hash is carried
    forward in `derived_from_v5a1_packet_hash` so the two are provably the same evidence
    behind a different surface.
    """
    out = copy.deepcopy(packet)
    exposure = build_exposure_v2(packet)

    secs = []
    for sec in out.get("sections") or []:
        if sec.get("section_type") == "AVAILABILITY_MAP":
            secs.append(_availability_section(exposure, sec.get("section")))
        else:
            secs.append(sec)
    out["sections"] = secs

    out["packet_surface_version"] = PACKET_SURFACE_VERSION
    out["ontology_version"] = O.ONTOLOGY_VERSION
    out["derived_from_v5a1_packet_hash"] = packet.get("packet_hash")
    out.pop("packet_hash", None)
    out["packet_hash"] = E.packet_hash(out)
    return out


def build_packet(index, target, *, arm: str):
    """Build a V5A.2 packet from the corpus, via the unchanged V5A.1 builder."""
    base = P1.build_packet(index, target, arm=arm)
    return None if base is None else upgrade_packet(base)
