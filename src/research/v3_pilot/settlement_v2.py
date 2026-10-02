"""Stable, append-only settlement path for the frozen V3 pilot.

This module repairs settlement evidence only. It does not alter declarations,
models, probabilities, market snapshots, selection rules, or frozen evidence.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import ledger
from .config import DATA_ROOT, PROVIDER_CACHE, SETTLEMENT_LOG
from .provider import ProviderBudgetStop, V3Provider
from .telegram import send, settlement_message

COMPLETION_BUFFER_SECONDS = 4 * 3600
MIN_STABLE_SNAPSHOTS = 2
MIN_STABLE_SPAN_SECONDS = 5 * 60
SETTLEMENT_VERSION = "V3_SETTLEMENT_STABLE_2"

@dataclass(frozen=True)
class ScoreEvidence:
    home: int
    away: int
    observed_at: float
    payload_hash: str

class SettlementEvidenceError(RuntimeError):
    pass

def _now_iso(ts: float | None = None) -> str:
    return datetime.fromtimestamp(time.time() if ts is None else ts, timezone.utc).isoformat()

def _append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        fh.flush()

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

def cached_score_evidence(cache_dir: Path, *, kickoff_ts: float) -> list[ScoreEvidence]:
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
    dedup = {(r.observed_at, r.payload_hash): r for r in rows}
    return sorted(dedup.values(), key=lambda r: (r.observed_at, r.payload_hash))

def stable_regulation_score(evidence: list[ScoreEvidence]) -> tuple[ScoreEvidence, ScoreEvidence] | None:
    if len(evidence) < MIN_STABLE_SNAPSHOTS:
        return None
    last = evidence[-1]
    same = [r for r in evidence if (r.home, r.away) == (last.home, last.away)]
    if len(same) < MIN_STABLE_SNAPSHOTS:
        return None
    prev, last_same = same[-2], same[-1]
    if last_same.observed_at - prev.observed_at < MIN_STABLE_SPAN_SECONDS:
        return None
    if any((r.home, r.away) != (last.home, last.away)
           for r in evidence if r.observed_at > prev.observed_at):
        return None
    return prev, last_same

def _closing_for(declaration: dict) -> dict | None:
    from .pipeline import _closing_for as parent_closing
    return parent_closing(declaration)

def _settle_result(declaration: dict, *, home: int, away: int) -> tuple[str, float, str]:
    family = str(declaration["market_family"])
    if family != "goals":
        raise SettlementEvidenceError(f"stable v2 only supports V3 goals settlement here: {family}")
    value = float(home + away)
    line = float(declaration["line"])
    side = str(declaration["side"]).upper()
    if value == line:
        result = "PUSH"
    else:
        won = value > line if side == "OVER" else value < line
        result = "WIN" if won else "LOSS"
    return result, value, "total_goals"

def safe_settle_due(provider: V3Provider) -> dict:
    now = time.time()
    existing = ledger.settlements()
    declarations = [
        d for d in ledger.declarations()
        if d.get("origin") == "V3_AUTOMATED_THESTATSAPI_PROSPECTIVE"
        and str(d.get("hypothesis_id")) not in existing
        and str(d.get("market_family")) == "goals"
    ]
    settled_events = []

    for d in sorted(declarations, key=lambda x: x.get("kickoff_utc", "")):
        kickoff = datetime.fromisoformat(
            str(d["kickoff_utc"]).replace("Z", "+00:00")
        ).timestamp()
        if now < kickoff + COMPLETION_BUFFER_SECONDS:
            continue
        mid = str(d["fixture_id"])
        try:
            payload, _, payload_hash = provider.match_detail(mid)
        except ProviderBudgetStop:
            break
        if not payload:
            continue
        evidence = cached_score_evidence(
            PROVIDER_CACHE / "match_detail" / mid,
            kickoff_ts=kickoff,
        )
        stable = stable_regulation_score(evidence)
        _append_jsonl(DATA_ROOT / "settlement_v2_evidence.jsonl", {
            "event_type": "SETTLEMENT_EVIDENCE_CHECK",
            "settlement_version": SETTLEMENT_VERSION,
            "hypothesis_id": d["hypothesis_id"],
            "fixture_id": mid,
            "observed_at_utc": _now_iso(),
            "latest_payload_hash": payload_hash,
            "eligible_snapshots": len(evidence),
            "stable": stable is not None,
        })
        if stable is None:
            continue

        prev, last = stable
        result, value, unit = _settle_result(
            d, home=last.home, away=last.away
        )
        settlement = {
            "result": result,
            "settled_value": value,
            "settled_unit": unit,
            "final_score": f"{d['fixture']} {last.home}-{last.away}",
            "verification_class": "THESTATSAPI_STABLE_POSTBUFFER_V2",
            "closing_benchmark": _closing_for(d),
            "source_payload_hashes": {
                "match_detail_stable_1": prev.payload_hash,
                "match_detail_stable_2": last.payload_hash,
            },
        }
        event = ledger.append_settlement(str(d["hypothesis_id"]), settlement)
        if event is None:
            continue
        settled_events.append((event, d))
        _append_jsonl(SETTLEMENT_LOG, event)
        try:
            ledger.git_commit(
                [ledger.LEAN_LEDGER],
                f"Settle V3 pilot test {d.get('test_number')} with stable v2 evidence",
            )
        except Exception as exc:
            _append_jsonl(DATA_ROOT / "ops_errors.jsonl", {
                "event_type": "GIT_COMMIT_FAILED",
                "observed_at_utc": _now_iso(),
                "hypothesis_id": d["hypothesis_id"],
                "error": str(exc)[:300],
            })

        ok, detail_msg = send(settlement_message(event, d))
        _append_jsonl(DATA_ROOT / "telegram_delivery.jsonl", {
            "event_type": "SETTLEMENT_TELEGRAM",
            "settlement_version": SETTLEMENT_VERSION,
            "hypothesis_id": d["hypothesis_id"],
            "ok": ok,
            "detail": detail_msg,
            "observed_at_utc": _now_iso(),
        })
    return {
        "settlement_version": SETTLEMENT_VERSION,
        "settled": len(settled_events),
        "pilot_status": ledger.pilot_status(),
        "requests": provider.requests,
    }
