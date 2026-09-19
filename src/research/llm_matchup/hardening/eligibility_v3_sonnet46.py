"""Sonnet 4.6 V3 mechanism eligibility — V3_SONNET46_ELIGIBILITY.

Thin generation wiring only. The decision logic that used to live here is now
`eligibility_v3_core`, shared verbatim with the 4.5 arm so neither arm can be judged by a bar
the other was not — the same extraction `controls_v3_core` performed for the control battery.
The refactor was proven output-identical to the frozen 4.6 eligibility + mechanism-sensitivity
artifacts before it was adopted (tests/research/test_eligibility_v3_core.py).

Coexists with, and NEVER modifies, the 4.5 arm's eligibility result: a mechanism may be
eligible on one model generation and rejected on another; that is the point of running two.
Writes only under out/v3_sonnet46/.

Thresholds and gate semantics come from `eligibility` unchanged. The fail-closed
PENDING_SURROGATE rule (no V3 surrogate ladder was run for EITHER arm, so no V3 mechanism may
be called PHASE_C_ELIGIBLE) is defined in the core; see its docstring.

Offline and free: per-mechanism sensitivity is recomputed from the already-paid 4.6 response
cache. This module makes zero Bedrock calls.
"""
from __future__ import annotations
import json
import os

from src.research.llm_matchup.hardening import controls_v3_sonnet46 as C46
from src.research.llm_matchup.hardening import eligibility_v3_core as ECORE
from src.research.llm_matchup.hardening import golden_v3_sonnet46 as G46
from src.research.llm_matchup.hardening import versions_v3_sonnet46 as V46

OUT = G46.OUT
ELIG_JSON = os.path.join(OUT, "golden_v3_sonnet46_eligibility.json")
ELIG_CSV = os.path.join(OUT, "golden_v3_sonnet46_eligibility.csv")
SENS_JSON = os.path.join(OUT, "golden_v3_sonnet46_mechanism_sensitivity.json")

GATE_REJECTABLE_CLASSES = ECORE.GATE_REJECTABLE_CLASSES


def _cfg() -> ECORE.EligibilityConfig:
    return ECORE.EligibilityConfig(
        name="sonnet46", gen=V46, cache_dir=C46.CACHE_DIR,
        manifest=G46.build_or_load_manifest(),
        controls_path=C46.CONTROLS_PATH, repeat_path=C46.REPEAT_PATH,
        out_dir=OUT, elig_json=ELIG_JSON, elig_csv=ELIG_CSV, sens_json=SENS_JSON,
        gen_label="4.6",
        coexists_with="V3_SONNET45_ELIGIBILITY (separate artifact, NOT modified)")


def per_mechanism_sensitivity(k: int = 3, persist: bool = True) -> dict:
    return ECORE.per_mechanism_sensitivity(_cfg(), k=k, persist=persist)


def collect_signals(sens: dict | None = None) -> dict:
    return ECORE.collect_signals(_cfg(), sens)


def classify(sig: dict) -> list[dict]:
    return ECORE.classify(_cfg(), sig)


def identity_gate() -> dict:
    return ECORE.identity_gate(_cfg())


def apply_identity_gate(rows: list[dict], gate: dict) -> list[dict]:
    return ECORE.apply_identity_gate(rows, gate)


def run(k: int = 3, persist: bool = True) -> dict:
    return ECORE.run(_cfg(), k=k, persist=persist)


if __name__ == "__main__":
    print(json.dumps(run()["class_counts"], indent=2))
