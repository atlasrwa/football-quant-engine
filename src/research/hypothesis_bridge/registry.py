"""Explicit provider capability + provenance registry.

The previous version inferred the provider from the STORAGE CONTAINER a value happens to sit
in (`rich`/`extra` -> thestatsapi, base -> footystats). That is not provenance, and it was
wrong: `yellow_cards` lives in a FootyStats-SCHEMA field (`team_a_yellow_cards`) but is read
from the TheStatsAPI `/stats` payload at `overview.yellow_cards`.

Traced through the real load path rather than guessed:

    corpus.load_corpus
      -> multisrc_corpus.load_season
        -> _to_adapter_shape(fx)            "Map a TheStatsAPI fixture -> the shape
                                             adapt_match wants"
        -> championship_adapter.adapt_match(shape, stats_json)
             stats_json = the TheStatsAPI /stats response
             returns a FootyStats-SCHEMA dict
             base  fields  <- _cell(sd, group, stat, ...)
             _rich fields  <- _rich_fields(sd)   -> MatchRecord.rich
      -> corpus._extra_pairs(sd)                  -> MatchRecord.extra

Every value this bridge can measure therefore originates from TheStatsAPI. FootyStats is the
SCHEMA the rows are shaped into, not the source of the numbers. The two are recorded
separately below so nothing has to be inferred from a field name again.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict

from src.research.llm_matchup import cohorts as CH
from src.research.hypothesis_bridge.versions import CAPABILITY_REGISTRY_VERSION

THESTATSAPI = "thestatsapi"

#: The schema the corpus rows are shaped into. Recorded so a reader cannot mistake it for
#: the provider: `adapt_match` returns a FootyStats-schema dict built from TheStatsAPI data.
CORPUS_STORAGE_SCHEMA = "footystats_schema"


@dataclass(frozen=True)
class MetricCapability:
    metric: str
    provider: str
    source_path: str        # "<group>.<stat>" in the TheStatsAPI /stats payload
    container: str          # where the loader parks it: base | rich | extra
    period_support: tuple[str, ...]
    null_semantics: str


#: group.stat verified against `championship_adapter._rich_fields`, `corpus._EXTRA_STATS`
#: and `adapt_match`'s own `ov(...)` calls.
_SOURCE_PATH = {
    "crosses": ("passes.accurate_crosses", "rich"),
    "total_shots": ("overview.total_shots", "extra"),
    "shots_on_target": ("overview.shots_on_target", "rich"),
    "shots_inside_box": ("shots.shots_inside_box", "rich"),
    "shots_outside_box": ("shots.shots_outside_box", "rich"),
    "blocked_shots": ("shots.blocked_shots", "rich"),
    "corners": ("overview.corner_kicks", "rich"),
    "possession": ("overview.ball_possession", "extra"),
    "fouls": ("overview.fouls", "rich"),
    # FootyStats-SCHEMA field name, TheStatsAPI provenance. This is the entry the previous
    # container-based inference got wrong.
    "yellow_cards": ("overview.yellow_cards", "base"),
    "tackles": ("defending.tackles", "rich"),
    "touches_in_box": ("attack.touches_in_penalty_area", "rich"),
    "final_third_entries": ("passes.final_third_entries", "rich"),
    "throw_ins": ("passes.throw_ins", "extra"),
    "clearances": ("defending.clearances", "rich"),
    "interceptions": ("defending.interceptions", "rich"),
    "big_chances": ("overview.big_chances", "rich"),
    "npxg": ("np_expected_goals.np_expected_goals", "rich"),
    "saves": ("goalkeeping.saves", "rich"),
}

#: NULL means NOT RECORDED for every metric here: `grab()` and `_extra_pairs` emit a pair only
#: when BOTH sides are non-null, and a genuine (0, 0) is preserved. Never coerce to zero.
NULL_SEMANTICS = "NULL_IS_NOT_RECORDED_NEVER_ZERO"


def _build() -> dict[str, MetricCapability]:
    table = {}
    for metric in CH.ALL_METRICS:
        path, container = _SOURCE_PATH.get(metric, (None, None))
        if path is None:
            # Fail closed: a metric the corpus maps but this registry has not had its
            # provenance traced is NOT advertised as supported.
            continue
        periods = ("all", "first_half", "second_half") if metric in CH.HALF_METRICS else ("all",)
        table[metric] = MetricCapability(
            metric=metric, provider=THESTATSAPI, source_path=path, container=container,
            period_support=periods, null_semantics=NULL_SEMANTICS)
    return table


CAPABILITIES: dict[str, MetricCapability] = _build()


def is_supported(metric: str) -> bool:
    return metric in CAPABILITIES


def provider_for(metric: str) -> str | None:
    cap = CAPABILITIES.get(metric)
    return cap.provider if cap else None


def capability_for(metric: str) -> MetricCapability | None:
    return CAPABILITIES.get(metric)


def supported_metrics() -> dict[str, str]:
    return {m: c.provider for m, c in CAPABILITIES.items()}


def supports_period(metric: str, period: str) -> bool:
    cap = CAPABILITIES.get(metric)
    return bool(cap) and period in cap.period_support


def providers_in_use() -> list[str]:
    """Distinct providers. One entry today; cross-provider equivalence is NOT assumed, so if
    a second ever appears it must be declared here rather than folded into the first."""
    return sorted({c.provider for c in CAPABILITIES.values()})


def capability_hash() -> str:
    payload = {
        "registry_version": CAPABILITY_REGISTRY_VERSION,
        "storage_schema": CORPUS_STORAGE_SCHEMA,
        "capabilities": {m: asdict(c) for m, c in sorted(CAPABILITIES.items())},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
