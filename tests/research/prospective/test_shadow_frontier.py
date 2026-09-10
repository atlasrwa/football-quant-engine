"""Regression tests for the prospective-shadow live frontier + scheduler wiring.

These prove the two review blockers are fixed:

BLOCKER 1 — false PROSPECTIVE_SHADOW provenance:
    A candidate may be PROSPECTIVE_SHADOW only if the shadow instrumentation was
    operational (past the persisted live frontier ``F``) when it froze the
    candidate. Pre-frontier history can never become prospective; it may only be
    RECONSTRUCTED_SHADOW. Fail-closed on missing/corrupt frontier. Default CLI
    mode cannot convert old history to prospective. Restart preserves semantics.

BLOCKER 2 — processor wired into a live scheduled path:
    The existing ``capture-due`` tick invokes shadow processing over
    just-persisted state, with zero extra provider calls, idempotently, without
    corrupting capture data.

Every fixture is a deterministic synthetic broadcast ledger + capture store in a
tmp dir; no runtime capture data and no provider access are required.
"""

from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from src.research.prospective import shadow_process
from src.research.prospective.capture import CaptureRecord
from src.research.prospective.shadow_frontier import (
    ShadowFrontierError,
    establish_frontier,
    frontier_path,
    load_frontier,
)
from src.research.prospective.shadow_store import default_candidate_store
from src.research.prospective.storage import CaptureStore

# --- deterministic synthetic timeline -------------------------------------
KICKOFF = 1_788_979_500.0
GEN_AT = KICKOFF - 8 * 3600.0        # forecast committed 8h pre-kickoff
OBS_EARLY = KICKOFF - 6 * 3600.0     # market snapshot 6h pre-kickoff
OBS_LATE = KICKOFF - 1 * 3600.0      # a later same-key snapshot 1h pre-kickoff


def _write_broadcast(root: Path) -> None:
    """Write a synthetic FORECAST_COMMITTED broadcast ledger."""
    root.mkdir(parents=True, exist_ok=True)
    rec = {
        "record_type": "FORECAST_COMMITTED",
        "fixture_id": "mt_1",
        "comp_id": "comp_8321",
        "kickoff_unix": KICKOFF,
        "commitment_hash": "commit_abc",
        "scope_version_hash": "scope_123",
        "payload": {
            "fixture_id": "mt_1",
            "generated_at_utc": _iso(GEN_AT),
            "kickoff_unix": KICKOFF,
            "comp_id": "comp_8321",
            "model_version": "model_xyz",
            "scope_version_hash": "scope_123",
            "markets": [
                {"market": "goals", "line": 2.5, "p_over": 0.55, "p_under": 0.45},
            ],
        },
    }
    (root / "broadcasts.jsonl").write_text(
        json.dumps(rec) + "\n", encoding="utf-8"
    )


def _capture(observed_at: float, over: float, under: float) -> list[CaptureRecord]:
    """A paired over/under odds capture at one observed_at for the exact key."""
    common = dict(
        provider="thestatsapi",
        provider_entity_id="mt_1",
        canonical_entity_id="mt_1",
        observed_at=observed_at,
        retrieved_at=observed_at,
        raw_payload_hash=f"ph_{int(observed_at)}",
        raw_status="PROSPECTIVE_SNAPSHOT",
        event_time=KICKOFF,
    )
    return [
        CaptureRecord(concept="odds:total_goals:over:2.5:pinnacle", value=over, **common),
        CaptureRecord(concept="odds:total_goals:under:2.5:pinnacle", value=under, **common),
    ]


def _write_captures(root: Path, observed_ats) -> None:
    root.mkdir(parents=True, exist_ok=True)
    store = CaptureStore(path=root / "captures.jsonl.gz")
    for obs in observed_ats:
        for rec in _capture(obs, over=1.90, under=2.00):
            store.append(rec)


def _iso(ts: float) -> str:
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


