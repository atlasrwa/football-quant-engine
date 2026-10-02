from __future__ import annotations
import hashlib
import json
import os
import time
from datetime import datetime, timezone

from src.research.evidence_v32.settlement import cached_score_evidence, stable_regulation_score
from .config import (
    CACHE, DATA, EARLY, EVENTS, FINAL, FIXTURES, FREEZES, MARKET, MARKET_ATTEMPTS,
    MID, RETRY_BACKOFF, STATE, TARGET_FIXTURES, TELEGRAM, DISCOVERY_HOURS,
    DISCOVERY_REFRESH, scope,
)
from .market import best_qualifier, comparisons, team_corner_pair
from .model import freeze as model_freeze, predict_fixture
from .provider import BudgetStop, Provider
from .telegram import declaration as declaration_message, send, settlement as settlement_message

def iso(ts=None):
    return datetime.fromtimestamp(time.time() if ts is None else ts, timezone.utc).isoformat()

def atomic(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, sort_keys=True, indent=2, default=str) + "\n")
    os.replace(tmp, path)

def append(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())
def readj(path):
    if not path.exists():
        return []
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]

def state():
    if STATE.exists():
        return json.loads(STATE.read_text())
    return {
        "last_discovery_at": 0.0, "fixtures": {}, "vintages": {}, "enrolled": [],
        "declarations": {}, "settled": {}, "attempted_at": {}, "final_last_capture": {},
    }

def save(s):
    atomic(STATE, s)

def event(s, kind, **fields):
    prev = s.get("chain_head", "")
    body = {"event_type": kind, "recorded_at_utc": iso(), "prev_hash": prev, **fields}
    raw = json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    body["event_hash"] = hashlib.sha256(raw).hexdigest()
    append(EVENTS, body)
    s["chain_head"] = body["event_hash"]
    return body

def persist_market(body):
    raw = json.dumps(body, sort_keys=True, separators=(",", ":"), default=str).encode()
    rec = {**body, "market_observation_hash": hashlib.sha256(raw).hexdigest()}
    append(MARKET, rec)
    return rec
def attempt(s, fx, vintage, reason, started, received, payload_hash=""):
    key = f"{fx['match_id']}:{vintage}"
    s["attempted_at"][key] = float(received)
    append(MARKET_ATTEMPTS, {
        "event_type": "MARKET_CAPTURE_ATTEMPT", "fixture_id": fx["match_id"],
        "fixture": f"{fx['home_name']} vs {fx['away_name']}", "kickoff_utc": fx["utc_date"],
        "vintage": vintage, "reason": reason,
        "request_started_at": started, "request_started_at_utc": iso(started),
        "response_received_at": received, "response_received_at_utc": iso(received),
        "odds_payload_hash": payload_hash,
    })
    save(s)

def discover(provider, s, force=False):
    now = time.time()
    if not force and now - float(s.get("last_discovery_at", 0)) < DISCOVERY_REFRESH:
        return 0
    found = 0
    for comp in scope():
        try:
            rows = provider.upcoming(comp["competition_id"], DISCOVERY_HOURS)
        except BudgetStop:
            break
        for fx in rows:
            found += 1
            if fx["match_id"] not in s["fixtures"]:
                append(FIXTURES, {"event_type": "FIXTURE_DISCOVERED", "observed_at_utc": iso(), **fx})
            s["fixtures"][fx["match_id"]] = fx
    s["last_discovery_at"] = now
    save(s)
    return found
def fpath(mid):
    return FREEZES / mid / "bundle.json"

def freeze_fixture(s, fx):
    path = fpath(fx["match_id"])
    if path.exists():
        return json.loads(path.read_text())
    prediction = predict_fixture(fx)
    obj = {
        "record_type": "TEAM_CORNERS_V1_MODEL_FREEZE",
        "fixture": fx, "frozen_at": time.time(), "frozen_at_utc": iso(),
        "model_freeze_sha256": model_freeze()["freeze_sha256"],
        **prediction,
    }
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    obj["freeze_hash"] = hashlib.sha256(raw).hexdigest()
    atomic(path, obj)
    event(s, "MODEL_FROZEN", fixture_id=fx["match_id"], freeze_hash=obj["freeze_hash"],
          abstentions=obj.get("abstentions", []))
    save(s)
    return obj

