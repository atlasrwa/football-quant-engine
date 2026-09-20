"""Provider capability registry: what is measurable, from which provider, with what nulls.

Grounded in `llm_matchup.cohorts.ALL_METRICS`, which is the only place the corpus's own
field mapping is declared. Nothing here imputes a field: a metric absent from the corpus
mapping is UNSUPPORTED, never approximated from a neighbouring provider.
"""
from __future__ import annotations

import hashlib
import json

from src.research.llm_matchup import cohorts as CH
from src.research.hypothesis_bridge.versions import CAPABILITY_REGISTRY_VERSION

#: Provider each metric family actually comes from. FootyStats and TheStatsAPI are NOT
#: assumed equivalent: a metric is bound to the provider that supplies it, and a proposal
#: asking for a provider that does not supply it is refused rather than silently served.
_PROVIDER_BY_SOURCE = {"rich": "thestatsapi", "extra": "thestatsapi", None: "footystats"}

#: Metrics whose NULL means "not recorded" rather than "zero". Measurement drops them from
#: the sample rather than coercing, so a missing cell never reads as a real low value.
NULL_IS_MISSING = frozenset(CH.ALL_METRICS)


def supported_metrics() -> dict[str, str]:
    """metric -> provider, for every metric the corpus mapping actually declares."""
    out = {}
    for metric, (source, _field) in CH.ALL_METRICS.items():
        out[metric] = _PROVIDER_BY_SOURCE.get(source, "thestatsapi")
    return out


def is_supported(metric: str) -> bool:
    return metric in CH.ALL_METRICS


def provider_for(metric: str) -> str | None:
    if not is_supported(metric):
        return None
    return supported_metrics()[metric]


def supports_period(metric: str, period: str) -> bool:
    """Half-split periods exist only for the metrics with a declared half mapping."""
    if period == "all":
        return True
    return metric in CH.HALF_METRICS


def capability_hash() -> str:
    """Identity of the capability surface a record was validated against."""
    payload = {
        "registry_version": CAPABILITY_REGISTRY_VERSION,
        "metrics": supported_metrics(),
        "half_metrics": sorted(CH.HALF_METRICS),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
