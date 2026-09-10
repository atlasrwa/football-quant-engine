"""Focused tests for the prospective SHADOW_RESIDUAL instrumentation.

Covers the 22 required properties. Property tests use synthetic legs so they
are deterministic and independent of runtime capture data. Two integration
tests exercise the real persisted state read-only (skipped if absent).
"""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from src.research.prospective.shadow_residual import (
    CLASSIFICATION,
    ForecastLeg,
    MarketLeg,
    MovementDirection,
    ShadowJoinError,
    ShadowProvenanceKind,
    build_movement_evaluation,
    build_shadow_residual,
    classify_movement,
    logit,
)
from src.research.prospective.odds_capture import market_over_probability
from src.research.reconciliation.devig import devig

KICKOFF = 1_788_979_500.0
GEN_AT = KICKOFF - 8 * 3600.0          # model generated 8h pre-KO
T = KICKOFF - 6 * 3600.0                # information cutoff 6h pre-KO
OBS = KICKOFF - 6 * 3600.0 - 60.0       # market observed just before T


def _forecast(**kw) -> ForecastLeg:
    base = dict(
        fixture_id="mt_1",
        competition="comp_8321",
        kickoff_ts=KICKOFF,
        market="total_goals",
        selection="over",
        line=2.5,
        p_model=0.55,
        generated_at=GEN_AT,
        forecast_commitment_hash="commit_abc",
        model_version="model_xyz",
        scope_version_hash="scope_123",
    )
    base.update(kw)
    return ForecastLeg(**base)


def _market(**kw) -> MarketLeg:
    base = dict(
        fixture_id="mt_1",
        provider="thestatsapi",
        bookmaker="pinnacle",
        market="total_goals",
        selection="over",
        line=2.5,
        over_odds=1.90,
        under_odds=2.00,
        observed_at=OBS,
        retrieved_at=OBS,
        raw_payload_hash="ph_1",
    )
    base.update(kw)
    return MarketLeg(**base)


def _shadow(**kw):
    return build_shadow_residual(
        forecast=_forecast(**kw.pop("forecast_kw", {})),
        market=_market(**kw.pop("market_kw", {})),
        information_cutoff=kw.pop("cutoff", T),
        provenance_kind=kw.pop("provenance", ShadowProvenanceKind.PROSPECTIVE_SHADOW),
        **kw,
    )


# 1. exact fixture identity required
def test_fixture_identity_required():
    with pytest.raises(ShadowJoinError):
        build_shadow_residual(
            forecast=_forecast(fixture_id="mt_1"),
            market=_market(fixture_id="mt_2"),
            information_cutoff=T,
            provenance_kind=ShadowProvenanceKind.PROSPECTIVE_SHADOW,
        )


# 2. market observation must be at/before cutoff  (and 3. future rejected)
def test_future_market_snapshot_rejected():
    with pytest.raises(ShadowJoinError):
        _shadow(market_kw={"observed_at": T + 1.0, "retrieved_at": T + 1.0})


def test_market_at_cutoff_allowed():
    rec = _shadow(market_kw={"observed_at": T, "retrieved_at": T}, cutoff=T)
    assert rec.market_observed_at == T


# 4. post-kickoff snapshots rejected
def test_post_kickoff_snapshot_rejected():
    with pytest.raises(ShadowJoinError):
        # observed at/after kickoff, cutoff also after kickoff so the KO gate fires
        _shadow(market_kw={"observed_at": KICKOFF, "retrieved_at": KICKOFF},
                cutoff=KICKOFF + 10)


