"""V7.1 control universes (`v71_controls_v1`). Section 15.

Two frozen control pools, rebuilt under the hardened semantic IR rather than inherited from
V7's matching:

  **Endpoint A -- END-TO-END RESEARCH YIELD.** A UNIFORM pool over the whole structural
  grammar. It deliberately does NOT copy the LLM's metric preferences: the point of the
  end-to-end endpoint is to ask whether an LLM's choice of what to ask about beats blind
  enumeration, and a control that inherits those choices cannot answer that.

  **Endpoint B -- CONDITIONAL SIGNAL QUALITY.** A MARGINAL pool drawn from the treated arm's
  own structural marginals, then matched and weighted. It conditions on genuine measurability
  and support, never on an outcome. Controls buy matching FLEXIBILITY; they never become
  thousands of independent votes -- the inferential unit stays the canonical family and the
  clustered standard error stays on the frozen cluster unit.

The property that makes either pool admissible is SLOT INHABITATION: for every structural slot
the treated arm can occupy, the generator must be ABLE to occupy it too. A structural zero
caused by generator incapability is a bias, not a finding, and `slot_inhabitation` proves the
absence of one before any outcome exists.

Randomness is a SHA-256 counter stream: never `hash()`, never `random`, so enumeration is
byte-identical under every PYTHONHASHSEED and on every interpreter.
"""
from __future__ import annotations

import collections
import hashlib
import json

from . import ir as IRM
from . import ontology as O

CONTROLS_VERSION = "v71_controls_v1"

SEED = "V7_1_DETERMINISTIC_CONTROL_UNIVERSE_v1"

UNIFORM_POOL_SIZE = 2000
#: The marginal pool is large because Endpoint-B matching is EXACT on every frozen
#: covariate: flexibility has to come from pool size, not from coarsening the key.
MARGINAL_POOL_SIZE = 200000

SAMPLING_UNIFORM = "UNIFORM_GRAMMAR"
SAMPLING_MARGINAL = "TREATED_ARM_STRUCTURAL_MARGINALS"

#: The structural slots a generated hypothesis occupies. Slot inhabitation is proved over
#: exactly these, and they are also the axes the Endpoint-B matching conditions on.
SLOTS = ("comparator", "subject", "side", "window", "condition_kind", "n_conditions",
         "metric_group", "n_targets", "uses_similarity", "capability_class",
         "admissible_universe_size", "temporal_resolution", "confounder_family")

SUBJECTS = ("HOME_TEAM", "AWAY_TEAM")
SIDES = ("FOR", "AGAINST")
WINDOWS = ("ALL_PRIOR", "W5", "W10")
CONDITION_KINDS = ("NONE", "VENUE", "OPPONENT_PROFILE", "COMPETITION")
#: filter dimension -> the condition KIND slot it occupies.
CONDITION_KIND_OF = {"historical_venue_conditioning": "VENUE",
                     "opponent_profile": "OPPONENT_PROFILE",
                     "competition": "COMPETITION"}
PROFILE_AXES = ("goals_for", "goals_against", "shots_on_target_for",
                "shots_on_target_against", "possession_for", "shots_against")
PROFILE_VALUES = ("HIGH", "MID", "LOW")
VENUE_VALUES = ("HOME", "AWAY")
TARGET_SET_SIZES = (1, 2, 3, 4, 5)

#: Every comparator the ontology declares. A null that cannot express a comparator the LLM
#: used would create a structural zero -- the exact defect the slot-inhabitation proof exists
#: to rule out.
COMPARATORS = tuple(sorted(O.COMPARATOR_BINDINGS))

RESEARCH_FAMILIES = ("ATTACK_VOLUME", "ATTACK_QUALITY", "DEFENSIVE_CONCESSION",
                     "DEFENSIVE_SUPPRESSION", "SET_PIECE_GENERATION",
                     "TEMPO_AND_TERRITORY", "DISCIPLINE",
                     "OPPONENT_PROFILE_INTERACTION", "FORM_VS_BASELINE", "VENUE_EFFECT")