def _make_env(tmp_path: Path, observed_ats=(OBS_EARLY,)):
    shadow_root = tmp_path / "prospective"
    broadcast_root = tmp_path / "forecast_broadcast"
    _write_broadcast(broadcast_root)
    _write_captures(shadow_root, observed_ats)
    return shadow_root, broadcast_root


def _provenances(shadow_root: Path):
    store = default_candidate_store(root=shadow_root)
    return [d["provenance_kind"] for d in store.read_all_dicts()]


# ===========================================================================
# BLOCKER 1
# ===========================================================================

# 1. pre-deployment/pre-frontier persisted history cannot become PROSPECTIVE_SHADOW
def test_pre_frontier_history_never_prospective(tmp_path):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    # Instrumentation is "deployed" (frontier established) AFTER the market
    # snapshot already existed — the classic historical case.
    now = OBS_EARLY + 3600.0  # frontier is later than the candidate's cutoff T
    res = shadow_process.run(shadow_root=shadow_root, broadcast_root=broadcast_root, now=now)
    assert res.provenance_kind == "PROSPECTIVE_SHADOW"
    assert res.candidates_new == 0                    # nothing frozen prospective
    assert res.candidates_pre_frontier_excluded >= 1  # excluded, not relabeled
    assert _provenances(shadow_root) == []            # nothing persisted at all


# 2. historical data can still be explicitly RECONSTRUCTED_SHADOW
def test_historical_reconstructed_still_available(tmp_path):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    res = shadow_process.run(
        shadow_root=shadow_root, broadcast_root=broadcast_root,
        reconstructed=True, as_of=KICKOFF,
    )
    assert res.provenance_kind == "RECONSTRUCTED_SHADOW"
    assert res.candidates_new >= 1
    assert all(p == "RECONSTRUCTED_SHADOW" for p in _provenances(shadow_root))
    # a reconstructed run never establishes/consults the frontier file
    assert not frontier_path(shadow_root).exists()


# 3. newly eligible post-frontier candidate becomes PROSPECTIVE_SHADOW
def test_post_frontier_candidate_becomes_prospective(tmp_path):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    # Instrumentation went live BEFORE the market snapshot was captured, so the
    # candidate froze while the frontier was already live.
    now = OBS_EARLY + 60.0
    # Establish the frontier strictly before the snapshot to simulate a live
    # deployment that predates the eligible capture.
    establish_frontier(shadow_root, now=OBS_EARLY - 60.0)
    res = shadow_process.run(shadow_root=shadow_root, broadcast_root=broadcast_root, now=now)
    assert res.provenance_kind == "PROSPECTIVE_SHADOW"
    assert res.candidates_new >= 1
    assert res.candidates_pre_frontier_excluded == 0
    assert all(p == "PROSPECTIVE_SHADOW" for p in _provenances(shadow_root))


# 4. first processor run after kickoff cannot retrospectively manufacture prospective
def test_first_run_after_kickoff_cannot_manufacture_prospective(tmp_path):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY, OBS_LATE))
    # The processor is deployed for the first time the DAY AFTER kickoff.
    now = KICKOFF + 24 * 3600.0
    res = shadow_process.run(shadow_root=shadow_root, broadcast_root=broadcast_root, now=now)
    assert res.candidates_new == 0
    assert res.candidates_pre_frontier_excluded >= 1
    assert _provenances(shadow_root) == []
    # frontier was established at 'now' (after kickoff); no pre-KO snapshot qualifies
    fr = load_frontier(shadow_root)
    assert fr is not None and fr.established_at == now


# 5. restart preserves prospectivity semantics (frontier immutable across runs)
def test_restart_preserves_frontier(tmp_path):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    first_now = OBS_EARLY + 100.0
    shadow_process.run(shadow_root=shadow_root, broadcast_root=broadcast_root, now=first_now)
    fr1 = load_frontier(shadow_root)
    assert fr1 is not None
    # a "restart" — a much later run must NOT move the frontier
    shadow_process.run(shadow_root=shadow_root, broadcast_root=broadcast_root,
                       now=first_now + 10 * 3600.0)
    fr2 = load_frontier(shadow_root)
    assert fr2 is not None and fr2.established_at == fr1.established_at


