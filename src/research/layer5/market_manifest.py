"""Freeze a protected matched-market manifest without reading outcomes.

The builder scans an exact byte prefix of the QFE prospective capture store,
uses only protected fixture identity + timestamped odds metadata, applies the
frozen Layer 5 V1.1 bookmaker/bundle rules, and emits immutable market rows.
Football outcomes are neither required nor accepted by this module.
"""
from __future__ import annotations

import gzip
import hashlib
import io
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable

from src.research.dataset.manifest import canonical_json, sha256_json
from src.research.layer5.market_surface import (
    MarketSurface,
    TwoWayQuote,
    build_market_point,
    build_market_surface,
    select_benchmark_bundle,
)
from src.research.layer5.protocol import active_protocol_hash, protocol_active

MANIFEST_VERSION = "qfe-layer5-matched-market-manifest-v1.1"
_REGISTERED_GOAL_LINE = 2.5
_REGISTERED_CORNER_LINES = (7.5, 8.5, 9.5, 10.5, 11.5, 12.5)


@dataclass(frozen=True, slots=True)
class CapturePrefix:
    size_bytes: int
    sha256: str
    data: bytes


@dataclass(frozen=True, slots=True)
class PairRow:
    fixture_id: str
    market_key: str
    bookmaker: str
    line: float
    observed_at: float
    event_time: float
    raw_payload_hash: str
    over_odds: float
    under_odds: float

    @property
    def bundle_id(self) -> str:
        return f"{self.observed_at:.6f}:{self.raw_payload_hash}"

    def quote(self) -> TwoWayQuote:
        return TwoWayQuote(
            fixture_id=self.fixture_id,
            market_key=self.market_key,
            bookmaker=self.bookmaker,
            line=self.line,
            over_odds=self.over_odds,
            under_odds=self.under_odds,
            observed_at=self.observed_at,
            bundle_id=self.bundle_id,
        )


def snapshot_capture_prefix(path: Path, *, size_bytes: int | None = None) -> CapturePrefix:
    path = Path(path)
    n = path.stat().st_size if size_bytes is None else int(size_bytes)
    if n <= 0:
        raise ValueError("capture prefix must be non-empty")
    with path.open("rb") as fh:
        data = fh.read(n)
    if len(data) != n:
        raise ValueError("capture store shorter than requested frozen prefix")
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as gz:
            while gz.read(1024 * 1024):
                pass
    except (EOFError, OSError) as exc:
        raise ValueError("capture prefix ends in an incomplete/corrupt gzip member") from exc
    return CapturePrefix(size_bytes=n, sha256=hashlib.sha256(data).hexdigest(), data=data)


def _protected_contract(chronology_path: Path) -> tuple[tuple[str, ...], str, str]:
    obj = json.loads(Path(chronology_path).read_text())
    protected = next(p for p in obj["partitions"] if p["partition"] == "PROTECTED")
    fixture_ids = tuple(sorted(k.split(":", 1)[1] for k in protected["fixture_keys"]))
    if len(fixture_ids) != int(protected["n_fixtures"]):
        raise ValueError("protected fixture-count mismatch")
    return fixture_ids, str(protected["fixture_membership_hash"]), sha256_json(obj)


def _iter_prefix_rows(prefix: CapturePrefix) -> Iterable[dict[str, Any]]:
    with gzip.GzipFile(fileobj=io.BytesIO(prefix.data), mode="rb") as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8")
        for line in text:
            if line.strip():
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value


def _parse_registered(
    row: dict[str, Any],
    protected: set[str],
) -> tuple[str, str, str, float, str] | None:
    if row.get("provider") != "thestatsapi":
        return None
    if row.get("raw_status") != "PROSPECTIVE_SNAPSHOT":
        return None
    fixture_id = str(row.get("canonical_entity_id") or "")
    if fixture_id not in protected:
        return None
    concept = str(row.get("concept") or "")
    parts = concept.split(":")
    if len(parts) != 5 or parts[0] != "odds":
        return None
    provider_market, selection, line_raw, bookmaker = parts[1], parts[2], parts[3], parts[4]
    if selection not in {"over", "under"}:
        return None
    try:
        line = float(line_raw)
    except ValueError:
        return None
    if provider_market == "total_goals" and abs(line - _REGISTERED_GOAL_LINE) <= 1e-9:
        return fixture_id, "GOALS_TOTAL", selection, line, bookmaker
    if provider_market == "match_corners" and line in _REGISTERED_CORNER_LINES:
        return fixture_id, "CORNERS_TOTAL", selection, line, bookmaker
    return None


