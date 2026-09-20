"""Freeze the LLM_MATCHUP_V3_SONNET46 generation — the Sonnet 4.6 arm's scientific record.

Writes ONLY research/llm_matchup/out/FREEZE_LLM_MATCHUP_V3_SONNET46.json.

NEVER touches, and must never be made to touch:
  * research/llm_matchup/out/FREEZE_LLM_MATCHUP_V2.json          (the V2 generation's freeze)
  * research/llm_matchup/out/V3_CHECKPOINT.md                    (the 4.5 arm's checkpoint)
  * research/llm_matchup/out/hardening_v3/**                     (the 4.5 arm's artifacts)
A separate freeze path is asserted at runtime, so a rename cannot silently collide.

Records, per the mandate:
  * the EXACT resolved Bedrock model identity actually observed in the live calls (not merely
    the requested id), plus the requested profile id, ARN, region and inference config;
  * every shared content hash (prompt / output schema / ontology / neutralization module /
    formation structure / sampling module) so the single-variable claim is machine-checkable;
  * the inherited fixture manifest hash, proving the same 20 fixtures as the 4.5 arm;
  * the explicit diff vs the 4.5 arm (must be model id + generation id only);
  * content hashes of every 4.6 artifact produced;
  * the git commit/branch and working-tree state at freeze time;
  * an honest completeness block: which parts of the validation sequence ran, which did not,
    and why. A freeze must never imply more evidence than was collected.

Re-running without --force refuses to overwrite and instead emits a drift re-verification side
file, exactly like freeze_v2.
"""
from __future__ import annotations
import glob
import hashlib
import json
import os
import subprocess
import sys
import time

from src.research.llm_matchup.hardening import controls_v3_sonnet46 as C46
from src.research.llm_matchup.hardening import golden_manifest as GM
from src.research.llm_matchup.hardening import golden_v3_sonnet46 as G46
from src.research.llm_matchup.hardening import versions_v3 as V45
from src.research.llm_matchup.hardening import versions_v3_sonnet46 as V46

ROOT = "/home/ubuntu"
OUT = os.path.join(ROOT, "research/llm_matchup/out")

#: The scientific sources this freeze hashes, resolved from the EXECUTING checkout rather
#: than from `ROOT`. `SRC_DIR` was `<ROOT>/src/research/llm_matchup/hardening`, so a freeze
#: built or verified from any other checkout hashed the DEPLOYED tree's modules while
#: executing its own -- the same defect repaired in `golden_manifest` (PR #20), and it is
#: repaired the same way here rather than with a second, inconsistent mechanism.
#: `ROOT`, `OUT` and `PROTECTED` are artifact/output roots and are deliberately unchanged.
SRC_DIR = os.path.join(GM.REPO_ROOT, "src", "research", "llm_matchup", "hardening")
FREEZE_PATH = os.path.join(OUT, "FREEZE_LLM_MATCHUP_V3_SONNET46.json")

# Paths this module must NEVER write. (V3_CHECKPOINT.md lives in research/llm_matchup/, NOT
# in research/llm_matchup/out/ -- an earlier version of this list had it in the wrong place,
# which meant the guard silently protected a non-existent path.)
PROTECTED = (
    os.path.join(OUT, "FREEZE_LLM_MATCHUP_V2.json"),
    os.path.join(ROOT, "research/llm_matchup/V3_CHECKPOINT.md"),
    os.path.join(OUT, "hardening_v3"),
)

