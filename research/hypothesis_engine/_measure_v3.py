"""Deterministic historical measurement of the frozen V3 hypothesis corpus. ZERO SPEND.

No Bedrock import anywhere in the chain. Reads the immutable V3 outputs and the PIT-safe
dual-provider corpus, and writes descriptive measurements only. Nothing here trains a
model, touches CHAMPION or `p_model`, reads a price, or promotes a feature.
"""
from __future__ import annotations

import json
import math
import os
import sys
from collections import Counter, defaultdict

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")
sys.path.insert(0, ROOT)

from research.hypothesis_engine import (capability, cohort_measurement as CM,
                                        corpus_adapter as CA, query_plan, similarity,
                                        vocabulary)
from research.hypothesis_engine import context_packet as CP

OUT = f"{ROOT}/research/hypothesis_engine/out/v3_hypothesis_measurement"
PKT = f"{ROOT}/research/hypothesis_engine/out/MATERIALIZED_PACKETS_sonnet46_v3.json"

#: Metrics this corpus can actually read. A metric outside this map is typed
#: UNSUPPORTED_METRIC -- never silently replaced by a convenient proxy.
SUPPORTED_BY_CORPUS = set(CA._METRIC_SOURCE)


# ======================================================================================
# Fixture resolution + observation building
# ======================================================================================
class FixtureWorld:
    """Everything the measurement layer needs for ONE target fixture, all PIT-filtered."""

    def __init__(self, index: CA.HistoryIndex, target: CA.MC.MatchRecord):
        self.index = index
        self.target = target
        self.cutoff = int(target.kickoff_unix)
        self.competition = target.competition
        self._obs_cache: dict = {}
        self._axis_cache: dict = {}
        self._league_cache: dict = {}
        self._cands = None

    # ---- subject history -------------------------------------------------------------
    def observations(self, team: str, metric: str, side: str) -> list:
        key = (team, metric, side)
        if key in self._obs_cache:
            return self._obs_cache[key]
        out = []
        for r in self.index.prior(team, self.cutoff):
            if r.fixture_id == self.target.fixture_id:      # never the target fixture
                continue
            out.append(CM.Obs(
                fixture_id=r.fixture_id,
                kickoff_unix=r.kickoff_unix,
                competition=r.competition,
                opponent=(r.away if r.home == team else r.home),
                value=CA.team_value(r, team, metric, side),
                dimensions={
                    "venue": "HOME" if r.home == team else "AWAY",
                    "own_formation_family": CA.team_formation_family(r, team),
                    "opponent_formation_family": CA.team_formation_family(
                        r, team, opponent=True),
                }))
        self._obs_cache[key] = out
        return out

    # ---- competition-wide population -------------------------------------------------
    def league_values(self, metric: str, side: str) -> list:
        key = (metric, side)
        if key in self._league_cache:
            return self._league_cache[key]
        vals = []
        for r in self.index.records:
            if r.competition != self.competition or r.kickoff_unix >= self.cutoff:
                continue
            if r.fixture_id == self.target.fixture_id:
                continue
            for team in (r.home, r.away):
                vals.append(CA.team_value(r, team, metric, side))
        self._league_cache[key] = vals
        return vals

    # ---- opponent banding ------------------------------------------------------------
    def candidates(self) -> list:
        """Every club with matches in the target competition strictly before the cutoff.

        Competition-wide, not the subject's own opponent list, so a band means "top /
        middle / bottom third of THIS competition" and is comparable across subjects.
        """
        if self._cands is None:
            s = set()
            for r in self.index.records:
                if r.competition == self.competition and r.kickoff_unix < self.cutoff:
                    s.update((r.home, r.away))
            self._cands = sorted(s)
        return self._cands

    def axis_value_fn(self, metric: str, side: str):
        def fn(team: str, cutoff_unix: int):
            key = (team, metric, side, cutoff_unix)
            if key in self._axis_cache:
                return self._axis_cache[key]
            vals = []
            for r in self.index.prior(team, cutoff_unix):
                if r.fixture_id == self.target.fixture_id:
                    continue
                v = CA.team_value(r, team, metric, side)
                if v is not None:
                    vals.append(v)
            got = (sum(vals) / len(vals), len(vals)) if vals else None
            self._axis_cache[key] = got
            return got
        return fn

    def band_resolver(self):
        def resolve(axis: str, band: str, cutoff_unix: int):
            ms = CM.axis_to_metric_side(axis)
            metric, side = ms
            return similarity.resolve_band(
                axis=axis, requested_band=band, cutoff_unix=cutoff_unix,
                candidates=self.candidates(),
                axis_value_fn=self.axis_value_fn(metric, side))
        return resolve


