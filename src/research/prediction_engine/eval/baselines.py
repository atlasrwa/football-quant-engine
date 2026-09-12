"""Simple leak-free baselines to contextualize the champion's OOS skill.

Every baseline is evaluated on the SAME expanding-window folds and the SAME
eligible test observations as the champion, using ONLY information available
strictly before each fold's test window. A sophisticated model must beat these
to justify its complexity (task section 24).

Baselines:
  * base_rate    : constant = the training-block base rate for the cell
                   (the reference the Brier Skill Score is defined against).
  * team_form    : simple current-season-to-date rate that the team's matches
                   went over the line, averaged over home & away teams. No
                   regression, no standardization — a naive form heuristic.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

_SCRIPTS = str(Path("/home/ubuntu/scripts"))
if _SCRIPTS not in sys.path:
    sys.path.insert(0, _SCRIPTS)

from src.research.prediction_engine.eval import metrics as M
from src.research.prediction_engine.eval.walk_forward import (
    DEFAULT_CELLS,
    make_expanding_folds,
)


def _team_over_rate(hist, mix, team, market, line, before, season) -> Optional[float]:
    """Fraction of the team's current-season prior matches that went over line."""
    rows = [
        (d, m, r)
        for d, m, r in hist.get(team, [])
        if d < before and mix._season_key(m) == season
    ]
    if len(rows) < 3:
        return None
    hits = 0
    n = 0
    for _, m, _r in rows:
        o = mix.outcome(m, market, line)
        if o is None:
            continue
        n += 1
        hits += 1 if o >= 0.5 else 0
    return hits / n if n else None


def run_baselines(
    *, cells=DEFAULT_CELLS, n_folds: int = 5, min_train_frac: float = 0.4
) -> dict:
    """Compute base_rate and team_form baseline metrics on the champion folds."""
    import pilotC_stat_mixer as mix

    ms = [m for m in mix.load_corpus() if m.get("date_unix")]
    folds = make_expanding_folds([m["date_unix"] for m in ms], n_folds=n_folds, min_train_frac=min_train_frac)

    # accumulate predictions per cell for each baseline
    acc = {b: {c: {"p": [], "y": []} for c in cells} for b in ("base_rate", "team_form")}

    for fold in folds:
        train = [m for m in ms if m["date_unix"] < fold.test_start_unix]
        test = [m for m in ms if fold.test_start_unix <= m["date_unix"] < fold.test_end_unix]
        if len(train) < 400 or not test:
            continue
        hist_train = mix.build_histories(train)
        # training-block base rate per cell
        base_rate = {}
        for (market, line) in cells:
            ys = [mix.outcome(m, market, line) for m in train]
            ys = [v for v in ys if v is not None]
            base_rate[(market, line)] = (sum(ys) / len(ys)) if ys else 0.5
        for m in test:
            hp = mix.history_provenance(hist_train, m.get("home_name"), m.get("away_name"), m.get("date_unix"))
            if not hp.get("sufficient"):
                continue
            before = m["date_unix"]
            hs = mix.current_season_key(hist_train, m.get("home_name"), before)
            as_ = mix.current_season_key(hist_train, m.get("away_name"), before)
            for (market, line) in cells:
                y = mix.outcome(m, market, line)
                if y is None:
                    continue
                acc["base_rate"][(market, line)]["p"].append(base_rate[(market, line)])
                acc["base_rate"][(market, line)]["y"].append(float(y))
                hr = _team_over_rate(hist_train, mix, m.get("home_name"), market, line, before, hs)
                ar = _team_over_rate(hist_train, mix, m.get("away_name"), market, line, before, as_)
                vals = [v for v in (hr, ar) if v is not None]
                if not vals:
                    continue
                p = min(max(sum(vals) / len(vals), 0.01), 0.99)
                acc["team_form"][(market, line)]["p"].append(p)
                acc["team_form"][(market, line)]["y"].append(float(y))

    report = {}
    for b, cellmap in acc.items():
        report[b] = {}
        for (market, line), d in cellmap.items():
            if not d["y"]:
                continue
            report[b][f"{market}@{line}"] = M.metric_block(d["p"], d["y"]).to_dict()
    return report


def main(argv=None) -> int:  # pragma: no cover
    import argparse, json

    parser = argparse.ArgumentParser(description="Baseline OOS metrics (derived)")
    parser.add_argument("--folds", type=int, default=5)
    parser.add_argument("--out", default="research/evaluation/baseline_oos.json")
    args = parser.parse_args(argv)
    rep = run_baselines(n_folds=args.folds)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(rep, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(rep, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
