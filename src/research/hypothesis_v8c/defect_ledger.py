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

DEFECT_LEDGER_VERSION = "v8c_defect_ledger_v1"

CLOSED = "CLOSED"
OPEN = "OPEN"
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
         repair="", required_evidence=[], expected_terminal="mocked multi-turn Converse loop",
         status_override=OPEN),
    dict(id="P1-B-PROMPT-TOOL-CONTRACT", severity="P1",
         root_cause="the V8C submit tool is materially simpler than the prior deep-reasoning "
                    "interface while docs claim the football prompt is unchanged",
         repair="", required_evidence=[],
         expected_terminal="one frozen PROMPT_VERSION/PROMPT_SHA256/TOOL_SCHEMA_SHA256",
         status_override=OPEN),
    dict(id="P1-C-LIVE-SEARCH-REACHABILITY", severity="P1",
         root_cause="unreachable==0 was proven by unlimited pagination, not under the live "
                    "MAX_SEARCH_CALLS=6 x PAGE_SIZE_CAP=50 protocol",
         repair="", required_evidence=[],
         expected_terminal="LIVE_UNREACHABLE_CANDIDATES == 0 or a reported design conflict",
         status_override=OPEN),
    dict(id="P1-D-SUBMISSION-CONTRACT", severity="P1",
         root_cause="MAX_SELECTIONS undefined; a mixed valid/invalid submission is silently "
                    "converted into a clean partial treatment",
         repair="", required_evidence=[],
         expected_terminal="INVALID_SUBMISSION with zero accepted selections",
         status_override=OPEN),
    dict(id="P1-E-TREATMENT-PROVENANCE", severity="P1",
         root_cause="the all-arm freeze does not carry full treatment provenance",
         repair="", required_evidence=[], expected_terminal="every named field bound",
         status_override=OPEN),
    dict(id="P1-G-GATE-SELF-CERTIFICATION", severity="P1",
         root_cause="the evidence generator wrote p0_open/p1_open/new_sonnet_calls literals "
                    "and the gate believed them; artifacts were bound to CURRENT code hashes "
                    "rather than proven to have been produced by them",
         repair="", required_evidence=[],
         expected_terminal="gate booleans derived from this ledger + per-artifact provenance",
         status_override=OPEN),
    dict(id="P1-H-REAL-CORPUS-REACHABILITY", severity="P1",
         root_cause="SCORE_OK reachability was demonstrated on synthetic data only",
         repair="", required_evidence=[],
         expected_terminal="exposed-50 endpoint reachability, classified DEVELOPMENT",
         status_override=OPEN),
    dict(id="P1-I-R-ACTION-SPACE-COVERAGE", severity="P1",
         root_cause="R feasibility probed on only the first four evaluable candidates",
         repair="", required_evidence=[],
         expected_terminal="coverage over the whole S action space + set-level K matching",
         status_override=OPEN),
    dict(id="P1-J-PILOT-POPULATION-RULE", severity="P1",
         root_cause="the fresh-pilot selection rule is not preregistered",
         repair="", required_evidence=[], expected_terminal="frozen rule before any 947 scan",
         status_override=OPEN),
]

#: Findings raised BY this repair pass, for the auditor to classify. Not gate conditions.
NEW_FINDINGS = [
    dict(id="N1-SIMILARITY-TARGET-TIME-SELF-INCLUSION", severity="P1_CANDIDATE",
         finding="`similar_opponent_ids` builds every team's profile as of T. A historical "
                 "match H between the subject and opponent X therefore contributes to X's "
                 "profile, which helps decide whether X is judged similar to the target's "
                 "opponent -- so H participates in deciding its own cohort membership.",
         why_not_repaired_here=(
             "the similar-set is ONE set used to filter every H, so leave-H-out is incoherent "
             "by construction: it would need a different set per H and 'similar to today's "
             "opponent' would stop meaning anything. The conditioning variable is a property "
             "of the TARGET's opponent, not of H, and uses only data < T, so this is a "
             "target-time construct rather than the P1-K defect. The clean alternative -- "
             "excluding the subject's own matches from every opponent's similarity profile -- "
             "changes the FROZEN V7.1 similarity contract, which is not a call to make "
             "mid-mission."),
         candidate_repair="exclude the subject's own matches from opponent similarity profiles",
         status=DEFERRED_TO_AUDIT),
    dict(id="N2-P1K-UNIVERSE-COST", severity="INFORMATIONAL",
         finding="H-time classification costs ~23% of profile-conditioned evaluable candidates "
                 "at a data-rich fixture (879 -> 674 on mt_626333016). Those candidates were "
                 "evaluable only by hindsight. At thin fixtures the count is 0 under BOTH "
                 "semantics, so this is not a P1-K regression.",
         why_not_repaired_here="correct behaviour, not a defect",
         candidate_repair="none", status=DEFERRED_TO_AUDIT),
]


def evaluate(passed_node_ids) -> dict:
    """Derive P0_OPEN / P1_OPEN from ACTUAL test outcomes. Nothing here can be declared."""
    passed = set(passed_node_ids or ())
    rows = []
    for d in DEFECTS:
        if d.get("status_override"):
            status = d["status_override"]
            missing = []
        elif not d["required_evidence"]:
            status, missing = OPEN, ["no required evidence declared"]
        else:
            missing = [n for n in d["required_evidence"] if n not in passed]
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
            "derived_from": "actual pytest node outcomes; no literal is accepted"}


def ledger_hash() -> str:
    return hashlib.sha256(
        json.dumps(DEFECTS, sort_keys=True, default=str).encode()).hexdigest()


def version_stamp() -> dict:
    return {"defect_ledger_version": DEFECT_LEDGER_VERSION,
            "repairs": ["P1-G"],
            "p0_p1_open_are_derived_not_declared": True,
            "n_defects": len(DEFECTS), "n_new_findings": len(NEW_FINDINGS),
            "ledger_hash": ledger_hash()}