# ======================================================================================
# Main
# ======================================================================================
def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    corpus = json.load(open(f"{OUT}/frozen_hypothesis_corpus.json"))
    packets = json.load(open(PKT))
    index = CA.load_index()
    by_id = {r.fixture_id: r for r in index.records}

    worlds: dict = {}
    specs_out, meas_out = [], []
    funnel = Counter()
    compile_failures = []
    pit = {"checked": 0, "violations": [], "target_fixture_in_cohort": 0,
           "max_observed_kickoff_vs_cutoff": []}

    # ---- one pass over the frozen corpus ---------------------------------------------
    for rec in corpus["included"]:
        h = rec["hypothesis"]
        fid = rec["fixture_id"]
        packet = packets[f"reference::{fid}"]
        target = by_id[fid]
        world = worlds.setdefault(fid, FixtureWorld(index, target))
        cutoff = int(packet["information_cutoff_unix"])
        funnel["v3_valid_hypotheses"] += 1

        # frozen compiler, unchanged
        results = query_plan.compile_hypothesis(
            h, fixture_id=fid, cutoff_unix=cutoff,
            manifest=_manifest_of(packet))

        for res in results:
            if not res.ok:
                funnel["compile_failed"] += 1
                compile_failures.append({"fixture_id": fid,
                                         "hypothesis_id": h["hypothesis_id"],
                                         "failure": res.failure,
                                         "reasons": res.reasons})
                continue
            funnel["compilable_query_plans"] += 1
            plan = res.plan
            subject_team = target.home if plan.subject == "HOME_TEAM" else target.away

            if plan.metric not in SUPPORTED_BY_CORPUS:
                funnel["unsupported_by_corpus"] += 1
                spec = CM.build_spec(plan, subject_team=subject_team,
                                     target_competition=target.competition,
                                     required_fields=())
                specs_out.append(spec.to_dict())
                meas_out.append(CM.CohortMeasurement(
                    spec, CM.UNSUPPORTED_METRIC,
                    notes=[f"metric {plan.metric!r} has no reader in the corpus adapter; "
                           f"no proxy substituted"]).to_dict())
                continue

            src = CA._METRIC_SOURCE[plan.metric]
            spec = CM.build_spec(plan, subject_team=subject_team,
                                 target_competition=target.competition,
                                 required_fields=tuple(str(x) for x in src))
            specs_out.append(spec.to_dict())

            hist = world.observations(subject_team, plan.metric, plan.side)
            pit["checked"] += 1
            bad = [o for o in hist if o.kickoff_unix >= cutoff]
            if bad:
                pit["violations"].append({"hypothesis_id": h["hypothesis_id"],
                                          "fixture_id": fid, "n": len(bad)})
            if any(o.fixture_id == fid for o in hist):
                pit["target_fixture_in_cohort"] += 1
            if hist:
                pit["max_observed_kickoff_vs_cutoff"].append(
                    max(o.kickoff_unix for o in hist) - cutoff)

            m = CM.execute(
                spec, subject_history=hist,
                league_values=(world.league_values(plan.metric, plan.side)
                               if plan.comparison == "LEAGUE_ENVIRONMENT_BASELINE"
                               else None),
                band_resolver=world.band_resolver())
            funnel[f"outcome_{m.outcome}"] += 1
            if m.outcome in (CM.MEASURED, CM.INSUFFICIENT_DATA, CM.NOT_DISTINCT):
                funnel["historically_measurable"] += 1
            if m.outcome == CM.MEASURED:
                funnel["sufficient_data_and_distinct"] += 1
            d = m.to_dict()
            d["hypothesis_id"] = h["hypothesis_id"]
            d["seq"] = rec["seq"]
            d["research_family"] = h.get("research_family")
            d["question"] = h.get("question")
            meas_out.append(d)

    _write(f"{OUT}/measurement_specs.json", specs_out)
    _write(f"{OUT}/cohort_measurements.json", meas_out)

    # ---- PIT audit -------------------------------------------------------------------
    pit["max_delta_seconds"] = (max(pit["max_observed_kickoff_vs_cutoff"])
                                if pit["max_observed_kickoff_vs_cutoff"] else None)
    pit.pop("max_observed_kickoff_vs_cutoff")
    pit["clean"] = (not pit["violations"]) and pit["target_fixture_in_cohort"] == 0
    _write(f"{OUT}/pit_audit.json", pit)

    # ---- duplicates / equivalence ----------------------------------------------------
    dup = _duplicate_analysis(specs_out, corpus, packets, by_id)
    _write(f"{OUT}/duplicate_analysis.json", dup)

    # ---- family diagnostics ----------------------------------------------------------
    fam = _family_diagnostics(corpus, meas_out)
    _write(f"{OUT}/family_diagnostics.json", fam)

    # ---- distributions ---------------------------------------------------------------
    dist = _distributions(meas_out)
    _write(f"{OUT}/n_and_coverage_distributions.json", dist)

    # ---- funnel ----------------------------------------------------------------------
    f = dict(funnel)
    # The final funnel stage counts DISTINCT plan keys among plans that actually
    # measured -- not every compiled plan, and not plans whose conditional cohort was
    # identical to their comparison cohort.
    f["distinct_research_comparisons"] = len(
        {_plan_key(m["spec"]) for m in meas_out if m["outcome"] == CM.MEASURED})
    f["compile_failures"] = compile_failures
    _write(f"{OUT}/funnel.json", f)

    # ---- confounders -----------------------------------------------------------------
    _write(f"{OUT}/confounder_inventory.json", _confounders(corpus, fam))

    # ---- seq 8 multi-condition -------------------------------------------------------
    _write(f"{OUT}/seq8_multicondition.json",
           [m for m in meas_out if m["seq"] == 8 and m.get("hypothesis_id") == "H6"])

    print(f"specs={len(specs_out)} measurements={len(meas_out)}")
    print("funnel:", json.dumps({k: v for k, v in sorted(f.items())
                                 if isinstance(v, int)}, indent=1))
    print("PIT clean:", pit["clean"])
    return 0


