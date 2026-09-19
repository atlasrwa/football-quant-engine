"""V8C defect ledger (`v8c_defect_ledger_v1`) -- repairs P1-G.

THE DEFECT
----------
`_run_v8c_evidence.py` WROTE the literals

    p0_open = 0
    p1_open = 0
    new_sonnet_calls = 0

into a JSON file, and the freeze gate then READ those fields and believed them. That is
self-certification: the artifact asserting the gate condition was produced by a script that
simply declared it. A hand-written `{"p0_open": 0}` would have passed.

THE LEDGER
----------
Every P0/P1 has an entry naming:

    id, severity, root cause, repair
    required_evidence   the test node ids (or artifact) that must PASS for it to be CLOSED
    expected_terminal   the state that counts as closed

`P0_OPEN` / `P1_OPEN` are then DERIVED by counting entries whose required evidence did not
pass. No script can declare them; they are a function of test outcomes.

`required_artifact` is an ADDITIONAL requirement, never a substitute for tests. A defect that
declared only an artifact would close because a FILE EXISTS -- which is the same
self-certification this ledger exists to prevent, wearing a different hat. Every entry that
names an artifact also names tests that read its CONTENT.

PROVENANCE
----------
Every evidence artifact must embed the commit, module hashes and input hashes of the process
that produced it, and the freeze builder recomputes those CURRENT values and requires exact
equality. A stale artifact produced by older code therefore FAILS rather than silently
satisfying a condition -- which was the second half of P1-G.

ZERO SPEND. Reads no target outcome.
"""
from __future__ import annotations

import hashlib
import json

ROOT = "/home/ubuntu"

DEFECT_LEDGER_VERSION = "v8c_defect_ledger_v1"

CLOSED = "CLOSED"
OPEN = "OPEN"
REPAIRED = "REPAIRED"
DEFERRED_TO_AUDIT = "DEFERRED_TO_AUDIT"

T = "tests/research/hypothesis_v8c"

