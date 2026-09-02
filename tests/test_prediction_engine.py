"""Unit tests for the calibrated prediction engine (src/research/prediction_engine).

Covers the validated-scope registry, calibration metrics (ECE/Brier/BSS + the
minimum-sample gate + base-rate-collapse), w5/w10 window computability and
selection, directional calls, the multi-market fixture readout, and the public
reliability report. These lock in the honesty-critical behaviour: no calibration
figure below the sample gate, collapse is flagged not celebrated, goals/BTTS are
labelled no-skill, and cards is excluded in the Championship.
"""
import math
import random

import pytest

from src.research.asymmetric.derived import DerivedOutcomeCombiner
from src.research.asymmetric.models import DirectionPrediction, FixturePrediction
from src.research.data_source import ResearchMatch
from src.research.prediction_engine import (
    MarketStatus,
    base_rate_collapse,
    brier_skill_score,
    build_fixture_readout,
    build_reliability_report,
    calibration_report,
    directional_call,
    directional_probabilities,
    honest_framing_lines,
    market_status,
)
# Windows are an offline computability/analysis utility, deliberately NOT part of
# the public prediction-engine surface (not wired into the prediction path).
from src.research.prediction_engine.windows import (
    build_window_features,
    field_window_computability,
    select_window,
)
from src.research.prediction_engine.scope import is_championship, directional_status, NO_SKILL_LABEL

_DIRECTION_A = "A_attack_vs_B_defence"
_DIRECTION_B = "B_attack_vs_A_defence"


def _poisson_pmf(mean: float, n: int = 15) -> tuple[float, ...]:
    ps = [math.exp(-mean) * mean**k / math.factorial(k) for k in range(n)]
    s = sum(ps)
    return tuple(p / s for p in ps)


# ── scope ────────────────────────────────────────────────────────────────────

def test_corners_validated_everywhere():
    assert market_status("corners").status is MarketStatus.VALIDATED
    assert market_status("corners", "England Championship").status is MarketStatus.VALIDATED


def test_cards_validated_except_championship():
    # Cards remains validated in leagues NOT re-tested by the family-transfer study
    # (the pooled 25-league finding stands there). The three family-transfer top
    # flights (EPL, La Liga, Ligue 1) were re-tested within-league and did NOT confirm
    # skill, so they are downgraded to NO_DEMONSTRATED_SKILL (unvalidated), and the
    # Championship remains EXCLUDED (persistence confirmed absent).
    assert market_status("cards", "Germany Bundesliga").status is MarketStatus.VALIDATED
    assert market_status("cards", "England Premier League").status is MarketStatus.NO_DEMONSTRATED_SKILL
    for champ in ("England Championship", "comp_8321", "champ", "champ_2024"):
        assert market_status("cards", champ).status is MarketStatus.EXCLUDED


def test_family_transfer_new_top_flights_unvalidated():
    # EPL / La Liga / Ligue 1 corners+cards were re-tested within-league (2-season
    # walk-forward, BSS-vs-naive, BH family of 6) and did NOT demonstrate skill.
    for league in ("England Premier League", "La Liga", "Ligue 1",
                   "comp_3039", "comp_8814", "comp_0256"):
        for market in ("corners", "cards"):
            assert market_status(market, league).status is MarketStatus.NO_DEMONSTRATED_SKILL, (market, league)
    # second-tier partners unchanged: La Liga 2 cards still validated; Ligue 2 too.
    assert market_status("cards", "La Liga 2").status is MarketStatus.VALIDATED
    assert market_status("cards", "Ligue 2").status is MarketStatus.VALIDATED


def test_goals_and_btts_no_demonstrated_skill():
    assert market_status("goals").status is MarketStatus.NO_DEMONSTRATED_SKILL
    assert market_status("btts").status is MarketStatus.NO_DEMONSTRATED_SKILL


def test_is_championship_guards_against_champions_league():
    assert is_championship("England Championship")
    assert not is_championship("UEFA Champions League")
    assert not is_championship("Champions League")
    assert not is_championship(None)


def test_unknown_market_raises():
    with pytest.raises(ValueError):
        market_status("offsides")


def test_honest_framing_has_all_five_statements():
    lines = honest_framing_lines()
    assert len(lines) == 5
    joined = " ".join(lines).lower()
    assert "not betting advice" in joined
    assert "not been shown to beat" in joined
    assert "primary claim" in joined and "calibrated probabilities" in joined
    assert "directional calls" in joined
    assert "no stake" in joined or "no staking" in joined or "staking guidance" in joined


# ── calibration metrics ──────────────────────────────────────────────────────

def test_minimum_sample_gate_blocks_small_samples():
    r = random.Random(0)
    preds = [r.random() for _ in range(50)]
    outs = [r.random() < p for p in preds]
    rep = calibration_report("corners", preds, outs)
    assert not rep.gate_met
    assert "insufficient settled predictions" in rep.gate_notice
    assert rep.calibration is None


