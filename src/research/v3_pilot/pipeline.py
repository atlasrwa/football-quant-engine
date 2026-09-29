"""End-to-end V3 pilot orchestration."""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import ledger
from .config import (
    DATA_ROOT, DISCOVERY_HOURS, DISCOVERY_REFRESH_SECONDS, EVIDENCE_DIR,
    EARLY_WINDOW, FINAL_WINDOW, MID_WINDOW, OBSERVATION_LOG,
    PREDICTION_ROOT, SETTLEMENT_LOG, SHADOW_LOG, STATE_PATH, load_scope,
)
from .freeze import freeze_hash, load_freeze
from .market import corner_comparison, devig, goal_comparisons
from .model import (
    InsufficientHistory, canonical_hash, fit_goal_calibrators,
    predict_corners, predict_goals,
)
from .provider import ProviderBudgetStop, V3Provider
from .telegram import declaration_message, send, settlement_message

FREEZE = load_freeze()

def _now_iso(ts: float | None = None) -> str:
    value = time.time() if ts is None else ts
    return datetime.fromtimestamp(value, timezone.utc).isoformat()

def _atomic_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)

def _append_jsonl(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())

def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            out.append(json.loads(line))
    return out

def _state() -> dict:
    if not STATE_PATH.exists():
        return {"last_discovery_at": 0.0, "fixtures": {}, "vintages": {}, "telegram": {}}
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise RuntimeError("V3 state file is corrupt; refusing to continue")

def _save_state(state: dict) -> None:
    _atomic_json(STATE_PATH, state)

def _fixture_dir(match_id: str) -> Path:
    return PREDICTION_ROOT / str(match_id)

def _freeze_path(match_id: str, family: str) -> Path:
    return _fixture_dir(match_id) / f"{family}.json"

def _load_freeze_artifact(match_id: str, family: str) -> dict | None:
    p = _freeze_path(match_id, family)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))

def _write_freeze_artifact(match_id: str, family: str, obj: dict) -> dict:
    p = _freeze_path(match_id, family)
    raw = json.dumps(obj, sort_keys=True, indent=2, default=str).encode()
    if p.exists():
        if p.read_bytes() != raw:
            raise RuntimeError(f"immutable {family} freeze collision for {match_id}")
        return obj
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".json.tmp")
    tmp.write_bytes(raw)
    os.replace(tmp, p)
    return obj

def _calibration_path(comp_id: str, target_season: str, history_hash: str) -> Path:
    return DATA_ROOT / "calibration" / comp_id / f"{target_season}_{history_hash}.json"

def _goal_freeze(provider: V3Provider, fixture: dict) -> dict:
    existing = _load_freeze_artifact(fixture["match_id"], "goals")
    if existing:
        return existing
    history = provider.refresh_history(fixture["competition_id"])
    rows = history["matches"]
    cal_path = _calibration_path(
        fixture["competition_id"], fixture["season_id"], history["history_hash"]
    )
    if cal_path.exists():
        calibrator = json.loads(cal_path.read_text(encoding="utf-8"))
    else:
        calibrator = fit_goal_calibrators(rows, fixture["season_id"])
        _atomic_json(cal_path, calibrator)
    distribution = predict_goals(rows, fixture, calibrator)
    observed = time.time()
    art = {
        "record_type": "V3_FROZEN_DISTRIBUTION",
        "family": "goals",
        "fixture": fixture,
        "frozen_at": observed,
        "frozen_at_utc": _now_iso(observed),
        "information_cutoff": observed,
        "freeze_contract_sha256": freeze_hash(),
        "provider": "THESTATSAPI_ONLY",
        "history_snapshot_hash": history["history_hash"],
        "history_observed_at": history["observed_at"],
        "distribution": distribution,
    }
    art["artifact_hash"] = canonical_hash(art)
    _write_freeze_artifact(fixture["match_id"], "goals", art)
    _append_jsonl(SHADOW_LOG, {
        "event_type": "MODEL_DISTRIBUTION_FROZEN", **art
    })
    return art

