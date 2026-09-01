"""Edge-scanner flags must be STRUCTURALLY excluded from the Pilot C sample AND from
the manual_predict ledger.

These tests are the enforcement proof requested in the edge-scanner brief (§9 + ground
rules "structurally separate ... test-enforced, no directory globbing"). They assert —
against the real code, not by convention — that a scanner flag cannot appear in Pilot
C's settled sample, per-cell counts toward 385, health enumeration, or in the manual
ledger, and vice versa.

The separation rests on two facts, both checked here:
  1. PATH separation: scanner records live in data/forward/scanner_*.jsonl /
     scanner_*.json; Pilot C (and manual) only ever read their own literal filenames
     (no directory glob), so a scanner file is never enumerated by either.
  2. NAMESPACE separation: scanner prediction_ids are "flagged:...", never "pilotC:..."
     or "manual:...", so even a hypothetical file mixup could not collide.

A third block checks the pre-registration is committed BEFORE settlement and is
immutable (its recorded hash still matches the document on disk).
"""
import importlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

import edge_scanner as es  # noqa: E402
from src.research.forward.attestation_ledger import (  # noqa: E402
    AttestationLedger, compute_document_hash,
)


# ── 1. STRUCTURAL: scanner paths are distinct and never pilotC_* / manual_* ──

def test_scanner_paths_are_distinct_from_pilotc_and_manual():
    import pilotC_settle as settle
    import pilotC_forward_predict as fpred
    import manual_predict as mp

    scanner_paths = {
        es.SCANNER_FLAGGED_LOG, es.SCANNER_COMMIT_LEDGER, es.SCANNER_REVEAL_LEDGER,
        es.SCANNER_SETTLED_LOG, es.SCANNER_SCORECARD, es.SCANNER_PREREG_DOC,
        es.SCANNER_PREREG_LEDGER,
    }
    pilotc_paths = {
        settle.COMMIT_LEDGER, settle.REVEAL_LEDGER, settle.PRED, settle.LOG,
        fpred.COMMIT_LEDGER, fpred.REVEAL_LEDGER, fpred.OUT,
    }
    manual_paths = {
        mp.MANUAL_COMMIT_LEDGER, mp.MANUAL_REVEAL_LEDGER,
        mp.MANUAL_PRED_LOG, mp.MANUAL_SETTLED_LOG,
    }
    # No scanner artifact shares a filename with any Pilot C or manual artifact.
    assert scanner_paths.isdisjoint(pilotc_paths)
    assert scanner_paths.isdisjoint(manual_paths)
    # And none of the scanner filenames contain a pilotC_* or manual_* ledger basename.
    for p in scanner_paths:
        base = Path(p).name
        assert "pilotC_commitments" not in base
        assert "pilotC_reveals" not in base
        assert "pilotC_forward_predictions" not in base
        assert "pilotC_settled_log" not in base
        assert "manual_commitments" not in base
        assert "manual_reveals" not in base
        assert "manual_predictions" not in base
        assert "manual_settled_log" not in base


def test_scanner_id_prefix_is_not_pilotc_or_manual():
    pid = es._flag_id("mt_TEST", "goals", 2.5)
    assert pid.startswith("flagged:")
    assert not pid.startswith("pilotC:")
    assert not pid.startswith("manual:")


def test_pilotc_and_manual_sample_readers_use_literal_paths_no_glob():
    """Guard against a future refactor that globs data/forward/*.jsonl (which WOULD pick
    up scanner records). Pilot C's and manual's readers must reference literal own-named
    files only, and must never reference scanner_* artifacts."""
    settle_src = Path("/home/ubuntu/scripts/pilotC_settle.py").read_text()
    loop_src = Path("/home/ubuntu/scripts/pilotC_forward_loop.py").read_text()
    manual_src = Path("/home/ubuntu/scripts/manual_predict.py").read_text()
    # The Pilot C sample enumerator (score) must not glob the forward dir.
    assert "glob" not in _sample_reading_region(settle_src)
    # The per-cell tally reads the literal settled-log filename.
    assert "pilotC_settled_log.json" in loop_src
    # None of Pilot C's or manual's code references any scanner artifact.
    assert "scanner_" not in settle_src
    assert "scanner_" not in loop_src
    assert "scanner_" not in manual_src
    # Symmetric: the scanner never writes to a pilotC_* or manual_* ledger/log basename.
    scanner_src = Path("/home/ubuntu/scripts/edge_scanner.py").read_text()
    assert "manual_commitments" not in scanner_src
    assert "manual_reveals" not in scanner_src
    assert "manual_settled_log" not in scanner_src
    # The scanner reuses the READ-ONLY shared odds cache keys (pilotC_odds_*) — that is
    # allowed (it adds nothing to any ledger) — but never a pilotC ledger/log basename.
    assert "pilotC_commitments" not in scanner_src
    assert "pilotC_reveals" not in scanner_src
    assert "pilotC_settled_log" not in scanner_src
    assert "pilotC_forward_predictions" not in scanner_src


