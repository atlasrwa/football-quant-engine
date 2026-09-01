# Feature: asymmetric-matchup-engine, Property 13: Shuffle-null collapses to chance
"""Property 13: A shuffled feature->outcome mapping collapses to chance.

**Property 13: Shuffle-null collapses to chance** — for any dataset, permuting
the feature-to-outcome mapping yields an out-of-sample BSS within a small
tolerance of zero (chance), so the shuffle-null gate check passes only when no
leakage remains.

Validates: Requirements 6.6.

NOTE: ``hypothesis`` is not yet installed (added as a dev dependency in task
12.1). This is therefore a deterministic ``pytest`` test over synthetic datasets
with a known signal, plus a real-corpus check. When task 12.1 lands, convert to
``@given(...)`` with ``@settings(max_examples=100)`` over a strategy that
generates (feature, outcome) datasets with a controllable signal strength; the
assertions below map directly onto the per-example check.
"""

from __future__ import annotations

import math
import random

import pytest

from src.research.asymmetric.gates import (
    SHUFFLE_NULL_BSS_TOLERANCE,
    FeatureVerificationGate,
    _brier_skill_score,
    _fit_predict_logistic,
)
from src.research.data_source import ResearchMatch


def _fit_score(train_x, train_y, test_x, test_y):
    probs = _fit_predict_logistic(train_x, train_y, test_x)
    return _brier_skill_score(probs, test_y)


def test_shuffled_mapping_collapses_to_chance_synthetic():
    """A strong true signal has positive OOS BSS; shuffling destroys it."""
    rng = random.Random(1234)
    n = 600
    xs: list[float] = []
    ys: list[float] = []
    for _ in range(n):
        x = rng.gauss(0.0, 1.0)
        # Outcome strongly driven by the feature via a logistic link.
        p = 1.0 / (1.0 + math.exp(-(1.6 * x)))
        y = 1.0 if rng.random() < p else 0.0
        xs.append(x)
        ys.append(y)

    split = int(n * 0.6)
    tr_x, tr_y = xs[:split], ys[:split]
    te_x, te_y = xs[split:], ys[split:]

    true_bss = _fit_score(tr_x, tr_y, te_x, te_y)
    assert true_bss is not None and true_bss > 0.05, (
        f"true mapping should retain skill, got BSS={true_bss}"
    )

    # Shuffle the train outcomes: the feature now carries no information.
    # A single permutation can produce a small nonzero BSS by chance, so we
    # average over several permutations — the shuffle-null must centre at chance.
    shuffled_bsss = []
    for s in range(15):
        r = random.Random(1000 + s)
        shuffled = tr_y[:]
        r.shuffle(shuffled)
        b = _fit_score(tr_x, shuffled, te_x, te_y)
        if b is not None:
            shuffled_bsss.append(b)
    mean_shuffled = sum(shuffled_bsss) / len(shuffled_bsss)
    # Collapses to chance: mean is not materially positive.
    assert mean_shuffled <= SHUFFLE_NULL_BSS_TOLERANCE, (
        f"shuffled mapping should collapse to chance, got mean BSS={mean_shuffled}"
    )


def test_averaged_shuffles_center_near_zero():
    """Averaging many shuffles centres OOS BSS near zero (no residual skill)."""
    rng = random.Random(99)
    n = 500
    xs = [rng.gauss(0, 1) for _ in range(n)]
    ys = [
        1.0 if rng.random() < 1.0 / (1.0 + math.exp(-x)) else 0.0 for x in xs
    ]
    split = int(n * 0.6)
    tr_x, tr_y = xs[:split], ys[:split]
    te_x, te_y = xs[split:], ys[split:]

    bsss = []
    for s in range(30):
        r = random.Random(s)
        sh = tr_y[:]
        r.shuffle(sh)
        b = _fit_score(tr_x, sh, te_x, te_y)
        if b is not None:
            bsss.append(b)
    mean_bss = sum(bsss) / len(bsss)
    assert abs(mean_bss) <= 0.05, f"mean shuffled BSS should be ~0, got {mean_bss}"


# ---- Real-corpus gate check (kept small; skips if cache absent) ------------- #
def _load_rich_sample(n: int = 500):
    try:
        from src.research.asymmetric.corpus import RichCorpusLoader

        loaded = RichCorpusLoader().load()
    except Exception:
        return None, None
    if not loaded:
        return None, None
    matches = [lm.match for lm in loaded][:n]
    leagues = {lm.match.league_id: lm.league for lm in loaded}
    return matches, leagues


def test_shuffle_null_check_passes_on_real_corpus():
    """The gate's shuffle-null check passes on the real (non-leaky) corpus."""
    matches, leagues = _load_rich_sample()
    if not matches:
        pytest.skip("rich corpus cache not available")
    gate = FeatureVerificationGate()
    check = gate._check_shuffle_null(matches)
    assert check.name == "shuffle_null"
    assert check.metric is not None
    # Shuffled BSS must be within tolerance of zero (no leakage).
    assert check.passed is True, f"shuffle-null failed: {check.detail}"
    assert check.metric <= SHUFFLE_NULL_BSS_TOLERANCE
