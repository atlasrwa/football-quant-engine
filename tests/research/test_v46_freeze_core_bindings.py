"""The 4.6 freeze must bind the scientific cores its thin wrappers delegate to.

`freeze_v3_sonnet46.MODULES` hashed `controls_v3_sonnet46.py` and `eligibility_v3_sonnet46.py`
-- both thin wrappers that import `controls_v3_core` / `eligibility_v3_core` and delegate every
scientific decision to them. The cores were not hashed, so the control definitions and the
eligibility rules could change while the freeze reported the same instrument.

Two further defects in the same path: a required source that went missing was silently dropped
from the manifest (`if os.path.exists(p)`), and `SRC_DIR` was `<"/home/ubuntu">/src/...`, so any
other checkout hashed the deployed tree while executing its own.

OFFLINE. No corpus, no Bedrock call, no artifact assembly: binding integrity is a question about
source files, so `verify_freeze()` is deliberately independent of `build_manifest()`. Each
assertion runs in a subprocess with `cwd` set to the checkout under test and `PYTHONPATH` unset
-- `sys.modules` is process-global and the venv's editable finder maps `src` -> `/home/ubuntu/src`,
losing only to `cwd`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import textwrap

import pytest

CHECKOUT = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir, os.pardir))
HARDENING_REL = os.path.join("src", "research", "llm_matchup", "hardening")
STRUCTURE_REL = os.path.join("research", "llm_matchup", "FORMATION_STRUCTURE_V1.json")


def _run(script: str, *, cwd: str) -> dict:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, "-c", textwrap.dedent(script)],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    assert proc.returncode == 0, (
        f"subprocess failed ({proc.returncode})\n--- stdout ---\n{proc.stdout}"
        f"\n--- stderr ---\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _copy_checkout(dest: str) -> str:
    os.makedirs(dest, exist_ok=True)
    for rel in ("src", "scripts"):
        shutil.copytree(os.path.join(CHECKOUT, rel), os.path.join(dest, rel),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    os.makedirs(os.path.join(dest, os.path.dirname(STRUCTURE_REL)), exist_ok=True)
    shutil.copy2(os.path.join(CHECKOUT, STRUCTURE_REL), os.path.join(dest, STRUCTURE_REL))
    return os.path.realpath(dest)


@pytest.fixture(scope="module")
def checkout(tmp_path_factory) -> str:
    return _copy_checkout(str(tmp_path_factory.mktemp("v46_checkout")))


#: Build a freeze dict from the checkout's own sources, then verify it. `mutate` runs before
#: verification so a test can change a source file *after* the freeze recorded it.
SELF_FREEZE_THEN_VERIFY = """
    import json
    from src.research.llm_matchup.hardening import freeze_v3_sonnet46 as FZ
    frozen = {"module_hashes": dict(FZ.current_module_hashes()),
              "freeze_contract_version": FZ.FREEZE_CONTRACT_VERSION}
    %s
    print(json.dumps({"freeze": frozen, "report": FZ.verify_freeze(frozen),
                      "required": list(FZ.REQUIRED_MODULES),
                      "cores": list(FZ.REQUIRED_CORE_MODULES),
                      "src_dir": FZ.SRC_DIR}))
"""


# ------------------------------------------------------------------- 1. complete baseline

def test_both_cores_are_required_and_their_hashes_match_the_source_files(checkout):
    """Criterion 1: the cores are in the required set and bound to this checkout's files."""
    import hashlib
    result = _run(SELF_FREEZE_THEN_VERIFY % "", cwd=checkout)

    assert "controls_v3_core.py" in result["required"]
    assert "eligibility_v3_core.py" in result["required"]
    assert result["report"]["status"] == "OK" and result["report"]["ok"] is True

    for mod in ("controls_v3_core.py", "eligibility_v3_core.py"):
        path = os.path.join(checkout, HARDENING_REL, mod)
        expected = hashlib.sha256(open(path, "rb").read()).hexdigest()
        assert result["freeze"]["module_hashes"][mod] == expected, mod

    assert result["src_dir"] == os.path.join(checkout, HARDENING_REL)