#: The ledger. `required_evidence` are pytest node ids; a defect is CLOSED only when every one
#: of them PASSED in the run that produced the evidence artifact.
DEFECTS = [
    # ---------------------------------------------------------------- P0 -----------------
    dict(id="P0-A-DATA-VINTAGE-BINDING", severity="P0",
         root_cause="score_frozen trusted a frozen integer rec_i against a freshly supplied "
                    "index; an inserted/backfilled/reordered row repoints it, and a revised "
                    "historical value silently changes the statistical question",
         repair="freeze full binding identity (fixture metadata, corpus vintage, capability, "
                "grammar, PIT context, universe); process 2 resolves by fixture_id and "
                "verifies every binding BEFORE any outcome read",
         required_evidence=[
             f"{T}/test_freeze_binding.py::test_identical_frozen_data_scores",
             f"{T}/test_freeze_binding.py::test_freeze_carries_the_full_binding_identity",
             f"{T}/test_freeze_binding.py::test_row_inserted_before_frozen_rec_i_is_refused",
             f"{T}/test_freeze_binding.py::test_reordered_index_still_resolves_by_fixture_id",
             f"{T}/test_freeze_binding.py::test_mutated_prior_historical_value_is_refused",
             f"{T}/test_freeze_binding.py::test_mutated_fixture_metadata_is_refused",
             f"{T}/test_freeze_binding.py::test_mutated_capability_contract_is_refused",
             f"{T}/test_freeze_binding.py::test_mutated_grammar_version_is_refused",
             f"{T}/test_freeze_binding.py::test_mutated_pit_context_hash_is_refused",
             f"{T}/test_freeze_binding.py::test_missing_fixture_is_a_distinct_status"],
         expected_terminal="all binding mutations refuse before any outcome read"),
    dict(id="P0-B-EXTERNAL-FREEZE-ANCHOR", severity="P0",
         root_cause="a self-hashed JSON is tamper-evident only if the claimed hash is anchored "
                    "outside the payload; an editor could recompute the freeze's own hash",
         repair="FreezeReceipt written as a SEPARATE artifact anchoring the freeze FILE BYTES, "
                "plus producer commit and module hashes; scoring requires it",
         required_evidence=[
             f"{T}/test_freeze_binding.py::test_self_rehashed_tamper_is_caught_by_the_receipt",
             f"{T}/test_freeze_binding.py::test_edited_receipt_is_refused",
             f"{T}/test_freeze_binding.py::test_receipt_from_another_commit_is_refused",
             f"{T}/test_freeze_binding.py::test_missing_receipt_is_refused",
             f"{T}/test_freeze_binding.py::test_receipt_binds_producer_commit_and_code_hashes"],
         expected_terminal="a self-rehashed freeze is still refused"),
    # ---------------------------------------------------------------- P1 -----------------
    dict(id="P1-K-HISTORICAL-PROFILE-H-TIME", severity="P1",
         root_cause="a historical match H was classified using the opponent's profile as of T, "
                    "which included post-H matches AND H itself: the measured observation "
                    "influenced its own conditioning variable",
         repair="HistoricalProfileIndex -- profile AND tercile bounds both strictly before H",
         required_evidence=[
             f"{T}/test_historical_pit.py::test_profile_before_H_excludes_H_and_everything_after",
             f"{T}/test_historical_pit.py::test_post_H_extreme_matches_cannot_move_H_band",
             f"{T}/test_historical_pit.py::test_H_own_observation_cannot_move_its_conditioning_profile",
             f"{T}/test_historical_pit.py::test_LIVE_CONTROL_pre_H_data_DOES_move_the_profile",
             f"{T}/test_historical_pit.py::test_terciles_are_also_as_of_H",
             f"{T}/test_historical_pit.py::test_unclassifiable_match_is_excluded_not_imputed"],
         expected_terminal="post-H and self data cannot move H's band; pre-H data can"),
    dict(id="P1-L-RESOLVER-CACHE-COLLISION", severity="P1",
         root_cause="_resolver_key hashed a custom condition_set by len() alone, so two "
                    "different sets of equal length collided",
         repair="content fingerprint over the nested shape structure, canonicalised",
         required_evidence=[
             f"{T}/test_universe_grammar.py::test_resolver_key_does_not_collide_on_equal_length"],
         expected_terminal="equal-length different condition sets produce different keys"),
    dict(id="P1-F-BLOCKS-FROZEN-PRE-OUTCOME", severity="P1",
         root_cause="chronological blocks were built in process 2 after scoring, although the "
                    "contract says they are predeclared",
         repair="process 1 computes and freezes fixture_id -> block_id; process 2 CONSUMES it "
                "and recomputes only as a verification check",
         required_evidence=[
             f"{T}/test_freeze_binding.py::test_blocks_are_frozen_in_the_selection",
             f"{T}/test_freeze_binding.py::test_post_freeze_block_change_is_refused"],
         expected_terminal="post-freeze blocking changes cannot alter the experiment"),
    # ---------------------------------------------------- still open --------------------
    dict(id="P1-A-REAL-SONNET-RUNNER", severity="P1",
         root_cause="runner.py provides the session/validation surface but not the real "
                    "Bedrock Converse orchestration, so the paid treatment path does not exist",
         expected_terminal="mocked multi-turn Converse loop",
         repair='runner.run_fixture_converse -- the real multi-turn Bedrock Converse loop with the transport INJECTED; no boto3 import anywhere, so the mocked tests exercise the same orchestration a paid run would',
         required_evidence=['tests/research/hypothesis_v8c/test_runner_converse.py::test_tool_loop_executes_searches_then_submits', 'tests/research/hypothesis_v8c/test_runner_converse.py::test_seventh_search_does_not_execute_and_forces_submit', 'tests/research/hypothesis_v8c/test_runner_converse.py::test_no_live_bedrock_call_is_possible_here', 'tests/research/hypothesis_v8c/test_runner_converse.py::test_search_backend_is_v8c_not_v8b1'],
         bound_modules=['runner', 'universe', 'prompt']),
    dict(id="P1-B-PROMPT-TOOL-CONTRACT", severity="P1",
         root_cause="the V8C submit tool is materially simpler than the prior deep-reasoning "
                    "interface while docs claim the football prompt is unchanged",
         expected_terminal="one frozen PROMPT_VERSION/PROMPT_SHA256/TOOL_SCHEMA_SHA256",
         repair='prompt.py freezes ONE system prompt and ONE tool schema, both content-hashed and bound into the cache identity and every treatment record',
         required_evidence=['tests/research/hypothesis_v8c/test_runner_converse.py::test_runner_sends_the_frozen_prompt_and_tool_schema', 'tests/research/hypothesis_v8c/test_submission_contract_authority.py::test_freeze_carries_complete_treatment_provenance'],
         bound_modules=['prompt', 'runner']),
    dict(id="P1-C-LIVE-SEARCH-REACHABILITY", severity="P1",
         root_cause="unreachable==0 was proven by unlimited pagination, not under the live "
                    "MAX_SEARCH_CALLS=6 x PAGE_SIZE_CAP=50 protocol",
         repair="live_reachability.py -- a candidate is LIVE-ADDRESSABLE iff its canonical "
                "structural query returns it on the FIRST page, i.e. in one call; the count "
                "is COMPUTED and the call cap is not relaxed",
         required_evidence=[
             f"{T}/test_live_reachability.py::test_every_evaluable_candidate_is_live_addressable",
             f"{T}/test_live_reachability.py::test_canonical_query_is_expressible_by_the_model",
             f"{T}/test_live_reachability.py::test_call_cap_is_not_relaxed"],
         required_artifact="V8C_LIVE_SEARCH_REACHABILITY_REPORT.json",
         expected_terminal="LIVE_UNREACHABLE_CANDIDATES == 0 or a reported design conflict"),
    dict(id="P1-D-SUBMISSION-CONTRACT", severity="P1",
         root_cause="MAX_SELECTIONS undefined; a mixed valid/invalid submission is silently "
                    "converted into a clean partial treatment",
         repair="frozen contract: MAX_SELECTIONS=8, PARTIAL_ACCEPTANCE=False, "
                "INVALID_SUBMISSION with zero accepted selections",
         required_evidence=[
             f"{T}/test_submission_contract.py::test_contract_constants_are_frozen",
             f"{T}/test_submission_contract.py::test_valid_max_k_response_is_accepted",
             f"{T}/test_submission_contract.py::test_over_cap_is_invalid",
             f"{T}/test_submission_contract.py::test_duplicate_ids_are_invalid",
             f"{T}/test_submission_contract.py::test_one_valid_plus_one_fabricated_accepts_NOTHING",
             f"{T}/test_submission_contract.py::test_fabricated_id_alone_is_invalid",
             f"{T}/test_submission_contract.py::test_id_never_returned_this_session_is_invalid",
             f"{T}/test_submission_contract.py::test_abstention_is_legal",
             f"{T}/test_submission_contract.py::test_every_outcome_has_an_explicit_status"],
         expected_terminal="INVALID_SUBMISSION with zero accepted selections"),
    dict(id="P1-E-TREATMENT-PROVENANCE", severity="P1",
         root_cause="the all-arm freeze does not carry full treatment provenance",
         expected_terminal="every named field bound",
         repair='runner.treatment_record, emitted by select_freeze.select_cohort for every fixture; resolved model identity is carried as None when unavailable, never fabricated',
         required_evidence=['tests/research/hypothesis_v8c/test_submission_contract_authority.py::test_freeze_carries_complete_treatment_provenance', 'tests/research/hypothesis_v8c/test_submission_contract_authority.py::test_resolved_model_id_is_not_fabricated', 'tests/research/hypothesis_v8c/test_runner_converse.py::test_complete_treatment_provenance_is_emitted'],
         bound_modules=['runner', 'select_freeze', 'packet']),
    dict(id="P1-G-GATE-SELF-CERTIFICATION", severity="P1",
         root_cause="the evidence generator wrote p0_open/p1_open/new_sonnet_calls literals "
                    "and the gate believed them; artifacts were bound to CURRENT code hashes "
                    "rather than proven to have been produced by them",
         repair="P0/P1 openness DERIVED from this ledger against actual passed pytest nodes; "
                "every artifact must embed producer provenance, recomputed and compared by "
                "the gate",
         required_evidence=[
             f"{T}/test_gate_provenance.py::test_ledger_with_no_evidence_reports_everything_open",
             f"{T}/test_gate_provenance.py::test_ledger_closes_only_on_actual_passed_nodes",
             f"{T}/test_gate_provenance.py::test_hand_written_p0_open_zero_cannot_pass",
             f"{T}/test_gate_provenance.py::test_declared_p0_open_zero_is_ignored_even_with_passed_nodes",
             f"{T}/test_gate_provenance.py::test_artifact_without_provenance_cannot_satisfy_a_condition",
             f"{T}/test_gate_provenance.py::test_stale_evidence_from_older_code_is_refused",
             f"{T}/test_gate_provenance.py::test_ledger_change_invalidates_prior_evidence",
             f"{T}/test_gate_provenance.py::test_gate_has_no_override_flag"],
         expected_terminal="gate booleans derived from this ledger + per-artifact provenance"),
    dict(id="P1-H-REAL-CORPUS-REACHABILITY", severity="P1",
         root_cause="SCORE_OK reachability was demonstrated on synthetic data only",
         expected_terminal="exposed-50 endpoint reachability, classified DEVELOPMENT",
         repair='live_reachability.audit_fixture measures addressability under the REAL bounded 6-call protocol; select_freeze records theoretical and live reachability separately',
         required_evidence=['tests/research/hypothesis_v8c/test_submission_contract_authority.py::test_clean_submission_is_accepted_and_bound'],
         required_artifact='V8C_EXPOSED50_REHEARSAL_V2.json',
         bound_modules=['live_reachability', 'universe', 'select_freeze']),
    dict(id="P1-I-R-ACTION-SPACE-COVERAGE", severity="P1",
         root_cause="R feasibility probed on only the first four evaluable candidates",
         expected_terminal="coverage over the whole S action space + set-level K matching",
         repair="control_coverage: whole-action-space single-candidate coverage, SET-LEVEL feasibility by maximum bipartite matching, and a Hall's-condition minimum-degree proof over the whole space reported in the successor coverage artifact",
         required_evidence=['tests/research/hypothesis_v8c/test_control_coverage.py::test_single_candidate_coverage_is_computed_over_every_candidate', 'tests/research/hypothesis_v8c/test_control_coverage.py::test_set_level_uses_maximum_matching_not_greedy', 'tests/research/hypothesis_v8c/test_control_coverage.py::test_max_matching_beats_greedy_on_a_constructed_conflict'],
         required_artifact='V8C_R_ACTION_SPACE_COVERAGE_V2.json',
         bound_modules=['control_coverage', 'controls']),
    dict(id="P1-J-PILOT-POPULATION-RULE", severity="P1",
         root_cause="the fresh-pilot selection rule is not preregistered",
         repair="V8C_FRESH_PILOT_POPULATION_RULE.md -- N=60 derived from the frozen inference "
                "floor, structural eligibility only, first-N chronological, predeclared "
                "shortfall handling; frozen BEFORE any 947 scan",
         required_evidence=[
             f"{T}/test_pilot_rule.py::test_pilot_N_is_frozen_and_stated",
             f"{T}/test_pilot_rule.py::test_pilot_N_is_consistent_with_the_frozen_inference_floor",
             f"{T}/test_pilot_rule.py::test_eligibility_is_structural_only",
             f"{T}/test_pilot_rule.py::test_ordering_and_selection_are_deterministic",
             f"{T}/test_pilot_rule.py::test_shortfall_handling_is_predeclared",
             f"{T}/test_pilot_rule.py::test_rule_was_frozen_before_any_sealed_scan"],
         required_artifact="V8C_FRESH_PILOT_POPULATION_RULE.md",
         expected_terminal="frozen rule before any 947 scan"),
]

