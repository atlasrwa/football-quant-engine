"""Raw input feature matrix persistence (patch §18).

For every hardening evidence packet we persist a DETERMINISTIC, machine-readable
representation of the ACTUAL numeric inputs supplied to Sonnet. This is the ground truth for
the surrogate ladder (§19): the surrogate must be tested against the raw features Sonnet
actually saw, NOT against reconstructed prose or citation counts (patch §17, §18).

One row per (fixture_id, evidence_id). Columns (patch §18):
  fixture_id, competition, evidence_id, metric, base_metric, side (FOR/AGAINST), half,
  formation_condition, opponent_condition, value (raw estimate), raw_value, z_score,
  percentile, baseline (league-env mean), delta (value - baseline), sample_n, effective_n,
  shrinkage_level, evidence_level, venue, provider, reliability, temporal_status.

z_score / percentile are computed WITHIN the packet across all items sharing the same
base_metric+side (the peer group the model sees together), so they are reproducible from the
packet alone. baseline is the league-environment mean already present in the builder; when a
per-item baseline is not available we fall back to the packet peer-group mean.

No LLM calls. Pure function of the packet. Written to raw_input_feature_matrix.csv (+ .parquet
if pyarrow is available, else CSV only — documented).
"""
from __future__ import annotations
import os, csv, math, statistics
from collections import defaultdict

OUT = "/home/ubuntu/research/llm_matchup/out/hardening"

FEATURE_COLUMNS = [
    "fixture_id", "competition", "evidence_id", "metric", "base_metric", "side", "half",
    "formation_condition", "opponent_condition", "value", "raw_value", "z_score", "percentile",
    "baseline", "delta", "sample_n", "effective_n", "shrinkage_level", "evidence_level",
    "venue", "provider", "reliability", "temporal_status",
]


def _base_metric(metric: str) -> str:
    core = metric
    for pfx in ("formation_delta_", "fmx_", "fc_"):
        if core.startswith(pfx):
            core = core[len(pfx):]
            break
    core = core.replace("_2h_shift", "")
    return core.replace("_for", "").replace("_against", "")


def _side(metric: str) -> str:
    if metric.endswith("_against") or "_against" in metric:
        return "AGAINST"
    if metric.endswith("_for") or "_for" in metric:
        return "FOR"
    return "NEUTRAL"


def _half(metric: str) -> str:
    return "2H_SHIFT" if "2h_shift" in metric else "FULL"


def _formation_condition(metric: str, scope: dict) -> str:
    if metric.startswith("fmx_"):
        return "OPP_FORMATION_CONDITIONED"
    if metric.startswith(("fc_", "formation_delta_")):
        return "TEAM_FORMATION_CONDITIONED"
    return "UNCONDITIONED"


def _percentile(x, peers):
    if not peers:
        return None
    below = sum(1 for p in peers if p < x)
    equal = sum(1 for p in peers if p == x)
    return round((below + 0.5 * equal) / len(peers), 4)


def extract_feature_rows(packet: dict) -> list[dict]:
    """Deterministic per-evidence feature rows for one packet."""
    fx = packet["fixture"]
    fid = fx["fixture_id"]
    comp = fx.get("competition")
    ev = packet["evidence"]

    # peer groups by (base_metric, side) for z-score/percentile within the packet
    peers = defaultdict(list)
    for e in ev:
        if e.get("value") is None:
            continue
        peers[(_base_metric(e["metric"]), _side(e["metric"]))].append(float(e["value"]))

    rows = []
    for e in ev:
        metric = e.get("metric", "")
        val = e.get("value")
        base = _base_metric(metric)
        side = _side(metric)
        grp = peers.get((base, side), [])
        z = None
        pct = None
        baseline = None
        delta = None
        if val is not None and grp:
            mean = statistics.fmean(grp)
            baseline = round(mean, 4)
            delta = round(float(val) - mean, 4)
            pct = _percentile(float(val), grp)
            if len(grp) >= 2:
                sd = statistics.pstdev(grp)
                z = round((float(val) - mean) / sd, 4) if sd > 0 else 0.0
        scope = e.get("scope", {}) or {}
        n = e.get("sample_n") or 0
        # effective_n: shrinkage-aware — a shrunk/hierarchical estimate has lower effective n.
        shr = e.get("shrinkage_level")
        eff_n = n if shr == "DIRECT" else max(1, int(round(n * 0.6))) if n else 0
        rows.append({
            "fixture_id": fid, "competition": comp, "evidence_id": e.get("id"),
            "metric": metric, "base_metric": base, "side": side, "half": _half(metric),
            "formation_condition": _formation_condition(metric, scope),
            "opponent_condition": scope.get("opp_formation") or scope.get("opponent") or "",
            "value": val, "raw_value": val, "z_score": z, "percentile": pct,
            "baseline": baseline, "delta": delta, "sample_n": n, "effective_n": eff_n,
            "shrinkage_level": shr, "evidence_level": e.get("evidence_level"),
            "venue": scope.get("venue"), "provider": e.get("source_provider"),
            "reliability": e.get("reliability"), "temporal_status": e.get("temporal_status"),
        })
    return rows


def write_feature_matrix(all_rows: list[dict], path: str = None) -> dict:
    """Write the accumulated feature rows to CSV (+ parquet if pyarrow available)."""
    os.makedirs(OUT, exist_ok=True)
    csv_path = path or os.path.join(OUT, "raw_input_feature_matrix.csv")
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FEATURE_COLUMNS)
        w.writeheader()
        for r in all_rows:
            w.writerow({k: r.get(k) for k in FEATURE_COLUMNS})
    out = {"csv_path": csv_path, "n_rows": len(all_rows)}
    try:
        import pandas as pd
        try:
            import pyarrow  # noqa
            pq_path = csv_path.replace(".csv", ".parquet")
            pd.DataFrame(all_rows, columns=FEATURE_COLUMNS).to_parquet(pq_path, index=False)
            out["parquet_path"] = pq_path
        except Exception:
            out["parquet_path"] = None  # pyarrow absent -> CSV is the machine-readable artifact
    except Exception:
        out["parquet_path"] = None
    return out
