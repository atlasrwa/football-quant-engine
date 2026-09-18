"""The V8C compiler is a COPY of the frozen one with a single predicate changed. This bounds
the blast radius of that copy: for every hypothesis WITHOUT an opponent_profile condition, the
two must agree exactly."""
from __future__ import annotations

from src.research.hypothesis_v71 import compiler as FROZEN
from src.research.hypothesis_v71 import engine as ENG
from src.research.hypothesis_v71 import ir as IRM
from src.research.hypothesis_v8c import compiler as V8C
from src.research.hypothesis_v8c import grammar as GR


def _flat_ctx(ctx):
    """The frozen compiler wants a 2-tuple axis cache; V8C's is 3-tuple. For hypotheses with no
    profile condition neither is consulted, which is exactly what makes them comparable."""
    return {}, {}


def test_identical_without_opponent_profile(golden_env, golden_ctx):
    """Byte-identical CompiledQuery for every non-profile hypothesis that compiles."""
    ter, cache = _flat_ctx(golden_ctx)
    compared = 0
    for spec, ir in GR.build_valid_irs(golden_env.capability, metrics=["goals"]):
        if any(c.get("dimension") == "opponent_profile" for c in spec["conditions"]):
            continue
        rec = ENG.recency_family_for(ir)
        kw = dict(metric="goals", terciles=ter, axis_cache=cache,
                  similarity=golden_ctx.similarity, capability=golden_env.capability,
                  collect_fixtures=True)
        try:
            a = FROZEN.compile_query(ir, golden_env.index, golden_env.target_pos,
                                     recency=rec[0], **kw)
        except Exception as ea:
            try:
                V8C.compile_query(ir, golden_env.index, golden_env.target_pos,
                                  recency=rec[0], **kw)
            except Exception as eb:
                assert type(ea) is type(eb) and str(ea) == str(eb), (
                    f"refusal diverged for {ir.ir_id()}: {ea!r} vs {eb!r}")
                compared += 1
                continue
            raise AssertionError(f"frozen refused but v8c compiled: {ir.ir_id()}")
        b = V8C.compile_query(ir, golden_env.index, golden_env.target_pos,
                              recency=rec[0], **kw)
        assert a == b, f"CompiledQuery diverged for {ir.ir_id()}"
        compared += 1
    assert compared > 50, f"equivalence checked too few hypotheses ({compared})"


def test_profile_semantic_is_competition_and_H_time_coherent():
    """Both rounds of the repair: per competition (round 1) and strictly before H (P1-K)."""
    assert V8C.PROFILE_SEMANTIC == "(team, competition, axis, strictly-before-H)"
    st = V8C.version_stamp()
    assert st["profile_and_terciles_both_as_of_H"] is True
    assert "P1-K" in st["repairs_round_2"]
