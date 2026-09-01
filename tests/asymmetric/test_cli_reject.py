# Feature: asymmetric-matchup-engine, Property 21: Reject-without-predictions on bad resolution
"""Property 21: bad resolution rejects WITHOUT predictions (task 11.5).

**Property 21** — for any invocation whose home/away name is unrecognised, whose
name is ambiguous, or for which no fixture is scheduled on the supplied date, the
Analysis_CLI produces no Per_Side_Target or Derived_Outcome predictions and its
output identifies the specific offending input.

Validates: Requirements 9.13, 9.14, 9.15.

Implemented as one Hypothesis property test over the three bad-resolution kinds
with ``@settings(max_examples=100)``.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from tests.asymmetric._cli_helpers import build_corpus, load_cli_module

_MOD = load_cli_module()

# Markers that would ONLY appear if predictions were produced.
_PREDICTION_MARKERS = (
    "PER-SIDE PREDICTIONS",
    "DERIVED MATCH OUTCOMES",
    "ASYMMETRY STATEMENT",
)


def _has_no_predictions(out: str) -> bool:
    return all(marker not in out for marker in _PREDICTION_MARKERS)


@settings(max_examples=100, deadline=None)
@given(kind=st.sampled_from(["unrecognised", "ambiguous", "no_fixture"]))
def test_bad_resolution_produces_no_predictions_and_names_input(kind: str) -> None:
    if kind == "unrecognised":
        corpus = build_corpus()
        out = _MOD.analyze("Nonexistent FC", "Norwich", "2026-09-05", corpus=corpus)
        assert "UNRECOGNISED TEAM" in out
        assert "Nonexistent FC" in out  # names the offending input (Req 9.13)
    elif kind == "ambiguous":
        corpus = build_corpus(home="United City", away="United Town")
        out = _MOD.analyze("United", "United Town", "2026-09-05", corpus=corpus)
        assert "AMBIGUOUS TEAM" in out
        assert "United" in out
        assert "candidates:" in out  # lists candidates (Req 9.14)
    else:  # no_fixture
        corpus = build_corpus()
        out = _MOD.analyze("Leeds", "Norwich", "2026-09-07", corpus=corpus)
        assert "NO MATCHING FIXTURE" in out
        assert "2026-09-07" in out  # names the offending date (Req 9.15)

    assert _has_no_predictions(out), f"{kind}: predictions were produced"
