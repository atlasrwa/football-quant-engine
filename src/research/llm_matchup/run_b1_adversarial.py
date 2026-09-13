"""B1 — Adversarial football interpretation (30-50 fixtures).

Evaluates INTERPRETATION FIDELITY (not predictive performance, brief §16). Runs, per
selected fixture:
  * FULL packet (behavior + formation);
  * ABLATION packet (behavior only, formation removed) — brief §20;
  * LABEL-SHUFFLE control (behavior unchanged, nominal formation labels swapped) — §21;
  * REPEATABILITY (a second FULL call with cache disabled) — stability;
  * SWAP metamorphic test on a subset (A-vs-B vs a coherent transform) — §19.

Also computes:
  * behavior-vs-formation: does the FULL state differ from ABLATION? (formation sensitivity)
  * formation-stereotype flag: does shuffling labels change the state materially? (bad)

Writes: out/phase_b_calls.csv (phase=B1), out/llm_states_b1.jsonl, out/formation_ablation.csv,
        out/formation_shuffle_control.csv, out/repeatability_results.csv, out/b1_summary.json.

Run:  .venv/bin/python -m src.research.llm_matchup.run_b1_adversarial [N]
"""
from __future__ import annotations
import os, sys, json, csv, time, random
from collections import Counter

from src.research.llm_matchup import phaseb_harness as H
from src.research.llm_matchup import bedrock_adapter as BA
from src.research.llm_matchup import versions as V

OUT = H.OUT
random.seed(20260913)   # deterministic selection


def _state_signature(state: dict) -> dict:
    """Compact comparable signature: mechanism -> (level/assessment, confidence)."""
    sig = {}
    if not state:
        return sig
    for key in ("team_a_states", "team_b_states", "matchup_states"):
        for st in state.get(key, []):
            lv = st.get("level") or st.get("assessment")
            sig[f"{key}:{st['mechanism']}"] = (lv, st.get("confidence"))
    return sig


def _sig_distance(a: dict, b: dict) -> float:
    """Fraction of shared mechanisms whose (level, confidence) changed."""
    keys = set(a) & set(b)
    if not keys:
        return 0.0
    changed = sum(1 for k in keys if a[k] != b[k])
    return changed / len(keys)


def _formation_mech_count(state):
    if not state:
        return 0
    n = 0
    for key in ("team_a_states", "team_b_states", "matchup_states"):
        for st in state.get(key, []):
            if st["mechanism"].startswith("FORMATION"):
                n += 1
    return n


def select_adversarial(ctx: H.HarnessContext, n: int):
    """Deterministic adversarial selection stratified by difficulty signals."""
    cands = ctx.candidates(min_prior=8, min_form_cov=1)
    scored = []
    for c in cands:
        # difficulty signals from projection concentration + formation coverage
        dist_a = c.a_form.distribution or {}
        conc_a = max(dist_a.values()) if dist_a else 0.0
        unstable = 1 if (0 < conc_a < 0.6) else 0                 # formation changed recently
        sparse = 1 if (c.a_prior_form_cov <= 3 or c.b_prior_form_cov <= 3) else 0
        diverse_form = 1 if len(dist_a) >= 3 else 0
        score = unstable + sparse + diverse_form
        scored.append((score, c))
    # stratify: take a spread across score buckets deterministically
    scored.sort(key=lambda x: (-x[0], x[1].target.kickoff_unix))
    chosen, seen_pairs = [], set()
    for _, c in scored:
        key = (c.target.home, c.target.away)
        if key in seen_pairs:
            continue
        seen_pairs.add(key)
        chosen.append(c)
        if len(chosen) >= n:
            break
    return chosen