def _stream_int(index: int, slot: str, modulus: int) -> int:
    digest = hashlib.sha256(f"{SEED}|{index}|{slot}".encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") % modulus


def _pick(index, slot, options):
    return options[_stream_int(index, slot, len(options))]


def _weighted_pick(index, slot, pairs):
    total = sum(c for _v, c in pairs)
    if total <= 0:
        return pairs[0][0]
    r = _stream_int(index, slot, total)
    acc = 0
    for val, cnt in pairs:
        acc += cnt
        if r < acc:
            return val
    return pairs[-1][0]


def derive_marginals(treated_specs) -> dict:
    """The treated arm's structural marginals, as [(value, count)] per slot.

    Structure only: no metric of quality, no outcome, no effect. A marginal-matched pool built
    from these inhabits the same structural neighbourhood as the treated arm without copying
    any individual question.
    """
    out = {}
    for slot, fn in (("comparator", lambda s: (s.get("comparison") or "").upper()),
                     ("subject", lambda s: (s.get("subject") or "").upper()),
                     ("side", lambda s: (s.get("side") or "").upper()),
                     ("window", lambda s: (s.get("window") or "ALL_PRIOR").upper()),
                     ("n_targets", lambda s: len(s.get("target_metrics") or [])),
                     ("family", lambda s: (s.get("research_family") or "").upper()),
                     ("n_conditions",
                      lambda s: len(IRM.normalise_conditions(s.get("conditions"))[0]))):
        c = collections.Counter(fn(s) for s in treated_specs)
        out[slot] = sorted(c.items(), key=lambda kv: (-kv[1], str(kv[0])))
    kinds = collections.Counter()
    for s in treated_specs:
        filters = IRM.normalise_conditions(s.get("conditions"))[0]
        if not filters:
            kinds["NONE"] += 1
        else:
            for f in filters:
                kinds[CONDITION_KIND_OF[f.dimension]] += 1
    out["condition_kind"] = sorted(kinds.items(), key=lambda kv: (-kv[1], kv[0]))
    return out


def _conditions_for(index, kind, n):
    if kind == "NONE" or n == 0:
        return []
    out = []
    for j in range(n):
        if kind == "VENUE":
            out.append({"dimension": "historical_venue_conditioning",
                        "value": _pick(index, f"venue{j}", VENUE_VALUES)})
        elif kind == "COMPETITION":
            out.append({"dimension": "competition", "value": "SAME"})
        else:
            out.append({"dimension": "opponent_profile",
                        "axis": _pick(index, f"axis{j}", PROFILE_AXES),
                        "value": _pick(index, f"band{j}", PROFILE_VALUES)})
    return out


def enumerate_pool(metric_vocabulary, size, *, sampling=SAMPLING_UNIFORM, marginals=None):
    """Deterministically enumerate `size` generic hypotheses over the structural grammar."""
    vocab = tuple(sorted(metric_vocabulary))
    pool = []
    for i in range(size):
        if sampling == SAMPLING_MARGINAL and marginals:
            comparator = _weighted_pick(i, "comparator", marginals["comparator"])
            subject = _weighted_pick(i, "subject", marginals["subject"])
            side = _weighted_pick(i, "side", marginals["side"])
            window = _weighted_pick(i, "window", marginals["window"])
            n_targets = int(_weighted_pick(i, "n_targets", marginals["n_targets"]) or 1)
            family = _weighted_pick(i, "family", marginals["family"])
            kind = _weighted_pick(i, "condition_kind", marginals["condition_kind"])
            n_conditions = int(_weighted_pick(i, "n_conditions",
                                              marginals["n_conditions"]) or 0)
        else:
            comparator = _pick(i, "comparator", COMPARATORS)
            subject = _pick(i, "subject", SUBJECTS)
            side = _pick(i, "side", SIDES)
            window = _pick(i, "window", WINDOWS)
            n_targets = _pick(i, "n_targets", TARGET_SET_SIZES)
            family = _pick(i, "family", RESEARCH_FAMILIES)
            kind = _pick(i, "condition_kind", CONDITION_KINDS)
            n_conditions = 0 if kind == "NONE" else _pick(i, "n_conditions", (1, 1, 2))

        # A comparator that REQUIRES a restriction must receive one: the generator may not
        # manufacture structurally invalid questions the treated arm could never produce.
        binding = O.COMPARATOR_BINDINGS[comparator]
        if binding.get("requires_conditions") and (kind == "NONE" or n_conditions == 0):
            kind, n_conditions = "OPPONENT_PROFILE", 1
        if binding.get("requires_filter"):
            kind, n_conditions = "COMPETITION", 1

        metrics, seen = [], set()
        for j in range(max(1, int(n_targets))):
            m = vocab[_stream_int(i, f"metric{j}", len(vocab))]
            if m not in seen:
                seen.add(m)
                metrics.append(m)
        caps = ["opponent_profile"] if (kind == "OPPONENT_PROFILE"
                                        or binding.get("requires_similarity")) else []
        pool.append({"null_index": i,
                     "target_metrics": sorted(metrics), "subject": subject, "side": side,
                     "comparison": comparator, "window": window,
                     "conditions": _conditions_for(i, kind, int(n_conditions)),
                     "research_family": family, "required_capabilities": caps})
    return pool


# ---- slot inhabitation ------------------------------------------------------------------
def _slot_values(spec, ir, capability):
    filters = ir.cohort.filters if (ir and ir.cohort) else ()
    kinds = sorted({CONDITION_KIND_OF[f.dimension] for f in filters}) or ["NONE"]
    status, adm, _d = capability.classify_metrics(
        ir.target_metrics if ir else spec.get("target_metrics") or [])
    from . import covariate_bridge as CB
    return {
        "comparator": (spec.get("comparison") or "").upper(),
        "subject": (spec.get("subject") or "").upper(),
        "side": (spec.get("side") or "").upper(),
        "window": (spec.get("window") or "ALL_PRIOR").upper(),
        "condition_kind": "|".join(kinds),
        "n_conditions": len(filters),
        "metric_group": CB.metric_group(ir.target_metrics if ir else ()),
        "n_targets": len(spec.get("target_metrics") or []),
        "uses_similarity": bool(ir and ir.cohort and ir.cohort.similar_to_opponent),
        "capability_class": status,
        "admissible_universe_size": len(adm),
        "temporal_resolution": (ir.temporal_resolution if ir else "MATCH"),
        "confounder_family": (spec.get("research_family") or "").upper(),
    }


def slot_inhabitation(treated_specs, control_specs, capability) -> dict:
    """Prove the control generator can occupy every structural slot the treated arm occupies.

    A slot the treated arm occupies and the control CANNOT is a structural zero caused by
    generator incapability. Reported per slot, outcome-blind, before any measurement.
    """
    def occupied(specs):
        acc = collections.defaultdict(collections.Counter)
        for s in specs:
            ir = IRM.build_ir(s)
            vals = _slot_values(s, ir if ir.status == IRM.OK else None, capability)
            for slot, v in vals.items():
                acc[slot][v] += 1
        return acc

    t, c = occupied(treated_specs), occupied(control_specs)
    rows, missing = {}, []
    for slot in SLOTS:
        tv, cv = set(t[slot]), set(c[slot])
        gap = sorted(str(x) for x in (tv - cv))
        rows[slot] = {"treated_values": sorted(str(x) for x in tv),
                      "control_values": sorted(str(x) for x in cv),
                      "treated_only": gap,
                      "inhabited": not gap}
        if gap:
            missing.append({"slot": slot, "values": gap})
    return {"controls_version": CONTROLS_VERSION,
            "slots": rows, "uninhabited": missing,
            "no_structural_zero_from_generator_incapability": not missing,
            "reads_outcomes": False}


def pool_hash(pool) -> str:
    return hashlib.sha256(
        json.dumps(pool, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def version_stamp() -> dict:
    return {"controls_version": CONTROLS_VERSION,
            "seed": SEED,
            "rng": "SHA256_COUNTER_STREAM (never hash() or random)",
            "uniform_pool_size": UNIFORM_POOL_SIZE,
            "marginal_pool_size": MARGINAL_POOL_SIZE,
            "endpoint_a_control": ("UNIFORM grammar pool; deliberately does not copy the "
                                   "treated arm's metric preferences"),
            "endpoint_b_control": ("MARGINAL pool from the treated arm's structural "
                                   "marginals, then matched and weighted"),
            "comparators": list(COMPARATORS),
            "slots": list(SLOTS),
            "controls_are_not_independent_votes": True,
            "reads_outcomes": False}
