"""Build + FREEZE the V8A development design. ZERO SPEND -- no Converse call is made here.

CountTokens IS called when reachable: it is non-generative and free, and an exact
provider-native input-token count makes the pre-spend ceiling a real bound rather than an
estimate. If it is unreachable the proven UTF-8 byte bound is used and the manifest records
which path each request took.

Produces, under research/hypothesis_engine/out/v8a/ and the artifact paths the brief names:

    V8A_FIXTURE_MANIFEST.json         the frozen 12-fixture development sample
    V8A_CAPABILITY_MANIFEST.json      per-fixture five-state capability envelopes
    V8A_GENERIC_LIBRARY_MANIFEST.json the outcome-blind structural library + its proofs
    V8A_PROMPT_FREEZE.json            prompt + schema hashes, frozen before any call
    V8A_PRE_SPEND_REPORT.md           the section-25 gate
    packets_v8a.json / packets_arm_a.json
    V8A_CALL_PLAN.json                every planned call, with its cost ceiling

Run:  python3 research/hypothesis_engine/_freeze_v8a.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, "/home/ubuntu/v8a-worktree")

import src  # noqa: F401,E402 -- binds src.__path__ to the worktree FIRST

from src.research.hypothesis_engine import corpus_adapter as CA          # noqa: E402
from src.research.hypothesis_engine import schema_v4 as SCHEMA_V4        # noqa: E402
from src.research.hypothesis_oos import v5a2_packet as P2                # noqa: E402
from src.research.hypothesis_oos import v6_prompt as V6PR                # noqa: E402
from src.research.hypothesis_v7 import provider as V7P                   # noqa: E402
from src.research.hypothesis_v71 import corpus_index as CI               # noqa: E402
from src.research.hypothesis_v8a import envelope as EN                   # noqa: E402
from src.research.hypothesis_v8a import fixtures as FX                   # noqa: E402
from src.research.hypothesis_v8a import genericlib as G                  # noqa: E402
from src.research.hypothesis_v8a import packet as PK                     # noqa: E402
from src.research.hypothesis_v8a import prompt_v8a as PR                 # noqa: E402
from src.research.hypothesis_v8a import schema_v8a as S                  # noqa: E402
from src.research.hypothesis_v8a import transport as TR                  # noqa: E402
from src.research.hypothesis_v8a.frozencap import FrozenCapability       # noqa: E402

ROOT = "/home/ubuntu/v8a-worktree"
OUT = f"{ROOT}/research/hypothesis_engine/out/v8a"
HE = f"{ROOT}/research/hypothesis_engine"
OOS_OUT = f"{ROOT}/research/hypothesis_oos/out"
CAP_PATH = f"{OOS_OUT}/v7_1/V7_1_CAPABILITY_MATRIX.json"

MODEL_ID = "us.anthropic.claude-sonnet-4-6"
TEMPERATURE = 0.0
MAX_TOKENS_PASS1 = 24576
MAX_TOKENS_PASS2 = 8192
REGION = "us-east-1"

#: FROZEN BEFORE ANY CALL (brief section 24): the second pass is ONE CALL PER CANDIDATE.
#: Batching a fixture's candidates into one call would let the model see its own siblings
#: while judging each, which is a different experiment from the one the brief specifies.
PASS2_GRANULARITY = "ONE_CALL_PER_CANDIDATE"


def _sha(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str).encode()
    ).hexdigest()


def _write(name, obj):
    path = os.path.join(OUT, name)
    json.dump(obj, open(path, "w"), indent=2, sort_keys=True, default=str)
    return {"artifact": name, "sha256": _sha(obj)}


def main():
    os.makedirs(OUT, exist_ok=True)
    cap = FrozenCapability.load(CAP_PATH)
    VOCAB = list(cap.measurable_vocabulary())

    # ---- corpus + fixtures ------------------------------------------------------------
    mc = V7P.METRIC_CONTRACT
    recs = CI.load_records(include_fresh=True)
    idx = CI.PITIndex(recs, sorted(mc), mc)
    chosen, fixture_audit = FX.select(recs, oos_out_root=OOS_OUT, index=idx)
    fixture_audit["frozen_before_any_model_call"] = True
    fixture_audit["n_fixtures_frozen"] = len(chosen)
    fixture_audit["manifest_sha256"] = FX.manifest_hash(fixture_audit)

    # ---- capability envelopes + V8A packets --------------------------------------------
    by = lambda p: idx.recs[p]                                          # noqa: E731
    envelopes, packets, pit = {}, {}, {}
    for rec in chosen:
        ri = idx.pos_of_fixture[str(rec.fixture_id)]
        env = EN.build(cap, idx, rec, ri, VOCAB, by)
        pkt = PK.build(idx, cap, rec, ri, VOCAB, by, env)
        envelopes[str(rec.fixture_id)] = env
        packets[str(rec.fixture_id)] = pkt
        pit[str(rec.fixture_id)] = PK.pit_audit(pkt, int(rec.kickoff_unix))

    # ---- Arm A packets: the GENUINE V6.1 surface, unmodified ---------------------------
    a_idx = CA.load_index()
    a_by_id = {str(r.fixture_id): r for r in a_idx.records}
    arm_a_packets, arm_a_missing = {}, []
    for rec in chosen:
        fid = str(rec.fixture_id)
        tgt = a_by_id.get(fid)
        if tgt is None:
            arm_a_missing.append(fid)
            continue
        p = P2.build_packet(a_idx, tgt, arm="research")
        if p is None:
            arm_a_missing.append(fid)
        else:
            arm_a_packets[fid] = p

    # ---- generic library ---------------------------------------------------------------
    lib = G.build_library(VOCAB)
    lib_keys = sorted({h["structural_key_sha256"] for h in lib})
    from src.research.hypothesis_v71 import controls as C
    pool = C.enumerate_pool(VOCAB, 2000)
    nondeg = [p for p in pool if not G.is_degenerate(p.get("conditions"))]
    unreachable = [p for p in nondeg if not G.reachability(p, VOCAB)["reachable"]]

    generic_manifest = {
        "genericlib": G.version_stamp(),
        "shared_metric_vocabulary": VOCAB,
        "n_metrics": len(VOCAB),
        "vocabulary_parity": ("the LLM arms and the generic library are offered the SAME "
                              "metric set; a difference would bias the comparison"),
        "materialized_library_size": len(lib),
        "materialized_library_purpose": "nearest-3 retrieval and predicate agreement only",
        "distinct_structural_keys": len(lib_keys),
        "library_keys_sha256": _sha(lib_keys),
        "membership_is_analytic": True,
        "slot_inhabitation_proof": {
            "n_generator_draws": len(pool),
            "n_degenerate_excluded_by_frozen_rule": len(pool) - len(nondeg),
            "n_non_degenerate": len(nondeg),
            "n_unreachable_by_predicate": len(unreachable),
            "predicate_agrees_with_generator": not unreachable,
            "meaning": ("every structure the real V7.1 generator can emit is recognised as "
                        "GENERIC, so an LLM candidate cannot score INCREMENTAL_STRUCTURE "
                        "merely because a finite sample missed it"),
        },
        "known_structural_zeros": {
            "formation_conditioned_cohort": (
                "UNSUPPORTED for EVERY arm alike: v71_ontology declares formation not "
                "resolvable per prior match in this corpus. Neither the generic generator "
                "nor an LLM can produce a measurable formation-conditioned hypothesis, so "
                "the zero is capability-blocked, not generator-incapable."),
            "half_state_conditioned_cohort": (
                "UNAVAILABLE for EVERY arm alike: half-time score state is populated on 0 "
                "of 5636 corpus records. A half-state rate of zero in the report is a "
                "property of the corpus, not a failure of a model."),
        },
        "the_incremental_structure_channel": (
            "Because the compiler honours exactly three filter dimensions and the generator "
            "emits all conditions with a SINGLE kind, the reachable channels for genuine "
            "incremental structure are: a mixed-kind condition set (e.g. venue AND "
            "opponent-profile together), or three or more conditions. Both are two-variable "
            "interactions, which is what brief section 12 phase 2 asks the model to find."),
    }

    # ---- prompt + schema freeze --------------------------------------------------------
    prompt_freeze = {
        "frozen_before_first_paid_call": True,
        "v8a_prompt": PR.version_stamp(),
        "v8a_schema": S.version_stamp(),
        "pass2_granularity": PASS2_GRANULARITY,
        "arm_a_prompt": {
            "prompt_version": V6PR.V6_PROMPT_VERSION,
            "system_sha256": hashlib.sha256(V6PR.SYSTEM_PROMPT.encode()).hexdigest(),
            "schema_version": SCHEMA_V4.SCHEMA_VERSION,
            "schema_content_hash": SCHEMA_V4.schema_content_hash(),
            "reproduced_verbatim_from_frozen_commit": True,
            "reconstructed_or_approximated": False,
        },
        "model": {"model_id": MODEL_ID, "temperature": TEMPERATURE,
                  "max_tokens_pass1": MAX_TOKENS_PASS1,
                  "max_tokens_pass2": MAX_TOKENS_PASS2, "region": REGION,
                  "max_tokens_amended": {
                      "amendment": "V8A_PRE_SPEND_AMENDMENT",
                      "was_pass1": 8192, "was_pass2": 2048,
                      "why": ("the 8192 pass-1 ceiling BOUND for Arm B: both executed "
                              "responses stopped at max_tokens with the `candidates` key "
                              "absent entirely, so they could not contain the measured "
                              "quantity. An apparatus fault, not a result."),
                      "arm_a_affected": False,
                      "arm_a_reason": ("the 8192 ceiling never bound for Arm A -- all 12 "
                                       "responses stopped naturally at tool_use, max 6730 "
                                       "output tokens. At temperature 0 a non-binding "
                                       "ceiling is purely a stopping condition and cannot "
                                       "alter the emitted tokens, so Arm A is not re-run."),
                      "prompt_unchanged": True}},
        "revision_policy": ("If the structural results disappoint, the result is recorded "
                            "as it stands. A prompt revision becomes V8A.1 with its own "
                            "frozen development sample; it is never the same experiment."),
    }

    # ---- call plan + cost ceiling (CountTokens is free) --------------------------------
    client = None
    try:
        client = TR.build_client(REGION)
    except Exception as exc:                                            # noqa: BLE001
        prompt_freeze["client_build_error"] = f"{type(exc).__name__}: {exc}"[:200]

    calls, seq = [], 0
    p1_schema, p2_schema = S.pass1_schema(), S.pass2_schema()
    v4_schema = SCHEMA_V4.build_schema()

    for fid, pkt in sorted(packets.items()):
        seq += 1
        calls.append({"seq": seq, "arm": "B", "pass": 1, "fixture_id": fid,
                      **TR.cost_entry(PR.SYSTEM_PROMPT_PASS1, PK.serialize(pkt),
                                      p1_schema, "Return the research analysis.",
                                      model_id=MODEL_ID, temperature=TEMPERATURE,
                                      max_tokens=MAX_TOKENS_PASS1, client=client,
                                      label=f"B/pass1/{fid}")})
    for fid, pkt in sorted(arm_a_packets.items()):
        seq += 1
        calls.append({"seq": seq, "arm": "A", "pass": 1, "fixture_id": fid,
                      **TR.cost_entry(V6PR.SYSTEM_PROMPT, V6PR.build_user_payload(pkt),
                                      v4_schema, "Return the hypothesis set.",
                                      model_id=MODEL_ID, temperature=TEMPERATURE,
                                      max_tokens=MAX_TOKENS_PASS1, client=client,
                                      label=f"A/pass1/{fid}")})

    # Pass 2: bounded by MAX_HYPOTHESES per fixture. Priced with a WORST-CASE payload so the
    # ceiling holds however many candidates actually survive.
    worst_cand = {"candidate_id": "C" * 24, "research_family": "OPPONENT_PROFILE_INTERACTION",
                  "subject": "TEAM_A", "opponent": "TEAM_B",
                  "target_metric": VOCAB[:5], "metric_perspective": "FOR",
                  "behavioral_observations": [{"observation": "x" * 500,
                                               "evidence_refs": ["r"] * 12}] * 8,
                  "football_mechanism": "x" * 900, "comparison": "SIMILAR_OPPONENT_COHORT",
                  "window": "W5", "conditions": [{"dimension": "opponent_profile",
                                                  "axis": "goals_against",
                                                  "value": "HIGH"}] * 4,
                  "falsifiable_question": "x" * 600, "falsifier": "x" * 600,
                  "similar_opponent_rationale": "x" * 500, "formation_context": "x" * 500,
                  "self_critique": {"notes": "x" * 600}, "provider_requirements": ["p"] * 12,
                  "support_risk": "LOW", "coverage_risk": "LOW"}
    worst_generics = G.nearest(worst_cand, lib, 3)
    p2_entry = TR.cost_entry(PR.SYSTEM_PROMPT_PASS2,
                             PR.build_pass2_user(worst_cand, worst_generics),
                             p2_schema, "Return the novelty judgment.",
                             model_id=MODEL_ID, temperature=TEMPERATURE,
                             max_tokens=MAX_TOKENS_PASS2, client=client,
                             label="B/pass2/WORST_CASE")
    n_p2_max = len(packets) * S.MAX_HYPOTHESES
    for k in range(n_p2_max):
        seq += 1
        calls.append({"seq": seq, "arm": "B", "pass": 2,
                      "fixture_id": "BOUND_ONLY", "bound_slot": k, **p2_entry})

    ceiling = sum(Decimal(c["max_request_cost_usd_ceil"]) for c in calls)
    call_plan = {
        "calls_planned_max": len(calls),
        "arm_a_calls": sum(1 for c in calls if c["arm"] == "A"),
        "arm_b_pass1_calls": sum(1 for c in calls if c["arm"] == "B" and c["pass"] == 1),
        "arm_b_pass2_calls_max": n_p2_max,
        "arm_c_calls": 0,
        "arm_d_calls": 0,
        "pass2_granularity": PASS2_GRANULARITY,
        "pass2_priced_with": "worst-case maximal candidate payload",
        "hard_max_cost_usd": str(ceiling),
        "retries_on_billable_path": 0,
        "calls": calls,
    }

    # ---- artifacts ---------------------------------------------------------------------
    hashes = []
    hashes.append(_write("V8A_FIXTURE_MANIFEST.json", fixture_audit))
    hashes.append(_write("V8A_CAPABILITY_MANIFEST.json",
                         {"envelope": EN.ENVELOPE_VERSION,
                          "frozen_capability": cap.version_stamp(),
                          "per_fixture": envelopes}))
    hashes.append(_write("V8A_GENERIC_LIBRARY_MANIFEST.json", generic_manifest))
    hashes.append(_write("V8A_PROMPT_FREEZE.json", prompt_freeze))
    hashes.append(_write("V8A_CALL_PLAN.json", call_plan))
    hashes.append(_write("packets_v8a.json", packets))
    hashes.append(_write("packets_arm_a.json", arm_a_packets))
    hashes.append(_write("V8A_PIT_AUDIT.json", pit))
    json.dump([{"generic_id": h["generic_id"],
                "structural_key_sha256": h["structural_key_sha256"]} for h in lib],
              open(os.path.join(OUT, "generic_library_keys.json"), "w"))

    freeze = {"v8a_freeze_version": "v8a_freeze_v1",
              "artifact_hashes": {h["artifact"]: h["sha256"] for h in hashes},
              "arm_a_missing_packets": arm_a_missing,
              "n_fixtures": len(chosen),
              "all_pit_clean": all(v["pit_clean"] for v in pit.values()),
              "all_no_banned_tokens": all(v["no_banned_tokens"] for v in pit.values()),
              "spend_so_far_usd": "0.00",
              "converse_called": False}
    _write("V8A_FREEZE.json", freeze)

    print(json.dumps({"n_fixtures": len(chosen),
                      "n_arm_a_packets": len(arm_a_packets),
                      "arm_a_missing": arm_a_missing,
                      "library": len(lib),
                      "calls_max": len(calls),
                      "hard_max_cost_usd": str(ceiling),
                      "counting_method": sorted({c["counting_method"] for c in calls}),
                      "all_pit_clean": freeze["all_pit_clean"]}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
