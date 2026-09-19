"""Generation-neutral V3 mechanism-eligibility core.

Extracted VERBATIM from `eligibility_v3_sonnet46` so both V3 arms are judged by one
implementation and one bar, exactly as `controls_v3_core` did for the control battery. The
scientific decision logic is generation-neutral -- only the wiring (versions module, response
cache, artifact paths, labels) differs -- so it is parameterized, not duplicated.

REUSED BY IMPORT from `eligibility` (unchanged, so the arms share the same thresholds):
    MIN_COVERAGE, MAX_SEVERE_DISAGREE, MIN_SEMANTIC_STABLE,
    MAX_IDENTITY_TRIP_RATE, MIN_N_FOR_IDENTITY_GATE, _control_verdict

FAIL-CLOSED SURROGATE RULE (inherited, not invented here). `eligibility.classify`'s terminal
class PHASE_C_ELIGIBLE requires a SURROGATE verdict -- evidence the mechanism is not a trivial
deterministic transform of the raw feature matrix. The surrogate ladder has NOT been run for
EITHER V3 arm (surrogate artifacts exist only under the V2/Phase-B out/hardening namespace and
belong to a different generation's states). So no V3 mechanism may be called PHASE_C_ELIGIBLE.
Mechanisms clearing every measured bar are classified:

    PENDING_SURROGATE  -- passed stability + sensitivity, but the surrogate check is missing,
                          so Phase-C eligibility is NOT established.

"we did not measure it" stays visibly distinct from "it passed".

Per-mechanism sensitivity is recomputed OFFLINE and FREE from each arm's own response cache:
the reference and formation-ablation states are already paid for, so the per-mechanism severity
of a genuine football evidence change is re-derived with zero new Bedrock calls.
"""
from __future__ import annotations
import csv as _csv
import json
import os
import statistics
from collections import Counter, defaultdict
from dataclasses import dataclass

from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup import phaseb_harness as H
from src.research.llm_matchup.hardening import ablation_noise as AN
from src.research.llm_matchup.hardening import adapter_v4 as A4
from src.research.llm_matchup.hardening import atomic_io as AIO
from src.research.llm_matchup.hardening import eligibility as EL
from src.research.llm_matchup.hardening import neutralize_v3 as NZ3
from src.research.llm_matchup.hardening import sampling as SMP


@dataclass
class EligibilityConfig:
    """The MINIMUM generation-specific wiring. Every threshold, class ladder and gate rule is
    shared by import -- nothing scientific lives in here."""
    name: str                 # "sonnet45" | "sonnet46" -- label only, never branched on
    gen: object               # versions module
    cache_dir: str
    manifest: dict            # frozen fixture manifest (for sampling params)
    controls_path: str
    repeat_path: str
    out_dir: str
    elig_json: str
    elig_csv: str
    sens_json: str
    gen_label: str            # "4.5" | "4.6" -- prose label inside reported strings
    coexists_with: str


#: Classes a FAILED identity gate must force-reject. Mirrors eligibility.apply_identity_gate's
#: set and ADDS PENDING_SURROGATE. Without it PENDING_SURROGATE would silently escape the gate
#: and a mechanism could read as "passed everything measured" although the generation's
#: identity gate FAILED. The gate is a generation-level fail-closed verdict; nothing survives it.
GATE_REJECTABLE_CLASSES = ("PHASE_C_ELIGIBLE", "REDUNDANT_WITH_DETERMINISTIC",
                           "PENDING_SURROGATE")


def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path))
    except Exception:
        return None


def _cached_state(cfg: EligibilityConfig, packet, call_index=0):
    """Load an ALREADY-PAID-FOR response from this generation's cache. Returns None if absent
    -- this function must never trigger a Bedrock call."""
    model_id = cfg.gen.DEFAULT_BEDROCK_MODEL_ID
    key = A4._cache_key(model_id, packet["packet_hash"], call_index, gen=cfg.gen)
    payload = A4._load_cache(key, cfg.cache_dir, expect_model_id=model_id)
    if not payload or payload.get("status") != "OK":
        return None
    return payload.get("state")