#: Findings raised BY this repair pass, for the auditor to classify. Not gate conditions.
NEW_FINDINGS = [
    dict(id="N1-SIMILARITY-TARGET-TIME-SELF-INCLUSION", severity="P0",
         finding="`similar_opponent_ids` builds every team's profile as of T. A historical "
                 "match H between the subject and opponent X therefore contributes to X's "
                 "profile, which helps decide whether X is judged similar to the target's "
                 "opponent -- so H participates in deciding its own cohort membership.",
         status=REPAIRED,
         repaired_by="hypothesis_v8c.historical_similarity.HistoricalSimilarityIndex "
                     "(P0-SIMSELF); compiler._select now resolves membership per historical "
                     "match, strictly before H.",
         previously="DEFERRED_TO_AUDIT. The earlier pass argued that a per-H set was "
                    "'incoherent by construction' because 'similar to today's opponent' would "
                    "stop meaning anything, and that the construct was target-time rather than "
                    "a P1-K-class defect.",
         why_the_deferral_was_overturned=(
             "The deferral rested on an argument, not a measurement. The adversarial battery "
             "in tests/research/hypothesis_v8c/test_similarity_self_inclusion.py DEMONSTRATES "
             "the leak on a synthetic corpus: mutating H's OWN measured values flips H's "
             "opponent out of the k=8 set, and so does appending extreme post-H pre-T rows. "
             "Under the Gate-A stop rule that is items 1 (future/target leakage into the "
             "conditioning variable) and 5 (outcome information influencing selection), so it "
             "blocks the mission and cannot be deferred. The 'stops meaning anything' "
             "objection does not survive contact with the repair: the semantic becomes 'was X "
             "similar to the target's opponent, judged from information available before H?', "
             "which is exactly the per-H move P1-K already made for `opponent_profile` bands. "
             "The alternative the earlier pass proposed -- excluding the subject's own matches "
             "from opponent profiles -- would have CHANGED the frozen V7 similarity contract; "
             "this repair changes only the reference INSTANT and reuses every frozen "
             "dimension, weight, k and tie-break verbatim."),
         adversarial_tests=[
             f"{T}/test_similarity_self_inclusion.py::"
             "test_h_own_observation_does_not_change_its_own_membership",
             f"{T}/test_similarity_self_inclusion.py::"
             "test_post_h_data_does_not_change_h_membership",
             f"{T}/test_similarity_self_inclusion.py::test_unrepaired_engine_leaks",
             f"{T}/test_similarity_self_inclusion.py::"
             "test_compiler_refuses_similarity_without_h_time_index"]),
    dict(id="N2-P1K-UNIVERSE-COST", severity="INFORMATIONAL",
         finding="H-time classification costs ~23% of profile-conditioned evaluable candidates "
                 "at a data-rich fixture (879 -> 674 on mt_626333016). Those candidates were "
                 "evaluable only by hindsight. At thin fixtures the count is 0 under BOTH "
                 "semantics, so this is not a P1-K regression.",
         why_not_repaired_here="correct behaviour, not a defect",
         candidate_repair="none", status=DEFERRED_TO_AUDIT),
]


