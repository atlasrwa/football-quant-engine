"""Fundamental-vs-market disagreement buckets and diagnostics.

We bucket forecasts by how far the fundamental sits from the market (in
probability points) and measure outcomes / CLV per bucket, to learn whether
disagreement itself contains information. Thresholds are FIXED here (declared
constants), never optimized on the evaluation set.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Optional, Sequence

import numpy as np


class DisagreementBucket(str, Enum):
    MUCH_LOWER = "model_much_lower"
    MODERATELY_LOWER = "model_moderately_lower"
    AGREE = "agree"
    MODERATELY_HIGHER = "model_moderately_higher"
    MUCH_HIGHER = "model_much_higher"


#: Fixed probability-point thresholds (NOT tuned on eval data).
MODERATE_PP = 0.02
MUCH_PP = 0.05


def bucket_for(fundamental_prob: float, market_prob: float) -> DisagreementBucket:
    """Bucket by signed probability-point gap (fundamental - market)."""
    gap = fundamental_prob - market_prob
    if gap <= -MUCH_PP:
        return DisagreementBucket.MUCH_LOWER
    if gap <= -MODERATE_PP:
        return DisagreementBucket.MODERATELY_LOWER
    if gap < MODERATE_PP:
        return DisagreementBucket.AGREE
    if gap < MUCH_PP:
        return DisagreementBucket.MODERATELY_HIGHER
    return DisagreementBucket.MUCH_HIGHER


@dataclass(frozen=True)
class BucketDiagnostics:
    """Outcome / CLV diagnostics for one disagreement bucket."""

    bucket: str
    n: int
    mean_fundamental: float
    mean_market: float
    outcome_rate: Optional[float]
    #: Mean signed later-market move (later_market - market) in prob points,
    #: when later-market probabilities are supplied. Positive means the market
    #: moved toward the fundamental's direction of disagreement.
    mean_clv_pp: Optional[float]

    def to_dict(self) -> dict[str, object]:
        return {
            "bucket": self.bucket,
            "n": self.n,
            "mean_fundamental": self.mean_fundamental,
            "mean_market": self.mean_market,
            "outcome_rate": self.outcome_rate,
            "mean_clv_pp": self.mean_clv_pp,
        }


@dataclass(frozen=True)
class DisagreementRow:
    fundamental_prob: float
    market_prob: float
    outcome: Optional[bool] = None
    later_market_prob: Optional[float] = None


def bucket_diagnostics(rows: Sequence[DisagreementRow]) -> list[BucketDiagnostics]:
    """Group rows into fixed buckets and compute per-bucket diagnostics."""
    by_bucket: dict[DisagreementBucket, list[DisagreementRow]] = {b: [] for b in DisagreementBucket}
    for r in rows:
        by_bucket[bucket_for(r.fundamental_prob, r.market_prob)].append(r)

    out: list[BucketDiagnostics] = []
    for bucket in DisagreementBucket:
        group = by_bucket[bucket]
        if not group:
            out.append(BucketDiagnostics(bucket.value, 0, float("nan"), float("nan"), None, None))
            continue
        f = np.array([g.fundamental_prob for g in group])
        m = np.array([g.market_prob for g in group])
        outs = [g.outcome for g in group if g.outcome is not None]
        outcome_rate = float(np.mean([1.0 if o else 0.0 for o in outs])) if outs else None
        clvs = [
            (g.later_market_prob - g.market_prob)
            for g in group
            if g.later_market_prob is not None
        ]
        mean_clv = float(np.mean(clvs)) if clvs else None
        out.append(
            BucketDiagnostics(
                bucket=bucket.value, n=len(group), mean_fundamental=float(f.mean()),
                mean_market=float(m.mean()), outcome_rate=outcome_rate, mean_clv_pp=mean_clv,
            )
        )
    return out
