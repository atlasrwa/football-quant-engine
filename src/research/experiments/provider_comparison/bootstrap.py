"""Paired moving-block bootstrap for metric differences (Phase 10).

Compares two arms on the SAME fixtures. For a chosen loss (Brier or log loss),
we align both arms' per-fixture losses by identical pair keys, order them
chronologically, and resample contiguous blocks (moving-block bootstrap) to
respect temporal dependence between consecutive fixtures. The statistic is the
paired mean loss difference (arm_a - arm_b); a negative value means arm_a has
lower loss (is better).

Reported per comparison: observed difference, bootstrap CI, the probability the
difference is in the observed direction, and N. Nothing here declares
significance thresholds; it reports uncertainty so the caller can judge.

Multiple comparisons: the caller evaluates several correlated lines/markets;
this module exposes the machinery to aggregate across lines (average paired
loss per fixture over lines) so correlated lines are not counted as independent
evidence. See paired_block_bootstrap(..., collapse_lines=True).
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable, Optional, Sequence

from src.research.experiments.provider_comparison.metrics import brier_losses, log_losses
from src.research.experiments.provider_comparison.walkforward import Prediction


@dataclass
class PairedBootstrapResult:
    metric: str
    arm_a: str
    arm_b: str
    n_pairs: int
    n_fixtures: int
    observed_diff: Optional[float]      # mean(loss_a - loss_b); <0 => a better
    ci_low: Optional[float]
    ci_high: Optional[float]
    prob_a_better: Optional[float]      # P(bootstrap diff < 0)
    block_len: int
    n_boot: int

    def to_dict(self) -> dict:
        def r(x):
            return None if x is None else round(x, 5)
        return {
            "metric": self.metric, "arm_a": self.arm_a, "arm_b": self.arm_b,
            "n_pairs": self.n_pairs, "n_fixtures": self.n_fixtures,
            "observed_diff_a_minus_b": r(self.observed_diff),
            "ci95_low": r(self.ci_low), "ci95_high": r(self.ci_high),
            "prob_a_better": r(self.prob_a_better),
            "block_len": self.block_len, "n_boot": self.n_boot,
        }


_LOSS_FNS: dict[str, Callable] = {"brier": brier_losses, "log_loss": log_losses}


def _aligned_fixture_losses(
    preds_a: list[Prediction], preds_b: list[Prediction], metric: str, *, collapse_lines: bool,
) -> tuple[list[int], list[float]]:
    """Return (ordered_fixture_keys, per-fixture paired loss diffs a-b).

    Aligns on identical pair keys (fixture, market, line). When collapse_lines
    is True, the per-fixture value is the mean loss-diff across that fixture's
    lines (so correlated lines within a fixture are one observation).
    """
    loss_fn = _LOSS_FNS[metric]
    a_by_key = {p.pair_key: p for p in preds_a}
    b_by_key = {p.pair_key: p for p in preds_b}
    common = sorted(set(a_by_key) & set(b_by_key),
                    key=lambda k: (a_by_key[k].kickoff_unix, k[0], k[2]))

    # Group by fixture (and kickoff) so blocks are over fixtures, not lines.
    from collections import defaultdict, OrderedDict
    per_fixture: "OrderedDict[int, list[float]]" = OrderedDict()
    fixture_kickoff: dict[int, int] = {}
    for k in common:
        pa, pb = a_by_key[k], b_by_key[k]
        la = loss_fn([pa.prob_over], [pa.outcome_over])[0]
        lb = loss_fn([pb.prob_over], [pb.outcome_over])[0]
        per_fixture.setdefault(pa.fixture_key, []).append(la - lb)
        fixture_kickoff[pa.fixture_key] = pa.kickoff_unix

    keys_sorted = sorted(per_fixture.keys(), key=lambda fk: fixture_kickoff[fk])
    if collapse_lines:
        diffs = [sum(per_fixture[fk]) / len(per_fixture[fk]) for fk in keys_sorted]
    else:
        # flatten but keep fixture-contiguity for blocks
        diffs = [d for fk in keys_sorted for d in per_fixture[fk]]
    return keys_sorted, diffs


def paired_block_bootstrap(
    preds_a: list[Prediction],
    preds_b: list[Prediction],
    *,
    arm_a: str,
    arm_b: str,
    metric: str = "brier",
    block_len: Optional[int] = None,
    n_boot: int = 2000,
    seed: int = 12345,
    collapse_lines: bool = True,
    ci: float = 0.95,
) -> PairedBootstrapResult:
    """Moving-block bootstrap of the paired mean loss difference (a - b)."""
    keys, diffs = _aligned_fixture_losses(preds_a, preds_b, metric, collapse_lines=collapse_lines)
    n = len(diffs)
    res = PairedBootstrapResult(
        metric=metric, arm_a=arm_a, arm_b=arm_b, n_pairs=n, n_fixtures=len(keys),
        observed_diff=None, ci_low=None, ci_high=None, prob_a_better=None,
        block_len=0, n_boot=n_boot,
    )
    if n == 0:
        return res
    observed = sum(diffs) / n
    res.observed_diff = observed
    if block_len is None:
        block_len = max(1, int(round(n ** 0.5)))  # ~sqrt(n) respects dependence
    res.block_len = block_len

    rng = random.Random(seed)
    n_blocks = (n + block_len - 1) // block_len
    boot_means: list[float] = []
    for _ in range(n_boot):
        sample: list[float] = []
        for _ in range(n_blocks):
            start = rng.randint(0, n - 1)
            # circular moving block
            for j in range(block_len):
                sample.append(diffs[(start + j) % n])
        sample = sample[:n]
        boot_means.append(sum(sample) / len(sample))
    boot_means.sort()
    lo_idx = int((1 - ci) / 2 * n_boot)
    hi_idx = int((1 + ci) / 2 * n_boot) - 1
    res.ci_low = boot_means[max(0, lo_idx)]
    res.ci_high = boot_means[min(n_boot - 1, hi_idx)]
    res.prob_a_better = sum(1 for m in boot_means if m < 0) / n_boot
    return res
