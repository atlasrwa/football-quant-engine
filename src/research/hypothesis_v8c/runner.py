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
from src.research.hypothesis_v8c import prompt as PROMPT
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

#: The tool contract and the system prompt are the FROZEN artifacts from `prompt.py`.
#: The runner may not construct its own: a prompt that drifts between fixtures makes the
#: treatment arm unreproducible (stop-rule item 6).
TOOL_SCHEMAS = PROMPT.TOOL_SCHEMAS
SYSTEM_PROMPT = PROMPT.SYSTEM_PROMPT
PROMPT_VERSION = PROMPT.PROMPT_VERSION
PROMPT_SHA256 = PROMPT.PROMPT_SHA256
TOOL_SCHEMA_VERSION = PROMPT.TOOL_SCHEMA_VERSION
TOOL_SCHEMA_SHA256 = PROMPT.TOOL_SCHEMA_SHA256

SEARCH_TOOL_NAME = "search_hypotheses"
SUBMIT_TOOL_NAME = "submit_selections"

#: Terminal reasons for the orchestration loop, distinct from the SELECTION statuses above.
TERM_SUBMITTED = "SUBMITTED"
TERM_FORCED_SUBMIT = "FORCED_SUBMIT_AFTER_BUDGET_EXHAUSTED"
TERM_NO_SUBMISSION = "ENDED_WITHOUT_SUBMISSION"
TERM_MAX_TURNS = "MAX_TOOL_TURNS_EXCEEDED"
TERM_MALFORMED_TOOL_USE = "MALFORMED_TOOL_USE"


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
    result["ids_returned_to_model"] = sorted(session.returned_ids)
    result["submitted_ids"] = list(submitted)
    result["raw_model_response_hashes"] = []
    # The SAME orchestration block `run_fixture_converse` emits, so a treatment record is
    # complete whichever entry point produced it. A provenance field that is populated on one
    # path and silently None on the other is how an audit trail rots.
    result["orchestration"] = {
        "runner_version": RUNNER_VERSION,
        "orchestration_version": ORCHESTRATION_VERSION,
        "converse_calls": 0,
        "search_calls_attempted": len(session.calls),
        "search_calls_executed": session.search_calls_used,
        "max_search_calls": MAX_SEARCH_CALLS,
        "search_budget_exhausted": any(c.get("status") == SEARCH_BUDGET_EXHAUSTED
                                       for c in session.calls),
        "forced_submit": False,
        "termination_reason": TERM_SUBMITTED,
        "stop_reasons": [],
        "usage": [],
        "malformed_reason": None,
        "transport": "IN_PROCESS_SELECTOR (no model call)",
    }
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


# ==========================================================================================
# PHASE 1 -- the real Bedrock Converse orchestration.
#
# The model client is INJECTED. `converse` is any callable with the Bedrock Converse shape:
#
#     converse(modelId=..., messages=[...], system=[...], toolConfig={...},
#              inferenceConfig={...}) -> {"output": {"message": {"role", "content": [...]}},
#                                         "stopReason": ..., "usage": {...}}
#
# Nothing in this module imports boto3 and nothing here constructs a client. A test supplies a
# deterministic mock; a paid run would supply a real Bedrock client. That is the only
# difference, which is what makes the mocked tests evidence about the real path.
# ==========================================================================================

def _tool_uses(response: dict) -> list:
    """Every toolUse block in a Converse response, in order."""
    content = (((response or {}).get("output") or {}).get("message") or {}).get("content") or []
    return [b["toolUse"] for b in content if isinstance(b, dict) and "toolUse" in b]


def _assistant_message(response: dict) -> dict:
    msg = (((response or {}).get("output") or {}).get("message") or {})
    return {"role": msg.get("role", "assistant"), "content": msg.get("content", [])}


def _tool_result(tool_use_id: str, payload: dict, *, ok: bool = True) -> dict:
    return {"toolResult": {"toolUseId": tool_use_id,
                           "content": [{"json": payload}],
                           "status": "success" if ok else "error"}}


