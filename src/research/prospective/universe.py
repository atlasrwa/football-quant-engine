"""Initial operational universe for prospective live capture.

We do NOT start with every competition. The initial universe is a controlled
set where all four conditions hold, verified against the research corpus:

1. canonical identity mapping is strong (present in the provider registry),
2. the champion supports the relevant markets (goals, corners),
3. TheStatsAPI coverage is good,
4. odds coverage is good.

Selection was made from corpus coverage statistics (goals O/U 2.5 and corners
O/U 9.5 pre-match odds coverage), NOT from any apparent model profitability.

Chosen: the five major European leagues, which show ~100% goals-odds and
94-100% corners-odds coverage in the discovery corpus and have strong canonical
identity mapping and champion support.

Competition ids are the live TheStatsAPI ``comp_*`` ids; only ids we have
verified in the contract examples are hard-coded. Others resolve at runtime via
the identity registry — the universe is a POLICY (league names + optional ids),
not a guarantee that every id is live-valid here (no API key in this env).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class UniverseLeague:
    """One league in the operational universe."""

    corpus_name: str          # name as it appears in the research corpus
    competition_id: Optional[str]  # TheStatsAPI comp id when known, else None
    rationale: str


#: The initial operational universe. comp_3039 = Premier League is the only id
#: confirmed from the live contract examples; others are left None and resolved
#: at runtime via the identity registry (no fabricated ids).
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
    """Corpus league names in the initial universe (for coverage filtering)."""
    return frozenset(u.corpus_name for u in INITIAL_UNIVERSE)


def universe_competition_ids() -> tuple[str, ...]:
    """Known live competition ids in the universe (only verified ids)."""
    return tuple(u.competition_id for u in INITIAL_UNIVERSE if u.competition_id)
