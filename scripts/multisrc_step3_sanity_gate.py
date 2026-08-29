"""
Multi-source Step 3 — per-league, per-target SANITY GATE.

Purpose
-------
Before any metric search runs on a league/target slice, we must confirm the
*known-good* raw signal is actually present and correctly oriented on THAT slice.
This is the gate that decides where we are allowed to search at all. Per the
standing rules:

    * F016 (raw-feature Spearman) is the DECISIVE, model-free instrument — never
      pooled across seasons, always reported per season.
    * F017 (validated finding): on the Championship, team yellow-card-rate does NOT
      predict total cards (rho -0.044 / +0.033 / +0.012 across the three seasons —
      flat). So a CARDS gate FAIL on the Championship is an EXPECTED generalization
      result, not a bug in this script.

For EACH league (champ, ligue2, laliga2) and EACH target (cards, goals, corners)
this script runs two stages and emits a single PASS/FAIL gate decision:

STAGE 1 — model-free raw-feature Spearman (decisive), per season, never pooled.
    cards  : yellow-card-rate(w5, home+away) -> total_cards
             AND foul-rate(w5, home+away)     -> total_cards
    goals  : SOT-rate(w5, home+away)          -> total_goals
             AND xg-rate(w5, home+away)       -> total_goals
    corners: corner-rate(w5, home+away, _rich, id-keyed) -> total_corners
    Reports Spearman rho, p, n per season and a note on whether the sign is
    consistently positive across the league's seasons.

    This mirrors champ_raw_feature_corr.corr_named_stat (named/extract_stat fields)
    and champ_raw_feature_corr.corr_rich_stat (_rich id-keyed rolling) EXACTLY —
    same window w5, same home+away sum aggregation, same outcome functions.

STAGE 2 — model-based walk-forward (championship_step34_analysis.wf_predict_existing),
    pooled over the league's seasons (concatenate matches, build_team_histories once).
    Runs the KNOWN-GOOD metric for the target and checks Spearman(predicted_lambda,
    actual) > 0.  Mirrors championship_step34_analysis.sanity_gate.
        cards : features [(home,yellow_cards,5),(away,yellow_cards,5)] -> total_cards
        goals : features [(home,shotsOnTarget,10),(away,xg,10)]        -> total_goals
        corners: no ev.METRICS-style named model exists (wf_predict_existing only
                 supports total_cards / total_goals outcomes), so Stage 2 is not
                 applicable to corners; the gate for corners rests on Stage 1.

GATE DECISION per (league, target):
    PASS if the raw-feature signal is present (positive) AND the model-based
    Spearman > 0.  For corners (no Stage-2 model), PASS if Stage 1 is positive.

    A cards FAIL on Championship is tagged expected_generalization=True so the
    orchestrator does not treat it as an error.

The output makes the operating rule explicit:
    "search only where gate passes; report the rest as untestable."

Output
------
Writes data/thestatsapi/championship/_step3_sanity_gate.json and prints a per
league/target PASS/FAIL table.

Usage
-----
    python3 multisrc_step3_sanity_gate.py [league_tag]
        league_tag defaults to all leagues (champ, ligue2, laliga2).

NOTE: this reads one /stats file per match via multisrc_corpus.load_season. Data
is still being fetched, so do NOT run this until all stats land — it is written and
py_compile-checked only.
"""
import os
import sys
import json

import numpy as np
from scipy.stats import spearmanr

sys.path.insert(0, os.path.dirname(__file__))
import ev_test_metrics_vs_bet365 as ev
import multisrc_corpus as corpus
import champ_raw_feature_corr as rfc
import championship_step34_analysis as step34

CACHE = "/home/ubuntu/data/thestatsapi/championship"
OUT = f"{CACHE}/_step3_sanity_gate.json"

# Targets analysed by the gate.
TARGETS = ("cards", "goals", "corners")


# ─────────────────────────────────────────────────────────────
# Per-target STAGE 1 raw-feature predictors (mirror champ_raw_feature_corr).
#
# Each entry lists the raw-feature Spearman tests to run for that target.  We reuse
# rfc.corr_named_stat / rfc.corr_rich_stat and rfc.total_* outcome functions VERBATIM
# so the numbers match the F016 decisive method exactly (window w5, home+away sum).
#   kind="named" -> rfc.corr_named_stat(matches, team_hist, stat, outcome_fn)
#   kind="rich"  -> rfc.corr_rich_stat(matches, rich_idx, field, outcome_fn)
# ─────────────────────────────────────────────────────────────
STAGE1_TESTS = {
    "cards": [
        {"label": "cards_from_yellow_rate", "kind": "named",
         "stat": "yellow_cards", "outcome": rfc.total_cards},
        {"label": "cards_from_foul_rate", "kind": "named",
         "stat": "fouls", "outcome": rfc.total_cards},
    ],
    "goals": [
        {"label": "goals_from_sot_rate", "kind": "named",
         "stat": "shotsOnTarget", "outcome": rfc.total_goals},
        {"label": "goals_from_xg_rate", "kind": "named",
         "stat": "xg", "outcome": rfc.total_goals},
    ],
    "corners": [
        {"label": "corners_from_corner_rate", "kind": "rich",
         "field": "corner_kicks", "outcome": rfc.total_corners},
    ],
}