def test_gate_met_produces_calibration_and_bss():
    r = random.Random(1)
    preds = [min(0.97, max(0.03, r.betavariate(2, 2))) for _ in range(250)]
    outs = [r.random() < p for p in preds]
    rep = calibration_report("corners", preds, outs)
    assert rep.gate_met and rep.publishable
    assert rep.calibration is not None and rep.calibration.ece is not None
    assert rep.bss is not None


def test_base_rate_collapse_detected():
    coll = base_rate_collapse([0.5] * 100)
    assert coll.collapsed
    not_coll = base_rate_collapse([0.1, 0.5, 0.9] * 40)
    assert not not_coll.collapsed


def test_bss_positive_for_skilful_predictions():
    # Perfectly-informed predictions should beat the base rate.
    outcomes = [True, False] * 100
    preds = [0.99 if y else 0.01 for y in outcomes]
    res = brier_skill_score(preds, outcomes)
    assert res.bss is not None and res.bss > 0.9
    assert res.has_skill


def test_bss_none_when_outcomes_all_identical():
    res = brier_skill_score([0.5] * 10, [True] * 10)
    assert res.bss is None  # naive base rate is a perfect constant predictor


# ── windows ──────────────────────────────────────────────────────────────────

def _synthetic_matches(n=120, rich_share=0.3, seed=2):
    r = random.Random(seed)
    teams = [f"T{i}" for i in range(8)]
    out = []
    t = 1_600_000_000
    for i in range(n):
        h, a = r.sample(teams, 2)
        rich = r.random() < rich_share
        out.append(ResearchMatch(
            match_id=i, date_unix=t + i * 86400, league_id=42, season="2024",
            home_team=h, away_team=a,
            home_goals=r.randint(0, 4), away_goals=r.randint(0, 3),
            corners_home=r.randint(2, 9), corners_away=r.randint(2, 8),
            shots_on_target_home=r.randint(1, 8), shots_on_target_away=r.randint(1, 7),
            yellow_cards_home=r.randint(0, 4), yellow_cards_away=r.randint(0, 5),
            red_cards_home=0, red_cards_away=0,
            tackles_home=(r.randint(10, 25) if rich else None),
            tackles_away=(r.randint(10, 25) if rich else None),
            goals_prevented_home=None, goals_prevented_away=None,
        ))
    return out


def test_window_features_are_look_ahead_free_and_dual_window():
    matches = _synthetic_matches()
    rows = build_window_features(matches)
    assert len(rows) == 2 * len(matches)
    # a late row has both w5 and w10 broad features
    late = [rw for rw in rows if rw.n_prior >= 12][-1]
    assert any(k.endswith("_w5") for k in late.features)
    assert any(k.endswith("_w10") for k in late.features)


def test_goals_prevented_never_a_feature():
    rows = build_window_features(_synthetic_matches())
    assert not any("goals_prevented" in k for rw in rows for k in rw.features)


def test_thin_rich_field_excluded_not_zero_filled():
    comp = field_window_computability(_synthetic_matches(rich_share=0.3), league_id=42)
    tackles = [c for c in comp if c.field_name == "tackles"]
    assert tackles and all(not c.computable for c in tackles)
    corners = [c for c in comp if c.field_name == "corners"]
    assert corners and all(c.computable for c in corners)


def test_select_window_reports_dominant_window():
    sel = select_window("cards", {"yellow_cards_w5": 0.8, "yellow_cards_w10": 0.1})
    assert sel.selected_window == 5
    sel2 = select_window("corners", {"corners_w10": 0.9, "corners_w5": 0.15})
    assert sel2.selected_window == 10


# ── directional calls ────────────────────────────────────────────────────────

def test_directional_probabilities_sum_to_one():
    a = _poisson_pmf(6.0)
    b = _poisson_pmf(3.0)
    pa, pb, pt = directional_probabilities(a, b)
    assert abs(pa + pb + pt - 1.0) < 1e-9
    assert pa > pb  # A has the higher mean


def test_directional_call_names_the_stronger_side():
    call = directional_call("corners", _poisson_pmf(6.0), _poisson_pmf(3.0))
    assert call.called_side == "home"
    assert "home takes more than away" in call.statement()


# ── fixture readout ──────────────────────────────────────────────────────────

def _fixture():
    dirs = []
    for tgt, ha, aw in [("corners", 6.0, 3.5), ("cards", 1.8, 2.4),
                        ("goals", 1.6, 1.1), ("sot", 5.0, 3.8)]:
        dirs.append(DirectionPrediction(
            direction=_DIRECTION_A, attacker="Home FC", defender="Away FC",
            target=tgt, distribution=_poisson_pmf(ha), expected_value=ha,
            driving_features=(f"att.{tgt}_w10",)))
        dirs.append(DirectionPrediction(
            direction=_DIRECTION_B, attacker="Away FC", defender="Home FC",
            target=tgt, distribution=_poisson_pmf(aw), expected_value=aw,
            driving_features=(f"att.{tgt}_w5",)))
    derived = DerivedOutcomeCombiner().combine(dirs)
    return FixturePrediction(
        home_team="Home FC", away_team="Away FC", date_unix=1_700_000_000,
        directions=tuple(dirs), derived=derived,
        independence_assumption="test")


