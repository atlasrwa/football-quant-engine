"""DEVELOPMENT-ONLY path adapter for the V8C exposed-50 handoff bundle.

WHY THIS EXISTS
---------------
The engine hardcodes absolute paths:

    src/research/matchup/corpus.py        CACHE    = "/home/ubuntu/data/thestatsapi/championship"
    src/research/matchup/corpus.py        _SCRIPTS = "/home/ubuntu/scripts"
    src/research/hypothesis_v71/corpus_index.py    sys.path.insert(0, "/home/ubuntu/scripts")
    src/research/hypothesis_v8c/harness.py         ROOT = "/home/ubuntu"

A byte-perfect extraction still yields ZERO records if the checkout is not literally at
/home/ubuntu -- the loaders do not error, they `os.path.exists(...) -> False` and skip.

This shim redirects the cache root at the single choke point every loader path funnels
through (`multisrc_corpus.CACHE`, which backs `fixture_path()` and `stats_path()`), so the
scientific apparatus itself is NOT patched. It is a development harness, not part of the
contract, and is deliberately NOT committed to the repository.

USAGE -- import BEFORE any `src.research.*` import:

    import sys; sys.path.insert(0, "<bundle>/loader_adapter")
    import v8c_dev_paths; v8c_dev_paths.install()

ENVIRONMENT
-----------
    V8C_DEV_CACHE_ROOT   default: <bundle>/data/thestatsapi/championship
    V8C_DEV_REPO_ROOT    default: /home/ubuntu   (checkout of football-quant-engine)

ZERO SPEND. No network. No CHAMPION write. Loads no scorer.
"""
from __future__ import annotations

import os
import sys

BUNDLE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CACHE_ROOT = os.environ.get("V8C_DEV_CACHE_ROOT",
                            os.path.join(BUNDLE, "data", "thestatsapi", "championship"))
REPO_ROOT = os.environ.get("V8C_DEV_REPO_ROOT", "/home/ubuntu")

COVERAGE_MATRIX = os.path.join(BUNDLE, "research", "hypothesis_oos", "out", "v7",
                               "V7_COVERAGE_MATRIX.json")
SELECTION_FREEZE = os.path.join(BUNDLE, "research", "hypothesis_engine",
                                "V8B1_PILOT50_SELECTION_FREEZE.json")
FIXTURE_MANIFEST = os.path.join(BUNDLE, "research", "hypothesis_engine",
                                "V8B1_FIXTURE_MANIFEST.json")
SEALED_EXCLUSION = os.path.join(BUNDLE, "research", "hypothesis_engine",
                                "V8C_SEALED947_EXCLUSION_IDS.json")


def install() -> str:
    """Point every cache-reading loader at this bundle. Returns the cache root."""
    if not os.path.isdir(CACHE_ROOT):
        raise SystemExit(f"V8C_DEV_CACHE_ROOT does not exist: {CACHE_ROOT}")
    if not os.path.isdir(os.path.join(REPO_ROOT, "src", "research", "hypothesis_v8c")):
        raise SystemExit(
            f"V8C_DEV_REPO_ROOT does not look like a football-quant-engine checkout: "
            f"{REPO_ROOT} (expected src/research/hypothesis_v8c)")

    for p in (REPO_ROOT, os.path.join(REPO_ROOT, "scripts")):
        if p not in sys.path:
            sys.path.insert(0, p)

    import multisrc_corpus as msc
    msc.CACHE = CACHE_ROOT

    from src.research.matchup import corpus as MC
    MC.CACHE = CACHE_ROOT

    return CACHE_ROOT


def build_v8c_apparatus():
    """-> (capability, PITIndex, SimilarityEngine) for the exposed-50 development cohort.

    Mirrors `hypothesis_v8c.harness.build()` but reads the capability contract from the
    bundle instead of the hardcoded ROOT path, and does NOT check CHAMPION -- CHAMPION is
    not shipped in this bundle and must be verified in the receiving checkout.
    """
    install()
    import json

    from src.research.hypothesis_v71 import capability as CAP
    from src.research.hypothesis_v71 import corpus_index as CI
    from src.research.hypothesis_v71 import similarity as SIM

    cap = CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))
    recs = CI.load_records(include_fresh=True)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    index = CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)
    return cap, index, SIM.SimilarityEngine(index)
