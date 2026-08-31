"""Tests for the tamper-evident commit-reveal attestation ledger.

These tests enforce the hardening-brief invariants:
- commitments bind prediction + fixture + reference price + timestamp
- pre-kickoff enforcement (no commitment after kickoff; never backdated)
- immutability: any edit / reorder / insertion is detectable
- reveal requires a prior commitment
"""

import json

import pytest

from src.research.forward.attestation_ledger import (
    AttestationLedger,
    LedgerTamperError,
    compute_commitment_hash,
    GENESIS_PREV_HASH,
)


def _ledger(tmp_path, clock):
    return AttestationLedger(
        commit_path=tmp_path / "commitments.jsonl",
        reveal_path=tmp_path / "reveals.jsonl",
        clock=clock,
    )


class FakeClock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t


def test_commit_before_kickoff_succeeds_and_binds_reference_price(tmp_path):
    clock = FakeClock(1000.0)
    led = _ledger(tmp_path, clock)
    res = led.commit(
        prediction_id="p1", fixture_id="f1", model="goals_2.5",
        kickoff_unix=2000.0, p_over=0.55, p_under=0.45,
        reference_price={"book": "betfair-exchange", "over_odds": 1.9,
                         "under_odds": 2.1, "fair_p_over": 0.52},
    )
    assert res.committed is True
    assert res.record["pre_kickoff"] is True
    assert res.record["anchor_unix"] == 1000.0
    # reference price is bound into the commitment hash
    expected = compute_commitment_hash(
        prediction_id="p1", fixture_id="f1", model="goals_2.5",
        p_over=0.55, p_under=0.45,
        reference_price={"book": "betfair-exchange", "over_odds": 1.9,
                         "under_odds": 2.1, "fair_p_over": 0.52},
        prediction_timestamp=res.record["prediction_timestamp"],
    )
    assert res.record["commitment_hash"] == expected


def test_reference_price_change_changes_hash(tmp_path):
    a = compute_commitment_hash(
        prediction_id="p", fixture_id="f", model="m", p_over=0.5, p_under=0.5,
        reference_price={"book": "betfair", "over_odds": 1.9},
        prediction_timestamp="2026-01-01T00:00:00+00:00",
    )
    b = compute_commitment_hash(
        prediction_id="p", fixture_id="f", model="m", p_over=0.5, p_under=0.5,
        reference_price={"book": "betfair", "over_odds": 2.0},  # different price
        prediction_timestamp="2026-01-01T00:00:00+00:00",
    )
    assert a != b


def test_commit_after_kickoff_refused_not_backdated(tmp_path):
    clock = FakeClock(3000.0)  # after kickoff
    led = _ledger(tmp_path, clock)
    res = led.commit(
        prediction_id="p1", fixture_id="f1", model="goals_2.5",
        kickoff_unix=2000.0,
    )
    assert res.committed is False
    assert "kicked off" in res.reason
    # nothing written
    assert not (tmp_path / "commitments.jsonl").exists()


def test_anchor_timestamp_ignores_caller_supplied_time(tmp_path):
    clock = FakeClock(1500.0)
    led = _ledger(tmp_path, clock)
    # caller tries to claim an earlier prediction_timestamp; anchor stays our clock
    res = led.commit(
        prediction_id="p1", fixture_id="f1", model="m", kickoff_unix=9999.0,
        prediction_timestamp="1970-01-01T00:00:00+00:00",
    )
    assert res.committed is True
    assert res.record["anchor_unix"] == 1500.0  # our clock, not 1970


def test_chain_verification_passes_for_untampered_ledger(tmp_path):
    clock = FakeClock(1000.0)
    led = _ledger(tmp_path, clock)
    for i in range(3):
        clock.t = 1000.0 + i
        r = led.commit(prediction_id=f"p{i}", fixture_id=f"f{i}", model="m",
                       kickoff_unix=1_000_000.0)
        assert r.committed
    ok, problems = led.verify_chain()
    assert ok, problems
    # first record chains to genesis
    rows = led.load_commitments()
    assert rows[0]["prev_hash"] == GENESIS_PREV_HASH
    assert rows[1]["prev_hash"] == rows[0]["link_hash"]