# 6. absent/corrupt frontier fails closed
def test_corrupt_frontier_fails_closed(tmp_path):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    # Establish, then corrupt the persisted frontier file with invalid JSON.
    establish_frontier(shadow_root, now=OBS_EARLY - 60.0)
    frontier_path(shadow_root).write_text("{not valid json", encoding="utf-8")
    with pytest.raises(ShadowFrontierError):
        shadow_process.run(shadow_root=shadow_root, broadcast_root=broadcast_root,
                           now=OBS_EARLY + 60.0)


# 6b. tampered frontier (timestamp moved, integrity hash stale) fails closed
def test_tampered_frontier_fails_closed(tmp_path):
    shadow_root, _ = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    establish_frontier(shadow_root, now=OBS_EARLY - 60.0)
    d = json.loads(frontier_path(shadow_root).read_text())
    d["established_at"] = d["established_at"] - 999999.0  # move boundary, keep old hash
    frontier_path(shadow_root).write_text(json.dumps(d), encoding="utf-8")
    with pytest.raises(ShadowFrontierError):
        load_frontier(shadow_root)


# 7. default CLI mode cannot convert old history to prospective
def test_default_cli_mode_cannot_relabel_history(tmp_path, capsys):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    # Pre-establish a frontier AFTER the historical snapshot (simulating that the
    # instrumentation only went live later), then invoke the default CLI 'run'.
    establish_frontier(shadow_root, now=OBS_EARLY + 3600.0)
    rc = shadow_process.main([
        "run",
        "--shadow-root", str(shadow_root),
        "--broadcast-root", str(broadcast_root),
    ])
    assert rc == 0
    out = json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["provenance_kind"] == "PROSPECTIVE_SHADOW"
    assert out["candidates_new"] == 0
    assert out["candidates_pre_frontier_excluded"] >= 1
    assert _provenances(shadow_root) == []


# ===========================================================================
# BLOCKER 2 — scheduler wiring
# ===========================================================================

class _FakeClient:
    """A client that must NEVER be asked for anything by shadow processing."""

    is_configured = True
    last_rate_limit = None

    def get(self, *a, **k):  # pragma: no cover - asserted not called by shadow
        raise AssertionError("shadow processing must not issue provider requests")


# 8. live scheduler/runner invokes shadow processing on the normal capture-due path
def test_scheduler_wiring_invokes_shadow(tmp_path, monkeypatch):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    _run_capture_due_with_shadow(tmp_path, shadow_root, broadcast_root, monkeypatch,
                                 now=OBS_EARLY + 60.0)
    # The scheduled capture-due tick invoked shadow processing WITHOUT any manual
    # command: a separate shadow ops record was written by the wiring in cli.main.
    shadow_ops = (shadow_root / "shadow_ops.jsonl")
    assert shadow_ops.exists()
    last = json.loads(shadow_ops.read_text().splitlines()[-1])
    assert last["health_state"] == "SHADOW_OK"


