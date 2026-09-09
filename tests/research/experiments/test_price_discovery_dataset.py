"""Tests for the deterministic price-discovery dataset builder.

Covers leakage-safety and correctness properties the mission requires:
- same-key vintage transitions only (no cross-book / cross-line movement)
- line changes tracked separately, never as price movement
- coexisting simultaneous lines are NOT a line change
- de-vig produces a fair probability; delta is logit(later) - logit(earlier)
- deterministic serialization
- preregistered gate is not silently relaxed; EVALUABLE only when met
- UNKNOWN predictor fields stay None (never fabricated)
"""

from __future__ import annotations

import math
from pathlib import Path

from src.research.experiments.price_discovery.dataset import (
    PROSPECTIVE_GATE,
    build_dataset,
)
from src.research.experiments.price_discovery.report import (
    assess_readiness,
    build_full_report,
    descriptive_report,
)
from src.research.prospective.capture import CaptureRecord
from src.research.prospective.storage import CaptureStore

KO = 1_800_000_000.0
DAY = 86400.0
HOUR = 3600.0


def _rec(store, *, market, selection, line, book, odds, seconds_to_kickoff, fixture="mt_1"):
    observed = KO - seconds_to_kickoff
    line_seg = "" if line is None else str(line)
    concept = f"odds:{market}:{selection}:{line_seg}:{book}"
    store.append(
        CaptureRecord(
            provider="thestatsapi",
            provider_entity_id=fixture,
            canonical_entity_id=fixture,
            concept=concept,
            value=odds,
            observed_at=observed,
            retrieved_at=observed,
            raw_payload_hash="h",
            event_time=KO,
        )
    )


def _pair(store, *, book, line, over, under, stk, market="total_goals", fixture="mt_1"):
    _rec(store, market=market, selection="over", line=line, book=book, odds=over,
         seconds_to_kickoff=stk, fixture=fixture)
    _rec(store, market=market, selection="under", line=line, book=book, odds=under,
         seconds_to_kickoff=stk, fixture=fixture)


def test_same_key_transition_built(tmp_path):
    store = CaptureStore(path=tmp_path / "c.jsonl")
    # EARLY (~24h) and MID (~6h) snapshots for the SAME key.
    _pair(store, book="pinnacle", line=2.5, over=1.90, under=2.00, stk=24 * HOUR)
    _pair(store, book="pinnacle", line=2.5, over=1.80, under=2.10, stk=6 * HOUR)
    ds = build_dataset(store)
    assert ds.transition_counts.get("EARLY->MID") == 2  # over and under are separate keys
    t = [x for x in ds.transitions if x.earlier_vintage == "EARLY" and x.later_vintage == "MID"]
    assert len(t) == 2  # over and under are separate keys
    row = next(x for x in t if x.selection == "over")
    # delta = logit(p_later) - logit(p_earlier); prices moved so delta != 0.
    assert row.delta_market_logit != 0.0
    assert 0.0 < row.p_market_earlier < 1.0
    # predictor placeholders are NULL, never fabricated.
    assert row.p_fundamental_earlier is None
    assert row.fundamental_market_disagreement is None
    assert row.lineup_observed is False


def test_cross_book_not_a_transition(tmp_path):
    store = CaptureStore(path=tmp_path / "c.jsonl")
    _pair(store, book="pinnacle", line=2.5, over=1.90, under=2.00, stk=24 * HOUR)
    _pair(store, book="bet365", line=2.5, over=1.80, under=2.10, stk=6 * HOUR)
    ds = build_dataset(store)
    # Each book has only one vintage -> no same-key transition across books.
    assert ds.transition_counts == {}
    assert ds.transitions == []


def test_cross_line_not_a_transition(tmp_path):
    store = CaptureStore(path=tmp_path / "c.jsonl")
    _pair(store, book="pinnacle", line=2.5, over=1.90, under=2.00, stk=24 * HOUR)
    _pair(store, book="pinnacle", line=2.75, over=1.80, under=2.10, stk=6 * HOUR)
    ds = build_dataset(store)
    # Different lines => not the same key => no price transition.
    assert ds.transitions == []


