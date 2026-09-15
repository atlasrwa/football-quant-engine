"""Freeze the deterministic measurement corpus from the immutable V3 outputs. ZERO SPEND.

Eligibility is MECHANICAL and is evaluated entirely from frozen V3 artifacts, before any
historical data is read. Nothing here can see a match outcome, an effect, a sample size or
a direction -- the corpus is fixed before the measurement layer is ever invoked.

INCLUSION RULE (both clauses required)
    control == "reference"                 -- the unperturbed, factually-true packet arm
    whole_response_failure is None         -- the response survived the frozen V3 gates
    the hypothesis is in `accepted_hypotheses` for that response

The repeatability arm is DELIBERATELY excluded from the measurement corpus (it re-sends 6
of the same 12 frozen packets, so folding it in would double-count those fixtures in every
family denominator) and is retained ONLY as input to the duplicate/equivalent-query
analysis, where same-input plan agreement is the quantity of interest.

Every other arm sent a deliberately altered packet (perturbed shot surfaces, withheld
dimensions, starved evidence, unsupported-data traps) and therefore proposes research about
counterfactual football. Those are instrument controls, not research proposals.
"""
from __future__ import annotations

import json
import os
import sys

ROOT = "/home/ubuntu"
sys.path.insert(0, ROOT + "/src")
sys.path.insert(0, ROOT + "/research/hypothesis_engine")

import _analyze_v3 as A                                          # noqa: E402
from research.hypothesis_engine import lifecycle                 # noqa: E402

OUT = f"{ROOT}/research/hypothesis_engine/out/v3_hypothesis_measurement"
CORPUS_VERSION = "v3_measurement_corpus_v1"


def build() -> dict:
    man, packets, specs, scored = A.score_all()

    included, excluded = [], []
    for seq in sorted(scored):
        e = scored[seq]
        ctrl = e["control"]
        if not e.get("completed"):
            excluded.append({"seq": seq, "control": ctrl, "fixture_id": e["fixture_id"],
                             "level": "RESPONSE", "n_hypotheses": 0,
                             "reason": "INFRASTRUCTURE_CENSORED"})
            continue
        if ctrl != "reference":
            excluded.append({"seq": seq, "control": ctrl, "fixture_id": e["fixture_id"],
                             "level": "RESPONSE", "n_hypotheses": e["n_hypotheses"],
                             "reason": "NON_REFERENCE_ARM",
                             "detail": "packet was deliberately transformed or duplicated; "
                                       "not an unperturbed research proposal"})
            continue
        if e["whole_response_failure"] is not None:
            excluded.append({"seq": seq, "control": ctrl, "fixture_id": e["fixture_id"],
                             "level": "RESPONSE", "n_hypotheses": e["n_hypotheses"],
                             "reason": e["whole_response_failure"],
                             "detail": "whole-response rejection under frozen V3 gates; "
                                       "no hypothesis salvaged"})
            continue

        accepted_ids = {h["hypothesis_id"] for h in (e["accepted"] or [])}
        payload = (e["validation"].canonical_payload or {})
        for h in (payload.get("hypotheses") or []):
            hid = h.get("hypothesis_id")
            rec = {"seq": seq, "control": ctrl, "fixture_id": e["fixture_id"],
                   "hypothesis_id": hid, "hypothesis": h}
            if hid in accepted_ids:
                included.append(rec)
            else:
                rec["level"] = "HYPOTHESIS"
                rec["reason"] = "NOT_ACCEPTED_BY_FROZEN_V3_VALIDATOR"
                excluded.append(rec)

    return {
        "corpus_version": CORPUS_VERSION,
        "source_experiment": man["experiment_id"],
        "source_manifest_hash": man["manifest_hash"],
        "inclusion_rule": {
            "control": "reference",
            "whole_response_failure": None,
            "hypothesis_in": "validator_v2.accepted_hypotheses",
        },
        "excluded_from_corpus_but_used_for_duplicate_analysis": ["repeatability"],
        "selection_inputs_forbidden": [
            "match outcome", "future fixture statistics", "closing line",
            "apparent plausibility", "effect direction", "effect magnitude",
            "statistical significance"],
        "n_included": len(included),
        "n_excluded_records": len(excluded),
        "included": included,
        "excluded": excluded,
    }


def repeatability_payloads() -> list:
    """Same-input duplicate-analysis input. Not part of the measurement corpus."""
    _, _, _, scored = A.score_all()
    out = []
    for seq in sorted(scored):
        e = scored[seq]
        if e["control"] != "repeatability" or not e.get("completed"):
            continue
        if e["whole_response_failure"] is not None:
            continue
        out.append({"seq": seq, "fixture_id": e["fixture_id"],
                    "hypotheses": e["accepted"] or []})
    return out


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    corpus = build()
    with open(f"{OUT}/frozen_hypothesis_corpus.json", "w") as fh:
        json.dump(corpus, fh, indent=1, sort_keys=True)
    rep = repeatability_payloads()
    with open(f"{OUT}/repeatability_payloads.json", "w") as fh:
        json.dump(rep, fh, indent=1, sort_keys=True)
    print(f"corpus: {corpus['n_included']} eligible hypotheses from "
          f"{len({r['seq'] for r in corpus['included']})} reference responses")
    from collections import Counter
    print("exclusions:", dict(Counter(r["reason"] for r in corpus["excluded"])))
    print(f"repeatability responses retained for duplicate analysis: {len(rep)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
