"""Numerical-authority firewall (`numerical_authority_firewall_v1`).

    The LLM proposes what to measure. It does not own any downstream numerical conclusion.

WHAT THIS BLOCKS AND WHY IT IS NOT A KEYWORD FILTER
---------------------------------------------------
Mandate §15: "Do not merely keyword-match prose if a stronger schema/semantic validator is
possible." So the firewall runs in three layers, strongest first:

  1. STRUCTURAL (authoritative). The hypothesis schema is closed
     (`additionalProperties: false`) and every value-bearing field is an enum, an id, or a
     bounded string. A probability therefore has NOWHERE to live: a float cannot be
     attached to any field, and an unknown field is a schema rejection before this module
     is reached. This is the real defence -- layers 2 and 3 exist because the free-text
     `question` field is the one place a model could still smuggle a number in prose.

  2. SEMANTIC-FIELD. Any float/int appearing anywhere in the payload outside an explicitly
     allow-listed structural field is a violation, regardless of what it is called. This
     catches `"delta": 4.2` as surely as `"probability": 0.617`, without needing to have
     predicted the field name.

  3. PROSE. Inside the free-text `question` (and only there), detect the semantic shapes of
     predictive authority: a percentage, a percentage-point adjustment, a decimal/fractional
     odds quote, a money line, an EV/edge/stake claim, or an explicit outcome-likelihood
     statement. Bare integers survive (a question may legitimately say "back-three" or
     "last 5 matches"); a number carrying predictive authority does not.

The ban is on PREDICTIVE NUMERICAL AUTHORITY, not on numbers. Structural metadata --
ids, window labels, sample counts supplied as evidence metadata, timestamps, provenance --
is explicitly permitted and enumerated below.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import vocabulary

FIREWALL_VERSION = "numerical_authority_firewall_v1"


# --------------------------------------------------------------------------------------
# Layer 2: structural fields in which a number is legitimate.
#
# Anything NOT on this list may not carry a numeric value anywhere in the payload.
# --------------------------------------------------------------------------------------
NUMERIC_ALLOWED_FIELDS = frozenset({
    "information_cutoff_unix",   # provenance timestamp, injected by the engine
    "generated_at_unix",         # provenance timestamp
    "schema_version_int",        # structural version counter
})

#: Schema-legitimate paths whose LEAF NAME collides with a forbidden concept name.
#:
#: `conditions[].value` is the cohort band a question is conditioned on ("HIGH" for the
#: opponent-profile axis). Its leaf name collides with "value" in the betting sense, which
#: is on the forbidden list. The collision is safe to exempt because the schema is closed:
#: the ONLY `value` field that can exist anywhere in a response is this one, and any other
#: would be rejected as an unknown field before the firewall runs.
#:
#: Compared against the path with list indices removed, so it matches at any depth.
_FIELD_NAME_EXEMPT_PATHS = frozenset({
    "$.hypotheses.conditions.value",
})


def _depath(path: str) -> str:
    return re.sub(r"\[\d+\]", "", path)


#: Field names whose value is a forbidden CONCEPT even when non-numeric ("edge": "large").
#: Present as a belt-and-braces check; the closed schema already rejects unknown fields.
FORBIDDEN_FIELD_NAMES = frozenset({
    "probability", "probabilities", "p", "p_model", "p_market", "prob", "probs",
    "model_probability", "expected_probability", "fair_probability", "implied_probability",
    "probability_adjustment", "prob_adjustment", "adjustment", "delta_pp", "pp",
    "edge", "edges", "value", "ev", "expected_value", "expected_events",
    "odds", "fair_odds", "price", "prices", "bookmaker_odds", "line_price",
    "stake", "bet", "bets", "selection", "pick", "recommendation", "wager",
    "confidence_pct", "confidence_percent", "likelihood", "chance",
    "model_score", "score_adjustment", "strength", "rating", "advantage",
    "expected_goals_prediction", "predicted_corners", "prediction", "forecast",
})


# --------------------------------------------------------------------------------------
# Layer 3: prose shapes carrying predictive authority.
# --------------------------------------------------------------------------------------
_PROSE_PATTERNS: tuple[tuple[str, str], ...] = (
    # a percentage of any precision: "61.7%", "55 %"
    (r"\d+(?:\.\d+)?\s*%", "percentage"),
    # percentage points, the model-market gap unit
    (r"\d+(?:\.\d+)?\s*(?:pp|percentage[ -]points?|pct[ -]points?)\b", "percentage_points"),
    # decimal odds quoted against a market: "at 1.85", "@ 2.30", "odds of 1.71"
    (r"(?:@|\bat\b|\bodds?\s+of\b|\bpriced\s+at\b)\s*\d+\.\d+", "decimal_odds"),
    # fractional odds: "5/2", "11/4"
    (r"\b\d{1,3}\s*/\s*\d{1,3}\b(?=\s*(?:odds|price|shot)?)", "fractional_odds"),
    # american odds: "+150", "-220"
    (r"(?<![\w.])[+-]\d{3,4}(?![\w.%])", "american_odds"),
    # an explicit probability statement in words
    (r"\b(?:probabilit|likelihood|chance|odds)\w*\s+(?:of|is|are|at)\b", "probability_claim"),
    (r"\b(?:expected value|EV|edge|overlay|value bet|fair (?:odds|price|probability))\b",
     "ev_or_edge_claim"),
    (r"\b(?:stake|bankroll|kelly|unit size|bet size)\b", "stake_claim"),
    # NB "back" alone is core football vocabulary ("back three", "back four", "back line"),
    # so a bare \bback\b would reject legitimate formation questions. Only the betting
    # senses are matched: an explicit bet verb, or "back(ing) the <market side>".
    (r"\b(?:lay\s+the|bet\s+on|place\s+a\s+bet|recommend(?:ing)?\s+(?:a\s+)?bet)\b",
     "bet_recommendation"),
    (r"\bback(?:ing)?\s+(?:the\s+)?"
     r"(?:over|under|draw|btts|favou?rite|underdog|home\s+win|away\s+win)\b",
     "bet_recommendation"),
    # a numeric prediction of an event count presented as a forecast
    (r"\b(?:expect|predict|project|forecast)\w*\s+(?:about\s+|around\s+|~\s*)?\d+(?:\.\d+)?",
     "numeric_forecast"),
    # over/under with a line, which is a market position rather than a question
    (r"\b(?:over|under)\s*\d+\.\d\b", "market_line_position"),
    # a bare decimal used as a magnitude claim: "+0.6 corners", "1.3 more shots"
    (r"[+-]?\d+\.\d+\s*(?:more|fewer|additional|extra)?\s*"
     r"(?:corners?|shots?|goals?|cards?|bookings?|tackles?|fouls?|crosses)\b",
     "numeric_effect_size"),
)

_COMPILED = tuple((re.compile(p, re.IGNORECASE), label) for p, label in _PROSE_PATTERNS)


@dataclass(frozen=True)
class Violation:
    layer: str          # "FIELD" | "NUMERIC" | "PROSE" | "GRADE"
    path: str
    kind: str
    detail: str

    def __str__(self) -> str:
        return f"[{self.layer}] {self.path}: {self.kind} -- {self.detail}"


def _walk(obj, path, out):
    """Yield (path, key, value) for every leaf and every dict key in the payload."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append((f"{path}.{k}", k, v))
            _walk(v, f"{path}.{k}", out)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.append((f"{path}[{i}]", None, v))
            _walk(v, f"{path}[{i}]", out)


