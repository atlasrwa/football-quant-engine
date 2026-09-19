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

THE SECOND DEFECT -- the environment override
---------------------------------------------
The first repair derived the root from this file but then let `V8C_ROOT` replace it:

    REPO_ROOT = os.environ.get("V8C_ROOT", _DERIVED_ROOT)

That reopened the same hole through configuration. A reviewer reproduced it by placing a
dummy `multisrc_corpus` in a foreign directory and pointing `V8C_ROOT` at it: the
interpreter executing THIS checkout imported the foreign module. An executable import path
that an environment variable can redirect is not a binding to the executing checkout.

THE BEHAVIOUR, EXACTLY
----------------------
`REPO_ROOT` and `SCRIPTS_DIR` are derived **only** from this module's own canonical
filesystem location and cannot be redirected by any environment variable.

* `src/_repo_paths.py` sits at `<repo>/src/_repo_paths.py`, so the root is one directory
  above this file's directory.
* The path is resolved with `os.path.realpath`, so a symlinked or otherwise aliased view of
  the same checkout yields one canonical root. Equivalent spellings of the same directory
  are therefore treated as the same directory, here and in `sys.path`.
* `V8C_ROOT` is **read here at no point** and cannot move executable imports. Relocating a
  checkout needs no variable: the derivation already follows the interpreter.
* There is no fallback. Nothing resolves to `/home/ubuntu`, to a parent directory, or to any
  other checkout. If this file is not inside a repository tree, the derived root simply does
  not contain `scripts/` and the import fails loudly where it always did.

WHAT IS DELIBERATELY NOT IN SCOPE
---------------------------------
Data and output configuration is a separate concern and stays separate. `V8C_ROOT` is still
honoured as a *tree* root by `src/research/hypothesis_v8c/receipt.py`,
`src/research/hypothesis_v8c/anchor.py` and
`research/hypothesis_engine/_run_v8c_exposed50_rehearsal_v3.py`. Those uses are provenance
and output roots, not `sys.path` entries; they are recorded in the review backlog and are
untouched by this module. Nothing about what any code computes changes here. The same
modules are imported, under the same names, in the same order.

This is also deliberately NOT a mechanical rewrite of every "/home/ubuntu" in the
repository. Data roots, output roots, historical evidence paths and documentation are
recorded as portability blockers rather than edited here.
"""
from __future__ import annotations

import os
import sys

#: <repo>/src/_repo_paths.py -> <repo>, canonicalised. Derived from this module's own
#: location and from nothing else: no environment variable participates.
REPO_ROOT = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

#: The repository's own `scripts/`, which holds the top-level modules (`multisrc_corpus`,
#: `championship_adapter`, `pilotC_stat_mixer`) that library code imports by bare name.
SCRIPTS_DIR = os.path.join(REPO_ROOT, "scripts")


def _insert_once(directory: str) -> str:
    """Prepend `directory` to `sys.path` unless an equivalent entry is already there.

    Equivalence is canonical, not textual: `<repo>/scripts` and
    `<repo>/scripts/../scripts` are the same directory and only one entry is added.
    Repeated calls are therefore idempotent and never grow `sys.path`.
    """
    for entry in sys.path:
        try:
            if entry and os.path.realpath(entry) == directory:
                return directory
        except OSError:                      # unreadable or malformed entry: not a match
            continue
    sys.path.insert(0, directory)
    return directory


def ensure_scripts_importable() -> str:
    """Put THIS checkout's `scripts/` on `sys.path`, once. Returns the directory.

    Idempotent, and it can never add a path belonging to a different checkout.
    """
    return _insert_once(SCRIPTS_DIR)


def ensure_repo_importable() -> str:
    """Put THIS checkout's root on `sys.path`, once. Returns the directory.

    Idempotent, and it can never add a path belonging to a different checkout.
    """
    return _insert_once(REPO_ROOT)
