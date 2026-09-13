"""Identifier / label controls, noise-referenced (patch §24, §25, §26).

Three adversarial controls, each measured against the SAME self-noise scale as ablation
(state_distance over the severity ladder). A control "trips" only when the perturbation's
induced state change MATERIALLY EXCEEDS identical-input self-noise — otherwise the model is
correctly ignoring the manipulated identifier/label.

  1. FORMATION LABEL-SHUFFLE v2 (patch §24). Behavior, numeric evidence, samples and context
     are UNCHANGED; only the nominal formation LABEL the cohorts key on is swapped (A<->B via
     formation_override). If the state changes materially beyond self-noise, the model is
     reacting to the formation LABEL as a stereotype -> FORMATION_STEREOTYPE_SENSITIVITY.

  2. TEAM-NAME control (patch §25). Real team names vs TEAM_A/TEAM_B, competition identical,
     evidence byte-identical. Material change -> the model leans on club-name stereotypes ->
     TEAM_NAME_SENSITIVITY (FAIL CLOSED for that mechanism/config).

  3. COMPETITION-NAME control (patch §26). Real competition vs COMP_NEUTRAL, team names kept,
     evidence identical. Material change -> league-stereotype dependence ->
     COMPETITION_NAME_SENSITIVITY.

For each control we need a self-noise reference; we reuse the FULL-packet k-call self-noise
computed on the SAME fixture (so the comparison is apples-to-apples). The runtime default is
already neutral identifiers (patch §25), so controls 2/3 measure the RISK that would exist if
real identifiers were sent — they justify keeping the neutral-by-default runtime.

Writes: formation_label_shuffle_v2.csv, team_name_control.csv, competition_name_control.csv,
controls_summary.json under out/hardening/.

Run: .venv/bin/python -m src.research.llm_matchup.hardening.run_controls [N] [K]
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


def _self_noise(full_ok_states) -> tuple[float, list[float]]:
    ds = []
    for a, b in itertools.combinations(full_ok_states, 2):
        d, _ = AN.state_distance(a, b)
        ds.append(d)
    p90 = sorted(ds)[int(0.9 * (len(ds) - 1))] if ds else 0.0
    return p90, ds


def run(n: int = 20, k: int = None, max_scan: int = 200, use_cache: bool = True):
    k = k or V2.REPEATABILITY_CALLS
    os.makedirs(OUT, exist_ok=True)
    ctx = H.HarnessContext(enrich_halves=False)
    picks = SMP.select_stratified(ctx, n=n, max_scan=max_scan)
    print(f"controls: {len(picks)} fixtures, k={k} self-noise calls + 3 control calls each")

    shuffle_rows, team_rows, comp_rows = [], [], []
    total_cost = 0.0

    for pi, p in enumerate(picks):
        cand = p.candidate
        full_real = ctx.build_packet(cand, include_formation=True, projected=True)
        full_neu = NZ.neutralize_packet(full_real)

        # self-noise reference on the neutral full packet
        full_results = A3.analyze_k(full_neu, k=k, use_cache=use_cache)
        for r in full_results:
            total_cost += A3.estimate_cost_usd(r.manifest.get("input_tokens"), r.manifest.get("output_tokens"))
        full_ok = [r.state for r in full_results if r.status == "OK"]
        if len(full_ok) < 2:
            print(f"  [{pi+1}/{len(picks)}] {p.fixture_id}: <2 OK full calls; skip")
            continue
        ref = full_ok[0]
        noise_p90, _ = _self_noise(full_ok)

        # 1. formation label-shuffle: swap A/B formation labels, behavior unchanged.
        af, bf = cand.a_form.formation, cand.b_form.formation
        if af and bf and af != bf:
            shuf_real = ctx.build_packet(cand, include_formation=True, projected=True,
                                         formation_override={"home": bf, "away": af})
            shuf_neu = NZ.neutralize_packet(shuf_real)
            rs = A3.analyze_matchup_v3(shuf_neu, use_cache=use_cache, call_index=0)
            total_cost += A3.estimate_cost_usd(rs.manifest.get("input_tokens"), rs.manifest.get("output_tokens"))
            if rs.status == "OK":
                d, _ = AN.state_distance(ref, rs.state)
                shuffle_rows.append({
                    "fixture_id": p.fixture_id, "competition": p.competition,
                    "orig_home_formation": af, "orig_away_formation": bf,
                    "shuffled_home_formation": bf, "shuffled_away_formation": af,
                    "shuffle_distance": d, "self_noise_p90": round(noise_p90, 4),
                    "exceeds_noise": d > noise_p90,
                    "flag": "FORMATION_STEREOTYPE_SENSITIVITY" if d > noise_p90 else "OK"})

        # 2. team-name control: real names vs neutral teams (competition identical).
        real_named, neutral_teams = NZ.team_name_control_pair(full_real)
        r_real = A3.analyze_matchup_v3(real_named, use_cache=use_cache, call_index=0)
        # neutral_teams == full_neu except competition kept real; call it directly
        r_neu = A3.analyze_matchup_v3(neutral_teams, use_cache=use_cache, call_index=0)
        for r in (r_real, r_neu):
            total_cost += A3.estimate_cost_usd(r.manifest.get("input_tokens"), r.manifest.get("output_tokens"))
        if r_real.status == "OK" and r_neu.status == "OK":
            d, _ = AN.state_distance(r_real.state, r_neu.state)
            team_rows.append({
                "fixture_id": p.fixture_id, "competition": p.competition,
                "team_name_distance": d, "self_noise_p90": round(noise_p90, 4),
                "exceeds_noise": d > noise_p90,
                "flag": "TEAM_NAME_SENSITIVITY" if d > noise_p90 else "OK"})

        # 3. competition-name control: real competition vs neutral (team names kept).
        real_comp, neutral_comp = NZ.competition_control_pair(full_real)
        c_real = A3.analyze_matchup_v3(real_comp, use_cache=use_cache, call_index=0)
        c_neu = A3.analyze_matchup_v3(neutral_comp, use_cache=use_cache, call_index=0)
        for r in (c_real, c_neu):
            total_cost += A3.estimate_cost_usd(r.manifest.get("input_tokens"), r.manifest.get("output_tokens"))
        if c_real.status == "OK" and c_neu.status == "OK":
            d, _ = AN.state_distance(c_real.state, c_neu.state)
            comp_rows.append({
                "fixture_id": p.fixture_id, "competition": p.competition,
                "competition_name_distance": d, "self_noise_p90": round(noise_p90, 4),
                "exceeds_noise": d > noise_p90,
                "flag": "COMPETITION_NAME_SENSITIVITY" if d > noise_p90 else "OK"})

        print(f"  [{pi+1}/{len(picks)}] {p.fixture_id} noise_p90={noise_p90:.3f} "
              f"shuffle={shuffle_rows[-1]['shuffle_distance'] if shuffle_rows and shuffle_rows[-1]['fixture_id']==p.fixture_id else 'NA'} "
              f"team={team_rows[-1]['team_name_distance'] if team_rows and team_rows[-1]['fixture_id']==p.fixture_id else 'NA'} "
              f"comp={comp_rows[-1]['competition_name_distance'] if comp_rows and comp_rows[-1]['fixture_id']==p.fixture_id else 'NA'}")

    AN.write_rows(os.path.join(OUT, "formation_label_shuffle_v2.csv"), shuffle_rows)
    AN.write_rows(os.path.join(OUT, "team_name_control.csv"), team_rows)
    AN.write_rows(os.path.join(OUT, "competition_name_control.csv"), comp_rows)

    def _rate(rows, flag):
        trips = sum(1 for r in rows if r["flag"] == flag)
        return {"n": len(rows), "n_tripped": trips,
                "trip_rate": round(trips / max(len(rows), 1), 4),
                "mean_distance": round(statistics.fmean([r[[c for c in r if c.endswith("_distance")][0]] for r in rows]), 4) if rows else None}

    summary = {
        "study": "identifier_controls", "generation_id": V2.GENERATION_ID,
        "n_fixtures": len(picks), "k_calls": k,
        "formation_label_shuffle": _rate(shuffle_rows, "FORMATION_STEREOTYPE_SENSITIVITY"),
        "team_name_control": _rate(team_rows, "TEAM_NAME_SENSITIVITY"),
        "competition_name_control": _rate(comp_rows, "COMPETITION_NAME_SENSITIVITY"),
        "cost_usd": round(total_cost, 4), "created_unix": int(time.time()),
    }
    json.dump(summary, open(os.path.join(OUT, "controls_summary.json"), "w"), indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))
    return summary


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    k = int(sys.argv[2]) if len(sys.argv) > 2 else None
    run(n=n, k=k)
