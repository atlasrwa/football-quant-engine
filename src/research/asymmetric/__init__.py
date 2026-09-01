"""Asymmetric Matchup Engine — per-side football matchup prediction.

This is a deliberately isolated, namespaced package that treats a fixture as an
asymmetric interaction between two continuous team profiles rather than as a
single aggregate total. For a fixture it builds, per side, an expectation of
what each team is expected to *produce* and to *concede* across corners, cards,
goals, and shots on target, deriving match-level outcomes from the per-side
predictions rather than modelling them directly.

Isolation (Requirements 13.2, 13.4):
    This package is fully separate from Prior_Efforts (Pilot C, Pipeline A,
    manual work, and flagged ledgers). It MUST NOT import from, inherit feature
    selections from, reuse multiple-testing families from, or depend on the
    results of any prior effort. It integrates with the existing engine only by
    reusing the general-purpose ``src/features/`` and ``src/research/`` building
    blocks named in the design's "Reused vs New Components" table, and it adds a
    single new CLI at ``scripts/asymmetric_analyze.py``.

The build/backtest path is strictly zero-API; only the on-demand Analysis_CLI
may make capped, reported live API requests.

This ``__init__`` intentionally performs no imports so that importing the
package has no side effects and cannot pull in any prior-effort module.
"""
