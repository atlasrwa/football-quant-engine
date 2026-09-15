"""Build + audit the V5A.1 packet set. ZERO SPEND: no Bedrock, no network, no mutation.

Writes both arms, the exposure audit, the evidence-id audit and the A/B isolation audit.
Freezing (manifest, cost model, preregistration) is `_freeze_v5a1.py`, run after this.
"""
from __future__ import annotations

import json, os, sys, hashlib
from collections import Counter

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")

from src.research.hypothesis_engine import corpus_adapter as CA
from src.research.hypothesis_oos import v5a1_packet as PK
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_prompt as P
from src.research.hypothesis_oos import v5a1_semantics as S
from src.research.hypothesis_oos import v5a1_admissibility as ADM

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v5a1"

#: Task §26: the V5A eligible set, unchanged. mt_013233190 remains excluded for the same
#: deterministic pre-spend reason (too little prior history), now measured against the FULL
#: PIT-safe universe rather than the raw-row cap.
CANDIDATES = ['mt_010243515', 'mt_010243537', 'mt_010243938', 'mt_010244159', 'mt_010244193',
              'mt_010441320', 'mt_010441491', 'mt_010444904', 'mt_012232295', 'mt_012232411',
              'mt_013233190']


def main():
    os.makedirs(OUT, exist_ok=True)
    idx = CA.load_index()
    by_id = {r.fixture_id: r for r in idx.records}

    base, research = {}, {}
    exposure, evid_audit, iso_audit = {}, {}, {}
    excluded = {}
    cells_checked = cells_bad = 0

    for fid in CANDIDATES:
        target = by_id[fid]
        a = PK.build_packet(idx, target, arm="base")
        b = PK.build_packet(idx, target, arm="research")
        if a is None or b is None:
            ph = PK.full_prior(idx, target, target.home)
            pa = PK.full_prior(idx, target, target.away)
            excluded[fid] = (f"fewer than {PK.MIN_PRIOR_MATCHES_PER_TEAM} PIT-safe prior "
                             f"matches for one team (home={len(ph)}, away={len(pa)}); "
                             f"excluded from BOTH arms to keep the pairing symmetric")
            continue
        base[fid], research[fid] = a, b

        prior = {s: PK.full_prior(idx, target, t)
                 for s, t in (("HOME", target.home), ("AWAY", target.away))}
        teams = {"HOME": target.home, "AWAY": target.away}

        # ---- §18 raw cell fidelity: serialized == canonical, every visible cell ---------
        bad = []
        for blk in _blocks(b):
            subj = blk["subject"]; team = teams[subj]
            rows = PK.raw_rows(prior[subj])
            for i, (row, rec) in enumerate(zip(blk["rows"], rows), start=1):
                for c, v in zip(blk["cell_columns"], row["cells"]):
                    metric, side = c.rsplit("_", 1)
                    canon = PK._team_value(rec, team, metric, side.upper())
                    cells_checked += 1
                    if canon != v:
                        cells_bad += 1
                        bad.append((subj, i, c, canon, v))

        # ---- exposure accounting (§10) -------------------------------------------------
        nulls = sum(1 for blk in _blocks(b) for r in blk["rows"]
                    for v in r["cells"] if v is None)
        n_cells = sum(len(blk["rows"]) * len(blk["cell_columns"]) for blk in _blocks(b))
        allprior_n = {}
        for sec in b["sections"]:
            if sec.get("section_type") == "DERIVED_SUMMARIES":
                cols = sec["columns"]
                iw, iv, isb, isn = (cols.index("window"), cols.index("venue_scope"),
                                    cols.index("subject"), cols.index("sample_n"))
                for row in sec["rows"]:
                    if row[iw] == "ALL_PRIOR" and row[iv] == "ANY":
                        allprior_n.setdefault(row[isb], set()).add(row[isn])
        exposure[fid] = {
            "competition": target.competition,
            "cutoff_unix": int(target.kickoff_unix),
            "TOTAL_PIT_SAFE_PRIOR_MATCHES": {s: len(prior[s]) for s in prior},
            "RAW_ROWS_SERIALIZED": {s: len(PK.raw_rows(prior[s])) for s in prior},
            "ROWS_OMITTED_BY_RAW_ROW_POLICY": {
                s: len(prior[s]) - len(PK.raw_rows(prior[s])) for s in prior},
            "ALL_PRIOR_SUMMARY_SAMPLE_N_RANGE": {
                s: [min(v), max(v)] for s, v in sorted(allprior_n.items())},
            "raw_row_policy": f"most recent {PK.MAX_RAW_ROWS_PER_TEAM} matches, serialized "
                              f"as rows for prompt size only",
            "baseline_universe": PK.BASELINE_UNIVERSE,
            "CANONICAL_METRIC_CELLS_SERIALIZED": n_cells,
            "CANONICAL_METRIC_CELLS_NONNULL": n_cells - nulls,
            "METRIC_CELL_EXPOSURE_RATE": round((n_cells - nulls) / n_cells, 4) if n_cells else None,
            "UNEXPLAINED_OMISSION": 0,
            "CELL_FIDELITY_MISMATCHES": len(bad),
            "cell_fidelity_examples": bad[:3],
            "base_packet_hash": a["packet_hash"],
            "research_packet_hash": b["packet_hash"],
            "real_home": target.home, "real_away": target.away,
        }

        # ---- evidence-id audit (§3) ----------------------------------------------------
        ida, idb = E.resolve_evidence_ids(a), E.resolve_evidence_ids(b)
        evid_audit[fid] = {
            "VALID_EVIDENCE_IDS": {"base": len(ida), "research": len(idb)},
            "DUPLICATE_EVIDENCE_IDS": {"base": _dupes(a), "research": _dupes(b)},
            "DUPLICATE_MATCH_ALIASES": _dup_aliases(b),
            # sorted(): `ida`/`idb` are SETS, so Counter's insertion order follows set
            # iteration order, which varies with PYTHONHASHSEED. Without this the audit
            # artifact is not byte-reproducible across runs even though its content is
            # identical -- and a frozen artifact that cannot be reproduced cannot be
            # verified. Caught by the rebuild-determinism check.
            "id_prefix_counts": {
                "base": dict(sorted(Counter(i.split(":")[0] for i in ida).items())),
                "research": dict(sorted(Counter(i.split(":")[0] for i in idb).items()))},
        }

        # ---- A/B isolation (§4, §5) ----------------------------------------------------
        recs_a = {r["evidence_id"]: r for r in E.evidence_records_of(a)
                  if r.get("evidence_id")}
        recs_b = {r["evidence_id"]: r for r in E.evidence_records_of(b)
                  if r.get("evidence_id")}
        shared = sorted(set(recs_a) & set(recs_b))
        mismatched_all = [k for k in shared if _cmp(recs_a[k]) != _cmp(recs_b[k])]
        # An AVAILABILITY_DECLARATION whose value is the exposure state MUST differ: task
        # §7 requires the base arm to say truthfully that it does not carry this evidence.
        # That is the treatment being declared, not an isolation leak. Every OTHER shared
        # record must be value-identical across arms.
        expected_avail = [k for k in mismatched_all if k.startswith("AVAIL:")]
        mismatched = [k for k in mismatched_all if not k.startswith("AVAIL:")]
        iso_audit[fid] = {
            "BASE_IDS": len(ida), "RESEARCH_IDS": len(idb),
            "BASE_IDS_NOT_IN_RESEARCH": sorted(ida - idb),
            "RESEARCH_SUPERSET_OF_BASE": ida <= idb,
            "SHARED_RECORDS": len(shared),
            "EXPECTED_AVAILABILITY_DIFFERENCES": sorted(expected_avail),
            "N_EXPECTED_AVAILABILITY_DIFFERENCES": len(expected_avail),
            "UNEXPECTED_SHARED_VALUE_MISMATCHES": mismatched[:10],
            "N_UNEXPECTED_SHARED_VALUE_MISMATCHES": len(mismatched),
            "RESEARCH_ONLY_IDS": len(idb - ida),
            "packet_schema_version_identical":
                a["packet_schema_version"] == b["packet_schema_version"],
            "admissible_surface": {"base": ADM.packet_capability_summary(a),
                                   "research": ADM.packet_capability_summary(b)},
        }

    _w("packets_base.json", base)
    _w("packets_research.json", research)
    _w("exposure_audit.json", {
        "policy": {"baseline_universe": PK.BASELINE_UNIVERSE,
                   "max_raw_rows_per_team": PK.MAX_RAW_ROWS_PER_TEAM,
                   "min_prior_matches_per_team": PK.MIN_PRIOR_MATCHES_PER_TEAM,
                   "summary_estimator": PK.SUMMARY_ESTIMATOR},
        "canonical_metrics": list(S.CANONICAL_METRICS),
        "excluded_metrics": S.EXCLUDED_METRICS,
        "cell_fidelity": {"checked": cells_checked, "mismatches": cells_bad,
                          "clean": cells_bad == 0},
        "hard_fail": cells_bad > 0,
        "excluded_fixtures": excluded,
        "fixtures": exposure})
    _w("evidence_id_audit.json", evid_audit)
    _w("ab_isolation_audit.json", iso_audit)

    print("fixtures built:", len(base))
    print("excluded:", excluded)
    print("cell fidelity: checked", cells_checked, "mismatches", cells_bad)
    print("min VALID_EVIDENCE_IDS base:",
          min(v["VALID_EVIDENCE_IDS"]["base"] for v in evid_audit.values()))
    print("min VALID_EVIDENCE_IDS research:",
          min(v["VALID_EVIDENCE_IDS"]["research"] for v in evid_audit.values()))
    print("superset holds everywhere:",
          all(v["RESEARCH_SUPERSET_OF_BASE"] for v in iso_audit.values()))
    print("expected availability differences:",
          sum(v["N_EXPECTED_AVAILABILITY_DIFFERENCES"] for v in iso_audit.values()))
    print("UNEXPECTED shared value mismatches:",
          sum(v["N_UNEXPECTED_SHARED_VALUE_MISMATCHES"] for v in iso_audit.values()))
    return 0


