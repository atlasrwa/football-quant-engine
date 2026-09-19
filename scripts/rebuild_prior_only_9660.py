"""Rebuild strictly-prior EPL 2023/24 (FootyStats season 9660) walk-forward predictions.

Purpose (Task 2 of the leak-remediation work):
  - Read the ALREADY-CACHED FootyStats season 9660 corpus (no network, no credentials).
  - Build corners/cards features using ONLY pre-match information via the existing
    src.research.models.prior_only_features.build_prior_only_features (rolling means over
    strictly-earlier matches). This eliminates the within-row same-match leak that the
    old run_benchmark.py / run_robustness_check.py had (they copied the predicted match's
    own realized shots/attacks/possession/fouls into the feature dict).
  - Prove absence of leak by construction with assert_no_same_match_leakage.
  - Run an expanding-window walk-forward with the same CountRegression models and refit
    intervals, producing prior-only probabilities.
  - Persist FIXTURE-KEYED probabilities (keyed on the FootyStats match id) to disk so any
    later comparison scores the identical fixtures.

Season labeling: season 9660 == EPL 2023/24 (verified against league_list.json:
  4759=2020/21, 6135=21/22, 7704=22/23, 9660=23/24). The old benchmark used 4759 while
  labeling it 2023/24; this script uses 9660 and labels it 2023/24 correctly.

Outputs:
  data/results/prior_only_9660_predictions.json  (fixture-keyed predictions + outcomes + odds)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/home/ubuntu")

import numpy as np

from src.research.models.count_regression import create_corners_model, create_cards_model
from src.research.models.prior_only_features import (
    build_prior_only_features,
    assert_no_same_match_leakage,
)

CACHE_DIR = Path("/home/ubuntu/.cache/footystats_research")
SEASON_ID = 9660           # EPL 2023/24
SEASON_LABEL = "2023/24"
CORNERS_LINE = 9.5
CARDS_LINE = 3.5
MIN_TRAIN = 150            # same as old run_benchmark.py
REFIT_INTERVAL_CORNERS = 50
REFIT_INTERVAL_CARDS = 50
OUT_PATH = Path("/home/ubuntu/data/results/prior_only_9660_predictions.json")


def load_cached_season(season_id: int) -> list[dict]:
    """Load the cached raw FootyStats match dicts for a season (all pages)."""
    matches: list[dict] = []
    page = 1
    while True:
        fn = CACHE_DIR / (
            f"league-matches_{{max_per_page:_300,_page:_{page},_season_id:_{season_id}}}.json"
        )
        if not fn.exists():
            break
        with open(fn) as f:
            payload = json.load(f)
        data = payload.get("data") if isinstance(payload, dict) else payload
        if not data:
            break
        matches.extend(data)
        page += 1
    return matches


def total_cards(m: dict) -> float | None:
    ya, yb = m.get("team_a_yellow_cards"), m.get("team_b_yellow_cards")
    ra = m.get("team_a_red_cards") or 0
    rb = m.get("team_b_red_cards") or 0
    if ya is None or yb is None or ya == -1 or yb == -1:
        return None
    return float(ya) + float(yb) + float(ra) + float(rb)


def main() -> None:
    raw = load_cached_season(SEASON_ID)
    complete = [m for m in raw if m.get("status") == "complete"]
    complete.sort(key=lambda m: m.get("date_unix", 0))
    n = len(complete)
    print(f"Season {SEASON_ID} (EPL {SEASON_LABEL}): {len(raw)} raw, {n} complete fixtures")
    assert n == 380, f"expected 380 complete EPL fixtures, got {n}"

    # ── Build strictly-prior features (leak-free) ────────────────────────────
    corners_feats = build_prior_only_features(complete, target_field="total_corners")
    cards_feats = build_prior_only_features(complete, target_field="total_cards")

    # Structural proof: no feature carries the predicted match's own realized stat.
    assert_no_same_match_leakage(complete, corners_feats)
    assert_no_same_match_leakage(complete, cards_feats)
    print("Anti-leakage assertions PASSED for corners and cards (prior-only by construction).")

    # Attach team ids as floats (model expects home_team_id/away_team_id floats) and the
    # fixture identity. build_prior_only_features already keyed home_team_id/away_team_id to
    # the FootyStats homeID/awayID and carried date_unix + the target; add match id + odds.
    sorted_matches = sorted(complete, key=lambda m: m.get("date_unix", 0))
    for feat, m in zip(corners_feats, sorted_matches):
        feat["match_id"] = m.get("id")
        feat["home_team_id"] = float(feat["home_team_id"]) if feat["home_team_id"] is not None else None
        feat["away_team_id"] = float(feat["away_team_id"]) if feat["away_team_id"] is not None else None
    for feat, m in zip(cards_feats, sorted_matches):
        feat["match_id"] = m.get("id")
        feat["home_team_id"] = float(feat["home_team_id"]) if feat["home_team_id"] is not None else None
        feat["away_team_id"] = float(feat["away_team_id"]) if feat["away_team_id"] is not None else None

    # ── Walk-forward (expanding window, no look-ahead) ───────────────────────
    records: dict[int, dict] = {}
    corners_model = None
    cards_model = None

    for i in range(MIN_TRAIN, n):
        c_train = corners_feats[:i]
        k_train = cards_feats[:i]
        c_test = corners_feats[i]
        k_test = cards_feats[i]
        m = sorted_matches[i]
        mid = m.get("id")

        if (i - MIN_TRAIN) % REFIT_INTERVAL_CORNERS == 0:
            corners_model = create_corners_model(line=CORNERS_LINE)
            corners_model.fit(
                c_train,
                [(f.get("total_corners") or 0) > CORNERS_LINE for f in c_train],
            )
        if (i - MIN_TRAIN) % REFIT_INTERVAL_CARDS == 0:
            cards_model = create_cards_model(line=CARDS_LINE)
            cards_model.fit(
                k_train,
                [(f.get("total_cards") or 0) > CARDS_LINE for f in k_train],
            )

        # Realized outcomes (labels) from the corpus — used ONLY for scoring, never as features.
        tc = c_test.get("total_corners")
        tk = k_test.get("total_cards")
        actual_corners = None if tc is None else (1.0 if tc > CORNERS_LINE else 0.0)
        actual_cards = None if tk is None else (1.0 if tk > CARDS_LINE else 0.0)

        # Naive baseline = training base rate of over.
        naive_corners = sum(
            1 for f in c_train if (f.get("total_corners") or -1) > CORNERS_LINE
        ) / len(c_train)
        naive_cards = sum(
            1 for f in k_train if (f.get("total_cards") or -1) > CARDS_LINE
        ) / len(k_train)

        p_corners = corners_model.predict(c_test).p_over
        p_cards = cards_model.predict(k_test).p_over

        records[mid] = {
            "match_id": mid,
            "date_unix": m.get("date_unix"),
            "home_name": m.get("home_name"),
            "away_name": m.get("away_name"),
            "walk_forward_index": i,
            # corners
            "corners_line": CORNERS_LINE,
            "total_corners": tc,
            "actual_corners_over": actual_corners,
            "model_p_corners_over": p_corners,
            "naive_p_corners_over": naive_corners,
            # cards
            "cards_line": CARDS_LINE,
            "total_cards": tk,
            "actual_cards_over": actual_cards,
            "model_p_cards_over": p_cards,
            "naive_p_cards_over": naive_cards,
            # pre-match odds carried for downstream use (goals odds handled separately in Task 4)
            "odds_ft_over25": m.get("odds_ft_over25"),
            "odds_ft_under25": m.get("odds_ft_under25"),
            "odds_corners_over_95": m.get("odds_corners_over_95"),
            "odds_corners_under_95": m.get("odds_corners_under_95"),
        }

    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    out = {
        "meta": {
            "season_id": SEASON_ID,
            "season_label": SEASON_LABEL,
            "league": "England Premier League",
            "n_complete_fixtures": n,
            "min_train": MIN_TRAIN,
            "refit_interval_corners": REFIT_INTERVAL_CORNERS,
            "refit_interval_cards": REFIT_INTERVAL_CARDS,
            "corners_line": CORNERS_LINE,
            "cards_line": CARDS_LINE,
            "feature_construction": "prior_only (build_prior_only_features); "
                                     "assert_no_same_match_leakage passed",
            "leak_free": True,
            "n_predictions": len(records),
        },
        "predictions": list(records.values()),
    }
    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)
    print(f"Wrote {len(records)} fixture-keyed prior-only predictions to {OUT_PATH}")


if __name__ == "__main__":
    main()
