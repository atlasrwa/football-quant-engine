"""Leakage guard for the fixture-context packet (`hypothesis_leakage_guard_v1`).

Runs on the packet BEFORE transmission and on the response AFTER receipt.

WHAT COUNTS AS LEAKAGE HERE
---------------------------
The hypothesis layer sits upstream of the probability engine, so the leakage surface is
different from the champion's. Three classes must never reach the model:

  1. FUTURE INFORMATION about the target fixture -- any evidence item whose observation
     time is at or after kickoff. The target fixture's own result is the extreme case, but
     a post-kickoff rolling value is equally disqualifying.

  2. MARKET INFORMATION -- odds, implied probabilities, closing lines, price movement.
     Not because it is unavailable, but because the whole scientific point is that the
     hypothesis layer proposes measurements from FOOTBALL evidence, and the market
     comparison happens far downstream in the quant engine. A hypothesis generated with
     sight of the price is no longer an independent research proposal.

  3. SETTLEMENT INFORMATION -- results, win/loss, settled statistics, CLV.

A packet failing any check is never transmitted: the call is refused, not censored and
sent anyway, so no partially-clean request can reach a paid endpoint.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

LEAKAGE_GUARD_VERSION = "hypothesis_leakage_guard_v1"


#: Field-name fragments that denote market or settlement information. Matched against KEYS
#: anywhere in the packet, case-insensitively, on word-ish boundaries.
_FORBIDDEN_KEY_FRAGMENTS = (
    "odds", "price", "bookmaker", "bookie", "implied_prob", "overround", "vig", "devig",
    "closing", "close_line", "closing_line", "clv", "market_prob", "p_market",
    "settlement", "settled", "result", "winner", "winning_team", "outcome",
    "final_score", "fulltime", "full_time_goals", "ft_goals",
    "profit", "pnl", "roi", "stake", "payout",
    "p_model", "model_probability", "forecast", "prediction", "commitment",
)

#: Prose shapes that reveal a market or a settled outcome inside a free-text value.
_FORBIDDEN_TEXT_PATTERNS = (
    (r"\b(?:closing|opening)\s+(?:line|price|odds)\b", "closing_line_text"),
    (r"\b(?:settled|final)\s+(?:result|score|outcome)\b", "settlement_text"),
    (r"\bmatch\s+(?:ended|finished)\b", "settlement_text"),
    (r"\b(?:won|lost)\s+(?:the\s+)?(?:bet|market)\b", "settlement_text"),
    (r"\bimplied\s+probabilit", "market_text"),
    (r"\b\d+\.\d{2}\s*(?:@|on)\s*(?:pinnacle|betfair|bet365|williamhill)\b", "market_text"),
)

_COMPILED_TEXT = tuple(
    (re.compile(p, re.IGNORECASE), label) for p, label in _FORBIDDEN_TEXT_PATTERNS)


@dataclass(frozen=True)
class LeakageFinding:
    kind: str
    path: str
    detail: str

    def __str__(self) -> str:
        return f"{self.kind} at {self.path}: {self.detail}"


class LeakageRejected(Exception):
    """Raised instead of transmitting. Named for lifecycle.LEAKAGE_REJECTED."""

    def __init__(self, findings: list[LeakageFinding]):
        self.findings = findings
        super().__init__(f"{len(findings)} leakage finding(s): "
                         + "; ".join(str(f) for f in findings[:5]))


def _walk(obj, path, out):
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append((f"{path}.{k}", k, v))
            _walk(v, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.append((f"{path}[{i}]", None, v))
            _walk(v, f"{path}[{i}]", out)


def _key_is_forbidden(key: str) -> str | None:
    low = key.lower()
    for frag in _FORBIDDEN_KEY_FRAGMENTS:
        if frag in low:
            return frag
    return None


def audit_packet(packet: dict, *, cutoff_unix: int | None = None) -> list[LeakageFinding]:
    """Full pre-transmission audit. Returns every finding; empty means clean."""
    findings: list[LeakageFinding] = []
    nodes: list = []
    _walk(packet, "$", nodes)

    cutoff = cutoff_unix
    if cutoff is None:
        cutoff = packet.get("information_cutoff_unix")

    for path, key, value in nodes:
        if key:
            frag = _key_is_forbidden(key)
            if frag:
                findings.append(LeakageFinding(
                    "MARKET_OR_SETTLEMENT_FIELD", path,
                    f"key {key!r} contains forbidden fragment {frag!r}"))

        if isinstance(value, str):
            for rx, label in _COMPILED_TEXT:
                m = rx.search(value)
                if m:
                    findings.append(LeakageFinding(
                        "FORBIDDEN_TEXT", path, f"{label}: matched {m.group(0)!r}"))

    # Temporal check: no evidence item may be observed at or after the cutoff.
    if cutoff is not None:
        for item in packet.get("evidence", []) or []:
            eid = item.get("id", "<no-id>")
            for tkey in ("max_source_time_unix", "observed_at_unix", "cutoff_unix"):
                tval = item.get(tkey)
                if isinstance(tval, (int, float)) and tval > cutoff:
                    findings.append(LeakageFinding(
                        "FUTURE_INFORMATION", f"$.evidence[{eid}].{tkey}",
                        f"{tkey}={tval} is after information_cutoff_unix={cutoff}"))
            if item.get("temporal_status") not in (None, "PIT_SAFE", "UNAVAILABLE"):
                findings.append(LeakageFinding(
                    "FUTURE_INFORMATION", f"$.evidence[{eid}].temporal_status",
                    f"temporal_status={item.get('temporal_status')!r} is not PIT_SAFE"))

    return findings


def assert_packet_clean(packet: dict, *, cutoff_unix: int | None = None) -> None:
    """Refuse transmission on any finding. This is the pre-spend gate."""
    findings = audit_packet(packet, cutoff_unix=cutoff_unix)
    if findings:
        raise LeakageRejected(findings)


def audit_serialized_request(text: str) -> list[LeakageFinding]:
    """Audit the LITERAL serialized request text, after every transform.

    Carried over in spirit from the legacy `audit_request.py`, which scanned the actual
    bytes rather than the Python object. A transform that reintroduces a forbidden token
    during serialization is invisible to an object-level audit.
    """
    findings: list[LeakageFinding] = []
    low = text.lower()
    for frag in _FORBIDDEN_KEY_FRAGMENTS:
        idx = low.find(f'"{frag}')
        if idx >= 0:
            findings.append(LeakageFinding(
                "MARKET_OR_SETTLEMENT_FIELD", f"serialized@{idx}",
                f"serialized request contains field-like token {frag!r}"))
    for rx, label in _COMPILED_TEXT:
        m = rx.search(text)
        if m:
            findings.append(LeakageFinding(
                "FORBIDDEN_TEXT", f"serialized@{m.start()}",
                f"{label}: matched {m.group(0)!r}"))
    return findings
