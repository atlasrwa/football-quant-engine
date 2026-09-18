"""V8C runner (`v8c_runner_v1`) -- repairs P1 RUNNER-WIRE.

THE DEFECT
----------
V8C had no runner at all: the only one was `hypothesis_v8b1.runner`, whose `search_hypotheses`
tool called `hypothesis_v8b1.search.search()`. That function answers from V8B.1's undeclared
subset grammar (ALL_PRIOR only, conditions of arity <= 1), with no evaluability filter, no
pagination and no MEASSPACE projection. A "V8C run" driven by it would have put Sonnet back on
V8B.1's universe while every other arm used V8C's -- the exact arms-see-different-universes
defect V8C exists to fix.

THE WIRING
----------
The search tool answers ONLY from that fixture's V8C `FixtureUniverse`:

  * candidates come from `PRE_T_EVALUABLE_IR_SPACE`, the same set R matches within and H ranks
    over;
  * results are the `llm_facing` projection -- no raw_n, no effective_n (P1 MEASSPACE);
  * results are PAGINATED with a deterministic cursor, so no region is unreachable
    (P1 SEARCH-REACHABILITY);
  * every id returned this session is recorded in a live registry.

SUBMISSION VALIDATION, three checks, all of them explicit terminal states:

  1. the id must have been RETURNED by this session's search (live registry) -- an id the
     model invented or remembered from training is rejected, not silently kept;
  2. the id must RESOLVE under the V8C grammar;
  3. the resolved IR's canonical id must EQUAL the submitted id -- an id that resolves to a
     different IR is a grammar/canonicalisation fault, never quietly accepted.

There is no silent `continue` anywhere (P1 INVALID-S): each failure produces a named status
and a research-yield count.

ZERO SPEND IN THIS MISSION. `run_fixture` performs no model call unless it is handed a
`converse` callable; the V8C mission runs it with a deterministic stand-in only.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from src.research.hypothesis_v8c import cache as CACHE
from src.research.hypothesis_v8c import grammar as GR
from src.research.hypothesis_v8c import universe as UNI

RUNNER_VERSION = "v8c_runner_v2"
ORCHESTRATION_VERSION = "v8c_bounded_search_then_forced_submit_v1"
SEARCH_TOOL_VERSION = UNI.UNIVERSE_VERSION

#: Inherited unchanged from the V8B.1 orchestration amendment.
MAX_SEARCH_CALLS = 6
FINAL_FORCED_SUBMIT_CALLS = 1
MAX_TOOL_TURNS = MAX_SEARCH_CALLS + FINAL_FORCED_SUBMIT_CALLS

#: P1-D FROZEN SUBMISSION CONTRACT.
#:
#: MAX_SELECTIONS is 8, inherited from the V8B.1 orchestration amendment's stated "0-8
#: selections valid". It is restated here as a HARD contract rather than prose.
MAX_SELECTIONS = 8

OK = "OK"
OK_ABSTAIN = "OK_ABSTAIN"
INVALID_SUBMISSION = "INVALID_SUBMISSION"
SEARCH_BUDGET_EXHAUSTED = "SEARCH_BUDGET_EXHAUSTED"

#: Per-id reasons, reported inside an INVALID_SUBMISSION rather than as fixture statuses.
REASON_DUPLICATE = "DUPLICATE_ID"
REASON_NOT_RETURNED = "ID_NOT_RETURNED_THIS_SESSION"
REASON_UNKNOWN = "UNKNOWN_HYPOTHESIS_ID"
REASON_DIFFERENT_IR = "ID_RESOLVES_TO_DIFFERENT_IR"
REASON_OVER_CAP = "EXCEEDS_MAX_SELECTIONS"

TERMINAL_SELECTION_STATUSES = (OK, OK_ABSTAIN, INVALID_SUBMISSION)

#: THE ALL-OR-NOTHING RULE, preregistered here.
#:
#: A response containing [valid_id, fabricated_id] is NOT silently converted into a clean
#: one-selection treatment. Partial acceptance would mean the treatment arm's content depends
#: on which of the model's ids happened to survive validation -- an outcome-independent but
#: undeclared filter on the treatment. The whole fixture's treatment is INVALID_SUBMISSION
#: with ZERO accepted selections, and it is counted in research yield.
PARTIAL_ACCEPTANCE = False

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


@dataclass
class SearchSession:
    """The live registry of what the search tool actually returned THIS session."""
    fixture_universe: object
    returned_ids: set = field(default_factory=set)
    calls: list = field(default_factory=list)
    search_calls_used: int = 0

    def search(self, query_kwargs: dict) -> dict:
        """Answer one search_hypotheses call from the V8C evaluable universe."""
        if self.search_calls_used >= MAX_SEARCH_CALLS:
            self.calls.append({"status": SEARCH_BUDGET_EXHAUSTED, "query": query_kwargs})
            return {"status": SEARCH_BUDGET_EXHAUSTED, "results": [], "cursor": None,
                    "n_remaining": 0}
        self.search_calls_used += 1
        cursor = query_kwargs.pop("cursor", None)
        q = UNI.SearchQuery(**{k: v for k, v in query_kwargs.items()
                               if k in UNI.SearchQuery.__dataclass_fields__})
        page = UNI.search_evaluable(q, self.fixture_universe, cursor=cursor)
        for c in page["results"]:
            UNI.assert_llm_safe(c)            # MEASSPACE, enforced at the tool boundary
            self.returned_ids.add(c["hypothesis_id"])
        self.calls.append({"status": "OK", "query": query_kwargs,
                           "n_results": len(page["results"]),
                           "n_remaining": page["n_remaining"]})
        return {"status": "OK", **page}


def validate_submission(submitted_ids, session: SearchSession, capability,
                        grammar_kwargs=None) -> dict:
    """The FROZEN P1-D contract. All-or-nothing: any malformed element invalidates the whole
    fixture's treatment (PARTIAL_ACCEPTANCE = False).

    Checks, all explicit, none silent:
      * <= MAX_SELECTIONS
      * ids UNIQUE
      * every id RETURNED by this live session's search tool
      * every id present in THIS fixture's evaluable universe
      * every id RESOLVES under the V8C grammar
      * canonical id ROUND-TRIPS
      * zero selections is a LEGAL abstention
    """
    gkw = grammar_kwargs or {}
    by_id = {c["hypothesis_id"]: c for c in session.fixture_universe.evaluable}
    ids = list(submitted_ids)
    problems = []

    if not ids:
        return {"status": OK_ABSTAIN, "accepted": [], "problems": [],
                "n_submitted": 0, "partial_acceptance": PARTIAL_ACCEPTANCE,
                "research_yield": {"submitted": 0, "accepted": 0, "rejected": 0,
                                   "abstained": True}}

    if len(ids) > MAX_SELECTIONS:
        problems.append({"hypothesis_id": None, "reason": REASON_OVER_CAP,
                         "detail": f"{len(ids)} submitted, cap {MAX_SELECTIONS}"})

    seen = set()
    for hid in ids:
        if hid in seen:
            problems.append({"hypothesis_id": hid, "reason": REASON_DUPLICATE,
                             "detail": "id submitted more than once"})
            continue
        seen.add(hid)
        if hid not in session.returned_ids:
            problems.append({"hypothesis_id": hid, "reason": REASON_NOT_RETURNED,
                             "detail": "never returned by this session's search tool"})
            continue
        if hid not in by_id:
            problems.append({"hypothesis_id": hid, "reason": REASON_UNKNOWN,
                             "detail": "not in this fixture's PRE_T_EVALUABLE universe"})
            continue
        ir = GR.resolve(hid, capability, **gkw)
        if ir is None:
            problems.append({"hypothesis_id": hid, "reason": REASON_UNKNOWN,
                             "detail": "does not resolve under the V8C grammar"})
            continue
        if ir.ir_id() != hid:
            problems.append({"hypothesis_id": hid, "reason": REASON_DIFFERENT_IR,
                             "detail": f"resolves to {ir.ir_id()!r}"})

    if problems:
        # ALL-OR-NOTHING: zero accepted treatment selections for this fixture.
        return {"status": INVALID_SUBMISSION, "accepted": [], "problems": problems,
                "n_submitted": len(ids), "partial_acceptance": PARTIAL_ACCEPTANCE,
                "research_yield": {"submitted": len(ids), "accepted": 0,
                                   "rejected": len(ids), "abstained": False}}

    return {"status": OK, "accepted": list(ids), "problems": [],
            "n_submitted": len(ids), "partial_acceptance": PARTIAL_ACCEPTANCE,
            "research_yield": {"submitted": len(ids), "accepted": len(ids), "rejected": 0,
                               "abstained": False}}


def cache_identity_for(*, fixture_universe, pit_context_hash, packet_hash, prompt_hash,
                       model_id, resolved_model_id, model_config_stamp) -> dict:
    """Bind a cached response to EVERYTHING that determines the model's task (P1 CACHE)."""
    return CACHE.build_identity(
        model_id=model_id, resolved_model_id=resolved_model_id, prompt_hash=prompt_hash,
        tool_schema_hash=CACHE.tool_schema_hash(TOOL_SCHEMAS), packet_hash=packet_hash,
        pit_context_hash=pit_context_hash,
        fixture_universe_hash=CACHE.fixture_universe_hash(fixture_universe),
        search_version=SEARCH_TOOL_VERSION, runner_version=RUNNER_VERSION,
        orchestration_version=ORCHESTRATION_VERSION,
        model_config_hash=CACHE.model_config_hash(model_config_stamp))