def _manifest_of(packet):
    cm = packet["capability_manifest"]
    return capability.FixtureCapabilityManifest(
        fixture_id=cm["fixture_id"],
        available_metrics=tuple(cm["available_metrics"]),
        available_dimensions=tuple(cm["available_dimensions"]),
        unsupported_context=dict(cm.get("unsupported_context") or {}),
        coverage=dict(cm.get("coverage") or {}),
        notes=tuple(cm.get("notes") or ()))


def _plan_key(s: dict) -> str:
    return "|".join(str(s[k]) for k in (
        "fixture_id", "subject_label", "target_metric", "side", "window", "period",
        "venue", "competition", "own_formation_family", "opponent_formation_family",
        "opponent_profile_band", "opponent_profile_axis", "comparison_cohort"))


def _duplicate_analysis(specs, corpus, packets, by_id) -> dict:
    keys = Counter(_plan_key(s) for s in specs)
    within = {k: n for k, n in keys.items() if n > 1}

    # same-input agreement: the repeatability arm re-sent 6 of the frozen packets.
    rep = json.load(open(f"{OUT}/repeatability_payloads.json"))
    rep_keys: dict = defaultdict(set)
    for r in rep:
        fid = r["fixture_id"]
        target = by_id[fid]
        packet = packets[f"reference::{fid}"]
        for h in r["hypotheses"]:
            for res in query_plan.compile_hypothesis(
                    h, fixture_id=fid,
                    cutoff_unix=int(packet["information_cutoff_unix"]),
                    manifest=_manifest_of(packet)):
                if res.ok:
                    rep_keys[fid].add(_plan_key(CM.build_spec(
                        res.plan, subject_team="X", target_competition=target.competition,
                        required_fields=()).to_dict()))

    ref_keys: dict = defaultdict(set)
    for s in specs:
        ref_keys[s["fixture_id"]].add(_plan_key(s))

    overlap = []
    for fid, rk in sorted(rep_keys.items()):
        base = ref_keys.get(fid, set())
        inter = len(base & rk)
        union = len(base | rk)
        overlap.append({"fixture_id": fid, "reference_plan_keys": len(base),
                        "repeatability_plan_keys": len(rk),
                        "shared": inter,
                        "jaccard": round(inter / union, 4) if union else 0.0})

    return {
        "n_plans": len(specs),
        "n_distinct_plan_keys_measured": len(keys),
        "duplicate_rate": round(1 - len(keys) / len(specs), 4) if specs else 0.0,
        "n_duplicate_keys": len(within),
        "duplicated_keys": dict(sorted(within.items(), key=lambda kv: -kv[1])[:20]),
        "same_input_plan_overlap": overlap,
        "same_input_mean_jaccard": round(
            sum(o["jaccard"] for o in overlap) / len(overlap), 4) if overlap else None,
    }