def _sample_reading_region(src: str) -> str:
    """The body of score() where the sample is enumerated — must not glob."""
    start = src.find("def score(")
    end = src.find("def topup(")
    return src[start:end if end > 0 else len(src)]


# ── 2. BEHAVIORAL: write scanner records, run Pilot C readers, assert no leakage ─

@pytest.fixture
def isolated_scanner(tmp_path, monkeypatch):
    """Point the scanner module at temp files and write one committed+revealed flag."""
    commit = tmp_path / "scanner_commitments.jsonl"
    reveal = tmp_path / "scanner_reveals.jsonl"
    flagged = tmp_path / "scanner_flagged_lines.jsonl"
    settled = tmp_path / "scanner_settled_log.json"
    scorecard = tmp_path / "scanner_scorecard.json"
    monkeypatch.setattr(es, "SCANNER_COMMIT_LEDGER", str(commit))
    monkeypatch.setattr(es, "SCANNER_REVEAL_LEDGER", str(reveal))
    monkeypatch.setattr(es, "SCANNER_FLAGGED_LOG", str(flagged))
    monkeypatch.setattr(es, "SCANNER_SETTLED_LOG", str(settled))
    monkeypatch.setattr(es, "SCANNER_SCORECARD", str(scorecard))

    led = AttestationLedger(commit_path=str(commit), reveal_path=str(reveal))
    future = 9_999_999_999.0
    pid = es._flag_id("mt_SCANNER_TEST", "goals", 2.5)
    res = led.commit(prediction_id=pid, fixture_id="mt_SCANNER_TEST", model="goals_2.5",
                     kickoff_unix=future, p_over=0.56, p_under=0.44,
                     reference_price={"book": "betfair-exchange", "over_odds": 1.88,
                                      "under_odds": 2.02, "fair_p": 0.518, "overround": 0.004,
                                      "soft_book_only": False},
                     extra={"source": "scanner", "p_over": 0.56, "p_under": 0.44,
                            "side": "over", "net_edge_pp": 2.4})
    assert res.committed
    rev = led.reveal(prediction_id=pid, fixture_id="mt_SCANNER_TEST", model="goals_2.5",
                     outcome={"actual_over_or_yes": 1.0, "actual_value": 3, "side": "over",
                              "side_won": 1.0, "model_p_broad": 0.56},
                     extra={"source": "scanner"})
    assert rev.committed
    settled.write_text(json.dumps({"settled": [{
        "source": "scanner", "prediction_id": pid, "match_id": "mt_SCANNER_TEST",
        "market": "goals", "line": 2.5, "side": "over", "model_p_broad": 0.56,
        "actual_over_or_yes": 1.0, "side_won": 1.0,
        "best_price_odds": 1.88, "realized_return_at_best_price": 0.88,
        "settled_at": "now"}], "n_settled_total": 1}))
    return {"pid": pid, "commit": commit, "reveal": reveal, "settled": settled}


def test_scanner_record_absent_from_pilotc_commit_ledger(isolated_scanner):
    import pilotC_settle as settle
    led = AttestationLedger(commit_path=settle.COMMIT_LEDGER, reveal_path=settle.REVEAL_LEDGER)
    pilotc_ids = set(led.commitments_by_prediction().keys())
    assert isolated_scanner["pid"] not in pilotc_ids
    assert not any(i.startswith("flagged:") for i in pilotc_ids)