def _blocks(p):
    for sec in p["sections"]:
        if sec.get("section_type") == "MATCH_LEVEL_OBSERVATIONS":
            return sec["blocks"]
    return []


def _cmp(rec):
    """Compare the parts of a record that must be identical across arms."""
    return {k: rec.get(k) for k in ("value", "sample_n", "metric", "side", "subject",
                                    "window", "venue_scope", "evidence_type")}


def _dupes(p):
    ids = []
    for sec in p["sections"]:
        if sec.get("section_type") == "MATCH_LEVEL_OBSERVATIONS":
            for blk in sec["blocks"]:
                ids += [r["evidence_id"] for r in blk["rows"]]
        else:
            cols = sec.get("columns") or []
            if "evidence_id" in cols:
                i = cols.index("evidence_id")
                ids += [r[i] for r in sec.get("rows") or []]
            ids += [r["evidence_id"] for r in (sec.get("records") or [])
                    if r.get("evidence_id")]
    return sorted(k for k, n in Counter(ids).items() if n > 1)


def _dup_aliases(p):
    ids = []
    for blk in _blocks(p):
        ids += [r["evidence_id"] for r in blk["rows"]]
    return sorted(k for k, n in Counter(ids).items() if n > 1)


def _w(name, obj):
    with open(f"{OUT}/{name}", "w") as fh:
        json.dump(obj, fh, indent=1, sort_keys=False, default=str)


if __name__ == "__main__":
    raise SystemExit(main())
