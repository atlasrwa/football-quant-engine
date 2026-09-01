"""Tests for the Pilot C predict-phase COVERED-LEAGUE gate.

The predict phase must gate on COVERED-LEAGUE membership (competition id), NOT on
corpus-team membership. The old gate tested corpus teams, so out-of-coverage
fixtures (Veikkausliiga / Serie A / Brazil) whose teams happened to appear in the
corpus slipped through and were committed into a covered-league-only pre-registered
sample. These tests assert the predict phase can NEVER commit a fixture outside the
covered leagues.
"""

import importlib
import json
import sys

import pytest

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

from src.research.forward.attestation_ledger import AttestationLedger
from src.research.forward.league_coverage import (
    COVERED_LEAGUE_COMP_IDS,
    is_covered_comp,
)

import pilotC_forward_predict as predict


# ── 1. the pure gate helper ──────────────────────────────────────────────────

def test_commit_gate_rejects_out_of_coverage_even_with_corpus_teams():
    """A fixture in a non-covered league is rejected even if BOTH teams are in the
    corpus — this is exactly the case that let Veikkausliiga through before."""
    corpus = {"Ilves", "HJK", "Inter Turku", "KuPS"}
    veikkausliiga = {"comp": "comp_2674", "home": "Ilves", "away": "HJK"}
    assert not is_covered_comp("comp_2674")
    assert predict.commit_gate(veikkausliiga, corpus) == "reject_out_of_coverage"


def test_commit_gate_rejects_serie_a_and_brazil():
    corpus = {"Atalanta", "Bologna", "Bahia", "Internacional"}
    serie_a = {"comp": "comp_5840", "home": "Atalanta", "away": "Bologna"}
    brazil = {"comp": "comp_4795", "home": "Bahia", "away": "Internacional"}
    assert predict.commit_gate(serie_a, corpus) == "reject_out_of_coverage"
    assert predict.commit_gate(brazil, corpus) == "reject_out_of_coverage"


def test_commit_gate_allows_covered_league_with_corpus_teams():
    corpus = {"Leeds", "Norwich"}
    championship = {"comp": "comp_8321", "home": "Leeds", "away": "Norwich"}
    assert is_covered_comp("comp_8321")
    assert predict.commit_gate(championship, corpus) == "commit"


def test_commit_gate_skips_covered_league_without_corpus_history():
    """Covered league but a team lacks corpus history -> skip (not out-of-coverage)."""
    corpus = {"Leeds"}
    championship = {"comp": "comp_8321", "home": "Leeds", "away": "UnknownFC"}
    assert predict.commit_gate(championship, corpus) == "skip_no_corpus_history"


def test_missing_comp_is_out_of_coverage():
    corpus = {"A", "B"}
    assert predict.commit_gate({"home": "A", "away": "B"}, corpus) == "reject_out_of_coverage"


# ── 2. end-to-end: main() never commits an out-of-coverage fixture ───────────

def test_predict_main_never_commits_out_of_coverage(tmp_path, monkeypatch):
    """Drive predict.main() with a universe containing BOTH a covered fixture and an
    out-of-coverage fixture whose teams are in the corpus. Assert the ledger receives
    a commitment ONLY for the covered fixture — never the out-of-coverage one."""
    # Redirect all output paths into the tmp dir so we never touch the real ledger.
    ch = tmp_path / "ch"
    ch.mkdir()
    commit_ledger = tmp_path / "commitments.jsonl"
    reveal_ledger = tmp_path / "reveals.jsonl"
    out_file = tmp_path / "predictions.json"
    monkeypatch.setattr(predict, "CH", str(ch))
    monkeypatch.setattr(predict, "OUT", str(out_file))
    monkeypatch.setattr(predict, "COMMIT_LEDGER", str(commit_ledger))
    monkeypatch.setattr(predict, "REVEAL_LEDGER", str(reveal_ledger))

    corpus_teams = {"Leeds", "Norwich", "Ilves", "HJK"}
    kickoff = 9_999_999_999.0  # far future so commit is always pre-kickoff

    # A covered Championship fixture and an out-of-coverage Veikkausliiga fixture.
    # Both fixtures' teams are in the corpus — so a corpus-team gate would (wrongly)
    # admit both. The covered-league gate must admit only the Championship one.
    fixture_list = {
        "meta": {
            "mt_COVERED": {"comp": "comp_8321", "home": "Leeds", "away": "Norwich",
                           "ts": kickoff, "status": "scheduled"},
            "mt_OOC": {"comp": "comp_2674", "home": "Ilves", "away": "HJK",
                       "ts": kickoff, "status": "scheduled"},
        }
    }
    (ch / "_pilotC_fixture_list.json").write_text(json.dumps(fixture_list))

    # Stub the heavy corpus/model machinery so the test is hermetic and fast.
    import pilotC_stat_mixer as mix
    monkeypatch.setattr(mix, "load_corpus", lambda: [])
    monkeypatch.setattr(mix, "build_histories", lambda ms: {t: {} for t in corpus_teams})

    # A single goals@2.5 model that always predicts 0.55; fit is stubbed away.
    saved_models = {"models": [{"market": "goals", "line": 2.5, "C": 1.0, "l1_ratio": 0.5}]}
    stat_mixer_path = tmp_path / "pilotC_stat_mixer.json"
    stat_mixer_path.write_text(json.dumps(saved_models))
    # main() hardcodes the stat_mixer.json path; patch json.load-driven open by
    # monkeypatching the module's fit_full and the saved-models load path.
    monkeypatch.setattr(predict, "fit_full", lambda *a, **k: {"stub": True})
    monkeypatch.setattr(predict, "predict_one", lambda model, hist, m, market: 0.55)

    # Provide odds books for BOTH fixtures so odds availability is never the reason a
    # fixture is skipped — the ONLY thing that should stop the OOC fixture is the gate.
    def fake_books(mid):
        return {"betfair-exchange": {"total_goals": {"2.5": {
            "over": {"last_seen": 1.9}, "under": {"last_seen": 2.0}}}}}
    monkeypatch.setattr(predict, "load_forward_books", fake_books)

    # main() loads saved hyperparameters from a hardcoded absolute path; redirect the
    # builtin open for that one path to our stub file.
    real_open = open
    hard_path = "/home/ubuntu/data/discovery/pilotC_stat_mixer.json"

    def patched_open(path, *args, **kwargs):
        if path == hard_path:
            return real_open(stat_mixer_path, *args, **kwargs)
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr("builtins.open", patched_open)

    attest = predict.main()

    # The out-of-coverage fixture must be rejected and never committed.
    assert attest["rejected_out_of_coverage"] >= 1
    assert "comp_2674" in attest["rejected_out_of_coverage_by_league"]

    led = AttestationLedger(commit_path=commit_ledger, reveal_path=reveal_ledger)
    committed_fixtures = {c["fixture_id"] for c in led.load_commitments()}
    assert "mt_OOC" not in committed_fixtures, (
        "out-of-coverage fixture was committed — the gate failed")
    assert "mt_COVERED" in committed_fixtures, (
        "covered fixture should have been committed")

    # Ledger chain still verifies (no tampering, no backdating).
    ok, problems = led.verify_chain(commit_ledger)
    assert ok, f"commit ledger chain broken: {problems}"
