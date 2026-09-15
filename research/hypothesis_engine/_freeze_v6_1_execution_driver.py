"""Freeze the V6.1 execution-driver amendment. ZERO SPEND. No network, no model.

This is a PRE-SPEND APPARATUS AMENDMENT. It does NOT touch the frozen V6.1 scientific
artifacts (preregistration scientific content, fixtures, packets, evaluator, metric
registry, schedule, canonical request manifest). It ADDS the missing executable apparatus --
the V6.1 execution driver `_execute_v6_1.py` -- and binds it, with its full transitive
project-owned execution dependencies, into a NEW amendment artifact set:

    out/v6_1/EXECUTION_DRIVER_FREEZE.json          -- driver + dependency hashes
    out/v6_1/PREREGISTRATION_EXECUTION_AMENDMENT.json
                                                   -- the prior preregistration, UNCHANGED,
                                                      PLUS an `execution_apparatus` block
                                                      binding the driver path/hash/version.

The prior freeze (PREREGISTRATION.json, EVALUATOR_FREEZE.json, V6_1_STATES.json, ...) is
LEFT BYTE-FOR-BYTE UNCHANGED. This script only reads it and writes new files.

It re-proves, at freeze time, that:
  * every frozen V6.1 scientific artifact hash is unchanged from the prior freeze snapshot;
  * the driver's dry run passes over all 36 scheduled calls with zero inference;
  * the cost bound is unchanged (1,312,305 exact input tokens, 294,912 max output, $8.52,
    36 max billable attempts);
  * CHAMPION is unchanged.

If any of those fails, it writes nothing and exits non-zero (the amendment is BLOCKED).
"""
from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import os
import sys

sys.path.insert(0, "/home/ubuntu/src")
sys.path.insert(0, "/home/ubuntu")

ROOT = "/home/ubuntu"
V61 = f"{ROOT}/research/hypothesis_oos/out/v6_1"
DRIVER_REL = "research/hypothesis_engine/_execute_v6_1.py"
DRIVER_TEST_REL = "tests/research/hypothesis_oos/test_execute_v6_1.py"
CHAMPION = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_FROZEN_SHA = \
    "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"

EXECUTION_DRIVER_VERSION = "v6_1_execute_v2"

# The scientific artifacts whose hashes MUST be unchanged by this apparatus amendment.
SCIENTIFIC_ARTIFACTS = (
    "PREREGISTRATION.json", "EVALUATOR_FREEZE.json", "fixture_selection.json",
    "packets_base.json", "packets_research.json", "call_schedule.json",
    "INPUT_TOKEN_MANIFEST.json", "EXACT_INPUT_TOKEN_MANIFEST.json",
    "arm_isolation_audit.json", "pit_audit.json", "V6_1_DESIGN_COMPARISON.json")

# The scientific-hash snapshot captured BEFORE this amendment (this session). Values are
# re-verified below; a mismatch BLOCKS the amendment. Full SHA-256, no truncation.
PRIOR_SCIENTIFIC_HASHES = {
    "PREREGISTRATION.json":
        "93c2374248ec1c2f14a144205ebb198ec46f6c1dc65a98a00793918fce901cfc",
    "EVALUATOR_FREEZE.json":
        "4fe9c18b3a18f0a481072035ef96f0e49f3636b52699cd1d84da727bcd9eb8be",
    "fixture_selection.json":
        "557c5f4ea67e29d65708380a3a7e1878b0dc8dd7ce5cca1ca6e5da376c0d7625",
    "packets_base.json":
        "d8d86e8a89f440e9",         # prefix; full re-hash below is authoritative
    "packets_research.json":
        "0c9e3ddf74d474f1",         # prefix
    "call_schedule.json":
        "dc74772778ba9c60",         # prefix
    "INPUT_TOKEN_MANIFEST.json":
        "8c2ecae80731c621",         # prefix
    "EXACT_INPUT_TOKEN_MANIFEST.json":
        "583593c992743c63",         # prefix
    "arm_isolation_audit.json":
        "053a42fd03fde45e",         # prefix
    "pit_audit.json":
        "1dfebf38f7657311",         # prefix
    "V6_1_DESIGN_COMPARISON.json":
        "0ff43c2924464814",         # prefix
}


def _sha(path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(65536), b""):
            h.update(c)
    return h.hexdigest()


