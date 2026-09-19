"""Diagnose the surviving cards +5.72% edge on leak-free features (Task 3 follow-up).

Question: after removing the same-match leak, cards still shows ~+5.7% vs naive while
corners goes to ~0. Is the cards edge coming from the conditioning FEATURES (fouls/
attacks/possession rolling means), or is it just the count model's distributional prior
(team effects + Poisson/NB shape) beating a base-rate constant at the 3.5 line?

Test: rebuild cards predictions three ways on the SAME 9660 walk-forward and compare
vs-naive Brier:
  A) full prior-only features (what Task 2/3 used)
  B) NO conditioning features (feature_fields=()), team effects ON  -> pure count prior
  C) NO features, NO team effects                                    -> intercept-only count

If B (and especially C) already captures most of the +5.7%, the edge is the count-model
prior over the line, not predictive information in the prior-only features.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import sys
sys.path.insert(0, "/home/ubuntu")
from src.research.models.count_regression import CountRegressionModel
from src.research.models.prior_only_features import build_prior_only_features

CACHE_DIR = Path("/home/ubuntu/.cache/footystats_research")
SEASON_ID = 9660
CARDS_LINE = 3.5
MIN_TRAIN = 150
REFIT = 50


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


def brier(preds, actuals):
    return float(np.mean([(p - a) ** 2 for p, a in zip(preds, actuals)]))


def run(feats, make_model):
    n = len(feats)
    model = None
    preds, naive, actual = [], [], []
    for i in range(MIN_TRAIN, n):
        train = feats[:i]
        test = feats[i]
        if (i - MIN_TRAIN) % REFIT == 0:
            model = make_model()
            model.fit(train, [(f.get("total_cards") or 0) > CARDS_LINE for f in train])
        tk = test.get("total_cards")
        if tk is None:
            continue
        actual.append(1.0 if tk > CARDS_LINE else 0.0)
        preds.append(model.predict(test).p_over)
        naive.append(sum(1 for f in train if (f.get("total_cards") or -1) > CARDS_LINE) / len(train))
    mb, nb = brier(preds, actual), brier(naive, actual)
    return mb, nb, (nb - mb) / nb * 100


def main():
    raw = load_cached_season(SEASON_ID)
    complete = sorted([m for m in raw if m.get("status") == "complete"], key=lambda m: m.get("date_unix", 0))
    feats = build_prior_only_features(complete, target_field="total_cards")
    for f, m in zip(feats, complete):
        f["home_team_id"] = float(f["home_team_id"])
        f["away_team_id"] = float(f["away_team_id"])

    CARDS_FF = ("fouls_home", "fouls_away", "dangerous_attacks_home",
                "dangerous_attacks_away", "possession_home", "possession_away")

    configs = {
        "A full prior-only features + team effects": lambda: CountRegressionModel(
            target_field="total_cards", line=CARDS_LINE, feature_fields=CARDS_FF, use_team_effects=True),
        "B no features, team effects ON": lambda: CountRegressionModel(
            target_field="total_cards", line=CARDS_LINE, feature_fields=(), use_team_effects=True),
        "C no features, no team effects (intercept-only)": lambda: CountRegressionModel(
            target_field="total_cards", line=CARDS_LINE, feature_fields=(), use_team_effects=False),
    }

    print("Cards O/U 3.5 — decomposing the surviving edge (EPL 2023/24, n=230, leak-free)")
    print("-" * 74)
    print(f"{'config':<48}{'model B':<10}{'naive B':<10}{'vs naive':<9}")
    for name, mk in configs.items():
        mb, nb, vs = run(feats, mk)
        print(f"{name:<48}{mb:<10.4f}{nb:<10.4f}{vs:>+7.2f}%")


if __name__ == "__main__":
    main()