# -------------------------------------------------------------------- 2 & 3. core mutation

@pytest.mark.parametrize("core", ["controls_v3_core.py", "eligibility_v3_core.py"])
def test_changing_only_one_core_rejects_the_existing_freeze(checkout, tmp_path, core):
    """Criteria 2 and 3: a change confined to one core invalidates the prior binding."""
    tree = _copy_checkout(str(tmp_path / f"mutate_{core}"))
    mutate = (
        'open(%r, "a").write("\\n# SCIENTIFIC_CHANGE_MARKER_7b1e\\n")'
        % os.path.join(tree, HARDENING_REL, core))

    result = _run(SELF_FREEZE_THEN_VERIFY % mutate, cwd=tree)
    report = result["report"]

    assert report["ok"] is False
    assert report["status"] == "BINDING_MISMATCH"
    assert report["mismatched"] == [core], (
        f"only {core} changed, so it must be the only mismatch")


# ------------------------------------------------------------------------ 4. missing source

def test_a_missing_required_source_fails_explicitly(checkout, tmp_path):
    """Criterion 4: absence is an error, not a quietly smaller manifest.

    The previous construction was `if os.path.exists(p): module_hashes[mod] = ...`, so this
    scenario produced a freeze that looked complete over a shorter list.
    """
    tree = _copy_checkout(str(tmp_path / "missing_source"))

    # Removed AFTER import, at hash time. Deleting it beforehand would fail earlier with an
    # ImportError -- also explicit, but a different mechanism; this targets the binding check
    # itself, which is where the old `if os.path.exists(p)` quietly dropped the entry.
    result = _run("""
        import json, os
        from src.research.llm_matchup.hardening import freeze_v3_sonnet46 as FZ
        os.remove(os.path.join(FZ.SRC_DIR, "controls_v3_core.py"))
        try:
            h = FZ.current_module_hashes()
            print(json.dumps({"outcome": "SILENTLY_OMITTED",
                              "has_core": "controls_v3_core.py" in h, "n": len(h)}))
        except FZ.FreezeBindingError as e:
            print(json.dumps({"outcome": "RAISED", "error": str(e)}))
    """, cwd=tree)

    assert result["outcome"] == "RAISED", result
    assert "controls_v3_core.py" in result["error"]


# --------------------------------------------------------------- 5. missing manifest binding

def test_removing_a_required_hash_from_the_freeze_fails_verification(checkout):
    """Criterion 5: a freeze that omits a required binding is not verified."""
    for core in ("controls_v3_core.py", "eligibility_v3_core.py"):
        result = _run("""
            import json
            from src.research.llm_matchup.hardening import freeze_v3_sonnet46 as FZ
            frozen = {"module_hashes": dict(FZ.current_module_hashes()),
                      "freeze_contract_version": FZ.FREEZE_CONTRACT_VERSION}
            frozen["module_hashes"].pop(%r)
            print(json.dumps(FZ.verify_freeze(frozen)))
        """ % core, cwd=checkout)
        assert result["ok"] is False
        assert result["status"] == "INCOMPLETE_BINDING"
        assert result["missing_bindings"] == [core]


# ------------------------------------------------------------------ 6. historical freeze

