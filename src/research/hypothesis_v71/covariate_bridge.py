"""Thin reuse shim over the frozen V7 covariate vocabulary (`v71_covariate_bridge_v1`).

V7's covariate schema was audited and frozen for the Control-B closure; V7.1 reuses its metric
grouping and banding rather than inventing a parallel vocabulary, and adds the one axis V7
could not have: the size of a family's ADMISSIBLE COMPETITION SET, which only becomes a
matching covariate once restricted universes exist.
"""
from __future__ import annotations

from src.research.hypothesis_v7 import covariates as V7C

BRIDGE_VERSION = "v71_covariate_bridge_v1"

MATCHING_COVARIATES = tuple(V7C.MATCHING_COVARIATES) + (
    # Without this, a control family drawn on a fully-covered metric would be matched against
    # a treated family restricted to four competitions -- exactly the measurability-opportunity
    # imbalance the Control-B design forbids.
    "n_admissible_competitions",
)

DESCRIPTIVE_ONLY_COVARIATES = dict(V7C.DESCRIPTIVE_ONLY_COVARIATES)


def metric_group(targets):
    return V7C.metric_group(list(targets or []))


def version_stamp() -> dict:
    return {"bridge_version": BRIDGE_VERSION,
            "source": V7C.COVARIATES_VERSION,
            "matching_covariates": list(MATCHING_COVARIATES),
            "added_in_v7_1": ["n_admissible_competitions"],
            "rationale": ("restricted universes make measurability OPPORTUNITY vary by "
                          "family; matching must condition on it or the comparison inherits "
                          "the imbalance")}