def in_window(fx, name, observed_at):
    low, high = {"EARLY": EARLY, "MID": MID, "FINAL": FINAL}[name]
    seconds = float(fx["ts"]) - float(observed_at)
    return low <= seconds <= high

def due(s, fx, name, now):
    if not in_window(fx, name, now):
        return False
    if name == "FINAL":
        last = float(s.get("final_last_capture", {}).get(fx["match_id"], 0) or 0)
        return now - last >= 240
    if s["vintages"].get(f"{fx['match_id']}:{name}"):
        return False
    last = float(s.get("attempted_at", {}).get(f"{fx['match_id']}:{name}", 0) or 0)
    return now - last >= RETRY_BACKOFF
def enroll(s, fx):
    if fx["match_id"] in s["enrolled"]:
        return s["enrolled"].index(fx["match_id"]) + 1
    if len(s["enrolled"]) >= TARGET_FIXTURES:
        return None
    s["enrolled"].append(fx["match_id"])
    number = len(s["enrolled"])
    event(s, "FIXTURE_ENROLLED", fixture_id=fx["match_id"], fixture_number=number,
          fixture=f"{fx['home_name']} vs {fx['away_name']}", kickoff_utc=fx["utc_date"])
    save(s)
    return number

def _declaration_record(s, mid, role):
    h = s.get("declarations", {}).get(f"{mid}:{role}")
    if not h:
        return None
    return next((r for r in reversed(readj(EVENTS)) if r.get("event_hash") == h), None)

def maybe_declare(s, fx, fixture_number, bundle, rows, vintage, market_rec):
    made = []
    for role in ("home", "away"):
        key = f"{fx['match_id']}:{role}"
        if key in s["declarations"]:
            continue
        candidate = best_qualifier(rows, role)
        if candidate is None:
            continue
        side_pred = bundle["sides"][role]
        rec = {
            "disagreement_number": len(s["declarations"]) + 1,
            "fixture_number": fixture_number, "fixture_id": fx["match_id"],
            "fixture": f"{fx['home_name']} vs {fx['away_name']}", "kickoff_utc": fx["utc_date"],
            "role": role, "team_id": candidate["team_id"], "team_name": candidate["team_name"],
            "side": candidate["side"], "line": candidate["line"], "price_decimal": candidate["price"],
            "p_model": candidate["p_model"], "p_market": candidate["p_market"],
            "delta": candidate["delta"], "raw_break_even": candidate["raw_break_even"],
            "mu": candidate["mu"], "components": candidate["components"],
            "ensemble_weights": side_pred["ensemble_weights"], "model_version": candidate["model_version"],
            "model_freeze_sha256": bundle["model_freeze_sha256"], "freeze_hash": bundle["freeze_hash"],
            "vintage": vintage, "bookmaker": "Bet365", "provider": "thestatsapi",
            "entry_over_odds": candidate["over_odds"], "entry_under_odds": candidate["under_odds"],
            "odds_payload_hash": market_rec["odds_payload_hash"],
            "market_observation_hash": market_rec["market_observation_hash"],
            "market_observed_at": market_rec["observed_at"],
            "market_observed_at_utc": market_rec["observed_at_utc"],
            "market_request_started_at": market_rec["request_started_at"],
            "market_request_started_at_utc": market_rec["request_started_at_utc"],
            "declared_at_utc": iso(),
        }
        ev = event(s, "DECLARATION", **rec)
        s["declarations"][key] = ev["event_hash"]
        ok, detail = send(declaration_message(rec))
        append(TELEGRAM, {"event_type": "DECLARATION_TELEGRAM", "fixture_id": fx["match_id"],
                          "role": role, "ok": ok, "detail": detail, "observed_at_utc": iso()})
        made.append(rec)
        save(s)
    return made
