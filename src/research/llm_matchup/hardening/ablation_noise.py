"""Normalized ablation-vs-noise signal (patch §21, §22, §23).

The central scientific test (patch §58): does the state change because FOOTBALL EVIDENCE
changed, or because Sonnet changes anyway? We answer it by comparing:

    D_ablation = distance(state_full, state_ablated)      # response to removing formation
against the empirical distribution of
    D_noise    = distance(state_call_i, state_call_j)      # identical-input self-noise

for the SAME fixtures. A formation ablation (or any evidence perturbation) counts as
MEANINGFUL only if its induced change MATERIALLY EXCEEDS normal repeatability variation
(patch §23). Mechanisms whose ablation distance does NOT exceed self-noise are flagged
UNSTABLE_SENSITIVITY (patch §21).

Distance metric (deterministic, reuses the repeatability severity ladder so ablation and
noise are measured on the SAME scale): for two states, the per-mechanism-key severity (0-4)
averaged over shared mechanism keys, normalized to [0,1] by /4. Mechanisms present in only
one state contribute the max severity (4/4=1.0) for that key (a presence change is a large
response). We report BOTH an overall distance and a per-mechanism severity so §23 can be
answered per formation mechanism.

This module is PURE given the states; the runner (run_ablation_noise) performs the live FULL
vs ABLATION calls and reads the repeatability self-noise from the repeatability study output.
"""
from __future__ import annotations
import os, csv, json, statistics
from collections import defaultdict

from src.research.llm_matchup.hardening import repeatability as REP

OUT = "/home/ubuntu/research/llm_matchup/out/hardening"


def _state_index(state: dict) -> dict:
    """mechanism_key -> (status, confidence)."""
    idx = {}
    if not state:
        return idx
    for side in ("team_a_states", "team_b_states", "matchup_states"):
        for st in state.get(side, []):
            key = f"{side}:{st['mechanism']}"
            idx[key] = (st.get("level") or st.get("assessment"), st.get("confidence"))
    return idx


def state_distance(a: dict, b: dict) -> tuple[float, dict]:
    """Normalized 0-1 distance + per-key severity between two states, using the severity ladder."""
    ia, ib = _state_index(a), _state_index(b)
    keys = set(ia) | set(ib)
    if not keys:
        return 0.0, {}
    per_key = {}
    for k in keys:
        if k in ia and k in ib:
            sev = REP.severity(ia[k][0], ia[k][1], ib[k][0], ib[k][1])
        else:
            sev = 4  # presence change = maximal response
        per_key[k] = sev
    dist = sum(per_key.values()) / (4.0 * len(keys))
    return round(dist, 4), per_key


def _formation_keys(per_key: dict) -> list[str]:
    return [k for k in per_key if k.split(":", 1)[1].startswith("FORMATION")]


def analyze_pair(fixture_id: str, full_state: dict, ablated_state: dict,
                 noise_distances: list[float], noise_per_key: dict) -> dict:
    """Compare one fixture's ablation distance vs the self-noise distribution (patch §22)."""
    d_abl, per_key = state_distance(full_state, ablated_state)
    noise_mean = statistics.fmean(noise_distances) if noise_distances else 0.0
    noise_p90 = (sorted(noise_distances)[int(0.9 * (len(noise_distances) - 1))]
                 if noise_distances else 0.0)
    # formation-specific ablation severity vs formation self-noise (patch §23)
    fkeys = _formation_keys(per_key)
    form_abl = (statistics.fmean([per_key[k] / 4.0 for k in fkeys]) if fkeys else 0.0)
    form_noise = statistics.fmean(
        [noise_per_key[k] for k in noise_per_key if k.split(":", 1)[1].startswith("FORMATION")]
        or [0.0])
    return {
        "fixture_id": fixture_id,
        "ablation_distance": d_abl,
        "self_noise_mean": round(noise_mean, 4),
        "self_noise_p90": round(noise_p90, 4),
        "ablation_exceeds_noise": d_abl > noise_p90,
        "ablation_gt_noise_mean": d_abl > noise_mean,
        "formation_ablation_norm": round(form_abl, 4),
        "formation_self_noise_norm": round(form_noise, 4),
        "formation_meaningful": form_abl > max(form_noise, 0.0) and form_abl > 0.0,
        "n_formation_keys": len(fkeys),
    }


def per_mechanism_sensitivity(pair_rows: list[dict], per_key_by_fixture: dict,
                              noise_per_key_by_fixture: dict) -> list[dict]:
    """Aggregate per-mechanism: mean ablation severity vs mean self-noise severity (patch §21).
    Flags UNSTABLE_SENSITIVITY when ablation response does not exceed self-noise."""
    abl = defaultdict(list)
    noise = defaultdict(list)
    for fx, pk in per_key_by_fixture.items():
        for k, sev in pk.items():
            abl[k].append(sev / 4.0)
    for fx, pk in noise_per_key_by_fixture.items():
        for k, sev in pk.items():
            noise[k].append(sev / 4.0)
    rows = []
    for k in sorted(set(abl) | set(noise)):
        a = statistics.fmean(abl[k]) if abl.get(k) else 0.0
        nz = statistics.fmean(noise[k]) if noise.get(k) else 0.0
        exceeds = a > nz and a > 0.05
        rows.append({
            "mechanism_key": k,
            "mean_ablation_norm": round(a, 4),
            "mean_self_noise_norm": round(nz, 4),
            "sensitivity_margin": round(a - nz, 4),
            "exceeds_self_noise": exceeds,
            "flag": "OK" if exceeds else "UNSTABLE_SENSITIVITY",
        })
    return rows


def write_rows(path: str, rows: list[dict]):
    if not rows:
        open(path, "w").close()
        return
    cols = list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow(r)
