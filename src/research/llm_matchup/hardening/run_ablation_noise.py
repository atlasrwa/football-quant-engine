"""Ablation-vs-noise + formation ablation v2 runner (patch §21, §22, §23).

For a stratified fixture subset, for each fixture:
  * run the FULL neutralized packet k times (self-noise reference + a full state);
  * run the ABLATION packet (include_formation=False) once;
  * compute D_ablation vs the fixture's self-noise distribution, and formation-specific
    ablation vs formation self-noise (patch §23).
Then aggregate a PER-MECHANISM sensitivity table flagging UNSTABLE_SENSITIVITY where the
ablation response does not exceed self-noise (patch §21).

Writes: out/hardening/ablation_vs_noise.csv (per fixture), formation_ablation_v2.csv
(per mechanism sensitivity), ablation_noise_summary.json.

Run: .venv/bin/python -m src.research.llm_matchup.hardening.run_ablation_noise [N] [K]
"""
from __future__ import annotations
import os, sys, json, time, itertools, statistics

from src.research.llm_matchup import phaseb_harness as H
from src.research.llm_matchup.hardening import sampling as SMP
from src.research.llm_matchup.hardening import neutralize as NZ
from src.research.llm_matchup.hardening import adapter_v3 as A3
from src.research.llm_matchup.hardening import ablation_noise as AN
from src.research.llm_matchup.hardening import versions_v2 as V2

OUT = "/home/ubuntu/research/llm_matchup/out/hardening"


def run(n: int = 20, k: int = None, max_scan: int = 200, use_cache: bool = True):
    k = k or V2.REPEATABILITY_CALLS
    os.makedirs(OUT, exist_ok=True)
    ctx = H.HarnessContext(enrich_halves=False)
    picks = SMP.select_stratified(ctx, n=n, max_scan=max_scan)
    print(f"ablation-vs-noise: {len(picks)} fixtures, k={k} full calls + 1 ablation each")

    pair_rows = []
    per_key_by_fixture = {}
    noise_per_key_by_fixture = {}
    total_cost = 0.0

    for pi, p in enumerate(picks):
        cand = p.candidate
        full_real = ctx.build_packet(cand, include_formation=True, projected=True)
        abl_real = ctx.build_packet(cand, include_formation=False, projected=True)
        full_pkt = NZ.neutralize_packet(full_real)
        abl_pkt = NZ.neutralize_packet(abl_real)

        full_results = A3.analyze_k(full_pkt, k=k, use_cache=use_cache)
        abl_result = A3.analyze_matchup_v3(abl_pkt, use_cache=use_cache, call_index=0)
        for r in full_results + [abl_result]:
            m = r.manifest
            total_cost += A3.estimate_cost_usd(m.get("input_tokens"), m.get("output_tokens"))

        full_ok = [r.state for r in full_results if r.status == "OK"]
        if len(full_ok) < 2 or abl_result.status != "OK":
            print(f"  [{pi+1}/{len(picks)}] {p.fixture_id}: insufficient OK calls "
                  f"(full_ok={len(full_ok)}, abl={abl_result.status}); skip")
            continue

        # self-noise distribution: pairwise distances among the full calls
        noise_ds = []
        noise_pk_accum = {}
        for a, b in itertools.combinations(full_ok, 2):
            d, pk = AN.state_distance(a, b)
            noise_ds.append(d)
            for kk, sev in pk.items():
                noise_pk_accum.setdefault(kk, []).append(sev)
        noise_per_key = {kk: statistics.fmean(v) for kk, v in noise_pk_accum.items()}
        noise_per_key_by_fixture[p.fixture_id] = noise_per_key

        # ablation distance: reference full state (first OK) vs ablated state
        ref_full = full_ok[0]
        d_abl, per_key = AN.state_distance(ref_full, abl_result.state)
        per_key_by_fixture[p.fixture_id] = per_key

        row = AN.analyze_pair(p.fixture_id, ref_full, abl_result.state, noise_ds, noise_per_key)
        row["competition"] = p.competition
        row["strata"] = "|".join(sorted(p.strata))
        pair_rows.append(row)
        print(f"  [{pi+1}/{len(picks)}] {p.fixture_id} D_abl={row['ablation_distance']} "
              f"noise_p90={row['self_noise_p90']} exceeds={row['ablation_exceeds_noise']} "
              f"form_meaningful={row['formation_meaningful']}")

    AN.write_rows(os.path.join(OUT, "ablation_vs_noise.csv"), pair_rows)
    mech_rows = AN.per_mechanism_sensitivity(pair_rows, per_key_by_fixture, noise_per_key_by_fixture)
    AN.write_rows(os.path.join(OUT, "formation_ablation_v2.csv"), mech_rows)

    n_exceed = sum(1 for r in pair_rows if r["ablation_exceeds_noise"])
    n_form_meaningful = sum(1 for r in pair_rows if r["formation_meaningful"])
    n_unstable = sum(1 for r in mech_rows if r["flag"] == "UNSTABLE_SENSITIVITY")
    form_mech_rows = [r for r in mech_rows if r["mechanism_key"].split(":", 1)[1].startswith("FORMATION")]
    summary = {
        "study": "ablation_vs_noise", "generation_id": V2.GENERATION_ID,
        "n_fixtures_analyzed": len(pair_rows), "k_calls": k,
        "n_ablation_exceeds_noise": n_exceed,
        "frac_ablation_exceeds_noise": round(n_exceed / max(len(pair_rows), 1), 4),
        "n_formation_meaningful": n_form_meaningful,
        "frac_formation_meaningful": round(n_form_meaningful / max(len(pair_rows), 1), 4),
        "n_mechanisms": len(mech_rows), "n_unstable_sensitivity": n_unstable,
        "n_formation_mechanisms": len(form_mech_rows),
        "n_formation_mechanisms_ok": sum(1 for r in form_mech_rows if r["flag"] == "OK"),
        "mean_ablation_distance": round(statistics.fmean([r["ablation_distance"] for r in pair_rows]), 4) if pair_rows else None,
        "mean_self_noise": round(statistics.fmean([r["self_noise_mean"] for r in pair_rows]), 4) if pair_rows else None,
        "cost_usd": round(total_cost, 4), "created_unix": int(time.time()),
    }
    json.dump(summary, open(os.path.join(OUT, "ablation_noise_summary.json"), "w"),
              indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    k = int(sys.argv[2]) if len(sys.argv) > 2 else None
    run(n=n, k=k)