def _corner_freeze(provider: V3Provider, fixture: dict) -> dict:
    existing = _load_freeze_artifact(fixture["match_id"], "corners")
    if existing:
        return existing
    history = provider.refresh_history(fixture["competition_id"])
    rows = provider.corner_history(history, fixture)
    distribution = predict_corners(rows, rows, fixture)
    observed = time.time()
    art = {
        "record_type": "V3_FROZEN_DISTRIBUTION",
        "family": "corners",
        "fixture": fixture,
        "frozen_at": observed,
        "frozen_at_utc": _now_iso(observed),
        "information_cutoff": observed,
        "freeze_contract_sha256": freeze_hash(),
        "provider": "THESTATSAPI_ONLY",
        "history_snapshot_hash": history["history_hash"],
        "corner_rows_count": len(rows),
        "distribution": distribution,
    }
    art["artifact_hash"] = canonical_hash(art)
    _write_freeze_artifact(fixture["match_id"], "corners", art)
    _append_jsonl(SHADOW_LOG, {
        "event_type": "MODEL_DISTRIBUTION_FROZEN", **art
    })
    return art

def discover(provider: V3Provider, *, force: bool = False) -> dict:
    state = _state()
    now = time.time()
    if not force and now - float(state.get("last_discovery_at", 0)) < DISCOVERY_REFRESH_SECONDS:
        return {"skipped": True, "fixtures": len(state.get("fixtures", {}))}
    scope = load_scope()
    found = 0
    for comp in scope:
        try:
            rows = provider.upcoming(comp["competition_id"], hours=DISCOVERY_HOURS)
        except ProviderBudgetStop:
            break
        for fx in rows:
            found += 1
            prior = state["fixtures"].get(fx["match_id"])
            state["fixtures"][fx["match_id"]] = fx
            if prior is None:
                _append_jsonl(DATA_ROOT / "fixtures.jsonl", {
                    "event_type": "FIXTURE_DISCOVERED",
                    "observed_at_utc": _now_iso(),
                    "scope_name": comp["name"],
                    **fx,
                })
    state["last_discovery_at"] = now
    _save_state(state)
    return {"skipped": False, "fixtures_discovered": found, "requests": provider.requests}

def _vintage_due(state: dict, fixture: dict, vintage: str, now: float) -> bool:
    stk = float(fixture["ts"]) - now
    windows = {"EARLY": EARLY_WINDOW, "MID": MID_WINDOW, "FINAL": FINAL_WINDOW}
    low, high = windows[vintage]
    if not (low <= stk <= high):
        return False
    key = f"{fixture['match_id']}:{vintage}"
    return not bool(state.get("vintages", {}).get(key))

def _mark_vintage(state: dict, fixture: dict, vintage: str, observed: float) -> None:
    state.setdefault("vintages", {})[f"{fixture['match_id']}:{vintage}"] = observed

def _fixture_market_observed(fixture_id: str) -> bool:
    return any(
        r.get("event_type") == "MARKET_OBSERVED"
        and str(r.get("fixture_id")) == str(fixture_id)
        for r in _read_jsonl(OBSERVATION_LOG)
    )

def _qualifier_key(fixture_id: str, cmp: dict) -> str:
    return f"{fixture_id}:{cmp['market_family']}:{float(cmp['line']):.1f}:{cmp['side']}"

def _hypothesis_id(fixture: dict, cmp: dict) -> str:
    suffix = re.sub(r"[^A-Za-z0-9]+", "", str(fixture["match_id"]))[-12:]
    family = "GOALS" if cmp["market_family"] == "goals" else "CORNERS"
    line = str(cmp["line"]).replace(".", "")
    return f"QFE-V3-{suffix}-{family}-{line}-{cmp['side']}"

