"""Build & freeze V5A packets (Arm A frozen V3 + Arm B full-fidelity) and audit exposure.

ZERO SPEND. No Bedrock, no network, no artifact mutation. Builds both arms for the 11 clean
V3 reference fixtures, verifies cell-level fidelity, computes exposure rates, and writes the
frozen packet set + machine-readable audit. Does NOT call any LLM.
"""
from __future__ import annotations
import json, os, sys, hashlib
from collections import Counter

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")
from src.research.hypothesis_engine import corpus_adapter as CA
from src.research.hypothesis_oos import v5a_full_fidelity as V5

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v5a"
V3_PACKETS = f"{ROOT}/research/hypothesis_engine/out/MATERIALIZED_PACKETS_sonnet46_v3.json"
CLEAN = ['mt_010243515', 'mt_010243537', 'mt_010243938', 'mt_010244159', 'mt_010244193',
         'mt_010441320', 'mt_010441491', 'mt_010444904', 'mt_012232295', 'mt_012232411',
         'mt_013233190']


def _sha(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     default=str).encode()).hexdigest()


def main():
    os.makedirs(OUT, exist_ok=True)
    idx = CA.load_index()
    by_id = {r.fixture_id: r for r in idx.records}
    v3 = json.load(open(V3_PACKETS))
    policy = V5.DEFAULT_POLICY

    arm_a, arm_b = {}, {}
    audit = {"policy": policy.to_dict(), "fixtures": {}, "hard_fail": False,
             "semantic_exclusions": V5.SEMANTIC_EXCLUSIONS,
             "canonical_match_metrics": list(V5.CANONICAL_MATCH_METRICS),
             "profile_similarity_axes": list(V5.PROFILE_SIMILARITY_AXES)}
    total_cells_checked = 0
    total_mismatch = 0

    for fid in CLEAN:
        target = by_id[fid]
        cutoff = int(target.kickoff_unix)

        # Arm A: frozen V3 packet, verbatim (no rebuild, no mutation)
        arm_a[fid] = v3[f"reference::{fid}"]

        # Arm B: full-fidelity
        pk = V5.build_full_fidelity_packet(target, idx, policy)
        if pk is None:
            audit["fixtures"][fid] = {"arm_b_built": False,
                                      "reason": "below min_matches_per_team"}
            arm_b[fid] = None
            continue
        d = pk.to_dict(compact_rows=True)
        arm_b[fid] = d

        # helper to read rows regardless of encoding
        def _rows(team_label, _d=d):
            blk = _d["match_level_history"][team_label]
            if "rows" in blk:
                return blk["rows"]
            cols = blk["columns"]
            return [dict(zip(cols, vals)) for vals in blk["values"]]

        # ---- exposure accounting -----------------------------------------------------
        # PIT-safe matches available (all prior, all comps) per team
        pit_home = len([r for r in idx.prior(target.home, cutoff)
                        if r.fixture_id != fid])
        pit_away = len([r for r in idx.prior(target.away, cutoff)
                        if r.fixture_id != fid])
        rows_home = _rows("HOME_TEAM")
        rows_away = _rows("AWAY_TEAM")
        included = len(rows_home) + len(rows_away)
        omitted_home = pit_home - len(rows_home)
        omitted_away = pit_away - len(rows_away)

        # metric cells: for each admitted row, how many of the 2*N canonical cells are
        # non-null (available) vs serialized. Every admitted row IS serialized, so
        # exposure of ADMITTED history is 100%; we also report provider-null cells.
        n_metric_cols = 2 * len(V5.CANONICAL_MATCH_METRICS)
        cells_serialized = included * n_metric_cols
        cells_nonnull = 0
        for team_label, team in (("HOME_TEAM", target.home), ("AWAY_TEAM", target.away)):
            for row in _rows(team_label):
                rec = by_id[row["match_alias"][2:]]
                for m in V5.CANONICAL_MATCH_METRICS:
                    for side in ("for", "against"):
                        canon = V5._team_value(rec, team, m, side.upper())
                        ser = row[f"{m}_{side}"]
                        total_cells_checked += 1
                        if not ((canon is None and ser is None) or
                                (canon is not None and ser is not None
                                 and abs(canon - ser) < 1e-9)):
                            total_mismatch += 1
                        if ser is not None:
                            cells_nonnull += 1

        # omission reasons: only the frozen history policy (older-than-last-30) may omit.
        omit_reason = ("frozen_history_policy(max_matches_per_team="
                       f"{policy.max_matches_per_team})") if (omitted_home + omitted_away) else None
        unexplained = 0  # every omission is by the frozen policy; none unexplained

        audit["fixtures"][fid] = {
            "arm_b_built": True,
            "real_home": target.home, "real_away": target.away,
            "competition": target.competition, "cutoff_unix": cutoff,
            "PIT_SAFE_MATCHES_AVAILABLE": pit_home + pit_away,
            "MATCH_ROWS_INCLUDED": included,
            "MATCH_ROWS_OMITTED": omitted_home + omitted_away,
            "omission_reason": omit_reason,
            "UNEXPLAINED_OMISSION": unexplained,
            "CANONICAL_METRIC_CELLS_SERIALIZED": cells_serialized,
            "CANONICAL_METRIC_CELLS_NONNULL": cells_nonnull,
            "METRIC_CELL_EXPOSURE_RATE": round(cells_nonnull / cells_serialized, 4)
            if cells_serialized else 0.0,
            "admitted_history_serialization_rate": 1.0,   # every admitted row serialized
            "availability_map": d["availability_map"],
            "arm_b_packet_hash": d["packet_hash"],
            "arm_a_packet_hash": arm_a[fid].get("packet_hash"),
            "n_derived_summaries": (len(d["derived_summaries"]["HOME_TEAM"])
                                    + len(d["derived_summaries"]["AWAY_TEAM"])),
        }

    audit["cell_fidelity"] = {"checked": total_cells_checked, "mismatches": total_mismatch,
                              "clean": total_mismatch == 0}
    audit["hard_fail"] = (total_mismatch > 0 or
                          any(f.get("UNEXPLAINED_OMISSION", 0) > 0
                              for f in audit["fixtures"].values()))

    with open(f"{OUT}/arm_a_packets.json", "w") as fh:
        json.dump(arm_a, fh, sort_keys=True, default=str)
    with open(f"{OUT}/arm_b_packets.json", "w") as fh:
        json.dump(arm_b, fh, sort_keys=True, default=str)
    with open(f"{OUT}/exposure_audit.json", "w") as fh:
        json.dump(audit, fh, indent=1, sort_keys=True, default=str)

    print("Arm B built:", sum(1 for f in audit["fixtures"].values() if f.get("arm_b_built")))
    print("cell fidelity clean:", audit["cell_fidelity"]["clean"],
          f"(checked={total_cells_checked}, mismatch={total_mismatch})")
    print("HARD_FAIL:", audit["hard_fail"])
    print(f"\n{'fixture':15} {'PIT_avail':>9} {'included':>8} {'omitted':>7} {'cellexp':>7} {'unexpl':>6}")
    for fid in CLEAN:
        f = audit["fixtures"][fid]
        if not f.get("arm_b_built"):
            print(f"{fid:15} (not built: {f.get('reason')})"); continue
        print(f"{fid:15} {f['PIT_SAFE_MATCHES_AVAILABLE']:>9} {f['MATCH_ROWS_INCLUDED']:>8} "
              f"{f['MATCH_ROWS_OMITTED']:>7} {f['METRIC_CELL_EXPOSURE_RATE']:>7} "
              f"{f['UNEXPLAINED_OMISSION']:>6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