def test_a_pre_repair_freeze_stays_readable_but_is_not_certified(checkout):
    """Criterion 6: old evidence remains inspectable; it is not upgraded or accepted.

    The pre-repair freeze is modelled exactly as it exists: the 19 wrapper-era bindings, no
    `freeze_contract_version`. Verification must name what is missing rather than fill it in.
    """
    result = _run("""
        import json
        from src.research.llm_matchup.hardening import freeze_v3_sonnet46 as FZ
        historical = {"freeze": "FREEZE_LLM_MATCHUP_V3_SONNET46",
                      "module_hashes": {m: h for m, h in FZ.current_module_hashes().items()
                                        if m not in FZ.REQUIRED_CORE_MODULES}}
        report = FZ.verify_freeze(historical)
        print(json.dumps({"report": report,
                          "still_readable": historical.get("freeze"),
                          "historical_hashes": sorted(historical["module_hashes"]),
                          "n_required": len(FZ.REQUIRED_MODULES),
                          "unchanged_hash_count": len(historical["module_hashes"])}))
    """, cwd=checkout)

    report = result["report"]
    assert result["still_readable"] == "FREEZE_LLM_MATCHUP_V3_SONNET46"   # inspectable
    assert report["ok"] is False
    # A pre-repair freeze declares no contract, and the contract is checked first, so that is
    # the reported reason. Updated to the declared policy rather than softening the policy to
    # preserve the older INCOMPLETE_BINDING string.
    assert report["status"] == "MISSING_CONTRACT"
    # ...but the binding diagnostics must SURVIVE the contract refusal: naming what an old
    # freeze lacks is the whole point of being able to inspect it.
    assert sorted(report["missing_required_cores"]) == sorted(report["missing_bindings"])
    assert report["missing_required_cores"], "diagnostics were blanked by the contract check"
    assert report["freeze_contract"] is None                              # not back-stamped
    # Verification must not have written anything into the historical freeze: it still holds
    # exactly the bindings it had, and the missing cores are reported, never filled in.
    assert result["unchanged_hash_count"] == result["n_required"] - len(report["missing_bindings"])
    assert all(c not in result["historical_hashes"] for c in report["missing_required_cores"])


# ------------------------------------------------------------------ 7. checkout attribution

def test_sources_are_not_taken_from_another_checkout(checkout, tmp_path):
    """Criterion 7: `SRC_DIR` follows the executing checkout, never the deployed tree."""
    foreign = _copy_checkout(str(tmp_path / "foreign"))
    with open(os.path.join(foreign, HARDENING_REL, "controls_v3_core.py"), "a") as f:
        f.write("\n# FOREIGN_TREE_MARKER_c40a\n")

    result = _run(SELF_FREEZE_THEN_VERIFY % "", cwd=checkout)

    assert result["src_dir"].startswith(checkout + os.sep)
    assert not result["src_dir"].startswith("/home/ubuntu/src")
    assert result["report"]["ok"] is True, "the foreign tree must not participate at all"

    foreign_hash = _run(SELF_FREEZE_THEN_VERIFY % "", cwd=foreign)
    assert (foreign_hash["freeze"]["module_hashes"]["controls_v3_core.py"]
            != result["freeze"]["module_hashes"]["controls_v3_core.py"]), (
        "fixture precondition: the two checkouts must differ")


# --------------------------------------------------------------------- 8. the real consumer

def test_freeze_refuses_to_return_a_stale_freeze(checkout, tmp_path):
    """Criterion 8: `freeze()` now refuses instead of handing back the stale manifest.

    `verify_freeze` is the GENUINE verifier here. Only `build_manifest()` is replaced, because
    it assembles eight result artifacts under `OUT` that have nothing to do with source
    binding -- an unrelated expensive dependency. The reverify branch, the side-file write and
    the refusal are all the real code path.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    result = _run("""
        import json, os
        from src.research.llm_matchup.hardening import freeze_v3_sonnet46 as FZ

        out = %r
        FZ.OUT = out
        FZ.FREEZE_PATH = os.path.join(out, "FREEZE_LLM_MATCHUP_V3_SONNET46.json")

        # A stale freeze: wrapper-era bindings only, exactly like the one on disk today.
        stale = {"freeze": "FREEZE_LLM_MATCHUP_V3_SONNET46", "generation_hash": "old",
                 "module_hashes": {m: h for m, h in FZ.current_module_hashes().items()
                                   if m not in FZ.REQUIRED_CORE_MODULES}}
        json.dump(stale, open(FZ.FREEZE_PATH, "w"))

        FZ.build_manifest = lambda: {"generation_hash": "new", "frozen_unix": 1}

        try:
            FZ.freeze()
            print(json.dumps({"outcome": "RETURNED_STALE"}))
        except FZ.FreezeBindingError as e:
            side = [f for f in os.listdir(out) if "reverify" in f]
            print(json.dumps({"outcome": "REFUSED", "error": str(e),
                              "side_file_written": bool(side)}))
    """ % str(out_dir), cwd=checkout)

    assert result["outcome"] == "REFUSED", (
        "freeze() handed back a freeze whose required bindings are absent")
    assert "controls_v3_core.py" in result["error"]
    assert result["side_file_written"] is True, "evidence must still be written before refusing"


# =====================================================================================
# Reviewer counterexamples. Each of these passed against the first version of this repair.
# =====================================================================================

#: Load a foreign core under its REAL dotted name *before* the wrapper and the freeze module
#: import it, so the wrapper genuinely binds the foreign object -- the mixed-checkout case
#: that two independent single-checkout runs cannot express.
PRELOAD_FOREIGN_CORE = """
    import importlib.util, json, os, sys
    dotted, foreign, wrapper, attr = %r, %r, %r, %r
    import src.research.llm_matchup.hardening
    spec = importlib.util.spec_from_file_location(dotted, foreign)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = mod
    spec.loader.exec_module(mod)

    wrapper_mod = __import__("src.research.llm_matchup.hardening." + wrapper,
                             fromlist=[wrapper])
    from src.research.llm_matchup.hardening import freeze_v3_sonnet46 as FZ

    frozen = {"module_hashes": dict(FZ.current_module_hashes(check_origins=False)),
              "freeze_contract_version": FZ.FREEZE_CONTRACT_VERSION}
    report = FZ.verify_freeze(frozen)
    try:
        FZ.current_module_hashes()
        construction = "NOT_BLOCKED"
    except FZ.FreezeBindingError:
        construction = "RAISED"
    print(json.dumps({
        "wrapper_uses_foreign": os.path.realpath(getattr(wrapper_mod, attr).__file__) == foreign,
        "report": report, "construction": construction}))