def per_mechanism_sensitivity(cfg: EligibilityConfig, k: int = 3, persist: bool = True) -> dict:
    """Per-mechanism response to a GENUINE football evidence change (formation ablation),
    referenced against that mechanism's own identical-input self-noise. Offline and free.

    For each fixture with a usable reference + ablation state in the cache:
      * noise severity per mechanism key = mean pairwise severity across the k identical calls
      * ablation severity per mechanism key = severity(reference, ablated)
    A mechanism is SENSITIVE when its mean ablation severity exceeds its mean noise severity.
    """
    controls = _read_json(cfg.controls_path) or {}
    fixture_ids = [r["fixture_id"] for r in
                   (controls.get("controls", {})
                            .get("D_behavior_sensitivity_formation_ablation", {})
                            .get("rows") or [])]
    if not fixture_ids:
        return {"status": "NO_ABLATION_ROWS"}

    sp = cfg.manifest["generation_fingerprint"]["sampling_params"]
    ctx = H.HarnessContext(enrich_halves=False)
    picks = {p.fixture_id: p for p in SMP.select_stratified(ctx, n=sp["n"],
                                                            max_scan=sp["max_scan"])}

    abl_sev = defaultdict(list)     # mechanism -> [severity]
    noise_sev = defaultdict(list)
    used = []
    for fid in fixture_ids:
        cand = picks[fid].candidate
        neu = NZ3.neutralize_for_llm_v2(
            ctx.build_packet(cand, include_formation=True, projected=True))
        neu_abl = NZ3.neutralize_for_llm_v2(
            ctx.build_packet(cand, include_formation=False, projected=True))

        ref_states = [s for s in (_cached_state(cfg, neu, i) for i in range(k)) if s]
        abl_state = _cached_state(cfg, neu_abl, 0)
        if not ref_states or not abl_state:
            continue
        ref = ref_states[0]
        used.append(fid)

        _, per_key_abl = AN.state_distance(ref, abl_state)
        for key, sev in per_key_abl.items():
            abl_sev[key.split(":", 1)[1]].append(sev)

        for i in range(len(ref_states)):
            for j in range(i + 1, len(ref_states)):
                _, pk = AN.state_distance(ref_states[i], ref_states[j])
                for key, sev in pk.items():
                    noise_sev[key.split(":", 1)[1]].append(sev)

    rows = {}
    for mech in sorted(set(abl_sev) | set(noise_sev)):
        a = abl_sev.get(mech, [])
        nz = noise_sev.get(mech, [])
        a_mean = round(statistics.fmean(a), 4) if a else None
        n_mean = round(statistics.fmean(nz), 4) if nz else None
        if a_mean is None or n_mean is None:
            flag = "INSUFFICIENT_DATA"
        elif a_mean > n_mean:
            flag = "SENSITIVE_TO_EVIDENCE"
        else:
            flag = "UNSTABLE_SENSITIVITY"
        rows[mech] = {"mechanism": mech, "n_ablation_obs": len(a), "n_noise_obs": len(nz),
                      "ablation_severity_mean": a_mean, "noise_severity_mean": n_mean,
                      "sensitivity_margin": (round(a_mean - n_mean, 4)
                                             if (a_mean is not None and n_mean is not None)
                                             else None),
                      "flag": flag}
    out = {"study": f"golden_v3_{cfg.name}_mechanism_sensitivity",
           "generation_id": cfg.gen.GENERATION_ID, "k": k,
           "fixtures_used": used, "n_fixtures_used": len(used),
           "note": (f"Recomputed OFFLINE from the already-paid {cfg.gen_label} response cache; "
                    "zero new Bedrock calls. Perturbation = formation ablation "
                    "(include_formation=False), the established V3 genuine-evidence change."),
           "rows": rows}
    if persist:
        AIO.atomic_write_json(cfg.sens_json, out)
    return out


def collect_signals(cfg: EligibilityConfig, sens: dict | None = None) -> dict:
    """Per-mechanism signals from this arm's repeatability study + per-mechanism sensitivity."""
    repeat = _read_json(cfg.repeat_path) or {}
    sig = defaultdict(lambda: {"coverage": 0, "n_severe": 0, "n_total": 0, "n_stable": 0,
                               "sensitivity_flag": None, "sensitivity_margin": None,
                               "surrogate_verdict": None, "surrogate_s1": None})
    for r in repeat.get("field_rows", []) or []:
        mech = EL._mech_of(r.get("mechanism_key", ""))
        s = sig[mech]
        s["coverage"] += 1
        s["n_total"] += 1
        ws = r.get("worst_severity") or 0
        if ws >= 3:
            s["n_severe"] += 1
        if ws <= 1:
            s["n_stable"] += 1
    for mech, row in ((sens or {}).get("rows") or {}).items():
        sig[mech]["sensitivity_flag"] = row.get("flag")
        sig[mech]["sensitivity_margin"] = row.get("sensitivity_margin")
    return sig


def classify(cfg: EligibilityConfig, sig: dict) -> list[dict]:
    """Same ladder as eligibility.classify, except the terminal class is PENDING_SURROGATE
    instead of PHASE_C_ELIGIBLE because no V3 surrogate ladder was run (fail closed)."""
    surrogate_label = f"NOT_RUN_FOR_{cfg.name.upper()}"
    rows = []
    for mech in sorted(ONT.MECHANISMS.keys()):
        s = sig.get(mech)
        if not s or s["coverage"] < EL.MIN_COVERAGE:
            rows.append({"mechanism": mech, "family": ONT.MECHANISMS[mech]["family"],
                         "coverage": (s["coverage"] if s else 0),
                         "eligibility": "INSUFFICIENT_COVERAGE"})
            continue
        n = s["n_total"] or 1
        severe_frac = s["n_severe"] / n
        stable_frac = s["n_stable"] / n
        sens_flag = s["sensitivity_flag"]

        if severe_frac > EL.MAX_SEVERE_DISAGREE or stable_frac < EL.MIN_SEMANTIC_STABLE:
            elig = "RESEARCH_ONLY_UNSTABLE"
        elif sens_flag == "UNSTABLE_SENSITIVITY":
            elig = "RESEARCH_ONLY_UNSTABLE"
        elif sens_flag in (None, "INSUFFICIENT_DATA"):
            elig = "INSUFFICIENT_COVERAGE"
        else:
            elig = "PENDING_SURROGATE"
        rows.append({
            "mechanism": mech, "family": ONT.MECHANISMS[mech]["family"],
            "coverage": s["coverage"], "semantic_stable_frac": round(stable_frac, 4),
            "severe_disagree_frac": round(severe_frac, 4),
            "sensitivity_flag": sens_flag, "sensitivity_margin": s["sensitivity_margin"],
            "surrogate_verdict": surrogate_label,
            "eligibility": elig,
        })
    return rows


