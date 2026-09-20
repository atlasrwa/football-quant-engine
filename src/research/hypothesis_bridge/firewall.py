"""The numerical firewall -- ONE place, both directions.

The LLM may propose WHAT to measure. It may never supply a number that is, or trivially
becomes, a prediction: probability, edge, EV, odds, stake, effect size, latent score.

Both directions live here deliberately. If the inbound allow-list lived in the canonicalizer
and the outbound deny-list lived in the record builder, a third path could add a field and
both checks would still pass. Every crossing goes through this module.
"""
from __future__ import annotations

import re

#: Inbound: the ONLY keys a proposal may carry. Allow-list, not deny-list -- an unknown key
#: is refused rather than ignored, so a new prediction-shaped field cannot arrive silently.
ALLOWED_PROPOSAL_FIELDS = frozenset({
    "fixture_id", "subject", "target_metric", "perspective", "comparator",
    "conditions", "window", "similar_opponent_intent", "research_reason", "evidence_refs",
})

#: Outbound and inbound: names that carry predictive meaning. Matched on normalised tokens,
#: so `p_model`, `pModel`, `model-probability` and `expected_value` all resolve.
PROHIBITED_TOKENS = frozenset({
    "probability", "prob", "pmodel", "p", "edge", "ev", "expectedvalue", "odds", "price",
    "stake", "kelly", "bankroll", "effectsize", "effect", "advantage", "score", "rating",
    "confidence", "likelihood", "payout", "roi", "yield", "margin", "vig", "overround",
})

_SPLIT = re.compile(r"[^a-z0-9]+")


def _tokens(name: str) -> set[str]:
    """Normalise a field name to comparable forms.

    Returns the individual tokens AND the separator-stripped whole, because a prohibited
    concept can be spelled either way: `ev` is one token, while `expected_value` splits into
    two harmless-looking ones and is only recognisable once rejoined as `expectedvalue`.
    Both forms are compared, so neither spelling slips through.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", str(name))
    parts = {t for t in _SPLIT.split(spaced.lower()) if t}
    return parts | {"".join(sorted(parts)), "".join(_SPLIT.split(spaced.lower()))}


class FirewallViolation(ValueError):
    """A prediction-shaped value tried to cross the research boundary."""


def prohibited_fields(payload, _path: str = "") -> list[str]:
    """Every path in `payload` whose key carries predictive meaning. Recurses."""
    hits: list[str] = []
    if isinstance(payload, dict):
        for k, v in payload.items():
            here = f"{_path}.{k}" if _path else str(k)
            if _tokens(k) & PROHIBITED_TOKENS:
                hits.append(here)
            hits.extend(prohibited_fields(v, here))
    elif isinstance(payload, (list, tuple)):
        for i, v in enumerate(payload):
            hits.extend(prohibited_fields(v, f"{_path}[{i}]"))
    return hits


def check_inbound(raw: dict) -> list[str]:
    """Problems with an incoming proposal. Empty list means it may proceed.

    Two independent refusals: a key outside the allow-list, and a key that is
    prediction-shaped. The second is reported even for an allowed key, so a field cannot be
    smuggled in under an approved name's sub-structure.
    """
    problems = []
    for k in sorted(raw):
        if k not in ALLOWED_PROPOSAL_FIELDS:
            problems.append(f"field_not_allowed:{k}")
    for path in sorted(prohibited_fields(raw)):
        problems.append(f"prediction_field:{path}")
    return problems


def assert_outbound_clean(record: dict) -> None:
    """A shadow record must carry no predictive quantity. Raises rather than returns.

    This is the last gate before a record is persisted, so it fails loudly: a record that
    reached storage carrying an edge or a probability would be indistinguishable from a
    legitimate one afterwards.
    """
    hits = prohibited_fields(record)
    if hits:
        raise FirewallViolation(
            "shadow record carries prediction-shaped field(s): " + ", ".join(sorted(hits)))
