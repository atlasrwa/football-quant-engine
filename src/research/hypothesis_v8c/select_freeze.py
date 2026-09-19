"""V8C PROCESS 1 of 2 -- pre-T selection and all-arm freeze (`v8c_select_freeze_v1`).

REPAIRS P0 OUTCOME-SEAL.

THE DEFECT
----------
`hypothesis_v8c.experiment.run_experiment` looped over fixtures doing, per iteration:

    build universe -> S select -> R select -> H select -> SCORE THE TARGET

so fixture 1's outcome was opened while fixtures 2..N had not yet been selected. Any
selection after the first was made in a process that had already read real target outcomes.
That is not a freeze; it is a rolling disclosure, and no amount of wrapper discipline inside
one process fixes it.

THE SEAL
--------
Two PHYSICALLY SEPARATE processes:

    PROCESS 1  select_freeze.py   selects S/R/H for the ENTIRE cohort, writes a durable
                                  hashed freeze file, and EXITS. It never imports a scorer,
                                  and asserts as much at start and at finish.
    PROCESS 2  score_frozen.py    reads that file, verifies its hash, and only then scores.

The seal is therefore an operating-system fact, not a code-review claim: process 1 terminates
before process 2 begins, and process 1's interpreter provably never contained a module capable
of reading a target outcome.

Defense in depth, on top of that:
  * every pre-T read goes through `TargetBlindIndex`, whose audit log is written into the
    freeze file;
  * the freeze file carries a self-hash that process 2 re-verifies before scoring;
  * `assert_no_scorer_loaded()` runs at entry and exit.

ZERO SPEND (the S arm is caller-supplied; no model call is made here).
ZERO TARGET-OUTCOME ACCESS. No CHAMPION write.
"""
from __future__ import annotations

import hashlib
import json
import sys
import time

from src.research.hypothesis_v8c import aggregate_blocks as BLK
from src.research.hypothesis_v8c import blind_index as BI
from src.research.hypothesis_v8c import controls as CTL
from src.research.hypothesis_v8c import live_reachability as LIVE
from src.research.hypothesis_v8c import packet as PK
from src.research.hypothesis_v8c import pit_context as PC
from src.research.hypothesis_v8c import runner as RUN
from src.research.hypothesis_v8c import universe as UNI
from src.research.hypothesis_v8c import vintage as VIN

SELECT_FREEZE_VERSION = "v8c_select_freeze_v2"

#: Any module whose presence in THIS interpreter would break the seal.
FORBIDDEN_MODULE_MARKERS = ("scorer", "score_frozen")

INVALID_UNKNOWN_HYPOTHESIS_ID = "INVALID_UNKNOWN_HYPOTHESIS_ID"

GRAMMAR_VERSION = __import__("src.research.hypothesis_v8c.grammar",
                             fromlist=["x"]).GRAMMAR_VERSION
SIMILARITY_VERSION = __import__("src.research.hypothesis_v71.similarity",
                                fromlist=["x"]).SIMILARITY_VERSION


def _grammar_size_hash() -> str:
    """Binds the freeze to the exact declared grammar SHAPE, so a silent grammar change
    (an added window, a new interaction family) invalidates the freeze."""
    import hashlib
    import json
    from src.research.hypothesis_v8c import grammar as GR
    payload = {"version": GR.GRAMMAR_VERSION, "windows": list(GR.WINDOWS),
               "subjects": list(GR.SUBJECTS), "perspectives": list(GR.PERSPECTIVES),
               "n_condition_shapes": len(GR.CONDITION_SHAPES),
               "condition_shapes": GR.CONDITION_SHAPES,
               "families": list(GR.RESEARCH_FAMILIES)}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


GRAMMAR_SIZE_HASH = _grammar_size_hash()

#: The frozen recency family the packet is built over.
RECENCY_FAMILY = (tuple(__import__("src.research.hypothesis_v71.recency",
                                   fromlist=["x"]).family())
                  + (__import__("src.research.hypothesis_v71.recency",
                                fromlist=["x"]).UniformRecency(),))


