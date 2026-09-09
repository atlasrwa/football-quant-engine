"""Canonical field definitions for provider comparison.

Only concepts that are GENUINELY the same measurement across both providers are
compared. Fields are NOT compared merely because their names look similar.

Each ConceptField declares:
- concept: canonical name used in the comparison
- fs_home/fs_away: FootyStats raw per-team keys (corpus schema)
- tsa_group/tsa_stat: TheStatsAPI /stats path (overview.<stat>.all.{home,away})
- kind: 'count' or 'float'
- semantic_note: why the two are considered the same measurement (or caveats)

Overlapping, safely-comparable concepts (present in both providers):
    total_goals, total_corners, total_cards, shots, shots_on_target,
    xg, possession.

Deliberately NOT treated as overlapping:
- dangerous_attacks: FootyStats provides team_a/b_dangerous_attacks, but
  TheStatsAPI has no equivalent 'dangerous attacks' concept in the /stats
  overview. Comparing them would be a semantic mismatch, so it is excluded from
  the head-to-head and only ever a FootyStats-only (new-feature) input.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class ConceptField:
    concept: str
    kind: str  # 'count' | 'float'
    fs_home: Optional[str]
    fs_away: Optional[str]
    tsa_group: Optional[str]
    tsa_stat: Optional[str]
    semantic_note: str
    # For totals derived from home+away, the per-side keys above are summed.


# Overlapping concepts measured the same way by both providers.
OVERLAPPING_CONCEPTS: list[ConceptField] = [
    ConceptField(
        concept="total_goals", kind="count",
        fs_home="homeGoalCount", fs_away="awayGoalCount",
        tsa_group="__score__", tsa_stat="goals",
        semantic_note="Full-time goals; validated by 100% score agreement on the join.",
    ),
    ConceptField(
        concept="total_corners", kind="count",
        fs_home="team_a_corners", fs_away="team_b_corners",
        tsa_group="overview", tsa_stat="corner_kicks",
        semantic_note="Corner kicks, full match, both sides summed.",
    ),
    ConceptField(
        concept="total_cards", kind="count",
        fs_home=None, fs_away=None,  # special: yellow+red both sides
        tsa_group="overview", tsa_stat="__cards__",
        semantic_note="Yellow+red cards, both sides. Reds null on TSA => component absent, not 0.",
    ),
    ConceptField(
        concept="shots", kind="count",
        fs_home="team_a_shots", fs_away="team_b_shots",
        tsa_group="overview", tsa_stat="total_shots",
        semantic_note="Total shots (all), both sides summed.",
    ),
    ConceptField(
        concept="shots_on_target", kind="count",
        fs_home="team_a_shotsOnTarget", fs_away="team_b_shotsOnTarget",
        tsa_group="overview", tsa_stat="shots_on_target",
        semantic_note="Shots on target (all), both sides summed.",
    ),
    ConceptField(
        concept="xg", kind="float",
        fs_home="team_a_xg", fs_away="team_b_xg",
        tsa_group="overview", tsa_stat="expected_goals",
        semantic_note="Expected goals (all). Provider xG models differ; treated as same concept, different estimator.",
    ),
    ConceptField(
        concept="possession", kind="float",
        fs_home="team_a_possession", fs_away="team_b_possession",
        tsa_group="overview", tsa_stat="ball_possession",
        semantic_note="Ball possession %, home side (away = 100-home). Compared on home side only.",
    ),
]

CONCEPTS_BY_NAME = {c.concept: c for c in OVERLAPPING_CONCEPTS}