# The 4.6 instrument's source modules. Note versions_v3.py / prompt_v4.py / schema_v3.py /
# validator_v3.py / neutralize_v3.py are SHARED with the 4.5 arm by design -- hashing them here
# records that they were unchanged, it does not claim ownership of them.
MODULES = [
    "versions_v3.py", "versions_v3_sonnet46.py", "prompt_v4.py", "schema_v3.py",
    "validator_v3.py", "adapter_v4.py", "neutralize_v3.py", "formation_structure.py",
    "repeatability.py", "ablation_noise.py", "sampling.py", "golden_manifest.py",
    "golden_v3_sonnet46.py", "controls_v3_sonnet46.py", "audit_prespend.py",
    "audit_request.py", "counter_golden.py", "eligibility.py",
    "eligibility_v3_sonnet46.py",
    # --- added by the core-binding repair -------------------------------------------
    # `controls_v3_sonnet46.py` and `eligibility_v3_sonnet46.py` above are THIN WRAPPERS:
    # they import `controls_v3_core` / `eligibility_v3_core` and delegate the scientific
    # decisions to them. Hashing only the wrappers meant the control definitions and the
    # eligibility rules could change with the freeze still reporting the same instrument.
    "controls_v3_core.py", "eligibility_v3_core.py",
    # `controls_v3_core` records `RG.classify_bedrock_error(...)` into its control results
    # (controls_v3_core.py:115 `err_class`, :135 `error_class`), so that classification is
    # an input to control outcomes and must be bound too.
    "resume_golden_v3.py",
]

#: Every entry of `MODULES` is required: the freeze may not be built from, nor verified
#: against, a partial source set. Named separately so the contract is explicit at the call
#: sites below rather than implied by a loop.
REQUIRED_MODULES = tuple(MODULES)

#: The cores whose absence distinguishes a pre-repair freeze from one built under the
#: repaired contract. A freeze lacking these is historical evidence, not a complete binding.
REQUIRED_CORE_MODULES = (
    "controls_v3_core.py", "eligibility_v3_core.py", "resume_golden_v3.py",
)

#: Bumped because the required source set grew. A freeze written before this repair cannot
#: satisfy the new contract and must not be silently upgraded to look as though it does.
FREEZE_CONTRACT_VERSION = "v3_sonnet46_freeze_contract_v2_core_bound"

#: Contracts this verifier is willing to certify. Matching hashes are NOT evidence of
#: contract compatibility: a manifest can carry every current hash and still describe a
#: different required set, which is exactly how a pre-repair freeze looks once the cores are
#: required. An unlisted or absent contract is refused rather than inferred.
SUPPORTED_CONTRACTS = frozenset({FREEZE_CONTRACT_VERSION})

#: Covered module basename -> the dotted name it is imported under. Used to find the module
#: OBJECT actually in play, so a foreign copy loaded under the real name is detected.
_COVERED_DOTTED = {
    mod: f"src.research.llm_matchup.hardening.{mod[:-3]}" for mod in REQUIRED_MODULES
}

#: The scientific wrappers and the attribute each binds its core to. `sys.modules` alone is
#: not enough: a wrapper keeps its own reference, so replacing `sys.modules[...]` after the
#: wrapper imported it would leave the foreign object in use but invisible to a
#: `sys.modules` scan. Both are checked; neither subsumes the other.
WRAPPER_BOUND_CORES = (
    ("controls_v3_sonnet46", "CORE", "controls_v3_core.py"),
    ("eligibility_v3_sonnet46", "ECORE", "eligibility_v3_core.py"),
)

#: `atomic_io.py` is a direct dependency of both cores and is deliberately NOT required: it
#: is an atomic-write utility and encodes no scientific decision. Recorded here so the
#: exclusion is a stated judgement rather than an oversight.
EXCLUDED_WITH_REASON = {
    "atomic_io.py": "write utility; no scientific decision, no effect on any result value",
}


class FreezeBindingError(RuntimeError):
    """A required scientific source binding is missing, unreadable, foreign or stale.

    Raised instead of returning a report, so an incomplete or drifted binding cannot be
    mistaken for a verified one by a caller that only checks a return value.
    """


class FreezeGenerationMismatch(FreezeBindingError):
    """The recomputed generation identity differs from the existing freeze's.

    A distinct type so a caller -- and a test -- can tell "the bindings are wrong" from
    "the bindings are fine but this is a different instrument".
    """


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _git(*args):
    try:
        return subprocess.check_output(["git", *args], cwd=ROOT,
                                       stderr=subprocess.DEVNULL).decode().strip()
    except Exception as e:
        return f"<git-error: {e}>"


def _read_json(path):
    if not os.path.exists(path):
        return None
    try:
        return json.load(open(path))
    except Exception:
        return None


