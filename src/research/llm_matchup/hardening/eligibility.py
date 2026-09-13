"""Phase-C eligibility classifier + cost accounting (patch §34, §50, §51, §52).

Classifies each ontology mechanism into a Phase-C eligibility class using MEASUREMENT
QUALITY ONLY — coverage, repeatability, evidence-sensitivity-vs-noise, counter-evidence
behavior, surrogate non-triviality, stereotype controls. It NEVER reads Phase-C predictive
outcomes (patch §52). The separation is the whole point of this hardening generation.

Classes (patch §50):
  PHASE_C_ELIGIBLE            — sufficient coverage, acceptable repeatability, sensitivity
                                exceeds self-noise, controls pass, not trivially redundant
                                (or redundant-but-useful).
  RESEARCH_ONLY_UNSTABLE      — coverage ok but repeatability/sensitivity fails
                                (UNSTABLE_SENSITIVITY or high severe-disagreement).
  REDUNDANT_WITH_DETERMINISTIC— reproduced ~perfectly by a single raw feature (surrogate
                                TRIVIALLY_REDUCIBLE). Still may be kept for interpretability
                                (patch §51) but not claimed as incremental intelligence.
  INSUFFICIENT_COVERAGE       — too few labelled fixtures to judge.
  REJECTED                    — fails a hard control (formation-stereotype / team-name /
                                competition-name sensitivity) OR severe repeatability failure.

Inputs are the study artifacts written under out/hardening/. Deterministic given those files.

Cost accounting (patch §34): from hardened_call_manifest.csv we report cost per fixture, per
stable state, per accepted state, and per incremental usable mechanism.

IDENTITY-CONTROL GLOBAL GATE (patch §24, §25, §26, §56). The formation-label-shuffle,
team-name, and competition-name controls are measured at the PACKET level (patch §25: "FAIL
CLOSED for that mechanism/prompt configuration"), not per-mechanism, so they cannot be
attributed to one mechanism — they indict the shared prompt/schema/runtime configuration
itself. The gate is therefore a single OR-of-three-failures check applied to the WHOLE
generation, exactly as specified for this hardening pass:

    if team_name_sensitivity fails
    or competition_name_sensitivity fails
    or formation_label_sensitivity fails:
        LLM layer = NOT PHASE_C ELIGIBLE

When the gate fails, every mechanism that would otherwise have been PHASE_C_ELIGIBLE or
REDUNDANT_WITH_DETERMINISTIC is force-reclassified to REJECTED (the pre-gate class is kept
alongside it for audit — patch §32/§33: preserve disagreement, don't hide it). Mechanisms
already RESEARCH_ONLY_UNSTABLE / INSUFFICIENT_COVERAGE for other reasons are left as-is; they
were not going to proceed either way, and re-labelling them would blur the actual cause.

MAX_IDENTITY_TRIP_RATE (0.20) is a conservative, pre-committed "materially above noise" bar,
not fit to the observed data — the first measured rates (formation 75%, team-name 69%,
competition-name 54%) are so far above any defensible bar that the exact threshold value is
not load-bearing here. MIN_N_FOR_IDENTITY_GATE guards against calling a control "passed" on
too few usable fixtures: a control that produced fewer than this many valid pairs is
INCONCLUSIVE, and — fail-closed, no salvage (patch §43) — INCONCLUSIVE is treated the same as
FAILED for gating purposes: absence of evidence that a control passed is not evidence that it
passed.
"""
from __future__ import annotations
import os, csv, json
from collections import defaultdict

from src.research.llm_matchup import ontology as ONT

OUT = "/home/ubuntu/research/llm_matchup/out/hardening"

# thresholds (documented; conservative — measurement quality, not prediction)
MIN_COVERAGE = 8                 # min labelled fixtures for a mechanism to be judged
MAX_SEVERE_DISAGREE = 0.34       # >1/3 severe disagreement -> unstable
MIN_SEMANTIC_STABLE = 0.60       # <60% semantically stable -> unstable

# identity-control global gate (patch §24-§26, §56)
MAX_IDENTITY_TRIP_RATE = 0.20    # trip_rate above this -> control FAILS (pre-committed bar)
MIN_N_FOR_IDENTITY_GATE = 5      # fewer usable pairs than this -> control is INCONCLUSIVE


def _read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path) as f:
        return list(csv.DictReader(f))


def _f(x, default=None):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _b(x):
    return str(x).strip().lower() in ("true", "1", "yes")


def _mech_of(key: str) -> str:
    return key.split(":", 1)[1] if ":" in key else key


