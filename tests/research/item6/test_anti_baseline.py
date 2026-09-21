"""ANTI-BASELINE tests. Synthetic stand-in outputs must classify as the mission specifies:
  simple mirror        -> BASELINE_EQUIVALENT
  simple venue effect  -> BASELINE_EQUIVALENT
  genuine multi-signal -> potentially novel (subject to measurability)
  unsupported tactical -> reject (F2)
  future-dependent     -> reject (F2)
Plus: the deterministic control (ARM G-D) never yields a novel measurable family, and the
apparatus can register BOTH a PASS and a FAIL (falsifiability of the instrument).
"""
from __future__ import annotations

from src.research.item6 import control_generator as cg
from src.research.item6.baseline_equivalence import classify, is_baseline_equivalent
from src.research.item6.formalizer import formalize
from src.research.item6.schema import Mechanism


def _m(mid, stmt, vars_, cond, rel, why, refs=("ev1",), res="match"):
    return Mechanism(mid, stmt, list(vars_), cond, rel, why, list(refs), res, list(vars_))


def test_simple_mirror_is_baseline_equivalent():
    m = _m("m", "Whether the subject's corner_kicks for exceeds the opponent's corner_kicks against (mirror)",
           ["corner_kicks"], "no extra conditioning; for versus against on one metric",
           "for exceeds against", "mirror")
    assert is_baseline_equivalent(m)
    assert formalize(m, allowed_evidence_refs=["ev1"]).f_class == "F1_BASELINE_EQUIVALENT"


def test_simple_venue_effect_is_baseline_equivalent():
    m = _m("m", "Whether the subject's shots differ at home versus away",
           ["shots", "venue_home_away"], "venue split only", "home vs away differ", "venue split")
    assert is_baseline_equivalent(m)
    assert formalize(m, allowed_evidence_refs=["ev1"]).f_class == "F1_BASELINE_EQUIVALENT"


def test_univariate_profile_split_is_baseline_equivalent():
    m = _m("m", "Whether the subject's shots vary against opponents in a goals_against band",
           ["shots"], "condition on one opponent-profile band on goals_against",
           "conditioned mean deviates", "single profile band")
    assert is_baseline_equivalent(m)


def test_genuine_multi_signal_is_potentially_novel():
    m = _m("m", "Whether elevated possession together with suppressed shots_on_target jointly relates to fouls",
           ["possession", "shots_on_target", "fouls"],
           "joint conditioning on two distinct metrics simultaneously",
           "joint state relates to elevated fouls",
           "combines two distinct metrics in a genuine interaction beyond single-metric grammar")
    v = classify(m)
    assert not v.is_baseline_equivalent
    f = formalize(m, allowed_evidence_refs=["ev1"])
    assert f.counts_as_novel_measurable
    assert f.f_class in ("F3_MEASURABLE_WITH_EXISTING_GRAMMAR",
                         "F4_MEASURABLE_WITH_SAFE_ADDITIVE_GRAMMAR_EXTENSION")


def test_threshold_is_novel_and_needs_extension():
    m = _m("m", "Whether accurate_crosses above a threshold saturate and stop increasing big_chances",
           ["accurate_crosses", "big_chances"], "threshold / nonlinear on a continuous observable",
           "saturates beyond a cutoff", "threshold nonlinearity not expressible by tercile bands")
    f = formalize(m, allowed_evidence_refs=["ev1"])
    assert f.f_class == "F4_MEASURABLE_WITH_SAFE_ADDITIVE_GRAMMAR_EXTENSION"
    assert f.required_extension in ("GX_THRESHOLD_CONDITION", "GX_CROSS_METRIC_JOINT")


def test_unsupported_tactical_is_rejected():
    m = _m("m", "Whether expected lineup and manager intention shift shots",
           ["shots"], "condition on predicted xi and managerial intention", "directional", "x")
    f = formalize(m, allowed_evidence_refs=["ev1"])
    assert f.f_class == "F2_GROUNDED_BUT_NOT_PROVIDER_MEASURABLE"
    assert not f.provider_safe


def test_future_dependent_is_rejected():
    m = _m("m", "Whether the closing line predicts shots",
           ["shots"], "use closing odds and settlement", "directional", "x")
    f = formalize(m, allowed_evidence_refs=["ev1"])
    assert f.f_class == "F2_GROUNDED_BUT_NOT_PROVIDER_MEASURABLE"
    assert f.future_leakage


def test_control_gd_never_yields_novel_measurable():
    mechs = cg.generate_families("mtZ", ["corner_kicks", "shots_on_target", "possession", "fouls"], 5)
    for g in mechs:
        f = formalize(g, allowed_evidence_refs=[g.evidence_refs[0]])
        assert f.f_class == "F1_BASELINE_EQUIVALENT", (g.mechanism_id_local, f.f_class)
        assert not f.counts_as_novel_measurable
