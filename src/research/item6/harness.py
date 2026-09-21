"""ITEM 6 Stage-1 evaluation harness  (`item6_harness_v1`).

Deterministic pipeline: raw per-fixture LLM responses (or stand-in / control outputs)
-> schema validation
-> per-fixture formalization (F0..F5)
-> within-fixture + corpus-level semantic dedup
-> novel-family registry
-> Stage-1 endpoints
-> frozen gate verdict.

The harness NEVER calls a model and NEVER reads an outcome. It consumes already-produced
response objects (a list of dicts). In the live experiment those come from the frozen Sonnet
transport; in rehearsal they come from stand-in fixtures. The harness is identical either way,
which is what lets the stand-in prove the apparatus end-to-end at zero spend.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from .formalizer import FormalizationResult, deduplicate, family_signature, formalize
from .registry import build_registry
from .schema import Mechanism, validate_response
from .stage1_gate import evaluate_gate
from .stage1_metrics import FixtureOutcome, compute_endpoints

HARNESS_VERSION = "item6_harness_v1"


def _corpus_dedup_rate(all_mechs: Sequence[Mechanism]) -> Tuple[float, List[str]]:
    """Cross-fixture dedup: corpus-level duplicate rate + list of distinct novel signatures."""
    rep = deduplicate(all_mechs)
    return rep["duplicate_rate"], list(rep["signature_groups"].keys())


def run_stage1(
    responses: Sequence[Dict],
    allowed_evidence_refs_by_fixture: Optional[Dict[str, Sequence[str]]] = None,
) -> Dict[str, object]:
    """responses: list of {"fixture_id": ..., "mechanisms":[...]} or abstention objects.

    Returns a full result dict (endpoints, gate, registry, per-fixture detail, validation).
    """
    per_fixture: List[FixtureOutcome] = []
    validation_errors: Dict[str, List[str]] = {}
    all_novel_mechs: List[Mechanism] = []
    accepted_pairs: List[Tuple[Mechanism, FormalizationResult]] = []
    within_fixture_dup_rates: List[float] = []

    for resp in responses:
        fx = str(resp.get("fixture_id", "UNKNOWN"))
        vr = validate_response(resp)
        if vr.errors:
            validation_errors[fx] = vr.errors
        allowed = None
        if allowed_evidence_refs_by_fixture is not None:
            allowed = allowed_evidence_refs_by_fixture.get(fx)

        formals: List[FormalizationResult] = []
        mechs = vr.mechanisms
        for m in mechs:
            f = formalize(m, allowed_evidence_refs=allowed)
            formals.append(f)
            if f.counts_as_novel_measurable:
                all_novel_mechs.append(m)
                accepted_pairs.append((m, f))

        # within-fixture dedup rate (over this fixture's mechanisms). This is the scale-stable
        # SEMANTIC_DUPLICATE_RATE unit: it measures whether a generator repeats itself WITHIN a
        # single fixture's K draws, exactly the pathology the prior small-corpus audit captured,
        # and it is not dominated by the (fixtures >> possible-families) arithmetic that a
        # corpus-wide 1 - unique/total ratio would suffer from.
        wf = deduplicate(mechs) if mechs else {"duplicate_rate": 0.0}
        if mechs:
            within_fixture_dup_rates.append(wf["duplicate_rate"])
        per_fixture.append(FixtureOutcome(
            fixture_id=fx,
            abstained=vr.is_abstention,
            formalizations=formals,
            duplicate_rate=wf["duplicate_rate"],
        ))

    # SEMANTIC_DUPLICATE_RATE = mean within-fixture duplicate rate (handles within-fixture
    # dependence; comparable to the prior audit's small-corpus figure).
    mean_within_dup = (0.0 if not within_fixture_dup_rates
                       else round(sum(within_fixture_dup_rates) / len(within_fixture_dup_rates), 6))

    # corpus distinct NOVEL family signatures (drives NEW_FAMILY_COUNT).
    novel_family_sigs_corpus = sorted({str(family_signature(m)) for m in all_novel_mechs})

    endpoints = compute_endpoints(
        outcomes=per_fixture,
        corpus_duplicate_rate=mean_within_dup,
        corpus_new_family_ids=novel_family_sigs_corpus,
    )
    gate = evaluate_gate(endpoints)
    registry = build_registry(accepted_pairs)

    # additional corpus-level diagnostics (reported, not gating)
    all_mechs: List[Mechanism] = []
    for resp in responses:
        vr2 = validate_response(resp)
        all_mechs.extend(vr2.mechanisms)
    corpus_rep = deduplicate(all_mechs)

    return {
        "harness_version": HARNESS_VERSION,
        "n_responses": len(responses),
        "validation_errors": validation_errors,
        "endpoints": endpoints.to_dict(),
        "gate": gate.to_dict(),
        "novel_family_registry": registry,
        "corpus_diagnostics": {
            "corpus_distinct_signatures": corpus_rep["n_unique_signatures"],
            "corpus_n_mechanisms": corpus_rep["n_total"],
            "corpus_raw_duplicate_rate": corpus_rep["duplicate_rate"],
            "mean_within_fixture_duplicate_rate": mean_within_dup,
            "n_distinct_novel_family_signatures": len(novel_family_sigs_corpus),
        },
        "per_fixture": [
            {
                "fixture_id": o.fixture_id,
                "abstained": o.abstained,
                "within_fixture_duplicate_rate": o.duplicate_rate,
                "formalizations": [f.to_dict() for f in o.formalizations],
            }
            for o in per_fixture
        ],
        "reads_outcomes": False,
        "made_paid_call": False,
    }


def version_stamp() -> Dict[str, object]:
    return {"harness_version": HARNESS_VERSION, "made_paid_call": False, "reads_outcomes": False}
