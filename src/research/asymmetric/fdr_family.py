"""Fresh FDR family construction for the Asymmetric Matchup Engine.

Responsibility:
    Build a fresh multiple-testing family (via the reused ``ResearchFamilyBuilder``)
    whose hypothesis count equals the number of target x direction x league
    models tested, with a deterministic ``family_id`` derived only from this
    engine's run identity, dataset version, and model family. The family is
    fresh and is *never* inherited from any prior effort (Requirements 8.8,
    8.10, 13.3).

Isolation (Req 8.10, 13.3):
    This module imports ONLY from ``src.research.fdr.*`` (the reused, frozen
    family builder) and the Python standard library / this package. It reads
    nothing from any prior-effort ledger, family, or result. It also uses a
    dedicated, namespaced ``market_type`` / ``research_run_id`` scheme
    (``asymmetric_matchup_engine:...``) so a family built here can never collide
    with a Pilot C / Pipeline A / multisrc / samegame family, even by accident.

Design notes:
    * ``family_id`` determinism is inherited directly from
      ``ResearchFamilyBuilder.build``: the id is the sha256 of the canonical
      JSON of ``{market_type, dataset_version, research_run_id,
      candidate_generation_config, model_family}``. To satisfy Req 8.10 / 13.3
      ("family_id is a deterministic function of ONLY this engine's run
      identity, dataset version, and model family") we hold
      ``candidate_generation_config`` fixed to a single engine-owned constant so
      the *only* varying inputs to the id are the run identity, dataset version,
      and model family. ``hypothesis_count`` deliberately does NOT feed the id
      (a family keeps its identity whether or not a cell is skipped), matching
      the reused builder's contract.
    * The family is constructed FRESH on every call; nothing is read from disk
      or from a prior-effort ledger.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Optional

from src.research.fdr.family import ResearchFamily, ResearchFamilyBuilder

# --------------------------------------------------------------------------- #
# Engine-owned identity constants.
#
# The market_type is namespaced to this engine so the resulting family_id can
# never collide with a prior-effort family (Pilot C / Pipeline A / multisrc /
# samegame), which use their own market_type / research_run_id values.
# --------------------------------------------------------------------------- #

#: Namespaced market type for every family this engine constructs. Distinct from
#: any prior-effort market string.
ASYMMETRIC_MARKET_TYPE: str = "asymmetric_matchup_engine:per_side_asymmetry"

#: Default model family label for the engine's directional count models.
DEFAULT_MODEL_FAMILY: str = "asymmetric_matchup_engine"

#: Fixed candidate-generation descriptor. Held CONSTANT on purpose so the
#: family_id varies with ONLY run identity, dataset version, and model family
#: (Req 8.10, 13.3). The grid axes (targets/directions/leagues) drive the
#: hypothesis COUNT, not the family identity.
_CANDIDATE_GENERATION_CONFIG: str = "asymmetric_matchup_engine:target_x_direction_x_league_grid"


def count_family_size(
    targets: Sequence[object],
    directions: Sequence[object],
    leagues: Sequence[object],
) -> int:
    """Return the full target x direction x league grid size.

    This is the number of models tested when every grid cell is exercised
    (Req 8.8). When some cells are skipped, pass the actual tested-cell count
    to :func:`build_asymmetric_family` via ``tested_cell_count`` instead.

    Args:
        targets: The per-side targets tested (e.g. corners, cards, goals, sot).
        directions: The interaction directions tested (e.g. A, B).
        leagues: The leagues tested (e.g. Championship, EPL, ...).

    Returns:
        ``len(targets) * len(directions) * len(leagues)``.
    """
    return len(targets) * len(directions) * len(leagues)


def build_asymmetric_family(
    targets: Sequence[object],
    directions: Sequence[object],
    leagues: Sequence[object],
    dataset_version: str,
    research_run_id: str,
    model_family: str = DEFAULT_MODEL_FAMILY,
    tested_cell_count: Optional[int] = None,
    description: str = "",
) -> ResearchFamily:
    """Build a FRESH FDR family for the Asymmetric Matchup Engine.

    Wraps :meth:`ResearchFamilyBuilder.build` to construct a brand-new
    multiple-testing family whose ``hypothesis_count`` equals the number of
    target x direction x league models tested (Req 8.8), and whose
    ``family_id`` is a deterministic function of ONLY this engine's run identity
    (``research_run_id``), ``dataset_version``, and ``model_family``
    (Req 8.10, 13.3). No prior-effort family is inherited: the family is built
    from scratch on every call and never read from a ledger.

    ``hypothesis_count`` is, by default, the full grid size
    ``len(targets) * len(directions) * len(leagues)``. If some grid cells are
    skipped (e.g. an insufficient-sample league-target), pass
    ``tested_cell_count`` with the actual count of models tested; that value is
    used verbatim as ``hypothesis_count``.

    Args:
        targets: The per-side targets tested.
        directions: The interaction directions tested.
        leagues: The leagues tested.
        dataset_version: The engine's dataset version (feeds ``family_id``).
        research_run_id: This engine's run identity (feeds ``family_id``).
        model_family: Model family label (feeds ``family_id``). Defaults to
            ``"asymmetric_matchup_engine"``.
        tested_cell_count: Optional explicit count of models actually tested,
            used when some grid cells are skipped. When ``None``, the full grid
            size is used.
        description: Optional human-readable description.

    Returns:
        A fresh :class:`ResearchFamily` with a deterministic ``family_id`` and a
        ``hypothesis_count`` reflecting the models tested.

    Raises:
        ValueError: If ``tested_cell_count`` is negative, or exceeds the full
            grid size (a skipped-cell count can only be <= the grid size).
    """
    grid_size = count_family_size(targets, directions, leagues)

    if tested_cell_count is None:
        hypothesis_count = grid_size
    else:
        if tested_cell_count < 0:
            raise ValueError(
                f"tested_cell_count must be non-negative, got {tested_cell_count}"
            )
        if tested_cell_count > grid_size:
            raise ValueError(
                f"tested_cell_count ({tested_cell_count}) cannot exceed the full "
                f"grid size ({grid_size})"
            )
        hypothesis_count = tested_cell_count

    return ResearchFamilyBuilder.build(
        market_type=ASYMMETRIC_MARKET_TYPE,
        dataset_version=dataset_version,
        research_run_id=research_run_id,
        candidate_generation_config=_CANDIDATE_GENERATION_CONFIG,
        model_family=model_family,
        hypothesis_count=hypothesis_count,
        description=description
        or (
            f"Fresh asymmetric-matchup-engine FDR family "
            f"(run={research_run_id}, dataset={dataset_version}, "
            f"models={hypothesis_count})"
        ),
    )