_CONDITION_FAMILY_ORDER = (
    ("meaningful_multi_condition", None),
    ("opponent_profile", "opponent_profile"),
    ("formation", "formation"),
    ("venue", "venue"),
    ("unconditional_behavioral_profile", None),
)

#: The one hypothesis the frozen V3 classifier accepted as meaningfully multi-condition.
MEANINGFUL_MULTI = {(8, "H6")}


def _condition_family(rec) -> str:
    h = rec["hypothesis"]
    if (rec["seq"], h["hypothesis_id"]) in MEANINGFUL_MULTI:
        return "meaningful_multi_condition"
    dims = {c["dimension"] for c in (h.get("conditions") or [])}
    if not dims:
        return "unconditional_behavioral_profile"
    if "opponent_profile" in dims:
        return "opponent_profile"
    if dims & {"own_formation_family", "opponent_formation_family"}:
        return "formation"
    if dims == {"venue"}:
        return "venue"
    return "other"


_METRIC_FAMILY = {
    "total_shots": "SHOT_VOLUME", "shots_on_target": "SHOT_QUALITY",
    "shots_inside_box": "SHOT_QUALITY", "big_chances": "SHOT_QUALITY",
    "touches_in_box": "TERRITORY", "final_third_entries": "TERRITORY",
    "possession": "TERRITORY", "corners": "SET_PIECE",
    "accurate_crosses": "SET_PIECE", "goals": "OUTCOME",
    "yellow_cards": "DISCIPLINE", "fouls": "DISCIPLINE",
    "tackles": "DEFENSIVE_ACTION", "interceptions": "DEFENSIVE_ACTION",
    "clearances": "DEFENSIVE_ACTION",
}


def _family_diagnostics(corpus, meas) -> dict:
    by_hyp = defaultdict(list)
    for m in meas:
        if "hypothesis_id" in m:
            by_hyp[(m["seq"], m["hypothesis_id"])].append(m)

    groups: dict = {"condition_family": defaultdict(list),
                    "research_family": defaultdict(list),
                    "metric_family": defaultdict(list),
                    "comparison_type": defaultdict(list)}

    for rec in corpus["included"]:
        h = rec["hypothesis"]
        ms = by_hyp.get((rec["seq"], h["hypothesis_id"]), [])
        groups["condition_family"][_condition_family(rec)].append(ms)
        groups["research_family"][h["research_family"]].append(ms)
        groups["comparison_type"][h["comparison"]].append(ms)
        for mf in sorted({_METRIC_FAMILY.get(t, "OTHER")
                          for t in (h.get("target_metrics") or [])}):
            groups["metric_family"][mf].append(ms)

    out: dict = {}
    for gname, g in groups.items():
        out[gname] = {}
        for key, entries in sorted(g.items()):
            plans = [m for ms in entries for m in ms]
            measured = [m for m in plans if m["outcome"] == CM.MEASURED]
            ns = [m["conditional"]["usable_n"] for m in measured]
            covs = [m["conditional"]["coverage_rate"] for m in plans
                    if m.get("conditional")]
            out[gname][key] = {
                "n_hypotheses_generated": len(entries),
                "n_query_plans": len(plans),
                "n_measured": len(measured),
                "measurable_rate": round(len(measured) / len(plans), 4) if plans else 0.0,
                "n_insufficient_data": sum(1 for m in plans
                                           if m["outcome"] == CM.INSUFFICIENT_DATA),
                "n_not_distinct": sum(1 for m in plans
                                      if m["outcome"] == CM.NOT_DISTINCT),
                "n_unsupported": sum(1 for m in plans
                                     if m["outcome"] in CM.UNSUPPORTED_OUTCOMES),
                "unsupported_rate": round(
                    sum(1 for m in plans if m["outcome"] in CM.UNSUPPORTED_OUTCOMES)
                    / len(plans), 4) if plans else 0.0,
                "conditional_n": _five_num(ns),
                "mean_conditional_coverage": round(sum(covs) / len(covs), 4) if covs else None,
            }
    return out