def universe_hash(fixture_universe) -> str:
    """The exact candidate set that was selectable at this fixture."""
    import hashlib
    import json
    return hashlib.sha256(json.dumps(
        {"fixture_id": fixture_universe.fixture_id,
         "evaluable_ids": list(fixture_universe.evaluable_ids()),
         "ledger": fixture_universe.ledger()},
        sort_keys=True, default=str).encode()).hexdigest()
OK = "OK"
OK_ABSTAIN = "OK_ABSTAIN"


class OutcomeSealViolation(Exception):
    """A scoring module was loaded inside the pre-T selection process."""


def assert_no_scorer_loaded() -> list:
    """The P0 seal assertion. Raises if any scoring module is importable-and-loaded here."""
    loaded = sorted(m for m in sys.modules
                    if any(k in m for k in FORBIDDEN_MODULE_MARKERS))
    if loaded:
        raise OutcomeSealViolation(
            f"PRE-T process has scoring module(s) loaded, seal broken: {loaded}")
    return loaded


def default_s_selector(session, k=3):
    """A deterministic STAND-IN for Sonnet so the composed path runs with no paid call.

    SESSION-BASED, deliberately. It issues a real search through the real tool surface, so the
    ids it submits were genuinely RETURNED BY THIS SESSION -- which is one of the six terms of
    the authoritative submission contract. A selector that returned ids straight out of
    `fixture_universe.evaluable` would bypass that term and could never be validated the way a
    model's submission is.

    NOT a model, NOT an arm of the real experiment: in a real run this is replaced by the
    frozen Sonnet selections from `runner.run_fixture_converse`. Reads no outcome and no
    support statistic -- it sees the same `llm_facing` projection Sonnet would.
    """
    page = session.search({"max_results": UNI.PAGE_SIZE_CAP})
    return [c["hypothesis_id"] for c in page.get("results", [])[:k]]


