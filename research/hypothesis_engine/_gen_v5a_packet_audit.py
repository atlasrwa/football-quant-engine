"""Generate V5A_FULL_PACKET_AUDIT.md (no truncation) + one exact byte-level export.

ZERO SPEND. Read-only over the frozen V5A packets. For EVERY paired fixture: prior-match
counts, included/omitted, exact metric columns, the COMPLETE match-level matrix as
serialized, derived summaries count, opponent-profile context, availability map, exact
system prompt, exact user payload reference, and serialized packet hash. No "...".
"""
from __future__ import annotations
import json, sys, hashlib

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")
from src.research.hypothesis_oos import v5a_prompt as P
from src.research.hypothesis_oos import v5a_full_fidelity as V5

ROOT = "/home/ubuntu"
OUT = f"{ROOT}/research/hypothesis_oos/out/v5a"
AUDIT_MD = f"{ROOT}/research/hypothesis_engine/V5A_FULL_PACKET_AUDIT.md"
BYTE_EXPORT = f"{OUT}/BYTELEVEL_ARM_B_mt_010244159.request.txt"
BYTE_EXPORT_A = f"{OUT}/BYTELEVEL_ARM_A_mt_010244159.request.txt"


def _rows(pk, tl):
    blk = pk["match_level_history"][tl]
    if "rows" in blk:
        cols = blk["columns"]
        return cols, [[r.get(c) for c in cols] for r in blk["rows"]]
    return blk["columns"], blk["values"]


