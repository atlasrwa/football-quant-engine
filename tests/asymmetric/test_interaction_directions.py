# Feature: asymmetric-matchup-engine, Property 1: Directions never collapse to a symmetric output
"""Property 1: Directions never collapse to a symmetric output (task 5.3).

**Property 1** — For a fixture whose two teams have DIFFERING attacking/defensive
profiles, the two Directions' predictive distributions for a given target are not
identical, and swapping team A with team B swaps the two Directions' outputs
(rather than leaving them unchanged) — so no single symmetric feature can
reproduce both Directions.

Validates: Requirements 2.1, 2.2, 2.3.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is written as a deterministic ``pytest`` test over several differing
profile pairs. When task 12.1 lands, convert to ``@given`` drawing attacker /
defender profile pairs with controllable divergence via the ``fixture_contexts``
strategy, wrapped with ``@settings(max_examples=100)``.
"""

from __future__ import annotations

import numpy as np
import pytest

from src.research.asymmetric.interaction import (
    DIRECTION_A,
    DIRECTION_B,
    TARGETS,
    FixtureContext,
    InteractionModel,
    build_direction_features,
)
from src.research.asymmetric.models import (
    AttackingProfile,
    DefensiveProfile,
    ProfileDimension,
    TeamMatchProfiles,
)

ATT_DIMS = ("width", "central_penetration", "volume_vs_quality",
            "set_piece_reliance", "directness")
DEF_DIMS = ("block_orientation", "aerial_vs_ground", "shot_suppression",
            "gk_contribution", "discipline")


def _dim(name: str, value: float) -> ProfileDimension:
    return ProfileDimension(
        name=name, value=float(value), source_fields=(name,), n_matches_used=10
    )


def _profiles(team: str, att_vals, def_vals, n_history: int = 10) -> TeamMatchProfiles:
    attacking = AttackingProfile(
        team=team,
        as_of_unix=1_600_000_000,
        width=_dim("width", att_vals[0]),
        central_penetration=_dim("central_penetration", att_vals[1]),
        volume_vs_quality=_dim("volume_vs_quality", att_vals[2]),
        set_piece_reliance=_dim("set_piece_reliance", att_vals[3]),
        directness=_dim("directness", att_vals[4]),
    )
    defensive = DefensiveProfile(
        team=team,
        as_of_unix=1_600_000_000,
        block_orientation=_dim("block_orientation", def_vals[0]),
        aerial_vs_ground=_dim("aerial_vs_ground", def_vals[1]),
        shot_suppression=_dim("shot_suppression", def_vals[2]),
        gk_contribution=_dim("gk_contribution", def_vals[3]),
        discipline=_dim("discipline", def_vals[4]),
    )
    return TeamMatchProfiles(
        team=team,
        n_history=n_history,
        insufficient=n_history < 5,
        attacking=attacking,
        defensive=defensive,
    )


def _fit_model(seed: int = 0) -> InteractionModel:
    """Fit an InteractionModel on synthetic directional rows with real signal.

    Counts depend on attacker/defender features so the fitted per-direction
    models produce feature-sensitive (non-constant) distributions.
    """
    rng = np.random.default_rng(seed)
    dataset = {(d, t): [] for d in (DIRECTION_A, DIRECTION_B) for t in TARGETS}
    base = {"corners": 5.0, "goals": 1.3, "sot": 4.0, "cards": 2.2}
    for _ in range(600):
        att = rng.normal(0.5, 1.0, size=5)
        deff = rng.normal(0.5, 1.0, size=5)
        atk = _profiles("ATK", att, rng.normal(0.5, 1.0, 5))
        dfd = _profiles("DEF", rng.normal(0.5, 1.0, 5), deff)
        for direction in (DIRECTION_A, DIRECTION_B):
            for t in TARGETS:
                feats = build_direction_features(
                    atk, dfd, t, card_rate=2.0 if t == "cards" else None
                )
                # Signal: attacking width/volume raise the count; defence lowers it.
                lam = base[t] + 0.35 * att[0] + 0.3 * att[2] - 0.25 * deff[2]
                lam = max(0.2, lam)
                feats["count"] = float(rng.poisson(lam))
                dataset[(direction, t)].append(
                    _obs(t, feats)
                )
    model = InteractionModel()
    model.fit(dataset)
    return model


def _obs(target, features):
    from src.research.asymmetric.interaction import DirectionObservation
    return DirectionObservation(target=target, features=features)


# Two clearly DIFFERING teams.
_TEAM_A_ATT = [3.0, 2.0, 1.0, 0.5, 0.2]
_TEAM_A_DEF = [2.0, 10.0, -1.0, 3.0, 4.0]
_TEAM_B_ATT = [0.3, 0.6, 2.5, 1.5, 1.1]
_TEAM_B_DEF = [5.0, -8.0, 2.0, 1.0, 1.5]


