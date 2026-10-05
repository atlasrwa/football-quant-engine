import gzip
import json
from pathlib import Path

from src.research.layer5.market_manifest import (
    build_matched_market_manifest,
    snapshot_capture_prefix,
    write_matched_market_manifest,
)


def _chrono(path: Path, fixture_ids=("mt_a", "mt_b")):
    keys = [f"THESTATSAPI:{x}" for x in fixture_ids]
    obj = {
        "manifest_hash": "chrono_hash",
        "partitions": [
            {
                "partition": "PROTECTED",
                "fixture_keys": keys,
                "n_fixtures": len(keys),
                "fixture_membership_hash": "membership",
            }
        ],
    }
    path.write_text(json.dumps(obj))


def _row(fid, concept, value, *, ko=100000.0, obs=78000.0, raw="h"):
    return {
        "provider": "thestatsapi",
        "canonical_entity_id": fid,
        "concept": concept,
        "value": value,
        "event_time": ko,
        "observed_at": obs,
        "retrieved_at": obs,
        "raw_payload_hash": raw,
        "raw_status": "PROSPECTIVE_SNAPSHOT",
    }


def _gz(path: Path, rows):
    raw = "".join(json.dumps(r, separators=(",", ":")) + "\n" for r in rows).encode()
    path.write_bytes(gzip.compress(raw, mtime=0))


def test_manifest_uses_direct_protected_identity_and_frozen_book_hierarchy(tmp_path):
    chrono = tmp_path / "chrono.json"
    _chrono(chrono)
    cap = tmp_path / "captures.gz"
    rows = []
    for book, over, under in (("pinnacle", 1.9, 1.9), ("bet365", 4.0, 1.3)):
        rows += [
            _row("mt_a", f"odds:total_goals:over:2.5:{book}", over, raw=book),
            _row("mt_a", f"odds:total_goals:under:2.5:{book}", under, raw=book),
        ]
    rows += [
        _row("mt_x", "odds:total_goals:over:2.5:pinnacle", 2.0),
        _row("mt_x", "odds:total_goals:under:2.5:pinnacle", 2.0),
    ]
    _gz(cap, rows)
    prefix = snapshot_capture_prefix(cap)
    manifest, kept = build_matched_market_manifest(
        capture_prefix=prefix,
        chronology_path=chrono,
    )
    a = next(x for x in manifest["fixture_rows"] if x["fixture_id"] == "mt_a")
    assert a["markets"]["GOALS_TOTAL"]["status"] == "OK"
    assert a["markets"]["GOALS_TOTAL"]["bookmaker"] == "pinnacle"
    assert all(r["fixture_id"] in {"mt_a", "mt_b"} for r in kept)
    assert manifest["protected_outcomes_read"] is False


def test_manifest_does_not_fallback_after_selected_book_price_failure(tmp_path):
    chrono = tmp_path / "chrono.json"
    _chrono(chrono, ("mt_a",))
    cap = tmp_path / "captures.gz"
    rows = []
    for book, over, under in (("pinnacle", 1.0, 2.0), ("bet365", 2.0, 2.0)):
        rows += [
            _row("mt_a", f"odds:total_goals:over:2.5:{book}", over, raw=book),
            _row("mt_a", f"odds:total_goals:under:2.5:{book}", under, raw=book),
        ]
    _gz(cap, rows)
    manifest, _ = build_matched_market_manifest(
        capture_prefix=snapshot_capture_prefix(cap),
        chronology_path=chrono,
    )
    a = manifest["fixture_rows"][0]["markets"]["GOALS_TOTAL"]
    assert a["status"] == "ABSTAIN"
    assert a["reason"] == "TWO_SIDED_QUOTE_MISSING"


def test_manifest_writer_is_byte_idempotent(tmp_path):
    chrono = tmp_path / "chrono.json"
    _chrono(chrono, ("mt_a",))
    cap = tmp_path / "captures.gz"
    _gz(
        cap,
        [
            _row("mt_a", "odds:total_goals:over:2.5:pinnacle", 2.0),
            _row("mt_a", "odds:total_goals:under:2.5:pinnacle", 2.0),
        ],
    )
    manifest, rows = build_matched_market_manifest(
        capture_prefix=snapshot_capture_prefix(cap),
        chronology_path=chrono,
    )
    p1, p2 = write_matched_market_manifest(
        output_dir=tmp_path / "out",
        manifest=manifest,
        retained_rows=rows,
    )
    before = (p1.read_bytes(), p2.read_bytes())
    write_matched_market_manifest(
        output_dir=tmp_path / "out",
        manifest=manifest,
        retained_rows=rows,
    )
    assert before == (p1.read_bytes(), p2.read_bytes())


def test_capture_prefix_hash_binds_exact_bytes(tmp_path):
    cap = tmp_path / "captures.gz"
    _gz(cap, [_row("mt_a", "odds:total_goals:over:2.5:pinnacle", 2.0)])
    frozen = snapshot_capture_prefix(cap)
    cap.write_bytes(cap.read_bytes() + gzip.compress(b'{"extra":1}\n', mtime=0))
    reproduced = snapshot_capture_prefix(cap, size_bytes=frozen.size_bytes)
    assert reproduced.sha256 == frozen.sha256
    assert reproduced.data == frozen.data


def test_historical_manifest_builder_remains_pinned_to_v1_1(tmp_path):
    from src.research.layer5.protocol import LAYER5_PROTOCOL_V1_1_HASH, active_protocol_hash
    chrono = tmp_path / "chrono.json"
    _chrono(chrono, ("mt_a",))
    cap = tmp_path / "captures.gz"
    _gz(
        cap,
        [
            _row("mt_a", "odds:total_goals:over:2.5:pinnacle", 2.0),
            _row("mt_a", "odds:total_goals:under:2.5:pinnacle", 2.0),
        ],
    )
    manifest, _ = build_matched_market_manifest(
        capture_prefix=snapshot_capture_prefix(cap),
        chronology_path=chrono,
    )
    assert active_protocol_hash() != LAYER5_PROTOCOL_V1_1_HASH
    assert manifest["active_protocol_hash"] == LAYER5_PROTOCOL_V1_1_HASH
