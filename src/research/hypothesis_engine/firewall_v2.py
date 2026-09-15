"""Numerical-authority firewall v2 (`numerical_authority_firewall_v2`) -- CLASSIFIED.

WHAT CHANGED, AND WHAT DELIBERATELY DID NOT
-------------------------------------------
The prohibition is NOT weakened. Every pattern in `firewall._PROSE_PATTERNS` is still
applied, the structural layers (`scan_numerical_authority`, `scan_latent_grading`) are
reused verbatim from v1, and probabilities, estimated percentage effects, odds, EV/edge,
stakes and latent advantage grades remain banned outright.

What changes is that a prose hit is now CLASSIFIED, because v1 conflated three things that
are scientifically different:

  A. GENERATED_NUMERIC -- the model produced a number carrying predictive authority: an
     effect size, a probability, an advantage estimate, an odds quote, an edge.
     This is the direct numerical-authority violation. BLOCKING.

  B. EVIDENCE_VALUE_REPRODUCTION -- the model copied a value it was SUPPLIED, in the
     evidence packet, into the question prose ("given their possession-for average of
     44.6%"). It asserted no effect and predicted nothing; it pointed at an observation
     through the only channel it had. This is still a discipline breach under the mandate
     ("not in a field, not in a question"), so it stays BLOCKING -- but it is bucketed
     separately, because the fix is architectural (give the model a structural evidence
     reference) rather than a matter of the model claiming authority it does not have.

  C. METRIC_LEXICAL -- the match is an artefact of an APPROVED METRIC NAME's lexical
     material, CARRIES NO NUMBER AT ALL, and is not any numerical claim. `big_chances` is in `capability.METRICS`, so a
     disciplined grounded question -- "Does the home team generate more big chances at
     home compared to its overall baseline?" -- trips v1's `probability_claim` pattern on
     the substring "chances at". This is instrumentation error, exactly analogous to the
     `\\bback\\b` / "back three" collision v1 already special-cased. It is SUPPRESSED: it
     is not a violation and never was.

C is suppressed by MASKING, not by a hand-written exception for "chances at". Every
approved metric name from `capability.METRICS` is masked out of the prose before the
patterns run, so any future metric whose name collides with trigger vocabulary is covered
by construction rather than by a patch after the fact.

A-vs-B IS A LABEL, NEVER A LICENCE
----------------------------------
The blocking decision is made WITHOUT the packet: any surviving prose match blocks. The
packet is consulted only to decide whether the number was one the model was handed (B) or
one it produced (A). A hit whose literals cannot be resolved against supplied evidence is
labelled A -- the conservative direction. `evidence_resolved` is reported per violation so
a fallback-A is always distinguishable from a positively-identified generated number.

Match semantics are identical to v1 (first match per pattern per field), so a v1-vs-v2
count difference is attributable to classification alone and to nothing else.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Optional

from . import capability, firewall

FIREWALL_VERSION = "numerical_authority_firewall_v2"


# --------------------------------------------------------------------------------------
# Classes
# --------------------------------------------------------------------------------------
CLASS_A = "A_GENERATED_NUMERIC"
CLASS_B = "B_EVIDENCE_VALUE_REPRODUCTION"
CLASS_C = "C_METRIC_LEXICAL"

#: Classes that reject the response. C is instrumentation error and does not.
BLOCKING_CLASSES = frozenset({CLASS_A, CLASS_B})


# --------------------------------------------------------------------------------------
# Class C: approved-metric lexical masking.
# --------------------------------------------------------------------------------------
#: A token with no word that any prose pattern keys on, and no digits. Substituted for an
#: approved metric name so the surrounding prose is still scanned normally.
_MASK = "METRICNAME"


def metric_lexical_phrases() -> tuple[str, ...]:
    """Every surface spelling of an approved metric name, longest first.

    Longest-first matters: `shots_on_target` must mask before `shots`, or the mask leaves
    "on target" stranded and a longer phrase can no longer be recognised.
    """
    phrases: set[str] = set()
    for name in capability.metric_names():
        phrases.add(name)
        phrases.add(name.replace("_", " "))
        phrases.add(name.replace("_", "-"))
    # Profile axes are metric names with a FOR/AGAINST suffix; their bare spellings are
    # already covered by the metric names above.
    return tuple(sorted(phrases, key=lambda p: (-len(p), p)))


_MASK_RX = re.compile(
    "|".join(re.escape(p) for p in metric_lexical_phrases()), re.IGNORECASE)


def mask_metric_lexicon(text: str) -> str:
    """Replace approved metric names with a neutral token.

    Everything else in the prose is left byte-identical. Masking alone is NOT sufficient
    to exempt a match: an approved metric name can also be the anchor of a genuine numeric
    claim ("+0.6 corners"), so `scan_prose` additionally requires a suppressed match to
    contain no numeric literal at all. See CLASS_C there.
    """
    return _MASK_RX.sub(_MASK, text or "")


# --------------------------------------------------------------------------------------
# Class A / B: does the literal resolve to a value the model was supplied?
# --------------------------------------------------------------------------------------
_NUM_RX = re.compile(r"\d+(?:\.\d+)?")


def evidence_values(packet: Optional[dict]) -> tuple[float, ...]:
    """Every numeric value the packet SUPPLIED to the model.

    Only `evidence[].value` is included. `sample_n` is deliberately excluded: a sample
    count is permitted structural metadata, never a quoted statistic, and including it
    widens the B-resolution surface with numbers no percentage could legitimately be.
    """
    if not packet:
        return ()
    out: list[float] = []
    for item in packet.get("evidence") or []:
        if isinstance(item, dict):
            v = item.get("value")
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                continue
            out.append(float(v))
    return tuple(out)


def _resolves(literal: str, values: tuple[float, ...]) -> bool:
    """Does a prose literal match a supplied evidence value AT ITS OWN PRECISION?

    "44.6" resolves against 44.6103 (the model rounded a value it was given). A BARE
    INTEGER does not resolve against 50.4552: "below 50%" is a domain constant a model can
    write with no evidence at all, and treating it as a supplied-value reproduction would
    mislabel a generated number as a copied one. A bare integer therefore has to BE the
    value, not a rounding of it.
    """
    try:
        x = float(literal)
    except ValueError:
        return False
    nd = len(literal.split(".")[1]) if "." in literal else 0
    tol = 0.05 if nd == 0 else 0.5 * (10.0 ** -nd)
    return any(abs(v - x) <= tol for v in values)


def _literals(fragment: str) -> tuple[str, ...]:
    return tuple(_NUM_RX.findall(fragment or ""))


# --------------------------------------------------------------------------------------
# Result type
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class ClassifiedViolation:
    layer: str
    path: str
    kind: str
    detail: str
    cls: str
    blocking: bool
    matched: str = ""
    #: A-vs-B provenance: True when every literal in the match was found in the packet's
    #: supplied evidence. False on an A assigned by fallback (no packet, or unresolvable).
    evidence_resolved: bool = False

    def to_dict(self) -> dict:
        return {"layer": self.layer, "path": self.path, "kind": self.kind,
                "class": self.cls, "blocking": self.blocking, "matched": self.matched,
                "evidence_resolved": self.evidence_resolved, "detail": self.detail}

    def __str__(self) -> str:
        return f"[{self.layer}/{self.cls}] {self.path}: {self.kind} -- {self.detail}"


def _classify_prose_match(matched: str, values: tuple[float, ...]) -> tuple[str, bool]:
    lits = _literals(matched)
    if lits and values and all(_resolves(l, values) for l in lits):
        return CLASS_B, True
    return CLASS_A, False


def scan_prose(text: str, path: str, *, packet: Optional[dict] = None,
               evidence: Optional[tuple] = None) -> list[ClassifiedViolation]:
    """Classified layer 3. Returns BOTH blocking (A/B) and suppressed (C) findings."""
    ev = evidence if evidence is not None else evidence_values(packet)
    raw = text or ""
    masked = mask_metric_lexicon(raw)

    out: list[ClassifiedViolation] = []
    for rx, label in firewall._COMPILED:
        raw_m = rx.search(raw)
        if not raw_m:
            continue
        masked_m = rx.search(masked)
        if not masked_m and not _literals(raw_m.group(0)):
            # The match carried NO number and disappears once approved metric names are
            # masked: it existed only because a metric name supplied the trigger
            # vocabulary. Instrumentation error, not a violation.
            out.append(ClassifiedViolation(
                "PROSE", path, label,
                f"matched {raw_m.group(0)!r}, but the match carries no number and is "
                f"entirely explained by an approved metric name from the capability "
                f"inventory; suppressed as instrumentation error",
                CLASS_C, blocking=False, matched=raw_m.group(0)))
            continue
        # A match that contains a NUMERIC LITERAL is never metric-lexical, even if the
        # metric name is what let the pattern anchor. "+0.6 corners" is an effect size
        # whether or not `corners` is an approved metric, so it is classified on the RAW
        # match and masking is not allowed to exempt it.
        effective = masked_m or raw_m
        cls, resolved = _classify_prose_match(effective.group(0), ev)
        detail = (f"matched {effective.group(0)!r}; "
                  + ("this reproduces a value supplied in the evidence packet -- a "
                     "question must reference evidence by id, never by copying its "
                     "number into prose"
                     if cls == CLASS_B else
                     "a question may not carry a predictive number, price, edge or "
                     "recommendation"))
        out.append(ClassifiedViolation(
            "PROSE", path, label, detail, cls, blocking=True,
            matched=effective.group(0), evidence_resolved=resolved))
    return out


def scan(payload: dict, *, packet: Optional[dict] = None,
         prose_fields: tuple[str, ...] = ("question",)) -> list[ClassifiedViolation]:
    """All layers, classified.

    Structural layers 1-2 and the latent-grading ban are reused from v1 unchanged: a
    number in a structural field, a forbidden field name or an advantage grade is always
    class A and always blocking. There is no lexical ambiguity to resolve there -- the
    schema is closed, so the field either exists legitimately or does not exist.
    """
    out: list[ClassifiedViolation] = []
    for v in firewall.scan_numerical_authority(payload):
        out.append(ClassifiedViolation(v.layer, v.path, v.kind, v.detail,
                                       CLASS_A, blocking=True))
    for v in firewall.scan_latent_grading(payload):
        out.append(ClassifiedViolation(v.layer, v.path, v.kind, v.detail,
                                       CLASS_A, blocking=True))

    ev = evidence_values(packet)
    nodes: list = []
    firewall._walk(payload, "$", nodes)
    for path, key, value in nodes:
        if key in prose_fields and isinstance(value, str):
            out.extend(scan_prose(value, path, evidence=ev))
    return out


def blocking(violations: Iterable[ClassifiedViolation]) -> list[ClassifiedViolation]:
    return [v for v in violations if v.blocking]


def suppressed(violations: Iterable[ClassifiedViolation]) -> list[ClassifiedViolation]:
    return [v for v in violations if not v.blocking]


def classification_counts(violations: Iterable[ClassifiedViolation]) -> dict:
    counts = {CLASS_A: 0, CLASS_B: 0, CLASS_C: 0}
    for v in violations:
        counts[v.cls] = counts.get(v.cls, 0) + 1
    return counts


def version_stamp() -> dict:
    return {
        "firewall_version": FIREWALL_VERSION,
        "inherits_from": firewall.FIREWALL_VERSION,
        "n_prose_patterns": len(firewall._COMPILED),
        "classes": [CLASS_A, CLASS_B, CLASS_C],
        "blocking_classes": sorted(BLOCKING_CLASSES),
        "capability_inventory_version": capability.CAPABILITY_INVENTORY_VERSION,
    }
