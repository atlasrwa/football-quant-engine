"""Gate-A Phases 1/3/4: the REAL tool loop, driven by a mocked Converse client.

No live Bedrock call. No network. No spend. The mock has the Bedrock Converse response shape,
so what these tests exercise is the same orchestration a paid run would execute -- only the
transport is substituted (dependency injection).
"""
from __future__ import annotations

import pytest

from src.research.hypothesis_v8c import prompt as PROMPT
from src.research.hypothesis_v8c import runner as R

MODEL = "us.anthropic.claude-sonnet-4-6"


# ------------------------------------------------------------------ mock Converse client
def _use(name, tool_input, use_id="tu1"):
    return {"output": {"message": {"role": "assistant",
                                   "content": [{"toolUse": {"toolUseId": use_id,
                                                            "name": name,
                                                            "input": tool_input}}]}},
            "stopReason": "tool_use", "usage": {"inputTokens": 10, "outputTokens": 5}}


def _text(t="done"):
    return {"output": {"message": {"role": "assistant", "content": [{"text": t}]}},
            "stopReason": "end_turn", "usage": {"inputTokens": 10, "outputTokens": 5}}


class MockConverse:
    """Replays a scripted list of responses and records what it was sent."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def __call__(self, **kw):
        self.calls.append(kw)
        if not self.script:
            return _text()
        nxt = self.script.pop(0)
        return nxt(self) if callable(nxt) else nxt


@pytest.fixture(scope="module")
def uni(golden_universe):
    return golden_universe


def _ids(uni, n):
    return [c["hypothesis_id"] for c in uni.evaluable[:n]]


def _run(uni, capability, script, **kw):
    mock = MockConverse(script)
    res = R.run_fixture_converse(uni, capability, converse=mock, packet="PACKET",
                                 model_id=MODEL, **kw)
    return res, mock


# ------------------------------------------------------------------ the loop itself
def test_tool_loop_executes_searches_then_submits(uni, golden_env):
    script = [_use("search_hypotheses", {"target_metric": "goals"}),
              _use("search_hypotheses", {"target_metric": "goals", "max_results": 5}),
              lambda m: _use("submit_selections",
                             {"hypothesis_ids": _ids(uni, 2),
                              "research_reason": "corners against similar defences"})]
    res, mock = _run(uni, golden_env.capability, script)
    assert res["status"] == R.OK
    assert len(res["accepted"]) == 2
    o = res["orchestration"]
    assert o["search_calls_executed"] == 2
    assert o["converse_calls"] == 3
    assert o["termination_reason"] == R.TERM_SUBMITTED
    assert o["search_budget_exhausted"] is False


def test_runner_sends_the_frozen_prompt_and_tool_schema(uni, golden_env):
    res, mock = _run(uni, golden_env.capability,
                     [_use("submit_selections", {"hypothesis_ids": []})])
    sent = mock.calls[0]
    assert sent["system"] == [{"text": PROMPT.SYSTEM_PROMPT}]
    names = [t["toolSpec"]["name"] for t in sent["toolConfig"]["tools"]]
    assert names == ["search_hypotheses", "submit_selections"]
    assert sent["modelId"] == MODEL
    assert res["status"] == R.OK_ABSTAIN


def test_search_backend_is_v8c_not_v8b1(uni, golden_env):
    """Every id handed to the model came from this fixture's V8C evaluable universe."""
    res, _ = _run(uni, golden_env.capability,
                  [_use("search_hypotheses", {}),
                   _use("submit_selections", {"hypothesis_ids": []})])
    evaluable = set(uni.evaluable_ids())
    assert res["ids_returned_to_model"], "search returned nothing to the model"
    assert set(res["ids_returned_to_model"]) <= evaluable


# ------------------------------------------------------------------ the search cap
def test_seventh_search_does_not_execute_and_forces_submit(uni, golden_env):
    script = [_use("search_hypotheses", {}) for _ in range(7)]
    script.append(_use("submit_selections", {"hypothesis_ids": []}))
    res, _ = _run(uni, golden_env.capability, script)
    o = res["orchestration"]
    assert o["search_calls_attempted"] == 7
    assert o["search_calls_executed"] == R.MAX_SEARCH_CALLS == 6, "a 7th search executed"
    assert o["search_budget_exhausted"] is True
    assert o["forced_submit"] is True
    assert o["termination_reason"] == R.TERM_FORCED_SUBMIT
    assert res["status"] == R.OK_ABSTAIN