# ─────────────────────────────────────────────────────────────
# STAGE 2 known-good model metric per target (mirror championship_step34).
# wf_predict_existing supports total_cards / total_goals outcomes only, so corners
# has no Stage-2 model.
# ─────────────────────────────────────────────────────────────
STAGE2_METRIC = {
    "cards": {
        "target": "total_cards",
        "features": [("home", "yellow_cards", 5), ("away", "yellow_cards", 5)],
        "lines": [3.5],
    },
    "goals": {
        "target": "total_goals",
        "features": [("home", "shotsOnTarget", 10), ("away", "xg", 10)],
        "lines": [2.5],
    },
    "corners": None,  # not applicable — see module docstring
}


def _tup_to_dict(tup):
    """champ_raw_feature_corr returns (rho, p, n). Normalise to a JSON-friendly dict."""
    rho, p, n = tup
    return {"spearman_rho": rho, "spearman_p": p, "n": n,
            "insufficient": rho is None}


def run_stage1_for_season(matches, target):
    """Run every Stage-1 raw-feature test for one league SEASON (never pooled).

    Builds the team-name history (for named/extract_stat fields) and the id-keyed
    _rich index (for corners) exactly as champ_raw_feature_corr does, then evaluates
    each configured predictor.  Returns {label: {rho, p, n, insufficient}}.
    """
    team_hist = ev.build_team_histories(matches)
    rich_idx = rfc.build_rich_idx(matches)
    results = {}
    for test in STAGE1_TESTS[target]:
        if test["kind"] == "named":
            tup = rfc.corr_named_stat(matches, team_hist, test["stat"], test["outcome"])
        else:  # rich
            tup = rfc.corr_rich_stat(matches, rich_idx, test["field"], test["outcome"])
        results[test["label"]] = _tup_to_dict(tup)
    return results


def summarise_stage1(per_season):
    """Aggregate Stage-1 across a league's seasons WITHOUT pooling the data.

    per_season: {season_id: {label: {rho, p, n, insufficient}}}
    For each predictor label, collect its per-season rho values and note whether the
    sign is CONSISTENTLY POSITIVE across every season that produced a value.

    Returns {label: {season_rhos, all_positive, any_computed, note}} plus a top-level
    'stage1_positive' flag = True iff at least one predictor is consistently positive
    across all seasons (i.e. the raw signal is present & correctly oriented).
    """
    labels = set()
    for s in per_season.values():
        labels.update(s.keys())

    per_label = {}
    stage1_positive = False
    for label in sorted(labels):
        rhos = {}
        for sid, res in per_season.items():
            r = res.get(label)
            if r and not r["insufficient"] and r["spearman_rho"] is not None:
                rhos[sid] = r["spearman_rho"]
        any_computed = len(rhos) > 0
        all_positive = any_computed and all(v > 0 for v in rhos.values())
        if all_positive:
            stage1_positive = True
        if not any_computed:
            note = "no season produced a computable Spearman (insufficient data)"
        elif all_positive:
            note = ("sign consistently POSITIVE across all "
                    f"{len(rhos)} computed season(s)")
        else:
            signs = ", ".join(f"{sid}:{v:+.3f}" for sid, v in rhos.items())
            note = f"sign NOT consistently positive ({signs})"
        per_label[label] = {
            "season_rhos": rhos,
            "any_computed": any_computed,
            "all_positive_across_seasons": all_positive,
            "note": note,
        }
    return per_label, stage1_positive


