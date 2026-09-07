"""Tests for the hierarchical count models and the coherence they guarantee.

The monotonicity test is the reason this architecture exists. Three independent
elastic nets at 8.5, 9.5 and 10.5 could produce ``P(over 9.5) > P(over 8.5)``,
which is impossible. One count distribution cannot. That property is asserted here
across the full declared line set rather than trusted.
"""

from __future__ import annotations

import math
import random

import pytest

from src.research.models.hierarchical_market_model import (
    NEGATIVE_BINOMIAL,
    POISSON,
    HierarchicalConfig,
    HierarchicalCountModel,
    MatchCountDistribution,
    NotFittedError,
    SideCountDistribution,
    SideRow,
    _gauss_hermite_mixture,
)
from src.research.models.market_family import (
    ALL_FAMILY_NAMES,
    default_market_families,
    family_by_name,
)

SEASON_EARLY = "season-1"
SEASON_LATE = "season-2"


def _synthetic_rows(
    family,
    *,
    n_leagues: int = 3,
    teams_per_league: int = 10,
    matches_per_team: int = 12,
    seed: int = 7,
    overdispersed: bool = True,
) -> list[SideRow]:
    """Side rows with a real league effect, real team effects, and two seasons."""
    rng = random.Random(seed)
    rows: list[SideRow] = []
    kickoff = 1_600_000_000
    for league_index in range(n_leagues):
        league = f"league-{league_index}"
        league_effect = 0.25 * (league_index - n_leagues / 2)
        attack = {
            f"t{league_index}-{team}": rng.gauss(0.0, 0.22)
            for team in range(teams_per_league)
        }
        for season in (SEASON_EARLY, SEASON_LATE):
            for _ in range(matches_per_team * teams_per_league // 2):
                home, away = rng.sample(sorted(attack), 2)
                kickoff += 3600
                for counting, opposing, is_home in (
                    (home, away, True),
                    (away, home, False),
                ):
                    base = 1.5 + league_effect + attack[counting] - 0.4 * attack[opposing]
                    base += 0.08 if is_home else 0.0
                    features = {
                        name: rng.gauss(0.0, 1.0) for name in family.feature_names
                    }
                    features["is_home"] = 1.0 if is_home else 0.0
                    features["support_n"] = 5.0
                    signal = 0.12 * features[family.feature_names[0]]
                    mean = math.exp(base + signal)
                    if overdispersed:
                        # Gamma-Poisson mixture: genuinely negative binomial.
                        mean *= rng.gammavariate(4.0, 0.25)
                    count = float(_poisson_draw(rng, mean))
                    rows.append(
                        SideRow(
                            fixture_id=f"{league}-{kickoff}",
                            league=league,
                            season=season,
                            kickoff_unix=kickoff,
                            counting_team=counting,
                            opposing_team=opposing,
                            is_home=is_home,
                            features=features,
                            count=count,
                        )
                    )
    return rows


def _poisson_draw(rng: random.Random, mean: float) -> int:
    """Knuth's algorithm; adequate for the small means used in these tests."""
    mean = min(mean, 60.0)
    limit = math.exp(-mean)
    product = rng.random()
    count = 0
    while product > limit:
        count += 1
        product *= rng.random()
    return count


def _fit(family, **kwargs) -> HierarchicalCountModel:
    rows = _synthetic_rows(family, **kwargs)
    model = HierarchicalCountModel(family, HierarchicalConfig(min_global_observations=40))
    model.fit(rows)
    return model


def _row(model, league: str, counting: str, opposing: str, *, is_home: bool) -> SideRow:
    layer = model.global_layer
    features = dict(layer.feature_means)
    features["is_home"] = 1.0 if is_home else 0.0
    return SideRow(
        fixture_id="fixture",
        league=league,
        season=SEASON_LATE,
        kickoff_unix=1_700_000_000,
        counting_team=counting,
        opposing_team=opposing,
        is_home=is_home,
        features=features,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Monotonicity: the defect this architecture exists to prevent
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("family_name", ALL_FAMILY_NAMES)
def test_line_ladder_is_monotone(family_name: str) -> None:
    """P(over a) >= P(over b) for every a < b, on every family's full line set."""
    family = family_by_name(family_name)
    model = _fit(family)
    teams = sorted({key[1] for key in model.attack_effects})
    checked = 0
    for index in range(0, min(len(teams) - 1, 8)):
        home, away = teams[index], teams[index + 1]
        league = next(key[0] for key in model.attack_effects if key[1] == home)
        probabilities = model.line_probabilities(
            _row(model, league, home, away, is_home=True),
            _row(model, league, away, home, is_home=False),
        )
        ordered = [probabilities[line] for line in family.lines]
        for lower_line, higher_line, lower_p, higher_p in zip(
            family.lines, family.lines[1:], ordered, ordered[1:]
        ):
            assert higher_p <= lower_p + 1e-12, (
                f"{family_name}: P(over {higher_line}) = {higher_p} exceeded "
                f"P(over {lower_line}) = {lower_p}; line probabilities are incoherent"
            )
        checked += 1
    assert checked > 0


def test_corners_ladder_matches_the_declared_line_set() -> None:
    """The corners ladder is exactly the one the prompt requires, and ordered."""
    family = family_by_name("corners")
    assert family.lines == (7.5, 8.5, 9.5, 10.5)
    model = _fit(family)
    teams = sorted({key[1] for key in model.attack_effects})
    league = next(key[0] for key in model.attack_effects if key[1] == teams[0])
    probabilities = model.line_probabilities(
        _row(model, league, teams[0], teams[1], is_home=True),
        _row(model, league, teams[1], teams[0], is_home=False),
    )
    assert (
        probabilities[7.5]
        >= probabilities[8.5]
        >= probabilities[9.5]
        >= probabilities[10.5]
    )


def test_monotonicity_survives_the_uncertainty_mixture() -> None:
    """A mixture of survival functions is still a survival function."""
    mixture = _gauss_hermite_mixture(math.log(4.0), 0.25, NEGATIVE_BINOMIAL, 0.3)
    distribution = MatchCountDistribution(home=mixture, away=mixture)
    values = [distribution.p_over(line) for line in (0.5, 1.5, 2.5, 3.5, 7.5, 12.5)]
    assert all(
        later <= earlier + 1e-12 for earlier, later in zip(values, values[1:])
    )


def test_total_pmf_is_a_distribution() -> None:
    side = _gauss_hermite_mixture(math.log(1.4), 0.0, POISSON, 0.0)
    distribution = MatchCountDistribution(home=side, away=side)
    assert math.isclose(sum(distribution.total_pmf), 1.0, abs_tol=1e-9)
    assert math.isclose(distribution.expected_total, 2.8, rel_tol=0.05)


# ─────────────────────────────────────────────────────────────────────────────
# Dispersion: verified, not assumed
# ─────────────────────────────────────────────────────────────────────────────
def test_overdispersed_counts_select_the_negative_binomial() -> None:
    model = _fit(family_by_name("corners"), overdispersed=True)
    assert model.distribution == NEGATIVE_BINOMIAL
    assert model.global_layer.dispersion > 0.0
    assert model.global_layer.residual_variance_mean_ratio > 1.10


def test_equidispersed_counts_select_poisson() -> None:
    """A genuinely Poisson process must not be given a spurious dispersion."""
    model = _fit(family_by_name("goals"), overdispersed=False)
    assert model.distribution == POISSON
    assert model.global_layer.dispersion == 0.0


def test_dispersion_is_selected_on_residual_not_marginal_variance() -> None:
    """Both ratios are reported, and the residual one is the smaller."""
    model = _fit(family_by_name("corners"), overdispersed=False)
    layer = model.global_layer
    assert layer.marginal_variance_mean_ratio > 0.0
    assert layer.residual_variance_mean_ratio <= layer.marginal_variance_mean_ratio + 1e-9


# ─────────────────────────────────────────────────────────────────────────────
# Partial pooling
# ─────────────────────────────────────────────────────────────────────────────
def test_thin_team_shrinks_harder_than_a_rich_one() -> None:
    """The whole point: less evidence means an estimate closer to the prior."""
    family = family_by_name("corners")
    rows = _synthetic_rows(family)
    thin_league = "league-0"
    thin_team = "thin-team"
    # Two side rows only: a team with almost no record.
    rows.extend(
        SideRow(
            fixture_id=f"thin-{index}",
            league=thin_league,
            season=SEASON_LATE,
            kickoff_unix=1_700_000_000 + index,
            counting_team=thin_team,
            opposing_team="t0-1",
            is_home=True,
            features={name: 0.0 for name in family.feature_names},
            count=9.0,
        )
        for index in range(2)
    )
    model = HierarchicalCountModel(family, HierarchicalConfig(min_global_observations=40))
    model.fit(rows)

    thin = model.attack_effects[(thin_league, thin_team)]
    rich = [
        effect
        for key, effect in model.attack_effects.items()
        if key[1] != thin_team and effect.n_observations >= 15
    ]
    assert rich, "expected at least one well-observed team"
    assert thin.shrinkage_weight < min(effect.shrinkage_weight for effect in rich)
    assert thin.sampling_variance > max(effect.sampling_variance for effect in rich)
    # Shrunk toward the prior, so the posterior is smaller in size than the raw.
    assert abs(thin.posterior) <= abs(thin.raw) + 1e-9


def test_every_league_gets_an_estimate_including_thin_ones() -> None:
    """A league too thin to fit alone is pooled, not excluded."""
    family = family_by_name("cards")
    rows = _synthetic_rows(family, n_leagues=3)
    thin_rows = [
        SideRow(
            fixture_id=f"thin-league-{index}",
            league="thin-league",
            season=SEASON_LATE,
            kickoff_unix=1_700_500_000 + index,
            counting_team=f"x{index % 4}",
            opposing_team=f"y{index % 3}",
            is_home=index % 2 == 0,
            features={name: 0.0 for name in family.feature_names},
            count=float(2 + index % 3),
        )
        for index in range(12)
    ]
    model = HierarchicalCountModel(family, HierarchicalConfig(min_global_observations=40))
    model.fit(rows + thin_rows)

    assert "thin-league" in model.league_effects
    effect = model.league_effects["thin-league"]
    rich = model.league_effects["league-0"]
    assert effect.shrinkage_weight <= rich.shrinkage_weight
    # And it can be predicted for, with wider uncertainty than a rich league.
    thin_row = _row(model, "thin-league", "x0", "y0", is_home=True)
    rich_row = _row(model, "league-0", "t0-0", "t0-1", is_home=True)
    thin_variance = model._side_terms(thin_row)["log_mean_variance"]
    rich_variance = model._side_terms(rich_row)["log_mean_variance"]
    assert thin_variance >= rich_variance


def test_thin_evidence_widens_the_published_interval() -> None:
    """Wide uncertainty must reach the output, not stop at a diagnostic."""
    family = family_by_name("corners")
    model = _fit(family)
    league = "league-0"
    known = sorted(key[1] for key in model.attack_effects if key[0] == league)[:2]
    known_distribution = model.predict_match(
        _row(model, league, known[0], known[1], is_home=True),
        _row(model, league, known[1], known[0], is_home=False),
    )
    unknown_distribution = model.predict_match(
        _row(model, league, "never-seen-a", "never-seen-b", is_home=True),
        _row(model, league, "never-seen-b", "never-seen-a", is_home=False),
    )
    known_low, known_high = known_distribution.total_interval(0.80)
    unknown_low, unknown_high = unknown_distribution.total_interval(0.80)
    assert (unknown_high - unknown_low) >= (known_high - known_low)


def test_league_slope_deviations_are_strongly_shrunk() -> None:
    """No league slope may take more than the declared share of its deviation."""
    family = family_by_name("corners")
    config = HierarchicalConfig(min_global_observations=40, slope_shrinkage_cap=0.25)
    rows = _synthetic_rows(family)
    model = HierarchicalCountModel(family, config)
    model.fit(rows)
    assert model.league_slopes, "expected league-varying slopes to be estimated"
    for effect in model.league_slopes.values():
        assert effect.shrinkage_weight <= 0.25 + 1e-12
        assert abs(effect.posterior) <= abs(effect.raw) + 1e-12


def test_only_declared_slopes_vary_by_league() -> None:
    family = family_by_name("corners")
    model = _fit(family)
    varying = set(family.features.league_varying)
    assert len(varying) <= 2, "the league-varying slope set must stay small"
    assert {key[1] for key in model.league_slopes} <= varying


# ─────────────────────────────────────────────────────────────────────────────
# Prior season as a decaying prior, never as window backfill
# ─────────────────────────────────────────────────────────────────────────────
def test_prior_season_weight_decays_as_current_matches_accumulate() -> None:
    config = HierarchicalConfig(prior_season_half_life_matches=6.0)
    assert config.prior_season_decay(0) == pytest.approx(1.0)
    assert config.prior_season_decay(6) == pytest.approx(0.5)
    assert config.prior_season_decay(12) == pytest.approx(0.25)
    decays = [config.prior_season_decay(n) for n in range(0, 40)]
    assert all(later <= earlier for earlier, later in zip(decays, decays[1:]))
    assert decays[-1] < 0.02


def test_prior_season_contribution_is_recorded_per_team() -> None:
    """A forecast carrying prior-season information must say so."""
    model = _fit(family_by_name("corners"))
    effects = list(model.attack_effects.values())
    assert any(effect.prior_season_decay > 0.0 for effect in effects)
    for effect in effects:
        payload = effect.to_dict()
        assert "prior_season_decay" in payload
        assert "prior_season_contribution" in payload
        assert "shrinkage_weight" in payload
        assert "n_observations" in payload


def test_posterior_is_the_stated_convex_combination() -> None:
    """posterior == w * raw + (1 - w) * decayed prior mean, exactly."""
    model = _fit(family_by_name("corners"))
    for effect in model.attack_effects.values():
        expected = (
            effect.shrinkage_weight * effect.raw
            + (1.0 - effect.shrinkage_weight)
            * effect.prior_season_decay
            * effect.prior_mean
        )
        assert effect.posterior == pytest.approx(expected, abs=1e-12)


# ─────────────────────────────────────────────────────────────────────────────
# BTTS from the bivariate structure
# ─────────────────────────────────────────────────────────────────────────────
def test_btts_is_derived_from_the_two_side_distributions() -> None:
    model = _fit(family_by_name("goals"), overdispersed=False)
    league = "league-0"
    teams = sorted(key[1] for key in model.attack_effects if key[0] == league)[:2]
    home_row = _row(model, league, teams[0], teams[1], is_home=True)
    away_row = _row(model, league, teams[1], teams[0], is_home=False)
    distribution = model.predict_match(home_row, away_row)
    expected = (
        distribution.home.p_at_least_one() * distribution.away.p_at_least_one()
    )
    assert distribution.p_both_score() == pytest.approx(expected, abs=1e-12)
    assert 0.0 <= distribution.p_both_score() <= 1.0


def test_btts_cannot_contradict_the_goals_lines() -> None:
    """Both teams scoring implies at least two goals, so BTTS <= P(over 1.5)."""
    model = _fit(family_by_name("goals"), overdispersed=False)
    league = "league-0"
    teams = sorted(key[1] for key in model.attack_effects if key[0] == league)[:2]
    distribution = model.predict_match(
        _row(model, league, teams[0], teams[1], is_home=True),
        _row(model, league, teams[1], teams[0], is_home=False),
    )
    assert distribution.p_both_score() <= distribution.p_over(1.5) + 1e-9


def test_only_the_full_match_goals_family_derives_btts() -> None:
    assert family_by_name("goals").derives_btts is True
    for name in ALL_FAMILY_NAMES:
        if name != "goals":
            assert family_by_name(name).derives_btts is False


# ─────────────────────────────────────────────────────────────────────────────
# Guards
# ─────────────────────────────────────────────────────────────────────────────
def test_prediction_before_fit_is_refused() -> None:
    family = family_by_name("corners")
    model = HierarchicalCountModel(family)
    row = SideRow(
        fixture_id="f",
        league="l",
        season="s",
        kickoff_unix=1,
        counting_team="a",
        opposing_team="b",
        is_home=True,
        features={name: 0.0 for name in family.feature_names},
    )
    with pytest.raises(NotFittedError):
        model.predict_side(row)


def test_fit_refuses_too_few_observations() -> None:
    family = family_by_name("corners")
    model = HierarchicalCountModel(family)
    with pytest.raises(ValueError, match="below the minimum"):
        model.fit([])


def test_side_distribution_rejects_unresolved_distribution() -> None:
    with pytest.raises(ValueError, match="unsupported distribution"):
        SideCountDistribution(mean=1.0, distribution="auto")


def test_negative_binomial_requires_positive_dispersion() -> None:
    with pytest.raises(ValueError, match="dispersion"):
        SideCountDistribution(mean=1.0, distribution=NEGATIVE_BINOMIAL, dispersion=0.0)


def test_fit_report_exposes_shrinkage_and_dispersion() -> None:
    model = _fit(family_by_name("corners"))
    report = model.fit_report()
    for key in (
        "family",
        "lines",
        "global",
        "median_league_shrinkage_weight",
        "median_team_shrinkage_weight",
        "league_slope_shrinkage_cap",
        "prior_season_half_life_matches",
        "league_residual_dispersion",
        "unavailable_mechanisms",
    ):
        assert key in report
    assert report["n_team_attack_states"] > 0
    assert report["n_team_concede_states"] > 0
