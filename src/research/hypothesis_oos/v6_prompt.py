"""V6 shared prompt (`v6_prompt_v1`). ZERO SPEND -- builds strings, calls nothing.

ONE prompt, byte-identical for both arms, still capability-driven, still silent about which
research dimensions are worth pursuing. It inherits every word of `v5a2_prompt`'s discipline
and its blinding/priming batteries VERBATIM, and adds exactly the two things V6's contract
changed and nothing else -- because a prompt that taught rules the model is not judged
against, or stayed silent about rules it IS judged against, is the class of defect that made
V5A.1 and V5A.2 uninterpretable.

WHAT V6 ADDS OVER V5A.2, AND WHY EACH ADDITION IS OWED
------------------------------------------------------
A1  THE evidence_summary FIELD (schema_v4 C2 / §4). V5A.2 had `question` as its only
    free-text field, so the one legitimate reason to write a number (reproducing a value the
    packet supplied) and the one illegitimate reason (authoring a prediction) shared a
    surface and had to share a verdict. `firewall_v5` now judges them apart, but only if the
    model knows the field exists and what it is for. So the prompt states, in the same
    breath: the field is OPTIONAL; it is the ONLY place a packet value may be written out;
    and a number that is a claim about the upcoming fixture is forbidden there exactly as
    everywhere else. §16's "do not require citation volume for its own sake" is stated too:
    a model that never needs to reproduce a value is never pushed into writing one.

A2  HYPOTHESIS-LEVEL INDEPENDENCE (§3). V5A.2 rejected a whole response on one bad
    hypothesis, and the model was never told otherwise -- so a cautious model had a reason
    to suppress a borderline-but-legitimate question rather than risk the batch. V6 tells
    the model the truth about how it is judged: each hypothesis is adjudicated on its own,
    and one rejected hypothesis does not discard its siblings. This is not an inducement to
    be reckless -- every hard rule still stands, per hypothesis -- it removes an incentive to
    self-censor that would have biased the very quantity §10 measures.

WHAT V6 DELIBERATELY DOES NOT ADD
---------------------------------
No hint about what to find, what is interesting, how many hypotheses to produce, or that
richer evidence should be used more. §11/§18: available terms are a boundary, not a quota,
and Arm B earns nothing for using a dimension it was handed -- only for using it correctly.
The prompt cannot know which arm it is serving (the arm string is never serialized, M-6),
and says nothing that would differ between them.

The numeric-authority FIELD contract (§5) is enforced structurally by `v6_numeric_contract`
and does not need a new sentence: the existing HARD RULES already forbid probabilities,
odds, EV, edges, stakes, advantage/matchup scores and effect sizes by name, which is the
same set the field contract rejects. Restating it as a field list would invite the model to
treat the list as exhaustive.

ZERO SPEND.
"""
from __future__ import annotations

from src.research.hypothesis_engine import schema_v4 as SCHEMA
from src.research.hypothesis_oos import v5a1_evidence as E
from src.research.hypothesis_oos import v5a1_prompt as P1
from src.research.hypothesis_oos import v5a2_prompt as P2

V6_PROMPT_VERSION = "v6_prompt_v1"

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

HOW EACH HYPOTHESIS IS JUDGED
Each hypothesis is evaluated ENTIRELY ON ITS OWN. A hypothesis that breaks a rule is set
aside by itself; it does not discard the others. So do not withhold a well-grounded,
in-bounds question for fear of the batch: propose every question the visible evidence
supports, and let each stand or fall alone. This is not licence to guess. Every rule below
applies to every hypothesis, one at a time.

STATING WHAT YOUR EVIDENCE SHOWS
Each hypothesis has an OPTIONAL `evidence_summary` field. It is the ONLY place you may write
out a value the packet gave you -- and only as a plain record of what was already observed:
say what was recorded, cited or measured, and in which cohort (for example, what a cited
summary row contained, or how large a cohort was). Use it only when it helps ground the
question; a hypothesis that needs no reproduced value should leave it empty. A number that
is a claim about the upcoming fixture -- a probability, a price, an edge, an advantage, an
expected effect or any adjustment -- is forbidden in `evidence_summary` exactly as it is
everywhere else. The research QUESTION itself should name what to measure and should not
carry numeric literals; put any value you must reproduce in `evidence_summary`, or better,
point at it with an evidence id.

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
  * A comparison must have a real contrast: do not condition a cohort on the same
    restriction its comparison baseline already carries, or the two sides are one set and
    there is nothing to measure.
  * Your rationale may describe what the cited evidence shows. It may not contain an
    estimated or expected result, and it may not author a number of its own.

Return ONLY JSON conforming to the provided schema.
"""


def build_user_payload(packet_dict: dict) -> str:
    """The user turn = the serialized packet. Order-preserving and byte-reproducible."""
    return E.serialize(packet_dict)


def build_request(packet_dict: dict) -> dict:
    """The request the driver sends. Carries the COMPOSED schema_v4 -- the model is shown
    the complete item contract, `evidence_summary` and all. Splitting the schema is how a
    RESPONSE is adjudicated (§3), never a relaxation of what the model was asked for."""
    return {
        "prompt_version": V6_PROMPT_VERSION,
        "system": SYSTEM_PROMPT,
        "user": build_user_payload(packet_dict),
        "response_schema_version": SCHEMA.SCHEMA_VERSION,
        "response_schema_content_hash": SCHEMA.schema_content_hash(),
        "max_hypotheses": SCHEMA.MAX_HYPOTHESES,
    }


def serialized_request(packet_dict: dict) -> str:
    """The exact byte string the request hash is taken over: system + NUL + user."""
    return SYSTEM_PROMPT + "\x00" + build_user_payload(packet_dict)


#: Inherited VERBATIM. The blinding and priming batteries are unchanged in V6; the treatment
#: is still carried only by which evidence the packet contains, never by the prompt.
PROHIBITION_ONLY_TERMS = P1.PROHIBITION_ONLY_TERMS
PRIMING_PHRASES = P1.PRIMING_PHRASES
TREATMENT_LABELS = P1.TREATMENT_LABELS

#: The corrected whole-word blinding check, reused from V5A.2 unchanged.
blinding_violations = P2.blinding_violations


def priming_violations(text: str) -> list:
    """Priming phrases present in the prompt. The prompt must not tell the model what is
    interesting. Returns the phrases found; empty is the required state."""
    low = (text or "").lower()
    return sorted({p for p in PRIMING_PHRASES if p.lower() in low})


def prohibition_terms_present(text: str) -> list:
    """PROHIBITION_ONLY_TERMS are allowed ONLY inside a prohibition. Reported for audit;
    every occurrence in this prompt is inside a `Do NOT ...` clause."""
    low = (text or "").lower()
    return sorted({t for t in PROHIBITION_ONLY_TERMS if t.lower() in low})


def version_stamp() -> dict:
    return {"prompt_version": V6_PROMPT_VERSION,
            "system_prompt_identical_across_arms": True,
            "response_schema_version": SCHEMA.SCHEMA_VERSION,
            "response_schema_content_hash": SCHEMA.schema_content_hash(),
            "adds_over_v5a2": ["evidence_summary field contract (§4)",
                               "hypothesis-level independence statement (§3)"],
            "teaches_what_to_find": False,
            "teaches_a_quota": False,
            "inherits_blinding_battery_from": P2.V5A2_PROMPT_VERSION}
