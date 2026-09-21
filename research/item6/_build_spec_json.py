"""Emit machine-readable JSON companions for the frozen Item-6 specs, straight from the code
modules (so JSON and code cannot drift). Reads no outcome, makes no paid call.
"""
from __future__ import annotations

import json

from src.research.item6 import (
    baseline_coverage as bc,
    formalizer as fz,
    provider_vocab as pv,
    quality_protocol as qp,
    registry as rg,
    schema as sc,
    stage1_gate as sg,
    stage1_metrics as sm,
    control_generator as cgd,
    harness as hz,
)

ROOT = "/home/ubuntu/research/item6"


def main():
    coverage = {
        "version": bc.BASELINE_COVERAGE_VERSION,
        "target_metrics": list(bc.BASELINE_TARGET_METRICS),
        "subjects": list(bc.BASELINE_SUBJECTS),
        "perspectives": list(bc.BASELINE_PERSPECTIVES),
        "comparators": list(bc.BASELINE_COMPARATORS),
        "windows": list(bc.BASELINE_WINDOWS),
        "profile_axes": list(bc.BASELINE_PROFILE_AXES),
        "condition_dimensions": list(bc.BASELINE_CONDITION_DIMENSIONS),
        "covered_families": list(bc.BASELINE_COVERED_FAMILIES),
        "unsupported_structures": list(bc.BASELINE_UNSUPPORTED_STRUCTURES),
        "research_family_labels": list(bc.BASELINE_RESEARCH_FAMILY_LABELS),
        "abstract_coverage_prose": bc.abstract_coverage_prose(),
        "version_stamp": bc.version_stamp(),
    }
    with open(f"{ROOT}/DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1.json", "w") as f:
        json.dump(coverage, f, indent=1, sort_keys=True)

    registry_schema = {
        "version": rg.NOVEL_FAMILY_REGISTRY_VERSION,
        "entry_fields": [
            "family_id", "family_signature", "semantic_description",
            "required_measurable_variables", "conditioning_dimensions",
            "temporal_resolution_requirement", "provider_requirements",
            "formalization_rule", "existing_grammar_supported",
            "required_additive_extension", "novelty_signals",
            "member_mechanism_ids", "n_members",
        ],
        "forbidden_predictive_keys": list(rg._FORBIDDEN_REGISTRY_KEYS),
        "additive_extensions": fz.SIGNAL_TO_EXTENSION,
        "version_stamp": rg.version_stamp(),
    }
    with open(f"{ROOT}/NOVEL_FAMILY_REGISTRY_SCHEMA_V1.json", "w") as f:
        json.dump(registry_schema, f, indent=1, sort_keys=True)

    version_stamps = {
        "baseline_coverage": bc.version_stamp(),
        "provider_vocab": pv.version_stamp(),
        "schema": sc.version_stamp(),
        "baseline_equivalence": __import__(
            "src.research.item6.baseline_equivalence", fromlist=["version_stamp"]).version_stamp(),
        "formalizer": fz.version_stamp(),
        "stage1_metrics": sm.version_stamp(),
        "stage1_gate": sg.version_stamp(),
        "control_gd": cgd.version_stamp(),
        "registry": rg.version_stamp(),
        "quality_protocol": qp.version_stamp(),
        "harness": hz.version_stamp(),
    }
    with open(f"{ROOT}/ITEM6_VERSION_STAMPS.json", "w") as f:
        json.dump(version_stamps, f, indent=1, sort_keys=True)

    print("[spec-json] wrote coverage spec, registry schema, version stamps")


if __name__ == "__main__":
    main()