def test_tamper_detected_on_content_edit(tmp_path):
    clock = FakeClock(1000.0)
    led = _ledger(tmp_path, clock)
    led.commit(prediction_id="p0", fixture_id="f0", model="m", p_over=0.5,
               kickoff_unix=1_000_000.0)
    path = tmp_path / "commitments.jsonl"
    rows = [json.loads(l) for l in open(path)]
    rows[0]["p_over"] = 0.99  # edit committed content, leave hashes
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    ok, problems = led.verify_chain()
    assert not ok
    assert any("link_hash mismatch" in p for p in problems)


def test_tamper_detected_on_reorder(tmp_path):
    clock = FakeClock(1000.0)
    led = _ledger(tmp_path, clock)
    for i in range(3):
        clock.t = 1000.0 + i
        led.commit(prediction_id=f"p{i}", fixture_id=f"f{i}", model="m",
                   kickoff_unix=1_000_000.0)
    path = tmp_path / "commitments.jsonl"
    rows = [json.loads(l) for l in open(path)]
    rows[0], rows[2] = rows[2], rows[0]  # reorder
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    ok, problems = led.verify_chain()
    assert not ok


def test_refuses_to_append_to_tampered_ledger(tmp_path):
    clock = FakeClock(1000.0)
    led = _ledger(tmp_path, clock)
    led.commit(prediction_id="p0", fixture_id="f0", model="m", kickoff_unix=1_000_000.0)
    path = tmp_path / "commitments.jsonl"
    rows = [json.loads(l) for l in open(path)]
    rows[0]["model"] = "tampered"
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    clock.t = 1001.0
    with pytest.raises(LedgerTamperError):
        led.commit(prediction_id="p1", fixture_id="f1", model="m",
                   kickoff_unix=1_000_000.0)


def test_reveal_requires_prior_commitment(tmp_path):
    clock = FakeClock(1000.0)
    led = _ledger(tmp_path, clock)
    res = led.reveal(prediction_id="nope", fixture_id="f", model="m",
                     outcome={"actual_over": 1.0})
    assert res.committed is False
    assert "no prior commitment" in res.reason


def test_reveal_after_commit_succeeds_and_binds_commitment(tmp_path):
    clock = FakeClock(1000.0)
    led = _ledger(tmp_path, clock)
    c = led.commit(prediction_id="p1", fixture_id="f1", model="m",
                   kickoff_unix=2000.0, p_over=0.6)
    clock.t = 5000.0  # after settlement
    r = led.reveal(prediction_id="p1", fixture_id="f1", model="m",
                   outcome={"actual_over": 1.0, "actual_total": 3})
    assert r.committed is True
    assert r.record["commitment_hash"] == c.record["commitment_hash"]
    ok, problems = led.verify_chain(led.reveal_path)
    assert ok, problems



# ── document attestation (pre-registration) ──────────────────────────────

from src.research.forward.attestation_ledger import (  # noqa: E402
    attest_document,
    compute_document_hash,
)


def test_attest_document_records_hash_and_is_idempotent(tmp_path):
    doc = tmp_path / "prereg.json"
    doc.write_text('{"plan": "primary hypothesis X"}')
    ledger = tmp_path / "prereg_ledger.jsonl"

    clock = FakeClock(1000.0)
    r1 = attest_document(ledger, document_path=doc, document_id="prereg_v1", clock=clock)
    assert r1["document_hash"] == compute_document_hash(doc)
    assert r1["anchor_unix"] == 1000.0

    # same content -> same record (idempotent), no duplicate line
    clock.t = 2000.0
    r2 = attest_document(ledger, document_path=doc, document_id="prereg_v1", clock=clock)
    assert r1["link_hash"] == r2["link_hash"]
    assert len([l for l in open(ledger) if l.strip()]) == 1


def test_attest_document_detects_edit_via_hash_change(tmp_path):
    doc = tmp_path / "prereg.json"
    doc.write_text('{"plan": "original"}')
    ledger = tmp_path / "prereg_ledger.jsonl"
    clock = FakeClock(1000.0)
    r1 = attest_document(ledger, document_path=doc, document_id="prereg_v1", clock=clock)

    # edit the document after registration -> hash changes -> new attestation row
    doc.write_text('{"plan": "SECRETLY CHANGED"}')
    clock.t = 3000.0
    r2 = attest_document(ledger, document_path=doc, document_id="prereg_v1", clock=clock)
    assert r2["document_hash"] != r1["document_hash"]
    # two distinct rows now exist — the tampering is on the permanent record
    assert len([l for l in open(ledger) if l.strip()]) == 2