# 5-8. same bookmaker/market/selection/line preserved (mismatches refused)
@pytest.mark.parametrize("field,value", [
    ("bookmaker", "bet365"),  # bookmaker is not part of forecast leg; see note below
    ("market", "match_corners"),
    ("selection", "under"),
    ("line", 3.5),
])
def test_key_mismatch_refused(field, value):
    # market/selection/line mismatch between forecast and market legs is refused.
    if field == "bookmaker":
        # bookmaker lives only on the market leg, so key identity is enforced at
        # evaluation time; here we assert the shadow simply carries it verbatim.
        rec = _shadow(market_kw={"bookmaker": value})
        assert rec.bookmaker == value
        return
    with pytest.raises(ShadowJoinError):
        build_shadow_residual(
            forecast=_forecast(),
            market=_market(**{field: value}),
            information_cutoff=T,
            provenance_kind=ShadowProvenanceKind.PROSPECTIVE_SHADOW,
        )


# 9. de-vigged probability used (not raw implied)
def test_devig_probability_used():
    rec = _shadow()
    expected = market_over_probability(1.90, 2.00, method="multiplicative")
    assert rec.p_market_devig == pytest.approx(expected)
    # raw implied differs from de-vigged (overround removed)
    assert rec.raw_implied_probability == pytest.approx(1.0 / 1.90)
    assert rec.p_market_devig != pytest.approx(rec.raw_implied_probability)


# 10. raw residual computed correctly
def test_raw_residual():
    rec = _shadow()
    assert rec.raw_probability_residual == pytest.approx(rec.p_model - rec.p_market_devig)


# 11. logit residual computed correctly
def test_logit_residual():
    rec = _shadow()
    assert rec.logit_residual == pytest.approx(logit(rec.p_model) - logit(rec.p_market_devig))


# 12. forecast commitment referenced
def test_forecast_commitment_referenced():
    rec = _shadow()
    assert rec.forecast_commitment_hash == "commit_abc"
    assert rec.model_version == "model_xyz"
    assert rec.scope_version_hash == "scope_123"


# 13. market snapshot provenance referenced
def test_market_snapshot_provenance_referenced():
    rec = _shadow()
    assert rec.provider == "thestatsapi"
    assert rec.raw_over_odds == 1.90 and rec.raw_under_odds == 2.00
    assert rec.market_snapshot_hash  # non-empty deterministic hash


# 14. deterministic shadow ID/hash
def test_deterministic_id_and_hash():
    a = _shadow(created_at=111.0)
    b = _shadow(created_at=999.0)  # different wall-clock
    assert a.shadow_id == b.shadow_id                      # id ignores created_at
    assert a.shadow_payload_hash == b.shadow_payload_hash  # payload hash too
    # changing a scientific field changes the hash
    c = _shadow(market_kw={"over_odds": 1.50})
    assert c.shadow_payload_hash != a.shadow_payload_hash


# 15. repeat execution is idempotent (store)
def test_store_idempotent(tmp_path):
    from src.research.prospective.shadow_store import ShadowResidualStore

    store = ShadowResidualStore(path=tmp_path / "shadow_residuals.jsonl")
    rec = _shadow()
    assert store.append(rec) is True
    assert store.append(rec) is False        # same id -> not duplicated
    # a fresh store over the same file re-primes seen ids
    store2 = ShadowResidualStore(path=tmp_path / "shadow_residuals.jsonl")
    assert store2.append(rec) is False
    assert store2.count() == 1


# 16. later evaluation references rather than mutates shadow
def test_evaluation_references_not_mutates(tmp_path):
    shadow = _shadow()
    later = _market(observed_at=KICKOFF - 600.0, retrieved_at=KICKOFF - 600.0,
                    over_odds=1.80, under_odds=2.10)
    ev = build_movement_evaluation(shadow=shadow, later_market=later)
    assert ev.shadow_id == shadow.shadow_id
    assert ev.shadow_payload_hash == shadow.shadow_payload_hash
    # shadow is a frozen dataclass; its fields are unchanged by evaluation
    assert shadow.p_market_devig == pytest.approx(
        market_over_probability(1.90, 2.00, method="multiplicative")
    )
    assert ev.p_market_earlier == pytest.approx(shadow.p_market_devig)


