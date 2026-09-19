"""LLM_MATCHUP_V3_SONNET46 control battery — the Sonnet 4.6 arm's identity / stability tests.

THIN WRAPPER over `controls_v3_core` (generation-neutral). This module used to contain the
full scientific control implementation hardwired to the 4.6 generation; that implementation
has been extracted VERBATIM into `controls_v3_core.run_controls` / `.run_counter_evidence` so
the Sonnet 4.5 arm (`controls_v3_sonnet45.py`) can run the exact same control logic instead of
forking a second copy. See `controls_v3_core` for the full docstring and
`tests/research/test_controls_v3_core_equivalence.py` for the proof that this extraction
reproduces the pre-refactor 4.6 output exactly.

This module still owns, and is the only writer of:
    out/v3_sonnet46/golden_v3_sonnet46_controls.json
    out/v3_sonnet46/golden_v3_sonnet46_repeatability.json
    out/v3_sonnet46/golden_v3_sonnet46_counter_evidence.json
    out/v3_sonnet46/cache/                              (LLM response cache namespace)

Public API (`run_controls`, `run_counter_evidence`, module-level constants) is UNCHANGED so
`eligibility_v3_sonnet46.py` and anything else importing this module keeps working.
"""
from __future__ import annotations
import os

from src.research.llm_matchup.hardening import controls_v3_core as CORE
from src.research.llm_matchup.hardening import golden_v3_sonnet46 as G46
from src.research.llm_matchup.hardening import versions_v3_sonnet46 as V46

OUT = G46.OUT
CACHE_DIR = G46.CACHE_DIR
CONTROLS_PATH = os.path.join(OUT, "golden_v3_sonnet46_controls.json")
REPEAT_PATH = os.path.join(OUT, "golden_v3_sonnet46_repeatability.json")
COUNTER_PATH = os.path.join(OUT, "golden_v3_sonnet46_counter_evidence.json")

# Re-exported for backward compatibility with anything importing these names from here.
TEAM_ALIAS_A, TEAM_ALIAS_B = CORE.TEAM_ALIAS_A, CORE.TEAM_ALIAS_B
COMP_ALIAS = CORE.COMP_ALIAS
FORMATION_ALIAS = CORE.FORMATION_ALIAS
QuotaExhausted = CORE.QuotaExhausted


def _cfg() -> CORE.GenerationConfig:
    return CORE.GenerationConfig(
        name="sonnet46", gen=V46, cache_dir=CACHE_DIR,
        manifest=G46.build_or_load_manifest(), golden_ledger=G46.load_ledger(),
        controls_path=CONTROLS_PATH, repeat_path=REPEAT_PATH, counter_path=COUNTER_PATH)


def run_controls(fixtures: list[str] | None = None, n_fixtures: int = 8, k: int = 3,
                 persist: bool = True) -> dict:
    return CORE.run_controls(_cfg(), fixtures=fixtures, n_fixtures=n_fixtures, k=k,
                             persist=persist)


def run_counter_evidence(k: int = 1, persist: bool = True) -> dict:
    return CORE.run_counter_evidence(_cfg(), k=k, persist=persist)
