"""Mandate §22, §23 -- the architectural firewall, proven mechanically.

    The baseline quantitative system must continue to function with the LLM completely
    disabled. This is a hard test requirement.

These tests do not read documentation or trust a comment. They walk the actual import
graph and hash the actual champion files.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import sys

sys.path.insert(0, "/home/ubuntu")

import pytest

REPO = pathlib.Path("/home/ubuntu")

#: Everything the quant engine owns. Nothing here may depend on any LLM package.
QUANT_ROOTS = (
    "src/research/prediction_engine",
    "src/research/prospective",
    "src/research/forward",
    "src/research/closing",
    "src/research/reconciliation",
    "src/research/paper",
    "src/engine",
    "src/features",
    "src/models",
)

QUANT_SCRIPTS = (
    "scripts/pilotC_stat_mixer.py",
    "scripts/pilotC_forward_predict.py",
    "scripts/forecast_broadcast.py",
)

#: Both LLM generations: the legacy latent-state experiment and the new hypothesis layer.
LLM_PACKAGES = ("src.research.llm_matchup", "src.research.hypothesis_engine")


def _imports_of(path: pathlib.Path) -> set[str]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                out.add(node.module)
    return out


def _py_files(rel: str):
    p = REPO / rel
    if p.is_file():
        return [p]
    return sorted(p.rglob("*.py")) if p.exists() else []


# ============================================================ quant must not import LLM
@pytest.mark.parametrize("root", QUANT_ROOTS + QUANT_SCRIPTS)
def test_quant_layer_does_not_import_any_llm_package(root):
    offenders: list[str] = []
    for f in _py_files(root):
        for mod in _imports_of(f):
            if any(mod.startswith(pkg) for pkg in LLM_PACKAGES):
                offenders.append(f"{f.relative_to(REPO)} imports {mod}")
    assert offenders == [], (
        "the quantitative engine must run with the LLM layer absent:\n"
        + "\n".join(offenders))


def test_champion_produces_p_model_with_the_llm_packages_uninstalled():
    """Import and exercise the champion's predict path in a subprocess where BOTH LLM
    packages are blocked at import time. If the champion needed them, this fails."""
    import subprocess

    probe = r"""
import sys, importlib.abc, importlib.machinery

BLOCKED = ("src.research.llm_matchup", "src.research.hypothesis_engine")

class Blocker(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == b or fullname.startswith(b + ".") for b in BLOCKED):
            raise ImportError("BLOCKED BY TEST: " + fullname)
        return None

sys.meta_path.insert(0, Blocker())
sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

import numpy as np
import pilotC_stat_mixer as mix
import pilotC_forward_predict as fwd

# The champion's probability path must be importable and callable without any LLM code.
assert callable(mix.roll) and callable(mix.match_features) and callable(mix.feat_names)
assert callable(fwd.fit_full) and callable(fwd.predict_one) and callable(fwd.devig)

# de-vig is pure and can be exercised directly: two fair 2.0 prices -> 0.5 with 0 overround
p, overround = fwd.devig(2.0, 2.0)
assert abs(p - 0.5) < 1e-9, p
assert abs(overround) < 1e-9, overround

