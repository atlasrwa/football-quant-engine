"""V7 hypothesis-universe extraction (`v7_universe_v1`). Phase 1. OUTCOME-BLIND, MECHANICAL.

Extracts EVERY V6.1 hypothesis that satisfies the FROZEN V6.1 definition of a qualified
research hypothesis -- `scorecard.per_hypothesis[i].qualified is True` -- and joins it to the
structural spec the model emitted in the raw payload, by `hypothesis_id` within a response.

It reads ONLY the immutable V6.1 execution artifacts (`scores.json` + `raw/NNN.json`). It
performs NO selection by persuasiveness, NO ranking, and NO inspection of any historical
effect (there is none to inspect). The qualification decision was made by the frozen V6.1
evaluator; V7 does not re-adjudicate it.

ZERO SPEND. Pure filesystem + structural copy.
"""
from __future__ import annotations

import hashlib
import json
import os

UNIVERSE_VERSION = "v7_universe_v1"

# The structural spec fields the model emitted per hypothesis. Copied verbatim -- V7 never
# rewrites a hypothesis. `candidate_confounders` and `evidence_summary` are carried as
# provenance/metadata; the deterministic confounder plan (Phase 11) does NOT trust the
# model's confounder list, it uses the frozen allowed set.
SPEC_FIELDS = (
    "target_metrics", "subject", "side", "comparison", "conditions", "window",
    "research_family", "required_capabilities", "evidence_refs", "candidate_confounders",
    "evidence_summary", "priority", "sufficiency", "question")


def _sha_str(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def _sha_file(path: str) -> str:
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def extract_universe(exec_dir: str) -> dict:
    """Return the full V7 hypothesis universe from the immutable V6.1 execution dir.

    A hypothesis is INCLUDED iff its frozen scorecard row has `qualified is True`. Each entry
    records a stable identity, its originating (fixture, arm, response seq, hypothesis_id),
    the structural spec, and provenance hashes binding it to the exact raw artifact.
    """
    scores = json.load(open(f"{exec_dir}/scores.json"))
    # index raw payloads by seq
    raw_by_seq = {}
    raw_dir = f"{exec_dir}/raw"
    for fn in sorted(os.listdir(raw_dir)):
        if fn.endswith(".json"):
            doc = json.load(open(f"{raw_dir}/{fn}"))
            raw_by_seq[int(doc["seq"])] = {"payload": doc.get("payload") or {},
                                           "request_sha256": doc.get("request_sha256"),
                                           "file": fn}

    entries = []
    n_total_rows = 0
    for s in sorted(scores, key=lambda x: x["seq"]):
        seq = int(s["seq"])
        arm = s["arm"]
        fixture_id = s["fixture_id"]
        rep = s.get("rep")
        sc = s["scorecard"]
        raw = raw_by_seq.get(seq, {})
        spec_by_id = {h.get("hypothesis_id"): h
                      for h in (raw.get("payload", {}).get("hypotheses") or [])}
        for ph in sc.get("per_hypothesis") or []:
            n_total_rows += 1
            if ph.get("qualified") is not True:
                continue
            hid = ph.get("hypothesis_id")
            spec = spec_by_id.get(hid, {})
            spec_copy = {k: spec.get(k) for k in SPEC_FIELDS}
            # a stable, provenance-bound identity: (fixture, arm, seq, rep, hid)
            identity_str = f"{fixture_id}|{arm}|{seq}|{rep}|{hid}"
            entry = {
                "v7_hypothesis_id": _sha_str(identity_str)[:24],
                "identity": identity_str,
                "originating_fixture": fixture_id,
                "arm": arm,
                "response_seq": seq,
                "rep": rep,
                "hypothesis_id": hid,
                "spec": spec_copy,
                "provenance": {
                    "raw_file": raw.get("file"),
                    "request_sha256": raw.get("request_sha256"),
                    "scorecard_qualified": True,
                    "conditioning_class": ph.get("conditioning_class"),
                    "outcome_class": ph.get("outcome_class")},
            }
            entries.append(entry)

    entries.sort(key=lambda e: (e["response_seq"], e["hypothesis_id"] or ""))
    by_arm = {"base": 0, "research": 0}
    for e in entries:
        by_arm[e["arm"]] = by_arm.get(e["arm"], 0) + 1
    return {
        "universe_version": UNIVERSE_VERSION,
        "source_exec_dir": exec_dir,
        "source_scores_sha256": _sha_file(f"{exec_dir}/scores.json"),
        "definition": ("QUALIFIED_RESEARCH_HYPOTHESIS = frozen V6.1 "
                       "scorecard.per_hypothesis[i].qualified is True. Extracted "
                       "mechanically; no selection by persuasiveness; no effect inspected."),
        "n_per_hypothesis_rows_total": n_total_rows,
        "n_qualified_total": len(entries),
        "n_qualified_by_arm": by_arm,
        "spec_fields": list(SPEC_FIELDS),
        "hypotheses": entries,
    }


def version_stamp() -> dict:
    return {"universe_version": UNIVERSE_VERSION,
            "outcome_blind": True, "mechanical": True,
            "reads_only_immutable_v6_1_execution": True,
            "spec_fields": list(SPEC_FIELDS)}