"""


@pytest.mark.parametrize("wrapper,attr,core", [
    ("controls_v3_sonnet46", "CORE", "controls_v3_core.py"),
    ("eligibility_v3_sonnet46", "ECORE", "eligibility_v3_core.py"),
])
def test_foreign_loaded_core_is_rejected(checkout, tmp_path, wrapper, attr, core):
    """Counterexample 1: the wrapper runs a foreign core; verification used to say OK.

    The earlier attribution test ran two checkouts independently, which never puts a foreign
    module and a local file in the same process. Here the wrapper demonstrably holds the
    foreign object and the genuine verifier must refuse.
    """
    foreign = _copy_checkout(str(tmp_path / f"foreign_{core}"))
    foreign_core = os.path.join(foreign, HARDENING_REL, core)
    with open(foreign_core, "a") as f:
        f.write("\nFOREIGN_CORE_MARKER_e91d = True\n")

    result = _run(PRELOAD_FOREIGN_CORE % (
        f"src.research.llm_matchup.hardening.{core[:-3]}", foreign_core, wrapper, attr),
        cwd=checkout)

    assert result["wrapper_uses_foreign"] is True, "fixture precondition"
    assert result["report"]["status"] == "FOREIGN_ORIGIN"
    assert result["report"]["ok"] is False
    assert [v["module"] for v in result["report"]["foreign_origins"]] == [core]
    assert result["construction"] == "RAISED", "construction must fail closed too"


def test_identical_byte_foreign_core_is_still_rejected(checkout, tmp_path):
    """Counterexample 1, byte-identical: origin is checked, not content."""
    foreign = _copy_checkout(str(tmp_path / "foreign_identical_core"))
    foreign_core = os.path.join(foreign, HARDENING_REL, "controls_v3_core.py")
    local_core = os.path.join(checkout, HARDENING_REL, "controls_v3_core.py")
    shutil.copy2(local_core, foreign_core)
    assert open(foreign_core, "rb").read() == open(local_core, "rb").read()

    result = _run(PRELOAD_FOREIGN_CORE % (
        "src.research.llm_matchup.hardening.controls_v3_core", foreign_core,
        "controls_v3_sonnet46", "CORE"), cwd=checkout)

    assert result["wrapper_uses_foreign"] is True
    assert result["report"]["status"] == "FOREIGN_ORIGIN", (
        "byte-identical foreign core bypassed the origin check")


@pytest.mark.parametrize("declared,expected", [
    (None, "MISSING_CONTRACT"),
    ("totally_made_up_v99", "UNSUPPORTED_CONTRACT"),
    ("__CURRENT__", "OK"),
])
def test_contract_is_enforced_not_inferred_from_hashes(checkout, declared, expected):
    """Counterexample 2: complete current hashes used to certify any contract, or none.

    Matching hashes are not evidence of contract compatibility -- a pre-repair freeze can
    carry every current hash and still describe a smaller required set.
    """
    result = _run("""
        import json
        from src.research.llm_matchup.hardening import freeze_v3_sonnet46 as FZ
        declared = %r
        frozen = {"module_hashes": dict(FZ.current_module_hashes())}
        if declared == "__CURRENT__":
            frozen["freeze_contract_version"] = FZ.FREEZE_CONTRACT_VERSION
        elif declared is not None:
            frozen["freeze_contract_version"] = declared
        print(json.dumps(FZ.verify_freeze(frozen)))
    """ % declared, cwd=checkout)

    assert result["status"] == expected
    assert result["ok"] is (expected == "OK")
    if expected != "OK":
        # Hashes were complete and current, so nothing else may be blamed for the refusal.
        assert result["missing_bindings"] == []
        assert result["mismatched"] == []


#: Bindings valid, contract supported, identity different. Only `build_manifest` is replaced
#: -- the unrelated artifact assembly -- so the reverify branch and the genuine verifier run.
GENERATION_DRIFT = """
    import json, os
    from src.research.llm_matchup.hardening import freeze_v3_sonnet46 as FZ
    out, recomputed = %r, %r
    FZ.OUT = out
    FZ.FREEZE_PATH = os.path.join(out, "FREEZE_LLM_MATCHUP_V3_SONNET46.json")
    existing = {"freeze": "FREEZE_LLM_MATCHUP_V3_SONNET46",
                "generation_hash": "IDENTITY_A",
                "module_hashes": dict(FZ.current_module_hashes()),
                "freeze_contract_version": FZ.FREEZE_CONTRACT_VERSION}
    json.dump(existing, open(FZ.FREEZE_PATH, "w"))
    before = open(FZ.FREEZE_PATH, "rb").read()
    FZ.build_manifest = lambda: {"generation_hash": recomputed, "frozen_unix": 1}
    try:
        got = FZ.freeze()
        outcome, detail = "RETURNED", got.get("generation_hash")
    except FZ.FreezeGenerationMismatch as e:
        outcome, detail = "REFUSED_GENERATION", str(e)
    except FZ.FreezeBindingError as e:
        outcome, detail = "REFUSED_BINDING", str(e)
    print(json.dumps({"outcome": outcome, "detail": detail,
                      "side_file": any("reverify" in f for f in os.listdir(out)),
                      "historical_unchanged": open(FZ.FREEZE_PATH, "rb").read() == before}))
