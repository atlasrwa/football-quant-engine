"""Normalized scientific intent (`hypothesis_intent_v1`).

REPURPOSED CONTROL TARGET
-------------------------
The legacy generation measured whether the LLM produced the SAME ORDINAL STATE twice, and
whether swapping "Arsenal" for "TEAM_A" moved that state. Those were the right controls for
the wrong output.

The new invariant (mandate §20, §27):

    When the structured evidence is equivalent, replacing a real identity with a neutral
    alias must not materially change the NORMALIZED SCIENTIFIC INTENT of the questions --
    while a genuine change to football evidence SHOULD change it.

Prose is explicitly not the unit of comparison. Two questions worded completely differently
("Does A win more corners against back-three sides?" / "Is A's corner generation elevated
versus opponents lining up with three at the back?") have IDENTICAL intent and must compare
as identical. So intent is the compilable core of the hypothesis:

    (research_family, subject, side, window, metric, sorted conditions, comparison)

The free-text `question`, the evidence-ref list, the confounder list and the priority are
deliberately EXCLUDED: they are commentary, scheduling or provenance, not the measurement
being requested.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from . import lifecycle, vocabulary

INTENT_VERSION = "hypothesis_intent_v1"


@dataclass(frozen=True)
class Intent:
    """One atomic measurement request: what would actually be computed."""

    research_family: str
    subject: str
    metric: str
    side: str
    window: str
    period: str
    conditions: tuple[tuple[str, str, Optional[str]], ...]
    comparison: str

    def to_tuple(self):
        return (self.research_family, self.subject, self.metric, self.side,
                self.window, self.period, self.conditions, self.comparison)

    def to_dict(self) -> dict:
        return {
            "research_family": self.research_family,
            "subject": self.subject,
            "metric": self.metric,
            "side": self.side,
            "window": self.window,
            "period": self.period,
            "conditions": [{"dimension": d, "value": v, **({"axis": a} if a else {})}
                           for d, v, a in self.conditions],
            "comparison": self.comparison,
        }

    def key(self) -> str:
        return lifecycle.stable_hash(self.to_dict())


def normalize_hypothesis(h: dict) -> list[Intent]:
    """Expand one hypothesis into its atomic intents -- one per target metric.

    Expanding by metric is what makes the comparison fair: a model that asks about three
    metrics in one hypothesis and another that asks about them in three hypotheses have
    proposed the same science, and should score as such.
    """
    subject = vocabulary.canonical_subject(h.get("subject", "")) or h.get("subject", "")

    conds: list[tuple[str, str, Optional[str]]] = []
    period = "ALL"
    for c in h.get("conditions", []) or []:
        dim, val, axis = c.get("dimension"), c.get("value"), c.get("axis")
        if dim == "period":
            period = val or "ALL"
            continue                      # period is promoted to its own intent field
        # A condition pinned to "ANY" places no restriction, so it carries no intent and
        # is dropped. Otherwise two semantically identical plans -- one that spells out
        # "venue=ANY" and one that omits venue -- would compare as different.
        if val == "ANY":
            continue
        conds.append((dim, val, axis))

    conds.sort()

    out: list[Intent] = []
    for metric in h.get("target_metrics") or []:
        out.append(Intent(
            research_family=h.get("research_family", ""),
            subject=subject,
            metric=metric,
            side=h.get("side", ""),
            window=h.get("window", ""),
            period=period,
            conditions=tuple(conds),
            comparison=h.get("comparison", ""),
        ))
    return out


def normalize_set(payload: dict) -> list[Intent]:
    """All atomic intents in a hypothesis set, de-duplicated and ordered deterministically.

    Abstentions (INSUFFICIENT_EVIDENCE) carry no measurement request, so they contribute
    no intent -- but they are counted separately by `intent_profile` because abstention
    quality is itself a scored dimension.
    """
    seen: dict[str, Intent] = {}
    for h in payload.get("hypotheses", []) or []:
        if h.get("sufficiency") == vocabulary.SUFFICIENCY[1]:
            continue
        for intent in normalize_hypothesis(h):
            seen.setdefault(intent.key(), intent)
    return [seen[k] for k in sorted(seen)]


def intent_key_set(payload: dict) -> set[str]:
    return {i.key() for i in normalize_set(payload)}


# --------------------------------------------------------------------------------------
# Comparison
# --------------------------------------------------------------------------------------
@dataclass
class IntentComparison:
    n_a: int
    n_b: int
    n_shared: int
    jaccard: float
    only_a: tuple[dict, ...]
    only_b: tuple[dict, ...]

    @property
    def equivalent(self) -> bool:
        return self.n_shared == self.n_a == self.n_b

    def to_dict(self) -> dict:
        return {
            "intent_version": INTENT_VERSION,
            "n_a": self.n_a, "n_b": self.n_b, "n_shared": self.n_shared,
            "jaccard": round(self.jaccard, 4),
            "equivalent": self.equivalent,
            "only_a": list(self.only_a), "only_b": list(self.only_b),
        }


def compare(payload_a: dict, payload_b: dict) -> IntentComparison:
    """Compare two responses by scientific intent, ignoring wording entirely."""
    a = {i.key(): i for i in normalize_set(payload_a)}
    b = {i.key(): i for i in normalize_set(payload_b)}
    shared = set(a) & set(b)
    union = set(a) | set(b)
    return IntentComparison(
        n_a=len(a), n_b=len(b), n_shared=len(shared),
        jaccard=(len(shared) / len(union)) if union else 1.0,
        only_a=tuple(a[k].to_dict() for k in sorted(set(a) - shared)),
        only_b=tuple(b[k].to_dict() for k in sorted(set(b) - shared)),
    )


# --------------------------------------------------------------------------------------
# Profiles used by the evaluation battery
# --------------------------------------------------------------------------------------
def intent_profile(payload: dict) -> dict:
    """Structural summary of a response: what it asked about, and how varied it was.

    `metric_richness` and `distinct_intents` together answer mandate §25 G/H -- diversity
    and rich-corpus use -- without rewarding raw quantity: both are counts of DISTINCT
    things, so restating one idea five times raises neither.
    """
    intents = normalize_set(payload)
    hyps = payload.get("hypotheses", []) or []
    abstentions = [h for h in hyps
                   if h.get("sufficiency") == vocabulary.SUFFICIENCY[1]]

    metrics = {i.metric for i in intents}
    families = {i.research_family for i in intents}
    dims = {d for i in intents for d, _, _ in i.conditions}
    subjects = {i.subject for i in intents}

    return {
        "intent_version": INTENT_VERSION,
        "n_hypotheses": len(hyps),
        "n_abstentions": len(abstentions),
        "n_distinct_intents": len(intents),
        "distinct_metrics": sorted(metrics),
        "metric_richness": len(metrics),
        "distinct_families": sorted(families),
        "family_richness": len(families),
        "distinct_condition_dimensions": sorted(dims),
        "dimension_richness": len(dims),
        "subjects_covered": sorted(subjects),
        # Redundancy: how much the response repeats itself. 0.0 means every hypothesis
        # contributed a distinct measurement; high values mean restatement.
        "redundancy_rate": round(
            1.0 - (len(intents) / sum(max(1, len(h.get("target_metrics") or []))
                                      for h in hyps if h not in abstentions)), 4)
        if (len(hyps) - len(abstentions)) else 0.0,
    }


def conditions_mentioning(payload: dict, dimension: str) -> list[Intent]:
    """Intents conditioned on a given dimension -- used by the evidence-perturbation and
    evidence-removal controls (e.g. do formation-conditioned questions disappear when
    formation evidence is removed?)."""
    return [i for i in normalize_set(payload)
            if any(d == dimension for d, _, _ in i.conditions)]


def metrics_used(payload: dict) -> set[str]:
    return {i.metric for i in normalize_set(payload)}
