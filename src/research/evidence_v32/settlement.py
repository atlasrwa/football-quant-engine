"""Settlement integrity for V3.2 and the V3.1 shadow path.

A provider status of finished is not sufficient evidence. TheStatsAPI has
been observed to emit transient 0-0 finished snapshots before the settled score
is populated. Settlement therefore requires post-buffer, internally coherent,
stable score evidence and remains append-only.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

COMPLETION_BUFFER_SECONDS = 4 * 3600
MIN_STABLE_SNAPSHOTS = 2
MIN_STABLE_SPAN_SECONDS = 5 * 60

@dataclass(frozen=True)
class ScoreEvidence:
    home: int
    away: int
    observed_at: float
    payload_hash: str

class SettlementEvidenceError(RuntimeError):
    pass

def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number) or number < 0 or int(number) != number:
        return None
    return int(number)

def score_from_detail(payload: dict[str, Any], observed_at: float,
                      payload_hash: str) -> ScoreEvidence | None:
    data = (payload or {}).get("data") or payload or {}
    if str(data.get("status") or "").lower() not in {"finished", "complete", "played"}:
        return None
    score = data.get("score") or {}
    regulation = score.get("regulation")

    if not isinstance(regulation, dict):
        return None
    home = _nonnegative_int(regulation.get("home"))
    away = _nonnegative_int(regulation.get("away"))
    top_home = _nonnegative_int(score.get("home"))
    top_away = _nonnegative_int(score.get("away"))
    if None in (home, away, top_home, top_away):
        return None
    if (home, away) != (top_home, top_away):
        raise SettlementEvidenceError("top-level score conflicts with regulation score")
    if score.get("went_to_extra_time") is True or score.get("went_to_penalties") is True:
        raise SettlementEvidenceError("regulation-only settlement cannot use extra-time result")
    return ScoreEvidence(home, away, float(observed_at), str(payload_hash))

def cached_score_evidence(cache_dir: Path, *, kickoff_ts: float,
                          current: ScoreEvidence | None = None) -> list[ScoreEvidence]:
    rows: list[ScoreEvidence] = []
    for path in sorted(cache_dir.glob("*.json")):
        try:
            observed_at = float(path.name.split("_", 1)[0])
            payload_hash = path.stem.split("_", 1)[1]

            payload = json.loads(path.read_text(encoding="utf-8"))
            evidence = score_from_detail(payload, observed_at, payload_hash)
        except (OSError, ValueError, json.JSONDecodeError, SettlementEvidenceError):
            continue
        if evidence is not None and evidence.observed_at >= kickoff_ts + COMPLETION_BUFFER_SECONDS:
            rows.append(evidence)
    if current is not None and current.observed_at >= kickoff_ts + COMPLETION_BUFFER_SECONDS:
        rows.append(current)
    dedup = {(r.observed_at, r.payload_hash): r for r in rows}
    return sorted(dedup.values(), key=lambda r: (r.observed_at, r.payload_hash))

def stable_regulation_score(evidence: list[ScoreEvidence]) -> ScoreEvidence | None:
    if len(evidence) < MIN_STABLE_SNAPSHOTS:
        return None
    last = evidence[-1]
    same = [r for r in evidence if (r.home, r.away) == (last.home, last.away)]
    if len(same) < MIN_STABLE_SNAPSHOTS:
        return None
    if same[-1].observed_at - same[-2].observed_at < MIN_STABLE_SPAN_SECONDS:
        return None

    if any((r.home, r.away) != (last.home, last.away)
           for r in evidence if r.observed_at > same[-2].observed_at):
        return None
    return last

def settle_binary(*, market_family: str, market: str, side: str,
                  line: float | None, home: int, away: int) -> tuple[str, Any, str]:
    family = str(market_family).lower()
    side = str(side).upper()
    if family == "btts" or str(market).upper() == "BTTS":
        occurred = home > 0 and away > 0
        selected = side == "YES"
        if side not in {"YES", "NO"}:
            raise SettlementEvidenceError(f"unsupported BTTS side {side}")
        return ("WIN" if occurred == selected else "LOSS", occurred, "both_teams_scored")
    if line is None:
        raise SettlementEvidenceError("count market requires a line")
    if family != "goals":
        raise SettlementEvidenceError(f"unsupported settlement family {market_family}")

    market_token = str(market).lower()
    if "home" in market_token and "goal" in market_token:
        value, unit = home, "home_goals"
    elif "away" in market_token and "goal" in market_token:
        value, unit = away, "away_goals"
    elif "total" in market_token and "goal" in market_token:
        value, unit = home + away, "total_goals"
    else:
        raise SettlementEvidenceError(f"ambiguous goals market {market}")
    if side not in {"OVER", "UNDER"}:
        raise SettlementEvidenceError(f"unsupported count side {side}")
    if value == float(line):
        return "PUSH", value, unit
    won = value > float(line) if side == "OVER" else value < float(line)
    return ("WIN" if won else "LOSS", value, unit)
