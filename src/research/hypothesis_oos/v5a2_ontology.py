"""The single authoritative ontology (`v5a2_ontology_v1`).

WHY THIS MODULE EXISTS
----------------------
V5A.1 died on its second research call with `SCHEMA_INVALID`, and the cause was not
football, not evidence and not the model. It was that the apparatus spoke THREE different
languages at the model simultaneously:

    packet availability map   ->  "venue_splits"     "opponent_profile_response"
    conditions[].dimension    ->  "venue"            "opponent_profile"
    required_capabilities     ->  "venue"            "competition"      (!)

`schema.py:52` types `dimension` from `vocabulary.dimension_names()` while `schema.py:102`
types `required_capabilities` from `sorted(capability.CONTEXT_SOURCES)`. Those are two
disjoint vocabularies that happen to share some spellings. A model that reads
`opponent_profile` in the packet, conditions on `opponent_profile`, and then declares it
needs `opponent_profile` is REJECTED -- because the correct capability token for
`opponent_profile` is the entirely unguessable `competition`. There is no text anywhere in
the packet or the prompt from which that mapping could be derived. Two of the first six
V5A.1 calls were lost to it and 24 hypotheses were discarded unread.

    THE MODEL MUST SPEAK EXACTLY ONE LANGUAGE.

This module defines that language. Every string the model READS in a packet and every
string the model WRITES in a response is a `term` declared here, once. The availability
map, the condition-dimension enum and the required-capabilities enum are all projections
of this one dict. They cannot drift, because none of them declares a vocabulary of its own.

Internal engine concepts still differ -- `vocabulary.DIMENSIONS` and
`capability.CONTEXT_SOURCES` are frozen (hashed into the V3 and V5A preregistrations) and
are NOT edited. They are reached by DETERMINISTIC TRANSLATION, applied by `v5a2_translate`
strictly AFTER schema acceptance. The model is never asked to perform that translation, and
never sees either internal name.

THE VENUE SPLIT (task S6)
-------------------------
V5A.1's base arm rejected 30 venue-conditioned hypotheses at `unsupported_dimension_rate =
1.0`, and that number was not interpretable: a single term `venue` carried two different
meanings at once.

    TARGET_FIXTURE_VENUE_CONTEXT   -- which side of the UPCOMING fixture is at home.
                                      A fact about the fixture. Always true, always
                                      exposed, in BOTH arms. Not conditionable.
    HISTORICAL_VENUE_CONDITIONING  -- splitting the subject's PRIOR matches by where they
                                      were played. Requires venue-split evidence, which
                                      the base arm deliberately does not carry.

A model that reads "HOME_TEAM plays at home" and concludes venue conditioning is licensed
is making a reasonable inference from an ambiguous term, not ignoring the availability map.
Splitting the term lets the base arm truthfully expose the first while withholding the
second, so the rejection that remains is a real measurement of restraint rather than an
artefact of our own naming. The rejection itself is PRESERVED, per task S6.

ZERO SPEND. This module builds strings and dicts and calls nothing.
"""
from __future__ import annotations

from typing import Optional

from src.research.hypothesis_engine import vocabulary as V

ONTOLOGY_VERSION = "v5a2_ontology_v1"

# --------------------------------------------------------------------------------------
# Roles. A term's role decides which model-visible enums it appears in.
# --------------------------------------------------------------------------------------
#: May appear as `conditions[].dimension`, AND in `required_capabilities`, AND in the
#: availability map.
ROLE_CONDITION_DIMENSION = "CONDITION_DIMENSION"
#: May appear in `required_capabilities` and in the availability map, but is NOT a cohort
#: split -- it names evidence a hypothesis leans on, or a fact about the target fixture.
ROLE_EVIDENCE_CONTEXT = "EVIDENCE_CONTEXT"

ROLES = (ROLE_CONDITION_DIMENSION, ROLE_EVIDENCE_CONTEXT)

#: Model-visible names for the two venue meanings (task S6). Exported as constants because
#: the packet builder, the admissibility gate, the evaluator and the audits all key on
#: them and none of them may re-spell either one.
TARGET_FIXTURE_VENUE_CONTEXT = "target_fixture_venue_context"
HISTORICAL_VENUE_CONDITIONING = "historical_venue_conditioning"


