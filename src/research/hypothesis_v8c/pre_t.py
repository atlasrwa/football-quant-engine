"""V8C pre-T evaluability classifier (`v8c_pre_t_evaluability_v1`) -- repairs P1
`D-V8C-P1-MEASSPACE` and `D-V8C-P1-COMPADM`. See V8C_PRE_T_EVALUABILITY_SPEC.md.

THE DISTINCTION V8C INTRODUCES
------------------------------
    ADMISSIBLE_IR        a hypothesis the ontology grammar + capability contract permit
    PRE_T_EVALUABLE_IR   a hypothesis the deterministic engine can prove, BEFORE kickoff, it
                         will be able to MEASURE at this target fixture

V8B let all three arms select from ADMISSIBLE_IR. The engine already knew, before the target
was played, that most of that space could not be evaluated -- so the experiment spent real
money on selections that were guaranteed to end SCORE_INSUFFICIENT_SUPPORT. That is
experimental-apparatus failure, not evidence about Sonnet.

THE KEY FACT THAT MAKES THIS POSSIBLE
-------------------------------------
Every quantity the post-T scorer gates on is computable from strictly-prior observations:

  cohort/baseline observation sets   `prior_entries` -- strictly before T by construction
  raw_n, unique_fixtures            counts over those sets
  unique_opponents                  distinct opponent ids in those sets
  effective_n, weight_concentration Kish ESS / max weight share of the cohort weights
  degeneracy                        cohort vs baseline fixture sets + weights
  environment mean availability     `env_mean(..., cutoff = target kickoff)`, strictly before
  scale_var                         weighted variance of COHORT values

The ONLY quantity genuinely unknowable before T is the target's own observed value. Hence the
consistency invariant this module is built to satisfy (§8):

    PRE_T_EVALUABLE  =>  post-T status in { SCORE_OK,
                                            SCORE_REFUSED("observed ... unavailable") }

Asserted unconditionally (§15) in tests/research/hypothesis_v8c/test_pre_t_consistency.py.

HOW IT IS COMPUTED
------------------
By running the FROZEN `compiler.compile_query` against a `TargetBlindIndex` in which the
target position's own observation is physically unavailable, then applying the FROZEN V8B.2
support classifier and the FROZEN scale floor. Nothing is reimplemented, so the pre-T verdict
cannot drift from the post-T scorer: it IS the post-T computation with `observed` withheld.

READS NO TARGET OUTCOME. READS NO EFFECT, SCORE, DIRECTION OR P-VALUE. ZERO SPEND.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.research.hypothesis_v7 import pit as V7PIT
from src.research.hypothesis_v71 import capability as CAP
from src.research.hypothesis_v71 import engine as ENG
from src.research.hypothesis_v71 import invariants as INV
from src.research.hypothesis_v71 import similarity as SIM
from src.research.hypothesis_v8b2 import support as SUP
from src.research.hypothesis_v8c import blind_index as BI
from src.research.hypothesis_v8c import cohort_stats as CS
from src.research.hypothesis_v8c import compiler as CO

PRE_T_VERSION = "v8c_pre_t_evaluability_v1"

# ---- statuses (§8) ----------------------------------------------------------------------
PRE_T_EVALUABLE = "PRE_T_EVALUABLE"
PRE_T_INSUFFICIENT_RAW_N = "PRE_T_INSUFFICIENT_RAW_N"
PRE_T_INSUFFICIENT_FIXTURES = "PRE_T_INSUFFICIENT_FIXTURES"
PRE_T_INSUFFICIENT_OPPONENTS = "PRE_T_INSUFFICIENT_OPPONENTS"
PRE_T_INSUFFICIENT_EFFECTIVE_N = "PRE_T_INSUFFICIENT_EFFECTIVE_N"
PRE_T_WEIGHT_CONCENTRATION = "PRE_T_WEIGHT_CONCENTRATION"
PRE_T_PROVIDER_UNSUPPORTED = "PRE_T_PROVIDER_UNSUPPORTED"
PRE_T_COMPILER_INVALID = "PRE_T_COMPILER_INVALID"
PRE_T_DEGENERATE_CONTRAST = "PRE_T_DEGENERATE_CONTRAST"
PRE_T_NO_SCALE = "PRE_T_NO_SCALE"

ALL_STATUSES = (PRE_T_EVALUABLE, PRE_T_INSUFFICIENT_RAW_N, PRE_T_INSUFFICIENT_FIXTURES,
                PRE_T_INSUFFICIENT_OPPONENTS, PRE_T_INSUFFICIENT_EFFECTIVE_N,
                PRE_T_WEIGHT_CONCENTRATION, PRE_T_PROVIDER_UNSUPPORTED,
                PRE_T_COMPILER_INVALID, PRE_T_DEGENERATE_CONTRAST, PRE_T_NO_SCALE)

#: Support-failure field -> the status it produces. Deterministic priority: the FIRST failing
#: field in this fixed order names the status, so a multi-failure cohort always reports the
#: same status. Order mirrors the funnel (volume -> diversity -> weighting), never an effect.
_FAILURE_STATUS_ORDER = (
    ("raw_n", PRE_T_INSUFFICIENT_RAW_N),
    ("unique_fixtures", PRE_T_INSUFFICIENT_FIXTURES),
    ("unique_opponents", PRE_T_INSUFFICIENT_OPPONENTS),
    ("effective_n", PRE_T_INSUFFICIENT_EFFECTIVE_N),
    ("weight_concentration", PRE_T_WEIGHT_CONCENTRATION),
)

#: Post-T statuses a PRE_T_EVALUABLE hypothesis is permitted to reach (§8 invariant).
PERMITTED_POST_T_STATUSES = (CS.SCORE_OK, CS.SCORE_REFUSED)
#: ...and the ONLY permitted reason for the SCORE_REFUSED branch. Referenced from the scorer's
#: own constant rather than copied, so the invariant cannot drift from the string it checks.
PERMITTED_REFUSAL_REASON = CS.OBSERVED_UNAVAILABLE_REASON


@dataclass(frozen=True)
class PreTEvaluability:
    """The pre-kickoff measurability verdict for ONE hypothesis at ONE target fixture."""
    status: str
    hypothesis_id: str | None = None
    raw_n: int | None = None
    unique_fixtures: int | None = None
    unique_opponents: int | None = None
    effective_n: float | None = None
    weight_concentration: float | None = None
    scale_var: float | None = None
    baseline_n: int | None = None
    support_status: str | None = None
    failures: tuple = ()
    reason: str = ""

    @property
    def evaluable(self) -> bool:
        return self.status == PRE_T_EVALUABLE


def competition_admissible(ir, capability, competition) -> tuple[bool, str]:
    """§30 / `D-V8C-P1-COMPADM`: the metric must be supported by the provider AT THIS
    FIXTURE'S COMPETITION, not merely somewhere in the corpus.

    `search()` returns `admissible_competitions` as a display field and never compares it to
    the target. `invariants.assert_valid` does not check competition at all. So a RESTRICTED
    metric could enter the selectable universe at a competition where the provider does not
    cover it (`offsides` is not admissible in epl/ligue1; `xg` not in laliga2/ligue2;
    `touches_in_penalty_area` not in champ). Enforced here, before anything is selectable.
    """
    status, adm, _detail = capability.classify_metrics(ir.target_metrics)
    if status not in (CAP.SUPPORTED, CAP.RESTRICTED):
        return False, f"capability status {status} for {sorted(ir.target_metrics)}"
    if competition not in adm:
        return False, (f"metric {sorted(ir.target_metrics)} is not admissible in "
                       f"competition {competition!r} (admissible: {sorted(adm)})")
    return True, ""


def _status_for(support) -> tuple[str, str]:
    fields = {f["field"] for f in support.failures}
    for field, status in _FAILURE_STATUS_ORDER:
        if field in fields:
            return status, "; ".join(
                f"{f['field']}: have={f.get('have')} need={f.get('need', f.get('limit'))}"
                for f in support.failures)
    # Unreachable while classify_fixture_support only emits the five known fields; fails
    # closed rather than silently admitting an unclassified failure.
    return PRE_T_COMPILER_INVALID, f"unclassified support failure: {support.failures!r}"


def classify_pre_t_evaluability(ir, index, rec_i, *, metric, terciles, axis_cache, similarity,
                                recency, capability=None) -> PreTEvaluability:
    """Decide, WITHOUT the target outcome, whether this hypothesis will be measurable at this
    fixture.

    The target position is sealed behind a `TargetBlindIndex` for the whole computation, so
    the verdict physically cannot depend on the target's own observation. Cohort/baseline
    values, weights and fixture sets are produced by the FROZEN compiler, and the support gate
    is the FROZEN V8B.2 classifier -- the same code the post-T scorer runs.
    """
    hid = None
    try:
        hid = ir.ir_id()
    except Exception:                                  # pragma: no cover - defensive
        pass

    rec = index.recs[rec_i]
    # The corpus index must actually CARRY the metric. On the real corpus every contracted
    # metric is indexed, so this is a no-op there; on a synthetic index it is the honest
    # reason a candidate is unmeasurable, and it must be named rather than raising a KeyError
    # out of `env_mean` (§5: "valid hypothesis destroyed by compiler" cuts both ways --
    # an unmeasurable one must fail with its own reason, not a stack trace).
    missing = [m for m in ir.target_metrics if m not in index.metrics]
    if missing:
        return PreTEvaluability(status=PRE_T_PROVIDER_UNSUPPORTED, hypothesis_id=hid,
                                reason=f"metric(s) {sorted(missing)} are not present in this "
                                       f"corpus index")
    if capability is not None:
        ok, why = competition_admissible(ir, capability, rec.competition)
        if not ok:
            return PreTEvaluability(status=PRE_T_PROVIDER_UNSUPPORTED, hypothesis_id=hid,
                                    reason=why)

    blind = index if isinstance(index, BI.TargetBlindIndex) else BI.TargetBlindIndex(
        index, [rec_i])

    try:
        scales, last_q = [], None
        for w in recency:
            q = CO.compile_query(ir, blind, rec_i, metric=metric, terciles=terciles,
                                 axis_cache=axis_cache, similarity=similarity, recency=w,
                                 capability=capability, collect_fixtures=True)
            if q.is_degenerate():
                return PreTEvaluability(status=PRE_T_DEGENERATE_CONTRAST, hypothesis_id=hid,
                                        reason="cohort and baseline read the same "
                                               "observations with the same weighting")
            if q.environment_mean is None:
                return PreTEvaluability(status=PRE_T_COMPILER_INVALID, hypothesis_id=hid,
                                        reason="competition environment mean unavailable")
            cw, bw = sum(q.cohort_weights), sum(q.baseline_weights)
            if cw <= 0 or bw <= 0:
                return PreTEvaluability(status=PRE_T_COMPILER_INVALID, hypothesis_id=hid,
                                        reason="degenerate weights")
            scales.append(CS.weighted_variance(q.cohort_values, q.cohort_weights))
            last_q = q
    except (CO.CompileRefused, SIM.SimilarityRefused, INV.InvariantViolation) as e:
        return PreTEvaluability(status=PRE_T_COMPILER_INVALID, hypothesis_id=hid,
                                reason=str(e))

    # ---- the frozen V8B.2 fixture-level support gate, computed pre-T ----------------------
    uniq_opp = CS.unique_opponents_of_cohort(ir, blind, rec_i, last_q.cohort_fixtures)
    support = SUP.classify_fixture_support(
        raw_n=last_q.cohort_n,
        unique_fixtures=len(last_q.cohort_fixtures),
        unique_opponents=uniq_opp,
        effective_n=V7PIT.kish_effective_n(last_q.cohort_weights),
        max_weight_share=V7PIT.weight_concentration(last_q.cohort_weights))

    common = dict(hypothesis_id=hid, raw_n=last_q.cohort_n,
                  unique_fixtures=len(last_q.cohort_fixtures), unique_opponents=uniq_opp,
                  effective_n=support.effective_n,
                  weight_concentration=support.weight_concentration,
                  baseline_n=last_q.baseline_n, support_status=support.status,
                  failures=support.failures)

    if support.status != SUP.SUPPORT_ADEQUATE:
        status, reason = _status_for(support)
        return PreTEvaluability(status=status, reason=reason, **common)

    # ---- the frozen scale floor, also pre-T knowable --------------------------------------
    scale_var = sum(scales) / len(scales)
    if scale_var is None or scale_var <= CS.ZERO_VARIANCE_FLOOR:
        return PreTEvaluability(status=PRE_T_NO_SCALE, scale_var=scale_var,
                                reason=f"cohort has no pre-T dispersion to standardize by "
                                       f"(scale_var={scale_var!r} <= "
                                       f"{CS.ZERO_VARIANCE_FLOOR})", **common)

    return PreTEvaluability(status=PRE_T_EVALUABLE, scale_var=scale_var, **common)


def evaluate_candidate(ir, index, rec_i, *, ctx, capability):
    """Convenience wrapper binding the frozen per-IR recency family and the IR's own metric."""
    return classify_pre_t_evaluability(
        ir, index, rec_i, metric=ir.target_metrics[0], terciles=ctx.terciles,
        axis_cache=ctx.axis_cache, similarity=ctx.similarity,
        recency=ENG.recency_family_for(ir), capability=capability)


def version_stamp() -> dict:
    return {"pre_t_evaluability_version": PRE_T_VERSION,
            "repairs": ["D-V8C-P1-MEASSPACE", "D-V8C-P1-COMPADM"],
            "statuses": list(ALL_STATUSES),
            "support_classifier": SUP.version_stamp()["fixture_support_version"],
            "cohort_stats": CS.version_stamp()["cohort_stats_version"],
            "imports_a_scorer": False,
            "compiler": CO.COMPILER_VERSION,
            "profile_semantic": CO.PROFILE_SEMANTIC,
            "thresholds_unchanged_from_v8b2": True,
            "target_position_sealed_during_classification": True,
            "consistency_invariant": ("PRE_T_EVALUABLE => post-T status in {SCORE_OK, "
                                      "SCORE_REFUSED(observed unavailable)}"),
            "permitted_post_t_statuses": list(PERMITTED_POST_T_STATUSES),
            "reads_target_outcome": False,
            "reads_effect_or_score_or_direction": False}
