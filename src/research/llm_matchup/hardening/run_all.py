"""Orchestrate the full pre-Phase-C hardening pipeline (patch §54).

Runs the live studies in a budget-respecting order, then the deterministic analyses, then
freezes the hardened generation. Each stage is independently runnable; this driver wires them
with shared, cost-saving cache reuse (all live calls share out/hardening/cache keyed by
packet_hash + call_index + prompt/schema content hash).

Order:
  1. repeatability   (k calls per stratified fixture; also persists the raw feature matrix)
  2. counter_golden  (synthetic adversarial cases)
  3. ablation_noise  (FULL vs ABLATION vs self-noise) — reuses repeatability full-call cache
  4. controls        (formation-shuffle / team-name / competition-name vs self-noise)
  5. surrogate       (deterministic; consumes feature matrix + states)
  6. aggregate       (deterministic; single-vs-3call comparison from repeatability states)
  7. eligibility     (deterministic; consumes all study artifacts) + cost accounting
  8. freeze_v2       (freeze the hardened generation manifest)

Run: .venv/bin/python -m src.research.llm_matchup.hardening.run_all [N] [K]
     (N = stratified fixtures for the live studies; K = calls per packet)
"""
from __future__ import annotations
import os, sys, json, time

from src.research.llm_matchup.hardening import run_repeatability as RR
from src.research.llm_matchup.hardening import run_counter_golden as RCG
from src.research.llm_matchup.hardening import run_ablation_noise as RAN
from src.research.llm_matchup.hardening import run_controls as RC
from src.research.llm_matchup.hardening import surrogate_ladder as SL
from src.research.llm_matchup.hardening import aggregate as AG
from src.research.llm_matchup.hardening import eligibility as EL
from src.research.llm_matchup.hardening import freeze_v2 as FZ

OUT = "/home/ubuntu/research/llm_matchup/out/hardening"


def _aggregate_comparison_from_states() -> dict:
    """Build the single-vs-3call aggregate comparison from the persisted repeatability states."""
    path = os.path.join(OUT, "llm_states_hardening.jsonl")
    if not os.path.exists(path):
        return {}
    by_fx = {}
    for line in open(path):
        line = line.strip()
        if not line:
            continue
        rec = json.loads(line)
        if rec.get("study") != "repeatability":
            continue
        by_fx.setdefault(rec["fixture_id"], []).append(rec.get("state") if rec.get("status") == "OK" else None)
    cmp = AG.compare_single_vs_aggregate({fx: [s for s in states] for fx, states in by_fx.items()})
    json.dump(cmp, open(os.path.join(OUT, "aggregate_comparison.json"), "w"), indent=2, default=str)
    return cmp


def run(n: int = 40, k: int = None, control_n: int = 15, use_cache: bool = True):
    os.makedirs(OUT, exist_ok=True)
    t0 = time.time()
    summary = {"pipeline": "pre_phase_c_hardening", "n": n, "k": k, "stages": {}}

    print("=== 1. repeatability ===")
    summary["stages"]["repeatability"] = RR.run(n=n, k=k, use_cache=use_cache)
    print("=== 2. counter_golden ===")
    summary["stages"]["counter_golden"] = RCG.run(k=2, use_cache=use_cache)
    print("=== 3. ablation_vs_noise ===")
    summary["stages"]["ablation_noise"] = RAN.run(n=control_n, k=k, use_cache=use_cache)
    print("=== 4. controls ===")
    summary["stages"]["controls"] = RC.run(n=control_n, k=k, use_cache=use_cache)
    print("=== 5. surrogate ladder ===")
    summary["stages"]["surrogate"] = SL.run()
    print("=== 6. aggregate comparison ===")
    summary["stages"]["aggregate"] = _aggregate_comparison_from_states()
    print("=== 7. mechanism eligibility + cost ===")
    summary["stages"]["eligibility"] = EL.run()
    print("=== 8. freeze LLM_MATCHUP_V2 ===")
    summary["stages"]["freeze_v2"] = FZ.freeze(force=False)

    summary["elapsed_s"] = round(time.time() - t0, 1)
    json.dump(summary, open(os.path.join(OUT, "pipeline_summary.json"), "w"), indent=2, default=str)
    print(json.dumps({"elapsed_s": summary["elapsed_s"],
                      "eligibility": summary["stages"]["eligibility"].get("class_counts")
                      if isinstance(summary["stages"].get("eligibility"), dict) else None}, indent=2))
    return summary


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 40
    k = int(sys.argv[2]) if len(sys.argv) > 2 else None
    run(n=n, k=k)
