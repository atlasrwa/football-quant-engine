"""``competition x market`` eligibility — the real unit of engine processing.

WHY THE UNIT IS NOT THE LEAGUE
==============================
A league is not uniformly supported. TheStatsAPI may price total goals in
Veikkausliiga while never pricing cards there, and may price everything in the
Bundesliga except shots on target. Treating the league as the unit of eligibility
forces a false choice: either discard the whole league for one absent market, or
pretend the absent market exists and fabricate a value for it.

So eligibility is per ``(competition, market)`` cell. A competition with

    goals -> READY, corners -> READY, cards -> PARTIAL, shots -> UNKNOWN

processes goals, corners and cards, and abstains on shots. It is not discarded,
and the abstention is recorded with a reason rather than looking like a zero.

THE FOUR-VALUE VOCABULARY IS PRESERVED
======================================
:class:`src.research.prospective.coverage_matrix.MarketEligibility` semantics are
carried through unchanged:

* ``READY``       — a live probe actually saw this market priced.
* ``PARTIAL``     — the provider reports odds for the competition but this market
                    was not seen on the probed fixture. A single fixture does not
                    price every market, so absence is not proof of unsupported.
* ``UNSUPPORTED`` — the provider explicitly reports no odds.
* ``UNKNOWN``     — no evidence either way. Never coerced to ``False`` and never
                    reported as zero.

``READY`` and ``PARTIAL`` are processable. ``UNSUPPORTED`` and ``UNKNOWN`` are
not: both fail closed at the *market* stage, and are reported distinctly so
"the provider says no" is never confused with "we have not looked yet".

SEPARATION OF CONCERNS
======================
This module answers "which markets may be processed for this competition". It
does not answer:

* whether the competition is in the engine universe — that is
  :mod:`src.research.scope.dual_provider` (provider eligibility);
* whether a model can legitimately produce a forecast — that is decided
  per fixture by the forecast engine's history/corpus prerequisites;
* whether accumulated evidence supports validation — that is
  :mod:`src.research._data_accumulation_mode`, and nothing here touches it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from src.research.identity.registry_loader import DEFAULT_REGISTRY_PATH
from src.research.prospective.coverage_matrix import (
    CHAMPION_MARKETS,
    MarketEligibility,
)
from src.research.scope.dual_provider import (
    DualProviderLeague,
    DualProviderUniverse,
    ScopeExclusionReason,
    build_dual_provider_universe,
)

#: Contract string for the machine-readable research scope report.
RESEARCH_SCOPE_CONTRACT = "research-competition-market-scope/v1"

#: Default location of the persisted coverage matrix (produced by
#: ``scripts/prospective_coverage_scan.py``).
DEFAULT_COVERAGE_MATRIX_PATH = Path("research/evaluation/prospective_coverage_matrix.json")

#: Market-eligibility values that permit processing.
PROCESSABLE_MARKET_STATUSES: frozenset[str] = frozenset(
    {MarketEligibility.READY.value, MarketEligibility.PARTIAL.value}
)

#: Model market key -> captured odds market key.
#:
#: This mirrors :data:`src.research.prospective.shadow_builder.MODEL_TO_ODDS_MARKET`
#: exactly, and must keep mirroring it: a model market with no odds counterpart can
#: never be joined against a market snapshot, so it can never become prospective
#: evidence. ``btts`` is absent deliberately — it has no line and no paired
#: over/under total in the capture concept space, so it is skipped rather than
#: guessed.
MODEL_MARKET_TO_ODDS_MARKET: dict[str, str] = {
    "goals": "total_goals",
    "corners": "match_corners",
    "cards": "total_cards",
}

#: The inverse map, for reporting a coverage cell back in model terms.
ODDS_MARKET_TO_MODEL_MARKET: dict[str, str] = {
    v: k for k, v in MODEL_MARKET_TO_ODDS_MARKET.items()
}


class MarketExclusionReason(str, Enum):
    """Why one ``(competition, market)`` cell is not processable.

    Distinct from :class:`~src.research.scope.dual_provider.ScopeExclusionReason`:
    that one excludes a competition, this one excludes a single market within an
    otherwise usable competition.
    """

    NONE = "NONE"
    #: Provider explicitly reports no odds for the competition.
    PROVIDER_MARKET_UNSUPPORTED = "PROVIDER_MARKET_UNSUPPORTED"
    #: No evidence either way yet. Fails closed, but is recoverable by a probe.
    PROVIDER_MARKET_UNKNOWN = "PROVIDER_MARKET_UNKNOWN"
    #: The market has no odds counterpart, so it can never be joined into
    #: prospective evidence (e.g. ``btts``, or an odds market with no model).
    NO_ODDS_COUNTERPART = "NO_ODDS_COUNTERPART"
    #: The coverage matrix has no row for this competition at all.
    NO_COVERAGE_EVIDENCE = "NO_COVERAGE_EVIDENCE"


@dataclass(frozen=True, slots=True)
class CompetitionMarketScope:
    """One eligible competition and the markets it may currently process."""

    competition_id: str
    canonical_name: str
    country: Optional[str]
    footystats_id: Optional[str]
    #: Odds-market key -> READY/PARTIAL/UNSUPPORTED/UNKNOWN, for every champion
    #: market. Always complete: a market is never dropped from this map.
    market_eligibility: dict[str, str]
    #: Odds-market keys that may be processed (READY or PARTIAL).
    processable_odds_markets: tuple[str, ...]
    #: Model-market keys that may be forecast: processable odds markets that have
    #: a model counterpart. This is what the research forecast pass iterates.
    processable_model_markets: tuple[str, ...]
    #: Per-market exclusion reasons, for the markets that are NOT processable.
    market_exclusions: dict[str, str]
    capture_classification: Optional[str]
    capture_priority: Optional[int]
    #: Completed corpus seasons — reported for model-readiness triage only.
    corpus_complete_seasons: Optional[int]
    #: The deprecated Pilot-C-era registry label, reported never applied.
    legacy_model_status: Optional[str]

    @property
    def has_processable_market(self) -> bool:
        return bool(self.processable_odds_markets)

    @property
    def has_forecastable_market(self) -> bool:
        """Whether any market can both be forecast and later joined to odds."""
        return bool(self.processable_model_markets)

    def to_dict(self) -> dict[str, Any]:
        return {
            "competition_id": self.competition_id,
            "canonical_name": self.canonical_name,
            "country": self.country,
            "footystats_id": self.footystats_id,
            "market_eligibility": dict(sorted(self.market_eligibility.items())),
            "processable_odds_markets": list(self.processable_odds_markets),
            "processable_model_markets": list(self.processable_model_markets),
            "market_exclusions": dict(sorted(self.market_exclusions.items())),
            "capture_classification": self.capture_classification,
            "capture_priority": self.capture_priority,
            "corpus_complete_seasons": self.corpus_complete_seasons,
            "legacy_model_status": self.legacy_model_status,
            "legacy_model_status_is_behavioral": False,
        }


def _load_coverage_rows(path: str | Path) -> dict[str, dict[str, Any]]:
    """Coverage-matrix rows keyed by TheStatsAPI competition id.

    A missing or unreadable matrix yields an empty mapping rather than an
    exception. That is the fail-closed outcome: every market becomes
    ``NO_COVERAGE_EVIDENCE`` and nothing is processed, while the competition
    itself remains visibly provider-eligible. Raising instead would make a
    missing observability artifact look like a scope collapse.
    """
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row in data.get("rows", []) or []:
        if not isinstance(row, dict):
            continue
        cid = row.get("thestatsapi_competition_id")
        if cid:
            out[str(cid)] = row
    return out


def _market_cells(
    coverage_row: Optional[dict[str, Any]],
) -> tuple[dict[str, str], dict[str, str]]:
    """Resolve every champion market to a status plus an exclusion reason.

    Returns ``(market_eligibility, market_exclusions)``. The eligibility map is
    always complete over :data:`CHAMPION_MARKETS`; the exclusion map carries a
    reason for exactly the markets that are not processable.
    """
    raw = {}
    if coverage_row is not None:
        candidate = coverage_row.get("market_eligibility")
        if isinstance(candidate, dict):
            raw = candidate

    eligibility: dict[str, str] = {}
    exclusions: dict[str, str] = {}
    for market in CHAMPION_MARKETS:
        if coverage_row is None:
            # No row at all: UNKNOWN, and say that the evidence is missing rather
            # than implying the provider was asked and declined.
            eligibility[market] = MarketEligibility.UNKNOWN.value
            exclusions[market] = MarketExclusionReason.NO_COVERAGE_EVIDENCE.value
            continue
        status = str(raw.get(market, MarketEligibility.UNKNOWN.value))
        if status not in {e.value for e in MarketEligibility}:
            status = MarketEligibility.UNKNOWN.value
        eligibility[market] = status
        if status in PROCESSABLE_MARKET_STATUSES:
            continue
        if status == MarketEligibility.UNSUPPORTED.value:
            exclusions[market] = MarketExclusionReason.PROVIDER_MARKET_UNSUPPORTED.value
        else:
            exclusions[market] = MarketExclusionReason.PROVIDER_MARKET_UNKNOWN.value
    return eligibility, exclusions


def _build_competition_scope(
    league: DualProviderLeague,
    coverage_row: Optional[dict[str, Any]],
) -> CompetitionMarketScope:
    eligibility, exclusions = _market_cells(coverage_row)

    processable_odds = tuple(
        m for m in sorted(eligibility) if eligibility[m] in PROCESSABLE_MARKET_STATUSES
    )

    # Model markets: a processable odds market is forecastable only if a model
    # market maps onto it. An odds market with no model (shots on target) is
    # captured but not forecast; a model market with no odds market (btts) could
    # be forecast but could never become prospective evidence, so it is excluded
    # here rather than producing a forecast that can never be evaluated.
    processable_model: list[str] = []
    for odds_market in processable_odds:
        model_market = ODDS_MARKET_TO_MODEL_MARKET.get(odds_market)
        if model_market is None:
            exclusions.setdefault(
                odds_market, MarketExclusionReason.NO_ODDS_COUNTERPART.value
            )
            continue
        processable_model.append(model_market)

    return CompetitionMarketScope(
        competition_id=str(league.thestatsapi_competition_id),
        canonical_name=league.canonical_name,
        country=league.country,
        footystats_id=league.footystats_id,
        market_eligibility=eligibility,
        processable_odds_markets=processable_odds,
        processable_model_markets=tuple(sorted(processable_model)),
        market_exclusions=exclusions,
        capture_classification=(
            str(coverage_row.get("capture_classification"))
            if coverage_row is not None and coverage_row.get("capture_classification")
            else None
        ),
        capture_priority=(
            int(coverage_row["capture_priority"])
            if coverage_row is not None
            and isinstance(coverage_row.get("capture_priority"), (int, float))
            else None
        ),
        corpus_complete_seasons=league.corpus_complete_seasons,
        legacy_model_status=league.legacy_model_status,
    )


@dataclass(frozen=True, slots=True)
class ResearchScope:
    """The engine's research processing scope: eligible competitions x markets.

    Built from the dual-provider universe (identity) and the coverage matrix
    (market evidence). Membership is always by TheStatsAPI competition id.
    """

    universe: DualProviderUniverse
    competitions: tuple[CompetitionMarketScope, ...]
    coverage_matrix_path: str

    # ── membership ──────────────────────────────────────────────────────────
    def is_in_research_scope(self, competition_id: Optional[str]) -> bool:
        """True iff the competition is provider-eligible AND has a usable market.

        Note both halves. Provider eligibility alone does not make a competition
        processable, and a usable market in a competition whose identity is not
        resolved is meaningless. Neither half is Pilot-C aware.
        """
        if not competition_id:
            return False
        return competition_id in self._by_id and self._by_id[
            competition_id
        ].has_processable_market

    def is_forecastable(self, competition_id: Optional[str]) -> bool:
        """True iff at least one market can be forecast AND later joined to odds."""
        if not competition_id:
            return False
        scope = self._by_id.get(competition_id)
        return bool(scope and scope.has_forecastable_market)

    def scope_for(self, competition_id: Optional[str]) -> Optional[CompetitionMarketScope]:
        if not competition_id:
            return None
        return self._by_id.get(competition_id)

    def model_markets_for(self, competition_id: Optional[str]) -> tuple[str, ...]:
        """Model market keys this competition may currently be forecast for."""
        scope = self.scope_for(competition_id)
        return scope.processable_model_markets if scope else ()

    def odds_markets_for(self, competition_id: Optional[str]) -> tuple[str, ...]:
        """Odds market keys this competition may currently be captured for."""
        scope = self.scope_for(competition_id)
        return scope.processable_odds_markets if scope else ()

    def label_for(self, competition_id: Optional[str]) -> Optional[str]:
        scope = self.scope_for(competition_id)
        return scope.canonical_name if scope else None

    @property
    def _by_id(self) -> dict[str, CompetitionMarketScope]:
        return {c.competition_id: c for c in self.competitions}

    @property
    def processable_competition_ids(self) -> tuple[str, ...]:
        """Competitions with at least one processable market, sorted."""
        return tuple(
            sorted(c.competition_id for c in self.competitions if c.has_processable_market)
        )

    @property
    def forecastable_competition_ids(self) -> tuple[str, ...]:
        """Competitions with at least one forecastable market, sorted."""
        return tuple(
            sorted(c.competition_id for c in self.competitions if c.has_forecastable_market)
        )

    # ── reporting ───────────────────────────────────────────────────────────
    def market_matrix(self) -> dict[str, dict[str, str]]:
        """``competition_id -> {odds_market: status}`` over every champion market."""
        return {
            c.competition_id: dict(sorted(c.market_eligibility.items()))
            for c in self.competitions
        }

    def market_status_counts(self) -> dict[str, dict[str, int]]:
        """Per-market tally of READY/PARTIAL/UNSUPPORTED/UNKNOWN.

        Every status key is always present with an explicit integer, including
        zero. A status silently absent from this map would be indistinguishable
        from a status that was never evaluated — the exact "zero conceals UNKNOWN"
        failure this report is meant to prevent.
        """
        counts: dict[str, dict[str, int]] = {
            market: {status.value: 0 for status in MarketEligibility}
            for market in CHAMPION_MARKETS
        }
        for comp in self.competitions:
            for market, status in comp.market_eligibility.items():
                if market in counts and status in counts[market]:
                    counts[market][status] += 1
        return counts

    def summary(self) -> dict[str, Any]:
        return {
            "contract": RESEARCH_SCOPE_CONTRACT,
            "coverage_matrix_path": self.coverage_matrix_path,
            "coverage_matrix_present": bool(Path(self.coverage_matrix_path).exists()),
            "registry_leagues_total": len(self.universe.leagues),
            "dual_provider_eligible": len(self.universe.eligible),
            "excluded_leagues": len(self.universe.excluded),
            "league_exclusion_reasons": self.universe.exclusion_summary(),
            "competitions_with_processable_market": len(
                self.processable_competition_ids
            ),
            "competitions_with_forecastable_market": len(
                self.forecastable_competition_ids
            ),
            "market_status_counts": self.market_status_counts(),
            "pilot_c_is_behavioral_input": False,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "summary": self.summary(),
            "competitions": [c.to_dict() for c in self.competitions],
            "excluded_leagues": [lg.to_dict() for lg in self.universe.excluded],
        }


def build_research_scope(
    *,
    registry_path: str | Path = DEFAULT_REGISTRY_PATH,
    coverage_matrix_path: str | Path = DEFAULT_COVERAGE_MATRIX_PATH,
    universe: Optional[DualProviderUniverse] = None,
) -> ResearchScope:
    """Build the research scope: dual-provider eligible competitions x markets.

    Args:
        registry_path: the provider league registry.
        coverage_matrix_path: the persisted coverage matrix supplying market
            evidence. Absent or unreadable means every market is UNKNOWN and
            nothing is processed — fail closed, while the competitions stay
            visible as provider-eligible.
        universe: a pre-built dual-provider universe (tests inject this).

    Returns:
        The :class:`ResearchScope`. One entry per *eligible* competition; excluded
        leagues are carried on ``universe`` so nothing disappears.
    """
    uni = universe or build_dual_provider_universe(registry_path)
    coverage = _load_coverage_rows(coverage_matrix_path)
    competitions = tuple(
        _build_competition_scope(lg, coverage.get(str(lg.thestatsapi_competition_id)))
        for lg in sorted(
            uni.eligible,
            key=lambda l: (l.canonical_name, l.thestatsapi_competition_id or ""),
        )
        if lg.thestatsapi_competition_id
    )
    return ResearchScope(
        universe=uni,
        competitions=competitions,
        coverage_matrix_path=str(coverage_matrix_path),
    )


def market_exclusion_reason_for(
    scope: ResearchScope, competition_id: str, odds_market: str
) -> str:
    """The reason one cell is not processable, or ``NONE`` if it is.

    Used by the coverage report so a per-cell abstention always carries a reason
    instead of appearing as an unexplained absence.
    """
    comp = scope.scope_for(competition_id)
    if comp is None:
        league = scope.universe.league_for(competition_id)
        if league is not None and not league.is_eligible:
            return league.exclusion_reason.value
        return ScopeExclusionReason.IDENTITY_UNRESOLVED.value
    if odds_market in comp.processable_odds_markets:
        return MarketExclusionReason.NONE.value
    return comp.market_exclusions.get(
        odds_market, MarketExclusionReason.PROVIDER_MARKET_UNKNOWN.value
    )