def _submitted_ids_from(tool_input) -> tuple:
    """(ids, malformed_reason). A malformed submission yields ids=None so the caller can
    record INVALID_SUBMISSION rather than silently treating it as an abstention."""
    if not isinstance(tool_input, dict):
        return None, "submit_selections input is not an object"
    if "hypothesis_ids" not in tool_input:
        return None, "submit_selections omitted the required `hypothesis_ids`"
    ids = tool_input["hypothesis_ids"]
    if not isinstance(ids, list):
        return None, "`hypothesis_ids` is not a list"
    if not all(isinstance(x, str) for x in ids):
        return None, "`hypothesis_ids` contains a non-string element"
    return tuple(ids), None


def run_fixture_converse(fixture_universe, capability, *, converse, packet,
                         model_id, resolved_model_id=None, model_config_stamp=None,
                         grammar_kwargs=None, inference_config=None) -> dict:
    """Drive ONE fixture through the REAL multi-turn tool loop.

    The search backend is `hypothesis_v8c.universe.search_evaluable`, via `SearchSession` --
    never V8B search. The call cap is enforced by `SearchSession`, which returns a
    deterministic SEARCH_BUDGET_EXHAUSTED rather than executing a seventh search.

    Returns the complete, immutable treatment record.
    """
    session = SearchSession(fixture_universe=fixture_universe)
    messages = [{"role": "user", "content": [{"text": packet}]}]
    tool_config = {"tools": [{"toolSpec": t} for t in TOOL_SCHEMAS]}

    converse_calls = 0
    search_attempted = 0
    budget_exhausted = False
    forced_submit_requested = False
    submitted, malformed, termination = None, None, None
    raw_response_hashes, stop_reasons, usages = [], [], []

    for _turn in range(MAX_TOOL_TURNS + 1):
        response = converse(modelId=model_id, messages=messages,
                            system=[{"text": SYSTEM_PROMPT}], toolConfig=tool_config,
                            inferenceConfig=inference_config or {})
        converse_calls += 1
        raw_response_hashes.append(CACHE._sha(response))
        stop_reasons.append(response.get("stopReason"))
        if response.get("usage"):
            usages.append(response["usage"])

        uses = _tool_uses(response)
        if not uses:
            termination = TERM_NO_SUBMISSION
            break

        messages.append(_assistant_message(response))
        results, terminated = [], False

        for use in uses:
            name = use.get("name")
            use_id = use.get("toolUseId", "")
            tool_input = use.get("input")

            if name == SUBMIT_TOOL_NAME:
                ids, why = _submitted_ids_from(tool_input)
                if ids is None:
                    submitted, malformed = None, why
                    termination = TERM_MALFORMED_TOOL_USE
                else:
                    submitted = ids
                    termination = (TERM_FORCED_SUBMIT if forced_submit_requested
                                   else TERM_SUBMITTED)
                terminated = True
                break

            if name == SEARCH_TOOL_NAME:
                search_attempted += 1
                page = session.search(dict(tool_input or {}))
                if page.get("status") == SEARCH_BUDGET_EXHAUSTED:
                    budget_exhausted = True
                    forced_submit_requested = True
                    # The seventh search does NOT run. The model is told, deterministically,
                    # that it must now submit.
                    page = {**page, "instruction": (
                        "SEARCH_BUDGET_EXHAUSTED: you have used all 6 searches. Call "
                        "submit_selections now with 0-8 ids you have already seen.")}
                results.append(_tool_result(use_id, page,
                                            ok=page.get("status") != SEARCH_BUDGET_EXHAUSTED))
                continue

            # An unknown tool is a malformed response, not something to route around.
            submitted, malformed = None, f"unknown tool {name!r}"
            termination = TERM_MALFORMED_TOOL_USE
            terminated = True
            break

        if terminated:
            break
        messages.append({"role": "user", "content": results})
    else:
        termination = TERM_MAX_TURNS

    if termination is None:
        termination = TERM_MAX_TURNS

    if submitted is None:
        # No usable submission. Never silently an abstention: an abstention is a submission of
        # zero ids, which is a different event from never submitting at all.
        result = {"status": INVALID_SUBMISSION, "accepted": [], "problems":
                  [{"hypothesis_id": None, "reason": "NO_VALID_SUBMISSION",
                    "detail": malformed or termination}],
                  "n_submitted": 0, "partial_acceptance": PARTIAL_ACCEPTANCE,
                  "research_yield": {"submitted": 0, "accepted": 0, "rejected": 0,
                                     "abstained": False}}
    else:
        result = validate_submission(submitted, session, capability,
                                     grammar_kwargs=grammar_kwargs)

    result["valid"] = result["accepted"]
    result["orchestration"] = {
        "runner_version": RUNNER_VERSION,
        "orchestration_version": ORCHESTRATION_VERSION,
        "converse_calls": converse_calls,
        "search_calls_attempted": search_attempted,
        "search_calls_executed": session.search_calls_used,
        "max_search_calls": MAX_SEARCH_CALLS,
        "search_budget_exhausted": budget_exhausted,
        "forced_submit": forced_submit_requested,
        "termination_reason": termination,
        "stop_reasons": stop_reasons,
        "usage": usages,
        "malformed_reason": malformed,
    }
    result["search_calls_used"] = session.search_calls_used
    result["n_ids_returned_this_session"] = len(session.returned_ids)
    result["search_trace"] = session.calls
    result["ids_returned_to_model"] = sorted(session.returned_ids)
    result["submitted_ids"] = list(submitted) if submitted is not None else []
    result["raw_model_response_hashes"] = raw_response_hashes
    return result


