"""Canonicalization: proposal -> deterministic canonical hypothesis (IR).

Free prose never controls measurement. The IR is a closed vocabulary; anything that does not
map into it exactly is REJECTED. There is no fuzzy fallback and no default that silently
changes what is measured -- an unmappable proposal is an answerable outcome, not a guess.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict

from src.research.hypothesis_bridge import proposal as P
from src.research.hypothesis_bridge.versions import CANONICAL_IR_VERSION


class CanonicalizationRefused(ValueError):
    """The proposal does not map unambiguously onto the canonical vocabulary."""


@dataclass(frozen=True)
class CanonicalHypothesis:
    ir_version: str
    fixture_id: str
    subject: str
    metric: str
    perspective: str
    comparator: str
    venue: str          # home | away | any
    period: str         # all | first_half | second_half
    window_mode: str    # all | last_n
    window_n: int       # 0 when window_mode == "all"

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def canonical_hypothesis_id(self) -> str:
        raw = json.dumps(self.to_dict(), sort_keys=True)
        return f"hyp_{hashlib.sha256(raw.encode()).hexdigest()[:24]}"


def canonicalize(prop: P.HypothesisProposal) -> CanonicalHypothesis:
    """Deterministic: the same structured proposal always yields the same hypothesis id."""
    problems = []
    if prop.subject not in P.SUBJECTS:
        problems.append(f"subject:{prop.subject}")
    if prop.perspective not in P.PERSPECTIVES:
        problems.append(f"perspective:{prop.perspective}")
    if prop.comparator not in P.COMPARATORS:
        problems.append(f"comparator:{prop.comparator}")

    unknown_conditions = sorted(set(prop.conditions) - {"venue", "period"})
    if unknown_conditions:
        problems.append("conditions:" + ",".join(unknown_conditions))

    venue = prop.conditions.get("venue", "any")
    if venue not in P.VENUES:
        problems.append(f"venue:{venue}")
    period = prop.conditions.get("period", "all")
    if period not in P.PERIODS:
        problems.append(f"period:{period}")

    mode = prop.window.get("mode", "all")
    if mode not in P.WINDOW_MODES:
        problems.append(f"window_mode:{mode}")
    n = prop.window.get("n", 0)
    if mode == "last_n":
        if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
            problems.append(f"window_n:{n!r}")
    else:
        n = 0

    # A similar-opponent intent is accepted as research intent but is NOT yet a supported
    # measurement axis. Refusing is the honest outcome; silently dropping it would measure
    # something other than what was proposed.
    if prop.similar_opponent_intent:
        problems.append("similar_opponent_intent:unsupported_measurement_axis")

    if problems:
        raise CanonicalizationRefused("; ".join(problems))

    return CanonicalHypothesis(
        ir_version=CANONICAL_IR_VERSION, fixture_id=prop.fixture_id, subject=prop.subject,
        metric=prop.target_metric, perspective=prop.perspective, comparator=prop.comparator,
        venue=venue, period=period, window_mode=mode, window_n=int(n),
    )