def run_stage2_pooled(pooled_matches, target):
    """Model-based walk-forward on the known-good metric, POOLED over the league's
    seasons.  Mirrors championship_step34_analysis.sanity_gate: build_team_histories
    once on the concatenated matches, run wf_predict_existing, check
    Spearman(predicted_lambda, actual) > 0.

    Returns a dict describing the check, or an 'applicable': False dict for corners.
    """
    mdef = STAGE2_METRIC[target]
    if mdef is None:
        return {"applicable": False,
                "reason": ("wf_predict_existing supports total_cards/total_goals "
                           "outcomes only; no named model for corners — gate rests "
                           "on Stage 1")}

    team_hist = ev.build_team_histories(pooled_matches)
    preds = step34.wf_predict_existing(mdef, pooled_matches, team_hist)
    if not preds:
        return {"applicable": True, "passed": False, "reason": "no predictions",
                "n": 0, "spearman_lambda_actual": None, "spearman_p": None}

    lam = np.array([p["predicted_lambda"] for p in preds], dtype=float)
    act = np.array([p["actual_count"] for p in preds], dtype=float)
    rho, pv = spearmanr(lam, act)
    passed = bool(rho is not None and rho > 0)
    return {
        "applicable": True,
        "passed": passed,
        "spearman_lambda_actual": None if rho is None else float(rho),
        "spearman_p": None if pv is None else float(pv),
        "predicted_mean_lambda": float(lam.mean()),
        "actual_mean": float(act.mean()),
        "n": len(preds),
        "metric": {"target": mdef["target"], "features": mdef["features"]},
    }


def gate_decision(tag, target, stage1_positive, stage2):
    """Combine Stage 1 + Stage 2 into a single PASS/FAIL decision for (league, target).

    PASS rule:
      * If Stage 2 is applicable (cards, goals): PASS iff raw-feature signal is present
        (stage1_positive) AND model-based Spearman > 0 (stage2['passed']).
      * If Stage 2 is not applicable (corners): PASS iff stage1_positive.

    Championship + cards is the validated F017 flat case: a FAIL there is EXPECTED and
    tagged expected_generalization=True so the orchestrator treats it as a
    generalization result, not an error.
    """
    stage2_applicable = stage2.get("applicable", False)
    stage2_passed = bool(stage2.get("passed", False)) if stage2_applicable else None

    if stage2_applicable:
        passed = bool(stage1_positive and stage2_passed)
    else:
        passed = bool(stage1_positive)

    expected_generalization = (tag == "champ" and target == "cards" and not passed)

    if passed:
        reason = ("raw-feature signal present (Stage 1 positive)"
                  + (" and model-based Spearman>0 (Stage 2)" if stage2_applicable
                     else "; Stage 2 n/a for corners"))
    else:
        bits = []
        if not stage1_positive:
            bits.append("Stage 1 raw signal absent / not consistently positive")
        if stage2_applicable and not stage2_passed:
            bits.append("Stage 2 model Spearman not > 0")
        reason = "; ".join(bits) or "gate not satisfied"
        if expected_generalization:
            reason += (" — EXPECTED per F017 (Championship yellow-rate->cards is flat: "
                       "-0.044/+0.033/+0.012); reported as a generalization result, "
                       "not an error")

    return {
        "passed": passed,
        "stage1_positive": bool(stage1_positive),
        "stage2_applicable": stage2_applicable,
        "stage2_passed": stage2_passed,
        "expected_generalization": expected_generalization,
        "reason": reason,
    }


def analyze_league(tag):
    """Full per-target gate for one league.  Loads each season once (Stage 1, never
    pooled) and the concatenation of all seasons (Stage 2, pooled)."""
    league = corpus.LEAGUES[tag]
    seasons = league["seasons"]

    # Load each season's adapted matches once; reused for Stage 1 and pooled Stage 2.
    season_matches = {}
    load_errors = {}
    for sid in seasons:
        try:
            season_matches[sid] = corpus.load_season(tag, sid)
        except Exception as exc:  # missing/incomplete files -> record, keep going
            load_errors[sid] = repr(exc)

    pooled = []
    for sid in seasons:
        pooled.extend(season_matches.get(sid, []))
    pooled.sort(key=lambda m: m["date_unix"])

    result = {
        "tag": tag,
        "display": league["display"],
        "comp": league["comp"],
        "seasons": seasons,
        "n_matches_per_season": {sid: len(season_matches.get(sid, [])) for sid in seasons},
        "n_pooled": len(pooled),
        "load_errors": load_errors,
        "targets": {},
    }

    for target in TARGETS:
        # STAGE 1 — per season, never pooled
        per_season = {}
        for sid in seasons:
            matches = season_matches.get(sid)
            if not matches:
                per_season[sid] = {}  # nothing to compute for a missing season
                continue
            per_season[sid] = run_stage1_for_season(matches, target)
        stage1_labels, stage1_positive = summarise_stage1(per_season)

        # STAGE 2 — pooled over the league's seasons
        stage2 = run_stage2_pooled(pooled, target)

        # GATE
        decision = gate_decision(tag, target, stage1_positive, stage2)

        result["targets"][target] = {
            "stage1_raw_feature": {
                "per_season": per_season,
                "by_predictor": stage1_labels,
                "stage1_positive": bool(stage1_positive),
                "method": ("model-free raw-feature Spearman, w5 home+away, per season "
                           "never pooled (mirrors champ_raw_feature_corr / F016)"),
            },
            "stage2_model_based": stage2,
            "gate": decision,
        }

    return result


