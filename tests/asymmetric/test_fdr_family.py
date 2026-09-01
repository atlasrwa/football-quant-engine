# Feature: asymmetric-matchup-engine, Property 19: Fresh FDR family sizing
"""Property 19: Fresh FDR family sizing (task 9.8).

**Property 19: Fresh FDR family sizing** — the constructed family's
``hypothesis_count`` equals the number of target x direction x league models
actually tested; and ``family_id`` is a deterministic function of ONLY this
engine's run identity, dataset version, and model family:

  * same (run_id, dataset_version, model_family) -> same ``family_id``;
  * changing any one of those three -> a different ``family_id``;
  * changing unrelated things (the target/direction/league lists, the
    hypothesis count, the description) -> the SAME ``family_id``.

Validates: Requirements 8.8, 8.10, 13.3.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is therefore written as a deterministic ``pytest`` test that sweeps
a range of grid sizes and identity permutations, exercising the same invariants
a Hypothesis strategy would. When task 12.1 lands, convert the grid-size and
identity sweeps to ``@given(...)`` over ``(n_targets, n_directions, n_leagues)``
and over ``(run_id, dataset_version, model_family)`` with
``@settings(max_examples=100)`` — the per-example assertions map directly onto
the checks below.
"""

from __future__ import annotations

from src.research.asymmetric.fdr_family import (
    build_asymmetric_family,
    count_family_size,
)


def _grid(n_targets: int, n_directions: int, n_leagues: int):
    targets = tuple(f"target_{i}" for i in range(n_targets))
    directions = tuple(f"dir_{i}" for i in range(n_directions))
    leagues = tuple(f"league_{i}" for i in range(n_leagues))
    return targets, directions, leagues


# --- hypothesis_count == number of models tested (Req 8.8) -----------------


def test_hypothesis_count_equals_full_grid_size():
    """Sweep grid dimensions; hypothesis_count == product of the three axes."""
    for nt in range(1, 6):
        for nd in range(1, 4):
            for nl in range(1, 6):
                targets, directions, leagues = _grid(nt, nd, nl)
                family = build_asymmetric_family(
                    targets=targets,
                    directions=directions,
                    leagues=leagues,
                    dataset_version="ds-v1",
                    research_run_id="run-1",
                )
                assert family.hypothesis_count == nt * nd * nl
                assert family.hypothesis_count == count_family_size(
                    targets, directions, leagues
                )


def test_hypothesis_count_honours_explicit_tested_cell_count():
    """When some cells are skipped, the tested-cell count is used verbatim."""
    targets, directions, leagues = _grid(4, 2, 4)  # full grid = 32
    for tested in (0, 1, 15, 31, 32):
        family = build_asymmetric_family(
            targets=targets,
            directions=directions,
            leagues=leagues,
            dataset_version="ds-v1",
            research_run_id="run-1",
            tested_cell_count=tested,
        )
        assert family.hypothesis_count == tested


def test_tested_cell_count_out_of_range_rejected():
    """A tested-cell count above the grid size or below zero is rejected."""
    targets, directions, leagues = _grid(4, 2, 4)  # full grid = 32
    for bad in (-1, 33, 100):
        try:
            build_asymmetric_family(
                targets=targets,
                directions=directions,
                leagues=leagues,
                dataset_version="ds-v1",
                research_run_id="run-1",
                tested_cell_count=bad,
            )
        except ValueError:
            pass
        else:  # pragma: no cover - defensive
            raise AssertionError(f"expected ValueError for tested_cell_count={bad}")


# --- family_id determinism over the identity triple (Req 8.10, 13.3) -------


def test_same_identity_gives_same_family_id():
    """Identical (run_id, dataset_version, model_family) -> identical id."""
    targets, directions, leagues = _grid(4, 2, 4)
    a = build_asymmetric_family(
        targets, directions, leagues,
        dataset_version="ds-v1", research_run_id="run-1",
        model_family="asymmetric_matchup_engine",
    )
    b = build_asymmetric_family(
        targets, directions, leagues,
        dataset_version="ds-v1", research_run_id="run-1",
        model_family="asymmetric_matchup_engine",
    )
    assert a.family_id == b.family_id


def test_changing_run_id_changes_family_id():
    targets, directions, leagues = _grid(4, 2, 4)
    base = build_asymmetric_family(
        targets, directions, leagues,
        dataset_version="ds-v1", research_run_id="run-1",
    )
    for other_run in ("run-2", "run-1 ", "RUN-1", "run-10"):
        other = build_asymmetric_family(
            targets, directions, leagues,
            dataset_version="ds-v1", research_run_id=other_run,
        )
        assert other.family_id != base.family_id, other_run


def test_changing_dataset_version_changes_family_id():
    targets, directions, leagues = _grid(4, 2, 4)
    base = build_asymmetric_family(
        targets, directions, leagues,
        dataset_version="ds-v1", research_run_id="run-1",
    )
    for other_ds in ("ds-v2", "ds-v1.0", "DS-V1"):
        other = build_asymmetric_family(
            targets, directions, leagues,
            dataset_version=other_ds, research_run_id="run-1",
        )
        assert other.family_id != base.family_id, other_ds


def test_changing_model_family_changes_family_id():
    targets, directions, leagues = _grid(4, 2, 4)
    base = build_asymmetric_family(
        targets, directions, leagues,
        dataset_version="ds-v1", research_run_id="run-1",
        model_family="asymmetric_matchup_engine",
    )
    other = build_asymmetric_family(
        targets, directions, leagues,
        dataset_version="ds-v1", research_run_id="run-1",
        model_family="asymmetric_matchup_engine_nb",
    )
    assert other.family_id != base.family_id


# --- family_id ignores everything else (Req 8.10, 13.3) --------------------


def test_family_id_independent_of_grid_and_count_and_description():
    """Changing the grid lists, hypothesis count, or description must NOT
    change the family id — the id depends only on the identity triple."""
    base = build_asymmetric_family(
        *_grid(4, 2, 4),
        dataset_version="ds-v1", research_run_id="run-1",
        description="base description",
    )

    # Different grid shape (hence different hypothesis_count) -> same id.
    different_grid = build_asymmetric_family(
        *_grid(2, 1, 3),
        dataset_version="ds-v1", research_run_id="run-1",
        description="totally different description",
    )
    assert different_grid.family_id == base.family_id
    assert different_grid.hypothesis_count != base.hypothesis_count

    # Explicit tested-cell count (skipped cells) -> same id, different count.
    skipped = build_asymmetric_family(
        *_grid(4, 2, 4),
        dataset_version="ds-v1", research_run_id="run-1",
        tested_cell_count=17,
    )
    assert skipped.family_id == base.family_id
    assert skipped.hypothesis_count == 17


def test_family_id_is_stable_across_calls():
    """Determinism: rebuilding with identical identity yields a stable id."""
    ids = {
        build_asymmetric_family(
            *_grid(4, 2, 4),
            dataset_version="ds-fixed", research_run_id="run-fixed",
        ).family_id
        for _ in range(20)
    }
    assert len(ids) == 1