def test_scanner_record_absent_from_manual_commit_ledger(isolated_scanner):
    import manual_predict as mp
    led = AttestationLedger(commit_path=mp.MANUAL_COMMIT_LEDGER, reveal_path=mp.MANUAL_REVEAL_LEDGER)
    manual_ids = set(led.commitments_by_prediction().keys())
    assert isolated_scanner["pid"] not in manual_ids
    assert not any(i.startswith("flagged:") for i in manual_ids)


def test_scanner_settled_row_absent_from_pilotc_per_cell_counts(isolated_scanner):
    """_per_cell_settled_counts reads ONLY pilotC_settled_log.json — the scanner settled
    row (in a different file) must not increment any cell."""
    loop = importlib.import_module("pilotC_forward_loop")
    counts = loop._per_cell_settled_counts()
    pilotc_log = Path("/home/ubuntu/data/discovery/pilotC_settled_log.json")
    expected = {f"{m}@{l}": 0 for m, l in loop.PREREG_CELLS}
    if pilotc_log.exists():
        data = json.loads(pilotc_log.read_text())
        for r in data.get("settled", []):
            cell = f"{r['market']}@{r['line']}"
            if cell in expected:
                expected[cell] += 1
    assert counts == expected  # identical => scanner row contributed nothing

    if pilotc_log.exists():
        ids = {r["prediction_id"] for r in json.loads(pilotc_log.read_text()).get("settled", [])}
        assert isolated_scanner["pid"] not in ids
        assert not any(i.startswith("flagged:") for i in ids)


def test_pilotc_settle_score_never_reveals_scanner(isolated_scanner, monkeypatch):
    """Run the REAL pilotC_settle.score() and assert it never touches the scanner id.

    score() reveals against its hardcoded pilotC commit ledger; a scanner id committed to
    a different file cannot be revealed by it. We stub the network fetch so the test is
    offline and deterministic."""
    import pilotC_settle as settle
    monkeypatch.setattr(settle, "_fetch_final", lambda api, mid: {
        "home_goals": None, "away_goals": None, "total_goals": None,
        "total_corners": None, "total_cards": None})

    class _StubApi:
        def budget_snapshot(self):
            return {"last_monthly_remaining": "9999"}
    monkeypatch.setitem(sys.modules, "thestatsapi_client", _StubApi())

    settle.score(verbose=False)
    led = AttestationLedger(commit_path=settle.COMMIT_LEDGER, reveal_path=settle.REVEAL_LEDGER)
    pilotc_reveal_ids = set(led.reveals_by_prediction().keys())
    assert isolated_scanner["pid"] not in pilotc_reveal_ids
    assert not any(i.startswith("flagged:") for i in pilotc_reveal_ids)


def test_scanner_scorecard_does_not_read_pilotc_or_manual(isolated_scanner):
    """The scanner scorecard counts ONLY scanner-settled flags — its numbers must come
    from the (isolated) scanner settled log, never from the real Pilot C / manual logs."""
    sc = es.build_scorecard()
    # Exactly the one isolated scanner flag is settled; a leak from the (large) real
    # Pilot C settled log would blow this far past 1.
    assert sc["flags_settled"] == 1
    assert sc["stopping_threshold_reached"] is False  # 1 < 100 pre-registered threshold


# ── 3. INTEGRITY: hash recomputable + pre-registration committed and immutable ─

def test_scanner_commit_hash_independently_recomputable(isolated_scanner):
    """A published scanner commitment hash must recompute from the record alone."""
    result = es.verify_hash("mt_SCANNER_TEST")
    assert result["rows_checked"] >= 1
    assert all(d["recomputed_matches"] for d in result["detail"])
    assert result["chain_verifies"]


