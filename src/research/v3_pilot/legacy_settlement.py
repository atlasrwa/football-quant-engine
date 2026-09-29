"""Safe settlement bridge for legacy lean-pilot rows 1-20.

Only provider semantics that are unambiguous are automated. Rushbet booking-point
rows remain manual because aggregate yellow/red counts do not identify second-yellow
sequences reliably enough to reproduce the sportsbook scoring contract.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from . import ledger
from .config import SETTLEMENT_LOG, STATE_PATH
from .provider import ProviderBudgetStop, V3Provider

def _norm(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())

def _kickoff_ts(value: Any) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None

def _state() -> dict:
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))

def _append_jsonl(path: Path, row: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

def _resolve_fixture(decl: dict, state: dict) -> dict | None:
    target_name = _norm(decl.get("fixture"))
    target_kickoff = _kickoff_ts(decl.get("kickoff_utc"))
    matches = []
    for fx in (state.get("fixtures") or {}).values():
        name = _norm(f"{fx.get('home_name')} vs {fx.get('away_name')}")
        if name != target_name:
            continue
        if target_kickoff is not None and abs(float(fx.get("ts", 0)) - target_kickoff) > 120:
            continue
        matches.append(fx)
    return matches[0] if len(matches) == 1 else None

def _corner_value(decl: dict, fx: dict, stats_payload: dict) -> tuple[float, str] | None:
    try:
        cv = stats_payload["data"]["overview"]["corner_kicks"]["all"]
        home = float(cv["home"])
        away = float(cv["away"])
    except (KeyError, TypeError, ValueError):
        return None
    market = str(decl.get("market") or "")
    if market == "total_corners":
        return home + away, "total_corners"
    suffix = "_team_corners"
    if not market.endswith(suffix):
        return None
    token = market[:-len(suffix)].replace("_", " ")
    team = _norm(token)
    if team == _norm(fx.get("home_name")):
        return home, f"{fx.get('home_name')}_team_corners"
    if team == _norm(fx.get("away_name")):
        return away, f"{fx.get('away_name')}_team_corners"
    return None

def _settled_result(value: float, line: float, side: str) -> str:
    if value == line:
        return "PUSH"
    won = value > line if side == "OVER" else value < line
    return "WIN" if won else "LOSS"

def settle_legacy_due(
    provider: V3Provider,
    *,
    now: float | None = None,
    settle_delay_seconds: int = 2 * 3600,
) -> dict:
    now = time.time() if now is None else float(now)
    state = _state()
    existing = ledger.settlements()
    settled: list[str] = []
    blocked: list[dict] = []
    unresolved: list[str] = []

    for decl in ledger.declarations():
        hid = str(decl.get("hypothesis_id") or "")
        if not hid or hid in existing:
            continue
        if decl.get("origin") == "V3_AUTOMATED_THESTATSAPI_PROSPECTIVE":
            continue
        kickoff = _kickoff_ts(decl.get("kickoff_utc"))
        if kickoff is None or now < kickoff + settle_delay_seconds:
            continue
        fx = _resolve_fixture(decl, state)
        if fx is None:
            unresolved.append(hid)
            continue

        family = str(decl.get("market_family") or "")
        market = str(decl.get("market") or "")
        side = str(decl.get("side") or "")
        source_hashes: dict[str, str] = {}
        settlement: dict[str, Any] | None = None

        if family == "bookings":
            blocked.append({
                "hypothesis_id": hid,
                "reason": "MANUAL_REQUIRED_RUSHBET_BOOKING_POINT_SEMANTICS",
            })
            continue

        if family == "corners":
            try:
                payload, _, payload_hash = provider.stats(str(fx["match_id"]))
            except ProviderBudgetStop:
                break
            if not payload:
                continue
            resolved = _corner_value(decl, fx, payload)
            if resolved is None:
                blocked.append({"hypothesis_id": hid, "reason": "UNSUPPORTED_CORNER_MARKET"})
                continue
            value, unit = resolved
            line = float(decl["line"])
            settlement = {
                "result": _settled_result(value, line, side),
                "settled_value": value,
                "settled_unit": unit,
                "verification_class": "THESTATSAPI_AUTOMATED_LEGACY_SETTLEMENT",
            }
            source_hashes["match_stats"] = payload_hash

        elif family == "goals":
            try:
                detail, _, detail_hash = provider.match_detail(str(fx["match_id"]))
            except ProviderBudgetStop:
                break
            if not detail:
                continue
            m = detail.get("data", detail)
            score = m.get("score") or {}
            gh, ga = score.get("home"), score.get("away")
            if gh is None or ga is None:
                continue
            gh, ga = float(gh), float(ga)
            source_hashes["match_detail"] = detail_hash
            if market == "BTTS":
                occurred = gh > 0 and ga > 0
                won = occurred if side == "YES" else not occurred
                settlement = {
                    "result": "WIN" if won else "LOSS",
                    "settled_value": occurred,
                    "settled_unit": "both_teams_scored",
                    "verification_class": "THESTATSAPI_AUTOMATED_LEGACY_SETTLEMENT",
                }
            elif market == "total_goals":
                value = gh + ga
                settlement = {
                    "result": _settled_result(value, float(decl["line"]), side),
                    "settled_value": value,
                    "settled_unit": "total_goals",
                    "verification_class": "THESTATSAPI_AUTOMATED_LEGACY_SETTLEMENT",
                }
            if settlement is not None:
                settlement["final_score"] = f"{decl.get('fixture')} {int(gh)}-{int(ga)}"

        if settlement is None:
            continue
        settlement["source_payload_hashes"] = source_hashes
        event = ledger.append_settlement(hid, settlement)
        if event is None:
            continue
        settled.append(hid)
        _append_jsonl(SETTLEMENT_LOG, event)
        ledger.git_commit([ledger.LEAN_LEDGER], f"Settle legacy pilot row {hid}")

    return {
        "settled": len(settled),
        "settled_hypothesis_ids": settled,
        "manual_required": blocked,
        "unresolved_fixture_ids": unresolved,
        "requests": provider.requests,
    }
