"""B2 — Corners-first capped pilot (<=300 fixtures, CORNERS ONLY).

Runs ONLY after B0 and B1 pass. Generates the frozen-stack Sonnet state dataset for the
corners market. Does NOT modify the quant model (brief §36). Predictive evaluation is
Phase C.

Selection is DETERMINISTIC and stratified across the football-state space (brief §23, §24):
competition, season bucket, venue corner environment, formation family, formation matchup,
behavioral cluster, evidence reliability. Fixture IDs + selection rationale are persisted
BEFORE any Sonnet call, in out/b2_selection.json.

Writes: out/b2_selection.json (BEFORE calls), out/phase_b_calls.csv (phase=B2),
        out/llm_states_b2.jsonl, out/b2_summary.json.

Run:  .venv/bin/python -m src.research.llm_matchup.run_b2_corners [CAP]  (default 120)
       set B2_SELECT_ONLY=1 to only write the selection manifest (no live calls).
"""
from __future__ import annotations
import os, sys, json, time, hashlib
from collections import Counter, defaultdict

from src.research.llm_matchup import phaseb_harness as H
from src.research.llm_matchup import bedrock_adapter as BA
from src.research.llm_matchup import cohorts as CH
from src.research.matchup.corpus import season_of
from src.research.llm_matchup import versions as V

OUT = H.OUT
CAP = 300                    # hard cap per brief §23


def _corner_env_bucket(env):
    if env is None:
        return "UNKNOWN"
    if env < 9.0:
        return "LOW_CORNER"
    if env < 11.0:
        return "MID_CORNER"
    return "HIGH_CORNER"


def _reliability_bucket(cand):
    m = min(cand.n_prior_a, cand.n_prior_b)
    if m >= 15:
        return "HIGH_HISTORY"
    if m >= 10:
        return "MED_HISTORY"
    return "LOW_HISTORY"


def _strata_key(ctx, cand):
    from src.research.llm_matchup.evidence import _league_env
    env = _league_env(ctx.recs, cand.target, "corners")
    return (
        cand.target.competition,
        str(cand.target.season_id)[:4],
        _corner_env_bucket(env),
        cand.a_form.formation_family,
        f"{cand.a_form.formation_family}_vs_{cand.b_form.formation_family}",
        _reliability_bucket(cand),
    )


def select(ctx: H.HarnessContext, cap: int):
    """Deterministic stratified selection. Round-robin across strata so no single
    stratum dominates; ordered within stratum by kickoff for reproducibility."""
    cands = ctx.candidates(min_prior=8, min_form_cov=1)
    strata = defaultdict(list)
    for c in cands:
        strata[_strata_key(ctx, c)].append(c)
    for k in strata:
        strata[k].sort(key=lambda c: (c.target.kickoff_unix, c.target.fixture_id))
    ordered_keys = sorted(strata.keys())
    chosen, i = [], 0
    while len(chosen) < min(cap, len(cands)):
        progressed = False
        for k in ordered_keys:
            if i < len(strata[k]):
                chosen.append((k, strata[k][i]))
                progressed = True
                if len(chosen) >= min(cap, len(cands)):
                    break
        if not progressed:
            break
        i += 1
    return chosen, strata


def write_selection(ctx, chosen, strata):
    rationale = {
        "policy": "deterministic_stratified_v1",
        "market": "corners",
        "cap": CAP,
        "seed_note": "no randomness; round-robin across sorted strata; within-stratum by kickoff",
        "strata_dimensions": ["competition", "season_bucket", "corner_env_bucket",
                              "formation_family", "formation_family_matchup", "history_reliability"],
        "n_candidates": sum(len(v) for v in strata.values()),
        "n_strata": len(strata),
        "n_selected": len(chosen),
        "strata_counts": {"|".join(map(str, k)): len(v) for k, v in sorted(strata.items())},
        "selected_fixture_ids": [c.target.fixture_id for _, c in chosen],
        "selected_detail": [
            {"fixture_id": c.target.fixture_id, "home": c.target.home, "away": c.target.away,
             "competition": c.target.competition, "stratum": "|".join(map(str, k)),
             "a_formation": c.a_form.formation, "b_formation": c.b_form.formation,
             "a_family": c.a_form.formation_family, "b_family": c.b_form.formation_family}
            for k, c in chosen
        ],
        "created_unix": int(time.time()),
    }
    rationale["selection_hash"] = hashlib.sha256(
        json.dumps(rationale["selected_fixture_ids"], sort_keys=True).encode()).hexdigest()
    os.makedirs(OUT, exist_ok=True)
    json.dump(rationale, open(os.path.join(OUT, "b2_selection.json"), "w"), indent=2, default=str)
    return rationale


def run(cap: int = 120):
    cap = min(cap, CAP)
    ctx = H.HarnessContext(enrich_halves=False)
    chosen, strata = select(ctx, cap)
    rationale = write_selection(ctx, chosen, strata)
    print(f"B2: selected {len(chosen)} fixtures across {len(strata)} strata "
          f"(selection_hash={rationale['selection_hash'][:12]})")
    print(f"B2: selection manifest written BEFORE any Sonnet call")

    if os.environ.get("B2_SELECT_ONLY") == "1":
        print("B2_SELECT_ONLY: skipping live calls")
        return {"phase": "B2", "select_only": True, "n_selected": len(chosen),
                "selection_hash": rationale["selection_hash"]}

    # Optional: execute only the first N of the frozen selection as a live subset (cost/
    # latency bound). The full deterministic selection is still persisted above, so the
    # dataset can be completed later without re-selection.
    live_limit = int(os.environ.get("B2_LIVE_LIMIT", str(len(chosen))))
    to_call = chosen[:live_limit]
    print(f"B2: executing {len(to_call)} live calls (of {len(chosen)} selected)")

    call_rows, states_out = [], []
    metrics = Counter()
    for k, c in to_call:
        pkt = ctx.build_packet(c, include_formation=True, projected=True)
        res = BA.analyze_matchup(pkt, use_cache=True)
        call_rows.append(H.call_record("B2", c, pkt, res))
        metrics["attempted"] += 1
        metrics[res.status] += 1
        states_out.append({"fixture_id": c.target.fixture_id, "stratum": "|".join(map(str, k)),
                           "status": res.status, "state": res.state, "manifest": res.manifest})
        print(f"  {c.target.fixture_id} {res.status}")

    H.append_calls_csv(os.path.join(OUT, "phase_b_calls.csv"), call_rows)
    with open(os.path.join(OUT, "llm_states_b2.jsonl"), "w") as f:
        for s in states_out:
            f.write(json.dumps(s, default=str) + "\n")

    summary = {
        "phase": "B2", "n_selected": len(chosen), "n_called": len(to_call),
        "n_strata": len(strata),
        "selection_hash": rationale["selection_hash"], "metrics": dict(metrics),
        "schema_valid_pct": round(100 * metrics.get("OK", 0) / max(1, metrics["attempted"]), 1),
        "versions": V.version_stamp(), "created_unix": int(time.time()),
    }
    json.dump(summary, open(os.path.join(OUT, "b2_summary.json"), "w"), indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    cap = int(sys.argv[1]) if len(sys.argv) > 1 else 120
    run(cap)