def treatment_record(*, fixture_id, kickoff_unix, fixture_universe, ctx, packet_hash,
                     capability_hash, corpus_vintage, result, model_id,
                     resolved_model_id=None, model_config_stamp=None,
                     cache_key=None, cache_hit=None, research_reason=None,
                     evidence_references=None) -> dict:
    """PHASE 4 -- the complete, immutable S-arm provenance record for ONE fixture.

    Everything that determined the treatment is frozen here. No prose becomes a numerical
    feature: `research_reason` is carried verbatim as TEXT and is never parsed, scored or
    turned into a covariate, and neither control arm can see it (see `controls.SonnetShape`,
    which has no prose field at all).
    """
    from src.research.hypothesis_v8c import pit_context as PC
    orch = result.get("orchestration") or {}
    return {
        # ---- identity of the measured thing -------------------------------------------
        "fixture_id": fixture_id,
        "kickoff_unix": int(kickoff_unix),
        "corpus_vintage": corpus_vintage,
        "capability_hash": capability_hash,
        "pit_context_hash": PC.context_hash(ctx),
        "universe_hash": CACHE.fixture_universe_hash(fixture_universe),
        "packet_hash": packet_hash,
        # ---- identity of the treatment ------------------------------------------------
        "requested_model_id": model_id,
        "resolved_model_id": resolved_model_id,
        "prompt_version": PROMPT_VERSION,
        "prompt_sha256": PROMPT_SHA256,
        "tool_schema_version": TOOL_SCHEMA_VERSION,
        "tool_schema_sha256": TOOL_SCHEMA_SHA256,
        "runner_version": RUNNER_VERSION,
        "orchestration_version": ORCHESTRATION_VERSION,
        "model_config_hash": (CACHE.model_config_hash(model_config_stamp)
                              if model_config_stamp is not None else None),
        "cache_key": cache_key,
        "cache_hit": cache_hit,
        # ---- what actually happened ----------------------------------------------------
        "converse_calls": orch.get("converse_calls"),
        "search_calls_attempted": orch.get("search_calls_attempted"),
        "search_calls_executed": orch.get("search_calls_executed"),
        "search_budget_exhausted": orch.get("search_budget_exhausted"),
        "forced_submit": orch.get("forced_submit"),
        "termination_reason": orch.get("termination_reason"),
        "search_queries": [c.get("query") for c in (result.get("search_trace") or [])],
        "ids_returned_to_model": result.get("ids_returned_to_model", []),
        # ---- the selection ---------------------------------------------------------------
        "submitted_ids": result.get("submitted_ids", []),
        "accepted_ids": result.get("accepted", []),
        "validation_status": result.get("status"),
        "validation_problems": result.get("problems", []),
        "research_yield": result.get("research_yield"),
        # ---- the reasoning, as TEXT, never as a feature -----------------------------------
        "research_reason": research_reason,
        "evidence_references": evidence_references or [],
        "prose_is_never_a_numerical_feature": True,
        "controls_can_read_prose": False,
        # ---- raw response binding ----------------------------------------------------------
        "raw_model_response_hashes": result.get("raw_model_response_hashes", []),
    }
