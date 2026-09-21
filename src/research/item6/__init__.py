"""ITEM 6 — Novel Hypothesis Discovery and Incremental Value.

Deterministic, zero-spend research apparatus for testing whether an LLM, given a
redesigned generation instrument, can discover *novel, grounded, falsifiable*
football hypothesis FAMILIES that the deterministic baseline enumeration does not
naturally produce (Stage 1), and — only if Stage 1 passes its frozen gate —
whether those families add out-of-sample predictive information (Stage 2).

GOVERNING PRINCIPLE (enforced structurally, never by convention alone):
    The LLM is NOT the football predictor. It never emits p_model, probabilities,
    effect sizes, odds, EV, edge, stakes, or latent matchup scores. Its only role
    is to DISCOVER WHAT THE DETERMINISTIC ENGINE SHOULD MEASURE. All estimation,
    support counting, similarity, effect estimation, calibration and p_model remain
    owned by deterministic code.

No module in this package performs a paid model call. Every module is pure/
deterministic and testable offline.

Versions are frozen strings so downstream freeze manifests can pin them.
"""
from __future__ import annotations

ITEM6_PACKAGE_VERSION = "item6_v1"

__all__ = ["ITEM6_PACKAGE_VERSION"]
