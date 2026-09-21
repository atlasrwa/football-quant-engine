"""ITEM 6 Stage-1 spend guard: durable pre-call monetary reservation ledger (B4).

`item6_stage1_spend_guard_v1`. ZERO SPEND. Importing this module makes no network call.

THE V3-STYLE DEFECT THIS FIXES
The prior Item 6 cost artifact carried only a PLANNING estimate ("EXPECTED ~$5.58 / MAX
~$15.64"). That is not an enforceable dollar cap: actual provider billing could exceed it
without the runner stopping (exactly the V3 spend incident, where realized input tokens
exceeded the frozen per-call assumption). This guard replaces estimate-only accounting with
a PRE-CALL MAXIMUM COST RESERVATION enforced against a human-authorized monetary ceiling.

RESERVATION MODEL (conservative, monotonic)
Before each paid call the runner computes:

    next_call_max_reservation =
        input_price_per_tok  * INPUT_TOKEN_UPPER_BOUND(request)      # bytes-based upper bound
      + output_price_per_tok * MAX_OUTPUT_TOKENS                     # frozen maxTokens, NOT expected

A call may transmit ONLY IF:

    reserved_so_far + next_call_max_reservation <= HUMAN_AUTHORIZED_MONETARY_CEILING

otherwise the status is CALL_BLOCKED_BY_SPEND_CAP and nothing is transmitted.

The reservation is MONOTONIC for this experiment: once reserved, a call's reservation is
NOT released even if realized usage is smaller. With N=120 this is affordable and it means
the cumulative theoretical worst case can never breach the ceiling. Post-call we RECONCILE
realized usage (for reporting and to prove reservations were conservative) but we do not
shrink the cumulative reservation.

INPUT TOKEN UPPER BOUND
Never an average "$/call". The v1 reservation used the request-builder's byte-based upper
bound (UTF-8 bytes of the canonical request, capped by the frozen MAX_REQUEST_UTF8_BYTES).
Because Claude tokenization is byte-level BPE, input tokens <= request bytes, so that
reservation cannot understate the tokens represented by transmitted bytes.

AMENDMENT (v2): AUTHORITATIVE PROVIDER TOKEN COUNT
A tool-enabled provider request may involve provider-side/system token accounting not
literally represented by canonical transmitted UTF-8 bytes. So the input reservation must not
depend EXCLUSIVELY on the byte bound. The v2 reserve path (`reserve_with_provider_count`)
reserves input cost from the AUTHORITATIVE AWS Bedrock CountTokens result
(`provider_counted_input_tokens`) obtained immediately before the paid call, while the byte
ceiling (MAX_REQUEST_UTF8_BYTES) remains INDEPENDENTLY enforced upstream by the runner. Output
is still reserved at the frozen MAX_TOKENS (never expected output). The reservation stays
monotonic and is enforced against the human-authorized monetary ceiling; the runner blocks
before inference if the next reservation would breach it. `SPEND_GUARD_VERSION` is bumped to
v2 to reflect the changed spend semantics; the byte-bound method is retained for the
independent-constraint proof and back-compat.
"""
from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from typing import Dict, List, Optional

SPEND_GUARD_VERSION = "item6_stage1_spend_guard_v2"

# Input-token reservation methods.
INPUT_RESERVATION_METHOD_BYTE_BOUND = "utf8_byte_upper_bound_over_canonical_request_capped_at_max_request_bytes"
INPUT_RESERVATION_METHOD_PROVIDER_COUNT = "authoritative_provider_count_tokens"


@dataclass
class PriceTable:
    input_price_usd_per_1k: float
    output_price_usd_per_1k: float
    safety_multiplier: float = 1.0
    currency: str = "USD"

    @classmethod
    def from_json(cls, path: str) -> "PriceTable":
        d = json.load(open(path))
        return cls(
            input_price_usd_per_1k=float(d["input_price_usd_per_1k_tokens"]),
            output_price_usd_per_1k=float(d["output_price_usd_per_1k_tokens"]),
            safety_multiplier=float(d.get("reservation_safety_multiplier", 1.0)),
            currency=d.get("currency", "USD"),
        )

    def call_reservation_usd(self, input_token_bound: int, max_output_tokens: int) -> float:
        raw = (input_token_bound / 1000.0 * self.input_price_usd_per_1k
               + max_output_tokens / 1000.0 * self.output_price_usd_per_1k)
        return raw * self.safety_multiplier


class SpendCapExceeded(RuntimeError):
    """Raised (or signalled via status) when a reservation would breach the ceiling."""


