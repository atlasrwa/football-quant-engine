"""Deterministic model-language -> engine-language translation (`v5a2_translate_v1`).

Applied STRICTLY AFTER schema acceptance, and never before. That ordering is the whole
point: the model is judged against the one language it was given, and only then is its
accepted response rewritten into the two frozen internal namespaces the compiler needs.

    conditions[].dimension    ontology term  ->  vocabulary.DIMENSIONS key
    required_capabilities     ontology term  ->  capability.CONTEXT_SOURCES member

Nothing else is touched. Values, axes, metrics, windows, comparisons and subjects already
share one spelling across both languages, and the round-trip audit proves it rather than
assuming it.

TWO PROPERTIES THIS MODULE GUARANTEES
-------------------------------------
1. TOTALITY on accepted input. Every term that can reach here has passed `schema_v3`, so
   it is in the ontology, so it has a declared mapping. A `KeyError` is therefore a bug in
   the ontology, not bad model output, and is raised rather than swallowed.

2. HONEST DROPPING. Four terms (`match_level_observations`, `recent_window_summaries`,
   `xg`, `market_prices`) name real evidence the engine has no `context_source` concept
   for. They translate to NOTHING and the drop is recorded in the report. The alternative
   -- mapping them onto some plausible-looking source like `competition` -- would hand the
   compiler a claim the model never made. `required_capabilities` has `minItems: 0`, so an
   emptied list is legal, and a hypothesis is never rejected for having declared its
   dependence on evidence honestly.

ZERO SPEND.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.research.hypothesis_oos import v5a2_ontology as O

TRANSLATION_VERSION = "v5a2_translate_v1"


class UntranslatableTerm(KeyError):
    """An ontology term with no declared mapping reached translation. A build defect."""


@dataclass
class TranslationReport:
    translation_version: str = TRANSLATION_VERSION
    n_dimensions_translated: int = 0
    n_capabilities_translated: int = 0
    #: term -> count. Terms with no engine context-source concept, dropped deliberately.
    dropped_capabilities: dict = field(default_factory=dict)
    #: term -> count, collapsed because two terms share one internal source
    #: (e.g. own/opponent formation family both -> historical_formation).
    collapsed_capabilities: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {"translation_version": self.translation_version,
                "n_dimensions_translated": self.n_dimensions_translated,
                "n_capabilities_translated": self.n_capabilities_translated,
                "dropped_capabilities": dict(sorted(self.dropped_capabilities.items())),
                "collapsed_capabilities": dict(sorted(self.collapsed_capabilities.items()))}


def translate_hypothesis(h: dict, report: TranslationReport) -> dict:
    """One hypothesis, model language -> engine language. Pure; `h` is not mutated."""
    out = dict(h)

    conds = h.get("conditions")
    if isinstance(conds, list):
        new_conds = []
        for c in conds:
            if not isinstance(c, dict):
                new_conds.append(c)
                continue
            term = c.get("dimension")
            internal = O.to_internal_dimension(term) if isinstance(term, str) else None
            if internal is None:
                raise UntranslatableTerm(
                    f"condition dimension {term!r} passed schema_v3 but declares no "
                    f"internal_dimension; the ontology is inconsistent with the schema "
                    f"it generated")
            nc = dict(c)
            nc["dimension"] = internal
            report.n_dimensions_translated += 1
            new_conds.append(nc)
        out["conditions"] = new_conds

    caps = h.get("required_capabilities")
    if isinstance(caps, list):
        seen: list = []
        for term in caps:
            if not isinstance(term, str) or O.term(term) is None:
                raise UntranslatableTerm(
                    f"required capability {term!r} passed schema_v3 but is not an "
                    f"ontology term")
            internal = O.to_internal_context_source(term)
            if internal is None:
                report.dropped_capabilities[term] = \
                    report.dropped_capabilities.get(term, 0) + 1
                continue
            if internal in seen:
                report.collapsed_capabilities[term] = \
                    report.collapsed_capabilities.get(term, 0) + 1
                continue
            seen.append(internal)
            report.n_capabilities_translated += 1
        out["required_capabilities"] = seen

    return out


def translate_payload(payload: dict) -> tuple:
    """Return (engine-language copy, TranslationReport). `payload` is not mutated."""
    report = TranslationReport()
    if not isinstance(payload, dict):
        return payload, report
    out = dict(payload)
    hyps = payload.get("hypotheses")
    if not isinstance(hyps, list):
        return out, report
    out["hypotheses"] = [translate_hypothesis(h, report) if isinstance(h, dict) else h
                         for h in hyps]
    return out, report


def round_trip_dimension(term: str) -> bool:
    """A conditionable term survives term -> internal -> term unchanged.

    Asserted for every conditionable term by `test_every_condition_term_round_trips`. It
    holds only while no two terms share an `internal_dimension`; if that ever stops being
    true the test fails rather than the inverse quietly returning the wrong term.
    """
    internal = O.to_internal_dimension(term)
    return internal is not None and O.from_internal_dimension(internal) == term