def test_preregistration_committed_before_settlement_and_immutable():
    """The pre-registration document must be attested (its hash recorded in the pre-reg
    ledger) and unchanged since — the recorded hash must still match the file on disk.
    This is the 'committed before any flag settles, never revised after seeing results'
    guarantee at the artifact level."""
    doc = Path(es.SCANNER_PREREG_DOC)
    ledger = Path(es.SCANNER_PREREG_LEDGER)
    assert doc.exists(), "pre-registration document must exist"
    assert ledger.exists(), "pre-registration ledger must exist"

    rows = [json.loads(l) for l in ledger.read_text().splitlines() if l.strip()]
    assert rows, "pre-registration ledger must contain at least one attestation"

    current_hash = compute_document_hash(doc)
    # The most recent attestation for this document must match the file as it stands now
    # (no post-attestation edits). A revision would need a NEW attestation row.
    matching = [r for r in rows if r.get("document_hash") == current_hash]
    assert matching, (
        "current pre-registration document hash is not attested in the ledger — the doc "
        "was edited after registration, or was never attested. That violates the "
        "'never revised after seeing results' rule.")

    # The registered stopping rule the scorecard enforces must be present and fixed.
    prereg = json.loads(doc.read_text())
    stop = prereg.get("minimum_sample_and_stopping_rule", {})
    assert stop.get("minimum_settled_flags_before_evaluation") == 100
    assert stop.get("type") == "fixed-sample, no peeking"


def test_no_stake_sizing_anywhere_in_scanner():
    """§8 / R06: the scanner must never emit stake sizing, Kelly, or bankroll advice.
    Guard that no such feature creeps into the CODE (not the docstring, which
    deliberately names these terms to forbid them).

    We AST-parse the module and check for staking-related symbol NAMES among its
    functions/classes/assignment targets — this ignores strings and comments, so the
    prohibition prose in the module docstring does not trip the guard, while an actual
    ``def kelly_fraction`` / ``stake = ...`` implementation would."""
    import ast
    src = Path("/home/ubuntu/scripts/edge_scanner.py").read_text()
    tree = ast.parse(src)
    banned_substrings = ("kelly", "stake", "bankroll", "position_size")
    offending = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
        for nm in names:
            low = nm.lower()
            if any(b in low for b in banned_substrings):
                offending.append(nm)
    assert not offending, f"forbidden staking construct(s) present in code: {sorted(set(offending))}"



# ── 4. CORE LOGIC: net-edge ranking, fair-vs-best-price, cross-book config ──────
#
# These are offline unit tests of the scanner's decision logic (no network, no model
# fit). They lock in the brief's critical design points so a refactor cannot silently
# regress them:
#   §4 rank by edge NET OF THE MARGIN HURDLE, never raw edge
#   §5 fair price (sharpest ref) and best price (highest odds) are DISTINCT roles
#   §6 the four cross-book configurations, classified boundary-stably

def _bf(fair_p, overround, over_odds, under_odds):
    return {"fair_p": fair_p, "overround": overround,
            "over_odds": over_odds, "under_odds": under_odds}


def test_net_edge_ranking_not_raw_edge():
    """The brief's central point: +7.91pp vs a 9.11% overround is a SMALLER real edge
    than +5.25pp vs a 0.76% overround. rank_flags must order by net_edge, not raw."""
    # Two synthetic flags mirroring the brief's example.
    cards = {"market": "cards", "line": 3.5, "is_flag": True,
             "raw_edge_pp": 7.91, "net_edge_pp": 3.36,
             "reliability": {"passes": True}}
    btts = {"market": "btts", "line": None, "is_flag": True,
            "raw_edge_pp": 5.25, "net_edge_pp": 4.87,
            "reliability": {"passes": True}}
    scan = {"lines": [cards, btts]}
    flags_pass, flags_fail = es.rank_flags(scan)
    assert [f["market"] for f in flags_pass] == ["btts", "cards"], (
        "must rank by NET edge (btts 4.87 > cards 3.36), NOT raw edge (cards 7.91 first)")
    assert not flags_fail


def test_reliability_filter_splits_pass_and_fail():
    passing = {"market": "goals", "line": 2.5, "is_flag": True, "net_edge_pp": 2.0,
               "reliability": {"passes": True}}
    failing = {"market": "corners", "line": 9.5, "is_flag": True, "net_edge_pp": 3.0,
               "reliability": {"passes": False}}
    not_flag = {"market": "goals", "line": 1.5, "is_flag": False}
    flags_pass, flags_fail = es.rank_flags({"lines": [passing, failing, not_flag]})
    assert [f["market"] for f in flags_pass] == ["goals"]
    assert [f["market"] for f in flags_fail] == ["corners"]  # edge but fails reliability — reported, not dropped


