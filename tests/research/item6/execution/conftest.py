"""Network kill-switch + shared fixtures for the Item 6 execution amendment tests.

Any non-loopback outbound socket connect raises. Zero real Bedrock calls are possible; the
runner is exercised only with deterministic local stand-ins. A module-level counter records
that zero non-loopback connects occurred so a test can assert it.
"""
from __future__ import annotations

import socket

import pytest

NON_LOOPBACK_CONNECTS = {"count": 0}
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "0.0.0.0"}
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex


def _host_of(address):
    if isinstance(address, tuple):
        return address[0]
    return str(address)


def _blocked_connect(self, address, *a, **k):
    host = _host_of(address)
    if host not in _LOOPBACK:
        NON_LOOPBACK_CONNECTS["count"] += 1
        raise RuntimeError(f"NETWORK_BLOCKED_ITEM6_EXEC_TEST: connect to {address}")
    return _real_connect(self, address, *a, **k)


def _blocked_connect_ex(self, address, *a, **k):
    host = _host_of(address)
    if host not in _LOOPBACK:
        NON_LOOPBACK_CONNECTS["count"] += 1
        raise RuntimeError(f"NETWORK_BLOCKED_ITEM6_EXEC_TEST: connect_ex to {address}")
    return _real_connect_ex(self, address, *a, **k)


@pytest.fixture(autouse=True)
def _network_kill_switch(monkeypatch):
    monkeypatch.setattr(socket.socket, "connect", _blocked_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _blocked_connect_ex)
    yield


@pytest.fixture
def sample_fixture():
    return {
        "fixture_id": "i6_test_0001",
        "home_id": "406",
        "away_id": "425",
        "competition": "comp_16572",
        "kickoff_unix": 1781352000,
    }


def good_converse_response(input_tokens: int = 6000, output_tokens: int = 1500):
    """A trustworthy Converse envelope stand-in (never touches the network)."""
    return {
        "output": {"message": {"role": "assistant", "content": [
            {"toolUse": {"name": "emit_item6_mechanisms",
                         "input": {"fixture_id": "i6_test_0001", "mechanisms": []}}}]}},
        "stopReason": "tool_use",
        "usage": {"inputTokens": input_tokens, "outputTokens": output_tokens,
                  "totalTokens": input_tokens + output_tokens},
        "modelId": "us.anthropic.claude-sonnet-4-6",
        "_resolved_model_id": "anthropic.claude-sonnet-4-6",
    }


# v2 amendment: a deterministic local CountTokens stand-in. It NEVER touches the network and
# returns only an input-token count (no generation), mirroring the AWS Bedrock CountTokens
# control operation. `make_count_fn` lets a test fix the provider count it wants to exercise.
DEFAULT_PROVIDER_COUNTED_INPUT_TOKENS = 6500


def make_count_fn(input_tokens: int = DEFAULT_PROVIDER_COUNTED_INPUT_TOKENS):
    """Return a CountTokens stand-in fn(modelId=..., input=...) -> {'inputTokens': n}."""
    def _count(modelId, input):  # noqa: A002  match boto3 kwarg name
        assert isinstance(modelId, str) and modelId
        assert "converse" in input and "toolConfig" in input["converse"]
        return {"inputTokens": input_tokens}
    return _count


def good_count_fn(modelId, input):  # noqa: A002  match boto3 kwarg name
    """Default healthy CountTokens stand-in used by the legacy execution tests."""
    return {"inputTokens": DEFAULT_PROVIDER_COUNTED_INPUT_TOKENS}