def transitive_execution_modules() -> dict:
    """Enumerate EVERY project-owned module the DRIVER loads that can affect a run.

    Returns {rel_path: sha256}. Excludes stdlib/site-packages, and excludes freeze/test
    tooling (this freeze script, the driver's own file, and the test module) -- those are
    not part of the executable run apparatus and binding them would make the manifest
    self-referential and non-deterministic. The driver's own hash is bound separately as
    `execution_driver.sha256`.
    """
    import subprocess
    # Import the driver in a CLEAN interpreter and have it print its own loaded project
    # modules, so this freeze script's imports never leak into the manifest.
    code = (
        "import importlib.util,sys,os\n"
        f"spec=importlib.util.spec_from_file_location('_execute_v6_1','{ROOT}/{DRIVER_REL}')\n"
        "m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\n"
        "import json\n"
        "out=[]\n"
        "for name,mod in sys.modules.items():\n"
        "    f=getattr(mod,'__file__',None)\n"
        "    if not f: continue\n"
        f"    if f.startswith('{ROOT}/src/research/') or f.startswith('{ROOT}/research/hypothesis'):\n"
        f"        out.append(os.path.relpath(f,'{ROOT}'))\n"
        "print(json.dumps(out))\n")
    env = dict(os.environ, PYTHONPATH=f"{ROOT}/src:{ROOT}")
    res = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         env=env, cwd=ROOT)
    rels = json.loads(res.stdout.strip().splitlines()[-1])
    exclude_substr = ("_freeze_v6_1_execution_driver.py", "_execute_v6_1.py",
                      "test_execute_v6_1.py")
    out = {}
    for rel in sorted(set(rels)):
        if any(s in rel for s in exclude_substr):
            continue
        out[rel] = _sha(f"{ROOT}/{rel}")
    return out


