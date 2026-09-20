"""Provider-SCOPED capability registry. Two real providers, never conflated.

QUANT FOOTBALL ENGINE has TWO data providers -- FootyStats and TheStatsAPI -- and this
registry is keyed on `(provider, canonical_metric)`, not on the metric alone. A metric name
is not a capability: the SAME canonical concept read from two providers is two separately
declared observations until an equivalence has actually been validated, and this module never
validates one implicitly.

WHY THE KEY HAS TO BE A PAIR
============================
`yellow_cards` is the proof. FootyStats genuinely exposes `team_a_yellow_cards`
(`footystats/normalizer.py:184`). TheStatsAPI exposes `overview.yellow_cards`, which
`scripts/championship_adapter.py` then PARKS in a field it also calls `team_a_yellow_cards`.
Identical storage-field spelling, two different providers, two different payloads. A registry
keyed on the metric alone cannot tell those apart, and a registry that reads the provider off
the field name gets it backwards.

    STORAGE SCHEMA != PROVIDER.

THE CORPUS THIS BRIDGE MEASURES
===============================
Traced through the real load path rather than guessed:

    corpus.load_corpus
      -> multisrc_corpus.load_season
        -> _to_adapter_shape(fx)            "Map a TheStatsAPI fixture -> the shape
                                             adapt_match wants"
        -> championship_adapter.adapt_match(shape, stats_json)
             stats_json = the TheStatsAPI /stats response
             returns a FootyStats-SCHEMA dict
      -> corpus._extra_pairs(sd)

Every number the bridge can currently read therefore originates from **TheStatsAPI**.
FootyStats is the SCHEMA the rows are shaped into, not the source of the values. So the
frozen policy for this experiment is `THESTATSAPI_ONLY` -- see `CORPUS_PROVIDER_LINEAGE`.
Declaring FootyStats capabilities here does NOT make the current rehearsal a blend, and
`resolve_measurement_provider` refuses to let it become one.

WHAT IS AND IS NOT DECLARED
===========================
Only the bridge's own canonical vocabulary (`cohorts.ALL_METRICS`) is keyed here, because a
capability for a metric the IR cannot express would be unmeasurable by construction. Two
exceptions are declared NON-measurably, because saying nothing would be read as "no such
field": `xg` (§3G) and FootyStats `total_shots`.

Every entry carries a `status`. Only `MEASURABLE` is measurable; every other status fails
closed. Nothing here is populated from a documentation list -- each entry names the file and
line it was traced from.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, asdict

from src.research.llm_matchup import cohorts as CH
from src.research.hypothesis_bridge.versions import CAPABILITY_REGISTRY_VERSION
# Reuse the ALREADY-EXISTING provider vocabulary and policy enum. Defining a second copy
# here would be exactly the competing reconciliation framework this must not become.
from src.research.reconciliation.reconciler import FOOTYSTATS, THESTATSAPI
from src.research.reconciliation.policy import ReconciliationPolicy

PROVIDERS = frozenset({FOOTYSTATS, THESTATSAPI})

#: The provider the CURRENT MatchRecord corpus's values actually come from, traced above.
#: Measuring this corpus under any other provider's capability would fabricate provenance.
CORPUS_PROVIDER_LINEAGE = THESTATSAPI

#: The schema the corpus rows are shaped into. Recorded so a reader cannot mistake it for the
#: provider: `adapt_match` returns a FootyStats-schema dict built from TheStatsAPI data.
CORPUS_STORAGE_SCHEMA = "footystats_schema"

#: The frozen policy for THIS confirmatory experiment. Not a default that drifts: the corpus
#: is single-provider, so anything else would be a different scientific instrument.
FROZEN_REHEARSAL_POLICY = ReconciliationPolicy.THESTATSAPI_ONLY

# --- capability status ------------------------------------------------------------------
#: Traced, semantically sound, and readable by this bridge. The ONLY measurable status.
MEASURABLE = "MEASURABLE"
#: Traced, but a provider-semantics audit found the values do not mean what the name says.
EXCLUDED_PROVIDER_SEMANTICS = "EXCLUDED_PROVIDER_SEMANTICS"
#: Traced at the provider, but outside this bridge's canonical IR vocabulary.
DECLARED_NOT_IN_BRIDGE_VOCABULARY = "DECLARED_NOT_IN_BRIDGE_VOCABULARY"
#: Traced at the provider, but its mapping onto the canonical metric is not validated.
UNVALIDATED_EQUIVALENCE = "UNVALIDATED_EQUIVALENCE"

#: NULL means NOT RECORDED everywhere in this registry: `team_metric` and `_extra_pairs` emit
#: a value only when both sides are non-null, and a genuine 0 is preserved. Never coerce.
NULL_IS_NOT_RECORDED = "NULL_IS_NOT_RECORDED_NEVER_ZERO"


class UnknownProvider(ValueError):
    """A provider outside the declared set. Fail closed -- never guess."""


class ProviderPolicyUnsupported(NotImplementedError):
    """A reconciliation policy this bridge deliberately does not implement.

    `PREFERRED_PROVIDER_WITH_FALLBACK` and `VALIDATED_BLEND` are legitimate policies in
    `src/research/reconciliation`, but no cross-provider resolution path exists in the bridge.
    Raising is the honest outcome: accepting the value and doing something reasonable-looking
    is how a silent fallback or a silent blend gets introduced.
    """


@dataclass(frozen=True)
class ProviderCapability:
    """One provider's ability to observe one canonical metric. Never cross-provider."""
    canonical_metric: str
    provider: str
    #: The PROVIDER's own field/path, in the provider's own payload. This is provenance.
    provider_source_field: str
    #: Where the loader parks it in a MatchRecord, when this provider feeds the corpus.
    storage_field: str | None
    storage_container: str | None          # base | rich | extra
    units: str
    definition: str                         # what the provider's field actually means
    period_support: tuple[str, ...]
    null_semantics: str
    status: str
    traced_from: str                        # file:line the mapping was read from
    #: Cross-provider equivalence is NEVER assumed. Set only by a versioned semantic decision.
    semantic_equivalence_validated: bool = False
    exclusion_reason: str | None = None
    exclusion_evidence: str | None = None

    @property
    def is_measurable(self) -> bool:
        return self.status == MEASURABLE

    @property
    def capability_id(self) -> str:
        """Identity of this capability. Binds the PROVIDER, so the same canonical metric
        from two providers can never share an id."""
        payload = {"registry_version": CAPABILITY_REGISTRY_VERSION, **asdict(self)}
        digest = hashlib.sha256(
            json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()
        return f"cap_{self.provider}_{self.canonical_metric}_{digest[:16]}"


# =========================================================================================
# TheStatsAPI -- traced against `championship_adapter.adapt_match` / `_rich_fields`,
# `corpus._EXTRA_STATS` and `cohorts.ALL_METRICS`/`HALF_METRICS`.
# =========================================================================================
_TSA_SOURCE = {
    # canonical metric        provider path                       storage key, container
    "crosses":              ("passes.accurate_crosses",            "accurate_crosses", "rich"),
    "total_shots":          ("overview.total_shots",               "total_shots", "extra"),
    "shots_on_target":      ("overview.shots_on_target",           "shots_on_target", "rich"),
    "shots_inside_box":     ("shots.shots_inside_box",             "shots_inside_box", "rich"),
    "shots_outside_box":    ("shots.shots_outside_box",            "shots_outside_box", "rich"),
    "blocked_shots":        ("shots.blocked_shots",                "blocked_shots", "rich"),
    "corners":              ("overview.corner_kicks",              "corner_kicks", "rich"),
    "possession":           ("overview.ball_possession",           "possession", "extra"),
    "fouls":                ("overview.fouls",                     "fouls", "rich"),
    # TheStatsAPI provenance parked in a FootyStats-SCHEMA storage field. The entry a
    # container-based or name-based inference gets wrong.
    "yellow_cards":         ("overview.yellow_cards",              "team_a_yellow_cards/team_b_yellow_cards", "base"),
    "tackles":              ("defending.tackles",                  "tackles", "rich"),
    "touches_in_box":       ("attack.touches_in_penalty_area",     "touches_in_penalty_area", "rich"),
    "final_third_entries":  ("passes.final_third_entries",         "final_third_entries", "rich"),
    "throw_ins":            ("passes.throw_ins",                   "throw_ins", "extra"),
    "clearances":           ("defending.clearances",               "clearances", "rich"),
    "interceptions":        ("defending.interceptions",            "interceptions", "rich"),
    "big_chances":          ("overview.big_chances",               "big_chances", "rich"),
    "saves":                ("goalkeeping.saves",                  "saves", "rich"),
}

_TSA_UNITS = {"possession": "percent"}

#: npxG is handled separately and EXCLUDED. `championship_adapter._cell` special-cases it:
#: the node is the ROOT key `np_expected_goals`, then `[period][side]` -- there is no
#: `np_expected_goals.np_expected_goals` path, and the previous registry invented one.
_TSA_NPXG_SOURCE = "np_expected_goals.all.{home|away}"

#: V5A.1 measured it rather than assuming: non-penalty xG exceeded TOTAL xG by >0.05 in
#: 511/3,242 raw pairs (15.8%), worst -0.99, with a smooth non-penalty-shaped error
#: distribution. The definitional relationship npxG <= xG is violated, classified
#: PROVIDER_SOURCE_INCONSISTENCY, and npxG was excluded from model-visible evidence. It
#: cannot be repaired: the corpus carries no penalty or penalty-xG field to recompute from.
_NPXG_AUDIT = "research/hypothesis_engine/V5A1_PROVIDER_SEMANTICS_AUDIT.md §2"


# =========================================================================================
# FootyStats -- traced ONLY against `src/research/footystats/normalizer.py`. Nothing here
# comes from a documentation list; a field that could not be traced is simply absent.
#
# ABSENT AND DELIBERATELY SO: FootyStats exposes no non-penalty-xG field anywhere in the
# normalizer, so there is NO ("footystats", "npxg") entry. That is a traced absence, not an
# oversight, and it is emphatically NOT inferred from FootyStats' `team_a_xg`.
# =========================================================================================
_FS_SOURCE = {
    # canonical metric   provider field                normalized field,        line
    "corners":          ("team_a_corners/team_b_corners",
                         "corners_home/corners_away", "normalizer.py:180-181"),
    "yellow_cards":     ("team_a_yellow_cards/team_b_yellow_cards",
                         "yellow_cards_home/yellow_cards_away", "normalizer.py:184-185"),
    "fouls":            ("team_a_fouls/team_b_fouls",
                         "fouls_home/fouls_away", "normalizer.py:194-195"),
    "possession":       ("team_a_possession/team_b_possession",
                         "possession_home/possession_away", "normalizer.py:202-203"),
    "shots_on_target":  ("team_a_shotsOnTarget/team_b_shotsOnTarget",
                         "shots_on_target_home/shots_on_target_away", "normalizer.py:175-176"),
}


def _tsa_periods(metric: str) -> tuple[str, ...]:
    return ("all", "first_half", "second_half") if metric in CH.HALF_METRICS else ("all",)


def _build() -> dict[tuple[str, str], ProviderCapability]:
    table: dict[tuple[str, str], ProviderCapability] = {}

    # --- TheStatsAPI: measurable entries ---------------------------------------------
    for metric in sorted(CH.ALL_METRICS):
        src = _TSA_SOURCE.get(metric)
        if src is None:
            continue                     # fail closed: untraced is never advertised
        path, storage, container = src
        table[(THESTATSAPI, metric)] = ProviderCapability(
            canonical_metric=metric, provider=THESTATSAPI, provider_source_field=path,
            storage_field=storage, storage_container=container,
            units=_TSA_UNITS.get(metric, "count"),
            definition=f"TheStatsAPI /stats {path}, per team, per period",
            period_support=_tsa_periods(metric), null_semantics=NULL_IS_NOT_RECORDED,
            status=MEASURABLE,
            traced_from="scripts/championship_adapter.py:_cell/_rich_fields")

    # --- TheStatsAPI: npxG, traced but EXCLUDED by the existing audit ------------------
    table[(THESTATSAPI, "npxg")] = ProviderCapability(
        canonical_metric="npxg", provider=THESTATSAPI,
        provider_source_field=_TSA_NPXG_SOURCE,
        storage_field="np_expected_goals", storage_container="rich",
        units="expected_goals",
        definition=("TheStatsAPI root node `np_expected_goals`, intended as NON-PENALTY "
                    "expected goals; the feed does not honour npxG <= xG"),
        period_support=("all",), null_semantics=NULL_IS_NOT_RECORDED,
        status=EXCLUDED_PROVIDER_SEMANTICS,
        traced_from="scripts/championship_adapter.py:24-33,125-128",
        exclusion_reason="PROVIDER_SOURCE_INCONSISTENCY",
        exclusion_evidence=_NPXG_AUDIT)

    # --- TheStatsAPI: xG, declared for §3G but outside the IR vocabulary ---------------
    table[(THESTATSAPI, "xg")] = ProviderCapability(
        canonical_metric="xg", provider=THESTATSAPI,
        provider_source_field="overview.expected_goals",
        storage_field="team_a_xg/team_b_xg", storage_container="base",
        units="expected_goals",
        definition="TheStatsAPI TOTAL expected goals, penalties INCLUDED",
        period_support=("all",), null_semantics=NULL_IS_NOT_RECORDED,
        status=DECLARED_NOT_IN_BRIDGE_VOCABULARY,
        traced_from="scripts/championship_adapter.py:54-55")

    # --- FootyStats: measurable-at-the-provider entries --------------------------------
    for metric, (field_, normalized, line) in sorted(_FS_SOURCE.items()):
        table[(FOOTYSTATS, metric)] = ProviderCapability(
            canonical_metric=metric, provider=FOOTYSTATS, provider_source_field=field_,
            storage_field=normalized, storage_container=None,
            units="percent" if metric == "possession" else "count",
            definition=f"FootyStats match field {field_}; -1 is a NOT-RECORDED sentinel",
            # The FootyStats normalizer exposes full-match values only; no half split.
            period_support=("all",), null_semantics=NULL_IS_NOT_RECORDED,
            status=MEASURABLE,
            traced_from=f"src/research/footystats/{line}")

    # --- FootyStats: traced, but NOT claimed equal to the TheStatsAPI concept ----------
    table[(FOOTYSTATS, "total_shots")] = ProviderCapability(
        canonical_metric="total_shots", provider=FOOTYSTATS,
        provider_source_field="team_a_shots/team_b_shots",
        storage_field="shots_home/shots_away", storage_container=None,
        units="count",
        definition=("FootyStats shot count; whether it counts the same events as "
                    "TheStatsAPI `overview.total_shots` has NOT been measured"),
        period_support=("all",), null_semantics=NULL_IS_NOT_RECORDED,
        status=UNVALIDATED_EQUIVALENCE,
        traced_from="src/research/footystats/normalizer.py:173-174",
        exclusion_reason="CANONICAL_MAPPING_NOT_VALIDATED",
        exclusion_evidence="no cross-provider shot-definition comparison has been run")

    # --- FootyStats: xG, declared for §3G. NOT equal to TheStatsAPI xG by assumption ----
    table[(FOOTYSTATS, "xg")] = ProviderCapability(
        canonical_metric="xg", provider=FOOTYSTATS,
        provider_source_field="team_a_xg/team_b_xg",
        storage_field="home_xg/away_xg", storage_container=None,
        units="expected_goals",
        definition=("FootyStats expected goals, from FootyStats' own model. Equality with "
                    "TheStatsAPI `overview.expected_goals` is NOT established"),
        period_support=("all",), null_semantics=NULL_IS_NOT_RECORDED,
        status=DECLARED_NOT_IN_BRIDGE_VOCABULARY,
        traced_from="src/research/footystats/normalizer.py:205-206")

    return table


#: Keyed on `(provider, canonical_metric)`. There is no metric-only accessor anywhere in this
#: module: a caller that does not know which provider it means has not earned an answer.
PROVIDER_CAPABILITIES: dict[tuple[str, str], ProviderCapability] = _build()


def _require_provider(provider: str) -> None:
    if provider not in PROVIDERS:
        raise UnknownProvider(f"unknown_provider:{provider!r} (declared: {sorted(PROVIDERS)})")


def capability_for(provider: str, metric: str) -> ProviderCapability | None:
    """The capability for exactly this `(provider, metric)`, or None. Never falls back to
    another provider -- that is the silent-substitution failure this key shape exists to
    prevent."""
    _require_provider(provider)
    return PROVIDER_CAPABILITIES.get((provider, metric))


def is_measurable(provider: str, metric: str) -> bool:
    cap = capability_for(provider, metric)
    return bool(cap) and cap.is_measurable


def supports_period(provider: str, metric: str, period: str) -> bool:
    cap = capability_for(provider, metric)
    return bool(cap) and cap.is_measurable and period in cap.period_support


def resolve_measurement_provider(policy: ReconciliationPolicy) -> str:
    """The single provider a measurement under `policy` may read. Explicit or nothing.

    Only the two single-provider policies resolve. `PREFERRED_PROVIDER_WITH_FALLBACK` and
    `VALIDATED_BLEND` raise: the bridge has no cross-provider resolution path, and pretending
    otherwise is precisely how an implicit fallback or blend arrives. When two providers do
    eventually observe the same concept here, the answer is
    `src/research/reconciliation/reconciler.py`, not a branch added to this function.
    """
    if policy is ReconciliationPolicy.THESTATSAPI_ONLY:
        return THESTATSAPI
    if policy is ReconciliationPolicy.FOOTYSTATS_ONLY:
        return FOOTYSTATS
    if isinstance(policy, ReconciliationPolicy):
        raise ProviderPolicyUnsupported(
            f"policy_not_implemented_in_bridge:{policy.value}; use "
            f"src/research/reconciliation/reconciler.py for cross-provider resolution")
    raise ProviderPolicyUnsupported(f"not_a_reconciliation_policy:{policy!r}")


def capabilities_for_provider(provider: str) -> dict[str, ProviderCapability]:
    _require_provider(provider)
    return {m: c for (p, m), c in PROVIDER_CAPABILITIES.items() if p == provider}


def measurable_metrics(provider: str) -> list[str]:
    return sorted(m for m, c in capabilities_for_provider(provider).items() if c.is_measurable)


def providers_declared() -> list[str]:
    return sorted(PROVIDERS)


def registry_hash() -> str:
    """Identity of the WHOLE registry. Moves when any provider's semantics move."""
    payload = {
        "registry_version": CAPABILITY_REGISTRY_VERSION,
        "corpus_provider_lineage": CORPUS_PROVIDER_LINEAGE,
        "corpus_storage_schema": CORPUS_STORAGE_SCHEMA,
        "capabilities": {f"{p}|{m}": asdict(c)
                         for (p, m), c in sorted(PROVIDER_CAPABILITIES.items())},
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


#: Back-compat alias: the old name for the whole-registry digest.
capability_hash = registry_hash
