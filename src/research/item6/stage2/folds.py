"""ITEM 6 STAGE 2 walk-forward fold manifest (`item6_stage2_folds_v1`).

Strictly chronological expanding-window folds, frozen and hashed BEFORE any outcome is
evaluated. Both arms receive byte-identically the same folds and the same fixture set; that is
what makes the paired comparison legitimate.

FROZEN WINDOW POLICY
--------------------
  TRAIN_WINDOW_POLICY      EXPANDING -- everything strictly before the fold's test window.
  VALIDATION_WINDOW_POLICY NESTED INSIDE TRAIN. There is no separate chronological validation
                           block: hyperparameters and calibration are selected by an inner
                           expanding TimeSeriesSplit over the training block only. This keeps
                           the maximum amount of data in both training and testing while
                           guaranteeing no test-fold row informs any tuning decision.
  TEST_WINDOW_POLICY       The fold's contiguous chronological block, disjoint from all others.
  RETRAIN_FREQUENCY        Once per fold (refit from scratch on that fold's training block).
  MIN_TRAINING_HISTORY     The first MIN_TRAIN_FRAC of the MATCH SEQUENCE is never tested on.

MIN_TRAIN_FRAC = 0.20 IS CHOSEN BY A PRE-DECLARED RULE, NOT BY TASTE
--------------------------------------------------------------------
The primary endpoint's precision is governed by the NUMBER OF ISO-WEEK BOOTSTRAP BLOCKS, so a
larger test span is scientifically valuable. But the training block must still support M1's
larger design matrix (174 columns), or the augmented arm is starved and the comparison is biased
toward the null. The frozen rule is therefore:

    pick the SMALLEST min_train_frac whose MINIMUM per-fold training size is at least
    20x the M1 feature-universe size (174 x 20 = 3480 matches).

Measured on this corpus (chronology only, no outcome read): 0.15 -> 2925 (fails), 0.20 -> 3904
(passes, 95 blocks), 0.25 -> 4881 (passes but only 88 blocks). 0.20 is the smallest passing
value and is frozen. The rule, the candidate grid and the selected value are all fixed before
any outcome is observed; the sweep measured only fold sizes, week counts and dates.
  CALIBRATION_WINDOW       Inner training folds only (never the test block).

ELIGIBILITY IS OUTCOME-BLIND
----------------------------
A fixture enters a test block on chronology plus FEATURE SUFFICIENCY only (both teams have at
least MIN_CURRENT_SEASON_MATCHES completed current-season matches before kickoff, evaluated
against train-only history -- the champion's own gate). Label availability is NOT consulted
during design, so the manifest's counts are an UPPER BOUND on scorable predictions.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Sequence

FOLDS_VERSION = "item6_stage2_folds_v1"

N_FOLDS = 5
MIN_TRAIN_FRAC = 0.20
MIN_TRAIN_MATCHES = 400

TRAIN_WINDOW_POLICY = "EXPANDING_ALL_STRICTLY_BEFORE_TEST_WINDOW"
VALIDATION_WINDOW_POLICY = "NESTED_INNER_TIMESERIES_SPLIT_INSIDE_TRAINING_BLOCK"
TEST_WINDOW_POLICY = "CONTIGUOUS_DISJOINT_CHRONOLOGICAL_BLOCK_OF_EQUAL_MATCH_COUNT"
RETRAIN_FREQUENCY = "ONCE_PER_FOLD"
CALIBRATION_WINDOW = "INNER_TRAINING_FOLDS_ONLY"


@dataclass(frozen=True)
class Stage2Fold:
    fold_index: int
    train_start_unix: float
    train_end_unix: float      # exclusive; == test_start
    test_start_unix: float
    test_end_unix: float       # exclusive

    def to_dict(self) -> Dict[str, object]:
        return {
            "fold_index": self.fold_index,
            "train_start_unix": self.train_start_unix,
            "train_end_unix": self.train_end_unix,
            "test_start_unix": self.test_start_unix,
            "test_end_unix": self.test_end_unix,
        }


def make_folds(kickoffs: Sequence[float], *, n_folds: int = N_FOLDS,
               min_train_frac: float = MIN_TRAIN_FRAC) -> List[Stage2Fold]:
    """Expanding chronological folds with test blocks of EQUAL MATCH COUNT.

    The engine's existing `make_expanding_folds` cuts on the TIME axis. This corpus is very
    unevenly dense -- it thins out sharply before 2023 -- so equal time blocks put only ~135
    training matches in the first two folds and those folds yield no usable test fixtures at
    all, discarding 2 of 5 folds and nearly halving the bootstrap block count.

    Cutting on MATCH-COUNT quantiles instead keeps every fold usable and maximises the number of
    ISO-week bootstrap blocks (which is what the primary inference's precision depends on). It is
    equally strictly chronological -- boundaries are still kickoff timestamps, training is still
    everything before the test block, and no fold sees its own future. The choice is made on
    data density alone, before any outcome is observed.
    """
    if not kickoffs:
        return []
    ds = sorted(float(k) for k in kickoffs)
    n = len(ds)
    start_idx = int(n * min_train_frac)
    if start_idx >= n - 1:
        return []
    remaining = n - start_idx
    out: List[Stage2Fold] = []
    for i in range(n_folds):
        lo_i = start_idx + (remaining * i) // n_folds
        hi_i = start_idx + (remaining * (i + 1)) // n_folds
        if lo_i >= n:
            break
        ts = ds[lo_i]
        te = ds[hi_i] if hi_i < n else ds[-1] + 1.0
        if te <= ts:
            continue
        out.append(Stage2Fold(i, ds[0], ts, ts, te))
    return out


def build_fold_manifest(matches: Sequence[Dict], *, sufficiency_fn: Callable,
                        n_folds: int = N_FOLDS,
                        min_train_frac: float = MIN_TRAIN_FRAC) -> Dict[str, object]:
    """Immutable fold manifest: one row per (fixture, fold) test assignment.

    `sufficiency_fn(train_matches, match) -> bool` decides feature sufficiency using train-only
    history. No label is read.
    """
    from src.research.item6.stage2.evaluation import iso_week_block

    ms = sorted((m for m in matches if m.get("date_unix")), key=lambda m: m["date_unix"])
    folds = make_folds([m["date_unix"] for m in ms], n_folds=n_folds,
                       min_train_frac=min_train_frac)
    rows: List[Dict[str, object]] = []
    per_fold: List[Dict[str, object]] = []

    for fd in folds:
        train = [m for m in ms if m["date_unix"] < fd.test_start_unix]
        test = [m for m in ms if fd.test_start_unix <= m["date_unix"] < fd.test_end_unix]
        if len(train) < MIN_TRAIN_MATCHES or not test:
            per_fold.append({**fd.to_dict(), "n_train": len(train), "n_test_candidates": 0,
                             "skipped": True})
            continue
        eligible = [m for m in test if sufficiency_fn(train, m)]
        for m in eligible:
            rows.append({
                "fixture_key": f"{m.get('home_name')}|{m.get('away_name')}|"
                               f"{int(m['date_unix'])}",
                "kickoff_unix": float(m["date_unix"]),
                "competition_id": m.get("competition_id"),
                "iso_week_block": iso_week_block(m["date_unix"]),
                "fold": fd.fold_index,
                "train_cutoff_unix": fd.train_end_unix,
                "validation_cutoff_unix": fd.train_end_unix,   # nested inside train
                "designation": "TEST",
            })
        per_fold.append({**fd.to_dict(), "n_train": len(train),
                         "n_test_candidates": len(eligible), "skipped": False})

    rows.sort(key=lambda r: (int(r["fold"]), float(r["kickoff_unix"]), str(r["fixture_key"])))
    blocks = sorted({str(r["iso_week_block"]) for r in rows})
    manifest = {
        "folds_version": FOLDS_VERSION,
        "train_window_policy": TRAIN_WINDOW_POLICY,
        "validation_window_policy": VALIDATION_WINDOW_POLICY,
        "test_window_policy": TEST_WINDOW_POLICY,
        "retrain_frequency": RETRAIN_FREQUENCY,
        "min_training_history_fraction": min_train_frac,
        "min_training_matches": MIN_TRAIN_MATCHES,
        "calibration_window": CALIBRATION_WINDOW,
        "n_folds_requested": n_folds,
        "n_folds_usable": sum(1 for f in per_fold if not f["skipped"]),
        "n_oos_fixtures_candidate": len(rows),
        "n_bootstrap_blocks_iso_weeks": len(blocks),
        "label_availability_consulted": False,
        "counts_are_upper_bound_pending_label_availability": True,
        "folds": per_fold,
        "rows": rows,
        "identical_for_both_arms": True,
    }
    manifest["fold_manifest_sha256"] = hashlib.sha256(
        json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                   ensure_ascii=False).encode("utf-8")).hexdigest()
    return manifest


def assert_chronological(manifest: Dict) -> None:
    """Fail closed if any fold's ordering or disjointness is violated."""
    usable = [f for f in manifest["folds"] if not f["skipped"]]
    for f in usable:
        if not (f["train_start_unix"] <= f["train_end_unix"] == f["test_start_unix"]
                < f["test_end_unix"]):
            raise AssertionError(f"fold {f['fold_index']} ordering violated")
    for a, b in zip(usable, usable[1:]):
        if a["test_end_unix"] > b["test_start_unix"]:
            raise AssertionError("test blocks overlap")
    for r in manifest["rows"]:
        if not (r["kickoff_unix"] >= r["train_cutoff_unix"]):
            raise AssertionError("a test fixture precedes its own train cutoff")


def version_stamp() -> Dict[str, object]:
    return {"folds_version": FOLDS_VERSION, "n_folds": N_FOLDS,
            "chronological": True, "identical_for_both_arms": True,
            "label_availability_consulted": False, "reads_outcomes": False}
