"""V5A.2 shared prompt (`v5a2_prompt_v1`). ZERO SPEND -- builds strings, calls nothing.

ONE prompt, byte-identical for both arms, still capability-driven and still silent about
which research dimensions are worth pursuing (V5A.1's discipline, preserved).

THREE THINGS ARE ADDED, each closing a rule the model was previously judged against
without ever being told:

  S3/S4  The single-language rule. The model is told explicitly that the terms in the
         availability map are the same strings it must write in `conditions[].dimension`
         and `required_capabilities`. V5A.1 never said this because it was not true: the
         packet said `venue_splits`, the condition enum said `venue`, and the capability
         enum wanted `venue` for venue but `competition` for opponent profile. Now it is
         true, so it can be stated.

  S5     The abstention contract. `INSUFFICIENT_EVIDENCE` may cite the evidence that shows
         WHY the question cannot be supported. V5A.1's validator rejected exactly that and
         no prompt, schema or packet mentioned the rule; 6 rejections were the result. The
         permission is now stated in the same sentence that invites abstention.

  S6     The venue distinction. Knowing which side is at home in the upcoming fixture does
         not license splitting prior matches by venue. V5A.1's base arm rejected 30 venue
         hypotheses without ever having drawn that line, which made the number impossible
         to interpret.

Nothing here tells the model what to find, what is interesting, or how many hypotheses to
produce. Available terms remain a boundary, not a quota.
"""
from __future__ import annotations

from src.research.hypothesis_engine import schema_v3 as SCHEMA
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_prompt as P1

V5A2_PROMPT_VERSION = "v5a2_prompt_v1"

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

ONE VOCABULARY
Every term in the AVAILABILITY_MAP is spelled exactly the same way in your response:
  * as `conditions[].dimension`, for the terms it marks conditionable;
  * in `required_capabilities`, for any term your question leans on.
There is no second vocabulary and nothing for you to translate. If you want to split a
cohort by a term, write that term. If your question depends on evidence, name that evidence
with the same term the map used for it. A term the map does not list is not a term.

TWO TERMS THAT ARE OFTEN CONFUSED
  * `target_fixture_venue_context` is the fact that the upcoming fixture has a home side
    and an away side. It is always available.
  * `historical_venue_conditioning` is splitting the subject's PRIOR matches by where they
    were played. It needs venue-split evidence in this packet.
Knowing the first does NOT give you the second. Check the map before conditioning on venue.

WHAT YOU MAY ASK ABOUT
Only what this packet exposes. Propose a question involving venue, short-window versus
long-run behaviour, opponent profile, formation, competition or an interaction ONLY when
the packet actually carries evidence supporting that dimension. These are a boundary, not
a checklist: a packet exposing a term is not a reason to use it. Let the visible evidence
decide what is worth testing, and prefer a simple question when a further condition is not
supported by what you can see.

If a research dimension is unavailable, do not use it, do not infer it, and do not work
around it. Marking a hypothesis INSUFFICIENT_EVIDENCE is a correct and valued answer, and
when you abstain you MAY cite the evidence that shows why the question cannot be supported
-- an abstention that points at the gap is more useful than a bare one. Every id you cite
must still be one the packet actually contains, whether you are abstaining or not.

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
    estimated or expected result, and it may not copy a number out of the packet into prose.

Return ONLY JSON conforming to the provided schema.
"""


def build_user_payload(packet_dict: dict) -> str:
    """The user turn = the serialized packet. Order-preserving and byte-reproducible."""
    return E.serialize(packet_dict)


def build_request(packet_dict: dict) -> dict:
    return {
        "prompt_version": V5A2_PROMPT_VERSION,
        "system": SYSTEM_PROMPT,
        "user": build_user_payload(packet_dict),
        "response_schema_version": SCHEMA.SCHEMA_VERSION,
        "response_schema_content_hash": SCHEMA.schema_content_hash(),
        "max_hypotheses": SCHEMA.MAX_HYPOTHESES,
    }


def serialized_request(packet_dict: dict) -> str:
    return SYSTEM_PROMPT + "\x00" + build_user_payload(packet_dict)


#: Inherited verbatim -- the blinding and priming batteries are unchanged in V5A.2.
PROHIBITION_ONLY_TERMS = P1.PROHIBITION_ONLY_TERMS
PRIMING_PHRASES = P1.PRIMING_PHRASES
TREATMENT_LABELS = P1.TREATMENT_LABELS


# ----------------------------------------------------------------------------------------
# Blinding check (task S6 of V5A.1, carried forward and corrected).
# ----------------------------------------------------------------------------------------
def blinding_violations(text: str) -> list:
    """Treatment labels present as WHOLE WORDS. Returns the labels found.

    V5A.1's audit substring-matched `TREATMENT_LABELS`, so `control` matched inside
    `"the cohort is not a controlled comparison"` -- a statistical caveat in a static
    disclaimer, present in the research arm only because that arm carries the
    opponent-profile section the disclaimer belongs to. Reporting that as a blinding leak
    is a false positive, and the fix is to match what the rule actually means rather than
    to add the phrase to an exemption list: a treatment label leaks the condition only when
    it appears AS the word. `controlled` is not the label `control`.

    Multi-word and punctuation-bearing entries (e.g. `"arm"`) are matched literally, since
    a word boundary is not meaningful for them.
    """
    import re
    found = []
    for label in TREATMENT_LABELS:
        if label.strip('"').isidentifier() and "_" not in label:
            hit = re.search(rf"\b{re.escape(label)}\b", text, re.IGNORECASE)
        else:
            hit = re.search(re.escape(label), text, re.IGNORECASE)
        if hit:
            found.append(label)
    return sorted(set(found))
