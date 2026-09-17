"""Build the R (matched-blind) and H (deterministic-heuristic) control arms for the V8B.1
PILOT-50 cohort, reusing the FROZEN apparatus with zero modification.

INVARIANTS:
  * ZERO paid Sonnet calls. ZERO network. Reads NO target outcome (the outcome seal is NOT
    crossed here -- scorer/compiler.team_value is never invoked).
  * The pilot cohort is EXACTLY the 50 fixtures in V8B1_TRANCHE_50_MANIFEST.fixture_ids_ordered.
  * Per fixture, K_valid(T) = number of Sonnet's *valid* final selections (i.e. the stored
    final_selections list). OK_ABSTAIN => 0 selections. INVALID_UNKNOWN_HYPOTHESIS_ID =>
    selections were dropped fail-closed => 0 valid selections. Those fixtures get empty R/H
    and contribute no paired difference (listwise), exactly as the frozen spec dictates.
  * Sonnet selection SHAPES are recovered structurally by re-walking search.py's own finite
    grammar (the same enumeration search() and resolve() use); NO prose is read.
  * R and H are pure deterministic functions of (shapes, capability); byte-identical on re-run.

Outputs:
  research/hypothesis_engine/V8B1_PILOT50_CONTROL_R.jsonl   (one line per fixture)
  research/hypothesis_engine/V8B1_PILOT50_CONTROL_H.jsonl   (one line per fixture)
"""
from __future__ import annotations

import hashlib
import json
import sys

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT)

TRANCHE_MANIFEST = f"{ROOT}/research/hypothesis_engine/V8B1_TRANCHE_50_MANIFEST.json"
SONNET_SELECTIONS = f"{ROOT}/research/hypothesis_engine/V8B1_TRANCHE_50_SELECTIONS.json"
OUT_R = f"{ROOT}/research/hypothesis_engine/V8B1_PILOT50_CONTROL_R.jsonl"
OUT_H = f"{ROOT}/research/hypothesis_engine/V8B1_PILOT50_CONTROL_H.jsonl"

CHAMPION_ARTIFACT = "data/discovery/pilotC_stat_mixer.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def _sha_file(path):
    with open(f"{ROOT}/{path}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _shape_from_grammar(hypothesis_id, capability, SE, IRM):
    """Recover a candidate dict for one hypothesis_id by re-walking search.py's own grammar,
    building the SAME structural fields search() emits. Returns None if the id does not
    resolve under this fixture's capability (should not happen for a validated OK selection)."""
    for spec in SE._candidate_shapes(capability):
        ir = IRM.build_ir(spec)
        if ir.status == IRM.OK and ir.ir_id() == hypothesis_id:
            status, _adm, _detail = capability.classify_metrics(ir.target_metrics)
            return {
                "hypothesis_id": ir.ir_id(),
                "target_metrics": list(ir.target_metrics),
                "subject": spec["subject"],
                "side": spec["side"],
                "comparator": spec["comparison"],
                "conditions": spec["conditions"],
                "window": spec["window"],
                "capability_status": status,
                "complexity": {
                    "n_conditions": len(spec["conditions"]),
                    "n_target_metrics": len(ir.target_metrics),
                    "uses_similarity": bool(spec["required_capabilities"]),
                },
            }
    return None


def main():
    # ---- pre-run integrity: CHAMPION + frozen scientific artifacts unchanged ----
    if _sha_file(CHAMPION_ARTIFACT) != CHAMPION_EXPECTED:
        raise SystemExit("CHAMPION changed -- refusing to build controls")

    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import execution as EX
    from src.research.hypothesis_v71 import ir as IRM
    from src.research.hypothesis_v71 import recency as REC
    from src.research.hypothesis_v8b1 import controls as CT
    from src.research.hypothesis_v8b1 import packet as PK
    from src.research.hypothesis_v8b1 import search as SE

    tm = json.load(open(TRANCHE_MANIFEST))
    pilot_ids = tm["fixture_ids_ordered"]
    assert len(pilot_ids) == 50 and len(set(pilot_ids)) == 50

    son = json.load(open(SONNET_SELECTIONS))
    by_fixture = {s["fixture_id"]: s for s in son["selections"]}
    assert set(by_fixture) == set(pilot_ids), "Sonnet selection set != pilot cohort"

    # Build the SAME index / capability / context the tranche runner used.
    cap = CAP.CapabilityContract(
        json.load(open(f"{ROOT}/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json")))
    recs = CI.load_records(include_fresh=True)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    index = CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)
    ctx = EX.build_context(index)
    recency_family = tuple(REC.family()) + (REC.UniformRecency(),)

    r_lines, h_lines = [], []
    n_r_unmatched = 0
    for fid in pilot_ids:
        pos = index.pos_of_fixture[fid]
        packet = PK.build_packet(index, pos, cap, ctx.terciles, ctx.axis_cache, ctx.similarity,
                                 recency_family)
        assert packet.get("reads_target_outcome") is False, "packet not outcome-blind"
        # capability is the global coverage contract (same object search() consumes); the
        # apparatus derives fixture-specificity from rec_i/pos, not from capability.
        fixture_cap = cap

        rec = by_fixture[fid]
        status = rec["status"]
        valid_sel = rec["final_selections"] if status in ("OK",) else []
        # OK_ABSTAIN => empty final_selections already; INVALID => selections dropped fail-closed.
        shapes = []
        shape_ids = []
        for sel in valid_sel:
            cand = _shape_from_grammar(sel["hypothesis_id"], fixture_cap, SE, IRM)
            if cand is None:
                # A validated OK selection that no longer resolves would itself be a defect.
                raise SystemExit(f"OK selection {sel['hypothesis_id']} at {fid} did not resolve")
            shapes.append(CT.shape_of(cand))
            shape_ids.append(cand["hypothesis_id"])

        k_valid = len(shapes)

        # Arm R: matched blind, sized to K_valid, in Sonnet emission order.
        r_out = CT.blind_selections_for_fixture(shapes, fixture_cap)
        n_r_unmatched += sum(1 for s in r_out["selections"] if s["status"] == "UNMATCHED")
        r_lines.append({"fixture_id": fid, "sonnet_status": status, "k_valid": k_valid,
                        "sonnet_selection_ids": shape_ids, **r_out})

        # Arm H: top-K_valid over full admissible universe.
        h_out = CT.heuristic_selections_for_fixture(k_valid, fixture_cap)
        h_lines.append({"fixture_id": fid, "sonnet_status": status, "k_valid": k_valid,
                        "heuristic_selection_ids": [s["hypothesis_id"] for s in h_out["selections"]],
                        **h_out})

    with open(OUT_R, "w") as f:
        for line in r_lines:
            f.write(json.dumps(line, sort_keys=True, default=str) + "\n")
    with open(OUT_H, "w") as f:
        for line in h_lines:
            f.write(json.dumps(line, sort_keys=True, default=str) + "\n")

    # post-run CHAMPION re-check
    champ_ok = _sha_file(CHAMPION_ARTIFACT) == CHAMPION_EXPECTED
    total_k = sum(l["k_valid"] for l in r_lines)
    print(f"[controls] pilot fixtures={len(pilot_ids)} total_k_valid={total_k} "
          f"R_unmatched={n_r_unmatched} champion_ok={champ_ok}")
    print(f"[controls] wrote {OUT_R} and {OUT_H}")
    print(f"[controls] controls_version={CT.version_stamp()['controls_version']} "
          f"reads_outcomes={CT.version_stamp()['reads_outcomes']}")


if __name__ == "__main__":
    main()
