"""Sonnet 4.5 V3 mechanism eligibility — V3_SONNET45_ELIGIBILITY.

Thin generation wiring only. Every threshold, class ladder, gate rule and the fail-closed
surrogate rule live in `eligibility_v3_core`, shared verbatim with the 4.6 arm, so neither
arm can be judged by a bar the other was not. Nothing here is 4.5-specific science.

Writes only under the 4.5 namespace (out/hardening_v3/). NEVER touches out/v3_sonnet46/.

Offline and free: per-mechanism sensitivity is recomputed from the already-paid 4.5 response
cache. This module makes zero Bedrock calls.
"""
from __future__ import annotations
import json
import os

from src.research.llm_matchup.hardening import controls_v3_sonnet45 as C45
from src.research.llm_matchup.hardening import eligibility_v3_core as ECORE
from src.research.llm_matchup.hardening import golden_manifest as GM
from src.research.llm_matchup.hardening import versions_v3 as V3

OUT = C45.OUT
ELIG_JSON = os.path.join(OUT, "golden_v3_sonnet45_eligibility.json")
ELIG_CSV = os.path.join(OUT, "golden_v3_sonnet45_eligibility.csv")
SENS_JSON = os.path.join(OUT, "golden_v3_sonnet45_mechanism_sensitivity.json")

GATE_REJECTABLE_CLASSES = ECORE.GATE_REJECTABLE_CLASSES


def _cfg() -> ECORE.EligibilityConfig:
    manifest = GM.load_manifest()
    if manifest is None:
        raise RuntimeError("frozen Sonnet 4.5 fixture manifest not found; refusing to judge "
                           "eligibility against an invented fixture selection")
    return ECORE.EligibilityConfig(
        name="sonnet45", gen=V3, cache_dir=C45.CACHE_DIR, manifest=manifest,
        controls_path=C45.CONTROLS_PATH, repeat_path=C45.REPEAT_PATH,
        out_dir=OUT, elig_json=ELIG_JSON, elig_csv=ELIG_CSV, sens_json=SENS_JSON,
        gen_label="4.5",
        coexists_with="V3_SONNET46_ELIGIBILITY (separate artifact, NOT modified)")


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
