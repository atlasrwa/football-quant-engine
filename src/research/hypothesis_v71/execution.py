"""V7.1 confirmatory execution path (`v71_execution_v1`). Sections 21, 22.

The SCIENTIFIC machinery of the confirmatory run, decomposed into five pure stages that are
callable on ANY fold positions -- synthetic, development or (after a separate authorization)
the fresh confirmatory sample:

    prepare_execution(...)        -> ExecutionPlan     (specs, IRs, folds, matching, clusters)
    evaluate_family_evidence(...) -> per-family evidence over the given fold positions
    aggregate_endpoints(...)      -> Endpoint A, Endpoint B, stability, multiplicity, candidates
    persist_evidence(...)         -> per-family evidence flushed to disk BEFORE any aggregate
    finalize_result(...)          -> the final experiment result + hashed evidence bundle

These functions know NOTHING about authorization. The authorization gate lives entirely in the
driver (`_v71_execute.py`); the future authorized run calls EXACTLY these functions on the
fresh fold positions with no code change. There is no separate "real-run-only" aggregation.

Every function is outcome-agnostic: it computes whatever effects the folds it is handed
support. It is the CALLER's responsibility (the driver's authorization gate) to decide which
folds may be handed in. That separation is what lets the whole path be exercised end to end on
development and synthetic data without ever opening the fresh sample.

ZERO SPEND. No network. No CHAMPION write. Imports no cloud module.
"""
from __future__ import annotations

import collections
import hashlib
import json
import os
from dataclasses import dataclass

from . import capability as CAP
from . import engine as EN
from . import estimator as ES
from . import invariants as INV
from . import ir as IRM
from . import matching as MATCH
from . import similarity as SIM
from src.research.hypothesis_v7 import analysis_spec as V7A
from src.research.hypothesis_v7 import endpoints as V7EP

EXECUTION_VERSION = "v71_execution_v1"

#: Every artifact this path writes carries one of these classifications. A run over anything
#: other than the authorized fresh sample is DEVELOPMENT_ONLY / SYNTHETIC_ONLY, and the driver
#: stamps CONFIRMATORY only when it has verified an authorization token.
CLASS_DEVELOPMENT = "DEVELOPMENT_ONLY"
CLASS_SYNTHETIC = "SYNTHETIC_ONLY"
CLASS_CONFIRMATORY = "CONFIRMATORY"
NON_CONFIRMATORY = "NON_CONFIRMATORY"

PROFILE_AXES = ("goals_for", "goals_against", "shots_on_target_for",
                "shots_on_target_against", "possession_for", "shots_against")


# ======================================================================================
# stage 0: plan
# ======================================================================================
@dataclass
class FamilySpec:
    """One evaluable family (treated or control), with its rebuilt IR and admissible set."""
    cid: str
    arm: str                       # "LLM" or "NULL"
    spec: dict
    ir: object
    admissible: tuple
    capability_status: str
    research_family: str
    multiplicity_family: str


@dataclass
class ExecutionPlan:
    classification: str
    treated: list                  # list[FamilySpec] evaluable LLM families
    controls: dict                 # cid -> FamilySpec for every matched control id
    uniform: list                  # list[FamilySpec] evaluable uniform-null families (Endpoint A)
    all_treated_rows: list         # every canonical LLM row (measurable or not) for Endpoint A
    all_uniform_rows: list         # every uniform-null row for Endpoint A
    folds: list                    # [{"fold_index", "positions"}]
    matching: dict                 # frozen matching assignments + control weights
    ctx: object                    # engine.Context
    capability: object
    engine_spec_hash: str


