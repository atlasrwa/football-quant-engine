"""Point-in-time support audit for Layer 5 market-relative fitting.

The audit reads market-capture timestamps only. It never reads football
outcomes. Its purpose is to prove whether the QFE-owned archive actually
contains observations early enough to support the preregistered pre-protected
market-only and market+QFE fitting windows.
"""
from __future__ import annotations

import gzip
import io
import json
from pathlib import Path
from typing import Any

from src.research.dataset.manifest import sha256_json
from src.research.layer5.market_manifest import snapshot_capture_prefix

SUPPORT_AUDIT_VERSION = "qfe-layer5-market-relative-support-audit-v1"


def audit_market_relative_support(
    *,
    capture_path: Path,
    prefix_size_bytes: int,
    expected_prefix_sha256: str,
    layer4_protocol_path: Path,
) -> dict[str, Any]:
    prefix = snapshot_capture_prefix(Path(capture_path), size_bytes=int(prefix_size_bytes))
    if prefix.sha256 != str(expected_prefix_sha256):
        raise ValueError("capture prefix hash mismatch")

    layer4 = json.loads(Path(layer4_protocol_path).read_text())
    boundary = layer4["scientific_boundary"]
    fit_window = boundary["calibration_fit_window"]
    select_window = boundary["calibration_select_window"]
    calibration_start = int(fit_window["start_ts"])
    fit_end = int(fit_window["end_exclusive_ts"])
    select_start = int(select_window["start_ts"])
    calibration_end = int(select_window["end_exclusive_ts"])
    if fit_end != select_start:
        raise ValueError("Layer 4 calibration FIT/SELECT windows are not contiguous")

    min_observed = None
    max_observed = None
    min_retrieved = None
    max_retrieved = None
    prospective_rows = 0
    thestatsapi_rows = 0

    with gzip.GzipFile(fileobj=io.BytesIO(prefix.data), mode="rb") as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8")
        for line in text:
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                continue
            if row.get("raw_status") != "PROSPECTIVE_SNAPSHOT":
                continue
            prospective_rows += 1
            if row.get("provider") != "thestatsapi":
                continue
            thestatsapi_rows += 1
            observed = row.get("observed_at")
            retrieved = row.get("retrieved_at")
            if isinstance(observed, (int, float)):
                value = float(observed)
                min_observed = value if min_observed is None else min(min_observed, value)
                max_observed = value if max_observed is None else max(max_observed, value)
            if isinstance(retrieved, (int, float)):
                value = float(retrieved)
                min_retrieved = value if min_retrieved is None else min(min_retrieved, value)
                max_retrieved = value if max_retrieved is None else max(max_retrieved, value)

    timestamp_support = min_observed is not None and min_observed < calibration_end
    if not timestamp_support:
        status = "INELIGIBLE_NO_PREPROTECTED_CAPTURE_HISTORY"
        reason = (
            "earliest QFE-owned prospective market observation is not earlier "
            "than the end of the frozen Layer 4 calibration window"
        )
    else:
        status = "TIMESTAMP_WINDOW_POTENTIALLY_ELIGIBLE_NEEDS_FIXTURE_MATCH_AUDIT"
        reason = (
            "capture timestamps overlap the calibration window; exact matched "
            "fixture/market support must still satisfy the protocol minimum"
        )

    result = {
        "version": SUPPORT_AUDIT_VERSION,
        "source_prefix": {
            "size_bytes": prefix.size_bytes,
            "sha256": prefix.sha256,
        },
        "layer4_protocol_hash": sha256_json(layer4),
        "calibration_windows": {
            "fit_start_ts": calibration_start,
            "fit_end_exclusive_ts": fit_end,
            "select_start_ts": select_start,
            "select_end_exclusive_ts": calibration_end,
        },
        "capture_timestamp_span": {
            "prospective_rows": prospective_rows,
            "thestatsapi_rows": thestatsapi_rows,
            "min_observed_at": min_observed,
            "max_observed_at": max_observed,
            "min_retrieved_at": min_retrieved,
            "max_retrieved_at": max_retrieved,
        },
        "market_relative_fit_support": {
            "status": status,
            "reason": reason,
            "minimum_unique_fixtures_required": 250,
            "fit_permitted_from_current_archive": bool(timestamp_support),
            "retrospective_backfill_permitted": False,
        },
        "outcomes_read": False,
    }
    result["audit_hash"] = sha256_json(result)
    return result


def render_market_relative_support_markdown(audit: dict[str, Any]) -> str:
    span = audit["capture_timestamp_span"]
    windows = audit["calibration_windows"]
    support = audit["market_relative_fit_support"]
    return "\n".join(
        [
            "# QFE V2 Layer 5 — Market-Relative Support Audit",
            "",
            f"Audit hash: {audit['audit_hash']}",
            "",
            f"Status: **{support['status']}**",
            "",
            f"- Layer 4 CALIBRATION starts: {windows['fit_start_ts']}",
            f"- Layer 4 CALIBRATION ends (exclusive): {windows['select_end_exclusive_ts']}",
            f"- Earliest QFE-owned observed_at in frozen capture prefix: {span['min_observed_at']}",
            f"- Latest QFE-owned observed_at in frozen capture prefix: {span['max_observed_at']}",
            f"- Minimum matched unique fixtures required by Layer 5: {support['minimum_unique_fixtures_required']}",
            f"- Fit permitted from current archive: {support['fit_permitted_from_current_archive']}",
            f"- Retrospective odds backfill permitted: {support['retrospective_backfill_permitted']}",
            "",
            support["reason"],
            "",
            "> Timestamp/provenance audit only. Football outcomes were not read.",
        ]
    ) + "\n"


def write_market_relative_support_audit(
    *,
    json_path: Path,
    markdown_path: Path,
    audit: dict[str, Any],
) -> None:
    json_path = Path(json_path)
    markdown_path = Path(markdown_path)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    markdown_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(audit, sort_keys=True, separators=(",", ":")) + "\n"
    markdown = render_market_relative_support_markdown(audit)
    for path, content in ((json_path, payload), (markdown_path, markdown)):
        if path.exists() and path.read_text() != content:
            raise FileExistsError(path)
        if not path.exists():
            path.write_text(content)