def evaluate(provider, s):
    now = time.time()
    observations = 0
    declared = 0
    for fx in sorted(s["fixtures"].values(), key=lambda x: (x["ts"], x["match_id"])):
        if not (now < fx["ts"] <= now + 32 * 3600):
            continue
        enrolled = fx["match_id"] in s["enrolled"]
        if len(s["enrolled"]) >= TARGET_FIXTURES and not enrolled:
            continue
        for vintage in ("EARLY", "MID"):
            if not due(s, fx, vintage, now):
                continue
            bundle = freeze_fixture(s, fx)
            if not bundle.get("sides"):
                s["vintages"][f"{fx['match_id']}:{vintage}"] = "MODEL_ABSTAIN"
                save(s)
                continue
            try:
                odds, seen, ph, started = provider.odds(fx["match_id"])
            except BudgetStop:
                return {"market_observations": observations, "declared": declared}
            if not odds:
                attempt(s, fx, vintage, "EMPTY_RESPONSE", started, seen, ph)
                continue
            if not in_window(fx, vintage, seen):
                attempt(s, fx, vintage, "RESPONSE_OUTSIDE_WINDOW", started, seen, ph)
                continue
            comps = comparisons(bundle, odds)
            market_rec = persist_market({
                "event_type": "TEAM_CORNERS_MARKET_OBSERVED", "fixture_id": fx["match_id"],
                "fixture": f"{fx['home_name']} vs {fx['away_name']}", "kickoff_utc": fx["utc_date"],
                "request_started_at": started, "request_started_at_utc": iso(started),
                "observed_at": seen, "observed_at_utc": iso(seen), "vintage": vintage,
                "odds_payload_hash": ph, "freeze_hash": bundle["freeze_hash"],
                "capture_status": "VALID" if comps else "NO_USABLE_TEAM_CORNERS",
                "comparisons": comps,
            })
            observations += 1
            if not comps:
                attempt(s, fx, vintage, "NO_USABLE_TEAM_CORNERS", started, seen, ph)
                continue
            s["vintages"][f"{fx['match_id']}:{vintage}"] = seen
            fixture_number = enroll(s, fx)
            save(s)
            if fixture_number:
                declared += len(maybe_declare(s, fx, fixture_number, bundle, comps, vintage, market_rec))
    return {"market_observations": observations, "declared": declared}

def capture_final(provider, s):
    now = time.time()
    captured = 0
    for mid in list(s["enrolled"]):
        fx = s["fixtures"][mid]
        if not due(s, fx, "FINAL", now):
            continue
        declarations = [d for role in ("home", "away") if (d := _declaration_record(s, mid, role))]
        if not declarations:
            continue
        bundle = json.loads(fpath(mid).read_text())
        try:
            odds, seen, ph, started = provider.odds(mid)
        except BudgetStop:
            break
        if not odds or not in_window(fx, "FINAL", seen):
            attempt(s, fx, "FINAL", "EMPTY_OR_OUTSIDE_WINDOW", started, seen, ph)
            continue
        comps = comparisons(bundle, odds)
        valid = all(team_corner_pair(odds, d["role"], d["line"]) is not None for d in declarations)
        persist_market({
            "event_type": "TEAM_CORNERS_MARKET_OBSERVED", "fixture_id": mid,
            "fixture": f"{fx['home_name']} vs {fx['away_name']}", "kickoff_utc": fx["utc_date"],
            "request_started_at": started, "request_started_at_utc": iso(started),
            "observed_at": seen, "observed_at_utc": iso(seen), "vintage": "FINAL",
            "odds_payload_hash": ph, "freeze_hash": bundle["freeze_hash"],
            "capture_status": "VALID" if valid else "DECLARED_LINE_NOT_QUOTED",
            "comparisons": comps,
        })
        s["final_last_capture"][mid] = seen
        save(s)
        if valid:
            captured += 1
    return captured

