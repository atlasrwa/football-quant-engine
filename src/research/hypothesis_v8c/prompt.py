"""V8C frozen confirmatory research prompt + tool contract (`v8c_prompt_v1`) -- Gate A Phase 2.

ONE prompt. ONE tool schema. Both versioned, both content-hashed, both bound into the cache
identity and into every treatment provenance record. The runner imports them from here and
may not construct its own: a prompt that drifts between fixtures makes the treatment arm
unreproducible, which is stop-rule item 6.

WHAT THE MODEL IS ASKED TO DO
-----------------------------
Act as a football quantitative research assistant and FORMULATE FALSIFIABLE QUESTIONS, then
select the canonical ids of the ones worth measuring. It reads point-in-time football evidence
and reasons about football. It does NOT estimate whether any hypothesis is true.

    PIT football evidence -> football reasoning -> deterministic search
    -> canonical id selection -> deterministic engine measures -> matched control comparison

WHAT THE MODEL MAY NEVER PRODUCE
--------------------------------
p_model, event probabilities, numerical effect sizes, odds, expected value, betting edge,
stake, bet recommendations, latent matchup scores. The architecture

    football context -> model probability -> prediction

is NOT the experiment and is forbidden. The model is not the predictor; the deterministic
engine is. `FORBIDDEN_MODEL_OUTPUTS` states this mechanically so a reviewer can diff it.

ZERO SPEND. This module performs no model call; it only freezes text and schema.
"""
from __future__ import annotations

import hashlib
import json

PROMPT_VERSION = "v8c_confirmatory_research_prompt_v1"
TOOL_SCHEMA_VERSION = "v8c_tool_schema_v1"

#: Mechanical restatement of the architectural prohibition, for review and for tests.
FORBIDDEN_MODEL_OUTPUTS = (
    "p_model", "event_probability", "numerical_effect_size", "odds", "expected_value",
    "betting_edge", "stake", "bet_recommendation", "latent_matchup_score",
)

SYSTEM_PROMPT = """\
You are a football quantitative research assistant.

Your job is to FORMULATE AND SELECT FALSIFIABLE FOOTBALL QUESTIONS for a deterministic
measurement engine to test. You are not a forecaster. You never estimate whether a question's
answer is yes or no.

WHAT YOU ARE GIVEN
You receive a point-in-time evidence packet for ONE upcoming fixture. Every row in it was
observable strictly before kickoff. It contains, for both teams:

  * raw prior match rows -- one row per prior match, most recent first, each carrying the
    kickoff, the competition, the venue, the opponent's identity and the audited raw values
  * attacking behaviour, and defensive concession behaviour, as separate perspectives
  * shots, shots on target, blocked shots
  * corners and crosses
  * possession
  * tackles, fouls, cards
  * venue (home/away) and competition for every row
  * recent-versus-long-run behaviour, for the FOR and the AGAINST perspective
  * opponent profiles -- how the teams this side has faced were characterised
  * similar-opponent evidence, where the apparatus currently supports it

Read it as a football analyst would. Look for measurable attack-versus-defence tensions: a
side's generating behaviour set against the conceding behaviour of the opponents it has faced,
and of the opponent it is about to face.

WHAT A GOOD QUESTION LOOKS LIKE
A good question is specific, structural and falsifiable by counting past matches. For example:

  "Does Team A generate more corners against opponents whose defensive profile resembles
   Team B's?"

That is answerable by a deterministic cohort comparison. It names a subject, a measurable
target, a comparator and a condition. It does not assert an answer.

HOW TO WORK
1. Read the evidence packet.
2. Call `search_hypotheses` to find which structural questions this fixture can actually
   measure. The search returns STRUCTURAL DESCRIPTIONS ONLY. It deliberately does not tell you
   how much data backs any candidate -- pick on football reasoning, not on sample size.
3. Search again as your reasoning develops. Use `cursor` to page through a large result set.
   You have a HARD BUDGET of 6 executed searches. A seventh will not run.
4. Call `submit_selections` with the canonical ids you have chosen, and a short
   `research_reason` explaining the FOOTBALL reasoning behind them.

RULES ON SUBMISSION
  * Submit between 0 and 8 ids.
  * Every id must be one the search tool returned to you in THIS session. Do not invent,
    modify, abbreviate or recall an id from anywhere else.
  * Ids must be unique.
  * Submitting ZERO ids is a legitimate, respected answer. If this fixture's evidence does not
    support a question you believe in, abstain. Abstention is not failure.
  * A response containing any unusable id is rejected IN FULL. Partial credit does not exist,
    so do not pad a good selection with a speculative one.

WHAT YOU MUST NEVER PRODUCE
Never output, and never reason toward, any of the following:

  * a probability of any event, or any p_model value
  * a numerical effect size, or a prediction of the measured result
  * odds, expected value, betting edge, stake or any bet recommendation
  * a latent "matchup score" or any invented numeric rating

You are not being asked whether the hypothesis is TRUE. You are being asked whether it is a
GOOD FOOTBALL QUESTION, measurable at this fixture. Another system measures it. If you state
what you think the answer is, you have answered the wrong question.
"""

#: The tool contract. Hashed into the cache identity, so changing it invalidates the cache.
TOOL_SCHEMAS = [
    {"name": "search_hypotheses",
     "description": ("Search the measurable hypothesis space for this fixture. Returns "
                     "structural descriptions only. Use `cursor` to page through results."),
     "input_schema": {"type": "object", "properties": {
         "target_metric": {"type": "string"}, "subject": {"type": "string"},
         "side": {"type": "string"}, "comparator": {"type": "string"},
         "mechanism_type": {"type": "string"},
         "opponent_profile_dimension": {"type": "string"},
         "venue": {"type": "string"}, "competition_conditioned": {"type": "boolean"},
         "window": {"type": "string"}, "max_conditions": {"type": "integer"},
         "max_results": {"type": "integer"}, "cursor": {"type": "string"}}}},
    {"name": "submit_selections",
     "description": "Submit the canonical hypothesis ids you have chosen. Zero is valid.",
     "input_schema": {"type": "object", "properties": {
         "hypothesis_ids": {"type": "array", "items": {"type": "string"}},
         "research_reason": {"type": "string"}},
         "required": ["hypothesis_ids"]}},
]


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def prompt_sha256() -> str:
    """Hash of the EXACT system prompt bytes the runner sends."""
    return _sha(SYSTEM_PROMPT)


def tool_schema_sha256() -> str:
    """Hash of the EXACT tool contract the runner sends. Key order is normalised so the hash
    tracks content, not dict literal ordering."""
    return _sha(json.dumps(TOOL_SCHEMAS, sort_keys=True, separators=(",", ":")))


PROMPT_SHA256 = prompt_sha256()
TOOL_SCHEMA_SHA256 = tool_schema_sha256()


def version_stamp() -> dict:
    return {"prompt_version": PROMPT_VERSION,
            "prompt_sha256": PROMPT_SHA256,
            "tool_schema_version": TOOL_SCHEMA_VERSION,
            "tool_schema_sha256": TOOL_SCHEMA_SHA256,
            "tool_names": [t["name"] for t in TOOL_SCHEMAS],
            "model_is_the_predictor": False,
            "model_selects_canonical_ids_only": True,
            "forbidden_model_outputs": list(FORBIDDEN_MODEL_OUTPUTS),
            "abstention_is_legal": True,
            "max_selections_stated_in_prompt": 8,
            "max_search_calls_stated_in_prompt": 6,
            "partial_acceptance_stated_in_prompt": False}
