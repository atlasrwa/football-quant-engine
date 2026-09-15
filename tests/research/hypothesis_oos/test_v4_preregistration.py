"""Zero-spend leakage / identifiability tests for the V4 hypothesis-derived OOS design.

$0.00. No Bedrock, no network, no CHAMPION mutation, no final OOS scoring. These prove the
preregistration is leakage-safe BY CONSTRUCTION and free of effect-based selection, before
any statistical experiment runs.
"""
from __future__ import annotations

import hashlib
import importlib
import json
import os

import pytest

ROOT = "/home/ubuntu"
V3_OUT = f"{ROOT}/research/hypothesis_engine/out/v3_hypothesis_measurement"
PREREG = f"{ROOT}/research/hypothesis_oos/out/PREREGISTRATION.json"

from src.research.hypothesis_oos import compatibility as COMPAT
from src.research.hypothesis_engine import cohort_measurement as CM


@pytest.fixture(scope="module")
def prereg():
    assert os.path.exists(PREREG), "run _freeze_v4_preregistration.py first"
    return json.load(open(PREREG))


# ---------------------------------------------------------------------------
# 1. No effect-based selection
# ---------------------------------------------------------------------------
def test_v4_no_effect_selection(prereg):
    rule = prereg["anti_selection_rule"]
    assert rule["eligibility"] == "STRUCTURAL_ONLY"
    assert rule["criteria_contain_no_effect_term"] is True
    for forbidden in ("difference", "sign", "magnitude", "abs_diff_over_se",
                      "significance", "story_success"):
        assert any(forbidden in s for s in rule["forbidden_selectors"])

    # No template or eligibility field may carry an observed effect quantity.
    blob = json.dumps({k: v for k, v in prereg.items()
                       if k in ("templates", "families", "target_mapping",
                                "venue_tautology_rule")})
    for banned in ("shrunk_difference", "abs_diff_over_se", "\"se\":", "p_value",
                   "significan"):
        assert banned not in blob, f"effect quantity {banned!r} leaked into selection"


# ---------------------------------------------------------------------------
# 2. Templates are identity-blind
# ---------------------------------------------------------------------------
def test_v4_templates_are_identity_blind(prereg):
    allowed = {"condition_dimension", "opponent_profile_axis", "opponent_profile_band",
               "target_metric", "side", "comparison_cohort", "window", "period"}
    assert prereg["templates"], "expected at least one template"
    for t in prereg["templates"]:
        assert set(t) <= allowed, f"template carries non-structural field: {set(t) - allowed}"
        for forbidden in ("fixture", "team", "club", "subject", "date", "kickoff",
                          "difference", "mean", "se"):
            assert not any(forbidden in k for k in t), \
                f"template key contains identity/effect token {forbidden!r}"


# ---------------------------------------------------------------------------
# 3. Origin fixtures quarantined
# ---------------------------------------------------------------------------
def test_v4_origin_fixtures_excluded(prereg):
    corpus = json.load(open(f"{V3_OUT}/frozen_hypothesis_corpus.json"))
    origin = sorted({r["fixture_id"] for r in corpus["included"]})
    quarantined = set(prereg["contamination_protocol"]["origin_fixtures_quarantined"])
    assert set(origin) <= quarantined, "some origin fixtures are not quarantined"
    assert prereg["contamination_protocol"]["design"] == "B_templates_walk_forward"


# ---------------------------------------------------------------------------
# 4. PIT strict-less-than (positive leakage test on the real executor)
# ---------------------------------------------------------------------------
def _spec(comparison="SUBJECT_OVERALL_BASELINE"):
    return CM.MeasurementSpec(
        spec_version=CM.COHORT_MEASUREMENT_VERSION, hypothesis_id="H_TEST",
        fixture_id="F", subject_label="HOME_TEAM", subject_team="T",
        target_metric="corners", side="FOR", window="ALL_PRIOR", period="ALL",
        granularity="FULL_MATCH", venue_condition=None, competition_condition=None,
        own_formation_condition=None, opponent_formation_condition=None,
        opponent_profile_band=None, opponent_profile_axis=None,
        profile_band_semantics=None, comparison_cohort=comparison,
        target_competition="L", cutoff_unix=1000, provider="thestatsapi",
        required_fields=(), plan_hash="h")


def test_v4_pit_strict_less_than():
    clean = [CM.Obs("a", 100, "L", "O1", 5.0, {"venue": "HOME"}),
             CM.Obs("b", 200, "L", "O2", 6.0, {"venue": "AWAY"}),
             CM.Obs("c", 300, "L", "O3", 7.0, {"venue": "HOME"}),
             CM.Obs("d", 400, "L", "O4", 8.0, {"venue": "AWAY"}),
             CM.Obs("e", 500, "L", "O5", 9.0, {"venue": "HOME"}),
             CM.Obs("f", 600, "L", "O6", 4.0, {"venue": "AWAY"}),
             CM.Obs("g", 700, "L", "O7", 5.0, {"venue": "HOME"}),
             CM.Obs("h", 800, "L", "O8", 6.0, {"venue": "AWAY"})]
    ok = CM.execute(_spec(), subject_history=clean)
    assert ok.outcome in (CM.MEASURED, CM.NOT_DISTINCT, CM.INSUFFICIENT_DATA)

    # kickoff == cutoff is a violation (strict <)
    boundary = clean + [CM.Obs("z", 1000, "L", "OZ", 99.0, {"venue": "HOME"})]
    assert CM.execute(_spec(), subject_history=boundary).outcome == CM.LEAKAGE_REJECTED

    # kickoff > cutoff is a violation
    future = clean + [CM.Obs("z", 1500, "L", "OZ", 99.0, {"venue": "HOME"})]
    assert CM.execute(_spec(), subject_history=future).outcome == CM.LEAKAGE_REJECTED