def test_budget_exhausted_is_deterministic(uni, golden_env):
    session = R.SearchSession(fixture_universe=uni)
    for _ in range(R.MAX_SEARCH_CALLS):
        assert session.search({})["status"] == "OK"
    for _ in range(3):
        page = session.search({})
        assert page["status"] == R.SEARCH_BUDGET_EXHAUSTED
        assert page["results"] == []
    assert session.search_calls_used == R.MAX_SEARCH_CALLS


# ------------------------------------------------------------------ Phase 3: the 9 cases
def test_zero_selections_is_a_legal_abstention(uni, golden_env):
    res, _ = _run(uni, golden_env.capability,
                  [_use("submit_selections", {"hypothesis_ids": []})])
    assert res["status"] == R.OK_ABSTAIN
    assert res["accepted"] == []
    assert res["research_yield"]["abstained"] is True


def test_eight_selections_accepted(uni, golden_env):
    script = [_use("search_hypotheses", {"max_results": 50}),
              lambda m: _use("submit_selections", {"hypothesis_ids": _ids(uni, 8)})]
    res, _ = _run(uni, golden_env.capability, script)
    assert res["status"] == R.OK
    assert len(res["accepted"]) == R.MAX_SELECTIONS == 8


def test_nine_selections_rejected_entirely(uni, golden_env):
    script = [_use("search_hypotheses", {"max_results": 50}),
              lambda m: _use("submit_selections", {"hypothesis_ids": _ids(uni, 9)})]
    res, _ = _run(uni, golden_env.capability, script)
    assert res["status"] == R.INVALID_SUBMISSION
    assert res["accepted"] == []
    assert any(p["reason"] == R.REASON_OVER_CAP for p in res["problems"])


def test_duplicate_ids_rejected_entirely(uni, golden_env):
    one = _ids(uni, 1)[0]
    script = [_use("search_hypotheses", {"max_results": 50}),
              lambda m: _use("submit_selections", {"hypothesis_ids": [one, one]})]
    res, _ = _run(uni, golden_env.capability, script)
    assert res["status"] == R.INVALID_SUBMISSION
    assert res["accepted"] == []
    assert any(p["reason"] == R.REASON_DUPLICATE for p in res["problems"])


def test_valid_plus_fabricated_accepts_nothing(uni, golden_env):
    """The all-or-nothing rule: a good id is NOT silently retained beside a fabricated one."""
    good = _ids(uni, 1)[0]
    script = [_use("search_hypotheses", {"max_results": 50}),
              lambda m: _use("submit_selections",
                             {"hypothesis_ids": [good, "hyp_TOTALLY_INVENTED"]})]
    res, _ = _run(uni, golden_env.capability, script)
    assert res["status"] == R.INVALID_SUBMISSION
    assert res["accepted"] == [], "partial acceptance leaked a valid id through"
    assert R.PARTIAL_ACCEPTANCE is False
    assert res["research_yield"]["rejected"] == 2


def test_unreturned_real_id_is_rejected(uni, golden_env):
    """A REAL evaluable id the search never surfaced this session is still rejected."""
    script = [_use("submit_selections", {"hypothesis_ids": _ids(uni, 1)})]
    res, _ = _run(uni, golden_env.capability, script)
    assert res["status"] == R.INVALID_SUBMISSION
    assert any(p["reason"] == R.REASON_NOT_RETURNED for p in res["problems"])


def test_id_from_an_old_session_is_rejected(uni, golden_env):
    """Ids are registered per SESSION: a previous fixture's session does not carry over."""
    first, _ = _run(uni, golden_env.capability,
                    [_use("search_hypotheses", {"max_results": 50}),
                     _use("submit_selections", {"hypothesis_ids": []})])
    carried = first["ids_returned_to_model"][0]
    res, _ = _run(uni, golden_env.capability,
                  [_use("submit_selections", {"hypothesis_ids": [carried]})])
    assert res["status"] == R.INVALID_SUBMISSION
    assert any(p["reason"] == R.REASON_NOT_RETURNED for p in res["problems"])


