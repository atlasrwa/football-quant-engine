"""Paired time-block uncertainty for QFE component comparisons."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np

WEEK_SECONDS = 7 * 24 * 3600


@dataclass(frozen=True, slots=True)
class PairedBlockResult:
    metric: str
    n_pairs: int
    n_time_blocks: int
    mean_improvement: float
    ci_low: float
    ci_high: float
    bootstrap_probability_positive: float
    block_seconds: int
    bootstrap_replicates: int
    seed: int

    def to_dict(self):
        return {
            "metric": self.metric,
            "n_pairs": self.n_pairs,
            "n_time_blocks": self.n_time_blocks,
            "mean_improvement": self.mean_improvement,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "bootstrap_probability_positive": self.bootstrap_probability_positive,
            "block_seconds": self.block_seconds,
            "bootstrap_replicates": self.bootstrap_replicates,
            "seed": self.seed,
        }


def paired_block_bootstrap(
    rows: Iterable[tuple[int, float, float]],
    *,
    metric: str,
    block_seconds: int = WEEK_SECONDS,
    bootstrap_replicates: int = 4000,
    seed: int = 1729,
) -> PairedBlockResult:
    """Bootstrap baseline-loss minus candidate-loss using whole time blocks."""
    data=[(int(ts),float(base),float(cand)) for ts,base,cand in rows]
    if len(data)<30:
        raise ValueError("at least 30 paired rows required")
    if block_seconds<=0 or bootstrap_replicates<100:
        raise ValueError("invalid block-bootstrap configuration")
    blocks: dict[int,list[float]]={}
    for ts,base,cand in data:
        block=ts//block_seconds
        blocks.setdefault(block,[]).append(base-cand)
    ordered=[np.asarray(blocks[k],float) for k in sorted(blocks)]
    if len(ordered)<4:
        raise ValueError("at least four time blocks required")
    observed=float(np.mean(np.concatenate(ordered)))
    rng=np.random.default_rng(seed)
    estimates=np.empty(bootstrap_replicates,float)
    n=len(ordered)
    for i in range(bootstrap_replicates):
        sample_idx=rng.integers(0,n,size=n)
        sample=np.concatenate([ordered[j] for j in sample_idx])
        estimates[i]=float(np.mean(sample))
    lo,hi=np.quantile(estimates,[0.025,0.975])
    return PairedBlockResult(
        metric=metric,
        n_pairs=len(data),
        n_time_blocks=n,
        mean_improvement=observed,
        ci_low=float(lo),
        ci_high=float(hi),
        bootstrap_probability_positive=float(np.mean(estimates>0.0)),
        block_seconds=block_seconds,
        bootstrap_replicates=bootstrap_replicates,
        seed=seed,
    )
