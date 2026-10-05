# QFE Prospective Execution Protocol V1

Protocol hash: bf5b1ba2b15be8db74618754028a34c9568dc281e2fb26a9d0e174552681ca4c

Status: **FROZEN BEFORE A NEW PROSPECTIVE COHORT OR PREDICTIONS**

This protocol binds the current Layer 4 V3 calibrated p_model to Layer 5 V1.2 and defines the only allowed path for genuine prospective predictions.

Key rules:
- cohort membership is frozen before each fixture's T-6h cutoff;
- the target fixture carries identity/kickoff only, never its own outcome or post-match statistics;
- model state uses only football evidence available by the T-6h cutoff under the 6h result-availability embargo;
- the Sep-14 canonical corpus may not be used alone for later fixtures: an immutable incremental provider-history snapshot is required;
- market prices never enter p_model;
- predictions are immutable and content-hashed;
- any material defect after cohort freeze aborts the cohort version rather than mutating its predictions.

The writer must first pass historical counterfactual replay against frozen Layer 4 probabilities before live cohort selection begins.