def test_other_fixture_id_is_rejected(uni, golden_env, multi_env):
    """An id evaluable at a DIFFERENT fixture is not evaluable here."""
    from src.research.hypothesis_v8c import pit_context as PC
    from src.research.hypothesis_v8c import universe as UNI
    other_pos = multi_env.target_positions[-1]
    other_ctx = PC.build_pit_context(multi_env.index, other_pos)
    other = UNI.build_fixture_universe(
        multi_env.index, other_pos, ctx=other_ctx, capability=multi_env.capability,
        fixture_id=multi_env.target_fixture_ids[-1],
        grammar_kwargs={"metrics": list(multi_env.metrics)})
    foreign = [c["hypothesis_id"] for c in other.evaluable
               if c["hypothesis_id"] not in set(uni.evaluable_ids())]
    if not foreign:
        pytest.skip("the two fixtures' universes coincide in this environment")
    res, _ = _run(uni, golden_env.capability,
                  [_use("submit_selections", {"hypothesis_ids": foreign[:1]})])
    assert res["status"] == R.INVALID_SUBMISSION


def test_malformed_tool_input_is_invalid_not_abstention(uni, golden_env):
    res, _ = _run(uni, golden_env.capability,
                  [_use("submit_selections", {"research_reason": "forgot the ids"})])
    assert res["status"] == R.INVALID_SUBMISSION
    assert res["research_yield"]["abstained"] is False
    assert res["orchestration"]["termination_reason"] == R.TERM_MALFORMED_TOOL_USE


def test_ending_without_submitting_is_invalid_not_abstention(uni, golden_env):
    res, _ = _run(uni, golden_env.capability, [_text("I have nothing to add.")])
    assert res["status"] == R.INVALID_SUBMISSION
    assert res["orchestration"]["termination_reason"] == R.TERM_NO_SUBMISSION
    assert res["research_yield"]["abstained"] is False


def test_unknown_tool_is_malformed(uni, golden_env):
    res, _ = _run(uni, golden_env.capability, [_use("place_a_bet", {"stake": 10})])
    assert res["status"] == R.INVALID_SUBMISSION
    assert res["orchestration"]["termination_reason"] == R.TERM_MALFORMED_TOOL_USE


# ------------------------------------------------------------------ Phase 4: provenance
def test_complete_treatment_provenance_is_emitted(uni, golden_env, golden_ctx):
    script = [_use("search_hypotheses", {"target_metric": "goals"}),
              lambda m: _use("submit_selections",
                             {"hypothesis_ids": _ids(uni, 1),
                              "research_reason": "attack vs concession tension"})]
    res, _ = _run(uni, golden_env.capability, script,
                  resolved_model_id="arn:aws:bedrock:::model/sonnet",
                  model_config_stamp={"temperature": 0, "top_p": 1})
    rec = R.treatment_record(
        fixture_id=golden_env.target_fixture_id,
        kickoff_unix=golden_env.index.recs[golden_env.target_pos].kickoff_unix,
        fixture_universe=uni, ctx=golden_ctx, packet_hash="PACKETHASH",
        capability_hash="CAPHASH", corpus_vintage={"n_records": 1},
        result=res, model_id=MODEL, resolved_model_id="arn:aws:bedrock:::model/sonnet",
        model_config_stamp={"temperature": 0, "top_p": 1},
        cache_key="ck", cache_hit=False, research_reason="attack vs concession tension")

    required = [
        "fixture_id", "kickoff_unix", "corpus_vintage", "capability_hash",
        "pit_context_hash", "universe_hash", "packet_hash",
        "requested_model_id", "resolved_model_id",
        "prompt_version", "prompt_sha256", "tool_schema_version", "tool_schema_sha256",
        "runner_version", "orchestration_version", "model_config_hash",
        "cache_key", "cache_hit",
        "converse_calls", "search_calls_attempted", "search_calls_executed",
        "search_budget_exhausted", "termination_reason",
        "search_queries", "ids_returned_to_model",
        "submitted_ids", "accepted_ids", "validation_status",
        "research_reason", "evidence_references", "raw_model_response_hashes",
    ]
    missing = [k for k in required if k not in rec]
    assert not missing, f"treatment provenance is missing {missing}"
    assert rec["prompt_sha256"] == PROMPT.PROMPT_SHA256
    assert rec["tool_schema_sha256"] == PROMPT.TOOL_SCHEMA_SHA256
    assert rec["raw_model_response_hashes"], "raw model response was not bound"
    assert rec["prose_is_never_a_numerical_feature"] is True
    assert rec["controls_can_read_prose"] is False


def test_no_live_bedrock_call_is_possible_here():
    """The runner never constructs a client; the transport is always injected."""
    import inspect

    from src.research.hypothesis_v8c import runner as mod
    src = inspect.getsource(mod)
    for banned in ("import boto3", "from boto3", "boto3.client", "botocore"):
        assert banned not in src, f"runner references {banned}"
    assert "converse" in inspect.signature(mod.run_fixture_converse).parameters