def _closing_for(declaration_event):
    rows = [
        r for r in readj(MARKET)
        if r.get("fixture_id") == declaration_event["fixture_id"]
        and r.get("vintage") == "FINAL"
        and r.get("capture_status") == "VALID"
    ]
    matches = []
    for rec in rows:
        for comp in rec.get("comparisons", []):
            if comp.get("role") != declaration_event["role"]:
                continue
            if abs(float(comp.get("line")) - float(declaration_event["line"])) > 1e-9:
                continue
            matches.append((float(rec["observed_at"]), comp))
    if not matches:
        return {"status": "UNAVAILABLE", "reason": "NO_VALID_FINAL"}
    _, comp = max(matches, key=lambda x: x[0])
    closing_p = comp["market_over"] if declaration_event["side"] == "OVER" else comp["market_under"]
    entry_p = float(declaration_event["p_market"])
    return {
        "status": "OK", "entry_market_p": entry_p, "closing_market_p": float(closing_p),
        "movement_toward_selection": float(closing_p) - entry_p,
    }

def corner_side(payload, role):
    try:
        node = payload["data"]["overview"]["corner_kicks"]["all"]
        return int(node[role])
    except Exception:
        return None

def settle(provider, s):
    now = time.time()
    done = 0
    for mid in list(s["enrolled"]):
        fx = s["fixtures"][mid]
        declarations = {role: _declaration_record(s, mid, role) for role in ("home", "away")}
        declarations = {k: v for k, v in declarations.items() if v is not None}
        if not declarations:
            continue
        settled = s["settled"].setdefault(mid, {})
        if all(settled.get(role) for role in declarations):
            continue
        if now < float(fx["ts"]) + 4 * 3600:
            continue
        try:
            provider.detail(mid)
        except BudgetStop:
            break
        stable = stable_regulation_score(cached_score_evidence(CACHE / "match_detail" / mid, kickoff_ts=fx["ts"]))
        if not stable:
            continue
        try:
            stats, stats_seen, stats_hash, _ = provider.stats(mid)
        except BudgetStop:
            break
        if not stats:
            continue
        for role, decl in declarations.items():
            if settled.get(role):
                continue
            value = corner_side(stats, role)
            if value is None:
                continue
            line = float(decl["line"])
            side = decl["side"]
            result = "PUSH" if value == line else ("WIN" if ((value > line) if side == "OVER" else (value < line)) else "LOSS")
            clv = _closing_for(decl)
            ev = event(s, "TEAM_SIDE_SETTLED", fixture_id=mid, role=role, value=value,
                       result=result, source="STABLE_SCORE_PLUS_PROVIDER_TEAM_CORNERS",
                       stats_observed_at=stats_seen, stats_payload_hash=stats_hash, clv=clv)
            settled[role] = ev["event_hash"]
            done += 1
            ok, detail = send(settlement_message({"result": result, "value": value, "clv": clv}, decl))
            append(TELEGRAM, {"event_type": "SETTLEMENT_TELEGRAM", "fixture_id": mid, "role": role,
                              "ok": ok, "detail": detail, "observed_at_utc": iso()})
        save(s)
    return done

def tick(force=False):
    DATA.mkdir(parents=True, exist_ok=True)
    s = state()
    provider = Provider()
    found = discover(provider, s, force)
    evaluated = evaluate(provider, s)
    final = capture_final(provider, s)
    settled = settle(provider, s)
    save(s)
    return {
        "version": "QFE Team Corners V1", "discovered": found,
        "enrolled": len(s["enrolled"]), "remaining": TARGET_FIXTURES - len(s["enrolled"]),
        "declarations": len(s["declarations"]), "final_captures": final,
        "settlement_events": settled, "requests": provider.requests, **evaluated,
    }

def status():
    s = state()
    return {
        "version": "QFE Team Corners V1",
        "enrolled": len(s["enrolled"]), "remaining": TARGET_FIXTURES - len(s["enrolled"]),
        "declarations": len(s["declarations"]),
        "settled": sum(len(v) for v in s["settled"].values()),
        "chain_head": s.get("chain_head"),
        "model_freeze_sha256": model_freeze()["freeze_sha256"],
    }