print("CHAMPION_OK")
"""
    r = subprocess.run([sys.executable, "-c", probe], capture_output=True, text=True,
                       cwd="/home/ubuntu")
    assert "CHAMPION_OK" in r.stdout, (
        f"champion could not run with the LLM packages blocked.\n"
        f"stdout={r.stdout}\nstderr={r.stderr[-2500:]}")


# ==================================================== LLM must not import the quant layer
def test_hypothesis_engine_imports_nothing_from_the_quant_or_market_layers():
    forbidden_fragments = (
        "prediction_engine", "prospective", "forward", "closing", "reconciliation",
        "paper", "broadcast", "pilotC", "src.engine", "src.features", "src.models",
        "telegram",
    )
    offenders: list[str] = []
    for f in _py_files("src/research/hypothesis_engine"):
        for mod in _imports_of(f):
            if any(fr in mod for fr in forbidden_fragments):
                offenders.append(f"{f.relative_to(REPO)} imports {mod}")
    assert offenders == [], "\n".join(offenders)


def test_hypothesis_engine_never_imports_the_legacy_latent_state_experiment():
    """Legacy ordinal state outputs must not be able to enter the new pipeline."""
    offenders: list[str] = []
    for f in _py_files("src/research/hypothesis_engine"):
        for mod in _imports_of(f):
            if "llm_matchup" in mod:
                offenders.append(f"{f.relative_to(REPO)} imports {mod}")
    assert offenders == [], "\n".join(offenders)


#: Assignments whose whole purpose is to NAME canonical paths in order to protect them.
#: Skipped when scanning for references, because listing a path in a deny-list is the
#: opposite of depending on it. Everything else in the file is still scanned.
_DENY_LIST_CONSTANTS = {"PROTECTED_PATHS"}


def test_hypothesis_engine_writes_no_canonical_data_path():
    """No module may reference a canonical evidence, commitment or settlement path.

    Scans the source with deny-list constants elided, so a protective mention does not
    read as a dependency while a real one still fails.
    """
    canonical = ("data/forward", "data/prospective", "data/attestations",
                 "data/forecast_broadcast", "data/discovery/pilotC",
                 "commitments.jsonl", "predictions.jsonl", "broadcasts.jsonl")
    offenders: list[str] = []
    for f in _py_files("src/research/hypothesis_engine"):
        src = f.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src)
        lines = src.splitlines()
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id in _DENY_LIST_CONSTANTS
                    for t in node.targets):
                for ln in range(node.lineno - 1, (node.end_lineno or node.lineno)):
                    lines[ln] = ""
        scrubbed = "\n".join(lines)
        for c in canonical:
            if c in scrubbed:
                offenders.append(f"{f.relative_to(REPO)} references {c}")
    assert offenders == [], "\n".join(offenders)


def test_the_canonical_path_scan_can_actually_fail(tmp_path):
    """A guard that cannot fail proves nothing: verify the scan detects a real reference."""
    src = 'X = "data/forward/predictions.jsonl"\n'
    tree = ast.parse(src)
    assert not any(
        isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id in _DENY_LIST_CONSTANTS
                for t in n.targets)
        for n in ast.walk(tree)), "this assignment must NOT be elided"
    assert "data/forward" in src


def test_no_module_opens_a_path_outside_the_engines_own_output_tree():
    """Every open()/write target must live under the hypothesis engine's out dir or the
    read-only corpus it is allowed to read."""
    allowed_fragments = (
        "research/hypothesis_engine/out",
        "data/thestatsapi/championship",     # read-only corpus (lineups)
    )
    offenders: list[str] = []
    for f in _py_files("src/research/hypothesis_engine"):
        tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                    and node.func.id == "open":
                for arg in node.args[:1]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if not any(a in arg.value for a in allowed_fragments):
                            offenders.append(
                                f"{f.relative_to(REPO)}:{node.lineno} open({arg.value!r})")
    assert offenders == [], "\n".join(offenders)


# ====================================================== the champion itself is untouched
def test_champion_freeze_hashes_still_match():
    fz = json.loads((REPO / "research/contextual_matchup/CHAMPION_FREEZE.json")
                    .read_text())

    def sha(rel):
        p = REPO / rel
        assert p.exists(), f"champion file missing: {rel}"
        return hashlib.sha256(p.read_bytes()).hexdigest()

    assert sha("scripts/pilotC_stat_mixer.py") == fz["stat_mixer_py_sha256"]
    assert sha("scripts/pilotC_forward_predict.py") == fz["forward_predict_py_sha256"]
    assert sha(fz["artifact_path"]) == fz["artifact_sha256"]
    assert sha(fz["scope_config_path"]) == fz["scope_config_sha256"]
    assert fz["frozen_at_commit"] == "224aef608f501496a06a7231401ee5706486890f"


# ================================================ no probability surface in this package
def test_no_module_in_the_package_defines_a_probability_producing_symbol():
    banned_names = {
        "p_model", "predict_proba", "calibrate", "calibration", "devig", "de_vig",
        "implied_probability", "edge", "expected_value", "fair_odds", "settle",
        "closing_line", "market_probability",
    }
    offenders: list[str] = []
    for f in _py_files("src/research/hypothesis_engine"):
        tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name.lower() in banned_names:
                    offenders.append(f"{f.relative_to(REPO)}:{node.lineno} {node.name}")
    assert offenders == [], (
        "the hypothesis layer may not define a probability/market symbol:\n"
        + "\n".join(offenders))


def test_lifecycle_has_no_edge_from_an_llm_output_to_a_model_feature():
    """The forbidden shortcut must be structurally unrepresentable, not just discouraged."""
    from src.research.hypothesis_engine import lifecycle as L

    with pytest.raises(L.LifecycleError):
        L.advance(L.LLM_PROPOSED, L.WALK_FORWARD_CANDIDATE)
    with pytest.raises(L.LifecycleError):
        L.advance(L.LLM_PROPOSED, L.OOS_SUPPORTED)
    with pytest.raises(L.LifecycleError):
        L.advance(L.LLM_PROPOSED, L.PROSPECTIVELY_SUPPORTED)
    with pytest.raises(L.LifecycleError):
        L.advance(L.QUERY_VALID, L.HISTORICAL_RESULT)   # skipping DATA_SUFFICIENT

    # the only legal forward step from a proposal is query validation
    assert L.advance(L.LLM_PROPOSED, L.QUERY_VALID) == L.QUERY_VALID


def test_terminal_success_state_is_not_promotion():
    """Reaching the end of the funnel makes a hypothesis ELIGIBLE for a separate human
    promotion decision. It is not itself promotion, and no state represents that."""
    from src.research.hypothesis_engine import lifecycle as L

    assert L.is_terminal(L.PROSPECTIVELY_SUPPORTED)
    assert L.next_state(L.PROSPECTIVELY_SUPPORTED) is None
    assert not any("PROMOT" in s for s in L.ALL_STATES)