def run_fixture(fixture_universe, capability, *, selector, grammar_kwargs=None) -> dict:
    """Drive ONE fixture's selection through the real tool surface.

    `selector(session)` stands in for the model: it may call `session.search(...)` any number
    of times and returns the ids it submits. In a paid run this is the Bedrock Converse loop;
    in this mission it is always a deterministic stand-in, so NEW_SONNET_CALLS stays 0.
    """
    session = SearchSession(fixture_universe=fixture_universe)
    submitted = list(selector(session))
    result = validate_submission(submitted, session, capability,
                                 grammar_kwargs=grammar_kwargs)
    result["valid"] = result["accepted"]        # back-compat alias for existing callers
    result["search_calls_used"] = session.search_calls_used
    result["n_ids_returned_this_session"] = len(session.returned_ids)
    result["search_trace"] = session.calls
    return result


def version_stamp() -> dict:
    return {"runner_version": RUNNER_VERSION,
            "orchestration_version": ORCHESTRATION_VERSION,
            "repairs": ["P1-RUNNER-WIRE", "P1-INVALID-S"],
            "search_tool_source": "hypothesis_v8c.universe.search_evaluable",
            "uses_v8b1_search": False,
            "search_returns_llm_facing_projection_only": True,
            "search_is_paginated": True,
            "validation_checks": ["max-selections", "unique-ids", "returned-by-this-session",
                                  "in-this-fixture-universe", "resolves-under-v8c-grammar",
                                  "canonical-id-round-trips"],
            "terminal_selection_statuses": list(TERMINAL_SELECTION_STATUSES),
            "max_selections": MAX_SELECTIONS,
            "partial_acceptance": PARTIAL_ACCEPTANCE,
            "invalid_response_policy": ("INVALID_SUBMISSION with ZERO accepted selections; a "
                                        "mixed valid/invalid response is never converted into "
                                        "a clean partial treatment"),
            "abstention_is_legal": True,
            "silent_drop_of_invalid_id": False,
            "max_search_calls": MAX_SEARCH_CALLS,
            "tool_schema_hash": CACHE.tool_schema_hash(TOOL_SCHEMAS),
            "performs_model_call_in_v8c_mission": False}
