# Feature: asymmetric-matchup-engine, Property 20: Mandatory caveat on every output
"""Property 20: the mandatory caveat appears on EVERY Analysis_CLI output (task 11.4).

**Property 20** — for any Analysis_CLI output (success, reduced-coverage,
unrecognised, ambiguous, no-fixture, zero-history, cap-exceeded), the rendered
output contains the mandatory caveat stating that a single fixture demonstrates
nothing about edge and that the engine has not beaten market prices in
systematic testing.

Validates: Requirements 9.12.

Implemented as a single Hypothesis property test over the space of output kinds
with ``@settings(max_examples=100)``.
"""

from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from src.research.asymmetric.cli import MANDATORY_CAVEAT
from src.research.asymmetric.live_fetch import CappedLiveFetcher
from tests.asymmetric._cli_helpers import build_corpus, load_cli_module

_MOD = load_cli_module()


def _caveat_key_phrases() -> None:
    # The caveat must state both load-bearing claims.
    assert "single fixture" in MANDATORY_CAVEAT
    assert "NOT beaten market prices" in MANDATORY_CAVEAT


@settings(max_examples=100, deadline=None)
@given(kind=st.sampled_from(
    ["success", "reduced", "unrecognised", "ambiguous", "no_fixture",
     "zero_history", "cap_exceeded", "bad_date"]
))
def test_every_output_kind_carries_the_caveat(kind: str) -> None:
    _caveat_key_phrases()

    if kind == "success":
        corpus = build_corpus()
        out = _MOD.analyze("Leeds", "Norwich", "2026-09-05", corpus=corpus)
    elif kind == "reduced":
        # Only a few completed matches for one team before the fixture.
        corpus = build_corpus(n_history=6)
        out = _MOD.analyze("Leeds", "Norwich", "2026-09-05", corpus=corpus)
    elif kind == "unrecognised":
        corpus = build_corpus()
        out = _MOD.analyze("Zzzz", "Norwich", "2026-09-05", corpus=corpus)
    elif kind == "ambiguous":
        # Two teams sharing a substring -> ambiguous query "Uni".
        corpus = build_corpus(home="United City", away="United Town")
        out = _MOD.analyze("United", "United Town", "2026-09-05", corpus=corpus)
    elif kind == "no_fixture":
        corpus = build_corpus()
        out = _MOD.analyze("Leeds", "Norwich", "2026-09-07", corpus=corpus)
    elif kind == "zero_history":
        corpus = build_corpus(n_history=0)
        out = _MOD.analyze("Leeds", "Norwich", "2026-09-05", corpus=corpus)
    elif kind == "cap_exceeded":
        corpus = build_corpus()
        out = _MOD.analyze(
            "Leeds", "Norwich", "2026-09-05", corpus=corpus,
            fetcher=CappedLiveFetcher(cap=0.0),
        )
    else:  # bad_date
        corpus = build_corpus()
        out = _MOD.analyze("Leeds", "Norwich", "05-09-2026", corpus=corpus)

    assert MANDATORY_CAVEAT in out, f"caveat missing from {kind} output"
