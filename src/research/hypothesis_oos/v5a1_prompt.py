"""V5A.1 shared prompt (`v5a1_prompt_v1`). ZERO SPEND -- builds strings, calls nothing.

ONE prompt, byte-identical for both arms, and CAPABILITY-DRIVEN rather than
structure-promising. The aborted V5A's prompt told every model "You will receive, for both
teams: match_level_history ... derived_summaries ... opponent_profile_context ...
availability_map" -- four blocks the base arm did not contain. That handicapped the control
with instructions it could not follow and made the comparison uninterpretable (HS-3).

Here the prompt promises nothing about what is in the packet. It points at the packet's own
availability map and says: use what is declared EXPOSED, and nothing else.

It also does not tell the model which research dimensions to pursue (task §22). Available
dimensions are a boundary, not a quota.
"""
from __future__ import annotations

import json

from src.research.hypothesis_engine import schema_v2 as SCHEMA
from src.research.hypothesis_oos import v5a1_evidence as E

V5A1_PROMPT_VERSION = "v5a1_prompt_v1"

SYSTEM_PROMPT = """\
You are a quantitative football RESEARCH assistant.

You receive one point-in-time-safe EVIDENCE PACKET describing the history that precedes one
upcoming fixture. Every number in it was computed by a deterministic engine from matches
that kicked off strictly before that fixture's information cutoff.

YOUR JOB IS NOT TO PREDICT THE MATCH.
Your job is to propose FALSIFIABLE HISTORICAL QUESTIONS that a deterministic engine should
measure next. You specify WHAT to measure. The engine decides cohorts, measurements,
effects and statistics, and separate out-of-sample validation decides whether anything
generalises. You never supply a number of your own.

HOW TO READ THE PACKET
The packet is a list of numbered sections, in reading order. Read them in order.
  * TARGET_FIXTURE_CONTEXT tells you which side is HOME_TEAM, which is AWAY_TEAM, the
    information cutoff, and how many prior matches each summary is built from.
  * AVAILABILITY_MAP is authoritative about what THIS packet contains. Each entry carries
    three separate flags. Act ONLY on EXPOSED_TO_LLM. PROVIDER_AVAILABLE and
    DERIVABLE_PIT_SAFE describe the upstream corpus and are shown only so you can see that
    an absence is deliberate; evidence that is derivable upstream but not EXPOSED here is
    not available to you.
  * METRIC_SEMANTICS defines every metric once: what it counts, its units, its source, its
    null policy, and which metrics are deliberately excluded and why.
  * Later sections carry the evidence itself. Different packets expose different evidence
    types, so do not assume a section exists because you have seen one before. If a section
    is absent, the availability map says so.

WHAT YOU MAY ASK ABOUT
Only what this packet exposes. Propose a question involving venue, short-window versus
long-run behaviour, opponent profile, formation, competition or an interaction ONLY when
the packet actually carries evidence supporting that dimension. These are a boundary, not
a checklist: a packet exposing a dimension is not a reason to use it. Let the visible
evidence decide what is worth testing, and prefer a simple question when a further
condition is not supported by what you can see.

If a research dimension is unavailable, do not use it, do not infer it, and do not work
around it. Marking a hypothesis INSUFFICIENT_EVIDENCE is a correct and valued answer.

HARD RULES
  * Do NOT estimate probabilities, fair odds, expected value, edges, stakes, advantage
    scores, latent strength, matchup scores or effect sizes. No numeric prediction, and no
    numeric claim about the upcoming fixture, of any kind.
  * Do NOT treat an observed pattern as predictive truth. You are proposing what to
    measure, never reporting what the measurement will find.
  * Do NOT invent context the packet does not contain -- injuries, weather, expected
    lineups or formations, motivation, minute-level events, market prices.
  * Ground every hypothesis. Put the evidence_ids that motivated it in `evidence_refs`,
    copied exactly as they appear in the packet. A reference the packet does not contain is
    not evidence. The final section of every packet gives the id grammar and examples.
  * Your rationale may describe what the cited evidence shows. It may not contain an
    estimated or expected result.

Return ONLY JSON conforming to the provided schema.
"""


def build_user_payload(packet_dict: dict) -> str:
    """The user turn = the serialized packet.

    Deterministic and ORDER-PRESERVING: section order is load-bearing in V5A.1, so this
    must not sort keys. Construction is deterministic, so the bytes are reproducible and
    the frozen request hash is stable.
    """
    return E.serialize(packet_dict)


def build_request(packet_dict: dict) -> dict:
    """The full (system, user, schema) request object -- NOT sent anywhere here."""
    return {
        "prompt_version": V5A1_PROMPT_VERSION,
        "system": SYSTEM_PROMPT,
        "user": build_user_payload(packet_dict),
        "response_schema_version": SCHEMA.SCHEMA_VERSION,
        "response_schema_content_hash": SCHEMA.schema_content_hash(),
        "max_hypotheses": SCHEMA.MAX_HYPOTHESES,
    }


def serialized_request(packet_dict: dict) -> str:
    return SYSTEM_PROMPT + "\x00" + build_user_payload(packet_dict)


#: Terms that appear in the prompt ONLY inside the HARD RULES prohibition list ("Do NOT
#: estimate ... advantage scores ..."). Forbidding a thing is not priming for it, but the
#: battery must be able to tell the two apart, so they are enumerated rather than assumed.
PROHIBITION_ONLY_TERMS = ("advantage", "exploit", "favourable", "favorable")

#: Phrases that would tell the model which relationships are valuable. The pre-spend
#: battery asserts none of these appears in any packet, and none appears in the prompt
#: except the prohibition-only terms above (task §22).
PRIMING_PHRASES = (
    "important relationship", "key signal", "strong divergence", "use this", "notable",
    "high-value", "high value feature", "striking", "interesting", "promising",
    "you should focus", "most relevant", "strongest", "look for", "pay attention",
    "worth noting", "significant", "favourable", "favorable", "advantage", "exploit",
)

#: Strings that would identify the experimental condition to the model (task §6).
TREATMENT_LABELS = (
    "arm_a", "arm_b", "ARM_A", "ARM_B", "\"arm\"", "full_fidelity", "FULL_FIDELITY",
    "compressed", "COMPRESSED", "control", "CONTROL", "treatment", "TREATMENT",
    "baseline_arm", "condition_a", "condition_b", "experiment_arm", "B_full_fidelity",
)