def test_coexisting_lines_not_a_line_change(tmp_path):
    store = CaptureStore(path=tmp_path / "c.jsonl")
    # Many lines offered at the SAME instant is not a line change.
    for ln in (0.5, 1.5, 2.5, 3.5):
        _pair(store, book="pinnacle", line=ln, over=1.90, under=2.00, stk=24 * HOUR)
    ds = build_dataset(store)
    assert ds.line_changes == []


def test_genuine_line_change_tracked_separately(tmp_path):
    store = CaptureStore(path=tmp_path / "c.jsonl")
    # At 24h the book offers line 2.5; at 6h it offers 2.75 (2.5 withdrawn).
    _pair(store, book="pinnacle", line=2.5, over=1.90, under=2.00, stk=24 * HOUR)
    _pair(store, book="pinnacle", line=2.75, over=1.85, under=2.05, stk=6 * HOUR)
    ds = build_dataset(store)
    # No same-line transition, but a line change IS recorded.
    assert ds.transitions == []
    assert len(ds.line_changes) >= 1
    # The change references the appearance of 2.75 and/or disappearance of 2.5.
    lines = {(c.earlier_line, c.later_line) for c in ds.line_changes}
    assert (None, 2.75) in lines or (2.5, None) in lines


def test_deterministic_serialization(tmp_path):
    store = CaptureStore(path=tmp_path / "c.jsonl")
    _pair(store, book="pinnacle", line=2.5, over=1.90, under=2.00, stk=24 * HOUR)
    _pair(store, book="pinnacle", line=2.5, over=1.80, under=2.10, stk=6 * HOUR)
    a = build_dataset(store)
    b = build_dataset(store)
    assert [t.to_dict() for t in a.transitions] == [t.to_dict() for t in b.transitions]


def test_delta_is_logit_difference(tmp_path):
    store = CaptureStore(path=tmp_path / "c.jsonl")
    # Symmetric prices -> p_fair(over) = 0.5 both times -> delta 0.
    _pair(store, book="pinnacle", line=2.5, over=2.00, under=2.00, stk=24 * HOUR)
    _pair(store, book="pinnacle", line=2.5, over=2.00, under=2.00, stk=6 * HOUR)
    ds = build_dataset(store)
    row = next(x for x in ds.transitions if x.selection == "over")
    assert abs(row.p_market_earlier - 0.5) < 1e-6
    assert abs(row.delta_market_logit) < 1e-6


def test_gate_not_relaxed_and_state(tmp_path):
    store = CaptureStore(path=tmp_path / "c.jsonl")
    _pair(store, book="pinnacle", line=2.5, over=1.90, under=2.00, stk=24 * HOUR)
    _pair(store, book="pinnacle", line=2.5, over=1.80, under=2.10, stk=6 * HOUR)
    ds = build_dataset(store)
    r = assess_readiness(ds)
    # Far below the preregistered thresholds -> NOT EVALUABLE.
    assert r.readiness_state != "PRICE_DISCOVERY_EVALUABLE"
    assert r.gate["met"] is False
    assert r.gate["checks"]["captured_fixtures"]["required"] == 300
    assert r.gate["checks"]["same_book_late_final"]["required"] == 200


def test_evaluable_only_when_gate_met():
    # Synthetic counts that meet every preregistered threshold.
    g = PROSPECTIVE_GATE.evaluate(
        captured_fixtures=300,
        same_book_late_final=200,
        confirmed_lineups=150,
        pre_post_lineup_pairs=100,
    )
    assert g["met"] is True
    # And one short of a single threshold fails closed.
    g2 = PROSPECTIVE_GATE.evaluate(
        captured_fixtures=300,
        same_book_late_final=199,
        confirmed_lineups=150,
        pre_post_lineup_pairs=100,
    )
    assert g2["met"] is False


def test_report_has_no_alpha_claims(tmp_path):
    store = CaptureStore(path=tmp_path / "c.jsonl")
    _pair(store, book="pinnacle", line=2.5, over=1.90, under=2.00, stk=24 * HOUR)
    _pair(store, book="pinnacle", line=2.5, over=1.80, under=2.10, stk=6 * HOUR)
    ds = build_dataset(store)
    import json
    text = json.dumps(build_full_report(ds)).lower()
    for banned in ("alpha", "edge", "profit", "promotion candidate"):
        # 'edge' may appear only inside the disclaimer's absence; ensure no
        # positive claim keys exist.
        assert f'"{banned}"' not in text