# 17. movement direction TOWARD/AWAY/FLAT correct
def test_movement_direction_semantics():
    # model higher than market (positive residual)
    assert classify_movement(raw_probability_residual=0.05,
                             p_market_earlier=0.50, p_market_later=0.55) is MovementDirection.TOWARD_MODEL
    assert classify_movement(raw_probability_residual=0.05,
                             p_market_earlier=0.50, p_market_later=0.45) is MovementDirection.AWAY_FROM_MODEL
    assert classify_movement(raw_probability_residual=0.05,
                             p_market_earlier=0.50, p_market_later=0.50) is MovementDirection.FLAT
    # model lower than market (negative residual): market falling is TOWARD
    assert classify_movement(raw_probability_residual=-0.05,
                             p_market_earlier=0.50, p_market_later=0.45) is MovementDirection.TOWARD_MODEL


def test_movement_evaluation_same_key_required():
    shadow = _shadow()
    with pytest.raises(ShadowJoinError):
        build_movement_evaluation(
            shadow=shadow,
            later_market=_market(bookmaker="bet365",
                                 observed_at=KICKOFF - 600.0, retrieved_at=KICKOFF - 600.0),
        )


def test_movement_requires_strictly_later():
    shadow = _shadow()
    with pytest.raises(ShadowJoinError):
        build_movement_evaluation(
            shadow=shadow,
            later_market=_market(observed_at=shadow.market_observed_at,
                                 retrieved_at=shadow.market_observed_at),
        )


# 18. no provider API call required (builder consumes persisted state; the
#     capture client is never imported by the shadow modules).
def test_no_provider_client_imported():
    import src.research.prospective.shadow_residual as sr
    import src.research.prospective.shadow_builder as sb
    import src.research.prospective.shadow_store as ss
    for mod in (sr, sb, ss):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "ProspectiveApiClient" not in src   # no live capture client
        assert "httpx" not in src                  # no HTTP transport
        assert "requests" not in src               # no HTTP transport


# 19. no signal-publication bypass: records carry the research classification
#     and never a VALIDATED_SIGNAL / STRATEGY_ACTION type.
def test_no_signal_publication_bypass():
    rec = _shadow()
    assert rec.record_type == "SHADOW_RESIDUAL"
    assert tuple(rec.classification) == CLASSIFICATION
    assert "VALIDATED_SIGNAL" not in rec.to_dict().values()
    assert "STRATEGY_ACTION" not in rec.to_dict().values()
    d = rec.to_dict()
    assert d["classification"] == ["RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"]


# 20. DATA_ACCUMULATION_MODE respected: shadow generation does not consult or
#     flip the publication gate; the gate remains closed regardless.
def test_data_accumulation_mode_respected(monkeypatch):
    monkeypatch.setenv("DATA_ACCUMULATION_MODE", "1")
    monkeypatch.delenv("SIGNAL_PUBLICATION_STATE", raising=False)
    from src.research._data_accumulation_mode import can_publish_validated_signals

    _shadow()  # building a shadow must not change the gate
    assert can_publish_validated_signals() is False


# 21/22 covered by the integration + git checks in the harness; here we assert
# the modules do not import or reference champion/gate mutation entry points.
def test_no_champion_or_gate_mutation_symbols():
    import src.research.prospective.shadow_residual as sr
    import src.research.prospective.shadow_builder as sb
    for mod in (sr, sb):
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "ReadinessGate(" not in src           # never constructs/alters the gate
        assert "hierarchical_market_model" not in src  # never touches the champion


# --- provenance-kind discipline (mission section 18) ---
def test_provenance_kinds_distinct():
    live = _shadow(provenance=ShadowProvenanceKind.PROSPECTIVE_SHADOW)
    recon = _shadow(provenance=ShadowProvenanceKind.RECONSTRUCTED_SHADOW)
    assert live.provenance_kind == "PROSPECTIVE_SHADOW"
    assert recon.provenance_kind == "RECONSTRUCTED_SHADOW"
    # differ only by provenance -> different payload hash (never conflated)
    assert live.shadow_payload_hash != recon.shadow_payload_hash