def _dim_values(internal_dimension: str) -> tuple:
    """Project a value set off the frozen vocabulary. Never re-typed here."""
    spec = V.dimension(internal_dimension)
    if spec is None:
        raise KeyError(f"no frozen vocabulary dimension {internal_dimension!r}")
    return tuple(spec["values"])


def _dim_axes(internal_dimension: str) -> tuple:
    spec = V.dimension(internal_dimension)
    if spec is None:
        raise KeyError(f"no frozen vocabulary dimension {internal_dimension!r}")
    return tuple(spec.get("axes") or ())


# --------------------------------------------------------------------------------------
# THE TERM SET.
#
# `internal_dimension`       -> vocabulary.DIMENSIONS key, or None if not conditionable.
# `internal_context_source`  -> capability.CONTEXT_SOURCES member, or None when the engine
#                               has no context-source concept for this term. None is
#                               HONEST: the translation drops it and records the drop,
#                               rather than inventing a source the engine would misread.
# `model_may_require`        -> False when the term may be DECLARED in the availability map
#                               but must not be a legal `required_capabilities` value. Only
#                               `market_prices` is such a term: injuries and weather are
#                               legitimate football-research concepts this corpus happens to
#                               lack, whereas odds are never legitimate input to this layer
#                               at all. Declaring it lets the packet state the absence is
#                               deliberate; keeping it out of the output enum means a model
#                               cannot name it even to ask.
# `corpus_supported`         -> False when no packet in this corpus can ever back the term.
#                               Such a term is still declared (so the model can see the
#                               absence is deliberate) but the availability map marks it
#                               unexposed and the admissibility gate refuses it.
# --------------------------------------------------------------------------------------
TERMS: dict[str, dict] = {
    # ---- conditionable cohort splits -------------------------------------------------
    HISTORICAL_VENUE_CONDITIONING: {
        "role": ROLE_CONDITION_DIMENSION,
        "internal_dimension": "venue",
        "internal_context_source": "venue",
        "corpus_supported": True,
        "values": _dim_values("venue"),
        "axes": (),
        "desc": "Split the subject's PRIOR matches by where they were played. Requires "
                "venue-split evidence in this packet. This is NOT the same as knowing "
                "which side is at home in the upcoming fixture -- that is "
                f"`{TARGET_FIXTURE_VENUE_CONTEXT}`, and it does not license this split.",
    },
    "opponent_profile": {
        "role": ROLE_CONDITION_DIMENSION,
        "internal_dimension": "opponent_profile",
        "internal_context_source": "competition",
        "corpus_supported": True,
        "values": _dim_values("opponent_profile"),
        "axes": _dim_axes("opponent_profile"),
        "desc": "Split the subject's prior matches by a band of the opponent faced, on one "
                "named measured axis. `axis` is REQUIRED for this term and forbidden for "
                "every other.",
    },
    "own_formation_family": {
        "role": ROLE_CONDITION_DIMENSION,
        "internal_dimension": "own_formation_family",
        "internal_context_source": "historical_formation",
        "corpus_supported": True,
        "values": _dim_values("own_formation_family"),
        "axes": (),
        "desc": "Structural family of the subject's RECORDED formation in each prior "
                "match. Requires a recorded formation on each observation.",
    },
    "opponent_formation_family": {
        "role": ROLE_CONDITION_DIMENSION,
        "internal_dimension": "opponent_formation_family",
        "internal_context_source": "historical_formation",
        "corpus_supported": True,
        "values": _dim_values("opponent_formation_family"),
        "axes": (),
        "desc": "Structural family of the OPPONENT's recorded formation in each prior "
                "match. Requires a recorded formation on each observation.",
    },
    "competition": {
        "role": ROLE_CONDITION_DIMENSION,
        "internal_dimension": "competition",
        "internal_context_source": "competition",
        "corpus_supported": True,
        "values": _dim_values("competition"),
        "axes": (),
        "desc": "Restrict the cohort to the upcoming fixture's competition, or any.",
    },
    "half_time_score_state": {
        "role": ROLE_CONDITION_DIMENSION,
        "internal_dimension": "half_score_state",
        "internal_context_source": "half_time_score_state",
        "corpus_supported": False,
        "values": _dim_values("half_score_state"),
        "axes": (),
        "desc": "Split by the score at half time. No half-level data exists in this "
                "corpus, so no packet can support it.",
    },
    "match_period": {
        "role": ROLE_CONDITION_DIMENSION,
        "internal_dimension": "period",
        "internal_context_source": "competition",
        "corpus_supported": False,
        "values": _dim_values("period"),
        "axes": (),
        "desc": "Restrict to a half of the match. No half-level split exists in this "
                "corpus, so no packet can support it.",
    },
    "referee": {
        "role": ROLE_CONDITION_DIMENSION,
        "internal_dimension": "referee",
        "internal_context_source": "referee",
        "corpus_supported": False,
        "values": _dim_values("referee"),
        "axes": (),
        "desc": "Split by match official. The adapter surfaces no referee field for this "
                "corpus, so no packet can support it.",
    },

    # ---- evidence context: present or deliberately absent -----------------------------
    TARGET_FIXTURE_VENUE_CONTEXT: {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": "venue",
        "corpus_supported": True,
        "values": (),
        "axes": (),
        "desc": "Which side of the UPCOMING fixture is at home. A fact about the fixture, "
                "stated in TARGET_FIXTURE_CONTEXT, always available in every packet. It "
                "does NOT let you split prior matches by venue -- see "
                f"`{HISTORICAL_VENUE_CONDITIONING}`.",
    },
    "match_level_observations": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": None,
        "corpus_supported": True,
        "values": (),
        "axes": (),
        "desc": "One row per prior match, per team, with every canonical metric. The "
                "lossless view of the history.",
    },
    "recent_window_summaries": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": None,
        "corpus_supported": True,
        "values": (),
        "axes": (),
        "desc": "Short-window summaries (W5, W10) alongside the long-run one, which is "
                "what makes a recent-versus-long-run question answerable.",
    },
    "formation_recorded_history": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": "historical_formation",
        "corpus_supported": True,
        "values": (),
        "axes": (),
        "desc": "How much of the prior history carries a recorded formation. Coverage "
                "alone tells you how reliable a formation question would be; conditioning "
                "on formation additionally requires match_level_observations.",
    },
    "xg": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": None,
        "corpus_supported": True,
        "values": (),
        "axes": (),
        "desc": "Expected goals as published by the provider. See METRIC_SEMANTICS for "
                "what it counts and what is excluded.",
    },
    "expected_formation": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": "expected_formation",
        "corpus_supported": False,
        "values": (),
        "axes": (),
        "desc": "Announced or predicted formation for the upcoming fixture. Not provided "
                "by the source.",
    },
    "lineup": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": "lineup_composition",
        "corpus_supported": False,
        "values": (),
        "axes": (),
        "desc": "Starting eleven. Provided by the source but not derivable point-in-time "
                "safe, so it is withheld.",
    },
    "injuries": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": "injuries",
        "corpus_supported": False,
        "values": (), "axes": (),
        "desc": "Availability of individual players. Not provided by the source.",
    },
    "weather": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": "weather",
        "corpus_supported": False,
        "values": (), "axes": (),
        "desc": "Match conditions. Not provided by the source.",
    },
    "minute_level_events": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": "minute_level_events",
        "corpus_supported": False,
        "values": (), "axes": (),
        "desc": "Timed events within a match. Not provided by the source.",
    },
    "player_ratings": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": "player_ratings",
        "corpus_supported": False,
        "values": (), "axes": (),
        "desc": "Per-player performance ratings. Not provided by the source.",
    },
    "market_prices": {
        "role": ROLE_EVIDENCE_CONTEXT,
        "internal_dimension": None,
        "internal_context_source": None,
        "corpus_supported": False,
        "model_may_require": False,
        "values": (), "axes": (),
        "desc": "Odds or prices of any kind. Never provided to this layer by design.",
    },
}