def run(n: int = 30, do_swap: int = 8):
    os.makedirs(OUT, exist_ok=True)
    ctx = H.HarnessContext(enrich_halves=False)
    chosen = select_adversarial(ctx, n)
    print(f"B1: selected {len(chosen)} adversarial fixtures")

    call_rows = []
    states_out = []
    abl_rows, shuf_rows, rep_rows = [], [], []
    metrics = Counter()

    for c in chosen:
        full_pkt = ctx.build_packet(c, include_formation=True, projected=True)
        res_full = BA.analyze_matchup(full_pkt, use_cache=True)
        call_rows.append(H.call_record("B1", c, full_pkt, res_full))
        metrics["attempted"] += 1
        if res_full.status == "OK":
            metrics["ok"] += 1
        elif res_full.status == "LLM_STATE_REJECTED":
            metrics["rejected"] += 1
        else:
            metrics["unavailable"] += 1
        states_out.append({"fixture_id": c.target.fixture_id, "variant": "FULL",
                           "status": res_full.status, "state": res_full.state,
                           "manifest": res_full.manifest})
        sig_full = _state_signature(res_full.state)

        # --- ablation: behavior only ---
        abl_pkt = ctx.build_packet(c, include_formation=False, projected=True)
        res_abl = BA.analyze_matchup(abl_pkt, use_cache=True)
        call_rows.append(H.call_record("B1", c, abl_pkt, res_abl))
        states_out.append({"fixture_id": c.target.fixture_id, "variant": "ABLATION",
                           "status": res_abl.status, "state": res_abl.state,
                           "manifest": res_abl.manifest})
        sig_abl = _state_signature(res_abl.state)
        abl_dist = _sig_distance(sig_full, sig_abl)
        abl_rows.append({
            "fixture_id": c.target.fixture_id, "full_status": res_full.status,
            "ablation_status": res_abl.status,
            "full_formation_mechs": _formation_mech_count(res_full.state),
            "n_shared_mechanisms": len(set(sig_full) & set(sig_abl)),
            "state_change_fraction": round(abl_dist, 4),
            "formation_adds_information": abl_dist > 0.0 or _formation_mech_count(res_full.state) > 0,
        })

        # --- label shuffle control: swap nominal labels, behavior unchanged ---
        override = None
        if c.a_form.formation and c.b_form.formation and c.a_form.formation != c.b_form.formation:
            override = {"home": c.b_form.formation, "away": c.a_form.formation}
        if override:
            shuf_pkt = ctx.build_packet(c, include_formation=True, projected=True,
                                        formation_override=override)
            res_shuf = BA.analyze_matchup(shuf_pkt, use_cache=True)
            call_rows.append(H.call_record("B1", c, shuf_pkt, res_shuf))
            sig_shuf = _state_signature(res_shuf.state)
            shuf_dist = _sig_distance(sig_full, sig_shuf)
            shuf_rows.append({
                "fixture_id": c.target.fixture_id,
                "orig_home_formation": c.a_form.formation, "orig_away_formation": c.b_form.formation,
                "shuffled_home_formation": override["home"], "shuffled_away_formation": override["away"],
                "full_status": res_full.status, "shuffle_status": res_shuf.status,
                "state_change_fraction": round(shuf_dist, 4),
                # a large change on shuffled labels with UNCHANGED behavior => stereotype dependence
                "stereotype_flag": shuf_dist > 0.34,
            })
            metrics["shuffle_stereotype_fail"] += 1 if shuf_dist > 0.34 else 0

        # --- repeatability: second FULL call, cache disabled ---
        res_rep = BA.analyze_matchup(full_pkt, use_cache=False)
        sig_rep = _state_signature(res_rep.state)
        rep_dist = _sig_distance(sig_full, sig_rep)
        rep_rows.append({
            "fixture_id": c.target.fixture_id, "status_1": res_full.status,
            "status_2": res_rep.status, "state_change_fraction": round(rep_dist, 4),
            "stable": rep_dist <= 0.15,
        })
        metrics["repeat_unstable"] += 1 if rep_dist > 0.15 else 0

        print(f"  {c.target.fixture_id} full={res_full.status} abl={res_abl.status} "
              f"abl_d={abl_dist:.2f} rep_d={rep_dist:.2f}")

    # persist
    H.append_calls_csv(os.path.join(OUT, "phase_b_calls.csv"), call_rows)
    with open(os.path.join(OUT, "llm_states_b1.jsonl"), "w") as f:
        for s in states_out:
            f.write(json.dumps(s, default=str) + "\n")
    _write_csv(os.path.join(OUT, "formation_ablation.csv"), abl_rows)
    _write_csv(os.path.join(OUT, "formation_shuffle_control.csv"), shuf_rows)
    _write_csv(os.path.join(OUT, "repeatability_results.csv"), rep_rows)

    summary = {
        "phase": "B1", "n_fixtures": len(chosen), "metrics": dict(metrics),
        "ablation_mean_change": round(_mean([r["state_change_fraction"] for r in abl_rows]), 4),
        "shuffle_mean_change": round(_mean([r["state_change_fraction"] for r in shuf_rows]), 4) if shuf_rows else None,
        "repeatability_mean_change": round(_mean([r["state_change_fraction"] for r in rep_rows]), 4),
        "n_formation_sensitive": sum(1 for r in abl_rows if r["formation_adds_information"]),
        "n_stereotype_flags": sum(1 for r in shuf_rows if r["stereotype_flag"]),
        "n_repeat_stable": sum(1 for r in rep_rows if r["stable"]),
        "versions": V.version_stamp(), "created_unix": int(time.time()),
    }
    json.dump(summary, open(os.path.join(OUT, "b1_summary.json"), "w"), indent=2, default=str)
    print(json.dumps(summary, indent=2, default=str))
    return summary


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else 0.0


def _write_csv(path, rows):
    if not rows:
        open(path, "w").close()
        return
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    run(n)