def _surface_dict(surface: MarketSurface) -> dict[str, Any]:
    return {
        "status": surface.status,
        "reason": surface.reason,
        "bookmaker": surface.bookmaker,
        "bundle_id": surface.bundle_id,
        "prediction_cutoff": surface.prediction_cutoff,
        "observed_at_min": surface.observed_at_min,
        "observed_at_max": surface.observed_at_max,
        "max_abs_repair": surface.max_abs_repair,
        "mean_abs_repair": surface.mean_abs_repair,
        "points": [asdict(p) for p in surface.points],
    }


def build_matched_market_manifest(
    *,
    capture_prefix: CapturePrefix,
    chronology_path: Path,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    protocol = protocol_active()
    fixture_ids, membership_hash, chronology_hash = _protected_contract(chronology_path)
    protected = set(fixture_ids)
    horizon = protocol["market_horizon"]

    retained: list[dict[str, Any]] = []
    pair_cells: dict[tuple[str, str, str, float, float, str], dict[str, float]] = {}
    event_times: dict[str, set[float]] = {fid: set() for fid in fixture_ids}
    source_counts = {
        "json_rows_scanned": 0,
        "protected_odds_rows_seen": 0,
        "registered_rows_seen": 0,
        "registered_rows_in_t6_window": 0,
        "invalid_timestamp_rows": 0,
    }

    for row in _iter_prefix_rows(capture_prefix):
        source_counts["json_rows_scanned"] += 1
        fixture_id = str(row.get("canonical_entity_id") or "")
        concept = str(row.get("concept") or "")
        if fixture_id in protected and concept.startswith("odds:"):
            source_counts["protected_odds_rows_seen"] += 1
        parsed = _parse_registered(row, protected)
        if parsed is None:
            continue
        source_counts["registered_rows_seen"] += 1
        fixture_id, market_key, selection, line, bookmaker = parsed
        try:
            event_time = float(row["event_time"])
            observed_at = float(row["observed_at"])
            retrieved_at = float(row["retrieved_at"])
            odds = float(row["value"])
        except (KeyError, TypeError, ValueError):
            source_counts["invalid_timestamp_rows"] += 1
            continue
        if abs(observed_at - retrieved_at) > 1e-6:
            source_counts["invalid_timestamp_rows"] += 1
            continue
        event_times[fixture_id].add(event_time)
        cutoff = event_time - float(horizon["target_seconds_before_kickoff"])
        age = cutoff - observed_at
        if age < 0 or age > float(horizon["max_snapshot_age_seconds"]):
            continue
        source_counts["registered_rows_in_t6_window"] += 1
        raw_hash = str(row.get("raw_payload_hash") or "")
        if not raw_hash:
            source_counts["invalid_timestamp_rows"] += 1
            continue
        frozen_row = {
            "provider": "thestatsapi",
            "fixture_id": fixture_id,
            "event_time": event_time,
            "observed_at": observed_at,
            "retrieved_at": retrieved_at,
            "raw_payload_hash": raw_hash,
            "market_key": market_key,
            "selection": selection,
            "line": line,
            "bookmaker": bookmaker,
            "decimal_odds": odds,
        }
        retained.append(frozen_row)
        cell = (fixture_id, market_key, bookmaker, line, observed_at, raw_hash)
        pair_cells.setdefault(cell, {})[selection] = odds

    conflicts = {fid: sorted(v) for fid, v in event_times.items() if len(v) > 1}
    if conflicts:
        raise ValueError(f"protected capture kickoff conflicts: {list(conflicts)[:5]}")

    pairs: list[PairRow] = []
    for (fid, market, book, line, obs, raw_hash), sels in sorted(pair_cells.items()):
        if set(sels) != {"over", "under"}:
            continue
        event_time = next(iter(event_times[fid]))
        pairs.append(
            PairRow(
                fid,
                market,
                book,
                line,
                obs,
                event_time,
                raw_hash,
                sels["over"],
                sels["under"],
            )
        )

    by_fixture_market: dict[tuple[str, str], list[TwoWayQuote]] = {}
    for pair in pairs:
        by_fixture_market.setdefault((pair.fixture_id, pair.market_key), []).append(pair.quote())

    fixture_rows: list[dict[str, Any]] = []
    valid_counts = {"GOALS_TOTAL": 0, "CORNERS_TOTAL": 0, "CORNERS_SIDE": 0}
    reason_counts: dict[str, int] = {}

    for fid in fixture_ids:
        event_set = event_times[fid]
        event_time = next(iter(event_set)) if event_set else None
        cutoff = (
            event_time - float(horizon["target_seconds_before_kickoff"])
            if event_time is not None
            else None
        )
        markets: dict[str, Any] = {}
        for market_key, min_lines in (
            ("GOALS_TOTAL", 1),
            ("CORNERS_TOTAL", protocol["market_surface"]["minimum_adjacent_lines"]),
        ):
            quotes = by_fixture_market.get((fid, market_key), [])
            if cutoff is None or not quotes:
                market_result = {
                    "status": "ABSTAIN",
                    "reason": "MARKET_HORIZON_MISSING",
                    "points": [],
                }
            else:
                selected = select_benchmark_bundle(
                    quotes,
                    prediction_cutoff=cutoff,
                    market_key=market_key,
                    minimum_adjacent_lines=int(min_lines),
                )
                if not selected:
                    market_result = {
                        "status": "ABSTAIN",
                        "reason": "BOOKMAKER_HIERARCHY_NO_COMPLETE_MARKET",
                        "points": [],
                    }
                elif market_key == "GOALS_TOTAL":
                    if len(selected) != 1:
                        raise ValueError("goal matched bundle must contain one registered line")
                    market_result = _surface_dict(
                        build_market_point(selected[0], prediction_cutoff=cutoff)
                    )
                else:
                    market_result = _surface_dict(
                        build_market_surface(selected, prediction_cutoff=cutoff)
                    )
            if market_result["status"] == "OK":
                valid_counts[market_key] += 1
            else:
                reason = str(market_result.get("reason") or "UNKNOWN")
                reason_counts[reason] = reason_counts.get(reason, 0) + 1
            markets[market_key] = market_result

        markets["CORNERS_SIDE"] = {
            "status": "ABSTAIN",
            "reason": "TARGET_UNSUPPORTED",
            "detail": "primary protected capture source contains no registered team-corner concepts",
            "points": [],
        }
        reason_counts["TARGET_UNSUPPORTED"] = reason_counts.get("TARGET_UNSUPPORTED", 0) + 1
        fixture_rows.append(
            {
                "fixture_id": fid,
                "event_time": event_time,
                "prediction_cutoff": cutoff,
                "markets": markets,
            }
        )

    retained_sorted = tuple(
        sorted(
            retained,
            key=lambda r: (
                r["fixture_id"],
                r["market_key"],
                r["bookmaker"],
                r["observed_at"],
                r["line"],
                r["selection"],
            ),
        )
    )
    fixture_rows = sorted(fixture_rows, key=lambda r: r["fixture_id"])
    manifest: dict[str, Any] = {
        "version": MANIFEST_VERSION,
        "active_protocol_hash": active_protocol_hash(),
        "scientific_status": "MARKET_METADATA_ONLY_PROTECTED_OUTCOMES_UNOPENED",
        "chronology_manifest_hash": chronology_hash,
        "protected_fixture_membership_hash": membership_hash,
        "protected_fixture_count": len(fixture_ids),
        "source": {
            "kind": protocol["market_source"]["primary_source"],
            "provider": protocol["market_source"]["provider"],
            "prefix_size_bytes": capture_prefix.size_bytes,
            "prefix_sha256": capture_prefix.sha256,
            "raw_status_required": protocol["market_source"]["required_raw_status"],
        },
        "source_counts": source_counts,
        "retained_source_rows_hash": sha256_json(retained_sorted),
        "retained_source_row_count": len(retained_sorted),
        "fixture_rows_hash": sha256_json(fixture_rows),
        "valid_matched_market_counts": valid_counts,
        "abstention_reason_counts": dict(sorted(reason_counts.items())),
        "fixture_rows": fixture_rows,
        "protected_outcomes_read": False,
    }
    manifest["manifest_hash"] = sha256_json(manifest)
    return manifest, retained_sorted


def write_matched_market_manifest(
    *,
    output_dir: Path,
    manifest: dict[str, Any],
    retained_rows: Iterable[dict[str, Any]],
) -> tuple[Path, Path]:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "QFE_LAYER5_MATCHED_MARKET_MANIFEST_V1_1.json"
    rows_path = output_dir / "QFE_LAYER5_MATCHED_MARKET_SOURCE_ROWS_V1_1.jsonl.gz"
    manifest_payload = canonical_json(manifest) + "\n"
    raw = "".join(canonical_json(r) + "\n" for r in retained_rows).encode()
    rows_payload = gzip.compress(raw, compresslevel=9, mtime=0)
    for path, payload in (
        (manifest_path, manifest_payload.encode()),
        (rows_path, rows_payload),
    ):
        if path.exists() and path.read_bytes() != payload:
            raise FileExistsError(f"frozen matched-market artifact differs: {path}")
        if not path.exists():
            path.write_bytes(payload)
    return manifest_path, rows_path
