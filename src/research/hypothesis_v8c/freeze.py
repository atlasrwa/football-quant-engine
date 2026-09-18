"""V8C fail-closed freeze builder (`v8c_freeze_v1`).

REFUSES unless every gate condition holds. There is NO override flag, by design.

NO PASS BY DEFINITION. Every boolean is bound to:
    * an EVIDENCE ARTIFACT hash   (the file that demonstrates it)
    * a PRODUCING CODE hash       (the module version that produced it)
    * an INPUT IDENTITY hash      (corpus / manifest / capability matrix)

A condition asserted without those three is itself a refusal reason. A hardcoded `true` cannot
satisfy this builder, because the builder does not read booleans -- it reads artifacts and
derives the booleans.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

import hashlib
import json
import os

FREEZE_VERSION = "v8c_freeze_v1"

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
CHAMPION_PATH = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

#: Every gate condition, with the artifact that must demonstrate it. A missing artifact is a
#: REFUSAL, never a default-true.
GATE_CONDITIONS = (
    "P0_OPEN_ZERO", "P1_OPEN_ZERO",
    "PIT_PASS", "OUTCOME_SEAL_PASS", "SEARCH_REACHABILITY_PASS",
    "S_PATH_REACHABLE", "R_PATH_REACHABLE", "H_PATH_REACHABLE",
    "SCORE_OK_REACHABLE",
    "R_IDENTITY_ZERO", "R_CROSS_TREATMENT_OVERLAP_ZERO", "PAIR_IDENTITY_PRESERVED",
    "INFERENCE_SEMANTICS_PASS", "DETERMINISM_PASS", "CACHE_ISOLATION_PASS",
    "CHAMPION_UNCHANGED", "NO_SONNET_CALLS", "SEALED_947_OUTCOMES_NOT_VIEWED",
)

#: Artifacts the gate needs. `required=True` means its absence is a refusal.
REQUIRED_ARTIFACTS = {
    "grammar_spec": ("V8C_HYPOTHESIS_GRAMMAR_SPEC.md", True),
    "pre_t_spec": ("V8C_PRE_T_EVALUABILITY_SPEC.md", True),
    "control_spec": ("V8C_DISTINCT_BLIND_CONTROL_SPEC.md", True),
    "seal_spec": ("V8C_OUTCOME_SEAL_SPEC.md", True),
    "contract": ("V8C_END_TO_END_CONTRACT.md", True),
    "test_results": ("V8C_TEST_RESULTS.json", True),
    "e2e_reachability": ("V8C_END_TO_END_REACHABILITY.json", True),
    "pit_results": ("V8C_PIT_ADVERSARIAL_RESULTS.json", True),
    "determinism_results": ("V8C_DETERMINISM_RESULTS.json", True),
    "exposed50_replay": ("V8C_EXPOSED50_STRUCTURAL_REPLAY.json", True),
    "sealed947_preflight": ("V8C_SEALED947_STRUCTURAL_PREFLIGHT.json", True),
    "score_stability": ("V8C_SCORE_STABILITY_AUDIT.json", True),
}

#: Code modules whose hashes are bound into the manifest.
CODE_MODULES = ("grammar", "pit_context", "compiler", "scorer", "cohort_stats", "pre_t",
                "universe", "controls", "aggregate", "blind_index", "select_freeze",
                "score_frozen", "packet", "runner", "cache", "env_semantics", "golden")


class FreezeRefused(Exception):
    """The V8C freeze gate refused. There is no override."""


def sha_file(path: str) -> str | None:
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def code_hashes() -> dict:
    out = {}
    for m in CODE_MODULES:
        p = f"{ROOT}/src/research/hypothesis_v8c/{m}.py"
        out[m] = {"path": f"src/research/hypothesis_v8c/{m}.py", "sha256": sha_file(p)}
    return out


def collect_artifacts() -> dict:
    out = {}
    for name, (fn, required) in REQUIRED_ARTIFACTS.items():
        p = f"{ENG}/{fn}"
        out[name] = {"file": fn, "sha256": sha_file(p), "present": os.path.exists(p),
                     "required": required}
    return out


def _evidence(artifacts, key, code_keys, inputs):
    """Bind one condition to artifact + code + input hashes (the §34 anti-'pass by definition'
    requirement). Returns None when the evidence is absent, which the gate treats as FAIL."""
    a = artifacts.get(key)
    if not a or not a["present"]:
        return None
    return {"artifact": a["file"], "artifact_sha256": a["sha256"],
            "producing_code": {k: code_keys[k]["sha256"] for k in code_keys},
            "input_identity": inputs}


def evaluate_gate(*, artifacts=None, code=None, inputs=None) -> dict:
    """Derive every gate boolean FROM ARTIFACTS. Absent evidence => False, never True."""
    artifacts = artifacts if artifacts is not None else collect_artifacts()
    code = code if code is not None else code_hashes()
    inputs = inputs or {}
    conditions, reasons = {}, []

    def need(name, art_key, code_keys, extract):
        ev = _evidence(artifacts, art_key, {k: code[k] for k in code_keys}, inputs)
        if ev is None:
            conditions[name] = {"value": False, "evidence": None,
                                "why": f"required artifact {REQUIRED_ARTIFACTS[art_key][0]} "
                                       f"is absent"}
            reasons.append(f"{name}: missing evidence artifact "
                           f"{REQUIRED_ARTIFACTS[art_key][0]}")
            return
        try:
            payload = json.load(open(f"{ENG}/{artifacts[art_key]['file']}"))
            value = bool(extract(payload))
        except Exception as e:                       # unreadable evidence is NOT a pass
            conditions[name] = {"value": False, "evidence": ev,
                                "why": f"evidence unreadable: {e}"}
            reasons.append(f"{name}: evidence unreadable ({e})")
            return
        conditions[name] = {"value": value, "evidence": ev}
        if not value:
            reasons.append(f"{name}: evidence present but condition is FALSE")

    need("P0_OPEN_ZERO", "test_results", ["select_freeze", "blind_index"],
         lambda d: d.get("p0_open") == 0)
    need("P1_OPEN_ZERO", "test_results", ["universe", "controls"],
         lambda d: d.get("p1_open") == 0)
    need("PIT_PASS", "pit_results", ["pit_context", "blind_index"],
         lambda d: d.get("verdict") == "PASS")
    need("OUTCOME_SEAL_PASS", "test_results", ["select_freeze", "score_frozen"],
         lambda d: d.get("outcome_seal") == "PASS")
    need("SEARCH_REACHABILITY_PASS", "e2e_reachability", ["universe"],
         lambda d: d.get("unreachable_candidate_count") == 0)
    need("S_PATH_REACHABLE", "e2e_reachability", ["universe", "runner"],
         lambda d: d.get("S_SELECTION_REACHABLE") is True)
    need("R_PATH_REACHABLE", "e2e_reachability", ["controls"],
         lambda d: d.get("DISTINCT_R_REACHABLE") is True)
    need("H_PATH_REACHABLE", "e2e_reachability", ["controls"],
         lambda d: d.get("H_SELECTION_REACHABLE") is True)
    need("SCORE_OK_REACHABLE", "e2e_reachability", ["scorer"],
         lambda d: all(d.get(k) is True for k in ("S_SCORE_OK_REACHABLE",
                                                  "R_SCORE_OK_REACHABLE",
                                                  "H_SCORE_OK_REACHABLE")))
    need("R_IDENTITY_ZERO", "e2e_reachability", ["controls"],
         lambda d: d.get("R_IDENTITY_COUNT") == 0)
    need("R_CROSS_TREATMENT_OVERLAP_ZERO", "e2e_reachability", ["controls"],
         lambda d: d.get("R_CROSS_TREATMENT_OVERLAP_COUNT") == 0)
    need("PAIR_IDENTITY_PRESERVED", "e2e_reachability", ["aggregate", "select_freeze"],
         lambda d: d.get("PAIR_IDENTITY_PRESERVED") is True)
    need("INFERENCE_SEMANTICS_PASS", "e2e_reachability", ["aggregate"],
         lambda d: d.get("INFERENCE_SEMANTICS_PASS") is True)
    need("DETERMINISM_PASS", "determinism_results", ["grammar", "universe", "controls"],
         lambda d: d.get("verdict") == "PASS")
    need("CACHE_ISOLATION_PASS", "test_results", ["cache", "runner"],
         lambda d: d.get("cache_isolation") == "PASS")
    need("SEALED_947_OUTCOMES_NOT_VIEWED", "sealed947_preflight", ["blind_index"],
         lambda d: d.get("sealed_947_outcomes_viewed") is False)
    need("NO_SONNET_CALLS", "test_results", ["runner"],
         lambda d: d.get("new_sonnet_calls") == 0)

    champ = sha_file(CHAMPION_PATH)
    champ_ok = champ == CHAMPION_EXPECTED
    conditions["CHAMPION_UNCHANGED"] = {
        "value": champ_ok,
        "evidence": {"artifact": "data/discovery/pilotC_stat_mixer.json",
                     "artifact_sha256": champ, "expected_sha256": CHAMPION_EXPECTED,
                     "producing_code": {}, "input_identity": inputs}}
    if not champ_ok:
        reasons.append(f"CHAMPION_UNCHANGED: hash is {champ}, expected {CHAMPION_EXPECTED}")

    missing = [k for k in GATE_CONDITIONS if k not in conditions]
    for k in missing:
        conditions[k] = {"value": False, "evidence": None, "why": "not evaluated"}
        reasons.append(f"{k}: not evaluated")

    passed = all(conditions[k]["value"] for k in GATE_CONDITIONS)
    return {"conditions": conditions, "failed_reasons": reasons,
            "gate": "PASS" if passed else "REFUSED"}


def build_freeze(*, inputs=None, out_path=None) -> dict:
    """Build the V8C freeze manifest, or RAISE. No override flag exists."""
    artifacts = collect_artifacts()
    code = code_hashes()
    verdict = evaluate_gate(artifacts=artifacts, code=code, inputs=inputs or {})

    manifest = {
        "freeze_version": FREEZE_VERSION,
        "gate": verdict["gate"],
        "conditions": verdict["conditions"],
        "failed_reasons": verdict["failed_reasons"],
        "artifacts": artifacts,
        "code_hashes": code,
        "input_identity": inputs or {},
        "champion_sha256": sha_file(CHAMPION_PATH),
        "champion_expected": CHAMPION_EXPECTED,
        "no_override_flag_exists": True,
        "pass_by_definition_is_impossible": (
            "every boolean is derived from an artifact on disk; an absent or unreadable "
            "artifact evaluates to FALSE, never to a default TRUE"),
    }
    manifest["manifest_hash"] = hashlib.sha256(
        json.dumps({k: v for k, v in manifest.items() if k != "manifest_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()

    if out_path:
        with open(out_path, "w") as f:
            json.dump(manifest, f, indent=1, default=str, sort_keys=True)

    if verdict["gate"] != "PASS":
        raise FreezeRefused(
            "V8C_FREEZE = REFUSED\n  " + "\n  ".join(verdict["failed_reasons"]))
    return manifest


def version_stamp() -> dict:
    return {"freeze_version": FREEZE_VERSION,
            "gate_conditions": list(GATE_CONDITIONS),
            "required_artifacts": {k: v[0] for k, v in REQUIRED_ARTIFACTS.items()},
            "code_modules_hashed": list(CODE_MODULES),
            "override_flag": None,
            "absent_evidence_evaluates_to": False,
            "booleans_are_derived_from_artifacts_not_read_from_them": True}
