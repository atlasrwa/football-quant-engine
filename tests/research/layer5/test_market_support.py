import gzip
import hashlib
import json
from pathlib import Path

from src.research.dataset.manifest import sha256_json
from src.research.layer5.market_support import audit_market_relative_support


def _write_capture(path: Path, rows):
    raw = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows).encode()
    path.write_bytes(gzip.compress(raw, mtime=0))


def _write_protocol(path: Path):
    obj = {
        "scientific_boundary": {
            "calibration_fit_window": {"start_ts": 100, "end_exclusive_ts": 200},
            "calibration_select_window": {"start_ts": 200, "end_exclusive_ts": 300},
        }
    }
    path.write_text(json.dumps(obj))
    return obj


def test_support_audit_fails_closed_when_capture_starts_after_calibration(tmp_path):
    capture = tmp_path / "captures.jsonl.gz"
    rows = [
        {
            "provider": "thestatsapi",
            "raw_status": "PROSPECTIVE_SNAPSHOT",
            "observed_at": 400.0,
            "retrieved_at": 401.0,
        }
    ]
    _write_capture(capture, rows)
    protocol = tmp_path / "layer4.json"
    obj = _write_protocol(protocol)
    prefix_sha = hashlib.sha256(capture.read_bytes()).hexdigest()

    audit = audit_market_relative_support(
        capture_path=capture,
        prefix_size_bytes=capture.stat().st_size,
        expected_prefix_sha256=prefix_sha,
        layer4_protocol_path=protocol,
    )
    support = audit["market_relative_fit_support"]
    assert support["status"] == "INELIGIBLE_NO_PREPROTECTED_CAPTURE_HISTORY"
    assert support["fit_permitted_from_current_archive"] is False
    assert support["retrospective_backfill_permitted"] is False
    assert audit["layer4_protocol_hash"] == sha256_json(obj)
    assert audit["outcomes_read"] is False


def test_support_audit_only_claims_potential_eligibility_on_timestamp_overlap(tmp_path):
    capture = tmp_path / "captures.jsonl.gz"
    rows = [
        {
            "provider": "thestatsapi",
            "raw_status": "PROSPECTIVE_SNAPSHOT",
            "observed_at": 250.0,
            "retrieved_at": 251.0,
        },
        {
            "provider": "other",
            "raw_status": "PROSPECTIVE_SNAPSHOT",
            "observed_at": 150.0,
            "retrieved_at": 151.0,
        },
    ]
    _write_capture(capture, rows)
    protocol = tmp_path / "layer4.json"
    _write_protocol(protocol)
    prefix_sha = hashlib.sha256(capture.read_bytes()).hexdigest()

    audit = audit_market_relative_support(
        capture_path=capture,
        prefix_size_bytes=capture.stat().st_size,
        expected_prefix_sha256=prefix_sha,
        layer4_protocol_path=protocol,
    )
    support = audit["market_relative_fit_support"]
    assert support["status"].startswith("TIMESTAMP_WINDOW_POTENTIALLY_ELIGIBLE")
    assert support["fit_permitted_from_current_archive"] is True
