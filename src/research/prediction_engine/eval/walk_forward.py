"""Chronological expanding-window walk-forward OOS evaluation of the champion.

WHAT IT DOES
============
Wraps the champion's own ``fit_full`` / ``predict_one`` (the elastic-net logistic
stat-mixer that produces p_model for commitments) in an expanding-window,
strictly-chronological walk-forward and reports proper probabilistic metrics
(Brier, LogLoss, BSS, ECE, reliability, confidence ladder, preferred-side
accuracy) per market/line, per competition, and pooled.

LEAK-FREE BY CONSTRUCTION
=========================
For each fold the corpus is split at a chronological boundary:
  * train = matches whose kickoff finished strictly before the fold's test_start
  * test  = matches with test_start <= kickoff < test_end
The champion model is fit on the train slice only. Each test match is predicted
using a history built ONLY from matches strictly before test_start, so no
test-fold match can inform another test-fold match's rolling features, and no
future information enters an earlier fold. Hyperparameters are the frozen
CV-selected (C, l1) from ``data/discovery/pilotC_stat_mixer.json`` — they are NOT
re-tuned here (tuning on these folds would itself be leakage/overfitting), which
matches how the champion runs in production (frozen hyperparameters, coefficients
refit per run).

DERIVED / READ-ONLY
===================
Reads only the champion corpus. Writes only a derived JSON report under
``research/evaluation/``. Never touches canonical evidence.
"""

from __future__ import annotations

import datetime as dt
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

# The champion lives in scripts/; make it importable without moving it.
_SCRIPTS = str(Path("/home/ubuntu/scripts"))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from src.research.prediction_engine.eval import metrics as M

#: Declared champion cells (market, line) — mirrors the frozen artifact + scope.
DEFAULT_CELLS: tuple[tuple[str, float], ...] = (
    ("goals", 1.5), ("goals", 2.5), ("goals", 3.5),
    ("corners", 8.5), ("corners", 9.5), ("corners", 10.5),
    ("cards", 3.5), ("cards", 4.5),
)

STAT_MIXER_ARTIFACT = Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")


def load_frozen_hparams() -> dict[tuple[str, float], tuple[float, float]]:
    """(market, line) -> (C, l1_ratio) from the frozen champion artifact."""
    import json

    data = json.loads(STAT_MIXER_ARTIFACT.read_text())
    out: dict[tuple[str, float], tuple[float, float]] = {}
    for row in data.get("models", []):
        mk, ln = row.get("market"), row.get("line")
        if mk is None or ln is None:
            continue
        out[(mk, float(ln))] = (float(row["C"]), float(row["l1_ratio"]))
    return out


@dataclass
class FoldSpec:
    index: int
    train_end_unix: float
    test_start_unix: float
    test_end_unix: float

    def label(self) -> str:
        return (
            f"fold{self.index}:"
            f"{dt.datetime.utcfromtimestamp(self.test_start_unix).date()}.."
            f"{dt.datetime.utcfromtimestamp(self.test_end_unix).date()}"
        )


def make_expanding_folds(
    dates: list[float], *, n_folds: int = 5, min_train_frac: float = 0.4
) -> list[FoldSpec]:
    """Expanding-window folds over the sorted match dates.

    The first ``min_train_frac`` of the timeline is the initial training block;
    the remainder is split into ``n_folds`` equal chronological test blocks. Each
    fold trains on everything before its test block.
    """
    if not dates:
        return []
    ds = sorted(dates)
    lo, hi = ds[0], ds[-1]
    span = hi - lo
    start = lo + span * min_train_frac
    folds: list[FoldSpec] = []
    block = (hi - start) / n_folds
    for i in range(n_folds):
        ts = start + i * block
        te = start + (i + 1) * block if i < n_folds - 1 else hi + 1.0
        folds.append(FoldSpec(index=i, train_end_unix=ts, test_start_unix=ts, test_end_unix=te))
    return folds


@dataclass
class Prediction:
    market: str
    line: float
    competition: Optional[str]
    fold: int
    p_over: float
    y: float
    kickoff_unix: float


