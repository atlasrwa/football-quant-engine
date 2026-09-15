"""Numerical-authority firewall, arm-neutral evidence provenance (`firewall_v3`).

`firewall_v2` is reused UNCHANGED for every classification decision. The only thing v3
changes is WHERE the supplied-evidence values come from: v2 reads `packet["evidence"]`, a
V3-shaped key, which in the aborted V5A returned 76 values for one arm and 0 for the other
and made the two arms' firewall-clean rates incomparable. v3 reads them through the common
evidence interface, so both arms are measured on the same scale.

`firewall_v2.py` is NOT modified: it is hashed into the frozen V3 and V5A preregistrations.
"""
from __future__ import annotations

from typing import Iterable, Optional

from src.research.hypothesis_engine import firewall, firewall_v2

FIREWALL_VERSION = "firewall_v3"

CLASS_A = firewall_v2.CLASS_A
ClassifiedViolation = firewall_v2.ClassifiedViolation
blocking = firewall_v2.blocking
suppressed = firewall_v2.suppressed


def evidence_values(packet: Optional[dict]) -> tuple:
    """Every numeric value the packet supplied, resolved arm-neutrally.

    Imported lazily so this module stays importable by the engine-side tests that do not
    depend on the oos packet builders.
    """
    from src.research.hypothesis_oos import v5a1_evidence as E
    return E.resolve_evidence_values(packet)


def scan(payload: dict, *, packet: Optional[dict] = None,
         evidence: Optional[Iterable[float]] = None,
         prose_fields: tuple = ("question",)) -> list:
    """All firewall layers, with arm-neutral provenance resolution.

    Structural layers and the latent-grading ban come from v1/v2 verbatim: a number in a
    structural field, a forbidden field name or an advantage grade is always class A and
    always blocking, whatever the packet contained.
    """
    out: list = []
    for v in firewall.scan_numerical_authority(payload):
        out.append(ClassifiedViolation(v.layer, v.path, v.kind, v.detail,
                                       CLASS_A, blocking=True))
    for v in firewall.scan_latent_grading(payload):
        out.append(ClassifiedViolation(v.layer, v.path, v.kind, v.detail,
                                       CLASS_A, blocking=True))

    ev = tuple(evidence) if evidence is not None else evidence_values(packet)
    nodes: list = []
    firewall._walk(payload, "$", nodes)
    for path, key, value in nodes:
        if key in prose_fields and isinstance(value, str):
            out.extend(firewall_v2.scan_prose(value, path, evidence=ev))
    return out


def version_stamp() -> dict:
    return {"firewall_version": FIREWALL_VERSION,
            "delegates_classification_to": firewall_v2.FIREWALL_VERSION
            if hasattr(firewall_v2, "FIREWALL_VERSION") else "firewall_v2",
            "evidence_resolution": "common evidence interface (arm-neutral)"}