def _observed_model_identities() -> dict:
    """The model identity ACTUALLY observed in live 4.6 responses, from the ledger. This is the
    authoritative record: the requested id is an intention, the resolved id is an observation."""
    ledger = G46.load_ledger()
    requested, resolved = set(), set()
    for e in (ledger.get("fixtures") or {}).values():
        for a in e.get("attempts", []) or []:
            if a.get("model_id"):
                requested.add(a["model_id"])
            if a.get("resolved_model_id"):
                resolved.add(a["resolved_model_id"])
    return {
        "requested_model_ids_observed": sorted(requested),
        "resolved_model_ids_observed": sorted(resolved),
        "single_model_identity_confirmed": len(resolved) == 1,
    }


def _loaded_covered_objects() -> dict:
    """Covered basename -> the module OBJECT in play, for those that are loaded.

    Two sources, because neither covers the other:

    * `sys.modules[dotted]` -- the general case. Any covered module loaded from somewhere
      else appears here under its real name.
    * the wrapper's own bound attribute (`controls_v3_sonnet46.CORE`) -- the narrow case
      where `sys.modules` was reassigned *after* the wrapper imported its core, leaving the
      foreign object in use but invisible to a `sys.modules` scan. This is the shape that
      defeated the previous verifier.

    A covered module that is not loaded contributes nothing: there is no origin to check.
    """
    found = {}
    for mod, dotted in _COVERED_DOTTED.items():
        obj = sys.modules.get(dotted)
        if obj is not None:
            found[mod] = obj
    for wrapper, attr, core in WRAPPER_BOUND_CORES:
        wrapper_obj = sys.modules.get(f"src.research.llm_matchup.hardening.{wrapper}")
        if wrapper_obj is None:
            continue
        bound = getattr(wrapper_obj, attr, None)
        if bound is not None:
            # The wrapper's reference wins: it is the object the science actually runs on.
            found[core] = bound
    return found


def loaded_origin_violations() -> list:
    """Covered modules that are loaded from outside this checkout, as report rows.

    Delegates the comparison to `golden_manifest._verified_source_path`, the mechanism
    accepted in the preceding repair, rather than adding a second one with its own rules.
    It is underscore-private but deliberately shared: both modules live in `hardening/` and
    a divergent copy here is exactly what this repair is meant to avoid.
    """
    violations = []
    for mod, obj in sorted(_loaded_covered_objects().items()):
        try:
            GM._verified_source_path(obj, mod)
        except GM.SourceBindingError as e:
            violations.append({
                "module": mod,
                "loaded_from": os.path.realpath(getattr(obj, "__file__", "") or ""),
                "expected": os.path.join(SRC_DIR, mod),
                "detail": str(e),
            })
    return violations


def current_module_hashes(check_origins: bool = True) -> dict:
    """Hash every REQUIRED module from the executing checkout, or fail.

    The original implementation was `if os.path.exists(p): module_hashes[mod] = ...`, so a
    required source that was renamed, moved or deleted simply vanished from the manifest and
    the freeze still reported success over a smaller set. Absence is an error.

    Hashing the file at the expected path is not by itself enough: a foreign copy of a core
    can be loaded under the real dotted name while this function happily hashes the local
    file, which is how a reviewer obtained an `OK` verdict over a mixed-checkout process.
    Loaded origins are therefore validated too.

    `check_origins=False` exists only so `verify_freeze` can REPORT a foreign origin rather
    than raise on it; the check itself is the same code either way.
    """
    if check_origins:
        violations = loaded_origin_violations()
        if violations:
            raise FreezeBindingError(
                "covered module(s) loaded from outside this checkout: "
                + "; ".join(f"{v['module']} <- {v['loaded_from']}" for v in violations)
                + ". Refusing to hash local files as though they described the loaded code.")
    hashes, missing = {}, []
    for mod in REQUIRED_MODULES:
        path = os.path.join(SRC_DIR, mod)
        if not os.path.isfile(path):
            missing.append(mod)
            continue
        hashes[mod] = _sha256_file(path)
    if missing:
        raise FreezeBindingError(
            f"required source(s) absent from {SRC_DIR!r}: {sorted(missing)}. A freeze "
            "cannot be built from a partial source set.")
    return hashes


