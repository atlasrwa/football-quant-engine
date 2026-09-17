"""Termination-contract tests for the V8B.1 runner (BOUNDED_SEARCH_THEN_FORCED_SUBMIT).

These tests exercise the orchestration/termination contract ONLY -- transport, turn budget,
forced submission, abstention, and the never-fabricate guard -- using a fake Converse client.
They make NO network call, touch NO real model, and read NO target outcome. They deliberately
avoid the real capability/ontology objects by monkeypatching the search/prompt seams, so the
test asserts runner behavior, not football content.
"""
from __future__ import annotations

import json

import pytest
from src.research.hypothesis_v8b1 import runner as RN
from src.research.hypothesis_v8b1 import prompt as PR
from src.research.hypothesis_v8b1 import search as SE


MODEL = "us.anthropic.claude-sonnet-4-6"
REGION = "us-east-1"
CONFIG_STAMP = {"max_tokens": 8192, "temperature": 1.0,
                "thinking": {"type": "enabled", "budget_tokens": 4096}}


def _packet():
    return {"packet_hash": "deadbeef" * 8, "fixture": {"fixture_id": "mt_test0001"}}


class FakeConverse:
    """A scripted Bedrock Converse client. `script` is a list of callables; each receives the
    kwargs of the converse() call and returns a canned Bedrock-shaped response dict. Records
    every call's toolChoice and whether extended thinking was requested."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def converse(self, **kwargs):
        self.calls.append({
            "toolChoice": kwargs["toolConfig"]["toolChoice"],
            "has_thinking": "thinking" in (kwargs.get("additionalModelRequestFields") or {}),
        })
        fn = self.script.pop(0)
        return fn(kwargs)


def _search_use(tool_use_id, **inp):
    return {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": tool_use_id, "name": "search_hypotheses", "input": inp}}]}},
        "stopReason": "tool_use", "usage": {"inputTokens": 100, "outputTokens": 10,
                                            "totalTokens": 110}}


def _submit_use(tool_use_id, selections, trace=None):
    return {"output": {"message": {"role": "assistant", "content": [
        {"toolUse": {"toolUseId": tool_use_id, "name": "submit_selections",
                     "input": {"final_selections": selections,
                               "research_trace": trace or {"note": "t"}}}}]}},
        "stopReason": "tool_use", "usage": {"inputTokens": 100, "outputTokens": 10,
                                            "totalTokens": 110}}


def _no_tool_end(kwargs=None):
    return {"output": {"message": {"role": "assistant", "content": [{"text": "done"}]}},
            "stopReason": "end_turn", "usage": {"inputTokens": 5, "outputTokens": 5,
                                                "totalTokens": 10}}


@pytest.fixture(autouse=True)
def _patch_seams(monkeypatch, tmp_path):
    # No network, no real prompt/search dependencies, isolated cache dir.
    monkeypatch.setattr(PR, "prompt_content_hash", lambda: "prompthash")
    monkeypatch.setattr(PR, "system_prompt", lambda: "SYS")
    monkeypatch.setattr(PR, "tool_specs", lambda: [
        {"name": "search_hypotheses", "description": "d", "inputSchema": {"json": {}}},
        {"name": "submit_selections", "description": "d", "inputSchema": {"json": {}}},
    ])
    monkeypatch.setattr(RN, "CACHE_DIR", str(tmp_path / "cache"))
    yield


def _run(fake, returned_ids=None, resolvable=True):
    """Wire the fake client + a search/resolve stub, then run one fixture."""
    ids = returned_ids if returned_ids is not None else ["idA", "idB"]

    def fake_search(query, capability):
        return [{"hypothesis_id": hid} for hid in ids]

    def fake_resolve(hid, capability):
        return object() if (resolvable and hid in ids) else None

    import contextlib
    with contextlib.ExitStack() as stack:
        stack.enter_context(_patched(SE, "search", fake_search))
        stack.enter_context(_patched(SE, "resolve", fake_resolve))
        stack.enter_context(_patched(RN, "_bedrock_client", lambda region: fake))
        return RN.run_fixture(_packet(), capability=None, model_id=MODEL, region=REGION,
                              config_stamp=CONFIG_STAMP, use_cache=False)


import contextlib


@contextlib.contextmanager
def _patched(obj, name, val):
    old = getattr(obj, name)
    setattr(obj, name, val)
    try:
        yield
    finally:
        setattr(obj, name, old)


# ---------------------------------------------------------------------------

def test_mechanical_turn_ceiling():
    assert RN.MAX_TOOL_TURNS == RN.MAX_SEARCH_CALLS + RN.FINAL_FORCED_SUBMIT_CALLS
    assert RN.MAX_SEARCH_CALLS == 6
    assert RN.FINAL_FORCED_SUBMIT_CALLS == 1
    assert RN.MAX_TOOL_TURNS == 7  # not an arbitrary large number


def test_early_submit_accepted_immediately():
    fake = FakeConverse([
        lambda k: _search_use("t1", target_metric="goals"),
        lambda k: _submit_use("t2", [{"hypothesis_id": "idA"}]),
    ])
    r = _run(fake)
    assert r.status == "OK"
    assert r.manifest["termination_reason"] == "EARLY_SUBMIT"
    assert r.manifest["search_calls"] == 1
    assert r.manifest["converse_calls"] == 2
    # never forced thinking off on an early (auto) turn
    assert all(c["toolChoice"] == {"auto": {}} for c in fake.calls)
    assert all(c["has_thinking"] for c in fake.calls)


def test_bounded_search_then_forced_submit():
    # 6 auto turns each doing one search, then a 7th FORCED turn that submits.
    script = [(lambda k: _search_use(f"s{i}", target_metric="goals")) for i in range(6)]
    script.append(lambda k: _submit_use("final", [{"hypothesis_id": "idA"},
                                                   {"hypothesis_id": "idB"}]))
    fake = FakeConverse(script)
    r = _run(fake)
    assert r.status == "OK"
    assert r.manifest["termination_reason"] == "FORCED_SUBMIT"
    assert r.manifest["search_calls"] == 6
    assert r.manifest["converse_calls"] == 7
    # the LAST call must be the forced submit with thinking DISABLED
    assert fake.calls[-1]["toolChoice"] == {"tool": {"name": "submit_selections"}}
    assert fake.calls[-1]["has_thinking"] is False
    # earlier calls were auto + thinking on
    assert all(c["toolChoice"] == {"auto": {}} and c["has_thinking"] for c in fake.calls[:-1])


def test_abstain_is_valid_ok_abstain():
    # forced turn returns ZERO selections -> OK_ABSTAIN, not an error, not fabricated.
    script = [(lambda k: _search_use(f"s{i}", target_metric="goals")) for i in range(6)]
    script.append(lambda k: _submit_use("final", []))
    r = _run(FakeConverse(script))
    assert r.status == "OK_ABSTAIN"
    assert r.final_selections == []
    assert r.manifest["termination_reason"] == "FORCED_SUBMIT"


def test_unknown_hypothesis_id_rejected_never_fabricated():
    # model searches (returns idA), then submits an id the search tool never returned.
    fake = FakeConverse([lambda k: _search_use("s0", target_metric="goals"),
                         lambda k: _submit_use("t1", [{"hypothesis_id": "ghost"}])])
    r = _run(fake, returned_ids=["idA"])  # 'ghost' not returned
    assert r.status == "INVALID_UNKNOWN_HYPOTHESIS_ID"
    assert r.final_selections == []
    assert r.manifest["validation_problems"]


def test_resolvable_but_not_returned_is_rejected():
    fake = FakeConverse([lambda k: _search_use("s0", target_metric="goals"),
                         lambda k: _submit_use("t1", [{"hypothesis_id": "idZ"}])])
    # idZ resolvable in principle, but never returned this session -> still rejected.
    r = _run(fake, returned_ids=["idA"], resolvable=True)
    assert r.status == "INVALID_UNKNOWN_HYPOTHESIS_ID"


def test_forced_submit_not_produced_is_orchestration_failure():
    # 6 searches, then the forced turn returns a search instead of a submission.
    script = [(lambda k: _search_use(f"s{i}", target_metric="goals")) for i in range(6)]
    script.append(lambda k: _search_use("still_searching", target_metric="goals"))
    r = _run(FakeConverse(script))
    assert r.status == "ORCHESTRATION_FORCED_SUBMIT_FAILED"
    assert r.final_selections == []
    assert r.manifest["termination_reason"] == "FORCED_SUBMIT_NOT_PRODUCED"


def test_transport_exception_is_llm_state_unavailable():
    def boom(k):
        raise RuntimeError("Read timeout on endpoint")
    r = _run(FakeConverse([boom]))
    assert r.status == "LLM_STATE_UNAVAILABLE"
    assert r.manifest["termination_reason"] == "TRANSPORT_FAILURE"
    assert r.manifest["call_state"] == "UNKNOWN_AFTER_SEND"


def test_accounting_counts_multiple_searches_per_turn():
    # one turn with THREE searches, then submit; search_calls must be 3 (not 1).
    def three_searches(k):
        c = [{"toolUse": {"toolUseId": f"m{i}", "name": "search_hypotheses",
                          "input": {"target_metric": "goals"}}} for i in range(3)]
        return {"output": {"message": {"role": "assistant", "content": c}},
                "stopReason": "tool_use",
                "usage": {"inputTokens": 300, "outputTokens": 30, "totalTokens": 330}}
    fake = FakeConverse([three_searches,
                         lambda k: _submit_use("t2", [{"hypothesis_id": "idA"}])])
    r = _run(fake)
    assert r.status == "OK"
    assert r.manifest["search_calls"] == 3
    assert r.manifest["converse_calls"] == 2
    assert r.manifest["usage"]["totalTokens"] == 330 + 110


def test_end_turn_without_tool_is_invalid_no_submission():
    r = _run(FakeConverse([_no_tool_end]))
    assert r.status == "INVALID_NO_SUBMISSION"
    assert r.manifest["termination_reason"] == "ENDED_WITHOUT_TOOL"


def test_cache_written_and_rehit_without_client(tmp_path, monkeypatch):
    # An OK result is cached; a second run with a client that would explode is served from cache.
    monkeypatch.setattr(PR, "prompt_content_hash", lambda: "prompthash")
    monkeypatch.setattr(PR, "system_prompt", lambda: "SYS")
    monkeypatch.setattr(PR, "tool_specs", lambda: [
        {"name": "search_hypotheses", "description": "d", "inputSchema": {"json": {}}},
        {"name": "submit_selections", "description": "d", "inputSchema": {"json": {}}}])
    monkeypatch.setattr(RN, "CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setattr(SE, "search", lambda q, c: [{"hypothesis_id": "idA"}])
    monkeypatch.setattr(SE, "resolve", lambda h, c: object())

    fake1 = FakeConverse([lambda k: _search_use("s0", target_metric="goals"),
                          lambda k: _submit_use("t1", [{"hypothesis_id": "idA"}])])
    monkeypatch.setattr(RN, "_bedrock_client", lambda region: fake1)
    r1 = RN.run_fixture(_packet(), None, model_id=MODEL, region=REGION,
                        config_stamp=CONFIG_STAMP, use_cache=True)
    assert r1.status == "OK" and r1.manifest["cache_hit"] is False

    def explode(region):
        raise AssertionError("cache miss: should not build a client on re-run")
    monkeypatch.setattr(RN, "_bedrock_client", explode)
    r2 = RN.run_fixture(_packet(), None, model_id=MODEL, region=REGION,
                        config_stamp=CONFIG_STAMP, use_cache=True)
    assert r2.status == "OK" and r2.manifest["cache_hit"] is True
