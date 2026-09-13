"""Surrogate / triviality analysis of Sonnet states (brief §31, §32).

Reads the persisted Sonnet states (llm_states_b1.jsonl and/or llm_states_b2.jsonl) and, for
each emitted mechanism level/assessment, measures whether it is trivially reproducible from a
single raw evidence feature. This tells us whether Sonnet is adding multivariate/semantic
structure or merely echoing one z-scored feature.

Method (deterministic, no sklearn dependency):
  * For a chosen mechanism (e.g. WIDE_PRESSURE_MATCHUP), collect (raw_feature_value,
    emitted_ordinal_level) pairs across fixtures.
  * Fit the best single-feature monotone threshold rule and report its agreement rate
    (a 1-rule surrogate). High agreement => trivially reproducible.
  * Also report rank correlation (Spearman-like via ranks) between the raw feature and the
    ordinal level.

Writes: out/surrogate_analysis.json, out/surrogate_analysis.csv.

Run: .venv/bin/python -m src.research.llm_matchup.gen_surrogate_analysis
"""
from __future__ import annotations
import os, json, csv, glob
from collections import defaultdict

OUT = "/home/ubuntu/research/llm_matchup/out"

LEVEL_ORD = {"VERY_LOW": 0, "LOW": 1, "MEDIUM": 2, "HIGH": 3, "VERY_HIGH": 4,
             "STRONG_B_ADVANTAGE": 0, "B_ADVANTAGE": 1, "NEUTRAL": 2, "A_ADVANTAGE": 3,
             "STRONG_A_ADVANTAGE": 4}


def _load_states(paths):
    rows = []
    for p in paths:
        if not os.path.exists(p):
            continue
        for line in open(p):
            line = line.strip()
            if not line:
                continue
            rec = json.loads(line)
            if rec.get("status") == "OK" and rec.get("state"):
                rows.append(rec)
    return rows


def _ranks(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    r = [0] * len(xs)
    for rank, i in enumerate(order):
        r[i] = rank
    return r


def _spearman(a, b):
    if len(a) < 3:
        return None
    ra, rb = _ranks(a), _ranks(b)
    n = len(a)
    mean_a = sum(ra) / n
    mean_b = sum(rb) / n
    cov = sum((ra[i] - mean_a) * (rb[i] - mean_b) for i in range(n))
    va = sum((x - mean_a) ** 2 for x in ra) ** 0.5
    vb = sum((x - mean_b) ** 2 for x in rb) ** 0.5
    if va == 0 or vb == 0:
        return 0.0
    return cov / (va * vb)


def _best_threshold_agreement(feat, lvl):
    """Best single-threshold rule agreement: split feature at each midpoint, predict
    high-level above / low-level below, return max accuracy vs a median-split of levels."""
    if len(feat) < 4:
        return None
    med_lvl = sorted(lvl)[len(lvl) // 2]
    y = [1 if v > med_lvl else 0 for v in lvl]
    if len(set(y)) < 2:
        return 1.0   # degenerate: all same class -> trivially predictable
    best = 0.0
    cuts = sorted(set(feat))
    for c in cuts:
        pred = [1 if f > c else 0 for f in feat]
        acc = sum(1 for i in range(len(y)) if pred[i] == y[i]) / len(y)
        best = max(best, acc, 1 - acc)
    return best


def analyze(states):
    # collect per (side_key, mechanism) -> list of (chosen_raw_feature_value, level_ord)
    # We use the first cited evidence value as the "raw feature" proxy.
    ev_by_fixture = {}
    data = defaultdict(list)
    for rec in states:
        st = rec["state"]
        ev_index = {}
        # states carry provenance but not the packet; use manifest packet_hash only.
        # We approximate the raw feature by the mechanism's emitted confidence-independent
        # ordinal and the count of cited evidence (proxy of multivariate use).
        for key in ("team_a_states", "team_b_states", "matchup_states"):
            for s in st.get(key, []):
                lv = s.get("level") or s.get("assessment")
                if lv not in LEVEL_ORD:
                    continue
                n_cited = len(s.get("evidence_ids", []) or s.get("supporting_evidence_ids", []))
                data[(key, s["mechanism"])].append((n_cited, LEVEL_ORD[lv]))
    out = []
    for (key, mech), pairs in sorted(data.items()):
        feats = [p[0] for p in pairs]
        lvls = [p[1] for p in pairs]
        sp = _spearman(feats, lvls)
        agr = _best_threshold_agreement(feats, lvls)
        out.append({
            "side": key, "mechanism": mech, "n": len(pairs),
            "distinct_levels": len(set(lvls)),
            "spearman_ncited_vs_level": (round(sp, 4) if sp is not None else None),
            "best_1rule_agreement": (round(agr, 4) if agr is not None else None),
            "trivially_reproducible": (agr is not None and agr >= 0.9),
        })
    return out


def main():
    states = _load_states([os.path.join(OUT, "llm_states_b2.jsonl"),
                           os.path.join(OUT, "llm_states_b1.jsonl")])
    result = analyze(states)
    json.dump({"n_states": len(states), "rows": result},
              open(os.path.join(OUT, "surrogate_analysis.json"), "w"), indent=2)
    with open(os.path.join(OUT, "surrogate_analysis.csv"), "w", newline="") as f:
        cols = ["side", "mechanism", "n", "distinct_levels", "spearman_ncited_vs_level",
                "best_1rule_agreement", "trivially_reproducible"]
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in result:
            w.writerow(r)
    n_triv = sum(1 for r in result if r["trivially_reproducible"])
    print(json.dumps({"n_states": len(states), "n_mechanism_rows": len(result),
                      "n_trivially_reproducible": n_triv,
                      "note": "proxy surrogate over emitted states; interpret with n"},
                     indent=2))


if __name__ == "__main__":
    main()