def _candidate(fixture: dict, cmp: dict, family_art: dict, observed: float,
               odds_hash: str, vintage: str) -> tuple[dict, dict]:
    selected = cmp["side"]
    model_version = family_art["distribution"]["version"]
    signal = {
        "hypothesis_id": _hypothesis_id(fixture, cmp),
        "fixture": f"{fixture['home_name']} vs {fixture['away_name']}",
        "fixture_id": fixture["match_id"],
        "market_family": cmp["market_family"],
        "market": cmp["market"],
        "side": selected,
        "line": cmp["line"],
        "price_decimal": cmp["price_decimal"],
        "opposite_price_decimal": cmp["opposite_price_decimal"],
        "kickoff_utc": fixture["utc_date"],
        "prediction_observed_at_utc": family_art["frozen_at_utc"],
        "market_observed_at_utc": _now_iso(observed),
        "cluster_id": f"{fixture['match_id']}:{cmp['market_family']}",
        "model": {
            "version": model_version,
            "distribution_hash": family_art["distribution"]["distribution_hash"],
            "p_selected": cmp["p_model_selected"],
            "p_over": cmp["p_model_over"],
        },
        "market_benchmark": {
            "bookmaker": "Bet365",
            "price_field": "last_seen observed prospectively",
            "vintage": vintage,
            "selected_odds": cmp["price_decimal"],
            "opposite_odds": cmp["opposite_price_decimal"],
            "raw_break_even_selected": cmp["raw_break_even_selected"],
            "two_way_overround": cmp["two_way_overround"],
            "no_vig_selected": cmp["p_market_novig_selected"],
            "model_minus_no_vig": cmp["model_minus_market_novig"],
            "opening": cmp.get("opening"),
            "odds_payload_hash": odds_hash,
        },
    }
    evidence = {
        "schema_version": "qfe-v3-evidence/1",
        "fixture": fixture,
        "freeze_contract_sha256": freeze_hash(),
        "family_freeze": family_art,
        "market_comparison": cmp,
        "market_observed_at": observed,
        "market_observed_at_utc": _now_iso(observed),
        "odds_payload_hash": odds_hash,
        "vintage": vintage,
        "selection_rule": FREEZE["selection"],
    }
    return signal, evidence

