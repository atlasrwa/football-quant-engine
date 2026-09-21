"""ANTI-IMITATION tests. Fail if the frozen Stage-1 prompt anchors generation with a concrete
worked football hypothesis / metric pair / opponent-profile example / example candidate_id /
attack-vs-concession template instantiated with a real metric.

These enforce KEY DESIGN CHANGE #1 (no worked football example in the scientific prompt).
"""
from __future__ import annotations

import re

PROMPT = "/home/ubuntu/research/item6/ITEM6_MECHANISM_PROMPT_V1.md"


def _prompt_text() -> str:
    """Return ONLY the model-facing prompt body (between PROMPT_BODY markers). The text
    outside the markers is documentation the model never sees; the anti-imitation guarantees
    apply to exactly what is sent to the model."""
    with open(PROMPT) as f:
        full = f.read()
    start = full.index("PROMPT_BODY_START")
    end = full.index("PROMPT_BODY_END")
    body = full[start:end]
    assert start < end, "prompt body markers malformed"
    return body


# Concrete provider metric names that must NOT appear as an instantiated worked example.
# We allow the abstract word "observable" but not a specific metric like "corner_kicks".
CONCRETE_METRICS = [
    "corner_kicks", "corners", "shots_on_target", "shots on target", "big_chances",
    "big chances", "accurate_crosses", "crosses", "possession", "tackles", "fouls",
    "yellow_cards", "interceptions", "clearances", "touches_in_penalty_area",
    "shots_against", "goals_for", "goals_against",
]


def test_prompt_has_no_concrete_metric_pair():
    text = _prompt_text().lower()
    # No two distinct concrete metrics co-occurring in a single sentence would already be a
    # worked pair; stricter: no concrete metric token appears AT ALL as an example.
    hits = [m for m in CONCRETE_METRICS if re.search(rf"(^|[^a-z_]){re.escape(m)}([^a-z_]|$)", text)]
    assert not hits, f"prompt contains concrete metric tokens (worked-example anchoring): {hits}"


def test_prompt_has_no_example_candidate_id():
    text = _prompt_text()
    # candidate ids in this codebase look like mt_..., i6_..., or hex ir ids. The only allowed
    # placeholder is the literal <id>. Reject concrete ids.
    assert not re.search(r"\bmt_\d", text), "prompt contains a concrete mt_ candidate id"
    assert not re.search(r"\bi6_\d", text), "prompt contains a concrete i6_ fixture id"
    assert not re.search(r"\bcandidate_id\s*[:=]\s*\"?[0-9a-f]{6}", text), \
        "prompt contains a concrete candidate_id value"


def test_prompt_has_no_worked_attack_vs_concession_template():
    text = _prompt_text().lower()
    # The banned V1 pattern: "does team a generate more <metric> against teams with high
    # <metric> conceded". Detect a fully instantiated attack-vs-concession sentence.
    assert "generate more corners" not in text
    assert not re.search(r"more \w+ against teams with high \w+ conceded", text), \
        "prompt instantiates an attack-vs-concession worked example"
    # abstract 'mirror' language is allowed; a concrete instantiation is not.


def test_prompt_permits_abstention_and_forbids_numbers():
    text = _prompt_text()
    assert "NO_NOVEL_GROUNDED_MECHANISM" in text, "abstention token missing"
    low = text.lower()
    for banned in ("probability", "effect size", "expected value", "odds", "p-value"):
        assert banned in low, f"prompt should explicitly PROHIBIT '{banned}'"
    # ensure it prohibits, not requests: the prohibition section exists
    assert "no numbers that resemble predictions" in low


def test_prompt_does_not_leak_prior_audit_statistics():
    low = _prompt_text().lower()
    for leak in ("80%", "duplicate rate", "corners cases", "example cop", "v3 tie",
                 "oos result", "150", "46/150", "77/150"):
        assert leak not in low, f"prompt leaks prior-audit knowledge: '{leak}'"


def test_prompt_requests_k_distinct_mechanisms():
    text = _prompt_text()
    assert "K = 5" in text or "K=5" in text, "prompt must request exactly K distinct mechanisms"
