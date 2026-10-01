"""Run frozen V3.5 against cached post-artifact fixtures/markets.

No network calls. Results are diagnostic unless the audited V32.1 settlement
evidence gate passes.
"""
from __future__ import annotations

import datetime as dt
import glob
import json
import math
import os
from pathlib import Path

from src.research.evidence_v32.settlement import (
    cached_score_evidence,
    stable_regulation_score,
)
from src.research.v35_frontier.market import corner_comparison, goal_comparisons
from src.research.v35_frontier.model import load_artifact
from src.research.v35_frontier.runtime import load_evidence, predict_bundle

ROOT = Path(__file__).resolve().parents[2]
SPEC_PATH = ROOT / "research/v35_frontier/CACHED_REPLAY_TEST_V1_SPEC.json"
ARTIFACT_PATH = ROOT / "research/v35_frontier/V35_MODEL_ARTIFACT_V1.json"
OUT = ROOT / "research/v35_frontier/out/cache_replay_v1"
CACHE = Path("/home/ubuntu/data/v3_pilot/provider_cache")


def _utc_ts(value: str) -> float:
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()


def _obs_from_path(path: str | Path) -> float:
    return float(Path(path).name.split("_", 1)[0])


def _records() -> dict[str, list[tuple[float, dict, str]]]:
    out: dict[str, list[tuple[float, dict, str]]] = {}
    patterns = [
        CACHE / "matches/*/*.json",
        CACHE / "upcoming/*/*.json",
    ]
    for pattern in patterns:
        for fn in glob.glob(str(pattern)):
            try:
                obs = _obs_from_path(fn)
                payload = json.loads(Path(fn).read_text())
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            data = payload.get("data", []) if isinstance(payload, dict) else []
            if not isinstance(data, list):
                continue
            for row in data:
                mid = str(row.get("id") or "")
                if mid:
                    out.setdefault(mid, []).append((obs, row, fn))
    for mid in out:
        out[mid].sort(key=lambda x: x[0])
    return out


def _coherent_regulation(row: dict) -> tuple[int, int] | None:
    if str(row.get("status") or "").lower() not in {"finished", "complete", "played"}:
        return None
    score = row.get("score") or {}
    reg = score.get("regulation")
    if not isinstance(reg, dict):
        return None
    try:
        home, away = int(reg["home"]), int(reg["away"])
        top_home, top_away = int(score["home"]), int(score["away"])
    except (KeyError, TypeError, ValueError):
        return None
    if min(home, away) < 0 or (home, away) != (top_home, top_away):
        return None
    if score.get("went_to_extra_time") is True or score.get("went_to_penalties") is True:
        return None
    return home, away


def _detail_final(mid: str) -> tuple[tuple[int, int], float, str] | None:
    candidates = []
    for fn in glob.glob(str(CACHE / "match_detail" / mid / "*.json")):
        try:
            obs = _obs_from_path(fn)
            payload = json.loads(Path(fn).read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        data = payload.get("data", payload) if isinstance(payload, dict) else {}
        score = _coherent_regulation(data)
        if score is not None:
            candidates.append((obs, score, fn))
    if not candidates:
        return None
    obs, score, fn = max(candidates)
    return score, obs, fn


def _finished_corners(mid: str) -> tuple[int, int] | None:
    path = CACHE / "finished_stats" / f"{mid}.json"
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text())
        payload = obj.get("payload", obj)
        allv = (((payload.get("data") or {}).get("overview") or {})
                .get("corner_kicks") or {}).get("all")
        if not isinstance(allv, dict):
            return None
        return int(allv["home"]), int(allv["away"])
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return None


def _latest_pre_odds(mid: str, kickoff: float) -> tuple[float, dict, str] | None:
    rows = []
    for fn in glob.glob(str(CACHE / "odds" / mid / "*.json")):
        try:
            obs = _obs_from_path(fn)
            if obs >= kickoff:
                continue
            payload = json.loads(Path(fn).read_text())
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        rows.append((obs, payload, fn))
    return max(rows, key=lambda x: x[0]) if rows else None


def _grade(side: str, line: float, value: int) -> str:
    side = side.upper()
    if value == line:
        return "PUSH"
    won = value > line if side == "OVER" else value < line
    return "WIN" if won else "LOSS"


def _diagnostic_grade(comparison: dict, score: tuple[int, int] | None,
                      corners: tuple[int, int] | None) -> dict | None:
    family = comparison["market_family"]
    if family == "goals":
        if score is None:
            return None
        value = score[0] + score[1]
    elif family == "corners":
        if corners is None:
            return None
        value = corners[0] + corners[1]
    else:
        return None
    return {
        "status": _grade(comparison["side"], float(comparison["line"]), int(value)),
        "realized_value": int(value),
        "side": comparison["side"],
        "line": float(comparison["line"]),
        "label": "NON_LEDGER_DIAGNOSTIC",
    }


def _official_score_gate(mid: str, kickoff: float) -> dict:
    cache_dir = CACHE / "match_detail" / mid
    evidence = cached_score_evidence(cache_dir, kickoff_ts=kickoff)
    stable = stable_regulation_score(evidence)
    return {
        "eligible_evidence_count": len(evidence),
        "passes": stable is not None,
        "stable_score": None if stable is None else [stable.home, stable.away],
        "latest_eligible_observed_at": (
            None if not evidence else evidence[-1].observed_at
        ),
    }