def evaluate_due(provider: V3Provider, *, dry_run: bool = False) -> dict:
    state = _state()
    now = time.time()
    scope = {r["competition_id"]: r for r in load_scope()}
    candidates: list[tuple[dict, dict, dict]] = []
    observations = 0
    freezes = 0

    fixtures = [
        fx for fx in state.get("fixtures", {}).values()
        if now < float(fx["ts"]) <= now + DISCOVERY_HOURS*3600
        and fx.get("competition_id") in scope
    ]
    fixtures.sort(key=lambda x: (x["ts"], x["match_id"]))

    for fixture in fixtures:
        stk = float(fixture["ts"]) - now
        if stk <= 0 or stk > 32*3600:
            continue
        comp = scope[fixture["competition_id"]]

        market_seen = _fixture_market_observed(fixture["match_id"])
        goal_art = _load_freeze_artifact(fixture["match_id"], "goals")
        if goal_art is None and market_seen:
            _append_jsonl(SHADOW_LOG, {
                "event_type": "GOALS_ABSTAIN", "fixture_id": fixture["match_id"],
                "observed_at_utc": _now_iso(),
                "reason": "POST_MARKET_MODEL_FREEZE_FORBIDDEN",
            })
        elif goal_art is None:
            try:
                goal_art = _goal_freeze(provider, fixture)
            except (InsufficientHistory, ProviderBudgetStop, RuntimeError) as exc:
                _append_jsonl(SHADOW_LOG, {
                    "event_type": "GOALS_ABSTAIN",
                    "fixture_id": fixture["match_id"],
                    "observed_at_utc": _now_iso(),
                    "reason": type(exc).__name__ + ":" + str(exc)[:240],
                })
        if goal_art is not None:
            freezes += 1

        corner_art = _load_freeze_artifact(fixture["match_id"], "corners")
        if comp.get("corners") and corner_art is None and market_seen:
            _append_jsonl(SHADOW_LOG, {
                "event_type": "CORNERS_ABSTAIN", "fixture_id": fixture["match_id"],
                "observed_at_utc": _now_iso(),
                "reason": "POST_MARKET_MODEL_FREEZE_FORBIDDEN",
            })
        elif comp.get("corners") and corner_art is None:
            try:
                corner_art = _corner_freeze(provider, fixture)
            except (InsufficientHistory, ProviderBudgetStop, RuntimeError) as exc:
                _append_jsonl(SHADOW_LOG, {
                    "event_type": "CORNERS_ABSTAIN",
                    "fixture_id": fixture["match_id"],
                    "observed_at_utc": _now_iso(),
                    "reason": type(exc).__name__ + ":" + str(exc)[:240],
                })
        if corner_art is not None:
            freezes += 1

        due = [v for v in ("EARLY", "MID") if _vintage_due(state, fixture, v, now)]
        if not due:
            continue
        vintage = due[0]
        try:
            odds_payload, observed, odds_hash = provider.odds(fixture["match_id"])
        except ProviderBudgetStop:
            break
        if odds_payload is None:
            _mark_vintage(state, fixture, vintage, now)
            continue
        observations += 1
        _mark_vintage(state, fixture, vintage, observed)

        comps: list[tuple[dict, dict]] = []
        if goal_art is not None:
            for cmp in goal_comparisons(goal_art["distribution"], odds_payload):
                comps.append((cmp, goal_art))
        if corner_art is not None:
            cmp = corner_comparison(corner_art["distribution"], odds_payload)
            if cmp is not None:
                comps.append((cmp, corner_art))

        obs_record = {
            "event_type": "MARKET_OBSERVED",
            "fixture_id": fixture["match_id"],
            "fixture": f"{fixture['home_name']} vs {fixture['away_name']}",
            "kickoff_utc": fixture["utc_date"],
            "observed_at": observed,
            "observed_at_utc": _now_iso(observed),
            "vintage": vintage,
            "odds_payload_hash": odds_hash,
            "comparisons": [c for c, _ in comps],
        }
        _append_jsonl(OBSERVATION_LOG, obs_record)

        for cmp, art in comps:
            _append_jsonl(SHADOW_LOG, {
                "event_type": "MARKET_COMPARISON",
                "fixture_id": fixture["match_id"],
                "observed_at_utc": _now_iso(observed),
                "vintage": vintage,
                "comparison": cmp,
                "distribution_hash": art["distribution"]["distribution_hash"],
            })
            if cmp["qualifies"]:
                key = _qualifier_key(fixture["match_id"], cmp)
                existing_ids = {str(d.get("hypothesis_id")) for d in ledger.declarations()}
                signal, evidence = _candidate(
                    fixture, cmp, art, observed, odds_hash, vintage
                )
                if signal["hypothesis_id"] not in existing_ids:
                    candidates.append((fixture, signal, evidence))

    _save_state(state)

    candidates.sort(key=lambda x: (
        float(x[0]["ts"]), str(x[0]["match_id"]),
        str(x[1]["market_family"]), float(x[1]["line"]), str(x[1]["side"])
    ))
    declared = []
    if not dry_run:
        remaining = ledger.pilot_status()["remaining"]
        for _, signal, evidence in candidates[:remaining]:
            event = ledger.append_declaration(signal, evidence)
            if event is None:
                continue
            declared.append(event)
            evidence_path = EVIDENCE_DIR / f"{event['hypothesis_id']}.json"
            try:
                ledger.git_commit(
                    [ledger.LEAN_LEDGER, evidence_path],
                    f"Record V3 pilot test {event['test_number']}"
                )
            except Exception as exc:
                _append_jsonl(DATA_ROOT / "ops_errors.jsonl", {
                    "event_type": "GIT_COMMIT_FAILED",
                    "observed_at_utc": _now_iso(),
                    "hypothesis_id": event["hypothesis_id"],
                    "error": str(exc)[:300],
                })
            ok, detail = send(declaration_message(event))
            _append_jsonl(DATA_ROOT / "telegram_delivery.jsonl", {
                "event_type": "DECLARATION_TELEGRAM",
                "hypothesis_id": event["hypothesis_id"],
                "ok": ok, "detail": detail, "observed_at_utc": _now_iso(),
            })
    return {
        "fixtures_considered": len(fixtures),
        "freezes_available": freezes,
        "market_observations": observations,
        "qualifying_candidates": len(candidates),
        "declared": len(declared),
        "pilot_status": ledger.pilot_status(),
        "requests": provider.requests,
    }

