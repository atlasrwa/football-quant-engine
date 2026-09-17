"""V8C composed experiment driver (`v8c_experiment_v1`).

ONE function that runs the WHOLE experiment -- measurable universe, S / R / H selection,
all-arm freeze, target-outcome scoring, arm aggregation, paired endpoints, inference -- over
whatever fixture positions it is handed. Synthetic, development or (after a separate
authorization that this module does not grant) a fresh pilot.

The point of having it as ONE composed path is the V8C mission itself: module-level tests were
insufficient, because every module passed while the COMPOSITION could not answer its question.
This is the object `test_experiment_end_to_end_reachability.py` exercises, and it is the same
code a future authorized pilot would run.

It knows nothing about authorization or spend. The S arm is supplied by the CALLER as a
selector function, so the composed path can be driven by a synthetic S-style selector with no
model call at all -- exactly as V7.1 separated `execution.py` from its authorization driver.

ZERO SPEND. No network. No CHAMPION.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.research.hypothesis_v71 import engine as ENGmod
from src.research.hypothesis_v8b1 import search as SE
from src.research.hypothesis_v8b2 import scorer as SC
from src.research.hypothesis_v8c import aggregate as AG
from src.research.hypothesis_v8c import controls as CTL
from src.research.hypothesis_v8c import pit_context as PC
from src.research.hypothesis_v8c import pre_t as PT
from src.research.hypothesis_v8c import universe as UNI

EXPERIMENT_VERSION = "v8c_experiment_v1"

CLASS_SYNTHETIC = "SYNTHETIC_ONLY"
CLASS_DEVELOPMENT = "DEVELOPMENT_ONLY"
CLASS_CONFIRMATORY = "CONFIRMATORY"


@dataclass
class ExperimentResult:
    classification: str
    per_fixture: list = field(default_factory=list)
    selection_freeze: list = field(default_factory=list)
    records: list = field(default_factory=list)
    arm_scores: list = field(default_factory=list)
    blocks: dict = field(default_factory=dict)
    endpoint_sr: dict = field(default_factory=dict)
    endpoint_sh: dict = field(default_factory=dict)
    reachability: dict = field(default_factory=dict)


def default_s_selector(fixture_universe, k=3):
    """A deterministic STAND-IN for Sonnet, used only to drive the composed path without a
    paid call. It picks the structurally first `k` evaluable candidates.

    It is NOT a model, NOT a heuristic under test, and NOT an arm of the real experiment: in a
    real run this function is replaced by the frozen Sonnet selections. It reads no outcome.
    """
    return [c["hypothesis_id"] for c in fixture_universe.evaluable[:k]]


def run_experiment(index, fixture_positions, *, capability, s_selector=None, k=3,
                   classification=CLASS_SYNTHETIC, similarity_engine=None,
                   fixture_ids=None) -> ExperimentResult:
    """Drive the complete experiment over `fixture_positions`, in the order given.

    Stages, in the order the contract matrix names them:
      S1..S5   per-target PIT context -> admissible universe -> pre-T evaluable universe
      S6..S8   S selection (caller-supplied) -> distinct R -> H over the SAME universe
      S9       all-arm selection freeze (recorded BEFORE any outcome is read)
      S10/S11  target outcome + fixture scorer
      S12..S15 arm aggregation -> paired endpoints -> inference
    """
    s_selector = s_selector or (lambda fu: default_s_selector(fu, k=k))
    per_fixture, freeze_rows, records = [], [], []
    ids_ordered = []

    for n, pos in enumerate(fixture_positions):
        fid = str(fixture_ids[n]) if fixture_ids else str(index.recs[pos].fixture_id)
        ids_ordered.append(fid)
        ctx = PC.build_pit_context(index, pos, similarity_engine=similarity_engine)
        fu = UNI.build_fixture_universe(index, pos, ctx=ctx, capability=capability,
                                        fixture_id=fid)

        # ---- S6: S arm ----------------------------------------------------------------
        s_ids = list(s_selector(fu))
        by_id = {c["hypothesis_id"]: c for c in fu.evaluable}
        s_shapes, s_valid = [], []
        for hid in s_ids:
            cand = by_id.get(hid)
            if cand is None:          # a selection outside the evaluable universe is INVALID
                continue
            s_shapes.append(CTL.shape_of(cand))
            s_valid.append(hid)

        # ---- S7/S8: control arms, same universe ---------------------------------------
        r_out = CTL.blind_selections_for_fixture(s_shapes, fu)
        h_out = CTL.heuristic_selections_for_fixture(len(s_valid), fu)
        r_ids = [s["hypothesis_id"] for s in r_out["selections"] if s["status"] == CTL.MATCHED]
        h_ids = [s["hypothesis_id"] for s in h_out["selections"]]

        # ---- S9: all-arm freeze, written BEFORE any outcome is read --------------------
        freeze_rows.append({"fixture_id": fid, "k_valid": len(s_valid),
                            "S": list(s_valid), "R": list(r_ids), "H": list(h_ids),
                            "r_identity_count": r_out["identity_count"],
                            "r_unmatched": r_out["n_unmatched"],
                            "h_status": h_out.get("status")})

        # ---- S10/S11: target outcome + scorer -----------------------------------------
        for arm, ids in (("S", s_valid), ("R", r_ids), ("H", h_ids)):
            for hid in ids:
                ir = SE.resolve(hid, capability)
                if ir is None:
                    records.append({"fixture_id": fid, "arm": arm, "hypothesis_id": hid,
                                    "status": "UNRESOLVED", "score": None, "reason": ""})
                    continue
                fs = SC.score_fixture(ir, index, pos, metric=ir.target_metrics[0],
                                      terciles=ctx.terciles, axis_cache=ctx.axis_cache,
                                      similarity=ctx.similarity,
                                      recency=ENGmod.recency_family_for(ir),
                                      capability=capability)
                records.append({"fixture_id": fid, "arm": arm, "hypothesis_id": hid,
                                "status": fs.status, "score": fs.score, "reason": fs.reason})

        per_fixture.append({"fixture_id": fid, "ledger": fu.ledger(),
                            "n_evaluable": fu.n_evaluable, "k_valid": len(s_valid),
                            "r_matched": r_out["n_matched"], "h_selected": h_out["n_selected"]})

    # ---- S12..S15 ---------------------------------------------------------------------
    arm_scores = AG.per_fixture_arm_scores(records, ids_ordered)
    blocks = AG.chronological_blocks(ids_ordered)
    sr = AG.paired_endpoint(arm_scores, "R", blocks["fixture_to_block"])
    sh = AG.paired_endpoint(arm_scores, "H", blocks["fixture_to_block"])

    reach = compute_reachability(per_fixture, freeze_rows, records, arm_scores, sr, sh)
    return ExperimentResult(classification=classification, per_fixture=per_fixture,
                            selection_freeze=freeze_rows, records=records,
                            arm_scores=arm_scores, blocks=blocks, endpoint_sr=sr,
                            endpoint_sh=sh, reachability=reach)


def compute_reachability(per_fixture, freeze_rows, records, arm_scores, sr, sh) -> dict:
    """The §32 reachability vector. Every entry is DERIVED from the run's own artifacts --
    none is asserted, defaulted or hardcoded (§34)."""
    def ok(arm):
        return sum(1 for r in records if r["arm"] == arm and r["status"] == SC.SCORE_OK)

    def armed(arm):
        return sum(1 for a in arm_scores if a.get(arm) is not None)

    return {
        "MEASURABLE_UNIVERSE_REACHABLE": any(f["n_evaluable"] > 0 for f in per_fixture),
        "S_SELECTION_REACHABLE": any(f["k_valid"] > 0 for f in freeze_rows),
        "DISTINCT_R_REACHABLE": any(f["r_matched"] > 0 for f in per_fixture),
        "R_IDENTITY_COUNT": sum(f["r_identity_count"] for f in freeze_rows),
        "H_SELECTION_REACHABLE": any(f["h_selected"] > 0 for f in per_fixture),
        "S_SCORE_OK_REACHABLE": ok("S") > 0,
        "R_SCORE_OK_REACHABLE": ok("R") > 0,
        "H_SCORE_OK_REACHABLE": ok("H") > 0,
        "S_ARM_SCORE_REACHABLE": armed("S") > 0,
        "R_ARM_SCORE_REACHABLE": armed("R") > 0,
        "H_ARM_SCORE_REACHABLE": armed("H") > 0,
        "PAIRED_SR_REACHABLE": sr["paired_n"] > 0,
        "PAIRED_SH_REACHABLE": sh["paired_n"] > 0,
        "AGGREGATION_REACHABLE": len(arm_scores) > 0 and armed("S") > 0,
        "INFERENCE_REACHABLE": (
            sr["inference"].get("inference_status") is not None
            and sh["inference"].get("inference_status") is not None),
        "counts": {"n_fixtures": len(per_fixture), "score_ok_S": ok("S"), "score_ok_R": ok("R"),
                   "score_ok_H": ok("H"), "paired_sr": sr["paired_n"],
                   "paired_sh": sh["paired_n"]},
        "inference_status_sr": sr["inference"].get("inference_status"),
        "inference_status_sh": sh["inference"].get("inference_status"),
    }


#: The booleans §32 requires to be simultaneously true in ONE composed run.
REQUIRED_TRUE = ("MEASURABLE_UNIVERSE_REACHABLE", "S_SELECTION_REACHABLE",
                 "DISTINCT_R_REACHABLE", "H_SELECTION_REACHABLE", "S_SCORE_OK_REACHABLE",
                 "R_SCORE_OK_REACHABLE", "H_SCORE_OK_REACHABLE", "S_ARM_SCORE_REACHABLE",
                 "R_ARM_SCORE_REACHABLE", "H_ARM_SCORE_REACHABLE", "PAIRED_SR_REACHABLE",
                 "PAIRED_SH_REACHABLE", "AGGREGATION_REACHABLE", "INFERENCE_REACHABLE")


def gate_verdict(reach: dict) -> dict:
    """PASS iff every REQUIRED_TRUE flag is true AND R_IDENTITY_COUNT == 0."""
    failed = [k for k in REQUIRED_TRUE if not reach.get(k)]
    identity_ok = reach.get("R_IDENTITY_COUNT", -1) == 0
    if not identity_ok:
        failed = failed + ["R_IDENTITY_COUNT == 0"]
    return {"END_TO_END_EXPERIMENT_REACHABILITY": "PASS" if not failed else "FAIL",
            "failed_conditions": failed,
            "checked": list(REQUIRED_TRUE) + ["R_IDENTITY_COUNT == 0"]}


def version_stamp() -> dict:
    return {"experiment_version": EXPERIMENT_VERSION,
            "composed_stages": ["pit_context", "universe", "pre_t", "S", "R", "H", "freeze",
                                "scorer", "aggregate", "paired", "inference"],
            "pre_t": PT.version_stamp()["pre_t_evaluability_version"],
            "universe": UNI.version_stamp()["universe_version"],
            "controls": CTL.version_stamp()["controls_version"],
            "aggregate": AG.version_stamp()["aggregate_version"],
            "scorer": SC.version_stamp()["scorer_version"],
            "s_arm_is_caller_supplied": True,
            "knows_about_authorization_or_spend": False,
            "required_true": list(REQUIRED_TRUE)}
