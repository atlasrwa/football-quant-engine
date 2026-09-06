#!/usr/bin/env python3
"""End-to-end verification of the corpus freshness fix, against real data.

Four claims, each checked against the live corpus and the live fixture universe rather
than against fixtures in a test:

1. A fresh forecast run uses current-season matches. Shows the data cutoff and the
   newest observation per team for real in-scope fixtures.
2. The freshness gate fires when the corpus is artificially aged.
3. The content hash changes with content and is stable across rebuilds.
4. The leakage assertion refuses a same-day result being used as its own input.

Read-only with respect to the provider and the ledger: it fits models and evaluates
gates, and writes nothing except its own report to stdout.

USAGE
=====
    python3 scripts/verify_corpus_freshness_fix.py
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone
from typing import Any

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.research.prediction_engine.broadcast.corpus_freshness import (
    CorpusFreshnessError,
    FreshnessState,
    evaluate_corpus_freshness,
    in_scope_kickoffs,
    require_fresh_corpus,
)
from src.research.prediction_engine.broadcast.corpus_snapshot import (
    CorpusFingerprint,
    SameMatchLeakageError,
    assert_fixture_absent_from_history,
    build_snapshot,
    fingerprint_matches,
    observations_per_season,
)
from src.research.prediction_engine.broadcast.scope_config import load_scope_config

DAY = 86400.0


def _iso(unix: float) -> str:
    return datetime.fromtimestamp(float(unix), timezone.utc).isoformat()


def check_1_fresh_run_uses_current_season() -> dict[str, Any]:
    """Fit the engine and show, per team, the newest match it actually holds."""
    import forecast_broadcast as fb
    import pilotC_stat_mixer as mix

    config = load_scope_config(require_recorded_change=False)
    universe = fb.load_fixture_universe()
    now = time.time()
    kickoffs = in_scope_kickoffs(universe, config.is_in_scope)

    engine = fb.ForecastEngine(
        config, reference_kickoffs=kickoffs, snapshot_cutoff_unix=now
    )

    out: dict[str, Any] = {
        "data_cutoff_utc": engine.data_cutoff_utc,
        "snapshot_cutoff_utc": engine.snapshot_cutoff_utc,
        "model_version": engine.model_version,
        "corpus_provenance": engine.corpus_provenance(),
        "freshness_gate": engine.freshness.to_dict()["state"],
        "current_season_coverage": {
            season_id: coverage
            for season_id, coverage in engine.season_coverage.items()
            if coverage.get("season") == "2026/2027"
        },
        "fixtures": [],
    }

    # Real in-scope fixtures still ahead of kickoff, so this is the genuine forward
    # case rather than a replay.
    upcoming = sorted(
        (
            (float(info["ts"]), fid, info)
            for fid, info in universe.items()
            if config.is_in_scope(info.get("comp")) and float(info.get("ts", 0)) > now
        )
    )[:4]

    for kickoff, fixture_id, info in upcoming:
        home, away = str(info.get("home") or ""), str(info.get("away") or "")
        newest = engine.newest_observations(home, away)
        probs, reasons = engine.probabilities(
            home_team=home, away_team=away, kickoff_unix=kickoff
        )
        entry: dict[str, Any] = {
            "fixture_id": fixture_id,
            "fixture": f"{home} vs {away}",
            "kickoff_utc": _iso(kickoff),
            "newest_observation_per_team": {},
            "probabilities": {
                f"{market}|{line}": (round(p, 4) if p is not None else None)
                for (market, line), p in probs.items()
            },
        }
        for team, observation in newest.items():
            if observation is None:
                entry["newest_observation_per_team"][team] = None
                continue
            entry["newest_observation_per_team"][team] = {
                "kickoff_utc": observation["kickoff_utc"],
                "season": observation["season"],
                "days_before_this_fixture": round(
                    (kickoff - observation["kickoff_unix"]) / DAY, 1
                ),
                "match": f"{observation['home_name']} vs {observation['away_name']}",
            }
        entry["all_teams_have_current_season_form"] = all(
            (o or {}).get("season") == "2026/2027" for o in newest.values()
        )
        out["fixtures"].append(entry)

    out["PASS"] = (
        out["corpus_provenance"]["corpus_seasons"].count("2026/2027") == 1
        and out["freshness_gate"] == "FRESH"
        and all(f["all_teams_have_current_season_form"] for f in out["fixtures"])
    )
    return out


def check_2_gate_fires_when_aged() -> dict[str, Any]:
    """Artificially age the corpus and confirm the gate refuses publication."""
    import forecast_broadcast as fb
    import pilotC_stat_mixer as mix

    config = load_scope_config(require_recorded_change=False)
    universe = fb.load_fixture_universe()
    now = time.time()
    kickoffs = in_scope_kickoffs(universe, config.is_in_scope)
    matches = mix.load_corpus()

    live = evaluate_corpus_freshness(
        fingerprint=fingerprint_matches(matches),
        reference_kickoffs=kickoffs,
        now_unix=now,
    )

    # Age the corpus by dropping everything from the current season — exactly the
    # pre-fix state, reconstructed from the same data.
    aged = [m for m in matches if str(m.get("season")) != "2026/2027"]
    aged_verdict = evaluate_corpus_freshness(
        fingerprint=fingerprint_matches(aged),
        reference_kickoffs=kickoffs,
        now_unix=now,
    )

    raised = False
    detail = ""
    try:
        require_fresh_corpus(
            fingerprint=fingerprint_matches(aged),
            reference_kickoffs=kickoffs,
            now_unix=now,
        )
    except CorpusFreshnessError as exc:
        raised = True
        detail = exc.verdict.detail

    return {
        "live_corpus_state": live.state.value,
        "live_lag_hours": live.metrics.get("corpus_lag_hours"),
        "aged_corpus_state": aged_verdict.state.value,
        "aged_lag_hours": aged_verdict.metrics.get("corpus_lag_hours"),
        "aged_may_publish": aged_verdict.may_publish,
        "require_fresh_corpus_raised": raised,
        "raised_detail": detail,
        "PASS": (
            live.state is FreshnessState.FRESH
            and aged_verdict.state is FreshnessState.STALE
            and aged_verdict.may_publish is False
            and raised
        ),
    }


def check_3_content_hash_behaviour() -> dict[str, Any]:
    """Hash tracks content; rebuild time changes nothing."""
    import pilotC_stat_mixer as mix

    matches = mix.load_corpus()
    now = time.time()

    first = fingerprint_matches(matches)
    time.sleep(0.05)
    rebuild = fingerprint_matches(list(reversed(matches)))  # different order, later time

    aged = fingerprint_matches(
        [m for m in matches if str(m.get("season")) != "2026/2027"]
    )

    # Substitution that preserves both count and newest date — the case a
    # (count, max_date) summary cannot see.
    substituted = list(matches)
    victim = dict(substituted[len(substituted) // 2])
    victim["id"] = "substituted-for-verification"
    substituted[len(substituted) // 2] = victim
    swapped = fingerprint_matches(substituted)

    # Two snapshots of the same content at different cutoffs far past every match.
    snap_a = build_snapshot(matches, cutoff_unix=now)[1]
    snap_b = build_snapshot(matches, cutoff_unix=now + 3600)[1]

    return {
        "content_hash": first.content_hash,
        "stable_across_rebuild_and_order": first.content_hash == rebuild.content_hash,
        "stable_across_build_time": snap_a.content_hash == snap_b.content_hash,
        "changes_when_current_season_removed": first.content_hash != aged.content_hash,
        "substitution_same_count_same_max_date": {
            "counts_equal": first.match_count == swapped.match_count,
            "max_dates_equal": (
                first.latest_observation_unix == swapped.latest_observation_unix
            ),
            "hash_differs": first.content_hash != swapped.content_hash,
        },
        "PASS": (
            first.content_hash == rebuild.content_hash
            and snap_a.content_hash == snap_b.content_hash
            and first.content_hash != aged.content_hash
            and first.content_hash != swapped.content_hash
        ),
    }


def check_4_leakage_refused() -> dict[str, Any]:
    """A completed fixture must not receive a forecast from a corpus containing it."""
    import pilotC_stat_mixer as mix

    matches = mix.load_corpus()
    histories = mix.build_histories(matches)

    # Pick a real, recently completed in-scope match from the corpus.
    current = [m for m in matches if str(m.get("season")) == "2026/2027"]
    target = max(current, key=lambda m: float(m["date_unix"]))
    home, away = target["home_name"], target["away_name"]
    kickoff = float(target["date_unix"])

    refused = False
    message = ""
    try:
        assert_fixture_absent_from_history(
            histories, home_team=home, away_team=away, kickoff_unix=kickoff
        )
    except SameMatchLeakageError as exc:
        refused = True
        message = str(exc)

    # The same pairing far in the future must NOT be refused, or ordinary fixtures
    # would be blocked.
    future_allowed = True
    try:
        assert_fixture_absent_from_history(
            histories, home_team=home, away_team=away, kickoff_unix=kickoff + 200 * DAY
        )
    except SameMatchLeakageError:
        future_allowed = False

    # A snapshot cut before the match must not contain it at all.
    snapshot, _ = build_snapshot(matches, cutoff_unix=kickoff)
    contains_target = any(str(m.get("id")) == str(target.get("id")) for m in snapshot)

    return {
        "tested_fixture": f"{home} vs {away}",
        "tested_kickoff_utc": _iso(kickoff),
        "same_match_refused": refused,
        "refusal_message": message[:220],
        "future_rematch_allowed": future_allowed,
        "snapshot_cut_before_kickoff_excludes_it": not contains_target,
        "PASS": refused and future_allowed and not contains_target,
    }


def main() -> int:
    report: dict[str, Any] = {
        "verification_contract": "corpus-freshness-verification/v1",
        "generated_at_utc": _iso(time.time()),
    }
    report["check_1_fresh_run_uses_current_season"] = check_1_fresh_run_uses_current_season()
    report["check_2_gate_fires_when_aged"] = check_2_gate_fires_when_aged()
    report["check_3_content_hash_behaviour"] = check_3_content_hash_behaviour()
    report["check_4_leakage_refused"] = check_4_leakage_refused()
    report["ALL_PASS"] = all(
        v.get("PASS") for k, v in report.items() if k.startswith("check_")
    )
    print(json.dumps(report, indent=2, sort_keys=False, default=str))
    return 0 if report["ALL_PASS"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
