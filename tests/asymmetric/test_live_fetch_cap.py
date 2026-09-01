# Feature: asymmetric-matchup-engine, Property 22: Live-fetch spend cap
"""Property 22: the live-fetch spend cap is never breached (task 11.6).

**Property 22** — for any sequence of live fetch costs, the cumulative admitted
spend never exceeds the configured cap; when the next fetch would breach the cap
it is refused and ``cap_exceeded`` is set; and the reported ``spend_units`` equals
the sum of the admitted fetch costs.

Validates: Requirements 12.4.

Implemented as one Hypothesis property test over the ``fetch_cost_sequences``
strategy with ``@settings(max_examples=100)``.
"""

from __future__ import annotations

from hypothesis import given, settings

from src.research.asymmetric.live_fetch import CappedLiveFetcher
from tests.asymmetric.strategies import fetch_cost_sequences

_EPS = 1e-9


@settings(max_examples=200, deadline=None)
@given(seq=fetch_cost_sequences())
def test_spend_cap_never_breached(seq) -> None:
    costs, cap = seq
    fetcher = CappedLiveFetcher(cap=cap)

    admitted_costs: list[float] = []
    any_refused = False
    for c in costs:
        admitted = fetcher.admit(c)
        if admitted:
            admitted_costs.append(max(0.0, c))
        else:
            any_refused = True
            # A refused fetch must be one that would breach the cap.
            assert fetcher.spend_units + max(0.0, c) > cap + _EPS

        # Invariant after every step: admitted spend never exceeds the cap.
        assert fetcher.spend_units <= cap + 1e-6

    # spend_units equals the exact sum of admitted costs.
    assert abs(fetcher.spend_units - sum(admitted_costs)) <= 1e-6
    # cap_exceeded is set iff at least one fetch was refused.
    assert fetcher.cap_exceeded is any_refused
    # requests_made counts only admitted fetches.
    assert fetcher.requests_made == len(admitted_costs)

    report = fetcher.report()
    assert report.spend_units == fetcher.spend_units
    assert report.cap == cap
    assert report.cap_exceeded == fetcher.cap_exceeded


def test_fetch_refused_returns_unadmitted_outcome() -> None:
    """A fetch that would breach the cap is refused with no payload."""
    calls: list[str] = []

    def transport(key: str) -> str:
        calls.append(key)
        return f"payload:{key}"

    fetcher = CappedLiveFetcher(cap=1.0, transport=transport, default_cost=1.0)
    ok = fetcher.fetch("first")     # admitted (spend 1.0 == cap)
    assert ok.admitted and ok.payload == "payload:first"
    refused = fetcher.fetch("second")  # would breach cap
    assert not refused.admitted
    assert refused.payload is None
    assert fetcher.cap_exceeded is True
    # Transport was invoked only for the admitted fetch.
    assert calls == ["first"]
