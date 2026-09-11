"""Tests for canonical genuine-close telemetry (genuine_close_metrics.py).

Proves:
- known genuine closes produce a non-zero count (using the canonical predicate);
- fake/invalid observations (last_seen, kickoff-unknown, non-numeric) never count;
- an unavailable / malformed canonical source reports UNKNOWN, never a fake 0;
- both explicitly-named units (fixtures vs keys) are computed distinctly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.research.prospective.capture import CaptureRecord
from src.research.prospective.genuine_close_metrics import (
    GenuineCloseCounts,
    count_genuine_closes,
    genuine_close_counts_from_root,
)
from src.research.prospective.storage import CaptureStore

K = 2_000_000.0  # kickoff timestamp


def _odds_record(
    *,
    fixture="mt_1",
    market="total_goals",
    selection="over",
    line=2.5,
    bookmaker="pinnacle",
    value=1.90,
    observed_at=K - 60 * 60,
    event_time=K,
    raw_status="PROSPECTIVE_SNAPSHOT",
) -> CaptureRecord:
    line_seg = "" if line is None else f":{line}"
    concept = f"odds:{market}:{selection}{line_seg}:{bookmaker}"
    return CaptureRecord(
        provider="thestatsapi",
        provider_entity_id=fixture,
        canonical_entity_id=fixture,
        concept=concept,
        value=value,
        observed_at=observed_at,
        retrieved_at=observed_at,
        raw_payload_hash="h",
        raw_status=raw_status,
        event_time=event_time,
    )


def _store(tmp_path, records) -> CaptureStore:
    store = CaptureStore(path=tmp_path / "captures.jsonl")
    for r in records:
        store.append(r)
    return store


# --- known genuine closes count (non-zero) ------------------------------


def test_known_genuine_close_counts_non_zero(tmp_path):
    # Two prospective pre-kickoff snapshots for the SAME key -> one genuine close.
    store = _store(tmp_path, [
        _odds_record(observed_at=K - 120 * 60),
        _odds_record(observed_at=K - 30 * 60),
    ])
    counts = count_genuine_closes(store)
    assert counts.available is True
    assert counts.fixtures_with_genuine_close == 1
    assert counts.genuine_closing_keys == 1


def test_distinct_fixtures_and_keys_are_named_distinctly(tmp_path):
    # Fixture A: two keys (over + under) -> 2 keys, 1 fixture.
    # Fixture B: one key -> 1 key, 1 fixture. Total: 2 fixtures, 3 keys.
    store = _store(tmp_path, [
        _odds_record(fixture="A", selection="over", observed_at=K - 40 * 60),
        _odds_record(fixture="A", selection="under", observed_at=K - 40 * 60),
        _odds_record(fixture="B", selection="over", observed_at=K - 40 * 60),
    ])
    counts = count_genuine_closes(store)
    assert counts.fixtures_with_genuine_close == 2
    assert counts.genuine_closing_keys == 3


# --- fake / invalid observations never count ----------------------------


def test_last_seen_semantics_never_counts(tmp_path):
    # A provider last_seen sighting is NOT a genuine close (no real timestamp
    # semantics accepted by the canonical predicate).
    store = _store(tmp_path, [
        _odds_record(raw_status="API_LAST_SEEN", observed_at=K - 30 * 60),
    ])
    counts = count_genuine_closes(store)
    assert counts.available is True
    assert counts.fixtures_with_genuine_close == 0
    assert counts.genuine_closing_keys == 0


def test_kickoff_unknown_never_counts(tmp_path):
    # event_time None => kickoff unknown => canonical predicate returns
    # NO_GENUINE_CLOSE. Must never be counted.
    store = _store(tmp_path, [
        _odds_record(event_time=None, observed_at=K - 30 * 60),
    ])
    counts = count_genuine_closes(store)
    assert counts.available is True
    assert counts.fixtures_with_genuine_close == 0


def test_post_kickoff_snapshot_never_counts(tmp_path):
    # observed_at at/after kickoff is not strictly pre-kickoff -> not genuine.
    store = _store(tmp_path, [
        _odds_record(observed_at=K + 10 * 60),
    ])
    counts = count_genuine_closes(store)
    assert counts.fixtures_with_genuine_close == 0


def test_unknown_raw_status_never_counts(tmp_path):
    # A malformed/unknown status maps to a non-genuine semantics (fail closed),
    # so it can never masquerade as a genuine close.
    store = _store(tmp_path, [
        _odds_record(raw_status="TOTALLY_MADE_UP", observed_at=K - 30 * 60),
    ])
    counts = count_genuine_closes(store)
    assert counts.fixtures_with_genuine_close == 0


def test_real_zero_is_available_not_unknown(tmp_path):
    # A readable store with no genuine close yet is a REAL 0 (available=True),
    # distinct from UNKNOWN.
    store = _store(tmp_path, [
        _odds_record(raw_status="API_LAST_SEEN", observed_at=K - 30 * 60),
    ])
    counts = count_genuine_closes(store)
    assert counts.available is True
    assert counts.fixtures_with_genuine_close == 0


# --- unavailable source reports UNKNOWN (never a fake 0) -----------------


def test_missing_source_reports_unknown_not_zero(tmp_path):
    # No captures file at all -> UNKNOWN, not 0.
    counts = genuine_close_counts_from_root(tmp_path)
    assert counts.available is False
    assert counts.fixtures_with_genuine_close is None
    assert counts.genuine_closing_keys is None


def test_malformed_source_reports_unknown_not_zero(tmp_path, monkeypatch):
    store = _store(tmp_path, [_odds_record(observed_at=K - 30 * 60)])

    def _boom():
        raise OSError("corrupt gzip stream")

    # Simulate an unreadable/malformed store mid-iteration.
    monkeypatch.setattr(store, "read_all", _boom)
    counts = count_genuine_closes(store)
    assert counts.available is False
    assert counts.fixtures_with_genuine_close is None


def test_unknown_counts_dict_shape():
    counts = GenuineCloseCounts(available=False, fixtures_with_genuine_close=None,
                                genuine_closing_keys=None)
    d = counts.to_dict()
    assert d == {
        "available": False,
        "fixtures_with_genuine_close": None,
        "genuine_closing_keys": None,
    }


# --- BLOCKER 4 (review): truncated/partial gzip fails closed to UNKNOWN ----
#
# A truncated .jsonl.gz capture store raises EOFError (zlib, NOT OSError) when
# the compressed stream ends before its end-of-stream marker. That must report
# UNKNOWN (source untrustworthy), never a fabricated 0 and never an escaping
# exception into the monitor.


def _write_truncated_gzip(path: Path, records: int = 300) -> None:
    import gzip

    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8") as fh:
        for i in range(records):
            fh.write(
                '{"provider":"p","provider_entity_id":"e","canonical_entity_id":'
                f'"f{i}","concept":"odds:total_goals:over:2.5:pinnacle","value":"1.9",'
                '"observed_at":1.0,"retrieved_at":1.0,"raw_payload_hash":"h",'
                '"raw_status":"PROSPECTIVE_SNAPSHOT","event_time":2000000.0}\n'
            )
    raw = path.read_bytes()
    path.write_bytes(raw[: len(raw) // 2])  # cut mid-stream -> EOFError on read


def test_truncated_gzip_from_root_reports_unknown_not_zero(tmp_path):
    _write_truncated_gzip(tmp_path / "captures.jsonl.gz")
    counts = genuine_close_counts_from_root(tmp_path)
    assert counts.available is False
    assert counts.fixtures_with_genuine_close is None
    assert counts.genuine_closing_keys is None


def test_truncated_gzip_direct_count_reports_unknown_not_zero(tmp_path):
    # Exercise count_genuine_closes directly (bypassing CaptureStore.__post_init__
    # priming, which would also raise) to prove the metric's own reader fails
    # closed on EOFError rather than raising or fabricating 0.
    path = tmp_path / "captures.jsonl.gz"
    _write_truncated_gzip(path)
    store = object.__new__(CaptureStore)
    store.path = path
    store._seen_ids = set()
    counts = count_genuine_closes(store)
    assert counts.available is False
    assert counts.fixtures_with_genuine_close is None
    assert counts.genuine_closing_keys is None
