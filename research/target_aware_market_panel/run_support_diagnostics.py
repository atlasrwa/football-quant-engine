"""Run the frozen, outcome-blind panel support diagnostics for GPT-5.6 Sol V1 templates.

Requires the original Ubuntu TheStatsAPI cache.  It does not settle targets, read cohort outcomes,
fit a model, score OOS, or inspect market results.
"""
from __future__ import annotations

import argparse
import calendar
import hashlib
import json
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from src.research.target_aware_market_panel import cohort_packets as CP  # noqa: E402
from src.research.target_aware_market_panel import panel as PN  # noqa: E402
from src.research.target_aware_market_panel import support as SP  # noqa: E402

CACHE = "/home/ubuntu/data/thestatsapi/championship"
OUT = ROOT / "research/target_aware_market_panel"
PANEL_END_UTC = "2026-09-14T23:59:59Z"
SOURCE_NOVELTY_COMMIT = "b068780497ea59713e268fb272bf44939f83f23e"
SOURCE_REGISTRY_SHA256 = "2367b9ea5b3bad10b66c2958599069d574d5bc8c829d6066dc04b75aa069bf1b"
SOURCE_RESPONSE_MANIFEST_SHA256 = "79edc665876aca82ba9425eb741d74fa5252722b9b017dd10bf8f37744b46c6a"
EXPECTED_PANEL_ROWS = 5620
EXPECTED_FOLD_ROWS_SHA256 = "9fca0ec2860ed13cda0368502978445b9444419eece690cba685449c26bf3270"
EXPECTED_CHAMPION_SHA256 = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"
CHAMPION = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")\nRESPONSE_MANIFEST = OUT / "SOL_RESPONSE_MANIFEST_V1.json"
OUTPUTS = (
    "SOL_PANEL_SUPPORT_DIAGNOSTICS_V1.json",
    "SOL_PANEL_SUPPORT_AUDIT_V1.md",
    "SOL_PANEL_SUPPORT_FREEZE_MANIFEST_V1.json",
)


def fsha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def dump(path: Path, obj) -> str:
    path.write_text(json.dumps(obj, indent=1, sort_keys=True, ensure_ascii=False) + "\n")
    return fsha(path)


def git(*args: str) -> str:
    return subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                          check=True).stdout.strip()


def _profile_key(dims):
    return tuple((d["metric"], d["perspective"]) for d in dims)


def _style_strength(template, h, fixtures):
    s = template["similarity"]
    side, dims = s["profile_side"], s["profile_dimensions"]
    out = defaultdict(lambda: {"x": [], "y": []})
    for fx in fixtures:
        team = fx["home_team_id"] if side == "HOME" else fx["away_team_id"]
        venue = "HOME" if side == "HOME" else "AWAY"
        p = PN.style_profile(h, team, venue, dims, fx["kickoff"], fx["competition_id"])
        st = h.strength(team, fx["competition_id"], fx["kickoff"])
        if p is None or st is None:
            continue
        for d in dims:
            key = (d["metric"], d["perspective"])
            if key in p:
                out[f"{key[0]}.{key[1]}"]["x"].append(float(p[key]))
                out[f"{key[0]}.{key[1]}"]["y"].append(float(st))
    ans = {}
    for k, v in sorted(out.items()):
        x, y = np.asarray(v["x"], float), np.asarray(v["y"], float)
        r = None if len(x) < 10 or np.std(x) <= 0 or np.std(y) <= 0 else float(np.corrcoef(x, y)[0, 1])
        ans[k] = {"n": len(x), "pearson_r": r}
    return ans