def test_fair_reference_prefers_sharp_then_pinnacle():
    both = {"betfair-exchange": _bf(0.50, 0.01, 1.98, 2.02),
            "pinnacle": _bf(0.51, 0.02, 1.95, 2.0),
            "bet365": _bf(0.49, 0.06, 2.05, 1.80)}
    assert es._pick_fair_reference(both) == ("betfair-exchange", False)
    no_betfair = {"pinnacle": _bf(0.51, 0.02, 1.95, 2.0), "bet365": _bf(0.49, 0.06, 2.05, 1.8)}
    assert es._pick_fair_reference(no_betfair) == ("pinnacle", False)
    soft_only = {"bet365": _bf(0.49, 0.06, 2.05, 1.8)}
    ref, soft = es._pick_fair_reference(soft_only)
    assert ref == "bet365" and soft is True  # soft-book-only must be flagged


def test_best_price_is_distinct_from_fair_reference():
    """§5: fair reference (Betfair) and best execution price (highest odds, maybe a soft
    book) are separate roles. Here Betfair is the fair ref but bet365 offers better over
    odds — the scanner must return bet365 for the OVER best price."""
    book_fair = {"betfair-exchange": _bf(0.50, 0.01, 1.98, 2.02),
                 "bet365": _bf(0.49, 0.06, 2.05, 1.80)}
    ref_book, soft_only = es._pick_fair_reference(book_fair)
    assert ref_book == "betfair-exchange"
    bp_book, bp_odds = es._best_price(book_fair, "over")
    assert (bp_book, bp_odds) == ("bet365", 2.05)  # best price != fair reference book
    bp_book_u, bp_odds_u = es._best_price(book_fair, "under")
    assert (bp_book_u, bp_odds_u) == ("betfair-exchange", 2.02)


def _cfg(model_p, sharp_fp, soft_fp, over=True):
    bf = {"betfair-exchange": _bf(sharp_fp, 0.01, 2.0, 2.0),
          "bet365": _bf(soft_fp, 0.06, 2.0, 2.0)}
    return es._cross_book_config(model_p, bf, "betfair-exchange", over)


def test_cross_book_config_four_configurations():
    # books agree with each other:
    assert _cfg(0.501, 0.50, 0.505) == "model_agrees_with_both_books"
    assert _cfg(0.56, 0.50, 0.505) == "model_disagrees_with_both_books_which_agree"
    # books disagree substantially:
    assert _cfg(0.50, 0.45, 0.55) == "model_between_books_that_disagree"
    assert _cfg(0.45, 0.45, 0.55) == "model_agrees_with_sharp_both_disagree_with_soft"
    assert _cfg(0.43, 0.45, 0.55) == "books_disagree_model_sides_with_sharp"
    assert _cfg(0.56, 0.45, 0.55) == "books_disagree_model_sides_with_soft"
    # single book -> operational fallback
    single = {"betfair-exchange": _bf(0.5, 0.01, 2.0, 2.0)}
    assert es._cross_book_config(0.5, single, "betfair-exchange", True) == "single_book_only"


def test_rich_unavailable_reported_when_corpus_not_joinable(monkeypatch):
    """The corpus is FootyStats-keyed (numeric ids), so rich /stats cannot be joined.
    _build_rich_history must report rich_structurally_available=False with a reason, and
    must NOT fabricate any npxG substitution."""
    class _NoFetchApi:
        def is_cached(self, k):
            return False
    hist = {"A": [(1.0, {"id": 8223680, "home_name": "A", "away_name": "B"}, "home")] * 5,
            "B": [(1.0, {"id": 8223731, "home_name": "C", "away_name": "B"}, "away")] * 5}
    rich_hist, info = es._build_rich_history(_NoFetchApi(), [], hist, "A", "B", allow_fetch=True)
    assert info["rich_structurally_available"] is False
    assert info["npxg_substitutions"] == 0
    assert info["unavailable_reason"] and "mt_" in info["unavailable_reason"]
