"""V8C shared harness (`v8c_harness_v1`): one place that builds the corpus, index, capability
contract and per-target PIT context, so every V8C script and test measures against exactly the
same apparatus. A second construction path is how two stages drift apart.

ZERO SPEND. Cache-only. No network. No CHAMPION write.
"""
from __future__ import annotations

import hashlib
import json

from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import corpus_index as CI
from src.research.hypothesis_v71 import similarity as SIM
from src.research.hypothesis_v8c import blind_index as BI
from src.research.hypothesis_v8c import pit_context as PC

HARNESS_VERSION = "v8c_harness_v1"

ROOT = "/home/ubuntu"
ENG = f"{ROOT}/research/hypothesis_engine"
COVERAGE_MATRIX = f"{ROOT}/research/hypothesis_oos/out/v7/V7_COVERAGE_MATRIX.json"
CHAMPION_PATH = f"{ROOT}/data/discovery/pilotC_stat_mixer.json"
CHAMPION_EXPECTED = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


def sha_file(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def sha_obj(obj) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def champion_unchanged() -> bool:
    return sha_file(CHAMPION_PATH) == CHAMPION_EXPECTED


def assert_champion_unchanged() -> str:
    got = sha_file(CHAMPION_PATH)
    if got != CHAMPION_EXPECTED:
        raise SystemExit(f"CHAMPION CHANGED ({got}) -- refusing to proceed")
    return got


def load_capability():
    return CAP.CapabilityContract(json.load(open(COVERAGE_MATRIX)))


def load_index():
    """The frozen corpus + fresh seasons, indexed exactly as every prior stage indexed it."""
    recs = CI.load_records(include_fresh=True)
    metrics = [m for m, r in CAP.METRIC_SEMANTICS.items() if r.get("block")]
    return CI.PITIndex(recs, metrics, CAP.METRIC_SEMANTICS)


def build(*, check_champion: bool = True):
    """-> (capability, index, shared SimilarityEngine). The similarity engine is shared because
    it caches on (competition, rec_i) and rebuilds every profile at that reference position --
    a cache hit can never serve a profile fitted at a later time."""
    if check_champion:
        assert_champion_unchanged()
    return load_capability(), load_index(), None


def target_context(index, rec_i, similarity_engine=None):
    """The V8C PER-TARGET PIT context (repairs D-V8C-P0-CTXCUT). Never `execution.build_context`."""
    return PC.build_pit_context(index, rec_i, similarity_engine=similarity_engine)


def sealed_view(index, rec_i, *, strict: bool = False):
    """The index with this target's own observation sealed away."""
    return BI.TargetBlindIndex(index, [rec_i], strict=strict)


def fresh_similarity(index):
    return SIM.SimilarityEngine(index)


def version_stamp() -> dict:
    return {"harness_version": HARNESS_VERSION,
            "pit_context": PC.version_stamp()["pit_context_version"],
            "blind_index": BI.version_stamp()["blind_index_version"],
            "index_version": CI.INDEX_VERSION,
            "uses_v71_execution_build_context": False,
            "champion_expected_sha256": CHAMPION_EXPECTED}
