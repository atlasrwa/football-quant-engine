"""CappedLiveFetcher — capped, reported live-fetch fallback for the CLI only.

Responsibility:
    Provide the ONLY place live API requests may occur, and only when required
    fixture/team data is absent from cache. Admits spend up to a configured cap,
    refuses a fetch that would breach the cap (setting ``cap_exceeded``), and
    reports the spend incurred. Confined to the CLI package and never imported
    into the build/backtest path, which is strictly zero-API (Req 9.16, 12.3,
    12.4).

Design decisions:
    * **Cap accounting is pure and monotonic.** :meth:`CappedLiveFetcher.admit`
      is a pure decision over the running total: a fetch of cost ``c`` is admitted
      iff ``spent + c <= cap``; otherwise it is refused and ``cap_exceeded`` is
      latched True. Admitted costs accumulate into ``spend_units`` (Property 22).
      This holds regardless of the order or magnitude of costs, so the reported
      ``spend_units`` is always the exact sum of admitted costs and never exceeds
      the cap.
    * **The transport is injected.** The actual fetch callable (which may reuse
      ``research/footystats/client.py`` or ``scripts/thestatsapi_client.py``) is
      passed in by the CLI. This module does not import those clients directly, so
      the build/backtest path can never pull a live client in through here, and
      tests can inject a stub. A ``None`` transport makes the fetcher
      accounting-only (useful for the pure cap property test).
    * **Refusal is not an error state for accounting.** A refused fetch simply
      does not advance ``spend_units``; the caller decides whether to terminate
      (the CLI terminates with a capped-fetch error, still emitting the caveat).

Isolation: imports nothing from Prior_Efforts (Req 13.2); confined to the CLI.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.research.asymmetric.models import SpendReport

#: Default per-invocation spend cap (in abstract "units"; one unit ~= one
#: admitted request unless the caller supplies a per-fetch cost).
DEFAULT_SPEND_CAP = 10.0


@dataclass(frozen=True)
class FetchOutcome:
    """The outcome of a single admit-or-refuse decision.

    Attributes:
        admitted: whether the fetch was admitted under the cap.
        cost: the cost that was considered.
        payload: the transport's return value when admitted (else None).
        spent_after: the cumulative admitted spend after this decision.
    """

    admitted: bool
    cost: float
    payload: Optional[Any]
    spent_after: float


# A transport is any callable ``(key: str) -> payload`` performing one fetch.
Transport = Callable[[str], Any]


class CapExceededError(RuntimeError):
    """Raised by :meth:`CappedLiveFetcher.fetch` when a fetch is refused.

    The CLI catches this to terminate with a capped-fetch error while still
    emitting the mandatory caveat (Req 12.4).
    """


class CappedLiveFetcher:
    """Capped, reported live fetcher — the only live-API surface (Req 12.3, 12.4).

    Args:
        cap: the maximum cumulative admitted spend (>= 0).
        transport: optional injected fetch callable ``(key) -> payload``. When
            ``None`` the fetcher is accounting-only (no I/O).
        default_cost: the cost charged per fetch when the caller does not supply
            an explicit per-fetch cost. Defaults to ``1.0``.
    """

    def __init__(
        self,
        cap: float = DEFAULT_SPEND_CAP,
        transport: Optional[Transport] = None,
        default_cost: float = 1.0,
    ) -> None:
        if cap < 0.0:
            raise ValueError(f"cap must be >= 0, got {cap}")
        if default_cost < 0.0:
            raise ValueError(f"default_cost must be >= 0, got {default_cost}")
        self._cap = float(cap)
        self._transport = transport
        self._default_cost = float(default_cost)
        self._spent = 0.0
        self._requests_made = 0
        self._cap_exceeded = False

    # ── accounting state ─────────────────────────────────────────
    @property
    def cap(self) -> float:
        return self._cap

    @property
    def spend_units(self) -> float:
        """Sum of admitted fetch costs (Property 22)."""
        return self._spent

    @property
    def requests_made(self) -> int:
        """Number of admitted (actually issued) fetches."""
        return self._requests_made

    @property
    def cap_exceeded(self) -> bool:
        """Latched True once any fetch was refused for breaching the cap."""
        return self._cap_exceeded

    def report(self) -> SpendReport:
        """Snapshot the spend accounting as a :class:`SpendReport` (Req 12.4)."""
        return SpendReport(
            requests_made=self._requests_made,
            spend_units=self._spent,
            cap=self._cap,
            cap_exceeded=self._cap_exceeded,
        )

    # ── pure admit decision (Property 22) ────────────────────────
    def would_admit(self, cost: float) -> bool:
        """True iff a fetch of ``cost`` fits under the cap given current spend."""
        return (self._spent + max(0.0, cost)) <= self._cap + 1e-12

    def admit(self, cost: Optional[float] = None) -> bool:
        """Admit or refuse a fetch of ``cost`` against the cap (Property 22).

        Admits iff ``spend_units + cost <= cap``; on admit, advances
        ``spend_units`` and ``requests_made``. On refusal, latches
        ``cap_exceeded`` True and leaves the accounting unchanged. Pure decision:
        no transport is invoked here.
        """
        c = self._default_cost if cost is None else max(0.0, float(cost))
        if self.would_admit(c):
            self._spent += c
            self._requests_made += 1
            return True
        self._cap_exceeded = True
        return False

    # ── fetch (admit + transport) ────────────────────────────────
    def fetch(self, key: str, cost: Optional[float] = None) -> FetchOutcome:
        """Admit and, if admitted, perform one transport fetch for ``key``.

        Returns a :class:`FetchOutcome`. When refused, ``admitted`` is False,
        ``payload`` is None, and ``cap_exceeded`` is set; the caller decides
        whether to raise/terminate. When admitted with no transport configured,
        ``payload`` is None but the spend is still charged (accounting-only mode).
        """
        c = self._default_cost if cost is None else max(0.0, float(cost))
        admitted = self.admit(c)
        if not admitted:
            return FetchOutcome(
                admitted=False, cost=c, payload=None, spent_after=self._spent
            )
        payload = self._transport(key) if self._transport is not None else None
        return FetchOutcome(
            admitted=True, cost=c, payload=payload, spent_after=self._spent
        )
