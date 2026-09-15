"""Provider capability inventory (`capability_inventory_v1`).

THE GOVERNING PRINCIPLE OF THIS PACKAGE
---------------------------------------
    The LLM proposes what to measure.
    The deterministic engine measures it.
    Statistical validation determines whether it generalizes.
    The quantitative model produces the probability.
    The market and prospective outcomes determine whether the resulting model adds value.

This module is the single source of truth for WHAT CAN BE ASKED. Every metric, provider
concept and semantic caveat below was verified against the corpus on disk, not assumed:

  * FootyStats league-match payloads  -> data/discovery/corpus/league-matches_*.json
    (215 top-level fields per match; 123 non-odds).
  * TheStatsAPI adapted matches       -> data/thestatsapi/championship/*stats_mt_*.json
    via scripts/championship_adapter._rich_fields + src/research/matchup/corpus._EXTRA_STATS.
  * TheStatsAPI lineups/formations    -> data/thestatsapi/championship/lineups_mt_*.json
  * Half-split availability            -> src/research/llm_matchup/cohorts.HALF_METRICS
    (documented there as "only stats verified present in the raw payload with
    first_half/second_half splits").
  * Cross-provider agreement           -> research/contextual_matchup/PROVIDER_SEMANTICS.md
    (546 joined EPL + 420 Championship fixtures).

A metric absent here CANNOT be queried. The compiler fails closed with UNSUPPORTED_METRIC
rather than approximating, because a silently-approximated metric is indistinguishable from
a hallucinated one once it reaches a research result.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

CAPABILITY_INVENTORY_VERSION = "capability_inventory_v1"


# --------------------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------------------
FOOTYSTATS = "footystats"
THESTATSAPI = "thestatsapi"
DERIVED = "derived"

PROVIDERS = (FOOTYSTATS, THESTATSAPI, DERIVED)


# --------------------------------------------------------------------------------------
# Cross-provider comparability.
#
# From PROVIDER_SEMANTICS.md. `MERGEABLE` means the two providers' values for the concept
# were measured to agree closely enough to be treated as one concept. `DO_NOT_MERGE` means
# they were measured to disagree materially -- a feature must pick ONE provider and stay
# with it. `UNMEASURED` means no agreement study exists; treated exactly like DO_NOT_MERGE
# for safety, but labelled differently so the distinction between "measured to disagree"
# and "never checked" is never lost.
# --------------------------------------------------------------------------------------
MERGEABLE = "MERGEABLE"
DO_NOT_MERGE = "DO_NOT_MERGE"
UNMEASURED = "UNMEASURED"
SINGLE_PROVIDER = "SINGLE_PROVIDER"     # only one provider supplies the concept at all


# --------------------------------------------------------------------------------------
# Granularity
# --------------------------------------------------------------------------------------
GRAN_FULL_MATCH = "FULL_MATCH"          # one value per team per match
GRAN_HALF = "HALF"                      # first_half / second_half splits exist
GRAN_EVENT = "EVENT"                    # minute-level timestamped events

#: Minute-level event granularity that the corpus DOES supply, and for which concept.
#: FootyStats records goal minutes only. No provider supplies timestamped corner, shot,
#: cross, tackle or card events, so no minute-level conditioning on those is possible.
EVENT_TIMED_CONCEPTS = frozenset({"goals"})


@dataclass(frozen=True)
class MetricSpec:
    """One canonical metric the deterministic engine can actually measure."""

    canonical: str
    definition: str
    providers: tuple[str, ...]
    #: provider -> raw source field path, exactly as it appears in the payload
    source_fields: dict[str, str]
    granularity: str
    comparability: str
    #: True when a FOR/AGAINST orientation is meaningful (team's own vs conceded)
    has_sides: bool = True
    #: True when the metric supports a venue (home/away) split -- all match-level stats do
    has_venue_split: bool = True
    caveat: Optional[str] = None
    families: tuple[str, ...] = ()

    def supports(self, granularity: str) -> bool:
        if granularity == GRAN_FULL_MATCH:
            return True
        if granularity == GRAN_HALF:
            return self.granularity in (GRAN_HALF, GRAN_EVENT)
        if granularity == GRAN_EVENT:
            return self.granularity == GRAN_EVENT
        return False


_M = MetricSpec

#: Canonical metric registry. Keys are the ONLY legal `target_metrics` values.
METRICS: dict[str, MetricSpec] = {
    # ---------------- offensive / outcome ----------------
    "goals": _M(
        canonical="goals",
        definition="Goals scored (for) / conceded (against), full time.",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "homeGoalCount|awayGoalCount",
                       THESTATSAPI: "overview/goals"},
        granularity=GRAN_EVENT,
        comparability=MERGEABLE,
        caveat="Also the settlement statistic for the goals market; never use a "
               "post-kickoff value as a feature.",
        families=("attack", "defense"),
    ),
    "total_shots": _M(
        canonical="total_shots",
        definition="All shot attempts, any location.",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "team_a_shots|team_b_shots",
                       THESTATSAPI: "shots/total_shots"},
        granularity=GRAN_HALF,
        comparability=DO_NOT_MERGE,
        caveat="MEASURED DISAGREEMENT: corr 0.80, MAD 2.24 across 966 joined fixtures. "
               "The providers use different shot definitions. Pick one provider per "
               "feature and stay with it; never average.",
        families=("attack", "defense"),
    ),
    "shots_on_target": _M(
        canonical="shots_on_target",
        definition="Shots on target.",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "team_a_shotsOnTarget|team_b_shotsOnTarget",
                       THESTATSAPI: "shots/shots_on_target"},
        granularity=GRAN_HALF,
        comparability=MERGEABLE,
        caveat="corr 0.994.",
        families=("attack", "defense"),
    ),
    "shots_off_target": _M(
        canonical="shots_off_target",
        definition="Shots off target.",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "team_a_shotsOffTarget|team_b_shotsOffTarget",
                       THESTATSAPI: "shots/shots_off_target"},
        granularity=GRAN_FULL_MATCH,
        comparability=DO_NOT_MERGE,
        caveat="Follows total_shots' definitional split; inherits DO_NOT_MERGE.",
        families=("attack", "defense"),
    ),
    "blocked_shots": _M(
        canonical="blocked_shots",
        definition="Shots blocked by an outfield defender.",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "shots/blocked_shots"},
        granularity=GRAN_HALF,
        comparability=SINGLE_PROVIDER,
        families=("attack", "defense"),
    ),
    "shots_inside_box": _M(
        canonical="shots_inside_box",
        definition="Shots taken inside the penalty area.",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "shots/shots_inside_box"},
        granularity=GRAN_HALF,
        comparability=SINGLE_PROVIDER,
        families=("attack", "defense"),
    ),
    "shots_outside_box": _M(
        canonical="shots_outside_box",
        definition="Shots taken outside the penalty area.",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "shots/shots_outside_box"},
        granularity=GRAN_FULL_MATCH,
        comparability=SINGLE_PROVIDER,
        families=("attack", "defense"),
    ),
    "corners": _M(
        canonical="corners",
        definition="Corner kicks won (for) / conceded (against).",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "team_a_corners|team_b_corners",
                       THESTATSAPI: "overview/corner_kicks"},
        granularity=GRAN_HALF,
        comparability=MERGEABLE,
        caveat="corr 0.996. FootyStats additionally exposes fh/2h counts directly "
               "(team_*_fh_corners / team_*_2h_corners).",
        families=("attack", "defense"),
    ),
    "accurate_crosses": _M(
        canonical="accurate_crosses",
        definition="ACCURATE crosses completed. This is NOT total crosses attempted.",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "passes/accurate_crosses"},
        granularity=GRAN_HALF,
        comparability=SINGLE_PROVIDER,
        caveat="SEMANTIC TRAP: the provider field is passes/accurate_crosses -- completed "
               "crosses only. Cross ATTEMPTS are not available from either provider. Never "
               "present this as 'crosses' or 'cross volume' without the accuracy qualifier.",
        families=("attack", "defense"),
    ),
    "possession": _M(
        canonical="possession",
        definition="Ball possession percentage.",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "team_a_possession|team_b_possession",
                       THESTATSAPI: "overview/ball_possession"},
        granularity=GRAN_HALF,
        comparability=MERGEABLE,
        caveat="corr 0.999. Zero-sum across the two teams; 'possession against' is "
               "definitionally 100 - possession for.",
        families=("attack", "defense", "context"),
    ),
    "xg": _M(
        canonical="xg",
        definition="Expected goals, post-match model estimate.",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "team_a_xg|team_b_xg",
                       THESTATSAPI: "expected_goals"},
        granularity=GRAN_FULL_MATCH,
        comparability=DO_NOT_MERGE,
        caveat="MEASURED DISAGREEMENT: corr 0.55, MAD 0.69. These are DIFFERENT xG MODELS, "
               "not two measurements of one quantity. Never average, never substitute one "
               "for the other. Provider must be pinned explicitly.",
        families=("attack", "defense"),
    ),
    "npxg": _M(
        canonical="npxg",
        definition="Non-penalty expected goals (TheStatsAPI model).",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "np_expected_goals"},
        granularity=GRAN_FULL_MATCH,
        comparability=SINGLE_PROVIDER,
        caveat="Distinct concept from post-match xg; not interchangeable with it.",
        families=("attack", "defense"),
    ),
    "big_chances": _M(
        canonical="big_chances",
        definition="Clear-cut scoring chances (TheStatsAPI classification).",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "overview/big_chances"},
        granularity=GRAN_FULL_MATCH,
        comparability=SINGLE_PROVIDER,
        families=("attack", "defense"),
    ),
    "touches_in_box": _M(
        canonical="touches_in_box",
        definition="Touches in the opposition penalty area.",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "attack/touches_in_penalty_area"},
        granularity=GRAN_HALF,
        comparability=SINGLE_PROVIDER,
        caveat="SEMANTIC TRAP: this is NOT FootyStats 'dangerous attacks'. The repository "
               "records it as a noted PROXY for that concept and no reconciliation study "
               "has been run. Never equate the two.",
        families=("attack", "defense"),
    ),
    "final_third_entries": _M(
        canonical="final_third_entries",
        definition="Successful entries into the attacking third.",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "passes/final_third_entries"},
        granularity=GRAN_HALF,
        comparability=SINGLE_PROVIDER,
        families=("attack", "defense"),
    ),
    "throw_ins": _M(
        canonical="throw_ins",
        definition="Throw-ins taken.",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "team_a_throwins|team_b_throwins",
                       THESTATSAPI: "passes/throw_ins"},
        granularity=GRAN_HALF,
        comparability=UNMEASURED,
        caveat="No cross-provider agreement study exists for this concept. Treated as "
               "single-provider-only until one is run.",
        families=("attack",),
    ),
    "attacks": _M(
        canonical="attacks",
        definition="FootyStats 'attacks' counter.",
        providers=(FOOTYSTATS,),
        source_fields={FOOTYSTATS: "team_a_attacks|team_b_attacks"},
        granularity=GRAN_FULL_MATCH,
        comparability=SINGLE_PROVIDER,
        caveat="FootyStats-proprietary counter with no published definition and no "
               "TheStatsAPI analogue.",
        families=("attack",),
    ),
    "dangerous_attacks": _M(
        canonical="dangerous_attacks",
        definition="FootyStats 'dangerous attacks' counter.",
        providers=(FOOTYSTATS,),
        source_fields={FOOTYSTATS: "team_a_dangerous_attacks|team_b_dangerous_attacks"},
        granularity=GRAN_FULL_MATCH,
        comparability=SINGLE_PROVIDER,
        caveat="SEMANTIC TRAP: FootyStats-proprietary. NOT equivalent to TheStatsAPI "
               "touches_in_box. src/research/matchup/corpus.py records touches_in_box as a "
               "'FS-only concept absent in TSA; proxy noted' -- a noted proxy is not a "
               "validated equivalence. Do not substitute one for the other.",
        families=("attack",),
    ),
    "offsides": _M(
        canonical="offsides",
        definition="Offside calls against the team.",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "team_a_offsides|team_b_offsides",
                       THESTATSAPI: "attack/offsides"},
        granularity=GRAN_FULL_MATCH,
        comparability=UNMEASURED,
        families=("attack",),
    ),

    # ---------------- defensive / physical ----------------
    "tackles": _M(
        canonical="tackles",
        definition="Tackles made.",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "defending/tackles"},
        granularity=GRAN_HALF,
        comparability=SINGLE_PROVIDER,
        families=("defense", "discipline"),
    ),
    "interceptions": _M(
        canonical="interceptions",
        definition="Interceptions made.",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "defending/interceptions"},
        granularity=GRAN_HALF,
        comparability=SINGLE_PROVIDER,
        families=("defense",),
    ),
    "clearances": _M(
        canonical="clearances",
        definition="Clearances made.",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "defending/clearances"},
        granularity=GRAN_HALF,
        comparability=SINGLE_PROVIDER,
        families=("defense",),
    ),
    "saves": _M(
        canonical="saves",
        definition="Goalkeeper saves.",
        providers=(THESTATSAPI,),
        source_fields={THESTATSAPI: "goalkeeping/saves"},
        granularity=GRAN_FULL_MATCH,
        comparability=SINGLE_PROVIDER,
        families=("defense",),
    ),
    "fouls": _M(
        canonical="fouls",
        definition="Fouls committed.",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "team_a_fouls|team_b_fouls",
                       THESTATSAPI: "overview/fouls"},
        granularity=GRAN_HALF,
        comparability=MERGEABLE,
        caveat="~0.89 exact agreement; same concept with minor definitional drift. "
               "Documented, not silently merged -- pin the provider on any feature.",
        families=("discipline",),
    ),
    "yellow_cards": _M(
        canonical="yellow_cards",
        definition="Yellow cards received.",
        providers=(FOOTYSTATS, THESTATSAPI),
        source_fields={FOOTYSTATS: "team_a_yellow_cards|team_b_yellow_cards",
                       THESTATSAPI: "overview/yellow_cards"},
        granularity=GRAN_HALF,
        comparability=MERGEABLE,
        families=("discipline",),
    ),
    "red_cards": _M(
        canonical="red_cards",
        definition="Red cards received.",
        providers=(FOOTYSTATS,),
        source_fields={FOOTYSTATS: "team_a_red_cards|team_b_red_cards"},
        granularity=GRAN_FULL_MATCH,
        comparability=SINGLE_PROVIDER,
        caveat="TheStatsAPI red-card cells are sometimes null and NULL != ZERO is "
               "preserved, so reds are taken from FootyStats only.",
        families=("discipline",),
    ),
    "total_bookings": _M(
        canonical="total_bookings",
        definition="Total cards (FootyStats cards_num: yellows + reds as the provider "
                   "counts them).",
        providers=(FOOTYSTATS,),
        source_fields={FOOTYSTATS: "team_a_cards_num|team_b_cards_num"},
        granularity=GRAN_HALF,
        comparability=SINGLE_PROVIDER,
        caveat="This is the cards-market settlement concept. FootyStats also exposes "
               "team_*_fh_cards / team_*_2h_cards for half-level work.",
        families=("discipline",),
    ),
}


# --------------------------------------------------------------------------------------
# Context sources: things that condition a query rather than being measured by it.
# --------------------------------------------------------------------------------------
SUPPORTED = "SUPPORTED"
UNSUPPORTED_CONTEXT_SOURCE = "UNSUPPORTED_CONTEXT_SOURCE"


@dataclass(frozen=True)
class ContextSourceSpec:
    name: str
    status: str
    providers: tuple[str, ...]
    note: str
    #: Present so a future provenance-tracked source can be wired in without a schema
    #: change. `None` while unsupported.
    source_path: Optional[str] = None


CONTEXT_SOURCES: dict[str, ContextSourceSpec] = {
    "venue": ContextSourceSpec(
        "venue", SUPPORTED, (FOOTYSTATS, THESTATSAPI),
        "home/away is intrinsic to every match record."),
    "competition": ContextSourceSpec(
        "competition", SUPPORTED, (FOOTYSTATS, THESTATSAPI),
        "competition_id on every match record."),
    "referee": ContextSourceSpec(
        "referee", SUPPORTED, (FOOTYSTATS,),
        "FootyStats refereeID only; absent from TheStatsAPI.",
        source_path="refereeID"),
    "historical_formation": ContextSourceSpec(
        "historical_formation", SUPPORTED, (THESTATSAPI,),
        "lineups_mt_<id>.json carries confirmed:true with home.formation / away.formation "
        "for a COMPLETED fixture. There is no announcement timestamp, which restricts "
        "temporal claims -- see TEMPORAL_CLAIM_RULES -- but does NOT restrict use as "
        "fixture-level historical context. Coverage is partial and must be reported.",
        source_path="data/thestatsapi/championship/lineups_mt_*.json"),
    "lineup_composition": ContextSourceSpec(
        "lineup_composition", SUPPORTED, (THESTATSAPI,),
        "starting_xi + substitutes lists in the same lineup payload. A roster, not a "
        "timed substitution feed.",
        source_path="data/thestatsapi/championship/lineups_mt_*.json"),
    "half_time_score_state": ContextSourceSpec(
        "half_time_score_state", SUPPORTED, (FOOTYSTATS, DERIVED),
        "Derived deterministically from FootyStats ht_goals_team_a / ht_goals_team_b "
        "(cross-checkable against homeGoals_timings / awayGoals_timings minute lists). "
        "Supports LEADING_AT_HT / LEVEL_AT_HT / TRAILING_AT_HT, and needs no minute-level "
        "event feed. "
        "CORPUS CAVEAT, VERIFIED: the TheStatsAPI-adapted rich corpus that "
        "`corpus_adapter` reads does NOT carry half-time goals -- the adapted record "
        "exposes only full-time goals plus a few second-half card counts. So this source "
        "is supported by the FOOTYSTATS corpus and is NOT available through the "
        "TheStatsAPI path; a fixture whose history comes from TheStatsAPI alone has the "
        "dimension withheld by its capability manifest. Enabling it for those fixtures "
        "requires a provenance-tracked FootyStats join, which is a separate piece of work "
        "and must not be faked by approximating HT state from full-time goals.",
        source_path="ht_goals_team_a|ht_goals_team_b"),
    "expected_formation": ContextSourceSpec(
        "expected_formation", UNSUPPORTED_CONTEXT_SOURCE, (),
        "No provider in this repository supplies a pre-match expected formation or a "
        "timestamped lineup feed. A FUTURE fixture's formation is therefore UNKNOWN. "
        "Hypotheses must instead range over the team's observed recent formation "
        "distribution, or be formation-independent. Wire a real source here with "
        "provenance to enable it."),
    "injuries": ContextSourceSpec(
        "injuries", UNSUPPORTED_CONTEXT_SOURCE, (),
        "Neither audited corpus contains an injury or availability field. Not banned "
        "architecturally -- add a provenance-tracked source and flip this to SUPPORTED. "
        "Until then any injury-conditioned hypothesis fails closed."),
    "minute_level_events": ContextSourceSpec(
        "minute_level_events", UNSUPPORTED_CONTEXT_SOURCE, (),
        "Only GOAL minutes are timestamped (FootyStats homeGoals_timings / "
        "awayGoals_timings). No timestamped corner, shot, cross, tackle, card or "
        "substitution events exist, so no 'in the N minutes after X' or 'between minute "
        "A and B' conditioning is possible for any metric other than goals."),
    "weather": ContextSourceSpec(
        "weather", UNSUPPORTED_CONTEXT_SOURCE, (),
        "Not present in either corpus."),
    "player_ratings": ContextSourceSpec(
        "player_ratings", UNSUPPORTED_CONTEXT_SOURCE, (),
        "Not surfaced by the adapters in use."),
}


# --------------------------------------------------------------------------------------
# Temporal-claim rules.
#
# §7 of the mandate: the absence of a formation announcement timestamp must NOT block
# historical formation-conditioned analysis. It blocks precisely three claim shapes, and
# those only.
# --------------------------------------------------------------------------------------
TEMPORAL_CLAIM_RULES = {
    "historical_formation_as_fixture_context": (
        "ALLOWED. 'Team A's full-match corners in fixtures where it was recorded as 4-3-3' "
        "is a statement about completed fixtures. No timestamp is required."),
    "formation_switch_timing": (
        "FORBIDDEN. 'Team A switched to 3-4-3 at minute 62' requires a timed formation "
        "feed that does not exist."),
    "post_switch_rate_change": (
        "FORBIDDEN. 'Corners rose after the formation switch' requires both a timed "
        "formation feed and timestamped corner events. Neither exists."),
    "prematch_formation_availability_time": (
        "FORBIDDEN. 'The formation was publicly known N hours before kickoff' requires an "
        "announcement timestamp that the lineup payloads do not carry."),
}


# --------------------------------------------------------------------------------------
# Lookups used by the compiler and validator
# --------------------------------------------------------------------------------------
def metric(name: str) -> Optional[MetricSpec]:
    return METRICS.get(name)


def is_supported_metric(name: str) -> bool:
    return name in METRICS


def metric_names() -> list[str]:
    return sorted(METRICS)


def metrics_with_granularity(granularity: str) -> list[str]:
    return sorted(n for n, s in METRICS.items() if s.supports(granularity))


def context_source(name: str) -> Optional[ContextSourceSpec]:
    return CONTEXT_SOURCES.get(name)


def is_supported_context_source(name: str) -> bool:
    spec = CONTEXT_SOURCES.get(name)
    return spec is not None and spec.status == SUPPORTED


def unsupported_context_sources() -> list[str]:
    return sorted(n for n, s in CONTEXT_SOURCES.items()
                  if s.status == UNSUPPORTED_CONTEXT_SOURCE)


def providers_for(name: str) -> tuple[str, ...]:
    spec = METRICS.get(name)
    return spec.providers if spec else ()


def may_merge_providers(name: str) -> bool:
    """True only when a measured agreement study licenses treating the two providers'
    values for this concept as one. UNMEASURED is treated as DO_NOT_MERGE."""
    spec = METRICS.get(name)
    return bool(spec) and spec.comparability == MERGEABLE


def semantic_conflicts() -> dict[str, str]:
    """Pairs that must never be silently equated, with the reason. Used by the validator
    to raise PROVIDER_SEMANTICS_CONFLICT rather than quietly substituting."""
    return {
        "dangerous_attacks~touches_in_box":
            "FootyStats dangerous_attacks is a proprietary counter; TheStatsAPI "
            "touches_in_box is a noted proxy with no reconciliation study. Not equivalent.",
        "accurate_crosses~crosses":
            "The only available field is passes/accurate_crosses (completed). Cross "
            "attempts are not available from either provider.",
        "xg@footystats~xg@thestatsapi":
            "Different xG models, corr 0.55. Never averaged or substituted.",
        "total_shots@footystats~total_shots@thestatsapi":
            "Different shot definitions, corr 0.80 / MAD 2.24. Never averaged.",
    }


@dataclass
class FixtureCapabilityManifest:
    """What can actually be asked about ONE upcoming fixture.

    Built per fixture because availability is not global: formation coverage varies by
    team and competition, half-level metrics depend on the provider that supplied the
    history, and a thin history can make an otherwise-supported metric unusable.
    """

    fixture_id: str
    available_metrics: tuple[str, ...]
    available_dimensions: tuple[str, ...]
    unsupported_context: dict[str, str] = field(default_factory=dict)
    #: dimension -> {"candidate_n", "usable_n", "coverage_rate", "missing_n"}
    coverage: dict[str, dict] = field(default_factory=dict)
    notes: tuple[str, ...] = ()

    def allows_metric(self, name: str) -> bool:
        return name in self.available_metrics

    def allows_dimension(self, name: str) -> bool:
        return name in self.available_dimensions

    def to_dict(self) -> dict:
        return {
            "capability_inventory_version": CAPABILITY_INVENTORY_VERSION,
            "fixture_id": self.fixture_id,
            "available_metrics": list(self.available_metrics),
            "available_dimensions": list(self.available_dimensions),
            "unsupported_context": dict(self.unsupported_context),
            "coverage": dict(self.coverage),
            "notes": list(self.notes),
        }


def default_unsupported_context() -> dict[str, str]:
    """The unsupported-context block every fixture manifest starts from, so the LLM is
    always told what it may NOT ask for rather than having to infer it."""
    return {n: CONTEXT_SOURCES[n].note for n in unsupported_context_sources()}