def module_hashes(modules) -> dict:
    """SHA256 of the CURRENT bytes of each bound module."""
    import hashlib
    import os
    out = {}
    for m in modules:
        path = f"{ROOT}/src/research/hypothesis_v8c/{m}.py"
        if os.path.exists(path):
            with open(path, "rb") as f:
                out[m] = hashlib.sha256(f.read()).hexdigest()
        else:
            out[m] = None
    return out


def evaluate(passed_node_ids, *, artifact_dir="/home/ubuntu/research/hypothesis_engine",
             evidence_binding=None) -> dict:
    """Derive P0_OPEN / P1_OPEN from ACTUAL test outcomes. Nothing here can be declared.

    `evidence_binding` is the record written when the evidence was produced:

        {defect_id: {"code_hashes": {module: sha}, "commit": ..., "input_hashes": {...}}}

    A defect whose bound modules have CHANGED since that record cannot be CLOSED on it. Stale
    evidence is not evidence: a passing node id from before a repair says nothing about the
    code running now.
    """
    import os
    passed = set(passed_node_ids or ())
    binding = evidence_binding or {}
    rows = []
    for d in DEFECTS:
        art = d.get("required_artifact")
        art_missing = ([f"required artifact {art} absent"]
                       if art and not os.path.exists(os.path.join(artifact_dir, art)) else [])
        if d.get("status_override"):
            status = d["status_override"]
            missing = []
        elif not d["required_evidence"] and not art:
            status, missing = OPEN, ["no required evidence declared"]
        else:
            missing = [n for n in d["required_evidence"] if n not in passed] + art_missing
            # STALENESS: the bound modules must be the ones the evidence was produced against.
            bound = d.get("bound_modules") or []
            if bound:
                rec = binding.get(d["id"])
                if not rec:
                    missing.append("no evidence binding recorded for the bound modules")
                else:
                    now = module_hashes(bound)
                    drifted = sorted(m for m in bound
                                     if rec.get("code_hashes", {}).get(m) != now.get(m))
                    if drifted:
                        missing.append(
                            f"evidence is STALE: bound module(s) changed since it was "
                            f"produced: {drifted}")
            status = CLOSED if not missing else OPEN
        rows.append({**{k: v for k, v in d.items() if k != "status_override"},
                     "status": status, "missing_evidence": missing})
    return {"defect_ledger_version": DEFECT_LEDGER_VERSION,
            "defects": rows,
            "new_findings": NEW_FINDINGS,
            "p0_total": sum(1 for r in rows if r["severity"] == "P0"),
            "p1_total": sum(1 for r in rows if r["severity"] == "P1"),
            "p0_open": sum(1 for r in rows if r["severity"] == "P0" and r["status"] != CLOSED),
            "p1_open": sum(1 for r in rows if r["severity"] == "P1" and r["status"] != CLOSED),
            "p0_closed": [r["id"] for r in rows if r["severity"] == "P0" and r["status"] == CLOSED],
            "p1_closed": [r["id"] for r in rows if r["severity"] == "P1" and r["status"] == CLOSED],
            "open_ids": [r["id"] for r in rows if r["status"] != CLOSED],
            "derived_from": "actual pytest node outcomes; no literal is accepted",
            "evidence_binding_supplied": bool(binding),
            "staleness_rule": ("a defect with bound_modules cannot be CLOSED unless an "
                               "evidence binding records the SAME module hashes that are on "
                               "disk now")}


def ledger_hash() -> str:
    return hashlib.sha256(
        json.dumps(DEFECTS, sort_keys=True, default=str).encode()).hexdigest()


def version_stamp() -> dict:
    return {"defect_ledger_version": DEFECT_LEDGER_VERSION,
            "repairs": ["P1-G"],
            "p0_p1_open_are_derived_not_declared": True,
            "n_defects": len(DEFECTS), "n_new_findings": len(NEW_FINDINGS),
            "ledger_hash": ledger_hash()}
