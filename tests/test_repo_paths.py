"""Executable source paths must resolve to the checkout the interpreter is executing.

These are packaging regression tests for `src/_repo_paths.py`. They assert a binding, not
a computation: no scientific behaviour is exercised, no credential is read and no network
call is made.

Every assertion about import resolution runs in an **isolated subprocess**, because
`sys.path` and `sys.modules` are process-global -- a foreign module imported once inside
the pytest process would contaminate every later check. Subprocesses run with `PYTHONPATH`
unset and `PYTHONNOUSERSITE=1` so only the checkout under test can satisfy an import.

The foreign-root case is the one that matters. `V8C_ROOT` used to replace the derived root,
and a reviewer reproduced importing a dummy `multisrc_corpus` from a foreign directory
through it. The test below recreates that dummy, marks it uniquely, and proves it is *not*
what loads. No file outside a pytest temporary directory is created or modified.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap

import pytest

import src._repo_paths as repo_paths

#: The checkout these tests are collected from, derived the same way the module under test
#: derives it -- from a file's own location, never from an environment variable.
CHECKOUT = os.path.realpath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), os.pardir))

#: Marker that exists in no real module in this repository.
FOREIGN_MARKER = "FOREIGN_V8C_ROOT_MARKER_9f3c1ab7"


def _run(script: str, *, cwd: str = CHECKOUT, env_extra: dict | None = None) -> dict:
    """Run `script` in a clean interpreter and return the JSON object it prints.

    The child inherits nothing that could satisfy an import by accident: `PYTHONPATH` is
    removed and user site-packages are disabled.
    """
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONNOUSERSITE"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env.update(env_extra or {})

    proc = subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script)],
        cwd=cwd, env=env, capture_output=True, text=True, timeout=180,
    )
    assert proc.returncode == 0, (
        f"subprocess failed ({proc.returncode})\n--- stdout ---\n{proc.stdout}"
        f"\n--- stderr ---\n{proc.stderr}"
    )
    return json.loads(proc.stdout.strip().splitlines()[-1])


@pytest.fixture()
def foreign_root(tmp_path):
    """A foreign tree holding a uniquely marked dummy `multisrc_corpus`.

    Laid out as a checkout would be -- `<root>/scripts/multisrc_corpus.py` -- so that a
    root override would in fact make it importable. That is the point: the module under
    test must refuse to look here, not merely fail to find anything.
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "multisrc_corpus.py").write_text(
        f'{FOREIGN_MARKER} = True\n'
        'def load_matches(*a, **k):\n'
        '    raise AssertionError("foreign multisrc_corpus was imported")\n'
    )
    # A foreign top-level package too, so a root override would shadow `src` itself.
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text(f'{FOREIGN_MARKER} = True\n')
    return os.path.realpath(str(tmp_path))


# --------------------------------------------------------------------------- derivation

def test_root_and_scripts_belong_to_the_executing_checkout():
    """The default root is this checkout, canonicalised, and `scripts/` sits inside it."""
    assert repo_paths.REPO_ROOT == CHECKOUT
    assert repo_paths.SCRIPTS_DIR == os.path.join(CHECKOUT, "scripts")
    assert os.path.isdir(repo_paths.SCRIPTS_DIR)
    # The modules the hardcoded "/home/ubuntu/scripts" insert used to supply.
    for name in ("multisrc_corpus.py", "championship_adapter.py", "pilotC_stat_mixer.py"):
        assert os.path.isfile(os.path.join(repo_paths.SCRIPTS_DIR, name)), name


def test_root_is_canonical_and_not_home_ubuntu_by_construction():
    """The derived root is already canonical, and is derived rather than hardcoded."""
    assert repo_paths.REPO_ROOT == os.path.realpath(repo_paths.REPO_ROOT)
    source = os.path.join(CHECKOUT, "src", "_repo_paths.py")
    body = open(source, encoding="utf-8").read()
    code = "\n".join(
        line for line in body.splitlines()
        if not line.lstrip().startswith("#")
    ).split('"""')[-1]          # drop the module docstring, which discusses both by name
    assert '"/home/ubuntu' not in code and "'/home/ubuntu" not in code
    assert "V8C_ROOT" not in code, "V8C_ROOT must not participate in import resolution"


# ------------------------------------------------------------------ the foreign override

