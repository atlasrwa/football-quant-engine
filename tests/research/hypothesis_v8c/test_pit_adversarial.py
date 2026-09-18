"""PIT adversarial battery. Injected future information must produce ZERO behavioural change,
and a GENUINE prior row must produce a change -- otherwise the battery proves only that the
apparatus ignores its inputs."""
from __future__ import annotations

from src.research.hypothesis_v8c import golden as G
from src.research.hypothesis_v8c import pit_context as PC
from src.research.hypothesis_v8c import universe as UNI

from .conftest import GOLDEN_METRICS, GRAMMAR_KW


def _fingerprint(env):
    ctx = PC.build_pit_context(env.index, env.target_pos)
    fu = UNI.build_fixture_universe(env.index, env.target_pos, ctx=ctx,
                                    capability=env.capability,
                                    fixture_id=env.target_fixture_id,
                                    grammar_kwargs=GRAMMAR_KW)
    return {"context_hash": PC.context_hash(ctx),
            "evaluable_ids": fu.evaluable_ids(),
            "ledger": fu.ledger()}


def test_future_row_injection_changes_nothing():
    """Matches AFTER the target, with extreme values, must not move the pre-T verdict."""
    base = _fingerprint(G.build_environment(metrics=GOLDEN_METRICS))
    for n in (1, 5, 25):
        got = _fingerprint(G.build_environment(metrics=GOLDEN_METRICS,
                                               inject_future_rows=n))
        assert got["context_hash"] == base["context_hash"], (
            f"{n} future rows changed the PIT context")
        assert got["evaluable_ids"] == base["evaluable_ids"], (
            f"{n} future rows changed the evaluable universe")
        assert got["ledger"] == base["ledger"]


def test_target_outcome_mutation_changes_nothing():
    """Mutating the TARGET's own observed values must not move the pre-T verdict."""
    base = _fingerprint(G.build_environment(metrics=GOLDEN_METRICS))
    mutated = G.build_environment(metrics=GOLDEN_METRICS)
    tpos = mutated.target_pos
    rec = mutated.index.recs[tpos]
    for k in list(rec.base):
        rec.base[k] = 999                      # obliterate the target's observed statistics
    mutated.index.vals["goals"][tpos] = (999.0, 999.0)
    mutated.index.vals["yellow_cards"][tpos] = (999.0, 999.0)
    got = _fingerprint(mutated)
    assert got["context_hash"] == base["context_hash"]
    assert got["evaluable_ids"] == base["evaluable_ids"]
    assert got["ledger"] == base["ledger"]


def test_genuine_prior_row_DOES_change_the_verdict():
    """THE LIVE CONTROL. Without it, the two tests above would also pass on an apparatus that
    simply ignored the corpus."""
    base = _fingerprint(G.build_environment(n_prior_blocks=40, metrics=GOLDEN_METRICS))
    more = _fingerprint(G.build_environment(n_prior_blocks=60, metrics=GOLDEN_METRICS))
    assert more["context_hash"] != base["context_hash"], (
        "adding 20 blocks of genuine PRIOR history changed nothing -- the battery is inert")
    assert more["ledger"] != base["ledger"]


def test_context_cut_is_strictly_before_the_target():
    """Every cached profile must equal the mean over STRICTLY-PRIOR same-competition matches.

    Recomputed independently here rather than inspecting the raw series: the target's own row
    IS in the subject's series (that is what a series is), so the thing to prove is that it did
    not CONTRIBUTE, not that it is absent.
    """
    from src.research.hypothesis_v71 import invariants as INV
    env = G.build_environment(metrics=GOLDEN_METRICS)
    ctx = PC.build_pit_context(env.index, env.target_pos)
    assert ctx.cut_unix == int(env.index.kick[env.target_pos])

    checked = 0
    for (tid, comp, axis), cached in ctx.axis_cache.items():
        metric, side = INV.axis_metric_perspective(axis)
        if metric not in env.index.metrics:
            continue
        prior = [e for e in env.index.series[tid] if e[2] == comp and e[1] < ctx.cut_unix]
        vals = [env.index.team_value(i, tid, metric, side) for (i, _k, _c, _h, _o) in prior]
        vals = [v for v in vals if v is not None]
        assert vals, f"cell ({tid},{comp},{axis}) cached a value with no prior observations"
        assert abs(cached - sum(vals) / len(vals)) < 1e-12, (
            f"cell ({tid},{comp},{axis}) does not equal its strictly-prior mean")
        assert all(e[0] != env.target_pos for e in prior), (
            "the target's own row contributed to a profile")
        checked += 1
    assert checked > 0, "no profile cells were checked"
