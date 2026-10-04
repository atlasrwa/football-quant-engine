import pytest

from src.research.prospective.v21_calibration_shadow import (
    CalibrationShadowLedger,
    SHADOW_FREEZE_VERSION,
    build_fixture_record,
    verify_ledger_rows,
)


def _freeze():
    return {
        "version": SHADOW_FREEZE_VERSION,
        "shadow_freeze_hash": "freeze-123",
        "reference": {
            "calibrator_spec": {
                "method": "PLATT_GLOBAL",
                "intercept": 0.0,
                "slope": 1.0,
                "eps": 1e-6,
            }
        },
        "challenger": {
            "calibrator_spec": {
                "method": "PLATT_ISOTONIC_BLEND",
                "alpha": 0.25,
                "platt": {
                    "method": "PLATT_GLOBAL",
                    "intercept": 0.0,
                    "slope": 1.0,
                    "eps": 1e-6,
                },
                "isotonic": {
                    "method": "ISOTONIC_GLOBAL",
                    "x_points": [0.1, 0.5, 0.9],
                    "y_points": [0.12, 0.48, 0.88],
                },
            }
        },
    }


def _surface():
    lines = [2.5,3.5,4.5,5.5,6.5,7.5]
    home = [0.88,0.78,0.65,0.50,0.34,0.20]
    away = [0.82,0.70,0.56,0.42,0.28,0.16]
    return {
        "HOME": dict(zip(lines, home)),
        "AWAY": dict(zip(lines, away)),
    }


def test_fixture_record_requires_exact_six_hour_cutoff():
    with pytest.raises(ValueError, match="21600"):
        build_fixture_record(
            freeze=_freeze(),
            fixture_key="f1",
            kickoff_ts=100000,
            prediction_cutoff_ts=79000,
            generated_at_ts=80000,
            raw_over_by_role=_surface(),
            prev_hash="",
        )


def test_fixture_record_is_complete_coherent_and_outcome_blind():
    record = build_fixture_record(
        freeze=_freeze(),
        fixture_key="f1",
        kickoff_ts=100000,
        prediction_cutoff_ts=78400,
        generated_at_ts=79000,
        raw_over_by_role=_surface(),
        prev_hash="",
    )
    assert record["market_odds_used"] is False
    assert record["outcomes_used"] is False
    assert set(record["surfaces"]) == {"HOME", "AWAY"}
    assert all(len(record["surfaces"][r]) == 6 for r in ("HOME","AWAY"))
    assert verify_ledger_rows([record]) == record["record_hash"]


def test_fixture_record_rejects_incomplete_or_nonmonotone_surface():
    surface = _surface()
    del surface["HOME"][7.5]
    with pytest.raises(ValueError, match="complete registered"):
        build_fixture_record(
            freeze=_freeze(),
            fixture_key="f1",
            kickoff_ts=100000,
            prediction_cutoff_ts=78400,
            generated_at_ts=79000,
            raw_over_by_role=surface,
            prev_hash="",
        )

    surface = _surface()
    surface["AWAY"][5.5] = 0.75
    with pytest.raises(ValueError, match="non-monotone"):
        build_fixture_record(
            freeze=_freeze(),
            fixture_key="f1",
            kickoff_ts=100000,
            prediction_cutoff_ts=78400,
            generated_at_ts=79000,
            raw_over_by_role=surface,
            prev_hash="",
        )


def test_shadow_ledger_is_append_only_hash_chained(tmp_path):
    ledger = CalibrationShadowLedger(
        tmp_path / "shadow.jsonl",
        _freeze(),
    )
    first = ledger.append_fixture(
        fixture_key="f1",
        kickoff_ts=100000,
        prediction_cutoff_ts=78400,
        generated_at_ts=79000,
        raw_over_by_role=_surface(),
    )
    second = ledger.append_fixture(
        fixture_key="f2",
        kickoff_ts=200000,
        prediction_cutoff_ts=178400,
        generated_at_ts=180000,
        raw_over_by_role=_surface(),
    )
    assert second["prev_hash"] == first["record_hash"]
    assert ledger.n_records == 2
    assert ledger.chain_head == second["record_hash"]

    reopened = CalibrationShadowLedger(
        tmp_path / "shadow.jsonl",
        _freeze(),
    )
    assert reopened.chain_head == second["record_hash"]
    with pytest.raises(ValueError, match="already committed"):
        reopened.append_fixture(
            fixture_key="f2",
            kickoff_ts=300000,
            prediction_cutoff_ts=278400,
            generated_at_ts=280000,
            raw_over_by_role=_surface(),
        )
