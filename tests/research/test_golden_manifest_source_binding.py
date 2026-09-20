"""The V3 generation fingerprint must describe the code that is actually executing.

`golden_manifest.current_generation_fingerprint()` used to hash two scientific sources
through hardcoded `/home/ubuntu/src/research/llm_matchup/hardening` paths. Reproduced
before the repair: in an independent checkout whose `sampling.py` had been edited, the
fingerprint still returned the DEPLOYED tree's hash and `check_compatible()` reported
`compatible: True` -- certifying a generation that did not describe the running code.

These tests are OFFLINE and make ZERO Bedrock calls. Every import-resolution assertion runs
in an isolated subprocess: `sys.modules` is process-global, so a foreign module loaded once
inside the pytest process would contaminate every later check. Subprocesses run with `cwd`
set to the checkout under test and `PYTHONPATH` unset, because the deployed venv's editable
finder maps `src` -> `/home/ubuntu/src` and only loses to `cwd`.
"""
from __future__ import annotations

import hashlib
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

#: The deployed tree's subdirectories that a correctly bound fingerprint must never read.
DEPLOYED_FORBIDDEN = ("/home/ubuntu/src", "/home/ubuntu/scripts", "/home/ubuntu/research")


def _run(script: str, *, cwd: str, expect_ok: bool = True) -> dict | str:
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    proc = subprocess.run([sys.executable, "-c", textwrap.dedent(script)],
                          cwd=cwd, env=env, capture_output=True, text=True, timeout=600)
    if not expect_ok:
        return proc.stdout + proc.stderr
    assert proc.returncode == 0, (
        f"subprocess failed ({proc.returncode})\n--- stdout ---\n{proc.stdout}"
        f"\n--- stderr ---\n{proc.stderr}")
    return json.loads(proc.stdout.strip().splitlines()[-1])