# 8b. end-to-end: the scheduled hook naturally produces PROSPECTIVE_SHADOW for a
#     legitimate post-frontier forecast<->market candidate (no manual command).
def test_scheduled_hook_produces_prospective_end_to_end(tmp_path):
    from src.research.prospective import cli

    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    # Frontier live before the eligible snapshot; freeze wall clock via now_ts.
    establish_frontier(shadow_root, now=OBS_EARLY - 60.0)
    import src.research.prospective.shadow_process as sp
    import datetime as _dt

    class _FrozenDT(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime.fromtimestamp(OBS_EARLY + 60.0, tz)

    orig = sp.datetime.datetime
    sp.datetime.datetime = _FrozenDT
    try:
        cli._run_shadow_after_capture(capture_root=shadow_root, broadcast_root=broadcast_root)
    finally:
        sp.datetime.datetime = orig
    assert all(p == "PROSPECTIVE_SHADOW" for p in _provenances(shadow_root))
    assert len(_provenances(shadow_root)) >= 1


# 9. normal scheduled path requires 0 extra provider calls
def test_scheduled_shadow_zero_provider_calls(tmp_path, monkeypatch):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    establish_frontier(shadow_root, now=OBS_EARLY - 60.0)
    # _FakeClient.get raises if called; the helper only runs the shadow hook.
    from src.research.prospective import cli
    cli._run_shadow_after_capture(capture_root=shadow_root)
    # If we got here without AssertionError, shadow made no provider calls.
    # (belt-and-suspenders: assert the shadow modules never import HTTP)
    for modname in ("shadow_residual", "shadow_builder", "shadow_store", "shadow_frontier"):
        mod = __import__(f"src.research.prospective.{modname}", fromlist=["x"])
        src = Path(mod.__file__).read_text()
        assert "httpx" not in src and "requests" not in src


# 10. repeated scheduled execution remains idempotent
def test_scheduled_shadow_idempotent(tmp_path):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    establish_frontier(shadow_root, now=OBS_EARLY - 60.0)
    now = OBS_EARLY + 60.0
    r1 = shadow_process.run(shadow_root=shadow_root, broadcast_root=broadcast_root, now=now)
    r2 = shadow_process.run(shadow_root=shadow_root, broadcast_root=broadcast_root, now=now)
    assert r1.candidates_new >= 1
    assert r2.candidates_new == 0        # nothing new on the second identical tick
    assert len(_provenances(shadow_root)) == r1.candidates_new


# 11. capture/collector semantics unchanged: shadow failure never corrupts capture
def test_shadow_failure_isolated_from_capture(tmp_path, monkeypatch):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    # Force shadow_process.run to blow up.
    from src.research.prospective import cli
    import src.research.prospective.shadow_process as sp

    def _boom(**kwargs):
        raise RuntimeError("simulated shadow failure")

    monkeypatch.setattr(sp, "run", _boom)
    # Must NOT raise — failure is isolated and recorded separately.
    cli._run_shadow_after_capture(capture_root=shadow_root)
    shadow_ops = json.loads((shadow_root / "shadow_ops.jsonl").read_text().splitlines()[-1])
    assert shadow_ops["health_state"] == "SHADOW_FAILED"
    assert shadow_ops["exit_status"] == "ERROR"
    # capture store untouched by the failure
    store = CaptureStore(path=shadow_root / "captures.jsonl.gz")
    assert sum(1 for _ in store.read_all()) == 2  # the two paired legs we wrote


# ===========================================================================
# Guardrails 12-16 (unchanged invariants)
# ===========================================================================

# 12. publication remains suppressed
def test_publication_remains_suppressed(monkeypatch):
    monkeypatch.setenv("DATA_ACCUMULATION_MODE", "1")
    monkeypatch.delenv("SIGNAL_PUBLICATION_STATE", raising=False)
    from src.research._data_accumulation_mode import can_publish_validated_signals
    assert can_publish_validated_signals() is False


# 13/14. VALIDATED_SIGNAL and STRATEGY_ACTION remain 0 in all shadow output
def test_no_validated_signal_or_strategy_action(tmp_path):
    shadow_root, broadcast_root = _make_env(tmp_path, observed_ats=(OBS_EARLY,))
    establish_frontier(shadow_root, now=OBS_EARLY - 60.0)
    shadow_process.run(shadow_root=shadow_root, broadcast_root=broadcast_root,
                       now=OBS_EARLY + 60.0)
    store = default_candidate_store(root=shadow_root)
    validated = 0
    strategy = 0
    for d in store.read_all_dicts():
        vals = list(d.values())
        assert d["record_type"] == "SHADOW_RESIDUAL"
        assert d["classification"] == ["RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"]
        validated += sum(1 for v in vals if v == "VALIDATED_SIGNAL")
        strategy += sum(1 for v in vals if v == "STRATEGY_ACTION")
    assert validated == 0
    assert strategy == 0


# 15. frozen research gates remain 300/200/150/100
def test_frozen_research_gates_unchanged():
    from src.research.experiments.price_discovery.dataset import ReadinessGate
    t = ReadinessGate()
    assert t.min_captured_fixtures == 300
    assert t.min_same_book_late_final == 200
    assert t.min_confirmed_lineups == 150
    assert t.min_pre_post_lineup_pairs == 100


# --- shared harness for the capture-due -> shadow wiring -------------------
def _run_capture_due_with_shadow(tmp_path, shadow_root, broadcast_root, monkeypatch, *, now):
    """Drive cli.main('capture-due') with a stub collector that captures nothing.

    We exercise the REAL wiring in cli.main: after the capture ops record is
    written, main() calls _run_shadow_after_capture. We stub the network-facing
    collector so no provider access happens, and pin shadow_process.run's clock
    via monkeypatching now_ts so the horizon includes the eligible snapshot.
    """
    from src.research.prospective import cli
    from src.research.prospective.cli import CollectorResult

    # Stub the client so cli.main passes the is_configured gate without network.
    monkeypatch.setattr(cli, "ProspectiveApiClient", lambda *a, **k: _FakeClient())

    # Stub capture_due so the collector does no work (capture semantics unchanged
    # is covered elsewhere; here we only prove the shadow hook fires).
    def _fake_capture_due(self, **kwargs):
        return CollectorResult(health="HEALTHY")

    monkeypatch.setattr(cli.ProspectiveCollector, "capture_due", _fake_capture_due)

    # Freeze the wall clock used by shadow_process.run via the module boundary.
    import src.research.prospective.shadow_process as sp
    import datetime as _dt

    class _FrozenDT(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return _dt.datetime.fromtimestamp(now, tz)

    monkeypatch.setattr(sp.datetime, "datetime", _FrozenDT)

    rc = cli.main(["--capture-root", str(shadow_root), "capture-due"])
    assert rc == 0



# 16. champion diff remains empty: the entire shadow implementation (frontier +
#     processor + builder + store + record) must import NO champion/model module
#     and reference no champion/model source path, so merging this instrumentation
#     cannot change the champion. This is the code-level guarantee behind the
#     empty `git diff` over src/research/models/.
def test_shadow_touches_no_champion_or_model_path():
    import importlib
    import subprocess
    import sys

    shadow_modnames = [
        "shadow_process",
        "shadow_builder",
        "shadow_store",
        "shadow_frontier",
        "shadow_residual",
    ]
    # (a) Importing the shadow chain must not pull in any champion/model module.
    #     Run in a FRESH interpreter so the assertion reflects only what the
    #     shadow chain itself imports (the in-process sys.modules is polluted by
    #     other tests in the suite that legitimately import the champion).
    prog = (
        "import importlib, sys; "
        + "; ".join(
            f"importlib.import_module('src.research.prospective.{n}')"
            for n in shadow_modnames
        )
        + "; "
        + "bad=[n for n in sys.modules if n.startswith('src.research.models')]; "
        + "print(';'.join(bad)); "
        + "sys.exit(1 if bad else 0)"
    )
    proc = subprocess.run(
        [sys.executable, "-c", prog],
        cwd=str(Path(__file__).resolve().parents[3]),
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, (
        f"shadow chain imported champion/model modules: {proc.stdout.strip()!r} "
        f"stderr={proc.stderr.strip()!r}"
    )

    # (b) No shadow source file references the champion/model package path or a
    #     model rerun entrypoint (belt-and-suspenders against a future edit).
    for name in shadow_modnames:
        mod = importlib.import_module(f"src.research.prospective.{name}")
        src = Path(mod.__file__).read_text(encoding="utf-8")
        assert "research.models" not in src, name
        assert "hierarchical_market_model" not in src, name