def verify_freeze(freeze_manifest: dict) -> dict:
    """Check a freeze's declared contract and source bindings against THIS checkout.

    Deliberately independent of `build_manifest()`, which reads eight result artifacts under
    `OUT`. Binding integrity is a question about a contract and some source files, so
    verifying it must not require a golden batch, a controls run or any other artifact.

    FAILURE ORDER -- first match wins, because each stage decides how the next is read:

        1. MISSING_CONTRACT      no `freeze_contract_version`
        2. UNSUPPORTED_CONTRACT  a contract this verifier does not certify
        3. INCOMPLETE_BINDING    a required hash is absent from the freeze
        4. FOREIGN_ORIGIN        a covered module is loaded from another checkout
        5. BINDING_MISMATCH      a recorded hash no longer matches this checkout
        6. OK

    Every diagnostic field is populated on EVERY return path, including the contract
    failures. A historical freeze must stay *readable* -- naming what it is missing is the
    point of inspecting it -- so a contract refusal never blanks the binding detail.

    Returns a report and never raises for a failed verification; `verify_freeze_or_raise`
    is the enforcing wrapper. Matching hashes are never read as contract compatibility.
    """
    freeze_manifest = freeze_manifest or {}
    declared = freeze_manifest.get("freeze_contract_version")
    recorded = freeze_manifest.get("module_hashes")
    recorded = recorded if isinstance(recorded, dict) else {}

    violations = loaded_origin_violations()
    current = current_module_hashes(check_origins=False)

    missing = sorted(m for m in REQUIRED_MODULES if m not in recorded)
    mismatched = sorted(m for m in REQUIRED_MODULES
                        if m in recorded and recorded[m] != current[m])

    if declared is None:
        status = "MISSING_CONTRACT"
    elif declared not in SUPPORTED_CONTRACTS:
        status = "UNSUPPORTED_CONTRACT"
    elif missing:
        status = "INCOMPLETE_BINDING"
    elif violations:
        status = "FOREIGN_ORIGIN"
    elif mismatched:
        status = "BINDING_MISMATCH"
    else:
        status = "OK"

    return {
        "ok": status == "OK",
        "status": status,
        "contract": FREEZE_CONTRACT_VERSION,
        "supported_contracts": sorted(SUPPORTED_CONTRACTS),
        "freeze_contract": declared,
        "missing_bindings": missing,
        # Called out separately: these are what a pre-repair freeze is missing, and the
        # reason it cannot be certified complete even though it remains inspectable.
        "missing_required_cores": sorted(m for m in REQUIRED_CORE_MODULES if m in missing),
        "foreign_origins": violations,
        "mismatched": mismatched,
        "source_dir": SRC_DIR,
    }


def verify_freeze_or_raise(freeze_manifest: dict) -> dict:
    """`verify_freeze`, but any non-OK verdict is an error rather than a return value.

    The message names the actual reason -- contract, missing binding, foreign origin or
    stale hash -- so a refusal is never reported as a generic failure.
    """
    report = verify_freeze(freeze_manifest)
    if not report["ok"]:
        raise FreezeBindingError(
            f"freeze source binding not verified ({report['status']}): "
            f"declared_contract={report['freeze_contract']!r} "
            f"supported={report['supported_contracts']} "
            f"missing={report['missing_bindings']} "
            f"foreign_origins={[v['module'] for v in report['foreign_origins']]} "
            f"mismatched={report['mismatched']}. "
            "This freeze does not describe the sources in the executing checkout.")
    return report