def _five_num(xs) -> dict:
    if not xs:
        return {"n": 0}
    s = sorted(xs)
    return {"n": len(s), "min": s[0], "p25": s[int(0.25 * (len(s) - 1))],
            "median": s[len(s) // 2], "p75": s[int(0.75 * (len(s) - 1))], "max": s[-1],
            "mean": round(sum(s) / len(s), 3)}


def _distributions(meas) -> dict:
    cond = [m["conditional"]["usable_n"] for m in meas if m.get("conditional")]
    comp = [m["comparison"]["usable_n"] for m in meas if m.get("comparison")]
    cov = [m["conditional"]["coverage_rate"] for m in meas if m.get("conditional")]
    rel = Counter(m["conditional"]["reliability"] for m in meas if m.get("conditional"))
    return {
        "conditional_usable_n": _five_num(cond),
        "comparison_usable_n": _five_num(comp),
        "conditional_coverage_rate": _five_num(cov),
        "conditional_reliability_bands": dict(rel),
        "conditional_n_histogram": dict(sorted(Counter(cond).items())),
        "canonical_thresholds_used": CM.CANONICAL_CONVENTION_SOURCES,
    }


_CONFOUNDER_LIBRARY = {
    "venue": ["opponent strength", "team strength", "competition",
              "schedule congestion", "score state"],
    "opponent_profile": ["opponent strength (band axis is behavioural, not strength)",
                         "venue", "team strength", "competition", "score state",
                         "band drift: bands resolved AS_OF_TARGET_CUTOFF, not per match"],
    "formation": ["manager/tactical regime", "opponent strength", "venue",
                  "formation selection is endogenous to expected opponent",
                  "lineup availability / injuries", "score state"],
    "meaningful_multi_condition": ["all confounders of both constituent dimensions",
                                   "cohort thinning (interaction cells are small)"],
    "unconditional_behavioral_profile": ["team strength", "opponent strength", "venue",
                                         "competition", "season/regime drift"],
    "other": ["opponent strength", "venue", "competition"],
}


def _confounders(corpus, fam) -> dict:
    out = {"association_type_now": "DESCRIPTIVE_ASSOCIATION",
           "association_type_later": "CONFOUNDER_ADJUSTED_EFFECT",
           "causality_claimed": False,
           "families": {}}
    seen = Counter()
    for rec in corpus["included"]:
        seen[_condition_family(rec)] += 1
        for c in (rec["hypothesis"].get("candidate_confounders") or []):
            seen[f"__llm_named__{c}"] += 1
    for f in sorted(k for k in seen if not k.startswith("__llm_named__")):
        out["families"][f] = {
            "n_hypotheses": seen[f],
            "confounders_the_next_stage_must_adjust_for": _CONFOUNDER_LIBRARY.get(
                f, _CONFOUNDER_LIBRARY["other"]),
        }
    out["confounders_named_by_the_model_itself"] = {
        k.replace("__llm_named__", ""): v
        for k, v in sorted(seen.items(), key=lambda kv: -kv[1])
        if k.startswith("__llm_named__")}
    return out


def _write(path, obj):
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=True, default=str)


if __name__ == "__main__":
    raise SystemExit(main())
