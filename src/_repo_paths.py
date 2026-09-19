"""Repository path resolution -- packaging only, no scientific behaviour.

THE DEFECT
----------
Library modules hardcoded the deployed host's layout:

    sys.path.insert(0, "/home/ubuntu/scripts")     # src/research/matchup/corpus.py
    _SCRIPTS = "/home/ubuntu/scripts"

`multisrc_corpus` and `championship_adapter` live in the repository's own `scripts/`
directory but are imported as TOP-LEVEL modules, so that insert is what made them
importable. On the deployed host it silently resolves to the deployed tree even from a
different checkout; anywhere else it is

    ModuleNotFoundError: No module named 'multisrc_corpus'

which is exactly what an independent reviewer reproduced running

    python -m pytest tests/research/test_matchup_leakage.py --collect-only -q

THE FIX
-------
Derive the repository root from THIS FILE's location. `src/_repo_paths.py` sits at
`<repo>/src/_repo_paths.py`, so the root is two parents up. `V8C_ROOT` overrides for a
relocated tree.

Nothing about what the code computes changes. The same modules are imported, under the
same names, in the same order -- only the directory they are found in stops being one
machine's absolute path.

This is deliberately NOT a mechanical rewrite of every "/home/ubuntu" in the repository.
Data roots, output roots, historical evidence paths and documentation are a separate
concern and are recorded as portability blockers rather than edited here.
"""
from __future__ import annotations

import os
import sys

#: <repo>/src/_repo_paths.py -> <repo>
_DERIVED_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

REPO_ROOT = os.environ.get("V8C_ROOT", _DERIVED_ROOT)
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")


def ensure_scripts_importable() -> str:
    """Put the repository's own `scripts/` on `sys.path`, once. Returns the directory.

    Idempotent, and it never adds a path belonging to a different checkout.
    """
    if SCRIPTS_DIR not in sys.path:
        sys.path.insert(0, SCRIPTS_DIR)
    return SCRIPTS_DIR


def ensure_repo_importable() -> str:
    """Put the repository root on `sys.path`, once. Returns the directory."""
    if REPO_ROOT not in sys.path:
        sys.path.insert(0, REPO_ROOT)
    return REPO_ROOT