def audit_md(doc):
    s = doc["summary"]
    L = ["# Sol V1 Panel Support Audit", "",
         f"Source novelty freeze: `{doc['source_novelty_commit']}`", "",
         "This stage is outcome-blind. It does not settle any target, fit any model, score OOS, or read market results.", "",
         "## Headline", "",
         f"- Frozen class-C templates: **{s['n_templates']}**",
         f"- Templates with at least one non-null panel value: **{s['n_with_any_support']}**",
         f"- Zero-support templates: **{s['n_zero_support']}**",
         f"- Global coverage >= 60% (diagnostic only): **{s['n_global_coverage_ge_60']}**",
         f"- Global coverage < 60% but nonzero (diagnostic only): **{s['n_global_coverage_lt_60']}**",
         f"- Near-duplicate feature pairs |r| >= {SP.NEAR_DUPLICATE_ABS_R}: "
         f"**{s['n_near_duplicate_pairs']}**",
         f"- Very-near pairs |r| >= {SP.VERY_NEAR_DUPLICATE_ABS_R}: "
         f"**{s['n_very_near_duplicate_pairs']}**", "",
         "## Selection rule", "",
         "No feature is pruned here for coverage, correlation or style-strength correlation. "
         "The frozen OOS design already specifies a **60% coverage screen fit on each training "
         "fold only**. That remains the availability gate. Exact canonical duplicates were already removed before this stage.", "",
         "## Family support", ""]
    for fam, x in sorted(doc["family_summary"].items()):
        L.append(f"- **{fam}**: {x['n_templates']} templates; {x['n_with_any_support']} with "
                 f"support; median global coverage {x['median_coverage_all']:.4f}.")
    L += ["", "## Interpretation", "",
          "Coverage and redundancy can tell us whether the frozen Sol ideas are operationally usable, but not whether they predict outcomes. Any predictive claim remains blocked until the subsequent frozen walk-forward M0-versus-M1 experiment.", ""]
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--authorized-head", required=True)
    args = ap.parse_args()
    head = git("rev-parse", "HEAD")
    if head != args.authorized_head:
        raise SystemExit(f"HEAD_MISMATCH expected={args.authorized_head} actual={head}")
    if git("status", "--porcelain"):
        raise SystemExit("WORKTREE_NOT_CLEAN")
    if fsha(CHAMPION) != EXPECTED_CHAMPION_SHA256:
        raise SystemExit("CHAMPION_HASH_MISMATCH")
    reg_path = OUT / "SOL_CLASS_C_TEMPLATE_REGISTRY_V1.json"
    if fsha(reg_path) != SOURCE_REGISTRY_SHA256:
        raise SystemExit("CLASS_C_REGISTRY_HASH_MISMATCH")
    if fsha(RESPONSE_MANIFEST) != SOURCE_RESPONSE_MANIFEST_SHA256:
        raise SystemExit("RESPONSE_MANIFEST_HASH_MISMATCH")
    for n in OUTPUTS:
        if (OUT / n).exists():
            raise SystemExit(f"OUTPUT_ALREADY_EXISTS:{n}")

    registry = json.loads(reg_path.read_text())
    if registry["n_templates"] != 124 or len(registry["templates"]) != 124:
        raise SystemExit("UNEXPECTED_CLASS_C_COUNT")
    folds = json.loads((OUT / "TARGET_AWARE_FOLD_MANIFEST_V1.json").read_text())
    if folds["n_panel_rows"] != EXPECTED_PANEL_ROWS or folds["rows_sha256"] != EXPECTED_FOLD_ROWS_SHA256:
        raise SystemExit("FOLD_MANIFEST_MISMATCH")
    fold_rows = {r["match_id"]: r for r in folds["rows"]}

    history, hmeta = CP.load_history(CACHE, include_gap_fetches=False)
    panel_end = calendar.timegm(time.strptime(PANEL_END_UTC, "%Y-%m-%dT%H:%M:%SZ"))
    rows = PN.rows_from_history(history)
    h = PN.PanelHistory(rows, panel_end)
    fixtures = []
    for fr in folds["rows"]:
        hm = history.get(fr["match_id"])
        if hm is None or hm.kickoff_unix > panel_end or not hm.stats:
            raise SystemExit(f"PANEL_FIXTURE_MISSING:{fr['match_id']}")
        home, away = hm.fixture.get("home_team") or {}, hm.fixture.get("away_team") or {}
        fixtures.append({"match_id": fr["match_id"], "kickoff": int(hm.kickoff_unix),
                         "competition_id": str(hm.fixture.get("competition_id")),
                         "home_team_id": str(home.get("id")), "away_team_id": str(away.get("id"))})
    if len(fixtures) != EXPECTED_PANEL_ROWS:
        raise SystemExit("PANEL_ROW_COUNT_MISMATCH")

    # Transparent memoization only; semantics are identical to panel.py.
    orig_prior = h.prior
    prior_cache = {}
    def cached_prior(team, before, venue=None):
        key = (str(team), int(before), venue)
        if key not in prior_cache:
            prior_cache[key] = orig_prior(team, before, venue)
        return prior_cache[key]
    h.prior = cached_prior

    orig_strength = h.strength
    strength_cache = {}
    def cached_strength(team, comp, before):
        key = (str(team), str(comp), int(before))
        if key not in strength_cache:
            strength_cache[key] = orig_strength(team, comp, before)
        return strength_cache[key]
    h.strength = cached_strength

    orig_style = PN.style_profile
    profile_cache = {}
    def cached_style(hh, team, venue, dims, before, comp):
        key = (str(team), venue, _profile_key(dims), int(before), str(comp))
        if key not in profile_cache:
            profile_cache[key] = orig_style(hh, team, venue, dims, before, comp)
        return profile_cache[key]
    PN.style_profile = cached_style

    match_ids = [f["match_id"] for f in fixtures]
    columns, metadata, per_template = {}, {}, []
    for item in registry["templates"]:
        tpl = item["feature_template"]
        vals, details = [], []
        for fx in fixtures:
            if tpl["template_type"] == "OPPONENT_SIMILARITY_CONDITIONAL":
                d = PN.similarity_detail(tpl, h, fx)
                details.append(d)
                vals.append(None if d is None else d["value"])
            else:
                vals.append(PN.instantiate(tpl, h, fx))
        sig = item["canonical_signature_sha256"]
        summary = SP.summarize_column(match_ids, fixtures, vals, fold_rows)
        rec = {k: item[k] for k in ("fixture_id", "family", "hypothesis_id", "market_id",
                                    "canonical_signature_sha256", "template_type")}
        rec["coverage"] = summary
        if tpl["template_type"] == "OPPONENT_SIMILARITY_CONDITIONAL":
            rec["similarity_support"] = SP.summarize_similarity_details(details)
            rec["style_strength_correlation"] = _style_strength(tpl, h, fixtures)
        else:
            rec["similarity_support"] = None
            rec["style_strength_correlation"] = None
        per_template.append(rec)
        columns[sig] = vals
        metadata[sig] = {"family": item["family"], "market_id": item["market_id"],
                          "hypothesis_id": item["hypothesis_id"]}

    near = SP.pairwise_near_duplicates(columns, metadata)
    fam = {}
    for family in sorted({x["family"] for x in per_template}):
        xs = [x for x in per_template if x["family"] == family]
        covs = [x["coverage"]["coverage_all"] for x in xs]
        fam[family] = {"n_templates": len(xs),
                       "n_with_any_support": sum(x["coverage"]["n_nonnull"] > 0 for x in xs),
                       "n_zero_support": sum(x["coverage"]["n_nonnull"] == 0 for x in xs),
                       "median_coverage_all": float(np.median(covs)) if covs else None,
                       "min_coverage_all": float(np.min(covs)) if covs else None,
                       "max_coverage_all": float(np.max(covs)) if covs else None}
    summary = {
        "n_templates": len(per_template),
        "n_with_any_support": sum(x["coverage"]["n_nonnull"] > 0 for x in per_template),
        "n_zero_support": sum(x["coverage"]["n_nonnull"] == 0 for x in per_template),
        "n_global_coverage_ge_60": sum(x["coverage"]["coverage_all"] >= 0.60 for x in per_template),
        "n_global_coverage_lt_60": sum(0 < x["coverage"]["coverage_all"] < 0.60 for x in per_template),
        "n_near_duplicate_pairs": len(near),
        "n_very_near_duplicate_pairs": sum(x["abs_r_ge_0_99"] for x in near),
    }
    doc = {
        "artifact_version": SP.SUPPORT_VERSION,
        "authorized_execution_head": head,
        "source_novelty_commit": SOURCE_NOVELTY_COMMIT,
        "source_registry_sha256": SOURCE_REGISTRY_SHA256,
        "source_response_manifest_sha256": SOURCE_RESPONSE_MANIFEST_SHA256,
        "cache": CACHE,
        "include_gap_fetches": False,
        "panel_end_utc": PANEL_END_UTC,
        "n_panel_rows": len(fixtures),
        "n_history_matches_loaded": len(history),
        "n_stats_conflicts": hmeta["n_stats_conflicts"],
        "selection_policy": "NO_NEW_PRE_OOS_PRUNING; frozen 60% training-fold coverage screen remains",
        "near_duplicate_policy": "REPORT_ONLY",
        "style_strength_policy": "REPORT_ONLY; strength never enters similarity distance",
        "summary": summary,
        "family_summary": fam,
        "templates": per_template,
        "near_duplicate_pairs": near,
        "target_outcomes_read": False,
        "market_results_read": False,
        "model_fit": False,
        "oos_executed": False,
    }
    diag_path = OUT / OUTPUTS[0]
    diag_sha = dump(diag_path, doc)
    audit_path = OUT / OUTPUTS[1]
    audit_path.write_text(audit_md(doc))
    audit_sha = fsha(audit_path)
    manifest = {
        "artifact_version": "sol_panel_support_freeze_manifest_v1",
        "authorized_execution_head": head,
        "source_novelty_commit": SOURCE_NOVELTY_COMMIT,
        "source_registry_sha256": SOURCE_REGISTRY_SHA256,
        "diagnostics_sha256": diag_sha,
        "audit_sha256": audit_sha,
        "n_templates": 124,
        "summary": summary,
        "champion_sha256": fsha(CHAMPION),
        "target_outcomes_read": False,
        "market_results_read": False,
        "model_fit": False,
        "oos_executed": False,
        "next_gate": "FREEZE_OUTPUT_COMMIT_THEN_REVIEW_SUPPORT_BEFORE_OOS",
    }
    man_sha = dump(OUT / OUTPUTS[2], manifest)
    print(json.dumps({"status": "SUPPORT_DIAGNOSTICS_COMPLETE",
                      "authorized_execution_head": head,
                      "diagnostics_sha256": diag_sha,
                      "audit_sha256": audit_sha,
                      "manifest_sha256": man_sha,
                      "summary": summary,
                      "target_outcomes_read": False,
                      "model_fit": False, "oos_executed": False}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