def main() -> None:
    if OUT.exists():
        raise RuntimeError(f"immutable replay output already exists: {OUT}")
    spec = json.loads(SPEC_PATH.read_text())
    artifact = load_artifact(ARTIFACT_PATH)
    if artifact["artifact_sha256"] != spec["artifact_sha256"]:
        raise RuntimeError("artifact does not match frozen replay spec")
    evidence_rows = load_evidence()
    records = _records()
    cutoff = float(spec["artifact_last_training_or_calibration_kickoff_ts"])

    fixtures = []
    for mid, versions in sorted(records.items()):
        latest = versions[-1][1]
        try:
            kickoff = _utc_ts(latest["utc_date"])
        except (KeyError, TypeError, ValueError):
            continue
        if kickoff <= cutoff:
            continue
        odds = _latest_pre_odds(mid, kickoff)
        if odds is None:
            continue

        finished_records = [
            (obs, row, fn, _coherent_regulation(row))
            for obs, row, fn in versions
            if _coherent_regulation(row) is not None
        ]
        if finished_records:
            obs, finished, final_src, score = max(finished_records, key=lambda x: x[0])
            outcome_source = "MATCH_LIST_FINISHED"
        else:
            detail = _detail_final(mid)
            if detail is None:
                continue
            score, obs, final_src = detail
            finished = latest
            outcome_source = "DETAIL_FINISHED_SUPPLEMENTAL"

        fixture = {
            "match_id": mid,
            "competition_id": str(latest["competition_id"]),
            "season_id": str(latest.get("season_id") or ""),
            "kickoff_ts": kickoff,
            "kickoff": str(latest["utc_date"]),
            "utc_date": str(latest["utc_date"]),
            "home_id": str(latest["home_team"]["id"]),
            "home_name": str(latest["home_team"].get("name") or ""),
            "away_id": str(latest["away_team"]["id"]),
            "away_name": str(latest["away_team"].get("name") or ""),
            "is_neutral": latest.get("is_neutral"),
        }
        odds_obs, odds_payload, odds_file = odds
        bundle = predict_bundle(
            fixture, evidence_rows=evidence_rows, artifact=artifact
        )
        comparisons = []
        if bundle.get("goals") is not None:
            comparisons.extend(goal_comparisons(bundle["goals"], odds_payload))
        if bundle.get("corners") is not None:
            cc = corner_comparison(bundle["corners"], odds_payload)
            if cc is not None:
                comparisons.append(cc)

        corners = _finished_corners(mid)
        for cmp in comparisons:
            cmp["diagnostic_grade"] = _diagnostic_grade(cmp, score, corners)

        fixtures.append({
            "fixture": fixture,
            "cohort": (
                "PRIMARY_FINISHED"
                if outcome_source == "MATCH_LIST_FINISHED"
                else "SUPPLEMENTAL_DIAGNOSTIC"
            ),
            "outcome_source": outcome_source,
            "outcome_source_file": final_src,
            "regulation_score": list(score),
            "corners": None if corners is None else list(corners),
            "odds_observed_at": odds_obs,
            "odds_hours_before_kickoff": (kickoff - odds_obs) / 3600.0,
            "odds_file": odds_file,
            "model_abstentions": bundle["abstentions"],
            "model_artifact_hash": bundle["artifact_hash"],
            "comparisons": comparisons,
            "official_settlement_gate": _official_score_gate(mid, kickoff),
        })

    qualified = []
    for fx in fixtures:
        for cmp in fx["comparisons"]:
            if cmp.get("qualifies"):
                qualified.append({
                    "match_id": fx["fixture"]["match_id"],
                    "home": fx["fixture"]["home_name"],
                    "away": fx["fixture"]["away_name"],
                    "cohort": fx["cohort"],
                    "kickoff": fx["fixture"]["kickoff"],
                    "odds_observed_at": fx["odds_observed_at"],
                    "market_family": cmp["market_family"],
                    "line": cmp["line"],
                    "side": cmp["side"],
                    "p_model_selected": cmp["p_model_selected"],
                    "p_market_novig_selected": cmp["p_market_novig_selected"],
                    "model_minus_market_novig": cmp["model_minus_market_novig"],
                    "price_decimal": cmp["price_decimal"],
                    "diagnostic_grade": cmp["diagnostic_grade"],
                    "official_settlement": (
                        "ELIGIBLE"
                        if fx["official_settlement_gate"]["passes"]
                        else "UNSETTLED"
                    ),
                })

    summary = {
        "version": spec["version"],
        "artifact_sha256": artifact["artifact_sha256"],
        "fixture_count": len(fixtures),
        "primary_finished_count": sum(f["cohort"] == "PRIMARY_FINISHED" for f in fixtures),
        "supplemental_count": sum(f["cohort"] == "SUPPLEMENTAL_DIAGNOSTIC" for f in fixtures),
        "qualified_disagreement_count": len(qualified),
        "qualified_diagnostic_wins": sum(
            q["diagnostic_grade"] and q["diagnostic_grade"]["status"] == "WIN"
            for q in qualified
        ),
        "qualified_diagnostic_losses": sum(
            q["diagnostic_grade"] and q["diagnostic_grade"]["status"] == "LOSS"
            for q in qualified
        ),
        "qualified_diagnostic_ungraded": sum(q["diagnostic_grade"] is None for q in qualified),
        "official_settled_count": sum(
            f["official_settlement_gate"]["passes"] for f in fixtures
        ),
        "scientific_status": spec["scientific_status"],
    }

    OUT.mkdir(parents=True)
    (OUT / "results.json").write_text(json.dumps({
        "summary": summary,
        "qualified_disagreements": qualified,
        "fixtures": fixtures,
    }, indent=2, sort_keys=True, default=str) + "\n")
    (OUT / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n"
    )
    print(json.dumps({
        "summary": summary,
        "qualified_disagreements": qualified,
    }, indent=2, sort_keys=True, default=str))


if __name__ == "__main__":
    main()