def build_manifest() -> dict:
    m46 = G46.build_or_load_manifest()
    frozen45 = GM.load_manifest(G46.SONNET45_MANIFEST_PATH) or {}
    summary = _read_json(G46.SUMMARY_PATH) or {}
    controls = _read_json(C46.CONTROLS_PATH) or {}
    repeat = _read_json(C46.REPEAT_PATH) or {}
    counter = _read_json(C46.COUNTER_PATH) or {}
    prespend = _read_json(G46.PRESPEND_AUDIT_PATH) or {}
    elig = _read_json(os.path.join(G46.OUT, "golden_v3_sonnet46_eligibility.json")) or {}

    module_hashes = current_module_hashes()

    artifact_hashes = {}
    for p in sorted(glob.glob(os.path.join(G46.OUT, "*"))):
        if os.path.isfile(p):
            artifact_hashes[os.path.basename(p)] = _sha256_file(p)

    version_payload = {
        # Part of the hashed identity on purpose: the required source set is what this
        # freeze claims to cover, so a freeze built under a different contract is a
        # different claim and must not collide with this one.
        "freeze_contract_version": FREEZE_CONTRACT_VERSION,
        "version_stamp": V46.version_stamp(),
        "content_hashes": G46.content_hashes(),
        "bedrock": {
            "requested_model_id": V46.DEFAULT_BEDROCK_MODEL_ID,
            "inference_profile_arn": V46.BEDROCK_INFERENCE_PROFILE_ARN,
            "base_model_id": V46.BEDROCK_BASE_MODEL_ID,
            "region": V46.DEFAULT_BEDROCK_REGION,
            "inference_config": V46.INFERENCE_CONFIG,
            "model_id_is_date_pinned": V46.MODEL_ID_IS_DATE_PINNED,
        },
        "fixture_manifest_hash": m46["fixture_manifest_hash"],
        "module_hashes": module_hashes,
    }
    generation_hash = hashlib.sha256(
        json.dumps(version_payload, sort_keys=True, default=str).encode()).hexdigest()

    # --- honest completeness accounting ------------------------------------------------
    completeness = {
        "prespend_audit": bool(prespend) and prespend.get("all_clean") is True,
        "golden_batch": bool(summary),
        "identity_controls": bool(controls),
        "repeatability": bool(repeat),
        "behavior_sensitivity": bool(controls.get("controls", {}).get(
            "D_behavior_sensitivity_formation_ablation")),
        "counter_evidence": bool(counter),
        "mechanism_eligibility": bool(elig),
        "surrogate_analysis": False,
        "phase_c": False,
    }

    manifest = {
        "freeze": "FREEZE_LLM_MATCHUP_V3_SONNET46",
        "generation_id": V46.GENERATION_ID,
        "arm": "SONNET_4_6",
        "parallel_arm": {
            "generation_id": V45.GENERATION_ID,
            "status": "FROZEN_AND_UNTOUCHED_BY_THIS_FREEZE",
            "note": ("The Sonnet 4.5 arm is a SEPARATE scientific generation with its own "
                     "manifest, ledger, cache and artifacts. This freeze neither reads nor "
                     "writes its results, other than inheriting its fixture id list."),
            "inherited_fixture_manifest_hash": frozen45.get("fixture_manifest_hash"),
        },
        **version_payload,
        "generation_hash": generation_hash,
        "model_identity_observed": _observed_model_identities(),
        "single_variable_proof": {
            "diff_vs_sonnet45": V46.diff_vs_v45(),
            "fingerprint_diff_vs_frozen_45_manifest": G46.manifest_vs_45_fingerprint_diff(),
            "fixture_selection_identical_to_45": (
                m46["fixture_manifest_hash"] == frozen45.get("fixture_manifest_hash")),
            "fixture_ids_identical_to_45": (
                m46.get("fixture_ids") == frozen45.get("fixture_ids")),
        },
        "results": {
            "golden_counts": summary.get("counts"),
            "golden_acceptance": summary.get("acceptance"),
            "tokens": summary.get("tokens"),
            "latency_s": summary.get("latency_s"),
            "cost_usd_estimate": summary.get("cost_usd_estimate"),
            "state_metrics_distribution": summary.get("state_metrics_distribution"),
            "rates": summary.get("rates"),
            "identity_gate": controls.get("identity_gate"),
            "controls_headline": {
                k: {kk: vv for kk, vv in v.items() if kk != "rows"}
                for k, v in (controls.get("controls") or {}).items()
            },
            "interpretation": controls.get("interpretation"),
            "repeatability_pooled": repeat.get("pooled"),
            "self_noise_pooled": repeat.get("self_noise_pooled"),
            "counter_evidence": {k: v for k, v in counter.items()
                                 if k not in ("rows", "call_log")},
            "eligibility": {k: v for k, v in elig.items() if k != "rows"},
        },
        "prespend_audit": {k: v for k, v in prespend.items() if k != "reports"},
        "artifact_hashes": artifact_hashes,
        "completeness": completeness,
        "phase_c_status": {
            "fed_into_phase_c": False,
            "champion_modified": False,
            "contextual_challenger_modified": False,
            "note": ("Mandate SS28: Phase C was deliberately NOT touched. Nothing here has "
                     "been promoted, and no predictive evaluation was performed. Predictive "
                     "value remains an open Phase-C question."),
        },
        "git": {
            "branch": _git("branch", "--show-current"),
            "head": _git("rev-parse", "HEAD"),
            "dirty_paths_llm_matchup": _git("status", "--short", "--",
                                            "src/research/llm_matchup", "research/llm_matchup"),
        },
        "frozen_unix": int(time.time()),
    }
    manifest["freeze_hash"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, default=str).encode()).hexdigest()
    return manifest