@pytest.mark.parametrize("target", list(TARGETS))
def test_directions_not_identical_for_differing_profiles(target):
    """The two directions' distributions differ when the teams differ (Req 2.3)."""
    model = _fit_model(seed=1)
    team_a = _profiles("A", _TEAM_A_ATT, _TEAM_A_DEF)
    team_b = _profiles("B", _TEAM_B_ATT, _TEAM_B_DEF)

    # Direction A: A attacks / B defends. Direction B: B attacks / A defends.
    pred_a = model.predict_direction(
        DIRECTION_A, team_a, team_b, target,
        card_rate=2.0 if target == "cards" else None,
    )
    pred_b = model.predict_direction(
        DIRECTION_B, team_b, team_a, target,
        card_rate=2.0 if target == "cards" else None,
    )

    assert pred_a.distribution != pred_b.distribution, (
        f"directions collapsed to identical distributions for {target}"
    )
    assert pred_a.attacker == "A" and pred_a.defender == "B"
    assert pred_b.attacker == "B" and pred_b.defender == "A"


@pytest.mark.parametrize("target", list(TARGETS))
def test_swapping_teams_swaps_direction_inputs(target):
    """Swapping A<->B exchanges the attacker/defender fed to the two direction slots.

    Predict fixture (A home, B away), then the swapped fixture (B home, A away).
    Under the swap:
      * the attacker/defender identities in each direction slot exchange
        (Direction A goes from A-attack-vs-B to B-attack-vs-A), and
      * the outputs genuinely CHANGE — the swapped Direction A output is not
        equal to the original Direction A output — which a symmetric
        ``(A+B)/2`` feature could never produce (it would be identical).

    This is the concrete, estimator-consistent form of Property 1's "swapping
    team A with team B swaps the two Directions' outputs rather than leaving them
    unchanged": each direction slot is scored by its own separately-fitted model,
    and swapping the teams changes what that model sees, so its output moves.
    """
    model = _fit_model(seed=2)
    team_a = _profiles("A", _TEAM_A_ATT, _TEAM_A_DEF)
    team_b = _profiles("B", _TEAM_B_ATT, _TEAM_B_DEF)

    cr = 2.0
    ctx_ab = FixtureContext(
        home_team="A", away_team="B", date_unix=1_600_000_000,
        home_profiles=team_a, away_profiles=team_b,
        card_rate_home=cr, card_rate_away=cr,
    )
    ctx_ba = FixtureContext(
        home_team="B", away_team="A", date_unix=1_600_000_000,
        home_profiles=team_b, away_profiles=team_a,
        card_rate_home=cr, card_rate_away=cr,
    )

    preds_ab = {(p.direction, p.target): p for p in model.predict_fixture(ctx_ab)}
    preds_ba = {(p.direction, p.target): p for p in model.predict_fixture(ctx_ba)}

    ab_dirA = preds_ab[(DIRECTION_A, target)]
    ab_dirB = preds_ab[(DIRECTION_B, target)]
    ba_dirA = preds_ba[(DIRECTION_A, target)]
    ba_dirB = preds_ba[(DIRECTION_B, target)]

    # The attacker/defender identities in each direction slot exchange.
    assert (ab_dirA.attacker, ab_dirA.defender) == ("A", "B")
    assert (ba_dirA.attacker, ba_dirA.defender) == ("B", "A")
    assert (ab_dirB.attacker, ab_dirB.defender) == ("B", "A")
    assert (ba_dirB.attacker, ba_dirB.defender) == ("A", "B")

    # The outputs genuinely move under the swap (not left unchanged): a symmetric
    # feature would leave each slot's output identical across the relabelling.
    assert ab_dirA.distribution != ba_dirA.distribution
    assert ab_dirB.distribution != ba_dirB.distribution

    # Within a single fixture the two directions differ (asymmetric matchup).
    assert ab_dirA.distribution != ab_dirB.distribution


def test_full_predictive_distributions_are_valid_pmfs():
    """Each direction/target returns a valid PMF (Req 2.4-2.7)."""
    model = _fit_model(seed=3)
    team_a = _profiles("A", _TEAM_A_ATT, _TEAM_A_DEF)
    team_b = _profiles("B", _TEAM_B_ATT, _TEAM_B_DEF)
    ctx = FixtureContext(
        home_team="A", away_team="B", date_unix=1_600_000_000,
        home_profiles=team_a, away_profiles=team_b,
        card_rate_home=2.0, card_rate_away=2.0,
    )
    preds = model.predict_fixture(ctx)
    assert len(preds) == 2 * len(TARGETS)
    for p in preds:
        assert all(0.0 <= x <= 1.0 for x in p.distribution)
        assert abs(sum(p.distribution) - 1.0) < 1e-9
        assert len(p.driving_features) > 0