def collect_signals() -> dict:
    """Gather per-mechanism measurement signals from the study artifacts."""
    sig = defaultdict(lambda: {
        "coverage": 0, "n_severe": 0, "n_total": 0, "n_stable": 0,
        "sensitivity_flag": None, "sensitivity_margin": None,
        "surrogate_verdict": None, "surrogate_s1": None,
    })

    # repeatability field-level -> coverage + severity
    for r in _read_csv(os.path.join(OUT, "repeatability_field_level.csv")):
        mech = _mech_of(r.get("mechanism_key", ""))
        s = sig[mech]
        s["coverage"] += 1
        s["n_total"] += 1
        ws = _f(r.get("worst_severity"), 0) or 0
        if ws >= 3:
            s["n_severe"] += 1
        if ws <= 1:
            s["n_stable"] += 1

    # ablation-vs-noise per-mechanism sensitivity
    for r in _read_csv(os.path.join(OUT, "formation_ablation_v2.csv")):
        mech = _mech_of(r.get("mechanism_key", ""))
        sig[mech]["sensitivity_flag"] = r.get("flag")
        sig[mech]["sensitivity_margin"] = _f(r.get("sensitivity_margin"))

    # surrogate verdicts
    for r in _read_csv(os.path.join(OUT, "surrogate_results.csv")):
        mech = r.get("mechanism")
        if mech:
            sig[mech]["surrogate_verdict"] = r.get("verdict")
            sig[mech]["surrogate_s1"] = _f(r.get("s1_best_single"))
    return sig


def _control_verdict(control: dict | None) -> dict:
    """PASS / FAIL / INCONCLUSIVE for one identity control, against the pre-committed bar."""
    n = (control or {}).get("n", 0) or 0
    trip_rate = (control or {}).get("trip_rate")
    if n < MIN_N_FOR_IDENTITY_GATE or trip_rate is None:
        return {"status": "INCONCLUSIVE", "n": n, "trip_rate": trip_rate}
    status = "FAIL" if trip_rate > MAX_IDENTITY_TRIP_RATE else "PASS"
    return {"status": status, "n": n, "trip_rate": trip_rate}


def identity_gate() -> dict:
    """Global OR-of-three-failures gate over the identity/label controls (patch §24-§26, §56):

        if team_name_sensitivity fails
        or competition_name_sensitivity fails
        or formation_label_sensitivity fails:
            LLM layer = NOT PHASE_C ELIGIBLE

    INCONCLUSIVE (too few usable pairs) counts as a failure to pass, not a pass (fail-closed,
    patch §43 — no salvage). Reads controls_summary.json written by run_controls.py.
    """
    controls = _read_json(os.path.join(OUT, "controls_summary.json")) or {}
    verdicts = {
        "formation_label_shuffle": _control_verdict(controls.get("formation_label_shuffle")),
        "team_name_control": _control_verdict(controls.get("team_name_control")),
        "competition_name_control": _control_verdict(controls.get("competition_name_control")),
    }
    failed = [name for name, v in verdicts.items() if v["status"] != "PASS"]
    passed_all = len(failed) == 0
    return {
        "gate": "identity_controls_global_gate",
        "threshold": {"max_trip_rate": MAX_IDENTITY_TRIP_RATE,
                      "min_n": MIN_N_FOR_IDENTITY_GATE},
        "verdicts": verdicts,
        "failed_controls": failed,
        "phase_c_eligible_generation": passed_all,
        "reason": (None if passed_all else
                  "NOT_PHASE_C_ELIGIBLE: " + ", ".join(
                      f"{name}={verdicts[name]['status']}"
                      f" (trip_rate={verdicts[name]['trip_rate']}, n={verdicts[name]['n']})"
                      for name in failed)),
    }


def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path))
    except Exception:
        return None


def classify(sig: dict) -> list[dict]:
    rows = []
    for mech in sorted(ONT.MECHANISMS.keys()):
        s = sig.get(mech)
        if not s or s["coverage"] < MIN_COVERAGE:
            rows.append({"mechanism": mech, "family": ONT.MECHANISMS[mech]["family"],
                         "coverage": (s["coverage"] if s else 0),
                         "eligibility": "INSUFFICIENT_COVERAGE"})
            continue
        n = s["n_total"] or 1
        severe_frac = s["n_severe"] / n
        stable_frac = s["n_stable"] / n
        sens_flag = s["sensitivity_flag"]
        verdict = s["surrogate_verdict"]

        # hard failures first
        if severe_frac > MAX_SEVERE_DISAGREE or stable_frac < MIN_SEMANTIC_STABLE:
            elig = "RESEARCH_ONLY_UNSTABLE"
        elif sens_flag == "UNSTABLE_SENSITIVITY":
            elig = "RESEARCH_ONLY_UNSTABLE"
        elif verdict == "TRIVIALLY_REDUCIBLE":
            elig = "REDUNDANT_WITH_DETERMINISTIC"
        else:
            elig = "PHASE_C_ELIGIBLE"

        rows.append({
            "mechanism": mech, "family": ONT.MECHANISMS[mech]["family"],
            "coverage": s["coverage"], "semantic_stable_frac": round(stable_frac, 4),
            "severe_disagree_frac": round(severe_frac, 4),
            "sensitivity_flag": sens_flag, "sensitivity_margin": s["sensitivity_margin"],
            "surrogate_verdict": verdict, "surrogate_s1": s["surrogate_s1"],
            "eligibility": elig,
        })
    return rows