# --------------------------------------------------------------------------------------
# Projections. EVERY model-visible enum in the apparatus comes from one of these.
# --------------------------------------------------------------------------------------
def all_terms() -> list[str]:
    """Every model-visible term, sorted. The availability map declares exactly these."""
    return sorted(TERMS)


def term(name: str) -> Optional[dict]:
    return TERMS.get(name)


def condition_dimension_terms() -> list[str]:
    """The `conditions[].dimension` enum."""
    return sorted(t for t, s in TERMS.items()
                  if s["role"] == ROLE_CONDITION_DIMENSION)


def capability_terms() -> list[str]:
    """The `required_capabilities` enum.

    Deliberately near the FULL term set, not just the conditionable ones: a hypothesis may
    legitimately depend on `match_level_observations` or `xg` without conditioning on
    anything. Under V5A.1 this field spoke a private namespace and there was no term a
    model could write for either.

    The one exclusion is `market_prices`. It is DECLARED in the availability map, so the
    packet can say the absence is deliberate, but it is not a legal thing to require: a
    research-question layer that names odds as a dependency has already left its remit.
    """
    return sorted(t for t, s in TERMS.items() if s.get("model_may_require", True))


def values_for(name: str) -> tuple:
    spec = TERMS.get(name)
    return tuple(spec["values"]) if spec else ()