def run_walk_forward(
    *,
    cells: tuple[tuple[str, float], ...] = DEFAULT_CELLS,
    n_folds: int = 5,
    min_train_frac: float = 0.4,
    hparams: Optional[dict] = None,
    progress: bool = False,
) -> list[Prediction]:
    """Run the champion through expanding-window folds; return raw OOS predictions.

    Returns one :class:`Prediction` per (test match, cell) with a valid label and
    a produced probability. These raw predictions are then aggregated by
    :func:`aggregate` into the report.
    """
    import pilotC_stat_mixer as mix
    import pilotC_forward_predict as fp

    ms = mix.load_corpus()
    ms = [m for m in ms if m.get("date_unix")]
    hp = hparams or load_frozen_hparams()
    dates = [m["date_unix"] for m in ms]
    folds = make_expanding_folds(dates, n_folds=n_folds, min_train_frac=min_train_frac)

    preds: list[Prediction] = []
    for fold in folds:
        train = [m for m in ms if m["date_unix"] < fold.test_start_unix]
        test = [m for m in ms if fold.test_start_unix <= m["date_unix"] < fold.test_end_unix]
        if len(train) < 400 or not test:
            continue
        # History for prediction is built from TRAIN ONLY (matches strictly before
        # the fold's test window). roll() further restricts to d<kickoff and the
        # current season, so no test-fold match can leak into another's features.
        hist_train = mix.build_histories(train)
        # Fit each cell once per fold on the train slice.
        models: dict[tuple[str, float], object] = {}
        for (market, line) in cells:
            if (market, line) not in hp:
                continue
            C, l1 = hp[(market, line)]
            try:
                models[(market, line)] = fp.fit_full(train, hist_train, market, line, C, l1)
            except Exception:  # noqa: BLE001 - a cell that cannot fit this fold is skipped
                continue
        for m in test:
            match = {
                "home_name": m.get("home_name"),
                "away_name": m.get("away_name"),
                "date_unix": m.get("date_unix"),
            }
            # Sufficiency gate: both teams need >=3 current-season prior matches,
            # evaluated against the TRAIN-ONLY history (leak-free).
            hp_prov = mix.history_provenance(
                hist_train, m.get("home_name"), m.get("away_name"), m.get("date_unix")
            )
            if not hp_prov.get("sufficient"):
                continue
            for (market, line), model in models.items():
                y = mix.outcome(m, market, line)
                if y is None:
                    continue
                try:
                    p = fp.predict_one(model, hist_train, match, market)
                except Exception:  # noqa: BLE001
                    p = None
                if p is None:
                    continue
                preds.append(Prediction(
                    market=market, line=line, competition=m.get("competition_id"),
                    fold=fold.index, p_over=float(p), y=float(y),
                    kickoff_unix=float(m["date_unix"]),
                ))
        if progress:
            print(f"  {fold.label()}: train={len(train)} test={len(test)} preds={len(preds)}",
                  file=sys.stderr)
    return preds


# ── simple baselines (leak-free, chronological) ─────────────────────────────
def baseline_base_rate(preds: list[Prediction]) -> dict[tuple[str, float], list[Prediction]]:
    """Group predictions by cell for base-rate comparison (base rate computed
    per fold from the training block is the natural reference; here we report the
    champion vs the constant base-rate predictor via BSS in aggregate)."""
    from collections import defaultdict
    g = defaultdict(list)
    for p in preds:
        g[(p.market, p.line)].append(p)
    return g


def aggregate(preds: list[Prediction], *, min_n_competition: int = 100) -> dict:
    """Build the full derived report from raw OOS predictions."""
    from collections import defaultdict

    def block(ps: list[Prediction]) -> dict:
        return M.metric_block([p.p_over for p in ps], [p.y for p in ps]).to_dict()

    report: dict = {
        "report_contract": "champion-walk-forward-oos/v1",
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "note": (
            "DERIVED, read-only. Champion elastic-net logistic evaluated in "
            "expanding-window chronological walk-forward. Metrics describe "
            "prediction of the actual football event; market is not involved. "
            "HISTORICAL_OOS evidence — never merged with PROSPECTIVE_SHADOW."
        ),
        "total_oos_predictions": len(preds),
        "n_folds": len(set(p.fold for p in preds)),
        "by_market_line": {},
        "by_market": {},
        "pooled": block(preds) if preds else None,
    }

    by_cell = defaultdict(list)
    by_market = defaultdict(list)
    for p in preds:
        by_cell[(p.market, p.line)].append(p)
        by_market[p.market].append(p)

    for (market, line), ps in sorted(by_cell.items()):
        key = f"{market}@{line}"
        entry = block(ps)
        entry["reliability"] = [b.to_dict() for b in M.reliability_bins([q.p_over for q in ps], [q.y for q in ps])]
        entry["confidence_ladder"] = M.confidence_ladder([q.p_over for q in ps], [q.y for q in ps])
        # per-fold variability
        fold_bss = {}
        for f in sorted(set(q.fold for q in ps)):
            fps = [q for q in ps if q.fold == f]
            fold_bss[f"fold{f}"] = round(M.brier_skill_score([q.p_over for q in fps], [q.y for q in fps]) * 100, 3)
        entry["fold_bss_pct"] = fold_bss
        # per-competition (only where N adequate)
        comp = defaultdict(list)
        for q in ps:
            comp[q.competition].append(q)
        entry["by_competition"] = {
            str(c): block(cps) for c, cps in comp.items() if len(cps) >= min_n_competition
        }
        report["by_market_line"][key] = entry

    for market, ps in sorted(by_market.items()):
        entry = block(ps)
        entry["confidence_ladder"] = M.confidence_ladder([q.p_over for q in ps], [q.y for q in ps])
        report["by_market"][market] = entry

    return report


def main(argv=None) -> int:  # pragma: no cover - CLI wrapper
    import argparse, json

    parser = argparse.ArgumentParser(description="Champion walk-forward OOS benchmark (derived)")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--min-train-frac", type=float, default=0.4)
    parser.add_argument("--out", default="research/evaluation/champion_walk_forward_oos.json")
    args = parser.parse_args(argv)

    preds = run_walk_forward(n_folds=args.folds, min_train_frac=args.min_train_frac, progress=True)
    report = aggregate(preds)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report["by_market"], indent=2))
    print(f"\nwrote {out}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