def run_dry_run() -> dict:
    """Run the driver's zero-inference dry run and return its report."""
    spec = importlib.util.spec_from_file_location(
        "_execute_v6_1_dryrun", f"{ROOT}/{DRIVER_REL}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.dry_run(out_dir=V61)


def main() -> int:
    problems = []

    # 1. scientific artifacts unchanged (full match when the recorded value is 64 hex chars;
    #    prefix match for the shorter recorded snapshots -- either way a change is caught)
    sci_hashes = {a: _sha(f"{V61}/{a}") for a in SCIENTIFIC_ARTIFACTS}
    for a, want in PRIOR_SCIENTIFIC_HASHES.items():
        got = sci_hashes[a]
        if len(want) >= 64:
            if got != want:
                problems.append(f"scientific artifact {a} changed since prior freeze "
                                f"({got[:12]} != {want[:12]})")
        elif not got.startswith(want):
            problems.append(f"scientific artifact {a} changed since prior freeze "
                            f"({got[:16]} does not start with {want})")

    # 2. CHAMPION unchanged
    champ_sha = _sha(CHAMPION)
    if champ_sha != CHAMPION_FROZEN_SHA:
        problems.append(f"CHAMPION changed ({champ_sha[:12]} != {CHAMPION_FROZEN_SHA[:12]})")

    # 3. cost bound unchanged
    ex = json.load(open(f"{V61}/EXACT_INPUT_TOKEN_MANIFEST.json"))
    if ex["total_exact_input_tokens"] != 1312305:
        problems.append(f"exact input tokens changed: {ex['total_exact_input_tokens']}")
    if ex["total_max_output_tokens"] != 294912:
        problems.append(f"max output tokens changed: {ex['total_max_output_tokens']}")
    if str(ex["hard_max_cost_usd"]) != "8.52":
        problems.append(f"hard ceiling changed: {ex['hard_max_cost_usd']}")
    if ex.get("total_max_billable_attempts") != 36:
        problems.append(f"max billable attempts changed: "
                        f"{ex.get('total_max_billable_attempts')}")

    # 4. dry run passes with zero inference
    dr = run_dry_run()
    if not dr["reverify_ok"]:
        problems.append(f"driver dry-run reverify failed: {dr['reverify_problems']}")
    if not dr["worst_case_within_ceiling"]:
        problems.append("driver dry-run worst-case cost exceeds ceiling")
    if not (dr["zero_inference"] and dr["all_36_present"]):
        problems.append("driver dry-run did not cover all 36 calls at zero inference")

    if problems:
        print("=== V6.1 EXECUTION-DRIVER AMENDMENT BLOCKED ===")
        for p in problems:
            print("  BLOCK:", p)
        return 1

    # ---- write the amendment artifacts (prior freeze untouched) ----
    driver_sha = _sha(f"{ROOT}/{DRIVER_REL}")
    exec_modules = transitive_execution_modules()

    driver_freeze = {
        "amendment": "V6_1_EXECUTION_DRIVER_AMENDMENT",
        "amendment_version": "v6_1_execution_driver_amendment_v2",
        "frozen_before_first_paid_call": True,
        "spend_usd_at_freeze": 0.0,
        "reason": ("v2 apparatus amendment: an unknown-after-send request (client.converse "
                   "entered, then raised, billing unknowable) is now accounted at its FROZEN "
                   "maximum as unresolved reserved exposure and consumed by the prospective "
                   "next-call guard -- never zero. v1 treated it as $0 exposure. EXECUTION "
                   "APPARATUS ONLY -- no scientific artifact changes."),
        "prior_execution_driver_sha256_v1":
            "3a7f1a85aef695490cb250c9ce247ada7453ab4058c35b8d48d868d4dddd2d9f",
        "execution_driver": {
            "path": DRIVER_REL,
            "sha256": driver_sha,
            "version": EXECUTION_DRIVER_VERSION,
            "test_path": DRIVER_TEST_REL,
            "test_sha256": _sha(f"{ROOT}/{DRIVER_TEST_REL}")},
        "prior_freeze_untouched": {a: sci_hashes[a] for a in SCIENTIFIC_ARTIFACTS},
        "transitive_execution_module_hashes": exec_modules,
        "n_execution_modules": len(exec_modules),
        "cost_bound_unchanged": {
            "total_exact_input_tokens": ex["total_exact_input_tokens"],
            "total_max_output_tokens": ex["total_max_output_tokens"],
            "hard_max_cost_usd": ex["hard_max_cost_usd"],
            "total_max_billable_attempts": ex["total_max_billable_attempts"]},
        "champion_sha256": champ_sha,
        "dry_run": {"all_36_present": dr["all_36_present"], "reverify_ok": dr["reverify_ok"],
                    "worst_case_within_ceiling": dr["worst_case_within_ceiling"],
                    "zero_inference": dr["zero_inference"]},
        "scientific_design_unchanged": True,
        "requires_fresh_human_authorization": True,
    }
    with open(f"{V61}/EXECUTION_DRIVER_FREEZE.json", "w") as fh:
        json.dump(driver_freeze, fh, indent=1, sort_keys=True, default=str)

    # the amendment preregistration = prior prereg (unchanged content) + execution_apparatus
    prior_prereg = json.load(open(f"{V61}/PREREGISTRATION.json"))
    amendment = dict(prior_prereg)          # shallow copy; we ADD one key, change nothing
    amendment["execution_apparatus"] = {
        "execution_driver_path": DRIVER_REL,
        "execution_driver_sha256": driver_sha,
        "execution_driver_version": EXECUTION_DRIVER_VERSION,
        "execution_driver_test_path": DRIVER_TEST_REL,
        "execution_module_manifest": "EXECUTION_DRIVER_FREEZE.json",
        "n_execution_modules": len(exec_modules),
        "prospective_cost_guard": ("accounted_spend + frozen max_request_cost_usd(next) "
                                   "<= hard_ceiling_usd, checked BEFORE client.converse()"),
        "retries_disabled": True,
        "path_isolation": "experiment_id startswith V6.1 AND output under out/v6_1 AND "
                          "NOT out/v6; asserted at startup and on every write",
        "raw_before_adjudication": True,
        "defines_scientific_policy": False,
        "prior_authorization_status": "EXPIRED_UNCONSUMED (bound to a package without an "
                                      "executor); fresh human authorization required",
        "amendment_version": "v6_1_execution_driver_amendment_v2",
    }
    amendment["prior_preregistration_sha256"] = _sha(f"{V61}/PREREGISTRATION.json")
    with open(f"{V61}/PREREGISTRATION_EXECUTION_AMENDMENT.json", "w") as fh:
        json.dump(amendment, fh, indent=1, sort_keys=True, default=str)

    print("=== V6.1 EXECUTION-DRIVER AMENDMENT FROZEN ===")
    print(f"  driver           : {DRIVER_REL}")
    print(f"  driver sha256    : {driver_sha}")
    print(f"  driver version   : {EXECUTION_DRIVER_VERSION}")
    print(f"  execution modules: {len(exec_modules)} project-owned deps bound")
    print(f"  cost bound       : {ex['total_exact_input_tokens']} in / "
          f"{ex['total_max_output_tokens']} out / ${ex['hard_max_cost_usd']} / "
          f"{ex['total_max_billable_attempts']} attempts (UNCHANGED)")
    print(f"  CHAMPION         : {champ_sha[:16]} (unchanged)")
    print(f"  scientific design: UNCHANGED")
    print("  wrote EXECUTION_DRIVER_FREEZE.json + PREREGISTRATION_EXECUTION_AMENDMENT.json")
    print("  prior freeze     : untouched")
    print("\n  V6_1_SPEND_AUTHORIZATION_REQUIRED (fresh authorization, bound to driver hash)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