def freeze(force: bool = False) -> dict:
    # Hard guard: this module writes exactly one path, and never a protected one.
    assert FREEZE_PATH not in PROTECTED
    for p in PROTECTED:
        assert os.path.abspath(FREEZE_PATH) != os.path.abspath(p), f"refusing to write {p}"
        assert not os.path.abspath(FREEZE_PATH).startswith(os.path.abspath(p) + os.sep)

    os.makedirs(OUT, exist_ok=True)
    manifest = build_manifest()
    if os.path.exists(FREEZE_PATH) and not force:
        existing = _read_json(FREEZE_PATH) or {}
        drift = existing.get("generation_hash") != manifest["generation_hash"]
        binding = verify_freeze(existing)
        side = os.path.join(
            OUT, f"FREEZE_LLM_MATCHUP_V3_SONNET46.reverify.{manifest['frozen_unix']}.json")
        json.dump({"existing_generation_hash": existing.get("generation_hash"),
                   "recomputed_generation_hash": manifest["generation_hash"],
                   "instrument_drift_detected": drift,
                   "source_binding": binding, "recomputed": manifest},
                  open(side, "w"), indent=2, default=str)
        print(json.dumps({"action": "reverify", "existing": FREEZE_PATH,
                          "instrument_drift_detected": drift,
                          "source_binding_status": binding["status"], "side_file": side},
                         indent=2))
        # Previously this returned `existing` here, drift or not: the drift flag was written
        # to a side file and to stdout and then discarded, so re-running the freeze over
        # changed sources handed back the stale manifest as though it still applied. The
        # side file is written FIRST on every refusal path -- the diagnostic evidence
        # survives regardless -- and only then is an invalid state raised.
        verify_freeze_or_raise(existing)

        # Source bindings can be perfectly valid while the instrument is still a different
        # one: `generation_hash` is taken over `version_payload`, which also covers the
        # contract, the version stamp, `content_hashes`, the Bedrock configuration and the
        # fixture manifest hash. A reviewer reproduced current hashes + supported contract +
        # a changed `generation_hash` being returned as accepted. No field is excluded from
        # this comparison: inventing an exclusion to make it pass would be manufacturing the
        # very assurance the freeze exists to provide.
        if drift:
            raise FreezeGenerationMismatch(
                "existing freeze describes a different generation identity: "
                f"existing={existing.get('generation_hash')!r} "
                f"recomputed={manifest['generation_hash']!r}. Source bindings verified, so "
                "this is an instrument/configuration change, not a stale source hash. The "
                f"existing freeze at {FREEZE_PATH} is unchanged and the recomputed manifest "
                f"is preserved at {side} for inspection.")
        return existing
    json.dump(manifest, open(FREEZE_PATH, "w"), indent=2, default=str)
    print(json.dumps({"action": "frozen", "path": FREEZE_PATH,
                      "generation_id": manifest["generation_id"],
                      "generation_hash": manifest["generation_hash"],
                      "freeze_hash": manifest["freeze_hash"],
                      "resolved_model_ids": manifest["model_identity_observed"][
                          "resolved_model_ids_observed"],
                      "completeness": manifest["completeness"]}, indent=2))
    return manifest


if __name__ == "__main__":
    freeze(force="--force" in sys.argv)
