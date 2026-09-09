"""Calibration & efficiency experiment (EVALUATION ONLY).

Two independent experiments, never combined until each is evaluated alone:

- Experiment A: does xG / shots signal (and the PROVIDER of it) measurably help
  the markets the champion predicts?
- Experiment B: does a signed home/away dependence correction on the corners
  total distribution improve calibration and proper scores over the champion's
  independence convolution?

This package NEVER modifies the champion engine and is NOT wired into production.
It reuses the champion's own side-marginal model and walk-forward, inserting a
dependence layer only at the point where the champion convolves the two side
PMFs. The correct outcome may be KEEP_BASELINE or INSUFFICIENT_EVIDENCE.
"""

from __future__ import annotations

__all__ = []