def cost_accounting(elig_rows: list[dict]) -> dict:
    """Cost per fixture / stable state / accepted state / usable mechanism (patch §34)."""
    calls = _read_csv(os.path.join(OUT, "hardened_call_manifest.csv"))
    total_cost = sum(_f(c.get("cost_usd"), 0.0) or 0.0 for c in calls)
    fixtures = {c.get("fixture_id") for c in calls}
    n_ok = sum(1 for c in calls if c.get("status") == "OK")

    # stable states / accepted states from repeatability field-level
    fl = _read_csv(os.path.join(OUT, "repeatability_field_level.csv"))
    n_states = len(fl)
    n_stable_states = sum(1 for r in fl if (_f(r.get("worst_severity"), 0) or 0) <= 1)

    eligible = [r for r in elig_rows if r["eligibility"] == "PHASE_C_ELIGIBLE"]
    usable = [r for r in elig_rows if r["eligibility"] in
              ("PHASE_C_ELIGIBLE", "REDUNDANT_WITH_DETERMINISTIC")]
    return {
        "total_cost_usd": round(total_cost, 4),
        "n_calls": len(calls), "n_ok_calls": n_ok, "n_fixtures": len(fixtures),
        "cost_per_fixture": round(total_cost / max(len(fixtures), 1), 4),
        "cost_per_call": round(total_cost / max(len(calls), 1), 4),
        "cost_per_stable_state": round(total_cost / max(n_stable_states, 1), 4),
        "cost_per_accepted_state": round(total_cost / max(n_ok, 1), 4),
        "n_phase_c_eligible_mechanisms": len(eligible),
        "cost_per_incremental_usable_mechanism": round(total_cost / max(len(eligible), 1), 4),
        "n_usable_mechanisms": len(usable),
    }


def apply_identity_gate(rows: list[dict], gate: dict) -> list[dict]:
    """Force-reclassify otherwise-usable mechanisms to REJECTED when the global identity-
    control gate fails (patch §25: FAIL CLOSED for that mechanism/prompt configuration). The
    pre-gate class is preserved for audit (patch §32/§33: preserve disagreement, don't hide
    it) instead of silently overwriting it."""
    if gate["phase_c_eligible_generation"]:
        return rows
    out = []
    for r in rows:
        r = dict(r)
        if r["eligibility"] in ("PHASE_C_ELIGIBLE", "REDUNDANT_WITH_DETERMINISTIC"):
            r["pre_gate_eligibility"] = r["eligibility"]
            r["eligibility"] = "REJECTED"
            r["reject_reason"] = gate["reason"]
        out.append(r)
    return out


def run() -> dict:
    os.makedirs(OUT, exist_ok=True)
    sig = collect_signals()
    rows = classify(sig)
    gate = identity_gate()
    rows = apply_identity_gate(rows, gate)
    _write_csv(os.path.join(OUT, "mechanism_eligibility.csv"), rows)
    cost = cost_accounting(rows)
    from collections import Counter
    counts = Counter(r["eligibility"] for r in rows)
    summary = {"study": "mechanism_eligibility",
               "n_mechanisms": len(rows), "class_counts": dict(counts),
               "identity_gate": gate,
               "phase_c_eligible_generation": gate["phase_c_eligible_generation"],
               "cost_accounting": cost, "rows": rows}
    json.dump(summary, open(os.path.join(OUT, "mechanism_eligibility.json"), "w"),
              indent=2, default=str)
    return summary


def _write_csv(path, rows):
    if not rows:
        open(path, "w").close()
        return
    cols = sorted({k for r in rows for k in r})
    # stable column order: mechanism, family, eligibility first
    lead = ["mechanism", "family", "eligibility", "coverage"]
    cols = lead + [c for c in cols if c not in lead]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in cols})


if __name__ == "__main__":
    print(json.dumps(run()["class_counts"], indent=2))