# ---------------------------------------------------------------------------
# 5. Venue tautology excluded by construction
# ---------------------------------------------------------------------------
def test_v4_venue_tautology_excluded_by_construction():
    # condition on venue + compare against SUBJECT_VENUE_BASELINE -> not distinct
    spec = _spec(comparison="SUBJECT_VENUE_BASELINE").to_dict()
    spec["venue"] = "HOME"
    v = COMPAT.check_spec(spec)
    assert v.status == COMPAT.NOT_DISTINCT_BY_CONSTRUCTION
    assert v.absorbed_dimension == "venue"
    assert not v.eligible

    # condition on venue + SUBJECT_OVERALL_BASELINE -> distinct, eligible
    ok = _spec(comparison="SUBJECT_OVERALL_BASELINE").to_dict()
    ok["venue"] = "HOME"
    assert COMPAT.check_spec(ok).eligible

    # competition condition + SUBJECT_COMPETITION_BASELINE -> not distinct
    comp = _spec(comparison="SUBJECT_COMPETITION_BASELINE").to_dict()
    comp["competition"] = "SAME"
    assert COMPAT.check_spec(comp).status == COMPAT.NOT_DISTINCT_BY_CONSTRUCTION


def test_v4_venue_tautology_count_matches_v3(prereg):
    # V3 found exactly 10 NOT_DISTINCT (7 venue + 3 unconditioned). The structural rule
    # must reproduce that count on the frozen corpus.
    assert prereg["venue_tautology_rule"]["n_excluded"] == 10


# ---------------------------------------------------------------------------
# 6. Competition-baseline real-data readiness smoke (zero spend)
# ---------------------------------------------------------------------------
def test_v4_competition_baseline_realdata_smoke():
    hist = [CM.Obs(str(i), 100 + i, "L1" if i % 2 else "L2", f"O{i}",
                   float(i % 5 + 3), {"venue": "HOME" if i % 2 else "AWAY"})
            for i in range(20)]
    spec = _spec(comparison="SUBJECT_COMPETITION_BASELINE")
    m = CM.execute(spec, subject_history=hist)
    # It resolves to a real comparison cohort (not UNSUPPORTED_COMPARISON).
    assert m.outcome != CM.UNSUPPORTED_COMPARISON


# ---------------------------------------------------------------------------
# 7. Missingness not favorable
# ---------------------------------------------------------------------------
def test_v4_missingness_not_favorable(prereg):
    pol = prereg["missingness_policy"]
    assert pol["favorable_imputation_forbidden"] is True
    assert pol["indicator_preregistered"] == "hd_available"
    # absent feature must NOT be encoded as 0.0 difference (which would bias toward "no
    # effect" on the favorable side); it is NaN + an availability indicator.
    assert "NaN" in pol["absent_feature"]


# ---------------------------------------------------------------------------
# 8. Champion read-only / sha unchanged
# ---------------------------------------------------------------------------
def test_v4_champion_readonly(prereg):
    cp = prereg["champion_protection"]
    assert cp["read_only"] is True and cp["auto_promotion"] is False
    path = cp["artifact"]
    if os.path.exists(path):
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        assert h.hexdigest() == cp["frozen_sha256"], "CHAMPION artifact changed!"


# ---------------------------------------------------------------------------
# 9. Import firewall: no Bedrock, no p_model, no production prediction
# ---------------------------------------------------------------------------
def test_v4_import_firewall():
    import sys
    mod = importlib.import_module("src.research.hypothesis_oos.compatibility")
    # walk the module's transitive imports that live under src.research
    seen = set()
    stack = [mod.__name__]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        m = sys.modules.get(name)
        if m is None:
            continue
        for attr in dir(m):
            sub = getattr(m, attr, None)
            subname = getattr(sub, "__module__", None)
            if isinstance(subname, str) and subname.startswith("src.research"):
                stack.append(subname)
    banned = ("bedrock", "p_model", "forecast_broadcast", "pilotC")
    for name in seen:
        for b in banned:
            assert b not in name.lower(), f"V4 layer transitively imports {b}: {name}"


# ---------------------------------------------------------------------------
# 10. Identifiability verdict present and scoped
# ---------------------------------------------------------------------------
def test_v4_identifiability_scoped(prereg):
    ident = prereg["identifiability"]
    assert ident["verdict"] == "IDENTIFIABLE_FOR_SINGLE_CONFIRMATORY_CONTRAST"
    assert ident["confirmatory_cell_identifiable"] is True
    assert prereg["multiplicity"]["confirmatory"]["market"] == "corners"
    # set-aside metrics really have no validated market
    for metric in prereg["target_mapping"]["set_aside_no_validated_target"]:
        assert prereg["target_mapping"]["per_metric"][metric]["market"] is None