def capture_final_for_declared(provider: V3Provider) -> dict:
    state = _state()
    now = time.time()
    v3_decs = [
        d for d in ledger.declarations()
        if d.get("origin") == "V3_AUTOMATED_THESTATSAPI_PROSPECTIVE"
    ]
    by_fixture = {}
    for d in v3_decs:
        by_fixture[str(d["fixture_id"])] = d
    captured = 0
    for mid, d in sorted(by_fixture.items(), key=lambda x: x[1].get("kickoff_utc", "")):
        fx = state.get("fixtures", {}).get(mid)
        if not fx or not _vintage_due(state, fx, "FINAL", now):
            continue
        try:
            payload, observed, ph = provider.odds(mid)
        except ProviderBudgetStop:
            break
        if payload is None:
            _mark_vintage(state, fx, "FINAL", now)
            continue
        goal_art = _load_freeze_artifact(mid, "goals")
        corner_art = _load_freeze_artifact(mid, "corners")
        comps = []
        if goal_art:
            comps.extend(goal_comparisons(goal_art["distribution"], payload))
        if corner_art:
            c = corner_comparison(corner_art["distribution"], payload)
            if c:
                comps.append(c)
        _append_jsonl(OBSERVATION_LOG, {
            "event_type": "MARKET_OBSERVED",
            "fixture_id": mid, "fixture": d["fixture"],
            "kickoff_utc": d["kickoff_utc"],
            "observed_at": observed, "observed_at_utc": _now_iso(observed),
            "vintage": "FINAL", "odds_payload_hash": ph,
            "comparisons": comps,
        })
        _mark_vintage(state, fx, "FINAL", observed)
        captured += 1
    _save_state(state)
    return {"final_captured": captured, "requests": provider.requests}

def _closing_for(declaration: dict) -> dict | None:
    rows = [
        r for r in _read_jsonl(OBSERVATION_LOG)
        if r.get("fixture_id") == declaration.get("fixture_id")
        and float(r.get("observed_at", 0)) > 0
    ]
    try:
        kickoff = datetime.fromisoformat(
            str(declaration["kickoff_utc"]).replace("Z", "+00:00")
        ).timestamp()
    except ValueError:
        return None
    candidates = []
    for r in rows:
        obs = float(r["observed_at"])
        if obs >= kickoff:
            continue
        for cmp in r.get("comparisons", []):
            if cmp.get("market_family") != declaration.get("market_family"):
                continue
            if abs(float(cmp.get("line")) - float(declaration.get("line"))) > 1e-9:
                continue
            candidates.append((obs, r, cmp))
    if not candidates:
        return None
    obs, rec, cmp = max(candidates, key=lambda x: x[0])
    selected_market = float(cmp["p_market_novig_selected"])
    # comparison side can flip as market crosses model; recompute selected-side
    # probability using raw side odds and the declaration's fixed side.
    over_odds = (
        cmp["price_decimal"] if cmp["side"] == "OVER"
        else cmp["opposite_price_decimal"]
    )
    under_odds = (
        cmp["price_decimal"] if cmp["side"] == "UNDER"
        else cmp["opposite_price_decimal"]
    )
    po, pu = devig(float(over_odds), float(under_odds))
    close_sel = po if declaration["side"] == "OVER" else pu
    entry = float(declaration["market_benchmark"]["no_vig_selected"])
    seconds_to_kickoff = kickoff - obs
    return {
        "observed_at_utc": rec["observed_at_utc"],
        "vintage": rec.get("vintage"),
        "closing_novig_selected": close_sel,
        "entry_novig_selected": entry,
        "movement_toward_selection": close_sel - entry,
        "seconds_to_kickoff": seconds_to_kickoff,
        "genuine_close_window": 0 <= seconds_to_kickoff <= FINAL_WINDOW[1],
        "quality": (
            "FINAL_5_20M" if 0 <= seconds_to_kickoff <= FINAL_WINDOW[1]
            else "LAST_PROSPECTIVE_BEFORE_KICKOFF"
        ),
    }