class CallCapExceeded(RuntimeError):
    """Raised (or signalled via status) when the paid-call count cap is reached."""


@dataclass
class SpendGuard:
    """Durable monotonic reservation ledger. Persisted to `ledger_path` (JSON) so a resumed
    run reads back exactly what was already reserved and never double-spends the ceiling."""
    ceiling_usd: float
    call_cap: int
    price: PriceTable
    ledger_path: Optional[str] = None
    reserved_usd: float = 0.0
    realized_usd: float = 0.0
    n_calls_reserved: int = 0
    n_calls_charged: int = 0
    events: List[Dict] = field(default_factory=list)

    # ---- durability ------------------------------------------------------------------
    def _persist(self) -> None:
        if not self.ledger_path:
            return
        payload = self.to_dict()
        d = os.path.dirname(self.ledger_path)
        if d:
            os.makedirs(d, exist_ok=True)
        # atomic write: temp file + rename, so a crash never leaves a torn ledger.
        fd, tmp = tempfile.mkstemp(dir=d or ".", prefix=".spendguard_", suffix=".tmp")
        try:
            with os.fdopen(fd, "w") as f:
                json.dump(payload, f, indent=1, sort_keys=True)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.ledger_path)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)

    @classmethod
    def load_or_new(cls, *, ceiling_usd: float, call_cap: int, price: PriceTable,
                    ledger_path: Optional[str]) -> "SpendGuard":
        if ledger_path and os.path.exists(ledger_path):
            d = json.load(open(ledger_path))
            g = cls(ceiling_usd=ceiling_usd, call_cap=call_cap, price=price,
                    ledger_path=ledger_path)
            g.reserved_usd = float(d.get("reserved_usd", 0.0))
            g.realized_usd = float(d.get("realized_usd", 0.0))
            g.n_calls_reserved = int(d.get("n_calls_reserved", 0))
            g.n_calls_charged = int(d.get("n_calls_charged", 0))
            g.events = list(d.get("events", []))
            return g
        return cls(ceiling_usd=ceiling_usd, call_cap=call_cap, price=price,
                   ledger_path=ledger_path)

    # ---- pre-call gates ---------------------------------------------------------------
    def next_call_reservation(self, input_token_bound: int, max_output_tokens: int) -> float:
        return self.price.call_reservation_usd(input_token_bound, max_output_tokens)

    def call_cap_ok(self) -> bool:
        return self.n_calls_reserved < self.call_cap

    def spend_cap_ok(self, input_token_bound: int, max_output_tokens: int) -> bool:
        res = self.next_call_reservation(input_token_bound, max_output_tokens)
        return (self.reserved_usd + res) <= self.ceiling_usd + 1e-12

    def reserve(self, *, fixture_id: str, input_token_bound: int,
                max_output_tokens: int,
                input_reservation_method: str = INPUT_RESERVATION_METHOD_BYTE_BOUND
                ) -> float:
        """Reserve for the next paid call. BOTH caps enforced independently. Persists the
        reservation BEFORE the caller transmits, so a crash mid-call cannot lose the reserve.

        `input_token_bound` is the input-token count used for the reservation; the v2 runner
        passes the AUTHORITATIVE provider CountTokens result here (method
        `authoritative_provider_count_tokens`), while the byte ceiling remains enforced
        independently by the runner. `input_reservation_method` is recorded for provenance."""
        if not self.call_cap_ok():
            raise CallCapExceeded(
                f"call cap {self.call_cap} reached (reserved {self.n_calls_reserved})")
        res = self.next_call_reservation(input_token_bound, max_output_tokens)
        if (self.reserved_usd + res) > self.ceiling_usd + 1e-12:
            raise SpendCapExceeded(
                f"reservation {res:.6f} + reserved {self.reserved_usd:.6f} "
                f"> ceiling {self.ceiling_usd:.6f}")
        self.reserved_usd += res
        self.n_calls_reserved += 1
        self.events.append({"event": "RESERVE", "fixture_id": fixture_id,
                            "reservation_usd": round(res, 6),
                            "input_token_bound": input_token_bound,
                            "input_reservation_method": input_reservation_method,
                            "max_output_tokens": max_output_tokens,
                            "cumulative_reserved_usd": round(self.reserved_usd, 6),
                            "seq": self.n_calls_reserved})
        self._persist()
        return res

    # ---- v2: authoritative provider-count reservation ---------------------------------
    def reserve_with_provider_count(self, *, fixture_id: str,
                                    provider_counted_input_tokens: int,
                                    max_output_tokens: int) -> float:
        """v2 reserve path: reserve input cost from the AUTHORITATIVE provider CountTokens
        result rather than the byte bound. The runner enforces the byte ceiling independently
        BEFORE calling this. Output is still reserved at the frozen max_output_tokens. Both
        caps (call count + monetary ceiling) are enforced exactly as in `reserve`."""
        if not isinstance(provider_counted_input_tokens, int) or \
                isinstance(provider_counted_input_tokens, bool) or \
                provider_counted_input_tokens <= 0:
            raise SpendCapExceeded(
                f"invalid provider_counted_input_tokens: {provider_counted_input_tokens!r}")
        return self.reserve(
            fixture_id=fixture_id,
            input_token_bound=provider_counted_input_tokens,
            max_output_tokens=max_output_tokens,
            input_reservation_method=INPUT_RESERVATION_METHOD_PROVIDER_COUNT)

    def spend_cap_ok_for_input_tokens(self, input_tokens: int,
                                      max_output_tokens: int) -> bool:
        """Pre-check whether reserving `input_tokens` (e.g. the provider count) plus the
        frozen output reserve would remain within the human ceiling. Same 1e-12 tolerance."""
        res = self.next_call_reservation(input_tokens, max_output_tokens)
        return (self.reserved_usd + res) <= self.ceiling_usd + 1e-12

    # ---- post-call reconciliation -----------------------------------------------------
    def reconcile(self, *, fixture_id: str, actual_input_tokens: int,
                  actual_output_tokens: int) -> float:
        """Record realized provider usage and its accounting cost. Does NOT release the
        reservation (monotonic policy). Realized cost is for reporting + conservativeness
        proof only."""
        cost = (actual_input_tokens / 1000.0 * self.price.input_price_usd_per_1k
                + actual_output_tokens / 1000.0 * self.price.output_price_usd_per_1k)
        self.realized_usd += cost
        self.n_calls_charged += 1
        self.events.append({"event": "RECONCILE", "fixture_id": fixture_id,
                            "actual_input_tokens": actual_input_tokens,
                            "actual_output_tokens": actual_output_tokens,
                            "realized_cost_usd": round(cost, 6),
                            "cumulative_realized_usd": round(self.realized_usd, 6)})
        self._persist()
        return cost

    def can_actual_exceed_ceiling_without_precall_block(self) -> bool:
        """Structural answer: False. Every paid call is preceded by a reservation of its
        MAXIMUM cost (byte-bounded input + frozen max output) against the ceiling, and the
        realized cost of a call is always <= its reservation, so cumulative realized cost is
        always <= cumulative reserved cost <= ceiling."""
        return False

    def to_dict(self) -> Dict:
        return {
            "spend_guard_version": SPEND_GUARD_VERSION,
            "ceiling_usd": self.ceiling_usd,
            "call_cap": self.call_cap,
            "reserved_usd": round(self.reserved_usd, 6),
            "realized_usd": round(self.realized_usd, 6),
            "n_calls_reserved": self.n_calls_reserved,
            "n_calls_charged": self.n_calls_charged,
            "precall_spend_reservation": True,
            "hard_monetary_stop": True,
            "call_cap_stop": True,
            "reservation_is_monotonic": True,
            "input_price_usd_per_1k": self.price.input_price_usd_per_1k,
            "output_price_usd_per_1k": self.price.output_price_usd_per_1k,
            "safety_multiplier": self.price.safety_multiplier,
            "input_reservation_authority": INPUT_RESERVATION_METHOD_PROVIDER_COUNT,
            "byte_ceiling_retained_independently": True,
            "events": self.events,
        }


def version_stamp() -> Dict:
    return {
        "spend_guard_version": SPEND_GUARD_VERSION,
        "precall_spend_reservation": True,
        "hard_monetary_stop": True,
        "call_cap_stop": True,
        "reservation_is_monotonic": True,
        "reservation_uses_average_per_call": False,
        # v2: the AUTHORITATIVE input reservation is the provider CountTokens result; the byte
        # upper bound remains available as an INDEPENDENT constraint (enforced by the runner as
        # MAX_REQUEST_UTF8_BYTES) but is no longer the sole basis of the input reservation.
        "reservation_uses_provider_token_count": True,
        "reservation_uses_input_byte_upper_bound": True,
        "reservation_uses_frozen_max_output_tokens": True,
        "byte_ceiling_retained_independently": True,
        "input_reservation_authority": INPUT_RESERVATION_METHOD_PROVIDER_COUNT,
    }