def identity_gate(cfg: EligibilityConfig) -> dict:
    """This arm's global identity gate, read from its controls artifact. Reshaped to the key
    `phase_c_eligible_generation` so eligibility.apply_identity_gate semantics carry over."""
    controls = _read_json(cfg.controls_path) or {}
    gate = dict(controls.get("identity_gate") or {})
    if not gate:
        return {"gate": "identity_controls_global_gate", "verdicts": {},
                "failed_controls": ["NOT_RUN"], "phase_c_eligible_generation": False,
                "reason": "NOT_PHASE_C_ELIGIBLE: identity controls not run (fail closed)"}
    passed = gate.get("identity_gate_passed", False)
    gate["phase_c_eligible_generation"] = bool(passed)
    if not passed:
        gate["reason"] = ("NOT_PHASE_C_ELIGIBLE: " + ", ".join(
            f"{n}={gate['verdicts'][n]['status']}"
            f" (trip_rate={gate['verdicts'][n].get('trip_rate')}, n={gate['verdicts'][n].get('n')})"
            for n in gate.get("failed_controls", []) if n in gate.get("verdicts", {})))
    return gate


def apply_identity_gate(rows: list[dict], gate: dict) -> list[dict]:
    """Same contract as eligibility.apply_identity_gate (pre-gate class preserved for audit,
    never silently overwritten) but over GATE_REJECTABLE_CLASSES so PENDING_SURROGATE cannot
    bypass a failed gate."""
    if gate.get("phase_c_eligible_generation"):
        return rows
    out = []
    for r in rows:
        r = dict(r)
        if r["eligibility"] in GATE_REJECTABLE_CLASSES:
            r["pre_gate_eligibility"] = r["eligibility"]
            r["eligibility"] = "REJECTED"
            r["reject_reason"] = gate.get("reason")
        out.append(r)
    return out


def run(cfg: EligibilityConfig, k: int = 3, persist: bool = True) -> dict:
    sens = per_mechanism_sensitivity(cfg, k=k, persist=persist)
    sig = collect_signals(cfg, sens if sens.get("rows") else None)
    rows = classify(cfg, sig)
    gate = identity_gate(cfg)
    rows = apply_identity_gate(rows, gate)

    counts = Counter(r["eligibility"] for r in rows)
    summary = {
        "study": f"V3_{cfg.name.upper()}_ELIGIBILITY",
        "generation_id": cfg.gen.GENERATION_ID,
        "model_id": cfg.gen.DEFAULT_BEDROCK_MODEL_ID,
        "coexists_with": cfg.coexists_with,
        "thresholds": {
            "MIN_COVERAGE": EL.MIN_COVERAGE,
            "MAX_SEVERE_DISAGREE": EL.MAX_SEVERE_DISAGREE,
            "MIN_SEMANTIC_STABLE": EL.MIN_SEMANTIC_STABLE,
            "MAX_IDENTITY_TRIP_RATE": EL.MAX_IDENTITY_TRIP_RATE,
            "MIN_N_FOR_IDENTITY_GATE": EL.MIN_N_FOR_IDENTITY_GATE,
            "source": "imported unchanged from hardening.eligibility",
        },
        "n_mechanisms": len(rows),
        "class_counts": dict(counts),
        "identity_gate": gate,
        "phase_c_eligible_generation": gate.get("phase_c_eligible_generation"),
        "surrogate_status": (f"NOT_RUN_FOR_{cfg.name.upper()} -- no {cfg.gen_label} mechanism "
                             "can be PHASE_C_ELIGIBLE; the terminal passing class is "
                             "PENDING_SURROGATE (fail closed)"),
        "mechanism_sensitivity": {k2: v for k2, v in sens.items() if k2 != "rows"},
        "rows": rows,
    }
    if persist:
        AIO.atomic_write_json(cfg.elig_json, summary)
        if rows:
            cols = ["mechanism", "family", "eligibility", "coverage", "semantic_stable_frac",
                    "severe_disagree_frac", "sensitivity_flag", "sensitivity_margin",
                    "surrogate_verdict", "pre_gate_eligibility", "reject_reason"]
            os.makedirs(cfg.out_dir, exist_ok=True)
            tmp = cfg.elig_csv + ".tmp"
            with open(tmp, "w", newline="") as f:
                w = _csv.DictWriter(f, fieldnames=cols)
                w.writeheader()
                for r in rows:
                    w.writerow({c: r.get(c) for c in cols})
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, cfg.elig_csv)
    return summary
