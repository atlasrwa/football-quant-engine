"""V8A frozen capability adapter (`v8a_frozencap_v1`).

V7.1's capability VERDICTS are already frozen in `V7_1_CAPABILITY_MATRIX.json`. That artifact
is the generator-facing envelope -- it carries the final per-metric status and admissible
competition set, not the raw per-competition coverage counts `CapabilityContract` expects as
input. Re-deriving coverage here would risk the two experiments disagreeing about what the
corpus supports, so V8A READS THE FROZEN VERDICTS instead and adds nothing to them.

The artifact is outcome-blind by construction: V7.1 states it carries no out-of-sample
outcome, no effect estimate and no ranking. This adapter copies only status, admissibility,
semantics, unit, perspectives and temporal resolution.

ZERO SPEND. Read-only; the V7.1 artifact is never written.
"""
from __future__ import annotations

import json

FROZENCAP_VERSION = "v8a_frozencap_v1"

SUPPORTED = "SUPPORTED"
RESTRICTED = "RESTRICTED"
INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"
UNSUPPORTED = "UNSUPPORTED"
UNKNOWN = "UNKNOWN"


class FrozenCapability:
    """Exactly the reads V8A needs, served from V7.1's frozen capability matrix."""

    def __init__(self, matrix: dict):
        self.matrix = matrix
        self._metrics = matrix.get("metrics", {})
        self.competitions = tuple(sorted(matrix.get("competitions") or []))
        self.policy = matrix.get("policy") or {}
        self.filter_dimensions_supported = matrix.get("filter_dimensions_supported") or {}

    @classmethod
    def load(cls, path: str):
        return cls(json.load(open(path)))

    def metrics(self):
        return tuple(sorted(self._metrics))

    def row(self, metric: str):
        return self._metrics.get(metric)

    def admissible_competitions(self, metric: str) -> frozenset:
        row = self._metrics.get(metric)
        return frozenset(row.get("admissible_competitions") or []) if row else frozenset()

    def classify_metric(self, metric: str):
        """-> (status, detail). Copied verbatim from the frozen verdict; never recomputed."""
        row = self._metrics.get(metric)
        if row is None:
            return (UNKNOWN, "no capability row in the frozen V7.1 contract: unknown is a "
                             "NAMED gap and is not the same as unsupported")
        return (row.get("status") or UNKNOWN, row.get("detail") or "")

    def resolution_of(self, metric: str):
        row = self._metrics.get(metric)
        return (row or {}).get("temporal_resolution")

    def semantic_of(self, metric: str):
        row = self._metrics.get(metric)
        return (row or {}).get("semantic")

    def unit_of(self, metric: str):
        row = self._metrics.get(metric)
        return (row or {}).get("unit")

    def measurable_vocabulary(self) -> tuple:
        """The metric set BOTH arms and the generic library share (brief parity rule).

        A metric is in the shared vocabulary iff the frozen contract marks it SUPPORTED or
        RESTRICTED. UNSUPPORTED (`cards`: ambiguous; `np_xg`: unaudited per-side split) and
        UNKNOWN are excluded from every arm alike, so no arm is offered a term another arm
        cannot use.
        """
        return tuple(sorted(m for m, r in self._metrics.items()
                            if r.get("status") in (SUPPORTED, RESTRICTED)))

    def version_stamp(self) -> dict:
        return {"frozencap_version": FROZENCAP_VERSION,
                "source": "research/hypothesis_oos/out/v7_1/V7_1_CAPABILITY_MATRIX.json",
                "capability_version": self.matrix.get("capability_version"),
                "contains_outcomes": self.matrix.get("contains_outcomes"),
                "contains_effect_estimates": self.matrix.get("contains_effect_estimates"),
                "n_metrics": len(self._metrics),
                "n_measurable_vocabulary": len(self.measurable_vocabulary()),
                "recomputes_any_verdict": False}