def _print_league_table(res):
    print("=" * 78)
    print(f"{res['display']}  (tag={res['tag']}, comp={res['comp']})")
    print("=" * 78)
    if res["load_errors"]:
        for sid, err in res["load_errors"].items():
            print(f"  ! load error {sid}: {err}")
    npr = res["n_matches_per_season"]
    print("  matches/season: " + "  ".join(f"{sid}={npr[sid]}" for sid in res["seasons"])
          + f"   pooled={res['n_pooled']}")
    print(f"  {'target':8s} {'gate':6s}  detail")
    print("  " + "-" * 68)
    for target in TARGETS:
        t = res["targets"][target]
        g = t["gate"]
        verdict = "PASS" if g["passed"] else "FAIL"
        tag_note = ""
        if g["expected_generalization"]:
            tag_note = "  [expected generalization — F017]"
        s1 = "S1+" if t["stage1_raw_feature"]["stage1_positive"] else "S1-"
        if t["stage2_model_based"].get("applicable"):
            rho = t["stage2_model_based"].get("spearman_lambda_actual")
            s2 = f"S2 rho={'n/a' if rho is None else format(rho, '+.3f')}"
        else:
            s2 = "S2 n/a"
        print(f"  {target:8s} {verdict:6s}  {s1} {s2}{tag_note}")
        # per-predictor Stage-1 line
        for label, info in t["stage1_raw_feature"]["by_predictor"].items():
            print(f"      - {label}: {info['note']}")


def main(tags):
    print("#" * 78)
    print("MULTI-SOURCE STEP 3 — PER-LEAGUE / PER-TARGET SANITY GATE")
    print("#" * 78)
    print("Operating rule: SEARCH ONLY WHERE THE GATE PASSES; report the rest as")
    print("UNTESTABLE. Stage 1 (raw-feature Spearman, per season) is decisive; Stage 2")
    print("(model-based walk-forward, pooled) confirms the model is wired to the signal.")
    print()

    out = {
        "operating_rule": ("search only where gate passes; report the rest as "
                           "untestable"),
        "method": {
            "stage1": ("model-free raw-feature Spearman, window w5, feature = home "
                       "rolling + away rolling, per season NEVER pooled (F016). cards: "
                       "yellow-rate & foul-rate -> total_cards; goals: SOT-rate & "
                       "xg-rate -> total_goals; corners: corner-rate (_rich id-keyed) "
                       "-> total_corners"),
            "stage2": ("model-based walk-forward (wf_predict_existing) on the known-good "
                       "metric, POOLED over the league's seasons, check "
                       "Spearman(predicted_lambda, actual) > 0. cards features "
                       "[(home,yellow_cards,5),(away,yellow_cards,5)] target total_cards; "
                       "goals features [(home,shotsOnTarget,10),(away,xg,10)] target "
                       "total_goals; corners: not applicable (no named model)"),
            "gate": ("PASS if raw-feature signal present (Stage 1 positive) AND "
                     "model-based Spearman > 0 (Stage 2). Corners: PASS if Stage 1 "
                     "positive (Stage 2 n/a)."),
        },
        "expected_findings": {
            "F017": ("Championship yellow-card-rate -> total_cards is flat "
                     "(-0.044/+0.033/+0.012 across seasons); a Championship cards FAIL "
                     "is an EXPECTED generalization result, not an error"),
        },
        "leagues": {},
    }

    for tag in tags:
        if tag not in corpus.LEAGUES:
            print(f"unknown tag: {tag} (known: {', '.join(corpus.LEAGUES)})")
            continue
        res = analyze_league(tag)
        out["leagues"][tag] = res
        _print_league_table(res)
        print()

    # Explicit PASS/FAIL roll-up across everything analysed.
    print("=" * 78)
    print("GATE ROLL-UP — where may we search?")
    print("=" * 78)
    passes, fails = [], []
    for tag, res in out["leagues"].items():
        for target in TARGETS:
            g = res["targets"][target]["gate"]
            combo = f"{tag}/{target}"
            (passes if g["passed"] else fails).append(
                combo + (" (expected-fail F017)" if g["expected_generalization"] else ""))
    out["gate_rollup"] = {"pass": passes, "fail": fails}
    print("  PASS (search here):     " + (", ".join(passes) if passes else "(none)"))
    print("  FAIL (untestable here): " + (", ".join(fails) if fails else "(none)"))
    print()
    print("  >>> search only where gate passes; report the rest as untestable. <<<")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as fh:
        json.dump(out, fh, indent=2, default=str)
    print(f"\nsaved: {OUT}")


if __name__ == "__main__":
    requested = sys.argv[1:] if len(sys.argv) > 1 else list(corpus.LEAGUES.keys())
    main(requested)
