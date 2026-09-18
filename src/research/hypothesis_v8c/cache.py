"""V8C cache identity (`v8c_cache_v1`) -- repairs P1 CACHE.

THE DEFECT
----------
`hypothesis_v8b1.runner._cache_key` bound a cached model response to only:

    model_id | config_stamp | prompt_hash | packet_hash

Everything else that determines what the model was actually ASKED was invisible to the key:
the tool schemas, the candidate universe the search tool would answer from, the PIT context
those candidates were derived from, and the search/runner/orchestration code versions. Under
V8C every one of those changed -- new grammar, new profile semantic, paginated search, new
projection -- while `packet_hash` and `prompt_hash` could easily stay equal. A V8B.1 cache
entry could therefore satisfy a V8C request and silently reintroduce V8B.1's universe into a
V8C result.

THE REPAIR
----------
A NEW NAMESPACE (`out/v8c_cache/`, never V8B.1's directory) and an identity bound to every
input that can change the model's task:

    model_id                 what we asked for
    resolved_model_id        what Bedrock actually served     <- silent-substitution guard
    prompt_hash              the research prompt
    tool_schema_hash         the tool contract
    packet_hash              the evidence
    pit_context_hash         the PIT frontier the candidates came from
    fixture_universe_hash    the exact candidate set the search tool can return
    search_version           pagination/projection semantics
    runner_version           orchestration loop
    orchestration_version    termination contract
    model_config_hash        temperature, thinking budget, maxTokens, ...
    cache_namespace          "v8c" -- a V8B key can never collide by construction

A cached entry is REFUSED unless every one of those matches. The namespace alone makes
cross-version poisoning impossible; the field list makes within-V8C drift impossible too.

ZERO SPEND. This module performs no model call.
"""
from __future__ import annotations

import hashlib
import json
import os

CACHE_VERSION = "v8c_cache_v1"
CACHE_NAMESPACE = "v8c"

#: Deliberately NOT `out/v8b1_cache`. A V8B.1 entry is not merely invalidated, it is
#: unreachable.
CACHE_DIR = "/home/ubuntu/research/hypothesis_engine/out/v8c_cache"

V8B1_CACHE_DIR = "/home/ubuntu/research/hypothesis_engine/out/v8b1_cache"

#: Every field that must match for a cached response to be served.
IDENTITY_FIELDS = ("cache_namespace", "model_id", "resolved_model_id", "prompt_hash",
                   "tool_schema_hash", "packet_hash", "pit_context_hash",
                   "fixture_universe_hash", "search_version", "runner_version",
                   "orchestration_version", "model_config_hash")


class CacheIdentityError(Exception):
    """A cached entry does not match the requested identity. It is refused, never served."""


def _sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, default=str).encode()).hexdigest()


def fixture_universe_hash(fixture_universe) -> str:
    """Bind the cache to the EXACT candidate set the search tool can return.

    Hashes the ordered evaluable ids, so any grammar, profile-semantic or evaluability change
    that moves a single candidate changes the key.
    """
    return _sha({"fixture_id": fixture_universe.fixture_id,
                 "evaluable_ids": list(fixture_universe.evaluable_ids()),
                 "ledger": fixture_universe.ledger()})


def tool_schema_hash(tool_schemas) -> str:
    return _sha(tool_schemas)


def model_config_hash(config_stamp) -> str:
    return _sha(config_stamp)


def build_identity(*, model_id, resolved_model_id, prompt_hash, tool_schema_hash,
                   packet_hash, pit_context_hash, fixture_universe_hash,
                   search_version, runner_version, orchestration_version,
                   model_config_hash) -> dict:
    ident = {"cache_namespace": CACHE_NAMESPACE, "model_id": model_id,
             "resolved_model_id": resolved_model_id, "prompt_hash": prompt_hash,
             "tool_schema_hash": tool_schema_hash, "packet_hash": packet_hash,
             "pit_context_hash": pit_context_hash,
             "fixture_universe_hash": fixture_universe_hash,
             "search_version": search_version, "runner_version": runner_version,
             "orchestration_version": orchestration_version,
             "model_config_hash": model_config_hash}
    missing = [f for f in IDENTITY_FIELDS if ident.get(f) in (None, "")]
    if missing:
        raise CacheIdentityError(f"cache identity is incomplete: {missing}")
    return ident


def cache_key(identity: dict) -> str:
    return _sha({f: identity[f] for f in IDENTITY_FIELDS})


def cache_path(key: str) -> str:
    return os.path.join(CACHE_DIR, f"{key}.json")


def load(identity: dict):
    """Serve a cached response ONLY if every identity field matches. Fails closed."""
    key = cache_key(identity)
    p = cache_path(key)
    if not os.path.exists(p):
        return None
    payload = json.load(open(p))
    stored = payload.get("cache_identity") or {}
    if stored.get("cache_namespace") != CACHE_NAMESPACE:
        raise CacheIdentityError(
            f"entry {key} is from namespace {stored.get('cache_namespace')!r}, not "
            f"{CACHE_NAMESPACE!r} -- refusing to serve")
    mismatched = [f for f in IDENTITY_FIELDS if stored.get(f) != identity.get(f)]
    if mismatched:
        raise CacheIdentityError(
            f"entry {key} mismatches on {mismatched} -- refusing to serve")
    return payload


def save(identity: dict, payload: dict) -> str:
    key = cache_key(identity)
    os.makedirs(CACHE_DIR, exist_ok=True)
    body = dict(payload)
    body["cache_identity"] = dict(identity)
    tmp = cache_path(key) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(body, f, indent=1, default=str, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, cache_path(key))
    return key


def assert_isolated_from_v8b1() -> dict:
    """Evidence that no V8B.1 entry can satisfy a V8C request."""
    return {"v8c_cache_dir": CACHE_DIR, "v8b1_cache_dir": V8B1_CACHE_DIR,
            "directories_distinct": os.path.abspath(CACHE_DIR)
            != os.path.abspath(V8B1_CACHE_DIR),
            "namespace": CACHE_NAMESPACE,
            "v8b1_entries_present": (len(os.listdir(V8B1_CACHE_DIR))
                                     if os.path.isdir(V8B1_CACHE_DIR) else 0),
            "v8b1_entries_reachable_from_v8c": False}


def version_stamp() -> dict:
    return {"cache_version": CACHE_VERSION, "repairs": ["P1-CACHE"],
            "namespace": CACHE_NAMESPACE, "cache_dir": CACHE_DIR,
            "identity_fields": list(IDENTITY_FIELDS),
            "v8b1_identity_fields": ["model_id", "config_stamp", "prompt_hash",
                                     "packet_hash"],
            "fields_added_vs_v8b1": ["resolved_model_id", "tool_schema_hash",
                                     "pit_context_hash", "fixture_universe_hash",
                                     "search_version", "runner_version",
                                     "orchestration_version", "cache_namespace"],
            "fails_closed_on_mismatch": True,
            "v8b1_cache_can_satisfy_a_v8c_request": False}
