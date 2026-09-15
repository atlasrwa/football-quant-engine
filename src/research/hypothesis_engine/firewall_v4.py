"""Numerical-authority firewall for V5A.2 (`firewall_v4`).

Every layer, every pattern and every classification is `firewall_v3`'s, reused unchanged.
This module ADDS prose patterns and removes none.

WHY IT EXISTS -- defect D5, found by the generated negative battery
-------------------------------------------------------------------
The frozen prose patterns catch a probability written as

    "probability of 0.62"        -> probability_claim

because the pattern is `(?:probabilit|likelihood|chance|odds)\\w*\\s+(?:of|is|are|at)`.
They do NOT catch the same claim written the other way round:

    "There is a 0.62 probability the subject exceeds its baseline."

The noun is followed by `the`, not by `of|is|are|at`, and no other pattern matches a bare
decimal next to a probability noun. `question` is the ONLY free-text field in the schema and
therefore the only place a number can appear at all, so this was the single surface the
firewall exists to cover, with a hole in it. It has been present since V2 and was never
exercised because no hand-written test phrased a probability that way. The generated battery
phrased it that way on the first pass.

This is a TIGHTENING, never a loosening: `firewall_v3`'s verdict is taken as-is and these
patterns can only add violations. Both violation classes already block, so no response that
V5A.1 would have rejected becomes acceptable here.

`firewall.py`, `firewall_v2.py` and `firewall_v3.py` are NOT edited -- their hashes are in
the frozen V2/V3/V5A preregistrations.
"""
from __future__ import annotations

import re

from . import firewall, firewall_v2, firewall_v3

CLASS_A = firewall_v2.CLASS_A
ClassifiedViolation = firewall_v2.ClassifiedViolation
suppressed = firewall_v2.suppressed

FIREWALL_VERSION = "firewall_v4"

#: Deliberately narrow. Each requires a NUMBER adjacent to a probability noun; a question
#: that merely uses the word "chance" in passing is untouched, and a question containing no
#: number at all can never match. The schema has no numeric field, so a number in prose is
#: already anomalous.
_ADDITIONAL_PROSE_PATTERNS: tuple = (
    # "0.62 probability", "62% likelihood", "3 in 10 chance"
    (r"\d+(?:\.\d+)?\s*(?:%|percent)?\s*(?:probabilit|likelihood|chance)\w*\b",
     "probability_claim"),
    # "probability the subject exceeds ... 0.62" -- noun first, number close behind
    (r"\b(?:probabilit|likelihood|chance|odds)\w*\b[^.;]{0,32}?\d+\.\d+",
     "probability_claim"),
    # a bare 0-1 decimal offered as the answer: "is 0.62", "= .62", "around 0.62"
    (r"\b(?:is|equals?|=|around|about|approximately|roughly)\s*0?\.\d+\b",
     "bare_probability_value"),
)

_COMPILED = tuple((re.compile(p, re.IGNORECASE), label)
                  for p, label in _ADDITIONAL_PROSE_PATTERNS)

#: Exported so the audit can prove v4 is a superset of v3 rather than a rewrite.
ADDED_PATTERN_LABELS = tuple(sorted({lbl for _, lbl in _ADDITIONAL_PROSE_PATTERNS}))


def scan_prose_additional(text: str, path: str, evidence: tuple = ()) -> list:
    """Classified exactly the way `firewall_v2.scan_prose` classifies its own matches.

    The A/B split is delegated to `firewall_v2._classify_prose_match`, not re-decided here,
    so a number that merely reproduces a packet value is labelled B (evidence reproduction)
    rather than A (generated numeric). BOTH classes block, so the label changes the audit
    record and not the enforcement -- but an audit that mislabels its own findings is worth
    less than one that does not.
    """
    raw = text or ""
    masked = firewall_v2.mask_metric_lexicon(raw)
    out = []
    for rx, label in _COMPILED:
        raw_m = rx.search(raw)
        if not raw_m:
            continue
        effective = rx.search(masked) or raw_m
        cls, resolved = firewall_v2._classify_prose_match(effective.group(0), evidence)
        detail = (f"matched {effective.group(0)!r}; "
                  + ("this reproduces a value supplied in the evidence packet -- a "
                     "question must reference evidence by id, never by copying its number "
                     "into prose"
                     if cls == firewall_v2.CLASS_B else
                     "a question may not carry a predictive number, price, edge or "
                     "recommendation"))
        out.append(ClassifiedViolation("PROSE", path, label, detail, cls, blocking=True,
                                       matched=effective.group(0),
                                       evidence_resolved=resolved))
    return out


def _questions(payload) -> list:
    out = []
    for i, h in enumerate((payload or {}).get("hypotheses") or []):
        if isinstance(h, dict) and isinstance(h.get("question"), str):
            out.append((f"$.hypotheses[{i}].question", h["question"]))
    return out


def scan(payload, *, packet=None, evidence=None, prose_fields: tuple = ("question",)) -> list:
    """`firewall_v3.scan` plus the additional prose patterns. Strictly additive.

    The same resolved evidence tuple is used for both halves, so v3's findings and v4's
    are classified against an identical notion of "a value the packet supplied".
    """
    ev = tuple(evidence) if evidence is not None else firewall_v3.evidence_values(packet)
    findings = list(firewall_v3.scan(payload, packet=packet, evidence=ev,
                                     prose_fields=prose_fields))
    for path, text in _questions(payload):
        findings.extend(scan_prose_additional(text, path, evidence=ev))
    return findings


def blocking(findings) -> list:
    """Classification is delegated: a PROSE violation blocks in v3, so it blocks here."""
    return firewall_v3.blocking(findings)


def version_stamp() -> dict:
    return {**firewall_v3.version_stamp(),
            "firewall_version": FIREWALL_VERSION,
            "added_prose_pattern_labels": list(ADDED_PATTERN_LABELS),
            "is_strict_superset_of": firewall_v3.FIREWALL_VERSION
            if hasattr(firewall_v3, "FIREWALL_VERSION") else "firewall_v3"}