def scan_numerical_authority(payload: dict) -> list[Violation]:
    """Layers 1-2: forbidden field names, and numbers outside allow-listed fields."""
    violations: list[Violation] = []
    nodes: list = []
    _walk(payload, "$", nodes)

    for path, key, value in nodes:
        if (key is not None and key.lower() in FORBIDDEN_FIELD_NAMES
                and _depath(path) not in _FIELD_NAME_EXEMPT_PATHS):
            violations.append(Violation(
                "FIELD", path, "forbidden_field",
                f"field {key!r} names a quantity the quant engine owns; the LLM may not "
                f"supply it"))
            continue
        if isinstance(value, bool):
            continue                      # bool is not a magnitude
        if isinstance(value, (int, float)):
            leaf = path.rsplit(".", 1)[-1]
            if leaf not in NUMERIC_ALLOWED_FIELDS:
                violations.append(Violation(
                    "NUMERIC", path, "numeric_value_outside_allowlist",
                    f"numeric {value!r} is not permitted here; the deterministic engine "
                    f"computes every magnitude. Allowed numeric fields: "
                    f"{sorted(NUMERIC_ALLOWED_FIELDS)}"))
    return violations


def scan_prose(text: str, path: str) -> list[Violation]:
    """Layer 3: predictive-authority shapes inside a free-text field."""
    violations: list[Violation] = []
    for rx, label in _COMPILED:
        m = rx.search(text or "")
        if m:
            violations.append(Violation(
                "PROSE", path, label,
                f"matched {m.group(0)!r}; a question may not carry a predictive number, "
                f"price, edge or recommendation"))
    return violations


