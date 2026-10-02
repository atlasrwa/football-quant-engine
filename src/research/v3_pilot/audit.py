"""Deterministic audit/map layer for the 40-test lean pilot ledger."""
from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from . import ledger
from .config import DATA_ROOT, LEAN_LEDGER, LEAN_LEDGER_REPO, ROOT
from .freeze import freeze_hash

AUDIT_PROTOCOL = ROOT / "research/v3_live_pilot/PILOT_AUDIT_PROTOCOL_V1.json"
AUDIT_MAP = DATA_ROOT / "lean_ledger_map_v1.json"

def _canonical(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()

def _sha256_bytes(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()

def _sha256_file(path: Path) -> str:
    return _sha256_bytes(path.read_bytes())

def _read_rows() -> list[dict]:
    if not LEAN_LEDGER.exists():
        return []
    return [json.loads(x) for x in LEAN_LEDGER.read_text(encoding="utf-8").splitlines() if x.strip()]

def _f(v: Any) -> float | None:
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None

def _ts(value: Any) -> float | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None

def _related(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for row in rows:
        hid = row.get("hypothesis_id")
        if hid:
            out.setdefault(str(hid), []).append(row)
    return out

def _model_probability(decl: dict, related: list[dict]) -> float | None:
    model = decl.get("model") or {}
    if _f(model.get("p_selected")) is not None:
        return _f(model.get("p_selected"))
    lean = decl.get("lean_model") or {}
    if _f(lean.get("p_selected")) is not None:
        return _f(lean.get("p_selected"))
    p_over = _f(lean.get("p_over"))
    if p_over is not None:
        return p_over if decl.get("side") in ("OVER", "YES") else 1.0 - p_over
    for row in related:
        if row.get("event_type") != "MODEL_CONTEXT_RECORDED":
            continue
        outputs = row.get("outputs") or {}
        p_over = _f(outputs.get("p_over"))
        if p_over is not None:
            return p_over if decl.get("side") in ("OVER", "YES") else 1.0 - p_over
    return None

def _market_probability(decl: dict, related: list[dict]) -> float | None:
    mb = decl.get("market_benchmark") or {}
    for key in ("no_vig_selected", "p_market_novig_selected"):
        if _f(mb.get(key)) is not None:
            return _f(mb.get(key))
    for row in related:
        if row.get("event_type") != "MARKET_CONTEXT_RECORDED":
            continue
        nv = row.get("no_vig_market_probability") or {}
        side = str(decl.get("side") or "").lower()
        key = "over" if side in ("over", "yes") else "under"
        if _f(nv.get(key)) is not None:
            return _f(nv.get(key))
    return None

def _unit_pnl(row: dict) -> float | None:
    result = row.get("result")
    price = _f(row.get("price_decimal"))
    if result == "PUSH":
        return 0.0
    if result == "LOSS":
        return -1.0 if price is not None else None
    if result == "WIN" and price is not None:
        return price - 1.0
    return None

def validate_integrity(rows: list[dict] | None = None) -> dict:
    rows = _read_rows() if rows is None else rows
    errors: list[str] = []
    warnings: list[str] = []
    declarations = [
        r for r in rows
        if r.get("event_type") == "HYPOTHESIS_DECLARED"
        and r.get("counts_toward_40") is not False
    ]
    seen: set[str] = set()
    for ordinal, decl in enumerate(declarations, 1):
        hid = str(decl.get("hypothesis_id") or "")
        if not hid:
            errors.append(f"declaration ordinal {ordinal} missing hypothesis_id")
        elif hid in seen:
            errors.append(f"duplicate hypothesis_id {hid}")
        seen.add(hid)
        explicit = decl.get("test_number")
        if explicit is not None and int(explicit) != ordinal:
            errors.append(f"test numbering mismatch {hid}: explicit={explicit} ordinal={ordinal}")
        if decl.get("origin") == "V3_AUTOMATED_THESTATSAPI_PROSPECTIVE":
            pt = _ts(decl.get("prediction_observed_at_utc"))
            mt = _ts(decl.get("market_observed_at_utc"))
            kt = _ts(decl.get("kickoff_utc"))
            if pt is None or mt is None or kt is None or not (pt < mt < kt):
                errors.append(f"point-in-time ordering invalid for {hid}")
            imm = decl.get("immutable_evidence") or {}
            rel = imm.get("relative_path")
            expected = str(imm.get("sha256") or "")
            if not rel:
                errors.append(f"missing immutable evidence path for {hid}")
            else:
                path = LEAN_LEDGER_REPO / str(rel)
                if not path.exists():
                    errors.append(f"missing immutable evidence file for {hid}")
                elif _sha256_file(path) != expected:
                    errors.append(f"immutable evidence hash mismatch for {hid}")

    prev: str | None = None
    v3_events = [r for r in rows if r.get("v3_event_hash")]
    for idx, event in enumerate(v3_events):
        saved = str(event["v3_event_hash"])
        payload = dict(event)
        payload.pop("v3_event_hash", None)
        actual = _sha256_bytes(_canonical(payload))
        if actual != saved:
            errors.append(f"v3 event hash mismatch at chain index {idx}")
        if event.get("v3_prev_hash") != prev:
            errors.append(f"v3 prev hash mismatch at chain index {idx}")
        if str(event.get("v3_freeze_sha256") or "") != freeze_hash():
            errors.append(f"v3 freeze hash mismatch at chain index {idx}")
        prev = saved

    if len(declarations) < 40:
        warnings.append(f"pilot incomplete: {len(declarations)}/40 declarations")
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "warnings": warnings,
        "declarations": len(declarations),
        "v3_chain_events": len(v3_events),
        "v3_chain_head": prev,
    }

def _logloss(p: float, y: int) -> float:
    p = min(max(float(p), 1e-12), 1 - 1e-12)
    return -(y * math.log(p) + (1 - y) * math.log(1 - p))

def _ece(samples: list[tuple[float, int]], bins: list[float]) -> float | None:
    if not samples:
        return None
    total = len(samples)
    acc = 0.0
    for lo, hi in zip(bins[:-1], bins[1:]):
        bucket = [(p, y) for p, y in samples if lo <= p < hi or (hi == 1.0 and p == 1.0)]
        if not bucket:
            continue
        mean_p = sum(p for p, _ in bucket) / len(bucket)
        mean_y = sum(y for _, y in bucket) / len(bucket)
        acc += len(bucket) / total * abs(mean_p - mean_y)
    return acc

def _metrics(mapped: list[dict]) -> dict:
    settled_binary = [
        r for r in mapped
        if r.get("result") in ("WIN", "LOSS")
        and r.get("p_model") is not None
        and r.get("p_market_entry_novig") is not None
    ]
    model_samples = [(float(r["p_model"]), 1 if r["result"] == "WIN" else 0) for r in settled_binary]
    market_samples = [(float(r["p_market_entry_novig"]), 1 if r["result"] == "WIN" else 0) for r in settled_binary]
    out: dict[str, Any] = {
        "declared": len(mapped),
        "settled": sum(1 for r in mapped if r.get("result") in ("WIN", "LOSS", "PUSH")),
        "pending": sum(1 for r in mapped if r.get("result") == "PENDING"),
        "wins": sum(1 for r in mapped if r.get("result") == "WIN"),
        "losses": sum(1 for r in mapped if r.get("result") == "LOSS"),
        "pushes": sum(1 for r in mapped if r.get("result") == "PUSH"),
        "proper_score_coverage": len(settled_binary),
    }
    if model_samples:
        n = len(model_samples)
        mll = sum(_logloss(p, y) for p, y in model_samples) / n
        kll = sum(_logloss(p, y) for p, y in market_samples) / n
        mb = sum((p - y) ** 2 for p, y in model_samples) / n
        kb = sum((p - y) ** 2 for p, y in market_samples) / n
        bins = [0.0, 0.6, 0.7, 0.8, 0.9, 1.0]
        out.update({
            "model_log_loss": mll,
            "market_entry_log_loss": kll,
            "paired_log_loss_improvement": kll - mll,
            "model_brier": mb,
            "market_entry_brier": kb,
            "paired_brier_improvement": kb - mb,
            "model_ece_fixed_bins": _ece(model_samples, bins),
            "market_ece_fixed_bins": _ece(market_samples, bins),
        })

    clv = [
        _f((r.get("closing_benchmark") or {}).get("movement_toward_selection"))
        for r in mapped
    ]
    clv = [x for x in clv if x is not None]
    genuine = [
        r for r in mapped
        if isinstance(r.get("closing_benchmark"), dict)
        and (r["closing_benchmark"] or {}).get("genuine_close_window") is True
    ]
    pnl = [_unit_pnl(r) for r in mapped]
    pnl = [x for x in pnl if x is not None]
    if clv:
        out["mean_clv_probability_movement_toward_selection"] = sum(clv) / len(clv)
        out["clv_coverage"] = len(clv) / max(len(mapped), 1)
    else:
        out["mean_clv_probability_movement_toward_selection"] = None
        out["clv_coverage"] = 0.0
    out["genuine_close_coverage"] = len(genuine) / max(len(mapped), 1)
    if pnl:
        out["unit_stake_pnl"] = sum(pnl)
        out["unit_stake_roi"] = sum(pnl) / len(pnl)
    else:
        out["unit_stake_pnl"] = None
        out["unit_stake_roi"] = None
    decisions = out["wins"] + out["losses"]
    out["hit_rate_secondary"] = out["wins"] / decisions if decisions else None
    return out

def _adjudicate(primary: dict, integrity: dict) -> str:
    if integrity.get("status") != "PASS":
        return "INCONCLUSIVE"
    if primary.get("declared") != 20 or primary.get("pending") != 0:
        return "NOT_READY"
    required = (
        "paired_log_loss_improvement", "paired_brier_improvement",
        "mean_clv_probability_movement_toward_selection", "unit_stake_pnl",
    )
    if any(primary.get(k) is None for k in required):
        return "INCONCLUSIVE"
    if float(primary.get("genuine_close_coverage", 0.0)) < 0.80:
        return "INCONCLUSIVE"
    vals = [
        float(primary["paired_log_loss_improvement"]),
        float(primary["paired_brier_improvement"]),
        float(primary["mean_clv_probability_movement_toward_selection"]),
        float(primary["unit_stake_pnl"]),
    ]
    if all(x > 0 for x in vals):
        return "DIRECTIONAL_PASS"
    if all(x <= 0 for x in vals):
        return "DIRECTIONAL_FAIL"
    return "INCONCLUSIVE"

def build_map(rows: list[dict] | None = None) -> dict:
    rows = _read_rows() if rows is None else rows
    rel = _related(rows)
    settlements = ledger.settlements(rows)
    declarations = [
        r for r in rows
        if r.get("event_type") == "HYPOTHESIS_DECLARED"
        and r.get("counts_toward_40") is not False
    ]
    mapped: list[dict] = []

    for ordinal, decl in enumerate(declarations, 1):
        hid = str(decl["hypothesis_id"])
        st = settlements.get(hid)
        p_model = _model_probability(decl, rel.get(hid, []))
        p_market = _market_probability(decl, rel.get(hid, []))
        cohort = "V3_PRIMARY_21_40" if decl.get("origin") == "V3_AUTOMATED_THESTATSAPI_PROSPECTIVE" else "LEGACY_1_20"
        mapped.append({
            "pilot_test_number": ordinal,
            "explicit_test_number": decl.get("test_number"),
            "numbering_source": "EXPLICIT" if decl.get("test_number") is not None else "LEDGER_ORDER_INFERRED",
            "hypothesis_id": hid,
            "cohort": cohort,
            "fixture": decl.get("fixture"),
            "fixture_id": decl.get("fixture_id"),
            "kickoff_utc": decl.get("kickoff_utc"),
            "market_family": decl.get("market_family"),
            "market": decl.get("market"),
            "side": decl.get("side"),
            "line": decl.get("line"),
            "price_decimal": _f(decl.get("price_decimal")),
            "opposite_price_decimal": _f(decl.get("opposite_price_decimal")),
            "origin": decl.get("origin"),
            "methodology_status": decl.get("methodology_status"),
            "p_model": p_model,
            "p_market_entry_novig": p_market,
            "model_minus_market_pp": (
                100.0 * (p_model - p_market)
                if p_model is not None and p_market is not None else None
            ),
            "immutable_evidence": decl.get("immutable_evidence"),
            "v3_event_hash": decl.get("v3_event_hash"),
            "v3_prev_hash": decl.get("v3_prev_hash"),
            "v3_freeze_sha256": decl.get("v3_freeze_sha256"),
            "result": st.get("result") if st else "PENDING",
            "settled_value": st.get("settled_value") if st else None,
            "settled_unit": st.get("settled_unit") if st else None,
            "verification_class": st.get("verification_class") if st else None,
            "closing_benchmark": st.get("closing_benchmark") if st else None,
            "settlement_event_hash": st.get("v3_event_hash") if st else None,
        })

    integrity = validate_integrity(rows)
    primary_rows = [r for r in mapped if r["cohort"] == "V3_PRIMARY_21_40"]
    legacy_rows = [r for r in mapped if r["cohort"] == "LEGACY_1_20"]
    primary_metrics = _metrics(primary_rows)
    legacy_metrics = _metrics(legacy_rows)
    whole_metrics = _metrics(mapped)
    manual_blockers = [
        r["hypothesis_id"] for r in legacy_rows
        if r.get("result") == "PENDING" and r.get("market_family") == "bookings"
    ]
    protocol_hash = _sha256_file(AUDIT_PROTOCOL) if AUDIT_PROTOCOL.exists() else None
    return {
        "schema_version": "qfe-lean-ledger-map/1",
        "generated_from_append_only_ledger": str(LEAN_LEDGER),
        "audit_protocol": {
            "path": str(AUDIT_PROTOCOL),
            "sha256": protocol_hash,
        },
        "integrity": integrity,
        "summary": {
            "whole_pilot_descriptive": whole_metrics,
            "legacy_1_20_descriptive": legacy_metrics,
            "v3_primary_21_40": primary_metrics,
            "v3_adjudication": _adjudicate(primary_metrics, integrity),
            "legacy_manual_settlement_required": manual_blockers,
            "warning": "Do not pool legacy 1-20 with V3 21-40 for primary predictive claims.",
        },
        "tests": mapped,
    }

def refresh_audit_map() -> dict:
    obj = build_map()
    AUDIT_MAP.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(obj, sort_keys=True, indent=2, default=str) + "\n"
    tmp = AUDIT_MAP.with_suffix(".json.tmp")
    tmp.write_text(raw, encoding="utf-8")
    tmp.replace(AUDIT_MAP)
    return {
        "path": str(AUDIT_MAP),
        "sha256": _sha256_bytes(raw.encode()),
        "integrity": obj["integrity"]["status"],
        "declared": obj["summary"]["whole_pilot_descriptive"]["declared"],
        "v3_adjudication": obj["summary"]["v3_adjudication"],
    }