"""


def test_generation_drift_cannot_return_the_old_freeze_as_accepted(checkout, tmp_path):
    """Counterexample 3: `instrument_drift_detected=true`, then the old manifest was returned.

    Source bindings are deliberately VALID here, so the refusal can only come from the
    generation-identity comparison -- a distinct exception type proves which one fired.
    """
    out_dir = tmp_path / "drift_out"
    out_dir.mkdir()
    result = _run(GENERATION_DRIFT % (str(out_dir), "IDENTITY_B"), cwd=checkout)

    assert result["outcome"] == "REFUSED_GENERATION", result
    assert "IDENTITY_A" in result["detail"] and "IDENTITY_B" in result["detail"]
    assert result["side_file"] is True, "diagnostic evidence must be written before refusing"
    assert result["historical_unchanged"] is True, "the historical freeze must not be rewritten"


def test_matching_generation_identity_returns_the_existing_freeze(checkout, tmp_path):
    """The other half of the contract: a genuinely unchanged instrument still revalidates."""
    out_dir = tmp_path / "match_out"
    out_dir.mkdir()
    result = _run(GENERATION_DRIFT % (str(out_dir), "IDENTITY_A"), cwd=checkout)

    assert result["outcome"] == "RETURNED", result
    assert result["detail"] == "IDENTITY_A"
    assert result["historical_unchanged"] is True
