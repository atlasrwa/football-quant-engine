"""LLM_MATCHUP_V3 (Sonnet 4.5 arm) control battery.

THIN WRAPPER over `controls_v3_core` (generation-neutral) -- the SAME control implementation
that runs the Sonnet 4.6 arm (`controls_v3_sonnet46.py`), just pointed at the frozen Sonnet
4.5 generation, its own manifest/ledger, and its own output/cache namespace. No control logic
is duplicated here; see `controls_v3_core` for the full docstring.

Cache namespace: reuses the Sonnet 4.5 GOLDEN cache dir (`adapter_v4.CACHE_DIR`, i.e.
out/hardening_v3/cache/), not a new one. This is deliberate, not an oversight: the control
battery's k self-noise calls at call_index=0 are IDENTICAL packets to the ones the golden
batch already paid for, and adapter_v4's cache key binds model_id + full version stamp +
prompt/schema hash + packet_hash + call_index -- so reusing the golden cache dir lets
call_index=0 replay for free (checkpoint mandate SS9: "reuse existing genuine Sonnet 4.5
self-noise calls ONLY if ... same exact packet hash"), while the cache key structurally
prevents any 4.6 response (different model_id, different cache_dir) from ever satisfying a
4.5 request, and vice versa.

Owns, and is the only writer of:
    out/hardening_v3/golden_v3_controls.json
    out/hardening_v3/golden_v3_repeatability.json
    out/hardening_v3/golden_v3_counter_evidence.json
    out/hardening_v3/golden_v3_control_manifest.json     (frozen BEFORE any paid control call)
NEVER writes to out/v3_sonnet46/ (the 4.6 arm's namespace) and never modifies the golden batch's
own execution ledger (`golden_v3_execution_ledger.json`) -- read-only for accepted-fixture
lookup.
"""
from __future__ import annotations
import os

from src.research.llm_matchup.bedrock_adapter import check_bedrock_capability, IncompatibleBotoError
from src.research.llm_matchup.hardening import adapter_v4 as A4
from src.research.llm_matchup.hardening import controls_v3_core as CORE
from src.research.llm_matchup.hardening import golden_manifest as GM
from src.research.llm_matchup.hardening import resume_golden_v3 as RG
from src.research.llm_matchup.hardening import run_lock as RL
from src.research.llm_matchup.hardening import versions_v3 as V3

OUT = GM.OUT
CACHE_DIR = A4.CACHE_DIR
CONTROLS_PATH = os.path.join(OUT, "golden_v3_controls.json")
REPEAT_PATH = os.path.join(OUT, "golden_v3_repeatability.json")
COUNTER_PATH = os.path.join(OUT, "golden_v3_counter_evidence.json")
CONTROL_MANIFEST_PATH = os.path.join(OUT, "golden_v3_control_manifest.json")
LOCK_PATH = os.path.join(OUT, ".golden_v3_control_live_runner.lock")

TEAM_ALIAS_A, TEAM_ALIAS_B = CORE.TEAM_ALIAS_A, CORE.TEAM_ALIAS_B
COMP_ALIAS = CORE.COMP_ALIAS
FORMATION_ALIAS = CORE.FORMATION_ALIAS
QuotaExhausted = CORE.QuotaExhausted


def _cfg() -> CORE.GenerationConfig:
    manifest = GM.load_manifest()
    if manifest is None:
        raise RuntimeError("frozen Sonnet 4.5 fixture manifest not found; refusing to invent "
                           "a fixture selection for controls")
    return CORE.GenerationConfig(
        name="sonnet45", gen=V3, cache_dir=CACHE_DIR, manifest=manifest,
        golden_ledger=RG.load_ledger(),
        controls_path=CONTROLS_PATH, repeat_path=REPEAT_PATH, counter_path=COUNTER_PATH)


def build_and_freeze_control_manifest(fixtures: list[str] | None = None, n_fixtures: int = 8,
                                      k: int = 3) -> dict:
    """Materialize + hash the complete intended 4.5 control battery BEFORE any paid call, and
    freeze it (refuses to overwrite an existing frozen control manifest)."""
    cfg = _cfg()
    chosen = fixtures or CORE.accepted_fixture_ids(cfg)[:n_fixtures]
    manifest = CORE.build_control_manifest(cfg, chosen, k)
    status = CORE.freeze_control_manifest_if_absent(manifest, CONTROL_MANIFEST_PATH)
    manifest["_save_status"] = status
    if status == "EXISTS_UNCHANGED":
        return CORE.load_control_manifest(CONTROL_MANIFEST_PATH)
    return manifest


def run_controls(fixtures: list[str] | None = None, n_fixtures: int = 8, k: int = 3,
                 persist: bool = True) -> dict:
    """Run the shared control battery against Sonnet 4.5. Guarded by the exclusive live-runner
    lock and a Bedrock-capability fail-fast check, exactly like `resume_golden_v3.resume`."""
    try:
        lock = RL.acquire(LOCK_PATH)
        lock.__enter__()
    except RL.AlreadyRunningError as e:
        return {"status": "ABORT_ALREADY_RUNNING", "detail": str(e)}
    try:
        try:
            check_bedrock_capability(region=V3.DEFAULT_BEDROCK_REGION)
        except IncompatibleBotoError as e:
            return {"status": "ABORT_INCOMPATIBLE_BOTO3", "detail": str(e)}
        return CORE.run_controls(_cfg(), fixtures=fixtures, n_fixtures=n_fixtures, k=k,
                                 persist=persist)
    finally:
        lock.__exit__(None, None, None)


def run_counter_evidence(k: int = 1, persist: bool = True) -> dict:
    try:
        lock = RL.acquire(LOCK_PATH)
        lock.__enter__()
    except RL.AlreadyRunningError as e:
        return {"status": "ABORT_ALREADY_RUNNING", "detail": str(e)}
    try:
        try:
            check_bedrock_capability(region=V3.DEFAULT_BEDROCK_REGION)
        except IncompatibleBotoError as e:
            return {"status": "ABORT_INCOMPATIBLE_BOTO3", "detail": str(e)}
        return CORE.run_counter_evidence(_cfg(), k=k, persist=persist)
    finally:
        lock.__exit__(None, None, None)
