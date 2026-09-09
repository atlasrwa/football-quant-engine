"""The reconciler — applies a ReconciliationPolicy to provider observations.

Input: the per-source observations for one concept (typically the output of
``ObservationStore.as_of_by_source``). Output: a ``ReconciledField`` retaining
the selected value, its source, every provider input, support/missingness, and
a measurable disagreement metric.

Hard rules (enforced and tested):
- NEVER select the numerically larger value. Selection is driven only by the
  policy and by provider preference — magnitude is irrelevant.
- NEVER coerce MISSING/None into 0.
- VALIDATED_BLEND averages ONLY when both numeric values agree within tolerance;
  on disagreement it selects nothing and flags it. No unvalidated averaging.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from src.research.observation.model import Missing, ProviderObservation
from src.research.reconciliation.policy import ReconciliationPolicy

FOOTYSTATS = "footystats"
THESTATSAPI = "thestatsapi"


class SelectionOutcome(Enum):
    """Why the reconciler produced (or did not produce) a selected value."""
    SELECTED = "SELECTED"                      # a value was chosen
    FELL_BACK = "FELL_BACK"                    # preferred missing -> used other
    BLENDED = "BLENDED"                        # validated agreement -> averaged
    NO_VALUE = "NO_VALUE"                      # nothing available to select
    DISAGREEMENT_UNRESOLVED = "DISAGREEMENT_UNRESOLVED"  # blend refused


@dataclass(frozen=True)
class ReconciledField:
    """Result of reconciling one concept across providers.

    Attributes:
        concept: The concept name reconciled.
        policy: Policy applied.
        outcome: Why this result was produced.
        value: Selected value (may be None if observed-absent; MISSING-typed
            only when nothing was selected).
        source: Source id of the selected value ("footystats"/"thestatsapi"/
            "blend"), or "" when nothing selected.
        inputs: Per-source observations considered (retained for audit).
        disagreement: Absolute numeric difference between the two providers when
            both are numeric; None otherwise. Always retained so disagreement is
            measurable regardless of policy.
        support: Support behind the selected value, if known.
    """
    concept: str
    policy: ReconciliationPolicy
    outcome: SelectionOutcome
    value: Any
    source: str
    inputs: dict[str, ProviderObservation]
    disagreement: Optional[float] = None
    support: Optional[int] = None

    @property
    def has_value(self) -> bool:
        return not isinstance(self.value, Missing)

    def to_dict(self) -> dict[str, Any]:
        return {
            "concept": self.concept,
            "policy": self.policy.value,
            "outcome": self.outcome.value,
            "value": ("MISSING" if isinstance(self.value, Missing) else self.value),
            "source": self.source,
            "disagreement": self.disagreement,
            "support": self.support,
            "inputs": {s: o.to_dict() for s, o in self.inputs.items()},
        }


def _numeric(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _disagreement(inputs: dict[str, ProviderObservation]) -> Optional[float]:
    fs = inputs.get(FOOTYSTATS)
    tsa = inputs.get(THESTATSAPI)
    if fs is None or tsa is None or not fs.has_value or not tsa.has_value:
        return None
    a = _numeric(fs.value)
    b = _numeric(tsa.value)
    if a is None or b is None:
        return None
    return abs(a - b)


class Reconciler:
    """Applies a reconciliation policy to per-source observations."""

    def __init__(
        self,
        policy: ReconciliationPolicy,
        *,
        preferred: str = FOOTYSTATS,
        blend_abs_tolerance: float = 0.0,
        blend_rel_tolerance: float = 0.0,
    ) -> None:
        """Configure the reconciler.

        Args:
            policy: The policy to apply.
            preferred: Preferred provider for PREFERRED_PROVIDER_WITH_FALLBACK.
            blend_abs_tolerance: Max absolute difference for VALIDATED_BLEND to
                consider the providers in agreement.
            blend_rel_tolerance: Max relative difference (fraction of mean) for
                VALIDATED_BLEND agreement. The looser of abs/rel is used.
        """
        self._policy = policy
        self._preferred = preferred
        self._abs_tol = blend_abs_tolerance
        self._rel_tol = blend_rel_tolerance

    def reconcile(
        self,
        concept: str,
        inputs: dict[str, ProviderObservation],
    ) -> ReconciledField:
        """Reconcile one concept given per-source observations.

        ``inputs`` maps source id -> ProviderObservation (as from
        ObservationStore.as_of_by_source). Sources absent from the dict are
        treated as having no observation.
        """
        disagreement = _disagreement(inputs)

        if self._policy == ReconciliationPolicy.FOOTYSTATS_ONLY:
            return self._single(concept, inputs, FOOTYSTATS, disagreement)
        if self._policy == ReconciliationPolicy.THESTATSAPI_ONLY:
            return self._single(concept, inputs, THESTATSAPI, disagreement)
        if self._policy == ReconciliationPolicy.PREFERRED_PROVIDER_WITH_FALLBACK:
            return self._preferred_with_fallback(concept, inputs, disagreement)
        if self._policy == ReconciliationPolicy.VALIDATED_BLEND:
            return self._validated_blend(concept, inputs, disagreement)
        raise ValueError(f"Unknown policy {self._policy}")

    def _single(self, concept, inputs, source, disagreement) -> ReconciledField:
        obs = inputs.get(source)
        if obs is None or not obs.has_value:
            return ReconciledField(
                concept=concept, policy=self._policy, outcome=SelectionOutcome.NO_VALUE,
                value=_MISSING, source="", inputs=inputs, disagreement=disagreement,
            )
        return ReconciledField(
            concept=concept, policy=self._policy, outcome=SelectionOutcome.SELECTED,
            value=obs.value, source=source, inputs=inputs,
            disagreement=disagreement, support=obs.support,
        )

    def _preferred_with_fallback(self, concept, inputs, disagreement) -> ReconciledField:
        other = THESTATSAPI if self._preferred == FOOTYSTATS else FOOTYSTATS
        pref = inputs.get(self._preferred)
        # "Preferred value present" means the provider produced an observation
        # (has_value). An observed None (observed-absent) is respected as the
        # preferred provider's answer and does NOT trigger fallback, because
        # NULL != MISSING. Fallback only when the preferred has NO observation.
        if pref is not None and pref.has_value:
            return ReconciledField(
                concept=concept, policy=self._policy, outcome=SelectionOutcome.SELECTED,
                value=pref.value, source=self._preferred, inputs=inputs,
                disagreement=disagreement, support=pref.support,
            )
        fb = inputs.get(other)
        if fb is not None and fb.has_value:
            return ReconciledField(
                concept=concept, policy=self._policy, outcome=SelectionOutcome.FELL_BACK,
                value=fb.value, source=other, inputs=inputs,
                disagreement=disagreement, support=fb.support,
            )
        return ReconciledField(
            concept=concept, policy=self._policy, outcome=SelectionOutcome.NO_VALUE,
            value=_MISSING, source="", inputs=inputs, disagreement=disagreement,
        )

    def _validated_blend(self, concept, inputs, disagreement) -> ReconciledField:
        fs = inputs.get(FOOTYSTATS)
        tsa = inputs.get(THESTATSAPI)
        fs_val = _numeric(fs.value) if (fs and fs.has_value) else None
        tsa_val = _numeric(tsa.value) if (tsa and tsa.has_value) else None

        # If only one numeric value exists, there is nothing to validate against;
        # we do NOT blend. Fall back to the single present numeric value only if
        # the other provider has no observation at all (not merely non-numeric).
        if fs_val is not None and tsa_val is None and (tsa is None or not tsa.has_value):
            return ReconciledField(
                concept=concept, policy=self._policy, outcome=SelectionOutcome.SELECTED,
                value=fs.value, source=FOOTYSTATS, inputs=inputs,
                disagreement=disagreement, support=fs.support,
            )
        if tsa_val is not None and fs_val is None and (fs is None or not fs.has_value):
            return ReconciledField(
                concept=concept, policy=self._policy, outcome=SelectionOutcome.SELECTED,
                value=tsa.value, source=THESTATSAPI, inputs=inputs,
                disagreement=disagreement, support=tsa.support,
            )

        if fs_val is None or tsa_val is None:
            return ReconciledField(
                concept=concept, policy=self._policy, outcome=SelectionOutcome.NO_VALUE,
                value=_MISSING, source="", inputs=inputs, disagreement=disagreement,
            )

        # Both numeric: blend ONLY if within validated tolerance.
        diff = abs(fs_val - tsa_val)
        mean = (fs_val + tsa_val) / 2.0
        rel_ok = self._rel_tol > 0 and mean != 0 and (diff / abs(mean)) <= self._rel_tol
        abs_ok = diff <= self._abs_tol
        if abs_ok or rel_ok:
            blended = mean
            support = None
            if fs and tsa and fs.support is not None and tsa.support is not None:
                support = fs.support + tsa.support
            return ReconciledField(
                concept=concept, policy=self._policy, outcome=SelectionOutcome.BLENDED,
                value=blended, source="blend", inputs=inputs,
                disagreement=diff, support=support,
            )
        # Disagreement beyond tolerance: refuse to blend, flag it.
        return ReconciledField(
            concept=concept, policy=self._policy,
            outcome=SelectionOutcome.DISAGREEMENT_UNRESOLVED,
            value=_MISSING, source="", inputs=inputs, disagreement=diff,
        )


# Local import alias to avoid a hard import cycle at module top.
from src.research.observation.model import MISSING as _MISSING  # noqa: E402
