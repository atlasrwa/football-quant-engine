"""Byte-identical reruns. A deterministic transform that is not reproducible is not evidence."""
from __future__ import annotations

import hashlib
import json

from src.research.hypothesis_v8c import controls as CTL
from src.research.hypothesis_v8c import golden as G
from src.research.hypothesis_v8c import pit_context as PC
from src.research.hypothesis_v8c import select_freeze as SF
from src.research.hypothesis_v8c import universe as UNI

from .conftest import GOLDEN_METRICS, GRAMMAR_KW


def _sha(o):
    return hashlib.sha256(json.dumps(o, sort_keys=True, default=str).encode()).hexdigest()


def test_pit_context_is_byte_identical_across_rebuilds():
    env = G.build_environment(metrics=GOLDEN_METRICS)
    a = PC.build_pit_context(env.index, env.target_pos)
    b = PC.build_pit_context(env.index, env.target_pos)
    assert PC.context_hash(a) == PC.context_hash(b)


def test_universe_is_byte_identical_across_rebuilds(golden_env, golden_ctx):
    def build():
        return UNI.build_fixture_universe(
            golden_env.index, golden_env.target_pos, ctx=golden_ctx,
            capability=golden_env.capability, fixture_id=golden_env.target_fixture_id,
            grammar_kwargs=GRAMMAR_KW)
    a, b = build(), build()
    assert a.evaluable_ids() == b.evaluable_ids()
    assert _sha(a.ledger()) == _sha(b.ledger())
    assert _sha([c["hypothesis_id"] for c in a.evaluable]) == \
           _sha([c["hypothesis_id"] for c in b.evaluable])


def test_controls_are_byte_identical_across_reruns(golden_universe):
    shapes = [CTL.shape_of(c) for c in golden_universe.evaluable[:6]]
    a = CTL.blind_selections_for_fixture(shapes, golden_universe)
    b = CTL.blind_selections_for_fixture(shapes, golden_universe)
    assert _sha(a["pairs"]) == _sha(b["pairs"])
    h1 = CTL.heuristic_selections_for_fixture(6, golden_universe)
    h2 = CTL.heuristic_selections_for_fixture(6, golden_universe)
    assert [c["hypothesis_id"] for c in h1["selections"]] == \
           [c["hypothesis_id"] for c in h2["selections"]]


def test_freeze_hash_is_stable_across_reruns(golden_env):
    def build():
        return SF.select_cohort(golden_env.index, [golden_env.target_pos],
                                capability=golden_env.capability, k=3,
                                fixture_ids=[golden_env.target_fixture_id],
                                grammar_kwargs=GRAMMAR_KW, enforce_seal=False)
    a, b = build(), build()
    assert a["freeze_hash"] == b["freeze_hash"], "the freeze manifest is not reproducible"


def test_grammar_enumeration_order_is_stable(golden_env):
    def ids():
        return [ir.ir_id() for _s, ir in
                __import__("src.research.hypothesis_v8c.grammar", fromlist=["x"])
                .build_valid_irs(golden_env.capability, metrics=["goals"])]
    assert ids() == ids()
