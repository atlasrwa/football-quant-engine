"""Typed deterministic query plans and the compiler (`query_plan_v1`).

    The LLM proposes what to measure. The deterministic engine measures it.

The LLM never writes SQL, never names a table, never supplies a filter expression and
never sets a time cutoff. It names a metric, a side, a window, a comparison and zero or
more (dimension, value) conditions -- all drawn from closed enums. This module turns that
into a `QueryPlan`, which is the ONLY object the measurement layer will execute.

COMPILER CHECKS (mandate §17), each producing a distinct named failure:

    metric supported                  -> UNSUPPORTED_METRIC
    condition dimension supported     -> UNSUPPORTED_DIMENSION
    condition value in dimension enum -> UNSUPPORTED_DIMENSION
    context source supported          -> UNSUPPORTED_CONTEXT_SOURCE
    provider granularity available    -> UNSUPPORTED_GRANULARITY
    provider semantics not conflated  -> PROVIDER_SEMANTICS_CONFLICT
    evidence references valid         -> INSUFFICIENT_EVIDENCE   (in validator.py)
    no future information             -> LEAKAGE_REJECTED
    no closing line / settlement      -> LEAKAGE_REJECTED        (in leakage.py)
    no target leakage                 -> LEAKAGE_REJECTED
    no unsupported fine-grained state -> UNSUPPORTED_CONTEXT_SOURCE

The cutoff is INJECTED by the compiler from the fixture record. There is deliberately no
path by which a hypothesis can widen, move or omit it.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from . import capability, lifecycle, vocabulary

QUERY_PLAN_VERSION = "query_plan_v1"


@dataclass(frozen=True)
class Condition:
    dimension: str
    value: str
    axis: Optional[str] = None       # only for opponent_profile

    def to_dict(self) -> dict:
        d = {"dimension": self.dimension, "value": self.value}
        if self.axis:
            d["axis"] = self.axis
        return d


@dataclass(frozen=True)
class QueryPlan:
    """A fully-resolved, executable measurement request. Immutable by construction."""

    plan_version: str
    hypothesis_id: str
    fixture_id: str
    subject: str                     # HOME_TEAM | AWAY_TEAM
    metric: str
    side: str                        # FOR | AGAINST
    window: str
    period: str                      # ALL | FIRST_HALF | SECOND_HALF
    conditions: tuple[Condition, ...]
    comparison: str
    provider: str                    # pinned; never merged across providers
    cutoff_unix: int                 # injected by the compiler, never by the LLM
    required_granularity: str

    def to_dict(self) -> dict:
        return {
            "plan_version": self.plan_version,
            "hypothesis_id": self.hypothesis_id,
            "fixture_id": self.fixture_id,
            "subject": self.subject,
            "metric": self.metric,
            "side": self.side,
            "window": self.window,
            "period": self.period,
            "conditions": [c.to_dict() for c in self.conditions],
            "comparison": self.comparison,
            "provider": self.provider,
            "cutoff_unix": self.cutoff_unix,
            "required_granularity": self.required_granularity,
        }

    def plan_hash(self) -> str:
        return lifecycle.stable_hash(self.to_dict())


@dataclass
class CompileResult:
    ok: bool
    plan: Optional[QueryPlan] = None
    failure: Optional[str] = None          # a lifecycle failure state
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "plan": self.plan.to_dict() if self.plan else None,
            "failure": self.failure,
            "reasons": list(self.reasons),
        }


def _fail(failure: str, *reasons: str) -> CompileResult:
    return CompileResult(ok=False, failure=failure, reasons=list(reasons))


def _pin_provider(metric_name: str, manifest_providers: Optional[dict]) -> tuple[str | None, str | None]:
    """Choose exactly ONE provider for the metric, and say why.

    Never returns a merged/averaged source. When both providers supply the concept and the
    agreement study licenses it (MERGEABLE), we still pin one -- consistency within a
    feature matters more than which one, and PROVIDER_SEMANTICS.md's rule is
    "no feature mixes a FootyStats stat with a TheStatsAPI stat of the same concept".
    """
    spec = capability.metric(metric_name)
    if spec is None:
        return None, "metric not in inventory"
    preferred = None
    if manifest_providers:
        preferred = manifest_providers.get(metric_name)
    if preferred:
        if preferred not in spec.providers:
            return None, (f"manifest pins provider {preferred!r} for {metric_name!r}, but "
                          f"the inventory says only {list(spec.providers)} supply it")
        return preferred, None
    # Deterministic default: TheStatsAPI where it supplies the concept (it is the rich
    # corpus the cohort engine reads); otherwise the sole provider.
    if capability.THESTATSAPI in spec.providers:
        return capability.THESTATSAPI, None
    return spec.providers[0], None


def compile_hypothesis(
    hypothesis: dict,
    *,
    fixture_id: str,
    cutoff_unix: int,
    manifest: Optional[capability.FixtureCapabilityManifest] = None,
    manifest_providers: Optional[dict] = None,
) -> list[CompileResult]:
    """Compile one validated hypothesis into one QueryPlan per target metric.

    A hypothesis names several target metrics because one football question ("does A's
    wide pressure rise against back-three opponents?") is answered by several measurements.
    Each becomes its own plan so each carries its own coverage and sample size.
    """
    results: list[CompileResult] = []

    subject = vocabulary.canonical_subject(hypothesis.get("subject", ""))
    if subject is None:
        return [_fail(lifecycle.QUERY_INVALID,
                      f"subject {hypothesis.get('subject')!r} is not a known subject")]

    side = hypothesis.get("side")
    if side not in vocabulary.SIDES:
        return [_fail(lifecycle.QUERY_INVALID, f"side {side!r} not in {vocabulary.SIDES}")]

    window = hypothesis.get("window")
    if window not in vocabulary.WINDOWS:
        return [_fail(lifecycle.QUERY_INVALID,
                      f"window {window!r} not in {vocabulary.WINDOWS}")]

    comparison = hypothesis.get("comparison")
    if comparison not in vocabulary.COMPARISONS:
        return [_fail(lifecycle.QUERY_INVALID,
                      f"comparison {comparison!r} not in {vocabulary.COMPARISONS}")]

    # ---- conditions ------------------------------------------------------------------
    conditions: list[Condition] = []
    period = "ALL"
    for raw in hypothesis.get("conditions", []) or []:
        dim = raw.get("dimension")
        val = raw.get("value")
        axis = raw.get("axis")

        spec = vocabulary.dimension(dim)
        if spec is None:
            return [_fail(lifecycle.UNSUPPORTED_DIMENSION,
                          f"dimension {dim!r} is not a supported cohort dimension; "
                          f"supported: {vocabulary.dimension_names()}")]

        if val not in spec["values"]:
            return [_fail(lifecycle.UNSUPPORTED_DIMENSION,
                          f"value {val!r} is not legal for dimension {dim!r}; "
                          f"legal: {list(spec['values'])}")]

        src_name = spec["context_source"]
        if not capability.is_supported_context_source(src_name):
            src = capability.context_source(src_name)
            return [_fail(lifecycle.UNSUPPORTED_CONTEXT_SOURCE,
                          f"dimension {dim!r} needs context source {src_name!r}, which is "
                          f"{src.status if src else 'UNKNOWN'}: "
                          f"{src.note if src else 'no such source'}")]

        if manifest is not None and not manifest.allows_dimension(dim):
            return [_fail(lifecycle.UNSUPPORTED_CONTEXT_SOURCE,
                          f"dimension {dim!r} is not available for fixture {fixture_id}; "
                          f"available: {list(manifest.available_dimensions)}")]

        if dim == "opponent_profile":
            if axis is None:
                return [_fail(lifecycle.QUERY_INVALID,
                              "opponent_profile requires an `axis` naming the measured "
                              "dimension the band applies to")]
            if axis not in vocabulary.PROFILE_AXES:
                return [_fail(lifecycle.UNSUPPORTED_DIMENSION,
                              f"profile axis {axis!r} not in {list(vocabulary.PROFILE_AXES)}")]
        elif axis is not None:
            return [_fail(lifecycle.QUERY_INVALID,
                          f"`axis` is only meaningful for opponent_profile, not {dim!r}")]

        if dim == "period":
            period = val
        conditions.append(Condition(dim, val, axis))

    required_granularity = (capability.GRAN_HALF if period in ("FIRST_HALF", "SECOND_HALF")
                            else capability.GRAN_FULL_MATCH)

    # ---- one plan per target metric ---------------------------------------------------
    metrics = hypothesis.get("target_metrics") or []
    if not metrics:
        return [_fail(lifecycle.QUERY_INVALID, "no target_metrics supplied")]

    for metric_name in metrics:
        spec = capability.metric(metric_name)
        if spec is None:
            results.append(_fail(
                lifecycle.UNSUPPORTED_METRIC,
                f"metric {metric_name!r} is not in the capability inventory; it is not "
                f"measurable from either corpus. Supported: {capability.metric_names()}"))
            continue

        if manifest is not None and not manifest.allows_metric(metric_name):
            results.append(_fail(
                lifecycle.UNSUPPORTED_METRIC,
                f"metric {metric_name!r} is not available for fixture {fixture_id}"))
            continue

        if not spec.supports(required_granularity):
            results.append(_fail(
                lifecycle.UNSUPPORTED_GRANULARITY,
                f"metric {metric_name!r} has granularity {spec.granularity}, which cannot "
                f"answer a {period} question. {spec.caveat or ''}".strip()))
            continue

        provider, why = _pin_provider(metric_name, manifest_providers)
        if provider is None:
            results.append(_fail(lifecycle.PROVIDER_SEMANTICS_CONFLICT,
                                 why or f"cannot pin a provider for {metric_name!r}"))
            continue

        results.append(CompileResult(ok=True, plan=QueryPlan(
            plan_version=QUERY_PLAN_VERSION,
            hypothesis_id=hypothesis["hypothesis_id"],
            fixture_id=fixture_id,
            subject=subject,
            metric=metric_name,
            side=side,
            window=window,
            period=period,
            conditions=tuple(conditions),
            comparison=comparison,
            provider=provider,
            cutoff_unix=int(cutoff_unix),     # injected, never LLM-supplied
            required_granularity=required_granularity,
        )))

    return results


def compile_set(
    hypothesis_set: dict,
    *,
    cutoff_unix: int,
    manifest: Optional[capability.FixtureCapabilityManifest] = None,
    manifest_providers: Optional[dict] = None,
) -> dict:
    """Compile a whole validated hypothesis set. Returns a per-hypothesis report.

    Compilation is per-hypothesis, NOT all-or-nothing: one uncompilable hypothesis does
    not discard the rest, because each is an independent research proposal. (Contrast the
    firewall and schema gates, which reject the whole response -- a model that emitted a
    probability anywhere is not trusted anywhere.)
    """
    fixture_id = hypothesis_set.get("fixture_id", "")
    out: dict[str, list[dict]] = {}
    compilable = 0
    total = 0
    for h in hypothesis_set.get("hypotheses", []) or []:
        res = compile_hypothesis(
            h, fixture_id=fixture_id, cutoff_unix=cutoff_unix,
            manifest=manifest, manifest_providers=manifest_providers)
        out[h.get("hypothesis_id", f"<anon{total}>")] = [r.to_dict() for r in res]
        total += 1
        if res and all(r.ok for r in res):
            compilable += 1
    return {
        "plan_version": QUERY_PLAN_VERSION,
        "fixture_id": fixture_id,
        "n_hypotheses": total,
        "n_fully_compilable": compilable,
        "compile_rate": (compilable / total) if total else 0.0,
        "results": out,
    }
