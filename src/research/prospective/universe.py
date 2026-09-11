"""DEPRECATED hard-coded operational universe. Retained for provenance only.

.. deprecated::
    Superseded by the dual-provider intersection rule in
    :mod:`src.research.scope.dual_provider`, surfaced operationally through
    :func:`src.research.prospective.cli.default_competition_ids`.

WHY IT WAS REMOVED FROM THE EXECUTION PATH
==========================================
:data:`INITIAL_UNIVERSE` declared five leagues but carried a live TheStatsAPI
competition id for only one of them (``comp_3039``, the Premier League); the other
four were ``None`` and were meant to "resolve at runtime". They never did.
:func:`universe_competition_ids` filters to ids that are present, so the function
returned a **single** competition id, and any caller that fell back to it silently
operated on one league while appearing to declare five.

That fallback was reachable from ``ProspectiveCollector.discover_upcoming``. On the
scheduled path ``capture_due`` always passed explicit ids, so the collapse was
invisible in production — which is precisely what made it dangerous.

The replacement derives the universe from provider evidence: a competition is in
scope when FootyStats and TheStatsAPI both support it and its identity maps
deterministically. A curated list cannot go stale into a one-league fallback,
because there is no list.

WHAT IS PRESERVED
=================
The corpus-name helper is still used by coverage tooling that reports on the
original five-league selection, and the rationale strings document why those
leagues were chosen (odds coverage in the discovery corpus, never apparent model
profitability). Nothing here gates the engine's reach any more.
"""

from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Optional

#: Marker so the deprecation is greppable and testable, not just documented.
UNIVERSE_POLICY_DEPRECATED = True

#: What replaced it, named so a reader of this module is never left guessing.
UNIVERSE_POLICY_SUCCESSOR = "src.research.scope.dual_provider.build_dual_provider_universe"


@dataclass(frozen=True)
class UniverseLeague:
    """One league in the legacy hard-coded universe (provenance only)."""

    corpus_name: str          # name as it appears in the research corpus
    competition_id: Optional[str]  # TheStatsAPI comp id when known, else None
    rationale: str


#: DEPRECATED. The original five-league selection, kept so historical coverage
#: reports remain interpretable. Note that four of the five carry no competition
#: id — the reason this could never function as an operational universe.
INITIAL_UNIVERSE: tuple[UniverseLeague, ...] = (
    UniverseLeague(
        "England Premier League", "comp_3039",
        "100% goals-odds, 100% corners-odds; strong identity; champion supports.",
    ),
    UniverseLeague(
        "Spain La Liga", None,
        "100% goals-odds, 100% corners-odds in corpus; strong identity.",
    ),
    UniverseLeague(
        "Italy Serie A", None,
        "100% goals-odds, ~92% corners-odds; strong identity.",
    ),
    UniverseLeague(
        "Germany Bundesliga", None,
        "100% goals-odds, ~94% corners-odds; strong identity.",
    ),
    UniverseLeague(
        "France Ligue 1", None,
        "100% goals-odds, 100% corners-odds; strong identity.",
    ),
)


def universe_corpus_names() -> frozenset[str]:
    """Corpus league names in the legacy universe (historical reporting only)."""
    return frozenset(u.corpus_name for u in INITIAL_UNIVERSE)


def universe_competition_ids() -> tuple[str, ...]:
    """DEPRECATED. Do not use to scope discovery, capture, or forecasting.

    Returns only ``("comp_3039",)`` because the other four legacy entries have no
    competition id. Emits a :class:`DeprecationWarning` so any remaining caller
    surfaces in test output rather than quietly narrowing the engine to one league.

    Use :func:`src.research.prospective.cli.default_competition_ids` instead.
    """
    warnings.warn(
        "universe_competition_ids() is deprecated and returns a single competition "
        "id, which silently collapses the engine to one league. Use "
        "src.research.prospective.cli.default_competition_ids(), backed by the "
        f"dual-provider intersection rule in {UNIVERSE_POLICY_SUCCESSOR}.",
        DeprecationWarning,
        stacklevel=2,
    )
    return tuple(u.competition_id for u in INITIAL_UNIVERSE if u.competition_id)
