"""Task 4 — Goals O/U 2.5: prior-only model vs market closing line (EPL 2023/24, 9660).

- Model: Dixon-Coles goals model, walk-forward expanding window, refit every 10 (same as
  the old benchmark's DC interval). DC uses ONLY team identity + past goals; it does not
  read any same-match realized stats, so it is leak-free for goals. The predicted match's
  own goals are used only as the scoring label, never as a feature.
- Market: Football-Data.co.uk E0 2023/24 CSV (FREE public data the user authorized).
  Closing O/U 2.5 columns AvgC>2.5 / AvgC<2.5 (market-consensus closing). De-vigged to a
  proper probability via normalization (two-way overround removal).
- Scoring: model Brier vs de-vigged-market Brier on IDENTICAL complete cases (fixtures
  present in both the persisted model predictions and the CSV with valid closing odds).

This is a retrospective 'is the model above or below the closing line' comparison, which
per the revised requirement does NOT need quote timestamps. No CLV claim is made.
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, "/home/ubuntu")
from src.research.models.dixon_coles import DixonColesModel

CACHE_DIR = Path("/home/ubuntu/.cache/footystats_research")
SEASON_ID = 9660
GOALS_LINE = 2.5
MIN_TRAIN = 150
REFIT_DC = 10
CSV_PATH = Path("/home/ubuntu/data/football_data/E0_2324.csv")
OUT_PATH = Path("/home/ubuntu/data/results/goals_vs_market_9660.json")

# FootyStats name -> Football-Data name.
NAME_MAP = {
    "AFC Bournemouth": "Bournemouth",
    "Brighton & Hove Albion": "Brighton",
    "Luton Town": "Luton",
    "Manchester City": "Man City",
    "Manchester United": "Man United",
    "Newcastle United": "Newcastle",
    "Nottingham Forest": "Nott'm Forest",
    "Tottenham Hotspur": "Tottenham",
    "West Ham United": "West Ham",
    "Wolverhampton Wanderers": "Wolves",
    # identical: Arsenal, Aston Villa, Brentford, Burnley, Chelsea, Crystal Palace,
    # Everton, Fulham, Liverpool, Sheffield United
}


def fd_name(fs_name: str) -> str:
    return NAME_MAP.get(fs_name, fs_name)


def load_cached_season(season_id):
    matches = []
    page = 1
    while True:
        fn = CACHE_DIR / f"league-matches_{{max_per_page:_300,_page:_{page},_season_id:_{season_id}}}.json"
        if not fn.exists():
            break
        payload = json.load(open(fn))
        data = payload.get("data") if isinstance(payload, dict) else payload
        if not data:
            break
        matches.extend(data)
        page += 1
    return matches


def load_market_closing():
    """Return {(home_fd, date_iso): (over_prob_devig, over_odds, under_odds)} from AvgC O/U 2.5."""
    out = {}
    with open(CSV_PATH) as f:
        for row in csv.DictReader(f):
            try:
                over = float(row["AvgC>2.5"])
                under = float(row["AvgC<2.5"])
            except (ValueError, KeyError):
                continue
            if over <= 1.0 or under <= 1.0:
                continue
            d = datetime.strptime(row["Date"], "%d/%m/%Y").date().isoformat()
            # De-vig: implied probs then normalize to remove two-way overround.
            io, iu = 1.0 / over, 1.0 / under
            p_over = io / (io + iu)
            out[(row["HomeTeam"], d)] = (p_over, over, under)
    return out


def brier(preds, actuals):
    return float(np.mean([(p - a) ** 2 for p, a in zip(preds, actuals)]))


def main():
    raw = load_cached_season(SEASON_ID)
    complete = sorted([m for m in raw if m.get("status") == "complete"],
                      key=lambda m: m.get("date_unix", 0))
    n = len(complete)

    # Build DC feature rows: team ids + goals + date. Goals are label/outcome only.
    team_to_id = {}
    feats = []
    for m in complete:
        h, a = m.get("home_name"), m.get("away_name")
        for t in (h, a):
            if t not in team_to_id:
                team_to_id[t] = len(team_to_id)
        feats.append({
            "home_team_id": float(team_to_id[h]),
            "away_team_id": float(team_to_id[a]),
            "home_goals": m.get("homeGoalCount"),
            "away_goals": m.get("awayGoalCount"),
            "total_goals": (m.get("homeGoalCount") or 0) + (m.get("awayGoalCount") or 0),
            "date_unix": m.get("date_unix"),
        })

    market = load_market_closing()

    dc = None
    rows = []
    for i in range(MIN_TRAIN, n):
        train = feats[:i]
        test = feats[i]
        m = complete[i]
        if (i - MIN_TRAIN) % REFIT_DC == 0:
            dc = DixonColesModel(line=GOALS_LINE)
            dc.fit(train, [(f["total_goals"]) > GOALS_LINE for f in train])

        tg = test["total_goals"]
        actual_over = 1.0 if tg > GOALS_LINE else 0.0
        model_p = dc.predict(test).p_over

        d_iso = datetime.fromtimestamp(m["date_unix"], tz=timezone.utc).date().isoformat()
        key = (fd_name(m["home_name"]), d_iso)
        mk = market.get(key)
        prior_over_rate = float(np.mean([f["total_goals"] > GOALS_LINE for f in train]))
        rows.append({
            "match_id": m.get("id"),
            "date": d_iso,
            "home": m.get("home_name"),
            "away": m.get("away_name"),
            "total_goals": tg,
            "actual_over25": actual_over,
            "model_p_over": model_p,
            "naive_p_over_rolling": prior_over_rate,
            "market_p_over_devig": mk[0] if mk else None,
            "market_over_odds": mk[1] if mk else None,
            "market_under_odds": mk[2] if mk else None,
        })

    # Complete cases: both model and market present.
    cc = [r for r in rows if r["market_p_over_devig"] is not None]
    model_b = brier([r["model_p_over"] for r in cc], [r["actual_over25"] for r in cc])
    market_b = brier([r["market_p_over_devig"] for r in cc], [r["actual_over25"] for r in cc])
    # Fair naive comparator: each fixture's forecast is the strictly-prior
    # expanding-training base rate, retained only on the same market-complete cases.
    naive_rolling_b = brier(
        [r["naive_p_over_rolling"] for r in cc],
        [r["actual_over25"] for r in cc],
    )
    # Descriptive only: this uses all 230 outcomes to estimate its own constant.
    # It is not a valid out-of-sample naive benchmark.
    base = float(np.mean([r["actual_over25"] for r in cc]))
    naive_in_sample_b = brier([base] * len(cc), [r["actual_over25"] for r in cc])

    print("=" * 74)
    print("TASK 4 — GOALS O/U 2.5: MODEL vs MARKET CLOSING LINE (EPL 2023/24, 9660)")
    print("=" * 74)
    print(f"Walk-forward predictions: {len(rows)}   matched complete cases (model & market): {len(cc)}")
    print(f"Market source: Football-Data E0 2023/24 closing AvgC>2.5 / AvgC<2.5 (de-vigged)")
    print(f"Over 2.5 realized rate (complete cases): {base:.3f}")
    print("Naive benchmark: rolling strictly-prior expanding-training over rate")
    print()
    print(f"{'':<30}{'Brier (lower=better)':<22}")
    print("-" * 52)
    print(f"{'Model (Dixon-Coles)':<30}{model_b:<.4f}")
    print(f"{'Market (de-vig close)':<30}{market_b:<.4f}")
    print(f"{'Naive (rolling prior rate)':<30}{naive_rolling_b:<.4f}")
    print(f"{'Naive (in-sample, invalid)':<30}{naive_in_sample_b:<.4f}")
    print()
    diff = market_b - model_b
    if diff > 0:
        print(f"Model is BELOW the closing line by {diff:+.4f} Brier "
              f"({diff/market_b*100:+.1f}% vs market) — model beats the market on this sample.")
    else:
        print(f"Model is ABOVE the closing line by {diff:+.4f} Brier "
              f"({diff/market_b*100:+.1f}% vs market) — the closing line beats the model.")
    print()
    print("Note: retrospective above/below-line comparison; no timestamp/CLV claim is made.")

    OUT_PATH.write_text(json.dumps({
        "meta": {
            "season_id": SEASON_ID, "season_label": "2023/24",
            "line": GOALS_LINE, "market_source": "football-data E0 2324 AvgC O/U 2.5 (de-vigged)",
            "n_walk_forward": len(rows), "n_complete_cases": len(cc),
            "over_base_rate": base,
        },
        "scores": {
            "model_brier": model_b,
            "market_brier": market_b,
            "naive_rolling_prior_brier": naive_rolling_b,
            "naive_in_sample_constant_brier_invalid": naive_in_sample_b,
            "model_minus_market": model_b - market_b,
        },
        "predictions": rows,
    }, indent=2))
    print(f"\nWrote {OUT_PATH}")


if __name__ == "__main__":
    main()