def settle_due(provider: V3Provider, *, settle_delay_seconds: int = 2*3600) -> dict:
    now = time.time()
    existing = ledger.settlements()
    v3_decs = [
        d for d in ledger.declarations()
        if d.get("origin") == "V3_AUTOMATED_THESTATSAPI_PROSPECTIVE"
        and str(d.get("hypothesis_id")) not in existing
    ]
    settled_events = []
    for d in sorted(v3_decs, key=lambda x: x.get("kickoff_utc", "")):
        kickoff = datetime.fromisoformat(
            str(d["kickoff_utc"]).replace("Z", "+00:00")
        ).timestamp()
        if now < kickoff + settle_delay_seconds:
            continue
        mid = str(d["fixture_id"])
        try:
            detail, _, detail_hash = provider.match_detail(mid)
        except ProviderBudgetStop:
            break
        if not detail:
            continue
        m = detail.get("data", detail)
        score = m.get("score") or {}
        gh, ga = score.get("home"), score.get("away")
        if gh is None or ga is None:
            continue
        source_hashes = {"match_detail": detail_hash}
        family = d["market_family"]
        if family == "goals":
            value = float(gh) + float(ga)
            unit = "total_goals"
        elif family == "corners":
            try:
                stats_payload, _, stats_hash = provider.stats(mid)
            except ProviderBudgetStop:
                break
            if not stats_payload:
                continue
            try:
                cv = stats_payload["data"]["overview"]["corner_kicks"]["all"]
                value = float(cv["home"]) + float(cv["away"])
            except (KeyError, TypeError, ValueError):
                continue
            unit = "total_corners"
            source_hashes["match_stats"] = stats_hash
        else:
            continue
        line = float(d["line"])
        side = str(d["side"])
        won = value > line if side == "OVER" else value < line
        settlement = {
            "result": "WIN" if won else "LOSS",
            "settled_value": value,
            "settled_unit": unit,
            "final_score": f"{d['fixture']} {int(gh)}-{int(ga)}",
            "closing_benchmark": _closing_for(d),
            "source_payload_hashes": source_hashes,
        }
        event = ledger.append_settlement(str(d["hypothesis_id"]), settlement)
        if event is None:
            continue
        settled_events.append((event, d))
        _append_jsonl(SETTLEMENT_LOG, event)
        try:
            ledger.git_commit(
                [ledger.LEAN_LEDGER],
                f"Settle V3 pilot test {d.get('test_number')}"
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
            "hypothesis_id": d["hypothesis_id"],
            "ok": ok, "detail": detail_msg, "observed_at_utc": _now_iso(),
        })
    status = ledger.pilot_status()
    if status["declared"] >= 40 and status["pending"] == 0:
        marker = DATA_ROOT / "AUDIT_READY.json"
        if not marker.exists():
            _atomic_json(marker, {
                "status": "AUDIT_READY",
                "observed_at_utc": _now_iso(),
                "pilot_status": status,
                "freeze_contract_sha256": freeze_hash(),
                "instruction": "Do not modify V3. Run independent 40-test audit before any rework.",
            })
            send(
                "QFE V3 PILOT — 40/40 SETTLED\n"
                "Audit checkpoint reached. Model remains frozen pending independent review."
            )
    return {"settled": len(settled_events), "pilot_status": status, "requests": provider.requests}

def tick(*, dry_run: bool = False, force_discovery: bool = False) -> dict:
    DATA_ROOT.mkdir(parents=True, exist_ok=True)
    provider = V3Provider()
    out = {"freeze_contract_sha256": freeze_hash()}
    out["discovery"] = discover(provider, force=force_discovery)
    out["evaluation"] = evaluate_due(provider, dry_run=dry_run)
    if not dry_run:
        out["final"] = capture_final_for_declared(provider)
        out["settlement"] = settle_due(provider)
    out["requests_total"] = provider.requests
    return out
