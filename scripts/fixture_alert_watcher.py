#!/usr/bin/env python3
"""Daily FootyStats fixture manifest and hourly bettor alert watcher.

The daily discovery keeps every fixture exposed by the FootyStats account. The
hourly path captures immutable FootyStats and TheStatsAPI raw observations,
records every executable book/market price, derives price-change events, runs the
existing fail-closed EV engine for eligible fixtures, and sends only clean bettor
alerts for candidates that pass every gate.

Usage:
  python scripts/fixture_alert_watcher.py --discover-only
  python scripts/fixture_alert_watcher.py
  python scripts/fixture_alert_watcher.py --dry-run
  python scripts/fixture_alert_watcher.py --date 2026-09-03
  python scripts/fixture_alert_watcher.py --fixture-id mt_466259566
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

import fixture_ev_engine as engine

ALERT_ROOT = engine.ROOT / "data/alerts"
DAILY_FIXTURE_ROOT = ALERT_ROOT / "daily_fixtures"
OBSERVATION_ROOT = ALERT_ROOT / "provider_observations"
STATE_FILE = ALERT_ROOT / "fixture_alert_state.json"
PRICE_STATE_FILE = ALERT_ROOT / "price_state.json"
LOG_FILE = ALERT_ROOT / "fixture_alert_log.jsonl"
PRICE_CHANGE_LOG = ALERT_ROOT / "price_changes.jsonl"
OBSERVATION_LOG = ALERT_ROOT / "provider_observations.jsonl"
IMMUTABLE_QUOTE_LOG = ALERT_ROOT / "immutable_quote_snapshots.jsonl"

TELEGRAM_API = "https://api.telegram.org/bot{token}/sendMessage"
ALERT_TTL_MINUTES = int(os.environ.get("FIXTURE_ALERT_TTL_MINUTES", "60"))
WATCHER_REQUEST_CAP = int(os.environ.get("FIXTURE_ALERT_REQUEST_CAP", "60"))
FOOTYSTATS_DETAIL_CAP = int(os.environ.get("FIXTURE_ALERT_FOOTYSTATS_DETAIL_CAP", "60"))
PRICE_CHANGE_MINIMUM = float(os.environ.get("FIXTURE_PRICE_CHANGE_MINIMUM", "0.01"))


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json_atomic(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n")
    tmp.replace(path)


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as handle:
        handle.write(json.dumps(payload, default=str, sort_keys=True) + "\n")


def _canonical_sha256(payload: dict) -> str:
    """Hash canonical evidence without mutating the captured observation."""
    raw = json.dumps(payload, default=str, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def persist_immutable_quote_snapshots(
    fixture: dict,
    prices: list[dict],
    observed: datetime,
    *,
    dry_run: bool,
) -> int:
    """Append every quote observation with explicit retrieval-time provenance.

    FootyStats/TheStatsAPI's live payload does not supply a verified provider
    source timestamp.  The watcher therefore records this honestly as retrieval
    time, retains even unchanged prices, and never relabels a snapshot as a
    close.  Database writers can ingest this append-only ledger into the
    hardened ``market_prices`` schema when a verified fixture-id mapping exists.
    """
    kickoff = fixture.get("kickoff_unix")
    try:
        kickoff_unix = int(float(kickoff))
    except (TypeError, ValueError):
        return 0
    observed_at = observed.isoformat()
    capture_run_id = _canonical_sha256({
        "fixture_id": str(fixture.get("fixture_id", "")),
        "observed_at": observed_at,
        "source": "thestatsapi",
    })
    written = 0
    for price in prices:
        quote_payload = {
            "fixture_id": str(fixture.get("fixture_id", price.get("fixture_id", ""))),
            "market": price.get("market", price.get("market_path")),
            "line": price.get("line"),
            "bookmaker": price.get("book"),
            "selection": price.get("side"),
            "decimal_odds": price.get("decimal_odds"),
            "observed_at": observed_at,
        }
        if not isinstance(quote_payload["decimal_odds"], (int, float)):
            continue
        record = {
            **quote_payload,
            "capture_run_id": capture_run_id,
            "source": "thestatsapi",
            "provider_source_time": None,
            "retrieved_at": observed_at,
            "timestamp_semantics": "RETRIEVAL_TIME",
            "quote_status": "ACTIVE",
            "price_type": "SNAPSHOT",
            "kickoff_unix": kickoff_unix,
            "raw_payload_hash": _canonical_sha256(quote_payload),
            "quote_hash": _canonical_sha256({
                "quote_contract": "watcher-quote-v1", **quote_payload
            }),
            "clv_eligible": observed.timestamp() < kickoff_unix,
            "dry_run": dry_run,
        }
        if not dry_run:
            append_jsonl(IMMUTABLE_QUOTE_LOG, record)
        written += 1
    return written


def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text())
        return payload if isinstance(payload, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


# --------------------------------------------------------------------------- #
# Daily all-league fixture manifest
# --------------------------------------------------------------------------- #
def daily_manifest_path(day: date) -> Path:
    return DAILY_FIXTURE_ROOT / f"{day.isoformat()}.json"


def save_daily_manifest(discovery: dict) -> Path:
    payload = dict(discovery)
    payload["generated_at"] = now_iso()
    payload["coverage"] = (
        "All fixtures returned for this UTC day by chosen_leagues_only=true on "
        "the configured FootyStats account. analysis_fixtures is the separately "
        "verified subset eligible for the EV engine."
    )
    path = daily_manifest_path(date.fromisoformat(payload["day"]))
    write_json_atomic(path, payload)
    write_json_atomic(DAILY_FIXTURE_ROOT / "latest.json", payload)
    return path


def discover_and_save(day: date) -> tuple[dict, Path]:
    discovery = engine.discover_footystats_fixtures_for_day(day, fresh=True)
    path = save_daily_manifest(discovery)
    return discovery, path


def load_or_discover(day: date, refresh: bool = False) -> tuple[dict, Path, bool]:
    path = daily_manifest_path(day)
    if path.exists() and not refresh:
        return load_json(path), path, False
    manifest, path = discover_and_save(day)
    return manifest, path, True


# --------------------------------------------------------------------------- #
# Candidate and full-price state
# --------------------------------------------------------------------------- #
def candidate_key(fixture_id: str, market: dict, candidate: dict) -> str:
    return (
        f"{fixture_id}:{market['market']}:{market['line']}:"
        f"{candidate['side']}:{candidate['book']}"
    )


def is_new_or_changed(state: dict, key: str, candidate: dict) -> bool:
    """Alert on first pass, fail-to-pass, or a real executable-price change.

    An unchanged candidate is not re-sent merely because an hour elapsed. The
    displayed validity window still tells bettors to revalidate before execution.
    """
    previous = state.get(key)
    if previous is None or not previous.get("active", True):
        return True
    delta = abs(
        float(previous.get("decimal_odds", 0))
        - float(candidate["decimal_odds"])
    )
    return round(delta, 4) >= PRICE_CHANGE_MINIMUM


def flatten_prices(report: dict) -> list[dict]:
    fixture_id = str(report["fixture"]["fixture_id"])
    rows: list[dict] = []
    for market in report.get("markets", []):
        for book, sides in market.get("books", {}).items():
            for side in sides:
                rows.append({
                    "key": (
                        f"{fixture_id}:{market['market']}:{market['line']}:"
                        f"{book}:{side['side']}"
                    ),
                    "fixture_id": fixture_id,
                    "market": market["market"],
                    "line": market["line"],
                    "book": book,
                    "side": side["side"],
                    "decimal_odds": float(side["decimal_odds"]),
                    "fair_probability": side.get("fair_p"),
                    "overround": side.get("overround"),
                })
    return rows


def flatten_raw_prices(fixture_id: str, raw_odds: dict) -> list[dict]:
    """Flatten every provider ``last_seen`` price, not only modeled markets."""
    rows: list[dict] = []
    for book, markets in engine.parse_books(raw_odds).items():
        def walk(node, path: tuple[str, ...]) -> None:
            if not isinstance(node, dict):
                return
            price = node.get("last_seen")
            if isinstance(price, (int, float)) and not isinstance(price, bool):
                market_path = "/".join(path)
                rows.append({
                    "key": f"{fixture_id}:{book}:{market_path}",
                    "fixture_id": fixture_id,
                    "market_path": market_path,
                    "book": book,
                    "decimal_odds": float(price),
                })
            for key, value in node.items():
                if key != "last_seen" and isinstance(value, dict):
                    walk(value, (*path, str(key)))
        walk(markets, ())
    rows.sort(key=lambda row: row["key"])
    return rows


def capture_hourly_prices(fixture: dict, observed: datetime) -> tuple[list[dict], dict]:
    """Capture all-book prices before model work so failures cannot hide movement."""
    thestats_id = fixture.get("thestats_fixture_id")
    if not thestats_id:
        return [], {"available": False, "reason": "no verified TheStatsAPI fixture id"}
    source_dir = (
        OBSERVATION_ROOT / observed.date().isoformat()
        / str(fixture["fixture_id"]) / observed.strftime("%Y%m%dT%H%M%S%fZ")
        / "odds"
    )
    try:
        raw_odds, quota = engine.capture_odds(
            str(thestats_id), source_dir, refresh=True,
            kickoff_unix=float(fixture["kickoff_unix"]),
        )
        prices = flatten_raw_prices(str(fixture["fixture_id"]), raw_odds)
        return prices, {
            "available": bool(raw_odds),
            "price_count": len(prices),
            "quota": quota,
        }
    except (ValueError, SystemExit) as exc:
        return [], {"available": False, "reason": f"{type(exc).__name__}: {exc}"}
    except Exception as exc:
        return [], {"available": False, "reason": f"{type(exc).__name__}: {exc}"}


def update_price_state(price_state: dict, prices: list[dict], observed_at: str,
                       dry_run: bool) -> list[dict]:
    events: list[dict] = []
    for price in prices:
        key = price["key"]
        previous = price_state.get(key)
        previous_odds = (
            float(previous["decimal_odds"])
            if previous and previous.get("decimal_odds") is not None
            else None
        )
        delta = (
            round(price["decimal_odds"] - previous_odds, 4)
            if previous_odds is not None
            else None
        )
        if previous_odds is None or abs(delta or 0.0) >= PRICE_CHANGE_MINIMUM:
            event = {
                **price,
                "event": "price_observed" if previous_odds is None else "price_changed",
                "previous_decimal_odds": previous_odds,
                "delta": delta,
                "observed_at": observed_at,
                "dry_run": dry_run,
            }
            events.append(event)
            if not dry_run:
                append_jsonl(PRICE_CHANGE_LOG, event)
        if not dry_run:
            price_state[key] = {
                "decimal_odds": price["decimal_odds"],
                "observed_at": observed_at,
            }
    return events


# --------------------------------------------------------------------------- #
# Raw provider observations
# --------------------------------------------------------------------------- #
def _numeric_field_count(value) -> int:
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return 1
    if isinstance(value, dict):
        return sum(_numeric_field_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_numeric_field_count(item) for item in value)
    return 0


def _payload_summary(payload) -> dict:
    if payload is None:
        return {"available": False, "numeric_field_count": 0, "top_level_fields": []}
    node = payload.get("data", payload) if isinstance(payload, dict) else payload
    fields = sorted(node.keys()) if isinstance(node, dict) else []
    return {
        "available": True,
        "numeric_field_count": _numeric_field_count(node),
        "top_level_fields": fields,
    }


def _persist_raw(path: Path, payload) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()
    path.write_bytes(raw)
    return {"path": str(path), "sha256": hashlib.sha256(raw).hexdigest()}


def capture_provider_stats(fixture: dict, footystats_client,
                           observed: datetime) -> dict:
    """Persist raw provider detail without feeding target-match stats into the model."""
    fixture_id = str(fixture["fixture_id"])
    bucket = observed.strftime("%Y%m%dT%H%M%S%fZ")
    source_dir = OBSERVATION_ROOT / observed.date().isoformat() / fixture_id / bucket
    output = {
        "observed_at": observed.isoformat(),
        "model_usage": "audit/analysis only; target-fixture stats are not model inputs",
        "footystats": {"available": False},
        "thestatsapi": {"available": False},
    }

    footystats_id = fixture.get("footystats_fixture_id")
    if footystats_id is None:
        output["footystats"]["reason"] = "no FootyStats fixture id"
    elif footystats_client.request_count >= FOOTYSTATS_DETAIL_CAP:
        output["footystats"]["reason"] = (
            f"hourly FootyStats detail cap {FOOTYSTATS_DETAIL_CAP} reached"
        )
    else:
        try:
            payload = footystats_client.fetch_match_detail(int(footystats_id))
            source = _persist_raw(source_dir / "footystats_match.json", payload)
            output["footystats"] = {**_payload_summary(payload), **source}
        except Exception as exc:
            output["footystats"] = {
                "available": False,
                "reason": f"{type(exc).__name__}: {exc}",
            }

    thestats_id = fixture.get("thestats_fixture_id")
    if not thestats_id:
        output["thestatsapi"]["reason"] = "no verified TheStatsAPI fixture id"
    else:
        try:
            import thestatsapi_client as stats_api

            cache_key = f"watcher_stats_{thestats_id}_{bucket}"
            payload, meta = stats_api.get_json(
                f"/football/matches/{thestats_id}/stats",
                cache_key=cache_key,
                allow_status=(200, 404),
            )
            if payload is None:
                output["thestatsapi"] = {
                    "available": False,
                    "http_status": meta.get("http_status"),
                    "reason": "provider returned no pre-match stats",
                }
            else:
                source = _persist_raw(source_dir / "thestatsapi_stats.json", payload)
                output["thestatsapi"] = {
                    **_payload_summary(payload),
                    **source,
                    "from_cache": bool(meta.get("from_cache")),
                    "http_status": meta.get("http_status", 200),
                }
        except SystemExit as exc:
            output["thestatsapi"] = {
                "available": False,
                "reason": f"request cap/API abort ({exc.code})",
            }
        except Exception as exc:
            output["thestatsapi"] = {
                "available": False,
                "reason": f"{type(exc).__name__}: {exc}",
            }
    return output


def historical_analysis_summary(report: dict | None) -> dict:
    if not report:
        return {"available": False}
    evidence = report.get("evidence", {})
    history_meta = evidence.get("history_meta", {})
    fallback = history_meta.get("fallback", {})
    return {
        "available": True,
        "footystats_history_counts": evidence.get("history_counts", {}),
        "supported_history_counts": evidence.get("supported_history_counts", {}),
        "thestatsapi_history_fallback_used": bool(fallback.get("used")),
        "thestatsapi_history_rows": fallback.get("adapted_rows", 0),
        "candidate_markets": report.get("summary", {}).get("candidate_markets", 0),
    }


# --------------------------------------------------------------------------- #
# Bettor output
# --------------------------------------------------------------------------- #
def send_telegram(text: str, token: str, chat_id: str) -> tuple[bool, str]:
    url = TELEGRAM_API.format(token=token)
    payload = urllib.parse.urlencode({
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    request = urllib.request.Request(url, data=payload, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            body = response.read().decode("utf-8", errors="replace")
            ok = response.status == 200 and '"ok":true' in body.replace(" ", "")
            return ok, body[:300]
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:300]
        return False, f"HTTP {exc.code}: {detail}"
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def selection_label(market: dict, side: str) -> str:
    positive = side == "over/yes"
    market_name = str(market["market"])
    line = market["line"]
    if market_name == "btts":
        return f"Both teams to score — {'Yes' if positive else 'No'}"
    unit = {
        "goals": "goals",
        "corners": "corners",
        "cards": "cards",
    }.get(market_name, market_name)
    return f"{'Over' if positive else 'Under'} {line} {unit}"


def format_alert(fixture: dict, market: dict, candidate: dict,
                 observed_at: str | None = None) -> str:
    try:
        observed = datetime.fromisoformat((observed_at or "").replace("Z", "+00:00"))
        if observed.tzinfo is None:
            observed = observed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        observed = datetime.now(timezone.utc)
    kickoff = datetime.fromtimestamp(float(fixture["kickoff_unix"]), timezone.utc)
    expires = min(kickoff, observed + timedelta(minutes=ALERT_TTL_MINUTES))
    match = html.escape(f"{fixture['home']} v {fixture['away']}")
    pick = html.escape(selection_label(market, candidate["side"]))
    book = html.escape(str(candidate["book"]).replace("-", " ").title())
    return (
        f"<b>BET ALERT</b>\n"
        f"{match}\n"
        f"Kickoff: {kickoff.strftime('%Y-%m-%d %H:%M UTC')}\n\n"
        f"Pick: <b>{pick}</b>\n"
        f"Odds: <b>{candidate['decimal_odds']:.2f}</b> at {book}\n"
        f"Use by: {expires.strftime('%H:%M UTC')} — recheck the price first\n\n"
        f"Why: passed the price, data-quality, model-skill and uncertainty checks.\n"
        f"Risk: prices, lineups and team news can change. Bet responsibly."
    )


# --------------------------------------------------------------------------- #
# Engine orchestration
# --------------------------------------------------------------------------- #
def candidate_delivery_eligibility(report: dict, candidate: dict) -> tuple[bool, tuple[str, ...]]:
    """Require explicit forward and provenance promotion before a bettor alert."""
    reasons: list[str] = []
    if report.get("production_enabled") is not True:
        reasons.append("production_not_enabled")
    if candidate.get("forward_attested") is not True:
        reasons.append("missing_forward_attestation")
    if candidate.get("immutable_price_provenance") is not True:
        reasons.append("missing_immutable_price_provenance")
    if candidate.get("pre_kickoff_commitment") is not True:
        reasons.append("missing_pre_kickoff_commitment")
    return not reasons, tuple(reasons)


def scan_fixture(fixture_id: str, resolved_fixture: dict | None = None,
                 refresh_odds: bool = True):
    try:
        report = engine.build_report(
            fixture_id,
            requested_by="alert-watcher",
            refresh_odds=refresh_odds,
            commit=False,
            resolved_fixture=resolved_fixture,
        )
    except ValueError as exc:
        return None, [], f"skipped: {exc}"
    except SystemExit as exc:
        return None, [], f"request-cap/api abort: {exc}"
    except Exception as exc:
        return None, [], f"{type(exc).__name__}: {exc}"

    hits = []
    blocked_candidates: list[dict] = []
    for market in report.get("markets", []):
        if market.get("decision") == "CANDIDATE" and market.get("best_candidate"):
            candidate = market["best_candidate"]
            eligible, reasons = candidate_delivery_eligibility(report, candidate)
            if eligible:
                hits.append((market, candidate))
            else:
                blocked_candidates.append({
                    "market": market.get("market"),
                    "line": market.get("line"),
                    "reasons": reasons,
                })
    if blocked_candidates:
        report["delivery_blocked_candidates"] = blocked_candidates
    return report, hits, None


def log(entry: dict) -> None:
    append_jsonl(LOG_FILE, {**entry, "ts": now_iso()})


def _future_fixture(fixture: dict, now: float) -> bool:
    if float(fixture.get("kickoff_unix") or 0) <= now:
        return False
    status = str(fixture.get("status") or "").casefold()
    return status not in {"complete", "completed", "cancelled", "canceled", "postponed"}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="All-FootyStats daily discovery and hourly bettor alert watcher"
    )
    parser.add_argument("--date", help="UTC date YYYY-MM-DD (default: today)")
    parser.add_argument(
        "--fixture-id",
        action="append",
        dest="fixture_ids",
        help="Scan a specific fixture id (repeatable); overrides daily manifest",
    )
    parser.add_argument(
        "--discover-only",
        action="store_true",
        help="Refresh and persist the all-league daily fixture manifest, then exit",
    )
    parser.add_argument(
        "--refresh-discovery",
        action="store_true",
        help="Refresh the daily manifest before the hourly scan",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print alerts without sending or changing production state",
    )
    args = parser.parse_args()

    import thestatsapi_client as stats_api

    stats_api.RUN_MAX_LIVE_REQUESTS = min(
        stats_api.CONFIGURED_MAX_LIVE_REQUESTS, WATCHER_REQUEST_CAP
    )
    stats_api.MAX_LIVE_REQUESTS = stats_api.RUN_MAX_LIVE_REQUESTS

    day = date.fromisoformat(args.date) if args.date else datetime.now(timezone.utc).date()
    manifest_complete = True
    if args.discover_only:
        manifest, path = discover_and_save(day)
        print(
            "[daily] FootyStats manifest: "
            f"complete={manifest['complete']} leagues={manifest['league_count']} "
            f"seasons={manifest['season_count']} fixtures={len(manifest['fixtures'])} "
            f"analysis_eligible={len(manifest.get('analysis_fixtures', []))} "
            f"failures={len(manifest['failures'])} path={path}"
        )
        log({
            "event": "daily_discovery",
            "day": day.isoformat(),
            "complete": manifest["complete"],
            "fixture_count": len(manifest["fixtures"]),
            "analysis_fixture_count": len(manifest.get("analysis_fixtures", [])),
            "manifest_path": str(path),
        })
        return 0 if manifest["complete"] else 1

    token = os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get(
        "SIGNALS_TELEGRAM_BOT_TOKEN"
    )
    chat_id = (
        os.environ.get("TELEGRAM_CHAT_ID")
        or os.environ.get("SIGNALS_TELEGRAM_CHAT_ID")
        or os.environ.get("HEARTBEAT_TELEGRAM_CHAT_ID")
    )
    if not args.dry_run and (not token or not chat_id):
        print(
            "ABORT: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be set "
            "(or use --dry-run).",
            file=sys.stderr,
        )
        return 2

    if args.fixture_ids:
        targets = [(fixture_id, {}, True) for fixture_id in args.fixture_ids]
        day_label = "explicit-ids"
        manifest_path = None
    else:
        manifest, manifest_path, refreshed = load_or_discover(
            day, refresh=args.refresh_discovery
        )
        manifest_complete = bool(manifest.get("complete"))
        analysis_ids = {
            str(fixture["fixture_id"])
            for fixture in manifest.get("analysis_fixtures", manifest.get("fixtures", []))
        }
        now = time.time()
        targets = [
            (
                str(fixture["fixture_id"]),
                fixture,
                str(fixture["fixture_id"]) in analysis_ids,
            )
            for fixture in manifest.get("fixtures", [])
            if _future_fixture(fixture, now)
        ]
        day_label = day.isoformat()
        print(
            "[watcher] daily manifest: "
            f"refreshed={refreshed} complete={manifest_complete} "
            f"leagues={manifest.get('league_count', 0)} "
            f"all_fixtures={len(manifest.get('fixtures', []))} "
            f"future_fixtures={len(targets)} analysis_eligible={len(analysis_ids)} "
            f"path={manifest_path}"
        )

    print(f"[watcher] scanning {len(targets)} fixture(s) for {day_label}")
    alert_state = load_json(STATE_FILE)
    price_state = load_json(PRICE_STATE_FILE)
    footystats_client = engine._footystats_client(cached=False)
    sent = previewed = scanned = errors = price_events = raw_captures = immutable_quotes = 0

    for fixture_id, fixture_meta, analysis_eligible in targets:
        scanned += 1
        observed = datetime.now(timezone.utc)
        # The EV engine narrows this shared client cap per stage. Restore the
        # watcher-wide remaining-budget ceiling before capturing the next
        # fixture's independent provider observation.
        stats_api.MAX_LIVE_REQUESTS = stats_api.RUN_MAX_LIVE_REQUESTS
        raw_stats = (
            capture_provider_stats(fixture_meta, footystats_client, observed)
            if fixture_meta
            else {"observed_at": observed.isoformat(), "pending_fixture_resolution": True}
        )
        if fixture_meta:
            raw_captures += 1
        prices: list[dict] = []
        changes: list[dict] = []
        odds_observation = {"available": False, "reason": "not analysis eligible"}
        if fixture_meta and analysis_eligible:
            prices, odds_observation = capture_hourly_prices(fixture_meta, observed)
            changes = update_price_state(
                price_state, prices, observed.isoformat(), args.dry_run
            )
            price_events += len(changes)
            immutable_quotes += persist_immutable_quote_snapshots(
                fixture_meta, prices, observed, dry_run=args.dry_run
            )

        if not analysis_eligible:
            append_jsonl(OBSERVATION_LOG, {
                "fixture": fixture_meta,
                "observed_at": observed.isoformat(),
                "raw_provider_stats": raw_stats,
                "odds_observation": odds_observation,
                "historical_analysis": {"available": False, "reason": "not analysis eligible"},
                "prices": prices,
                "price_events": changes,
                "dry_run": args.dry_run,
            })
            print(f"  {fixture_id}: raw stats captured; no verified analysis/odds identity")
            continue

        report, hits, error = scan_fixture(
            fixture_id,
            resolved_fixture=fixture_meta or None,
            refresh_odds=not bool(odds_observation.get("available")),
        )
        if error:
            errors += 1
            print(f"  {fixture_id}: {error}")
            log({"fixture_id": fixture_id, "event": "scan_error", "detail": error})
            append_jsonl(OBSERVATION_LOG, {
                "fixture": fixture_meta,
                "observed_at": observed.isoformat(),
                "raw_provider_stats": raw_stats,
                "odds_observation": odds_observation,
                "historical_analysis": {"available": False, "reason": error},
                "prices": prices,
                "price_events": changes,
                "dry_run": args.dry_run,
            })
            continue

        if not fixture_meta:
            raw_stats = capture_provider_stats(report["fixture"], footystats_client, observed)
            raw_captures += 1
        fixture = report["fixture"]
        if not prices:
            prices = flatten_prices(report)
            changes = update_price_state(
                price_state, prices, report.get("generated_at", observed.isoformat()), args.dry_run
            )
            price_events += len(changes)
            immutable_quotes += persist_immutable_quote_snapshots(
                fixture, prices, observed, dry_run=args.dry_run
            )
        append_jsonl(OBSERVATION_LOG, {
            "fixture": fixture,
            "request_id": report.get("request_id"),
            "report_path": report.get("report_path"),
            "observed_at": observed.isoformat(),
            "raw_provider_stats": raw_stats,
            "odds_observation": odds_observation,
            "historical_analysis": historical_analysis_summary(report),
            "prices": prices,
            "price_events": changes,
            "dry_run": args.dry_run,
        })

        label = f"{fixture['home']} v {fixture['away']}"
        hit_keys = {
            candidate_key(fixture_id, market, candidate)
            for market, candidate in hits
        }
        if not args.dry_run:
            withdrawn_at = now_iso()
            for key, previous in list(alert_state.items()):
                if (
                    key.startswith(f"{fixture_id}:")
                    and previous.get("active", True)
                    and key not in hit_keys
                ):
                    previous["active"] = False
                    previous["withdrawn_at"] = withdrawn_at
                    log({
                        "fixture_id": fixture_id,
                        "event": "candidate_withdrawn",
                        "key": key,
                    })

        if not hits:
            blocked = report.get("delivery_blocked_candidates", [])
            detail = f" delivery_blocked={len(blocked)}" if blocked else ""
            print(
                f"  {fixture_id} {label}: no delivery-eligible candidate; "
                f"prices={len(prices)} changes={len(changes)}{detail}"
            )
            continue

        for market, candidate in hits:
            key = candidate_key(fixture_id, market, candidate)
            if not args.dry_run and not is_new_or_changed(alert_state, key, candidate):
                print(
                    f"  {fixture_id} {label}: {selection_label(market, candidate['side'])} "
                    f"unchanged @ {candidate['decimal_odds']}"
                )
                continue

            message = format_alert(
                fixture, market, candidate, report.get("generated_at")
            )
            if args.dry_run:
                print("---- BETTOR ALERT (dry-run) ----")
                print(message)
                previewed += 1
                log({
                    "fixture_id": fixture_id,
                    "event": "alert_preview",
                    "key": key,
                    "candidate": candidate,
                    "market": market["market"],
                    "line": market["line"],
                })
                continue

            ok, detail = send_telegram(message, token, chat_id)
            log({
                "fixture_id": fixture_id,
                "event": "alert",
                "key": key,
                "sent": ok,
                "detail": detail,
                "candidate": candidate,
                "market": market["market"],
                "line": market["line"],
            })
            if ok:
                sent += 1
                alert_state[key] = {
                    "decimal_odds": candidate["decimal_odds"],
                    "active": True,
                    "alerted_at": now_iso(),
                }
                write_json_atomic(STATE_FILE, alert_state)
                print(
                    f"  {fixture_id} {label}: ALERT "
                    f"{selection_label(market, candidate['side'])} "
                    f"@ {candidate['decimal_odds']} ({candidate['book']})"
                )
            else:
                errors += 1
                print(f"  {fixture_id} {label}: Telegram send FAILED: {detail}")

    if not args.dry_run:
        write_json_atomic(STATE_FILE, alert_state)
        write_json_atomic(PRICE_STATE_FILE, price_state)

    summary = {
        "event": "run_summary",
        "day": day_label,
        "manifest_complete": manifest_complete,
        "manifest_path": str(manifest_path) if manifest_path else None,
        "scanned": scanned,
        "raw_captures": raw_captures,
        "price_events": price_events,
        "immutable_quote_snapshots": immutable_quotes,
        "alerts_sent": sent,
        "previews": previewed,
        "errors": errors,
        "dry_run": args.dry_run,
    }
    print(
        "[watcher] done: "
        f"scanned={scanned} raw_captures={raw_captures} "
        f"price_events={price_events} immutable_quotes={immutable_quotes} alerts_sent={sent} "
        f"previews={previewed} errors={errors}"
    )
    log(summary)
    return 0 if manifest_complete and errors == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