# --- integration: real persisted state, read-only, reconstructed only ---
_STORE = Path("data/prospective/captures.jsonl.gz")
_LEDGER = Path("data/forecast_broadcast/broadcasts.jsonl")


@pytest.mark.skipif(not (_STORE.exists() and _LEDGER.exists()),
                    reason="runtime persisted state not present")
def test_integration_reconstructed_candidates_and_evaluations():
    from src.research.prediction_engine.broadcast.record import BroadcastLedger
    from src.research.prospective.shadow_builder import (
        build_candidates,
        build_evaluations,
        default_capture_store,
    )

    recs = BroadcastLedger().records()
    store = default_capture_store()
    cands = build_candidates(
        broadcast_records=recs,
        capture_store=store,
        provenance_kind=ShadowProvenanceKind.RECONSTRUCTED_SHADOW,
    )
    assert cands, "expected at least one reconstructed candidate from persisted state"
    assert all(c.provenance_kind == "RECONSTRUCTED_SHADOW" for c in cands)
    # deterministic: rebuild yields identical ids/hashes
    cands2 = build_candidates(
        broadcast_records=recs,
        capture_store=store,
        provenance_kind=ShadowProvenanceKind.RECONSTRUCTED_SHADOW,
    )
    assert [c.shadow_id for c in cands] == [c.shadow_id for c in cands2]
    assert [c.shadow_payload_hash for c in cands] == [c.shadow_payload_hash for c in cands2]

    # freeze at an early cutoff then evaluate movement to the near-close
    early = min(c.generated_at for c in cands) + 3 * 3600.0
    early_cands = build_candidates(
        broadcast_records=recs, capture_store=store,
        provenance_kind=ShadowProvenanceKind.RECONSTRUCTED_SHADOW, as_of=early,
    )
    evals = build_evaluations(candidates=early_cands, capture_store=store)
    # every evaluation references a real candidate and never mutates it
    ids = {c.shadow_id for c in early_cands}
    assert all(e.shadow_id in ids for e in evals)
    assert all(e.movement_direction in {"TOWARD_MODEL", "AWAY_FROM_MODEL", "FLAT"} for e in evals)



# --- processor: idempotency + provenance discipline over real state ---
@pytest.mark.skipif(not (_STORE.exists() and _LEDGER.exists()),
                    reason="runtime persisted state not present")
def test_processor_reconstructed_idempotent(tmp_path):
    import gzip
    import shutil
    from src.research.prospective import shadow_process

    # copy the capture store into an isolated shadow root; never touch real data
    shutil.copy(_STORE, tmp_path / "captures.jsonl.gz")

    r1 = shadow_process.run(
        shadow_root=tmp_path, reconstructed=True,
        as_of=_parse_iso_z("2026-09-09T13:00:00Z"),
    )
    assert r1.provenance_kind == "RECONSTRUCTED_SHADOW"
    assert r1.candidates_new == r1.candidates_considered > 0
    assert r1.evaluations_new == r1.evaluations_considered

    r2 = shadow_process.run(
        shadow_root=tmp_path, reconstructed=True,
        as_of=_parse_iso_z("2026-09-09T13:00:00Z"),
    )
    assert r2.candidates_new == 0          # idempotent
    assert r2.evaluations_new == 0

    # every persisted record is research-classified and reconstructed-tagged
    import json
    for line in (tmp_path / "shadow_residuals.jsonl").read_text().splitlines():
        d = json.loads(line)
        assert d["record_type"] == "SHADOW_RESIDUAL"
        assert d["provenance_kind"] == "RECONSTRUCTED_SHADOW"
        assert d["classification"] == ["RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"]


def _parse_iso_z(v: str) -> float:
    import datetime
    return datetime.datetime.fromisoformat(v.replace("Z", "+00:00")).timestamp()
