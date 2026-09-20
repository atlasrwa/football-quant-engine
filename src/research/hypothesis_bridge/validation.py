"""Validation: provider, PIT and support. Fail closed, and name the actual cause."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.research.matchup.corpus import MatchRecord
from src.research.llm_matchup import cohorts as CH
from src.research.hypothesis_bridge import registry, status as ST
from src.research.hypothesis_bridge.canonical import CanonicalHypothesis
from src.research.hypothesis_bridge.measurement import MIN_SUPPORT, cohort_sample
from src.research.hypothesis_bridge.versions import VALIDATOR_VERSION


@dataclass
class ValidationResult:
    status: str
    rejection_reason: Optional[str] = None
    raw_n: Optional[int] = None
    effective_n: Optional[int] = None
    coverage: Optional[float] = None
    detail: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status == ST.VALID_MEASURABLE


def validate_provider(ir: CanonicalHypothesis, provider: str) -> Optional[ValidationResult]:
    """Capability is looked up on `(provider, metric)`, never on the metric alone.

    `provider` is the one the context's frozen policy resolved to. A metric this provider
    cannot observe is UNSUPPORTED_METRIC even when the OTHER provider can observe it: there
    is no cross-provider fallback, because substituting a different provider's number would
    silently change what was measured.
    """
    cap = registry.capability_for(provider, ir.metric)     # raises on an unknown provider
    if cap is None:
        return ValidationResult(
            ST.UNSUPPORTED_METRIC,
            f"no capability for (provider={provider}, metric={ir.metric}); this registry is "
            f"provider-scoped and does not fall back to another provider")
    if not cap.is_measurable:
        # A traced capability that a semantics audit excluded. Named as a PROVIDER semantics
        # failure, not a missing metric: the field exists and the provider's values for it
        # do not mean what the metric name says.
        return ValidationResult(
            ST.UNSUPPORTED_PROVIDER_SEMANTICS,
            f"({provider},{ir.metric}) is {cap.status}: {cap.exclusion_reason} "
            f"[{cap.exclusion_evidence}]")
    if ir.period not in cap.period_support:
        return ValidationResult(
            ST.UNSUPPORTED_PROVIDER_SEMANTICS,
            f"({provider},{ir.metric}) has no {ir.period} mapping, so period={ir.period} is "
            f"not measurable")
    return None


def validate_pit(idx: CH.HistoryIndex, target: MatchRecord,
                 ir: CanonicalHypothesis) -> Optional[ValidationResult]:
    """Re-check the temporal boundary on the rows actually selected.

    `prior_records` already filters strictly, so this is defence in depth: it verifies the
    rows this measurement will consume rather than trusting the selector, and it is the only
    check that would catch a future selector change.
    """
    cohort = cohort_sample(idx, target, ir)
    violations = [r.fixture_id for r in cohort.records if r.kickoff_unix >= target.kickoff_unix]
    if violations:
        return ValidationResult(
            ST.PIT_VIOLATION,
            f"rows at or after the target kickoff entered the cohort: {sorted(violations)[:5]}")
    if any(r.fixture_id == target.fixture_id for r in cohort.records):
        return ValidationResult(ST.PIT_VIOLATION, "the target fixture entered its own cohort")
    return None


def validate_support(idx: CH.HistoryIndex, target: MatchRecord,
                     ir: CanonicalHypothesis) -> ValidationResult:
    cohort = cohort_sample(idx, target, ir)
    common = dict(raw_n=cohort.raw_n, effective_n=cohort.effective_n, coverage=cohort.coverage)
    if cohort.raw_n == 0:
        return ValidationResult(
            ST.INSUFFICIENT_SUPPORT,
            "no prior matches in the target fixture's own season-instance", **common)
    if cohort.effective_n == 0:
        return ValidationResult(
            ST.MISSING_DATA,
            f"{ir.metric} is NULL in every cohort match (not recorded, not zero)", **common)
    if cohort.effective_n < MIN_SUPPORT:
        return ValidationResult(
            ST.INSUFFICIENT_SUPPORT,
            f"effective_n={cohort.effective_n} below the frozen floor {MIN_SUPPORT}", **common)
    return ValidationResult(ST.VALID_MEASURABLE, None, **common)


def validate(idx: CH.HistoryIndex, target: MatchRecord, ir: CanonicalHypothesis,
             *, provider: str) -> ValidationResult:
    """Ordered: provider -> PIT -> support. First failure wins and names itself.

    `provider` is mandatory and keyword-only: validation cannot be performed without knowing
    which provider's capability is being claimed.
    """
    check = validate_provider(ir, provider)
    if check is not None:
        return check
    pit = validate_pit(idx, target, ir)
    if pit is not None:
        return pit
    result = validate_support(idx, target, ir)
    cap = registry.capability_for(provider, ir.metric)
    result.detail["validator_version"] = VALIDATOR_VERSION
    result.detail["capability_hash"] = registry.registry_hash()
    result.detail["provider"] = provider
    result.detail["provider_capability_id"] = cap.capability_id if cap else None
    result.detail["provider_source_field"] = cap.provider_source_field if cap else None
    return result
