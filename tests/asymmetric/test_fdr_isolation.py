"""Integration test: fresh-family isolation from prior efforts (task 9.9).

Two isolation guarantees are asserted here (Requirements 8.10, 13.3):

1. **Disjoint identity.** A family constructed by ``build_asymmetric_family``
   has a ``family_id`` that differs from any prior-effort family (Pilot C,
   Pipeline A, multisrc, samegame) constructed via the SAME reused
   ``ResearchFamilyBuilder`` using those efforts' own identities. Because the
   engine namespaces its ``market_type`` and holds its candidate-generation
   descriptor constant, no accidental collision is possible even when a prior
   effort happens to share a dataset version, run id, or model family.

2. **No prior-effort imports.** ``src/research/asymmetric/fdr_family.py`` imports
   ONLY from ``src.research.fdr.*`` (the reused frozen family builder), the
   Python standard library, and this package. It reads nothing from any
   prior-effort script/module. This is verified by statically scanning the
   module's import statements.

Requirements: 8.10, 13.3.
"""

from __future__ import annotations

import ast
from pathlib import Path

from src.research.asymmetric.fdr_family import (
    ASYMMETRIC_MARKET_TYPE,
    build_asymmetric_family,
)
from src.research.fdr.family import ResearchFamilyBuilder

_FDR_FAMILY_PATH = (
    Path(__file__).resolve().parents[2]
    / "src" / "research" / "asymmetric" / "fdr_family.py"
)

# Representative prior-effort family identities. Each prior effort owns its own
# market_type / research_run_id / model_family. We build them with the SAME
# reused builder to prove the asymmetric family stays disjoint from all of them.
_PRIOR_EFFORT_FAMILIES = [
    {
        "market_type": "pilot_c:corners_over_under",
        "dataset_version": "ds-v1",
        "research_run_id": "pilotC_run_2024",
        "candidate_generation_config": "pilot_c:threshold_grid",
        "model_family": "logistic",
    },
    {
        "market_type": "pipeline_a:goals_totals",
        "dataset_version": "ds-v1",
        "research_run_id": "pipelineA_run_2024",
        "candidate_generation_config": "pipeline_a:auto",
        "model_family": "poisson",
    },
    {
        "market_type": "multisrc:cards",
        "dataset_version": "ds-v1",
        "research_run_id": "multisrc_run_2024",
        "candidate_generation_config": "multisrc:grid",
        "model_family": "negative_binomial",
    },
    {
        "market_type": "samegame:parlay",
        "dataset_version": "ds-v1",
        "research_run_id": "samegame_run_2024",
        "candidate_generation_config": "samegame:combo",
        "model_family": "logistic",
    },
]


def _asymmetric_family():
    return build_asymmetric_family(
        targets=("corners", "cards", "goals", "sot"),
        directions=("A", "B"),
        leagues=("Championship", "EPL", "Ligue2", "LaLiga2"),
        dataset_version="ds-v1",
        research_run_id="asym_run_2024",
    )


def test_asymmetric_family_disjoint_from_prior_efforts():
    """The asymmetric family_id differs from every prior-effort family_id."""
    asym = _asymmetric_family()
    prior_ids = {
        ResearchFamilyBuilder.build(**spec).family_id
        for spec in _PRIOR_EFFORT_FAMILIES
    }
    assert asym.family_id not in prior_ids
    assert asym.market_type == ASYMMETRIC_MARKET_TYPE
    # The engine's namespaced market_type is not any prior effort's market_type.
    assert asym.market_type not in {s["market_type"] for s in _PRIOR_EFFORT_FAMILIES}


def test_disjoint_even_when_prior_effort_shares_identity_fields():
    """Even if a prior effort shares the dataset version, run id, and model
    family, the engine's namespaced market_type / candidate config keeps the
    family_id disjoint — no accidental collision is possible."""
    asym = _asymmetric_family()
    # A prior effort that deliberately mimics the asymmetric identity triple but
    # keeps its own (prior-effort) market_type and candidate config.
    colliding_attempt = ResearchFamilyBuilder.build(
        market_type="pilot_c:corners_over_under",
        dataset_version="ds-v1",
        research_run_id="asym_run_2024",
        candidate_generation_config="pilot_c:threshold_grid",
        model_family="asymmetric_matchup_engine",
    )
    assert asym.family_id != colliding_attempt.family_id


def test_fdr_family_imports_no_prior_effort_modules():
    """Static scan: fdr_family.py imports only src.research.fdr.*, stdlib, and
    this package — never a prior-effort script/module."""
    source = _FDR_FAMILY_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported_modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # Relative import within this package — allowed.
                continue
            if node.module:
                imported_modules.append(node.module)

    # Allowed: standard library / typing / this package's own fdr reuse.
    allowed_prefixes = (
        "src.research.fdr",       # the reused frozen family builder
        "src.research.asymmetric",  # this package
        "collections",
        "typing",
        "hashlib",
        "json",
        "dataclasses",
        "__future__",
    )
    # Forbidden substrings identifying prior efforts.
    forbidden_substrings = (
        "pilot", "pipeline_a", "pipelinea", "multisrc",
        "samegame", "same_game", "ledger", "forward",
    )

    for mod in imported_modules:
        lowered = mod.lower()
        assert not any(bad in lowered for bad in forbidden_substrings), (
            f"fdr_family.py imports a prior-effort module: {mod}"
        )
        # Any src.* import must be from the allowed set.
        if mod.startswith("src."):
            assert mod.startswith(("src.research.fdr", "src.research.asymmetric")), (
                f"fdr_family.py imports an unexpected src module: {mod}"
            )

    # It MUST import from src.research.fdr (the reused builder).
    assert any(m.startswith("src.research.fdr") for m in imported_modules), (
        "fdr_family.py should reuse src.research.fdr.family.ResearchFamilyBuilder"
    )