def select_cohort(index, fixture_positions, *, capability, s_selector=None, k=3,
                  fixture_ids=None, similarity_engine=None, classification="SYNTHETIC_ONLY",
                  grammar_kwargs=None, progress=False, enforce_seal=True,
                  model_id="DETERMINISTIC_STANDIN", resolved_model_id=None,
                  model_config_stamp=None, cache_key=None, cache_hit=None,
                  s_runner=None) -> dict:
    """Select S/R/H for the WHOLE cohort. Returns the freeze payload. Reads no outcome.

    `enforce_seal=False` exists ONLY for in-process unit tests, whose interpreter is shared
    with scoring tests and is therefore contaminated by construction. It does NOT weaken the
    P0 guarantee: the real seal is that `_run_v8c_select.py` runs in its own process and
    exits, and `test_outcome_seal.py` proves that end to end by actually spawning the two
    processes. Any real run leaves this True.
    """
    # The test-only relaxation is NOT reachable for a real run. It exists because unit tests
    # share one interpreter with scoring tests and are contaminated by construction; it must
    # never be usable to produce real evidence.
    if not enforce_seal and not str(classification).startswith("SYNTHETIC"):
        raise AssertionError(
            f"enforce_seal=False is test-only and is refused for classification "
            f"{classification!r}: a real selection must run scorer-free in its own process")
    if enforce_seal:
        assert_no_scorer_loaded()
    s_selector = s_selector or (lambda session: default_s_selector(session, k=k))
    rows, t0 = [], time.time()

    for n, pos in enumerate(fixture_positions):
        fid = str(fixture_ids[n]) if fixture_ids else str(index.recs[pos].fixture_id)
        sealed = BI.TargetBlindIndex(index, [pos])
        ctx = PC.build_pit_context(sealed, pos, similarity_engine=similarity_engine)
        fu = UNI.build_fixture_universe(sealed, pos, ctx=ctx, capability=capability,
                                        fixture_id=fid, grammar_kwargs=grammar_kwargs)

        # ---- S arm: the ONE authoritative submission contract ---------------------------
        # `runner` owns validation. This function does NOT re-implement it. Re-implementing it
        # is how the two paths drifted: `select_cohort` used to keep the valid ids out of a
        # mixed valid/invalid submission (partial acceptance), while `runner.PARTIAL_ACCEPTANCE`
        # said False. One contract, one place.
        #
        # The real evidence packet is built FIRST, target-blind, because the packet is what the
        # model is shown -- so it must exist before the model is asked anything.
        pkt = PK.build_packet(sealed, pos, capability, ctx, RECENCY_FAMILY)
        packet_hash = pkt["packet_hash"]

        if s_runner is not None:
            # A caller-supplied runner (e.g. the real Converse loop) drives the tool session
            # itself and returns the VALIDATED result. It still goes through
            # `runner.validate_submission`, so the contract is unchanged.
            run = s_runner(fu, capability, grammar_kwargs=grammar_kwargs, packet=pkt)
        else:
            run = RUN.run_fixture(fu, capability, selector=s_selector,
                                  grammar_kwargs=grammar_kwargs)
        by_id = {c["hypothesis_id"]: c for c in fu.evaluable}
        s_valid = list(run["accepted"])
        # The runner's status is CARRIED, never recomputed and never softened. In particular
        # INVALID_SUBMISSION is preserved as failure: it is NOT relabelled OK_ABSTAIN just
        # because the accepted list is empty. Abstention is an explicit empty submission; a
        # rejected submission is a different event and the endpoint must be able to tell them
        # apart.
        arm_status = run["status"]
        s_invalid = list(run["problems"])

        # ---- control arms ----------------------------------------------------------------
        shapes = [CTL.shape_of(by_id[h]) for h in s_valid]
        r_out = CTL.blind_selections_for_fixture(shapes, fu)
        h_out = CTL.heuristic_selections_for_fixture(len(s_valid), fu)
        # BOTH reachability notions are recorded, explicitly labelled. `reachability_report`
        # paginates to exhaustion and so measures THEORETICAL API reachability; the live
        # protocol gives the model 6 calls and a 50-result page. Experiment ELIGIBILITY is
        # decided on the LIVE number only (P1-C); the theoretical one is kept as a diagnostic
        # so the gap between the two stays visible rather than being quietly conflated.
        reach = UNI.reachability_report(fu)
        live_reach = LIVE.audit_fixture(fu)

        meta = VIN.fixture_metadata(index, pos)
        rows.append({
            # ---- P0-A binding identity: enough to reproduce and VERIFY the pre-T state ----
            "fixture_id": fid,
            "fixture_metadata": meta,
            "rec_i": int(pos),          # diagnostic only; process 2 resolves by fixture_id
            "corpus_vintage_hash": VIN.corpus_vintage_before(index, meta["kickoff_unix"]),
            "capability_hash": VIN.capability_hash(capability),
            "grammar_version": GRAMMAR_VERSION,
            "grammar_size_hash": GRAMMAR_SIZE_HASH,
            "competition": index.recs[pos].competition,
            "kickoff_unix": int(index.kick[pos]),
            "arm_status": arm_status,
            "k_valid": len(s_valid),
            "S": list(s_valid),
            "S_invalid": s_invalid,
            "n_submitted": run["n_submitted"],
            "R_pairs": [{"s_id": p["s_id"], "r_id": p["r_id"], "tier": p["tier"],
                         "status": p["status"]} for p in r_out["pairs"]],
            "R": [p["r_id"] for p in r_out["pairs"] if p["r_id"]],
            "R_identity_count": r_out["identity_count"],
            "R_cross_treatment_overlap_count": r_out["cross_treatment_overlap_count"],
            "R_unmatched": r_out["n_unmatched"], "R_tiers": r_out["tiers"],
            "H": [c["hypothesis_id"] for c in h_out["selections"]],
            "H_status": h_out["status"], "H_ranked_over": h_out.get("n_ranked_over", 0),
            "universe_ledger": fu.ledger(),
            "research_family_counts": fu.research_family_counts(),
            "reachability_theoretical": reach,      # unlimited pagination
            "reachability_live": live_reach,        # the 6-call bounded protocol
            "live_search_addressable": live_reach["n_live_unreachable"] == 0,
            "reachability": reach,                  # retained: back-compat alias
            "pit_context_hash": PC.context_hash(ctx),
            "universe_hash": universe_hash(fu),
            "packet_hash": packet_hash,
            # ---- P1-E: the COMPLETE treatment provenance, emitted by the runner itself ----
            "treatment_provenance": RUN.treatment_record(
                fixture_id=fid, kickoff_unix=meta["kickoff_unix"], fixture_universe=fu,
                ctx=ctx, packet_hash=packet_hash,
                capability_hash=VIN.capability_hash(capability),
                corpus_vintage=VIN.corpus_vintage_before(index, meta["kickoff_unix"]),
                result=run, model_id=model_id, resolved_model_id=resolved_model_id,
                model_config_stamp=model_config_stamp,
                cache_key=cache_key, cache_hit=cache_hit,
                research_reason=run.get("research_reason"),
                evidence_references=run.get("evidence_references")),
            "similarity_version": SIMILARITY_VERSION,
            "blind_index_audit": sealed.audit_report(),
        })
        if progress:
            print(f"[select] {n + 1}/{len(fixture_positions)} {fid} "
                  f"eval={fu.n_evaluable} k={len(s_valid)} R={r_out['n_matched']} "
                  f"H={h_out['n_selected']} unreach={reach['unreachable_candidate_count']} "
                  f"[{time.time() - t0:.0f}s]", flush=True)

    if enforce_seal:
        assert_no_scorer_loaded()

    ids_ordered = [r["fixture_id"] for r in rows]
    # ---- P1-F: inference blocks are computed and FROZEN HERE, before any outcome exists ----
    blocks = BLK.chronological_blocks(ids_ordered)

    payload = {
        "freeze_version": SELECT_FREEZE_VERSION,
        "classification": classification,
        "n_fixtures": len(rows),
        "fixture_ids_ordered": ids_ordered,
        "inference_blocks": blocks,
        "inference_blocks_frozen_before_outcomes": True,
        "apparatus": {"universe": UNI.version_stamp(), "controls": CTL.version_stamp(),
                      "pit_context": PC.version_stamp(),
                      "blind_index": BI.version_stamp()},
        "totals": {
            "R_identity_count": sum(r["R_identity_count"] for r in rows),
            "R_cross_treatment_overlap_count":
                sum(r["R_cross_treatment_overlap_count"] for r in rows),
            "unreachable_candidate_count":
                sum(r["reachability"]["unreachable_candidate_count"] for r in rows),
            "live_search_unreachable_count":
                sum(r["reachability_live"]["n_live_unreachable"] for r in rows),
            "all_fixtures_live_search_addressable":
                all(r["live_search_addressable"] for r in rows) if rows else None,
            "S_invalid_count": sum(len(r["S_invalid"]) for r in rows),
            "target_outcomes_viewed":
                any(r["blind_index_audit"]["target_outcomes_viewed"] for r in rows),
        },
        "selections": rows,
        "scorer_loaded_in_this_process": bool(
            [m for m in sys.modules if any(k in m for k in FORBIDDEN_MODULE_MARKERS)]),
        "seal_enforced": bool(enforce_seal),
        "reads_target_outcome": False,
    }
    payload["freeze_hash"] = freeze_hash(payload)
    return payload


def freeze_hash(payload: dict) -> str:
    core = {k: v for k, v in payload.items() if k != "freeze_hash"}
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()


def write_freeze(payload: dict, path: str) -> str:
    """Durably write the freeze. Atomic, so a half-written freeze can never be scored."""
    import os
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=1, default=str, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return payload["freeze_hash"]


def version_stamp() -> dict:
    return {"select_freeze_version": SELECT_FREEZE_VERSION,
            "repairs": ["P0-OUTCOME-SEAL", "P1-INVALID-S"],
            "process_role": "PROCESS 1 of 2 -- pre-T selection only",
            "imports_a_scorer": False,
            "asserts_no_scorer_loaded": True,
            "forbidden_module_markers": list(FORBIDDEN_MODULE_MARKERS),
            "writes_durable_hashed_freeze": True,
            "invalid_id_handling": "explicit terminal status + research-yield count",
            "freezes_binding_identity": ["fixture_metadata", "corpus_vintage_hash",
                                         "capability_hash", "grammar_version",
                                         "grammar_size_hash", "pit_context_hash",
                                         "universe_hash", "similarity_version"],
            "freezes_inference_blocks": True,
            "reads_target_outcome": False}