def axes_for(name: str) -> tuple:
    spec = TERMS.get(name)
    return tuple(spec["axes"]) if spec else ()


def all_condition_values() -> tuple:
    seen: set = set()
    for name in condition_dimension_terms():
        seen.update(values_for(name))
    return tuple(sorted(seen))


def all_condition_axes() -> tuple:
    seen: set = set()
    for name in condition_dimension_terms():
        seen.update(axes_for(name))
    return tuple(sorted(seen))


def axis_required_terms() -> tuple:
    """A term requires an axis iff it declares axes. Read off, never hardcoded."""
    return tuple(t for t in condition_dimension_terms() if axes_for(t))


def corpus_supported_terms() -> list[str]:
    return sorted(t for t, s in TERMS.items() if s["corpus_supported"])


def corpus_unsupported_terms() -> list[str]:
    return sorted(t for t, s in TERMS.items() if not s["corpus_supported"])


# --------------------------------------------------------------------------------------
# Translation to the frozen internal namespaces. Applied ONLY after schema acceptance.
# --------------------------------------------------------------------------------------
def to_internal_dimension(name: str) -> Optional[str]:
    spec = TERMS.get(name)
    return spec["internal_dimension"] if spec else None


def to_internal_context_source(name: str) -> Optional[str]:
    spec = TERMS.get(name)
    return spec["internal_context_source"] if spec else None


def from_internal_dimension(internal: str) -> Optional[str]:
    """Inverse of `to_internal_dimension`. Total and unambiguous by construction: the
    round-trip test asserts no two terms share an `internal_dimension`."""
    for name, spec in TERMS.items():
        if spec["internal_dimension"] == internal:
            return name
    return None


def internal_dimension_map() -> dict:
    return {t: TERMS[t]["internal_dimension"] for t in condition_dimension_terms()}


def internal_context_source_map() -> dict:
    return {t: TERMS[t]["internal_context_source"] for t in all_terms()}


def ontology_snapshot() -> dict:
    """Machine-readable ontology, embedded in the packet, the prompt and provenance.

    Sorted throughout: this is hashed into the preregistration and must be byte-stable
    across interpreter hash seeds.
    """
    return {
        "ontology_version": ONTOLOGY_VERSION,
        "terms": {
            name: {
                "role": TERMS[name]["role"],
                "corpus_supported": TERMS[name]["corpus_supported"],
                "values": list(values_for(name)),
                "axes": list(axes_for(name)),
                "axis_required": bool(axes_for(name)),
                "desc": TERMS[name]["desc"],
            }
            for name in all_terms()
        },
        "condition_dimension_terms": condition_dimension_terms(),
        "capability_terms": capability_terms(),
        "axis_required_terms": list(axis_required_terms()),
        "single_language_rule": (
            "Every term you read in the availability map is spelled exactly the same way "
            "in `conditions[].dimension` (when it is conditionable) and in "
            "`required_capabilities`. There is no second vocabulary and no translation "
            "for you to perform."),
    }