def test_fixture_readout_labels_and_directional():
    # Use a league NOT re-tested by the family-transfer study, so the pooled
    # validated status still applies (EPL/La Liga/Ligue 1 are now unvalidated).
    ro = build_fixture_readout(_fixture(), league_label="Germany Bundesliga")
    assert ro.validated_markets() == ("corners", "cards")
    assert ro.market("goals").scope.status is MarketStatus.NO_DEMONSTRATED_SKILL
    assert ro.market("btts").scope.status is MarketStatus.NO_DEMONSTRATED_SKILL
    assert ro.market("btts").directional is None
    # honest framing present in the render
    assert "NOT betting advice" in ro.render()


def test_fixture_readout_excludes_cards_in_championship():
    ro = build_fixture_readout(_fixture(), league_label="England Championship")
    cards = ro.market("cards")
    assert cards.scope.status is MarketStatus.EXCLUDED
    assert cards.p_over_total is None and cards.directional is None
    assert ro.validated_markets() == ("corners",)


# ── directional gate (data-driven, accuracy + calibration separate) ───────────

def test_directional_gate_suppressed_for_corners_cards_goals_all_leagues():
    for market in ("corners", "cards", "goals"):
        for league in ("England Championship", "La Liga 2", "Ligue 2"):
            st = directional_status(market, league)
            assert st.emit_call is False, (market, league)
            assert st.show_probability is False, (market, league)
            assert "no directional call" in st.reason


def test_directional_gate_passes_only_sot_ligue2():
    st = directional_status("sot", "Ligue 2")
    assert st.emit_call is True and st.show_probability is True
    # every other sot cell is suppressed
    for league in ("Championship", "La Liga 2"):
        assert directional_status("sot", league).emit_call is False


def test_directional_gate_untested_cell_defaults_suppressed():
    st = directional_status("corners", "Serie A")  # not in the evidence table
    assert st.emit_call is False and st.show_probability is False
    assert "not evaluated" in st.reason


def test_directional_accuracy_and_calibration_gates_are_independent():
    from src.research.prediction_engine.scope import DirectionalEvidence
    # accuracy passes, calibration fails -> emit call, withhold probability
    ev = DirectionalEvidence(
        market="sot", league_label="Test", n_decisive=300,
        model_accuracy=0.64, home_baseline=0.58, diff_ci_low=0.02, diff_ci_high=0.10,
        ece=0.20, beats_home_bh=True, seed=1, family_size=12)
    assert ev.accuracy_gate_passed is True
    assert ev.calibration_gate_passed is False


def test_fixture_readout_suppresses_directional_calls_for_covered_markets():
    ro = build_fixture_readout(_fixture(), league_label="England Premier League")
    text = ro.render()
    # EPL corners/cards directional calls are suppressed. They are now in the
    # evidence table (family-transfer test) but do NOT beat the home-advantage
    # baseline under BH, so no call is emitted.
    assert "does not beat the home-advantage baseline" in text or "not evaluated" in text
    # EPL corners/cards are UNVALIDATED after the family-transfer test -> the
    # no-demonstrated-skill label is shown, never "validated skill".
    assert NO_SKILL_LABEL in text
    assert "validated skill" not in text


# ── reliability report ───────────────────────────────────────────────────────

def test_reliability_report_gate_and_collapse_and_exclusion():
    r = random.Random(9)
    good = [min(0.97, max(0.03, r.betavariate(2, 2))) for _ in range(250)]
    good_o = [r.random() < p for p in good]
    small = [r.random() for _ in range(30)]
    small_o = [r.random() < p for p in small]
    collapsed = [0.5] * 250
    collapsed_o = [r.random() < 0.5 for _ in range(250)]
    champ = [r.random() for _ in range(250)]
    champ_o = [r.random() < p for p in champ]

    rep = build_reliability_report([
        ("corners", "EPL", good, good_o),
        ("cards", "EPL", small, small_o),
        ("corners", "League X", collapsed, collapsed_o),
        ("cards", "England Championship", champ, champ_o),
    ])
    text = rep.render()
    assert "insufficient settled predictions" in text  # small cell gated
    assert "BASE-RATE COLLAPSE" in text                # collapsed cell flagged
    assert "EXCLUDED in the Championship" in text       # champ cards excluded
    displayable = {(c.market, c.league_label) for c in rep.displayable_cells()}
    assert ("corners", "EPL") in displayable
    assert ("corners", "League X") not in displayable  # collapsed -> not displayable
    assert ("cards", "England Championship") not in displayable  # excluded