def main():
    arm_a = json.load(open(f"{OUT}/arm_a_packets.json"))
    arm_b = json.load(open(f"{OUT}/arm_b_packets.json"))
    au = json.load(open(f"{OUT}/exposure_audit.json"))
    pr = json.load(open(f"{OUT}/PREREGISTRATION.json"))
    paired = pr["paired_fixtures"]

    L = []
    W = L.append
    W("# V5A Full Packet Audit — Exact Contents Sent to the LLM (pre-spend)\n")
    W("ZERO-SPEND, read-only. This document shows, WITHOUT truncation, exactly what each "
      "arm's packet contains for every paired fixture. Arm A = frozen V3 compressed "
      "evidence (verbatim). Arm B = full match-level PIT-safe research view. No LLM was "
      "called to produce this.\n")
    W(f"History policy: `{json.dumps(pr['history_policy'])}`.\n")
    W(f"Canonical match metrics ({len(V5.CANONICAL_MATCH_METRICS)}): "
      f"`{', '.join(V5.CANONICAL_MATCH_METRICS)}`.\n")
    W(f"Semantic exclusions: `{json.dumps(V5.SEMANTIC_EXCLUSIONS)}`.\n")
    W("---\n")

    W("## Exact system prompt (identical for both arms)\n")
    W("```")
    W(P.SYSTEM_PROMPT)
    W("```\n")
    W(f"System prompt sha256: `{hashlib.sha256(P.SYSTEM_PROMPT.encode()).hexdigest()}`\n")
    W("---\n")

    for fid in paired:
        f = au["fixtures"][fid]
        pkA, pkB = arm_a[fid], arm_b[fid]
        W(f"## {fid}\n")
        W(f"- PIT-safe matches available: **{f['PIT_SAFE_MATCHES_AVAILABLE']}**; "
          f"match rows included (both teams): **{f['MATCH_ROWS_INCLUDED']}**; "
          f"omitted: **{f['MATCH_ROWS_OMITTED']}** (reason: `{f['omission_reason']}`); "
          f"UNEXPLAINED_OMISSION: **{f['UNEXPLAINED_OMISSION']}**.")
        W(f"- Metric cell exposure rate (non-null of serialized): "
          f"**{f['METRIC_CELL_EXPOSURE_RATE']}**; derived summaries: "
          f"**{f['n_derived_summaries']}**.")
        W(f"- Availability map: `{json.dumps(f['availability_map'])}`")
        W(f"- Arm A packet hash: `{f['arm_a_packet_hash']}`")
        W(f"- Arm B packet hash: `{f['arm_b_packet_hash']}`\n")

        # ARM A evidence (compressed) — full list
        W("### Arm A — frozen V3 compressed evidence (all items)\n")
        W(f"{len(pkA['evidence'])} unconditional shrunk scalar items "
          f"(venue=ALL, window=ALL_PRIOR):\n")
        W("| id | metric | value | n | reliability |")
        W("|---|---|---|---|---|")
        for e in pkA["evidence"]:
            W(f"| {e['id']} | {e['metric']} | {e['value']} | {e['sample_n']} | {e['reliability']} |")
        W("")

        # ARM B match-level matrix — COMPLETE, no truncation
        for tl in ("HOME_TEAM", "AWAY_TEAM"):
            cols, vals = _rows(pkB, tl)
            W(f"### Arm B — {tl} match-level matrix ({len(vals)} rows × {len(cols)} cols)\n")
            W("Columns: `" + ", ".join(cols) + "`\n")
            W("| " + " | ".join(cols) + " |")
            W("|" + "|".join("---" for _ in cols) + "|")
            for row in vals:
                W("| " + " | ".join("" if v is None else str(v) for v in row) + " |")
            W("")

        # Arm B derived summaries (full)
        W(f"### Arm B — derived summaries (DERIVED_SUMMARY), "
          f"HOME {len(pkB['derived_summaries']['HOME_TEAM'])} + "
          f"AWAY {len(pkB['derived_summaries']['AWAY_TEAM'])}\n")
        W("HOME_TEAM (metric·side·window·venue = value [n, reliability]):\n")
        for s in pkB["derived_summaries"]["HOME_TEAM"]:
            W(f"- {s['metric']}·{s['side']}·{s['window']}·{s['venue']} = {s['value']} "
              f"[n={s['sample_n']}, {s['reliability']}]")
        W("\nAWAY_TEAM:\n")
        for s in pkB["derived_summaries"]["AWAY_TEAM"]:
            W(f"- {s['metric']}·{s['side']}·{s['window']}·{s['venue']} = {s['value']} "
              f"[n={s['sample_n']}, {s['reliability']}]")
        W("")

        # opponent profile
        W("### Arm B — opponent-profile context (deterministic bands)\n")
        W("```json")
        W(json.dumps(pkB["opponent_profile_context"], indent=1, sort_keys=True))
        W("```\n")
        W("---\n")

    # byte-level export
    reqB = P.build_request(arm_b["mt_010244159"])
    with open(BYTE_EXPORT, "w") as fh:
        fh.write("=== SYSTEM ===\n")
        fh.write(reqB["system"])
        fh.write("\n=== USER (exact bytes) ===\n")
        fh.write(reqB["user"])
    reqA = P.build_request(arm_a["mt_010244159"])
    with open(BYTE_EXPORT_A, "w") as fh:
        fh.write("=== SYSTEM ===\n")
        fh.write(reqA["system"])
        fh.write("\n=== USER (exact bytes) ===\n")
        fh.write(reqA["user"])

    W("## Byte-level exports\n")
    W(f"- Arm B exact request (system + user bytes): "
      f"`research/hypothesis_oos/out/v5a/BYTELEVEL_ARM_B_mt_010244159.request.txt` "
      f"(user sha256 `{hashlib.sha256(reqB['user'].encode()).hexdigest()}`)")
    W(f"- Arm A exact request: "
      f"`research/hypothesis_oos/out/v5a/BYTELEVEL_ARM_A_mt_010244159.request.txt` "
      f"(user sha256 `{hashlib.sha256(reqA['user'].encode()).hexdigest()}`)\n")

    open(AUDIT_MD, "w").write("\n".join(L))
    import os
    print("wrote", AUDIT_MD, f"({os.path.getsize(AUDIT_MD)} bytes)")
    print("byte exports written")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