def test_foreign_v8c_root_cannot_load_a_foreign_module(foreign_root):
    """With `V8C_ROOT` pointing at a foreign tree, the real module still loads.

    Three independent assertions, because any one alone is weak: an import that *succeeds*
    proves nothing on its own when a real `multisrc_corpus` also exists.
    """
    result = _run(
        """
        import json, os, sys
        import src._repo_paths as rp
        rp.ensure_scripts_importable()
        rp.ensure_repo_importable()
        import multisrc_corpus
        print(json.dumps({
            "repo_root": rp.REPO_ROOT,
            "scripts_dir": rp.SCRIPTS_DIR,
            "module_file": os.path.realpath(multisrc_corpus.__file__),
            "has_marker": hasattr(multisrc_corpus, "%s"),
            "sys_path": [os.path.realpath(p) for p in sys.path if p],
        }))
        """ % FOREIGN_MARKER,
        env_extra={"V8C_ROOT": foreign_root},
    )

    assert result["has_marker"] is False, "the foreign dummy module was imported"
    assert result["module_file"] == os.path.join(CHECKOUT, "scripts", "multisrc_corpus.py")
    assert result["repo_root"] == CHECKOUT
    assert result["scripts_dir"] == os.path.join(CHECKOUT, "scripts")
    foreign_entries = [p for p in result["sys_path"] if p == foreign_root
                       or p.startswith(foreign_root + os.sep)]
    assert foreign_entries == [], f"foreign sys.path entries: {foreign_entries}"


def test_foreign_v8c_root_does_not_redirect_the_derived_root(foreign_root):
    """Importing the module alone -- no helper call -- already ignores the override."""
    result = _run(
        """
        import json
        import src._repo_paths as rp
        print(json.dumps({"repo_root": rp.REPO_ROOT, "scripts_dir": rp.SCRIPTS_DIR}))
        """,
        env_extra={"V8C_ROOT": foreign_root},
    )
    assert result["repo_root"] == CHECKOUT
    assert result["scripts_dir"] == os.path.join(CHECKOUT, "scripts")


# ------------------------------------------------------------------- canonical behaviour

def test_equivalent_spellings_of_this_checkout_resolve_identically(tmp_path):
    """A symlinked view of the checkout yields the same canonical root.

    The override is not supported at all, so "equivalent canonical paths" is tested where
    it is still observable: the derivation itself.
    """
    link = tmp_path / "aliased_checkout"
    try:
        os.symlink(CHECKOUT, str(link), target_is_directory=True)
    except (OSError, NotImplementedError):      # pragma: no cover - platform dependent
        pytest.skip("symlinks unavailable in this environment")

    result = _run(
        """
        import json
        import src._repo_paths as rp
        print(json.dumps({"repo_root": rp.REPO_ROOT, "scripts_dir": rp.SCRIPTS_DIR}))
        """,
        cwd=str(link),
    )
    assert result["repo_root"] == CHECKOUT
    assert result["scripts_dir"] == os.path.join(CHECKOUT, "scripts")


def test_repeated_helper_calls_do_not_duplicate_path_entries():
    """Idempotent by canonical directory, not by exact string.

    18 call sites across 16 modules invoke these helpers at import time, so a non-idempotent
    insert would grow `sys.path` on every import. A pre-seeded *alias* of `scripts/` -- a
    different spelling of the very same directory -- must also be recognised, so it too
    produces no second entry.
    """
    result = _run(
        """
        import json, os, sys
        import src._repo_paths as rp
        sys.path.insert(0, os.path.join(rp.SCRIPTS_DIR, os.pardir, "scripts"))
        seeded = len(sys.path)
        rp.ensure_scripts_importable(); rp.ensure_repo_importable()
        after_first = len(sys.path)
        for _ in range(4):
            rp.ensure_scripts_importable(); rp.ensure_repo_importable()
        canon = [os.path.realpath(p) for p in sys.path if p]
        print(json.dumps({
            "added_by_first_round": after_first - seeded,
            "added_by_four_more_rounds": len(sys.path) - after_first,
            "scripts_entries": canon.count(rp.SCRIPTS_DIR),
            "root_entries": canon.count(rp.REPO_ROOT),
        }))
        """
    )
    # The aliased spelling already covered `scripts/`, so only the root is genuinely new.
    assert result["added_by_first_round"] == 1
    # Everything after that is a no-op -- this is the idempotence claim.
    assert result["added_by_four_more_rounds"] == 0
    assert result["scripts_entries"] == 1
    assert result["root_entries"] == 1


# ------------------------------------------------------- the reviewer's own reproducer

def test_matchup_corpus_import_resolves_to_this_checkout():
    """The reproducer that first failed with `ModuleNotFoundError: multisrc_corpus`."""
    result = _run(
        """
        import json, os, sys
        import src.research.matchup.corpus as corpus
        import multisrc_corpus, championship_adapter
        print(json.dumps({
            "corpus": os.path.realpath(corpus.__file__),
            "multisrc": os.path.realpath(multisrc_corpus.__file__),
            "adapter": os.path.realpath(championship_adapter.__file__),
        }))
        """
    )
    for key, value in result.items():
        assert value.startswith(CHECKOUT + os.sep), f"{key} loaded from outside: {value}"