def build_context(index):
    """Point-in-time terciles + similarity, built once from the whole index's early frontier.

    Identical construction to the diagnostic replay and the test fixtures, so a family scored
    here is scored the way every other stage of the apparatus scores it.
    """
    cut = index.kick[int(len(index.kick) * 0.7)] if index.kick else 0
    ter, cache = {}, {}
    for axis in PROFILE_AXES:
        metric, side = INV.axis_metric_perspective(axis)
        if metric not in index.metrics:
            continue
        by_comp = {}
        for tid, s in index.series.items():
            pre = [e for e in s if e[1] < cut]
            if len(pre) < 6:
                continue
            vals = [index.team_value(i, tid, metric, side) for (i, _k, _c, _h, _o) in pre]
            vals = [v for v in vals if v is not None]
            if not vals:
                continue
            mv = sum(vals) / len(vals)
            cache[(tid, axis)] = mv
            by_comp.setdefault(pre[-1][2], []).append(mv)
        for comp, xs in by_comp.items():
            xs.sort()
            if len(xs) >= 3:
                ter[(comp, axis)] = (xs[len(xs) // 3], xs[2 * len(xs) // 3])
    return EN.Context(index, ter, cache, SIM.SimilarityEngine(index))


def _family_spec(cid, arm, spec, capability):
    ir = IRM.build_ir(spec)
    status, adm, _d = capability.classify_metrics(ir.target_metrics)
    rf = ir.research_family
    return FamilySpec(cid=cid, arm=arm, spec=spec, ir=ir, admissible=tuple(sorted(adm)),
                      capability_status=status, research_family=rf,
                      multiplicity_family=V7A.multiplicity_family_of(rf))


def _evaluable(fs) -> bool:
    inv = INV.check(fs.ir, capability=None)
    return (fs.ir.status == IRM.OK and inv["ok"]
            and fs.capability_status in (CAP.SUPPORTED, CAP.RESTRICTED))


def prepare_execution(index, fold_positions, *, treated_specs, uniform_specs,
                      marginal_specs, matching, capability, classification):
    """Assemble everything a run needs, WITHOUT computing an effect.

    `treated_specs`  : {cid: spec} for every canonical LLM family (measurable or not).
    `uniform_specs`  : {cid: spec} for the uniform-grammar control (Endpoint A denominator).
    `marginal_specs` : {null_id: spec} for the marginal control pool (Endpoint B controls).
    `matching`       : the frozen V7_1_MATCHING assignments + control_weights.
    `fold_positions` : [{"fold_index", "positions"}] -- the ONLY thing that differs between a
                       synthetic, development and confirmatory run.
    """
    ctx = build_context(index)

    treated, all_treated_rows = [], []
    for cid, spec in sorted(treated_specs.items()):
        fs = _family_spec(cid, "LLM", spec, capability)
        all_treated_rows.append({"cid": cid, "arm": "LLM",
                                 "capability_status": fs.capability_status,
                                 "research_family": fs.research_family,
                                 "multiplicity_family": fs.multiplicity_family,
                                 "evaluable": _evaluable(fs)})
        if _evaluable(fs):
            treated.append(fs)

    uniform, all_uniform_rows = [], []
    for cid, spec in sorted(uniform_specs.items()):
        fs = _family_spec(cid, "NULL", spec, capability)
        all_uniform_rows.append({"cid": cid, "arm": "NULL",
                                 "capability_status": fs.capability_status,
                                 "research_family": fs.research_family,
                                 "multiplicity_family": fs.multiplicity_family,
                                 "evaluable": _evaluable(fs)})
        if _evaluable(fs):
            uniform.append(fs)

    # Only the control specs actually referenced by the frozen matching are rebuilt.
    needed_control_ids = {c for a in matching["assignments"] if a["tier"] != MATCH.NO_MATCH
                          for c in a["control_ids"]}
    controls = {}
    for nid in sorted(needed_control_ids):
        spec = marginal_specs.get(nid)
        if spec is None:
            continue
        controls[nid] = _family_spec(nid, "NULL", spec, capability)

    return ExecutionPlan(
        classification=classification, treated=treated, controls=controls,
        uniform=uniform, all_treated_rows=all_treated_rows,
        all_uniform_rows=all_uniform_rows, folds=fold_positions, matching=matching,
        ctx=ctx, capability=capability, engine_spec_hash=EN.spec_hash())


# ======================================================================================
# stage 1: per-family evidence
# ======================================================================================
def evaluate_family_evidence(fs, plan):
    """Score ONE family over the plan's fold positions. The single scientific measurement.

    Returns a durable per-family record: the terminal state, the OOS score components, the
    per-fold and per-competition cells, and the support/attrition accounting. Reads only
    strictly-prior observations (the compiler's structural PIT guarantee).
    """
    folds = plan.folds
    restrict = fs.admissible or None
    ev = EN.evaluate_family(fs.ir, folds, plan.ctx.index, plan.ctx, plan.capability,
                            restrict_to=restrict)
    sc = EN.score_family(ev)
    allc = [c for b in ev["per_metric"].values()
            for c in b["cells"] + b.get("competition_cells", [])]
    record = {
        "canonical_hypothesis_id": fs.cid,
        "arm": fs.arm,
        "ir_id": fs.ir.ir_id(),
        "research_family": fs.research_family,
        "multiplicity_family": fs.multiplicity_family,
        "capability_status": fs.capability_status,
        "admissible_competitions": list(fs.admissible),
        "n_fold_cells": sum(len(b["cells"]) for b in ev["per_metric"].values()),
        "n_fold_cells_with_effect": sum(
            1 for b in ev["per_metric"].values() for c in b["cells"]
            if c["effect"] is not None),
        "contrastless_cells": sum(1 for c in allc if c.get("contrastless")),
        "confounded_cells": sum(1 for c in allc if c.get("confounded_unresolved")),
        "rows_missing_required_confounder": sum(
            c.get("n_rows_missing_required_confounder", 0) or 0 for c in allc),
        "cells_failed_after_missing_confounder": sum(
            1 for c in allc if c.get("insufficient_after_missing_confounder")),
        "score": None,
        "terminal_state": None,
    }
    if sc is None:
        record["terminal_state"] = (
            EN.CONFOUNDED_UNRESOLVED if record["confounded_cells"]
            else EN.INSUFFICIENT_SUPPORT)
    else:
        record["score"] = {
            "oos_quality_score": sc["oos_quality_score"],
            "direction_agreement": sc["direction_agreement"],
            "competition_direction_agreement": sc["competition_direction_agreement"],
            "mean_fold_effect": sc["mean_fold_effect"],
            "se": sc["se"], "n_folds": sc["n_folds"], "p_value": sc["p_value"]}
        # FDR is decided at the multiplicity stage; the per-family terminal state uses the
        # pre-FDR classification and is upgraded to CANDIDATE only in aggregate_endpoints.
        record["terminal_state"] = EN.terminal_state(
            ir_ok=True, invariant_ok=True, capability_status=fs.capability_status,
            evidence=ev, score=sc, fdr_rejected=False)
    return record


# ======================================================================================
# stage 2: endpoints
# ======================================================================================
def _yield_ladder(rows, family_records):
    """The Endpoint-A attrition ladder for one arm: canonical -> measurable -> supported ->
    surviving. `family_records` maps cid -> per-family record for the evaluable subset."""
    n_canonical = len(rows)
    n_measurable = sum(1 for r in rows if r["evaluable"])
    supported, surviving = 0, 0
    for r in rows:
        rec = family_records.get(r["cid"])
        if rec is None:
            continue
        if rec["terminal_state"] not in (EN.INSUFFICIENT_SUPPORT, EN.CONFOUNDED_UNRESOLVED,
                                         EN.UNMEASURABLE, EN.STRUCTURALLY_INVALID,
                                         EN.SEMANTICALLY_AMBIGUOUS):
            supported += 1
        if rec["terminal_state"] in (EN.OOS_SURVIVES, EN.CANDIDATE_FEATURE_ELIGIBLE):
            surviving += 1
    return V7EP.attrition_ladder(n_canonical, n_measurable, supported) | {
        "oos_survives": surviving, "oos_stage_computed": True}


def _multiplicity(treated_records):
    """Apply the frozen family-level FDR + shrinkage to the treated families, clustered on the
    frozen MULTIPLICITY_FAMILY. Returns per-family FDR decisions and the cluster count."""
    scored = [(cid, r) for cid, r in sorted(treated_records.items())
              if r["score"] and r["score"]["p_value"] is not None]
    if not scored:
        return {"n_scored": 0, "n_clusters": 0, "rejected": {}, "clusters": {}}
    by_family = collections.defaultdict(list)
    for cid, r in scored:
        by_family[r["multiplicity_family"]].append((cid, r))
    rejected = {}
    for fam, members in sorted(by_family.items()):
        pvals = [r["score"]["p_value"] for _cid, r in members]
        flags = ES.benjamini_hochberg(pvals, V7A.FDR_Q)
        for (cid, _r), rej in zip(members, flags):
            rejected[cid] = bool(rej)
    return {"n_scored": len(scored), "n_clusters": len(by_family),
            "fdr_q": V7A.FDR_Q, "method": V7A.MULTIPLICITY_METHOD,
            "rejected": rejected,
            "clusters": {k: sorted(cid for cid, _ in v) for k, v in sorted(by_family.items())}}


def aggregate_endpoints(plan, treated_records, control_records, uniform_records):
    """Endpoint A, Endpoint B, stability views, multiplicity and the candidate set.

    treated_records / control_records / uniform_records map cid -> per-family record.
    No LLM is involved; every number is produced by the deterministic engine + estimator.
    """
    # ---- multiplicity FIRST: it decides CANDIDATE eligibility -----------------------
    mult = _multiplicity(treated_records)
    for cid, rec in treated_records.items():
        if rec["score"] and rec["terminal_state"] in (EN.OOS_SURVIVES,
                                                       EN.CANDIDATE_FEATURE_ELIGIBLE):
            rec["fdr_rejected"] = mult["rejected"].get(cid, False)
            rec["terminal_state"] = (EN.CANDIDATE_FEATURE_ELIGIBLE
                                     if rec["fdr_rejected"] else EN.OOS_SURVIVES)

    # ---- Endpoint A: end-to-end yield, per arm, NOT matched, includes unmeasurable ---
    endpoint_a = {
        "endpoint_id": V7EP.END_TO_END["endpoint_id"],
        "classification": [plan.classification, NON_CONFIRMATORY],
        "llm": _yield_ladder(plan.all_treated_rows, treated_records),
        "uniform_null": _yield_ladder(plan.all_uniform_rows, uniform_records),
        "denominator": V7EP.END_TO_END["denominator"],
        "matched": False,
    }
    a_llm, a_null = endpoint_a["llm"], endpoint_a["uniform_null"]
    ES.assert_rate("oos_surviving_rate", a_llm["oos_survives"], a_llm["canonical"],
                   a_llm["oos_survives"] / max(a_llm["canonical"], 1))
    endpoint_a["llm_surviving_rate"] = a_llm["oos_survives"] / max(a_llm["canonical"], 1)
    endpoint_a["uniform_surviving_rate"] = a_null["oos_survives"] / max(a_null["canonical"], 1)
    endpoint_a["surviving_rate_difference"] = (endpoint_a["llm_surviving_rate"]
                                               - endpoint_a["uniform_surviving_rate"])

    # ---- Endpoint B: matched, OOS_QUALITY_SCORE difference, sign-flip cluster inference
    diffs, clusters, per_pair = [], [], []
    for a in plan.matching["assignments"]:
        if a["tier"] == MATCH.NO_MATCH:
            continue
        cid = a["canonical_hypothesis_id"]
        trec = treated_records.get(cid)
        if not trec or not trec["score"]:
            continue
        # weighted control OOS score: total control weight per treated family is exactly 1,
        # so the control contributes ONE number, never len(control_ids) votes.
        w = a["weight_per_control"]
        cvals = [(control_records[c]["score"]["oos_quality_score"], w)
                 for c in a["control_ids"]
                 if c in control_records and control_records[c]["score"]]
        if not cvals:
            continue
        wsum = sum(wt for _v, wt in cvals)
        control_score = sum(v * wt for v, wt in cvals) / wsum if wsum > 0 else 0.0
        diff = trec["score"]["oos_quality_score"] - control_score
        diffs.append(diff)
        clusters.append(trec["multiplicity_family"])
        per_pair.append({"canonical_hypothesis_id": cid,
                         "multiplicity_family": trec["multiplicity_family"],
                         "llm_oos_quality_score": trec["score"]["oos_quality_score"],
                         "weighted_control_oos_quality_score": control_score,
                         "difference": diff, "n_controls": len(cvals)})

    # the experimental unit is the canonical family; repeated control rows may not inflate it
    ES.assert_unit_not_inflated(len(per_pair),
                                [p["canonical_hypothesis_id"] for p in per_pair])
    inference = (ES.small_cluster_inference(diffs, clusters) if diffs
                 else {"primary_p_value": None, "n_clusters": 0,
                       "inference_status": "NO_MATCHED_PAIRS"})
    endpoint_b = {
        "endpoint_id": V7EP.CONDITIONAL_SIGNAL["endpoint_id"],
        "classification": [plan.classification, NON_CONFIRMATORY],
        "primary_statistic": "OOS_QUALITY_SCORE_DIFFERENCE",
        "n_matched_pairs": len(per_pair),
        "mean_difference": (sum(diffs) / len(diffs)) if diffs else None,
        "inference": inference,
        "cluster_unit": ES.CLUSTER_UNIT,
        "per_pair": per_pair,
        "matched": True,
    }

    # ---- candidate set ---------------------------------------------------------------
    candidates = sorted(cid for cid, r in treated_records.items()
                        if r["terminal_state"] == EN.CANDIDATE_FEATURE_ELIGIBLE)
    return {
        "endpoint_a": endpoint_a,
        "endpoint_b": endpoint_b,
        "multiplicity": mult,
        "fold_stability": _stability(treated_records, "direction_agreement"),
        "competition_stability": _stability(treated_records,
                                            "competition_direction_agreement"),
        "candidate_feature_set": candidates,
        "candidate_feature_promotion": False,     # promotion is a separate, later decision
    }


def _stability(treated_records, key):
    vals = [r["score"][key] for r in treated_records.values()
            if r["score"] and r["score"].get(key) is not None]
    if not vals:
        return {"n": 0, "mean": None, "min": None}
    return {"n": len(vals), "mean": sum(vals) / len(vals), "min": min(vals)}


# ======================================================================================
# stage 3: persistence (per-family BEFORE aggregate)
# ======================================================================================
def _sha_obj(o):
    return hashlib.sha256(
        json.dumps(o, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def persist_evidence(out_dir, family_record, *, classification):
    """Flush ONE family's evidence to disk immediately, stamped, before any aggregate exists.

    An interruption after this call leaves a complete, hashed per-family record on disk, so a
    restart never has to reconstruct a family from a partial summary. Returns the record's
    content hash; writing is atomic (temp file + rename) so a crash mid-write cannot leave a
    half-written record that a restart would mistake for complete.
    """
    ev_dir = os.path.join(out_dir, "per_family_evidence")
    os.makedirs(ev_dir, exist_ok=True)
    stamped = dict(family_record, classification=[classification, NON_CONFIRMATORY],
                   execution_version=EXECUTION_VERSION)
    stamped["evidence_sha256"] = _sha_obj(family_record)
    path = os.path.join(ev_dir, f"{family_record['arm']}_{family_record['canonical_hypothesis_id']}.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(stamped, fh, sort_keys=True, indent=1, default=str)
    os.replace(tmp, path)          # atomic: a restart sees either the old file or the new one
    return stamped["evidence_sha256"]


def load_persisted(out_dir):
    """Every per-family record already on disk, keyed by (arm, cid). Deterministic restart:
    a family whose evidence is present is not recomputed, and its content hash is re-checked
    so a corrupted/partial record is treated as absent rather than silently trusted."""
    ev_dir = os.path.join(out_dir, "per_family_evidence")
    out = {}
    if not os.path.isdir(ev_dir):
        return out
    for fn in sorted(os.listdir(ev_dir)):
        if not fn.endswith(".json") or fn.endswith(".tmp"):
            continue
        try:
            rec = json.load(open(os.path.join(ev_dir, fn)))
        except (json.JSONDecodeError, OSError):
            continue
        core = {k: v for k, v in rec.items()
                if k not in ("classification", "execution_version", "evidence_sha256")}
        if rec.get("evidence_sha256") != _sha_obj(core):
            continue          # partial or corrupted: recompute rather than double-count
        out[(rec["arm"], rec["canonical_hypothesis_id"])] = core
    return out


# ======================================================================================
# stage 4: finalize
# ======================================================================================
def finalize_result(plan, aggregates, *, experiment_id, champion_sha256,
                    per_family_hashes):
    """The final experiment result. Binds the classification, endpoints, candidate set,
    CHAMPION (unchanged), and a single content hash over the whole evidence bundle."""
    body = {
        "execution_version": EXECUTION_VERSION,
        "experiment": experiment_id,
        "classification": [plan.classification, NON_CONFIRMATORY],
        "confirmatory_oos_computed": plan.classification == CLASS_CONFIRMATORY,
        "confirmatory_oos_viewed": False,
        "candidate_feature_promotion": False,
        "engine_spec_hash": plan.engine_spec_hash,
        "n_treated_evaluable": len(plan.treated),
        "n_controls_used": len(plan.controls),
        "n_uniform_evaluable": len(plan.uniform),
        "endpoint_a": aggregates["endpoint_a"],
        "endpoint_b": aggregates["endpoint_b"],
        "multiplicity": aggregates["multiplicity"],
        "fold_stability": aggregates["fold_stability"],
        "competition_stability": aggregates["competition_stability"],
        "candidate_feature_set": aggregates["candidate_feature_set"],
        "champion_sha256_before": champion_sha256,
        "champion_sha256_after": champion_sha256,      # never written by this path
        "champion_unchanged": True,
        "per_family_evidence_hashes": dict(sorted(per_family_hashes.items())),
    }
    body["evidence_bundle_sha256"] = _sha_obj(body)
    return body


# ======================================================================================
# orchestration: the ONE call the driver makes (dry or authorized), so both share it
# ======================================================================================
def run_experiment(plan, out_dir, *, experiment_id, champion_sha256, persist=True):
    """Evaluate every family, persist per-family evidence, aggregate and finalize.

    This is the complete measurement. The driver decides WHETHER to call it (authorization)
    and WITH WHICH folds (synthetic/development vs fresh); it never re-implements any of it.
    Restart-safe: a family already persisted with a valid hash is reused, not recomputed.
    """
    resume = load_persisted(out_dir) if persist else {}
    per_family_hashes = {}
    treated_records, control_records, uniform_records = {}, {}, {}

    def _do(fs, sink):
        key = (fs.arm, fs.cid)
        rec = resume.get(key)
        if rec is None:
            rec = evaluate_family_evidence(fs, plan)
            if persist:
                per_family_hashes[key[1]] = persist_evidence(
                    out_dir, rec, classification=plan.classification)
        else:
            per_family_hashes[key[1]] = _sha_obj(rec)
        sink[fs.cid] = rec

    for fs in plan.treated:
        _do(fs, treated_records)
    for fs in plan.controls.values():
        _do(fs, control_records)
    for fs in plan.uniform:
        _do(fs, uniform_records)

    aggregates = aggregate_endpoints(plan, treated_records, control_records, uniform_records)
    return finalize_result(plan, aggregates, experiment_id=experiment_id,
                           champion_sha256=champion_sha256,
                           per_family_hashes=per_family_hashes)


def version_stamp() -> dict:
    return {"execution_version": EXECUTION_VERSION,
            "stages": ["prepare_execution", "evaluate_family_evidence",
                       "aggregate_endpoints", "persist_evidence", "finalize_result"],
            "authorization_is_not_in_this_module": True,
            "callable_on_synthetic_and_development_folds": True,
            "per_family_evidence_persisted_before_aggregate": True,
            "restart_is_deterministic_and_does_not_double_count": True,
            "endpoint_b_inference": ES.SMALL_CLUSTER_METHOD,
            "controls_contribute_total_weight_one_never_extra_votes": True,
            "reads_no_cloud_module": True}
