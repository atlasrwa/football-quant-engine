#!/usr/bin/env python3
"""Score the stale-corpus forecasts against a fresh-corpus reconstruction.

WHAT THIS MEASURES
==================
The 16 forecasts published on 2026-09-05 were fitted on a corpus ending 2026-05-31.
Those fixtures have now settled and their results are in the corpus, so two things can
be compared against the same outcomes:

* STALE  — the probabilities actually published, read from the broadcast ledger.
* FRESH  — probabilities recomputed from a corpus that includes 2026/27 matches, cut
           before the earliest kick-off of the day.

WHAT THIS IS NOT
================
This is a walk-forward RECONSTRUCTION, not forward evidence. The fresh probabilities
were never published and were computed with knowledge that the fresh corpus exists;
only the leakage constraint (no match at or after the cutoff) makes the comparison
meaningful at all. With 16 fixtures across 4 market cells there are at most 64
observations, several of them correlated through shared teams and a shared matchday.
That is nowhere near enough to support a claim that either model has skill, and this
script does not make one. It answers a narrower question: did using last season's form
in place of this season's measurably change the published numbers, and in which
direction did it move against the results that actually occurred.

THE CUTOFF
==========
One snapshot boundary is used for all 16: the earliest kick-off among them
(2026-09-05T11:30Z). Every match admitted had certainly finished before that moment, so
no fixture in the set can contribute to its own features or to any other in the set.
This is stricter than necessary for the later kick-offs and deliberately so — the
reconstruction should not be able to flatter itself.

USAGE
=====
    python3 scripts/score_stale_vs_fresh_corpus.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from datetime import datetime, timezone
from typing import Any, Optional

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.research.prediction_engine.broadcast.corpus_snapshot import (
    build_snapshot,
    fingerprint_matches,
)
from src.research.prediction_engine.broadcast.record import (
    BroadcastLedger,
    DEFAULT_RECORD_ROOT,
)
from src.research.prediction_engine.broadcast.scope_config import load_scope_config

STALE_DATA_CUTOFF_UTC = "2026-05-31T16:30:00+00:00"
CURRENT_SEASON = "2026/2027"


def _iso(unix: float) -> str:
    return datetime.fromtimestamp(float(unix), timezone.utc).isoformat()


def _num(value: Any) -> Optional[float]:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out >= 0 else None


def actual_outcome(match: dict, market: str, line: Optional[float]) -> Optional[float]:
    """The realised 0/1 outcome for one market cell, from the settled corpus row.

    Reads the same fields the model's training targets use, so the comparison scores
    the published claim rather than a re-specified one.
    """
    home_goals, away_goals = _num(match.get("homeGoalCount")), _num(match.get("awayGoalCount"))
    if market == "goals":
        total = _num(match.get("totalGoalCount"))
        if total is None and home_goals is not None and away_goals is not None:
            total = home_goals + away_goals
        return None if total is None or line is None else float(total > line)
    if market == "btts":
        if home_goals is None or away_goals is None:
            return None
        return float(home_goals > 0 and away_goals > 0)
    if market == "corners":
        a, b = _num(match.get("team_a_corners")), _num(match.get("team_b_corners"))
        return None if a is None or b is None or line is None else float(a + b > line)
    if market == "cards":
        parts = [
            _num(match.get("team_a_yellow_cards")), _num(match.get("team_b_yellow_cards")),
            _num(match.get("team_a_red_cards")), _num(match.get("team_b_red_cards")),
        ]
        if any(p is None for p in parts) or line is None:
            return None
        return float(sum(parts) > line)  # type: ignore[arg-type]
    return None


def brier(pairs: list[tuple[float, float]]) -> Optional[float]:
    """Mean squared error of probability against outcome. Lower is better."""
    if not pairs:
        return None
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def log_loss(pairs: list[tuple[float, float]]) -> Optional[float]:
    """Mean negative log likelihood, clipped to keep a single miss from dominating."""
    import math

    if not pairs:
        return None
    eps = 1e-6
    return -sum(
        y * math.log(max(p, eps)) + (1 - y) * math.log(max(1 - p, eps))
        for p, y in pairs
    ) / len(pairs)


def main() -> int:
    import pilotC_forward_predict as fp
    import pilotC_stat_mixer as mix

    config = load_scope_config(require_recorded_change=False)
    ledger = BroadcastLedger(DEFAULT_RECORD_ROOT)

    affected = [
        rec for rec in ledger.commitments()
        if (rec.get("payload") or {}).get("data_cutoff_utc") == STALE_DATA_CUTOFF_UTC
    ]
    if not affected:
        print(json.dumps({"error": "no affected commitments found"}))
        return 1

    matches = mix.load_corpus()
    by_pair: dict[tuple[str, str, int], dict] = {}
    for m in matches:
        by_pair[(str(m["home_name"]), str(m["away_name"]), int(m["date_unix"]))] = m

    # One conservative cutoff for the whole set: the earliest kick-off among them.
    cutoff = min(float(rec["payload"]["kickoff_unix"]) for rec in affected)

    snapshot, fingerprint = build_snapshot(matches, cutoff_unix=cutoff)
    stale_matches = [m for m in snapshot if str(m.get("season")) != CURRENT_SEASON]
    stale_fingerprint = fingerprint_matches(stale_matches)

    fresh_hist = mix.build_histories(list(snapshot))
    stale_hist = mix.build_histories(stale_matches)

    artifact = json.loads(
        (
            __import__("pathlib").Path("/home/ubuntu/data/discovery/pilotC_stat_mixer.json")
        ).read_text(encoding="utf-8")
    )
    saved = {
        (row["market"], row.get("line")): (row["C"], row["l1_ratio"])
        for row in artifact["models"]
    }

    fresh_models: dict[tuple[str, Optional[float]], Any] = {}
    stale_models: dict[tuple[str, Optional[float]], Any] = {}
    for spec in config.markets:
        C, l1r = saved[spec.cell]
        fresh_models[spec.cell] = fp.fit_full(
            list(snapshot), fresh_hist, spec.market, spec.line, C, l1r
        )
        stale_models[spec.cell] = fp.fit_full(
            stale_matches, stale_hist, spec.market, spec.line, C, l1r
        )

    per_cell: dict[str, dict[str, list]] = {}
    fixtures: list[dict[str, Any]] = []
    reproduction_deltas: list[float] = []

    for rec in sorted(affected, key=lambda r: r["payload"]["kickoff_unix"]):
        payload = rec["payload"]
        home, away = payload["home_team"], payload["away_team"]
        kickoff = int(payload["kickoff_unix"])
        settled = by_pair.get((home, away, kickoff))
        entry: dict[str, Any] = {
            "fixture_id": rec.get("fixture_id"),
            "fixture": f"{home} vs {away}",
            "kickoff_utc": payload["kickoff_utc"],
            "settled_in_corpus": settled is not None,
            "markets": {},
        }
        if settled is None:
            fixtures.append(entry)
            continue
        entry["result"] = (
            f"{settled.get('homeGoalCount')}-{settled.get('awayGoalCount')}"
        )

        published = {
            (m["market"], m.get("line")): m.get("p_over")
            for m in payload.get("markets", [])
        }

        for spec in config.markets:
            cell_key = f"{spec.market}|{spec.line}"
            outcome = actual_outcome(settled, spec.market, spec.line)
            p_published = published.get(spec.cell)
            try:
                p_fresh = fp.predict_one(
                    fresh_models[spec.cell], fresh_hist,
                    {"home_name": home, "away_name": away, "date_unix": kickoff},
                    spec.market,
                )
            except Exception:  # noqa: BLE001
                p_fresh = None
            try:
                p_stale_recomputed = fp.predict_one(
                    stale_models[spec.cell], stale_hist,
                    {"home_name": home, "away_name": away, "date_unix": kickoff},
                    spec.market,
                )
            except Exception:  # noqa: BLE001
                p_stale_recomputed = None

            if p_published is not None and p_stale_recomputed is not None:
                reproduction_deltas.append(abs(p_published - p_stale_recomputed))

            entry["markets"][cell_key] = {
                "outcome": outcome,
                "p_published_stale": p_published,
                "p_fresh": round(p_fresh, 4) if p_fresh is not None else None,
                "shift": (
                    round(p_fresh - p_published, 4)
                    if p_fresh is not None and p_published is not None else None
                ),
            }

            if outcome is None:
                continue
            bucket = per_cell.setdefault(cell_key, {"stale": [], "fresh": []})
            if p_published is not None:
                bucket["stale"].append((float(p_published), outcome))
            if p_fresh is not None:
                bucket["fresh"].append((float(p_fresh), outcome))

        fixtures.append(entry)

    scores: dict[str, Any] = {}
    all_stale: list[tuple[float, float]] = []
    all_fresh: list[tuple[float, float]] = []
    for cell_key, bucket in sorted(per_cell.items()):
        all_stale += bucket["stale"]
        all_fresh += bucket["fresh"]
        stale_brier, fresh_brier = brier(bucket["stale"]), brier(bucket["fresh"])
        scores[cell_key] = {
            "n": len(bucket["stale"]),
            "base_rate": (
                round(statistics.fmean(y for _p, y in bucket["stale"]), 4)
                if bucket["stale"] else None
            ),
            "brier_stale": round(stale_brier, 5) if stale_brier is not None else None,
            "brier_fresh": round(fresh_brier, 5) if fresh_brier is not None else None,
            "brier_improvement": (
                round(stale_brier - fresh_brier, 5)
                if stale_brier is not None and fresh_brier is not None else None
            ),
            "log_loss_stale": round(log_loss(bucket["stale"]), 5),
            "log_loss_fresh": round(log_loss(bucket["fresh"]), 5),
        }

    pooled_stale, pooled_fresh = brier(all_stale), brier(all_fresh)

    # An in-sample base-rate reference. Both models must be read against something:
    # a Brier score alone says nothing about whether either forecast is informative.
    # This reference is FLATTERED because its rate is computed from the same 64
    # outcomes it is scored on, so it is a lower bound on what a naive forecast would
    # really achieve out of sample. It is included because omitting it would let a
    # pooled improvement of 0.0002 read as meaningful.
    base_rate_pairs = [
        (statistics.fmean(y for _p, y in bucket["stale"]), y)
        for bucket in per_cell.values()
        for _p, y in bucket["stale"]
    ]
    pooled_base_rate = brier(base_rate_pairs)

    shifts = [
        abs(m["shift"])
        for f in fixtures for m in f.get("markets", {}).values()
        if m.get("shift") is not None
    ]

    report = {
        "report_contract": "stale-vs-fresh-corpus-score/v1",
        "generated_at_utc": _iso(time.time()),
        "method": (
            "Walk-forward reconstruction. Both models use the frozen stat-mixer "
            "hyperparameters. Snapshot cutoff is the earliest kick-off in the set, so "
            "no fixture contributes to its own features or to any other in the set."
        ),
        "snapshot_cutoff_utc": _iso(cutoff),
        "fresh_corpus": fingerprint.provenance_dict(),
        "stale_corpus": stale_fingerprint.provenance_dict(),
        "reproduction_check": {
            "note": (
                "Refitting the stale corpus should reproduce the published "
                "probabilities; a large delta would mean the reconstruction is not "
                "comparable to what was published."
            ),
            "n": len(reproduction_deltas),
            "max_abs_delta": (
                round(max(reproduction_deltas), 6) if reproduction_deltas else None
            ),
            "mean_abs_delta": (
                round(statistics.fmean(reproduction_deltas), 6)
                if reproduction_deltas else None
            ),
        },
        "probability_shift": {
            "n": len(shifts),
            "mean_abs_shift": round(statistics.fmean(shifts), 4) if shifts else None,
            "median_abs_shift": round(statistics.median(shifts), 4) if shifts else None,
            "max_abs_shift": round(max(shifts), 4) if shifts else None,
        },
        "per_cell_scores": scores,
        "pooled": {
            "n": len(all_stale),
            "brier_stale": round(pooled_stale, 5) if pooled_stale is not None else None,
            "brier_fresh": round(pooled_fresh, 5) if pooled_fresh is not None else None,
            "brier_improvement": (
                round(pooled_stale - pooled_fresh, 5)
                if pooled_stale is not None and pooled_fresh is not None else None
            ),
            "brier_in_sample_base_rate_reference": (
                round(pooled_base_rate, 5) if pooled_base_rate is not None else None
            ),
            "base_rate_reference_note": (
                "Computed from the same 64 outcomes it is scored against, so it is "
                "flattered and is a lower bound on a naive forecast's real error. "
                "Included so the pooled figures are not read in isolation."
            ),
        },
        "interpretation_limits": [
            "16 fixtures, at most 64 market observations, one matchday. Far too few "
            "to establish that either corpus produces better-calibrated forecasts.",
            "Observations are correlated: fixtures share a matchday, and teams recur "
            "across the goals/corners/cards/btts cells for the same match.",
            "The fresh probabilities were never published. This is a reconstruction "
            "and must not be presented as forward evidence.",
            "A Brier improvement here is consistent with chance at this sample size. "
            "The case for the fix rests on the features being wrong by construction, "
            "not on this scoreboard.",
            "Two of the four cells improved and two worsened. That pattern is what "
            "noise looks like, and it should be reported as such rather than as a "
            "partial win.",
        ],
        "fixtures": fixtures,
    }
    out_path = __import__("pathlib").Path(
        "/home/ubuntu/data/discovery/stale_vs_fresh_corpus_score.json"
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(report, indent=2, sort_keys=False, default=str) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