def _copy_checkout(dest: str) -> str:
    """A self-contained copy of the WORKING TREE's importable + fingerprinted content.

    The working tree, not `git archive HEAD`: these tests must exercise the code as edited,
    not as last committed. `FORMATION_STRUCTURE_V1.json` is included because the fingerprint
    hashes it, so a copy without it could not produce a fingerprint at all.
    """
    os.makedirs(dest, exist_ok=True)
    for rel in ("src", "scripts"):
        shutil.copytree(os.path.join(CHECKOUT, rel), os.path.join(dest, rel),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    os.makedirs(os.path.join(dest, os.path.dirname(STRUCTURE_REL)), exist_ok=True)
    shutil.copy2(os.path.join(CHECKOUT, STRUCTURE_REL), os.path.join(dest, STRUCTURE_REL))
    return os.path.realpath(dest)


#: Appended to the independent checkout's `sampling.py` so its bytes differ from BOTH this
#: checkout's and the deployed tree's. Without it the attribution test below would pass
#: even against the unrepaired module, purely because the two trees happen to be identical.
CHECKOUT_MARKER = "# INDEPENDENT_CHECKOUT_MARKER_3ad9\n"


@pytest.fixture(scope="module")
def independent_checkout(tmp_path_factory) -> str:
    """A checkout at a path unrelated to this one and to `/home/ubuntu`.

    Its `sampling.py` carries a unique marker, so "the fingerprint describes THIS tree" is a
    claim that can actually fail rather than one satisfied by coincidental byte-equality.
    """
    root = _copy_checkout(str(tmp_path_factory.mktemp("independent_checkout")))
    with open(os.path.join(root, HARDENING_REL, "sampling.py"), "a") as f:
        f.write("\n" + CHECKOUT_MARKER)
    return root


# ------------------------------------------------------------------ 1. independent checkout

FINGERPRINT_WITH_AUDIT = """
    import json, os, sys
    opened = []
    def _hook(event, args):
        if event == "open":
            p = args[0]
            if isinstance(p, str):
                opened.append(p)
    sys.addaudithook(_hook)
    from src.research.llm_matchup.hardening import golden_manifest as GM
    fp = GM.current_generation_fingerprint(n=5, max_scan=50)
    print(json.dumps({"fingerprint": fp,
                      "opened": [os.path.realpath(p) for p in opened if os.path.isabs(p)]}))
"""


def test_fingerprint_succeeds_in_an_independent_checkout_reading_no_deployed_file(
        independent_checkout):
    """Criterion 1: generation succeeds without reading the deployed `/home/ubuntu` tree.

    Asserted by AUDITING every file the call opens, not by inspecting constants: an audit
    hook records each `open`, and no path under the deployed source, scripts or research
    trees may appear. `/home/ubuntu/.venv` is excluded -- that is the interpreter, not the
    scientific tree under test.
    """
    result = _run(FINGERPRINT_WITH_AUDIT, cwd=independent_checkout)

    assert result["fingerprint"]["sampling_module_hash"]
    leaked = [p for p in result["opened"]
              if any(p.startswith(d + os.sep) or p == d for d in DEPLOYED_FORBIDDEN)]
    assert leaked == [], f"fingerprint read deployed-tree files: {leaked}"
    # And it genuinely read this checkout's own covered sources.
    assert any(p.startswith(independent_checkout + os.sep) and p.endswith("sampling.py")
               for p in result["opened"])


# -------------------------------------------------------------------- 2. correct attribution

def test_recorded_hashes_are_the_executing_checkouts_source_bytes(independent_checkout):
    """Criterion 2: the hashes equal the expected bytes from the checkout that ran."""
    result = _run(FINGERPRINT_WITH_AUDIT, cwd=independent_checkout)
    fp = result["fingerprint"]

    for key, basename in (("sampling_module_hash", "sampling.py"),
                          ("neutralization_module_hash", "neutralize_v3.py")):
        path = os.path.join(independent_checkout, HARDENING_REL, basename)
        expected = hashlib.sha256(open(path, "rb").read()).hexdigest()
        assert fp[key] == expected, f"{key} does not describe {path}"

    structure = os.path.join(independent_checkout, STRUCTURE_REL)
    assert fp["formation_structure_hash"] == hashlib.sha256(
        open(structure, "rb").read()).hexdigest()


# --------------------------------------------------------------- 3 & 4. foreign-origin refusal

#: Load `sampling` from a FOREIGN checkout under its real dotted name, exactly as a
#: cross-checkout execution would, then ask for a fingerprint. Nothing is mocked: the real
#: verifier runs against a real module object whose `__file__` is foreign.
FOREIGN_PRELOAD = """
    import importlib.util, json, sys
    dotted = "src.research.llm_matchup.hardening.sampling"
    foreign = %r
    import src.research.llm_matchup.hardening          # anchor the real package first
    spec = importlib.util.spec_from_file_location(dotted, foreign)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = mod
    spec.loader.exec_module(mod)
    from src.research.llm_matchup.hardening import golden_manifest as GM
    try:
        GM.current_generation_fingerprint(n=5, max_scan=50)
        print(json.dumps({"outcome": "ACCEPTED", "loaded_from": mod.__file__}))
    except GM.SourceBindingError as e:
        print(json.dumps({"outcome": "REJECTED", "error": str(e),
                          "loaded_from": mod.__file__}))
"""


def test_foreign_checkout_module_is_rejected(independent_checkout, tmp_path):
    """Criterion 3: a covered module supplied by another checkout is refused."""
    foreign = _copy_checkout(str(tmp_path / "foreign"))
    foreign_sampling = os.path.join(foreign, HARDENING_REL, "sampling.py")
    with open(foreign_sampling, "a") as f:
        f.write("\n# FOREIGN_CHECKOUT_MARKER_5c2e\n")

    result = _run(FOREIGN_PRELOAD % foreign_sampling, cwd=independent_checkout)
    assert result["outcome"] == "REJECTED", result
    assert result["loaded_from"].startswith(foreign + os.sep)


def test_identical_bytes_from_a_foreign_checkout_are_still_rejected(
        independent_checkout, tmp_path):
    """Criterion 4: matching content does not buy a pass -- ORIGIN is what is checked."""
    foreign = _copy_checkout(str(tmp_path / "foreign_identical"))
    foreign_sampling = os.path.join(foreign, HARDENING_REL, "sampling.py")
    local_sampling = os.path.join(independent_checkout, HARDENING_REL, "sampling.py")
    shutil.copy2(local_sampling, foreign_sampling)      # make the bytes exactly equal

    assert open(foreign_sampling, "rb").read() == open(local_sampling, "rb").read(), (
        "fixture precondition: the foreign copy must be byte-identical")

    result = _run(FOREIGN_PRELOAD % foreign_sampling, cwd=independent_checkout)
    assert result["outcome"] == "REJECTED", (
        "byte-identical foreign source bypassed the origin check")
    assert "was loaded from" in result["error"]


# ----------------------------------------------------------------------- 5. source change

def test_editing_a_covered_source_changes_the_fingerprint(independent_checkout, tmp_path):
    """Criterion 5: a real source edit moves the hash and trips the compatibility gate.

    This is the declared contract's first branch: drift INSIDE the correct checkout is a
    generation mismatch, not a binding refusal, and is never silently ignored.
    """
    baseline = _run(FINGERPRINT_WITH_AUDIT, cwd=independent_checkout)["fingerprint"]

    edited = _copy_checkout(str(tmp_path / "edited"))
    with open(os.path.join(edited, HARDENING_REL, "sampling.py"), "a") as f:
        f.write("\n# DELIBERATE_SOURCE_EDIT_b93d\n")
    after = _run(FINGERPRINT_WITH_AUDIT, cwd=edited)["fingerprint"]

    assert after["sampling_module_hash"] != baseline["sampling_module_hash"]

    compat = _run("""
        import json
        from src.research.llm_matchup.hardening import golden_manifest as GM
        frozen = {"generation_fingerprint": json.loads(%r)}
        cur = GM.current_generation_fingerprint(n=5, max_scan=50)
        print(json.dumps(GM.check_compatible(frozen, cur)))
    """ % json.dumps(baseline), cwd=edited)
    assert compat["compatible"] is False
    assert [m["field"] for m in compat["mismatches"]] == ["sampling_module_hash"]


# -------------------------------------------------------------------- 6. canonical paths

def test_symlinked_spelling_of_the_same_checkout_is_not_a_foreign_origin(
        independent_checkout, tmp_path):
    """Criterion 6: an equivalent path spelling must not raise a false binding failure."""
    link = tmp_path / "aliased"
    try:
        os.symlink(independent_checkout, str(link), target_is_directory=True)
    except (OSError, NotImplementedError):  # pragma: no cover - platform dependent
        pytest.skip("symlinks unavailable in this environment")

    direct = _run(FINGERPRINT_WITH_AUDIT, cwd=independent_checkout)["fingerprint"]
    aliased = _run(FINGERPRINT_WITH_AUDIT, cwd=str(link))["fingerprint"]
    assert aliased == direct


# ------------------------------------------------------------------- 7. the real consumer

RESUME_WITH_FOREIGN_SAMPLING = """
    import importlib.util, json, os, sys
    dotted = "src.research.llm_matchup.hardening.sampling"
    foreign = %r
    out_dir = %r
    import src.research.llm_matchup.hardening
    spec = importlib.util.spec_from_file_location(dotted, foreign)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[dotted] = mod
    spec.loader.exec_module(mod)

    from src.research.llm_matchup.hardening import golden_manifest as GM
    from src.research.llm_matchup.hardening import resume_golden_v3 as RG
    GM.OUT = out_dir
    GM.MANIFEST_PATH = os.path.join(out_dir, "golden_v3_fixture_manifest.json")
    RG.LEDGER_PATH = os.path.join(out_dir, "golden_v3_execution_ledger.json")

    def boom(*a, **k):
        raise AssertionError("resume attempted a model call despite a foreign source")

    try:
        RG.resume(call_fn=boom, dry_run=True)
        print(json.dumps({"outcome": "RAN"}))
    except GM.SourceBindingError as e:
        print(json.dumps({"outcome": "REJECTED", "error": str(e)}))
"""


def test_resume_preflight_refuses_to_run_against_a_foreign_source(
        independent_checkout, tmp_path):
    """Criterion 7: the REAL resume consumer propagates the rejection.

    `resume()` is exercised with the genuine `current_generation_fingerprint` -- the
    verifier is never mocked. The injected `call_fn` only proves no model call is reached.
    A frozen manifest is written first so the run gets past ABORT_NO_FROZEN_MANIFEST and
    actually reaches the generation check.
    """
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    manifest = _run("""
        import json
        from src.research.llm_matchup.hardening import golden_manifest as GM
        print(json.dumps(GM.build_manifest(["mt_1"], n=5, max_scan=50)))
    """, cwd=independent_checkout)
    (out_dir / "golden_v3_fixture_manifest.json").write_text(json.dumps(manifest))

    foreign = _copy_checkout(str(tmp_path / "foreign_resume"))
    foreign_sampling = os.path.join(foreign, HARDENING_REL, "sampling.py")

    result = _run(RESUME_WITH_FOREIGN_SAMPLING % (foreign_sampling, str(out_dir)),
                  cwd=independent_checkout)
    assert result["outcome"] == "REJECTED", (
        "resume() accepted a foreign-sourced generation instead of refusing")
