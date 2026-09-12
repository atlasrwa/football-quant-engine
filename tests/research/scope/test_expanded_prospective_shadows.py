"""Prospective shadows across the expanded universe, with integrity preserved.

Proves boundary claims E and F:

E. Historical / reconstructed evidence cannot become prospective evidence.
F. A valid post-frontier forecast from a NEWLY covered (non-Pilot-C) league can
   become a genuine ``PROSPECTIVE_SHADOW``.

Also proves the research commitment ledger is actually read (the mechanism that
makes non-Pilot-C shadows possible at all), and that every pre-existing integrity
control still holds when the input league set is widened.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import pytest

from src.research.prospective import shadow_process
from src.research.prospective.capture import CaptureRecord
from src.research.prospective.shadow_residual import ShadowProvenanceKind
from src.research.prospective.shadow_store import (
    default_candidate_store,
    default_evaluation_store,
)
from src.research.prospective.storage import CaptureStore

# A deterministic synthetic timeline, all safely in the past so nothing depends
# on the wall clock except the frontier, which each test sets explicitly.
KICKOFF = 1_789_500_000.0
GEN_AT = KICKOFF - 30 * 3600.0     # research horizon: T-30h
OBS_EARLY = KICKOFF - 24 * 3600.0  # EARLY vintage snapshot
OBS_LATE = KICKOFF - 1 * 3600.0    # a later same-key snapshot

#: Deliberately NOT one of the Pilot-C four.
NON_PILOT_C_COMP = "comp_5840"  # Germany Bundesliga
PILOT_C_COMP = "comp_8321"      # England Championship


def _iso(ts: float) -> str:
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


def _commitment(
    *,
    fixture_id: str,
    comp_id: str,
    commitment_hash: str,
    kickoff: float = KICKOFF,
    generated_at: float = GEN_AT,
    market: str = "goals",
    line: float = 2.5,
    p_over: float = 0.58,
) -> dict:
    """One FORECAST_COMMITTED row in the shape the real ledger writes."""
    return {
        "record_contract": "forecast-broadcast-record/v1",
        "record_type": "FORECAST_COMMITTED",
        "fixture_id": fixture_id,
        "comp_id": comp_id,
        "league_label": comp_id,
        "kickoff_unix": kickoff,
        "commitment_hash": commitment_hash,
        "scope_version_hash": "research_scope_v1",
        "payload": {
            "fixture_id": fixture_id,
            "comp_id": comp_id,
            "kickoff_unix": kickoff,
            "generated_at_utc": _iso(generated_at),
            "model_version": "model_champion_v2",
            "scope_version_hash": "research_scope_v1",
            "markets": [
                {
                    "market": market,
                    "line": line,
                    "p_over": p_over,
                    "p_under": round(1.0 - p_over, 4),
                }
            ],
        },
    }


def _write_ledger(root: Path, records: list[dict]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "broadcasts.jsonl", "w", encoding="utf-8") as handle:
        for rec in records:
            handle.write(json.dumps(rec) + "\n")


def _captures(fixture_id: str, observed_at: float, *, over=1.85, under=2.05):
    common = dict(
        provider="thestatsapi",
        provider_entity_id=fixture_id,
        canonical_entity_id=fixture_id,
        observed_at=observed_at,
        retrieved_at=observed_at,
        raw_payload_hash=f"ph_{fixture_id}_{int(observed_at)}",
        raw_status="PROSPECTIVE_SNAPSHOT",
        event_time=KICKOFF,
    )
    return [
        CaptureRecord(concept="odds:total_goals:over:2.5:pinnacle", value=over, **common),
        CaptureRecord(concept="odds:total_goals:under:2.5:pinnacle", value=under, **common),
    ]


def _write_captures(root: Path, pairs: list[tuple[str, float]]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    store = CaptureStore(path=root / "captures.jsonl.gz")
    for fixture_id, observed_at in pairs:
        for rec in _captures(fixture_id, observed_at):
            store.append(rec)


def _frontier(root: Path, established_at: float) -> None:
    """Write a valid frontier artifact at a chosen timestamp."""
    root.mkdir(parents=True, exist_ok=True)
    from src.research.prospective.shadow_frontier import establish_frontier

    establish_frontier(root, now=established_at)


@pytest.fixture
def env(tmp_path):
    """A tmp environment with separate consumer and research ledgers."""
    return {
        "shadow_root": tmp_path / "prospective",
        "consumer_root": tmp_path / "forecast_broadcast",
        "research_root": tmp_path / "research_forecast",
    }


# ── F. non-Pilot-C league produces a genuine PROSPECTIVE_SHADOW ──────────────
def test_non_pilot_c_league_produces_a_genuine_prospective_shadow(env):
    """The headline claim: a newly covered league reaches PROSPECTIVE_SHADOW."""
    _write_ledger(env["consumer_root"], [])
    _write_ledger(
        env["research_root"],
        [_commitment(fixture_id="mt_bundes_1", comp_id=NON_PILOT_C_COMP,
                     commitment_hash="commit_bundes_1")],
    )
    _write_captures(env["shadow_root"], [("mt_bundes_1", OBS_EARLY)])
    # Frontier BEFORE the snapshot -> the candidate is legitimately prospective.
    _frontier(env["shadow_root"], GEN_AT - 3600.0)

    result = shadow_process.run(
        shadow_root=env["shadow_root"],
        broadcast_root=env["consumer_root"],
        research_broadcast_root=env["research_root"],
        now=KICKOFF - 60.0,
    )

    assert result.provenance_kind == ShadowProvenanceKind.PROSPECTIVE_SHADOW.value
    assert result.candidates_new >= 1
    assert result.candidates_pre_frontier_excluded == 0
    assert NON_PILOT_C_COMP in result.candidate_competitions

    stored = list(default_candidate_store(root=env["shadow_root"]).read_all_dicts())
    assert stored, "a shadow must have been persisted"
    rec = stored[0]
    assert rec["provenance_kind"] == "PROSPECTIVE_SHADOW"
    assert rec["competition"] == NON_PILOT_C_COMP
    assert rec["record_type"] == "SHADOW_RESIDUAL"
    assert set(rec["classification"]) >= {
        "RESEARCH_ONLY", "NOT_VALIDATED", "NOT_ACTIONABLE"
    }
    # Provenance is carried, not invented.
    assert rec["forecast_commitment_hash"] == "commit_bundes_1"
    assert rec["model_version"] == "model_champion_v2"
    # Prospective integrity: cutoff strictly before kickoff.
    assert rec["information_cutoff"] < rec["kickoff_ts"]


def test_research_ledger_is_read_alongside_the_consumer_ledger(env):
    """Both roots contribute; the counts prove the research root was read."""
    _write_ledger(
        env["consumer_root"],
        [_commitment(fixture_id="mt_champ_1", comp_id=PILOT_C_COMP,
                     commitment_hash="commit_champ_1")],
    )
    _write_ledger(
        env["research_root"],
        [_commitment(fixture_id="mt_bundes_1", comp_id=NON_PILOT_C_COMP,
                     commitment_hash="commit_bundes_1")],
    )
    _write_captures(
        env["shadow_root"], [("mt_champ_1", OBS_EARLY), ("mt_bundes_1", OBS_EARLY)]
    )
    _frontier(env["shadow_root"], GEN_AT - 3600.0)

    result = shadow_process.run(
        shadow_root=env["shadow_root"],
        broadcast_root=env["consumer_root"],
        research_broadcast_root=env["research_root"],
        now=KICKOFF - 60.0,
    )

    assert result.forecast_records_by_root == {
        str(env["consumer_root"]): 1,
        str(env["research_root"]): 1,
    }
    assert set(result.candidate_competitions) == {PILOT_C_COMP, NON_PILOT_C_COMP}


def test_empty_research_ledger_reports_zero_not_absent(env):
    """"Research ledger empty" must be distinguishable from "not read"."""
    _write_ledger(env["consumer_root"], [])
    _write_captures(env["shadow_root"], [])
    _frontier(env["shadow_root"], GEN_AT)

    result = shadow_process.run(
        shadow_root=env["shadow_root"],
        broadcast_root=env["consumer_root"],
        research_broadcast_root=env["research_root"],  # never created
        now=KICKOFF,
    )
    assert str(env["research_root"]) in result.forecast_records_by_root
    assert result.forecast_records_by_root[str(env["research_root"])] == 0
    assert str(env["research_root"]) in result.broadcast_roots_read


def test_duplicate_commitment_in_both_ledgers_yields_one_shadow(env):
    """A fixture in both scopes must not double-count as research evidence."""
    duplicate = _commitment(
        fixture_id="mt_dup", comp_id=PILOT_C_COMP, commitment_hash="commit_dup"
    )
    _write_ledger(env["consumer_root"], [duplicate])
    _write_ledger(env["research_root"], [json.loads(json.dumps(duplicate))])
    _write_captures(env["shadow_root"], [("mt_dup", OBS_EARLY)])
    _frontier(env["shadow_root"], GEN_AT - 3600.0)

    result = shadow_process.run(
        shadow_root=env["shadow_root"],
        broadcast_root=env["consumer_root"],
        research_broadcast_root=env["research_root"],
        now=KICKOFF - 60.0,
    )
    stored = list(default_candidate_store(root=env["shadow_root"]).read_all_dicts())
    # One (market, selection, bookmaker) pair per side -> over + under, once each.
    assert len({r["shadow_id"] for r in stored}) == len(stored)
    assert result.candidates_new == len(stored)
    assert len(stored) == 2, "exactly over+under for the single deduplicated forecast"


# ── E. reconstructed / pre-frontier evidence cannot become prospective ───────
def test_pre_frontier_candidate_from_new_league_cannot_become_prospective(env):
    """Widening coverage must not weaken the frontier."""
    _write_ledger(env["consumer_root"], [])
    _write_ledger(
        env["research_root"],
        [_commitment(fixture_id="mt_bundes_2", comp_id=NON_PILOT_C_COMP,
                     commitment_hash="commit_bundes_2")],
    )
    _write_captures(env["shadow_root"], [("mt_bundes_2", OBS_EARLY)])
    # Frontier AFTER the snapshot -> pre-frontier history.
    _frontier(env["shadow_root"], OBS_EARLY + 3600.0)

    result = shadow_process.run(
        shadow_root=env["shadow_root"],
        broadcast_root=env["consumer_root"],
        research_broadcast_root=env["research_root"],
        now=KICKOFF - 60.0,
    )

    assert result.candidates_new == 0
    assert result.candidates_pre_frontier_excluded >= 1
    assert list(default_candidate_store(root=env["shadow_root"]).read_all_dicts()) == []


def test_reconstructed_run_never_writes_prospective_provenance(env):
    """Reconstructed shadows from a new league stay reconstructed."""
    _write_ledger(env["consumer_root"], [])
    _write_ledger(
        env["research_root"],
        [_commitment(fixture_id="mt_bundes_3", comp_id=NON_PILOT_C_COMP,
                     commitment_hash="commit_bundes_3")],
    )
    _write_captures(env["shadow_root"], [("mt_bundes_3", OBS_EARLY)])

    result = shadow_process.run(
        shadow_root=env["shadow_root"],
        broadcast_root=env["consumer_root"],
        research_broadcast_root=env["research_root"],
        reconstructed=True,
    )

    assert result.provenance_kind == ShadowProvenanceKind.RECONSTRUCTED_SHADOW.value
    stored = list(default_candidate_store(root=env["shadow_root"]).read_all_dicts())
    assert stored
    assert all(r["provenance_kind"] == "RECONSTRUCTED_SHADOW" for r in stored)
    assert all(r["provenance_kind"] != "PROSPECTIVE_SHADOW" for r in stored)
    # A reconstructed run must not create or consult a frontier.
    assert result.frontier_established_at is None
    assert not (env["shadow_root"] / "shadow_frontier.json").exists()


def test_post_kickoff_snapshot_is_never_joined_for_a_new_league(env):
    """information_cutoff < kickoff_ts still holds in the expanded universe."""
    _write_ledger(env["consumer_root"], [])
    _write_ledger(
        env["research_root"],
        [_commitment(fixture_id="mt_bundes_4", comp_id=NON_PILOT_C_COMP,
                     commitment_hash="commit_bundes_4")],
    )
    # Only a POST-kickoff snapshot exists.
    _write_captures(env["shadow_root"], [("mt_bundes_4", KICKOFF + 600.0)])
    _frontier(env["shadow_root"], GEN_AT - 3600.0)

    result = shadow_process.run(
        shadow_root=env["shadow_root"],
        broadcast_root=env["consumer_root"],
        research_broadcast_root=env["research_root"],
        now=KICKOFF + 7200.0,
    )
    assert result.candidates_new == 0
    assert list(default_candidate_store(root=env["shadow_root"]).read_all_dicts()) == []


def test_snapshot_before_forecast_generation_is_not_joined(env):
    """A snapshot older than the forecast cannot be its market comparison."""
    _write_ledger(env["consumer_root"], [])
    _write_ledger(
        env["research_root"],
        [_commitment(fixture_id="mt_bundes_5", comp_id=NON_PILOT_C_COMP,
                     commitment_hash="commit_bundes_5")],
    )
    _write_captures(env["shadow_root"], [("mt_bundes_5", GEN_AT - 7200.0)])
    _frontier(env["shadow_root"], GEN_AT - 10_000.0)

    result = shadow_process.run(
        shadow_root=env["shadow_root"],
        broadcast_root=env["consumer_root"],
        research_broadcast_root=env["research_root"],
        now=KICKOFF - 60.0,
    )
    assert result.candidates_new == 0


# ── evaluations accrue for the new universe ──────────────────────────────────
def test_evaluation_is_produced_for_a_new_league_shadow(env):
    """A later same-key snapshot yields a movement evaluation (the Telegram update).

    Two ticks, as in production: the first freezes the candidate at the EARLY
    vintage, the second observes the later snapshot and evaluates the movement.
    A single tick would freeze at the *latest* eligible snapshot and correctly have
    nothing later to compare against.
    """
    _write_ledger(env["consumer_root"], [])
    _write_ledger(
        env["research_root"],
        [_commitment(fixture_id="mt_bundes_6", comp_id=NON_PILOT_C_COMP,
                     commitment_hash="commit_bundes_6")],
    )
    root = env["shadow_root"]
    root.mkdir(parents=True, exist_ok=True)
    store = CaptureStore(path=root / "captures.jsonl.gz")
    for rec in _captures("mt_bundes_6", OBS_EARLY, over=1.85, under=2.05):
        store.append(rec)
    _frontier(root, GEN_AT - 3600.0)

    kwargs = dict(
        shadow_root=root,
        broadcast_root=env["consumer_root"],
        research_broadcast_root=env["research_root"],
    )
    # Tick 1: only the EARLY snapshot exists, so the candidate freezes there.
    first = shadow_process.run(**kwargs, now=OBS_EARLY + 60.0)
    assert first.candidates_new >= 1
    assert first.evaluations_new == 0, "nothing later to compare against yet"

    # A later same-key snapshot arrives.
    for rec in _captures("mt_bundes_6", OBS_LATE, over=1.72, under=2.25):
        store.append(rec)

    # Tick 2: the movement is now observable.
    second = shadow_process.run(**kwargs, now=KICKOFF - 60.0)

    assert second.evaluations_new >= 1
    evals = list(default_evaluation_store(root=root).read_all_dicts())
    assert evals
    ev = evals[0]
    assert ev["record_type"] == "SHADOW_RESIDUAL_EVALUATION"
    assert ev["shadow_id"]
    assert ev["movement_direction"] in ("TOWARD_MODEL", "AWAY_FROM_MODEL", "FLAT")
    # The evaluation references the frozen shadow; it never mutates it.
    stored = list(default_candidate_store(root=root).read_all_dicts())
    assert {e["shadow_id"] for e in evals} <= {s["shadow_id"] for s in stored}


def test_rerun_is_idempotent_for_the_expanded_universe(env):
    """Re-running against unchanged state adds nothing."""
    _write_ledger(env["consumer_root"], [])
    _write_ledger(
        env["research_root"],
        [_commitment(fixture_id="mt_bundes_7", comp_id=NON_PILOT_C_COMP,
                     commitment_hash="commit_bundes_7")],
    )
    _write_captures(env["shadow_root"], [("mt_bundes_7", OBS_EARLY)])
    _frontier(env["shadow_root"], GEN_AT - 3600.0)

    kwargs = dict(
        shadow_root=env["shadow_root"],
        broadcast_root=env["consumer_root"],
        research_broadcast_root=env["research_root"],
        now=KICKOFF - 60.0,
    )
    first = shadow_process.run(**kwargs)
    second = shadow_process.run(**kwargs)

    assert first.candidates_new >= 1
    assert second.candidates_new == 0


def test_shadow_process_has_no_league_allowlist():
    """Structural: the shadow path must contain no competition predicate."""
    import inspect

    from src.research.prospective import shadow_builder, shadow_residual

    for module in (shadow_process, shadow_builder, shadow_residual):
        source = inspect.getsource(module)
        for banned in ("comp_3039", "comp_8321", "comp_9777", "comp_0976"):
            assert banned not in source, (
                f"{module.__name__} references Pilot-C competition id {banned}"
            )