def scan_latent_grading(payload: dict) -> list[Violation]:
    """Mandate §14: no ordinal grading of football strength or matchup advantage.

    A LOW/MEDIUM/HIGH token is legitimate in `priority` (a research-budget hint) and a
    LOW/MID/HIGH band is legitimate as a cohort `value` (naming which opponents to
    measure). Everywhere else it is the legacy latent-state grade and is rejected.
    """
    violations: list[Violation] = []
    nodes: list = []
    _walk(payload, "$", nodes)

    for path, key, value in nodes:
        if not isinstance(value, str):
            continue
        token = value.strip().upper()
        leaf = path.rsplit(".", 1)[-1]

        if token in vocabulary.BANNED_ADVANTAGE_GRADES:
            violations.append(Violation(
                "GRADE", path, "advantage_grade",
                f"{value!r} is a latent matchup-advantage grade. The LLM asks whether an "
                f"effect exists; the deterministic engine measures its direction and size."))
            continue

        if token in vocabulary.BANNED_LEVEL_GRADES:
            if leaf in vocabulary.GRADE_EXEMPT_FIELDS:
                continue
            # Compare on the index-stripped path: a cohort BAND ("HIGH" on an
            # opponent-profile axis) names which opponents to measure, and is not a grade
            # of anyone's strength. A team-strength grade lives in a different field.
            if any(_depath(path).endswith(sfx)
                   for sfx in vocabulary.BAND_EXEMPT_PATH_SUFFIXES):
                continue
            violations.append(Violation(
                "GRADE", path, "level_grade",
                f"{value!r} is a latent strength grade outside an exempt field "
                f"({sorted(vocabulary.GRADE_EXEMPT_FIELDS)}). Ask the question; do not "
                f"grade the answer."))
    return violations


def scan(payload: dict, prose_fields: tuple[str, ...] = ("question",)) -> list[Violation]:
    """Run all layers. Returns every violation found -- the caller rejects the WHOLE
    response on any non-empty result (no salvage)."""
    violations = scan_numerical_authority(payload)
    violations.extend(scan_latent_grading(payload))

    nodes: list = []
    _walk(payload, "$", nodes)
    for path, key, value in nodes:
        if key in prose_fields and isinstance(value, str):
            violations.extend(scan_prose(value, path))
    return violations


def assert_clean(payload: dict) -> None:
    """Raise on any violation. Used where a caller wants fail-fast rather than a report."""
    v = scan(payload)
    if v:
        raise NumericalAuthorityViolation(v)


class NumericalAuthorityViolation(Exception):
    def __init__(self, violations: list[Violation]):
        self.violations = violations
        super().__init__(
            f"{len(violations)} numerical-authority violation(s): "
            + "; ".join(str(x) for x in violations[:5]))
