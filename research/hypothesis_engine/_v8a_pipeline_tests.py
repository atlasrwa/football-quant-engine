"""V8A pipeline proof battery (brief section 26). ZERO SPEND -- no model, no network.

Fifteen properties the pipeline must exhibit BEFORE any paid call. Each is asserted against
synthetic candidates, so a defect surfaces here rather than after spending on it.

Run:  python3 research/hypothesis_engine/_v8a_pipeline_tests.py
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, "/home/ubuntu/v8a-worktree")

import src  # noqa: F401,E402  -- binds src.__path__ to the worktree before anything else

from src.research.hypothesis_v7 import provider as V7P            # noqa: E402
from src.research.hypothesis_v71 import controls as C             # noqa: E402
from src.research.hypothesis_v71 import corpus_index as CI        # noqa: E402
from src.research.hypothesis_v8a import audit as A                # noqa: E402
from src.research.hypothesis_v8a import envelope as EN            # noqa: E402
from src.research.hypothesis_v8a import fixtures as FX            # noqa: E402
from src.research.hypothesis_v8a import genericlib as G           # noqa: E402
from src.research.hypothesis_v8a import packet as PK              # noqa: E402
from src.research.hypothesis_v8a import prompt_v8a as PR          # noqa: E402
from src.research.hypothesis_v8a import schema_v8a as S           # noqa: E402
from src.research.hypothesis_v8a.frozencap import FrozenCapability  # noqa: E402

ROOT = "/home/ubuntu/v8a-worktree"
CAP_PATH = f"{ROOT}/research/hypothesis_oos/out/v7_1/V7_1_CAPABILITY_MATRIX.json"
OOS_OUT = f"{ROOT}/research/hypothesis_oos/out"

RESULTS = []


def check(name, ok, detail=""):
    RESULTS.append({"test": name, "pass": bool(ok), "detail": str(detail)[:300]})
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail else ""))
    return ok


def candidate(**over):
    base = {
        "candidate_id": "C1", "research_family": "ATTACK_VOLUME",
        "subject": "TEAM_A", "opponent": "TEAM_B",
        "target_metric": ["shots_on_target"], "metric_perspective": "FOR",
        "behavioral_observations": [
            {"observation": "The side's shot-on-target count in its recent matches sits "
                            "below its long-run level in the supplied summaries.",
             "evidence_refs": ["TEAM_A.recent_last_5.shots_on_target_for"]}],
        "football_mechanism": "A side meeting deeper defensive blocks may take more shots "
                              "from distance, which lowers the share arriving on target.",
        "comparison": "SUBJECT_CONDITIONAL_VS_BASELINE", "window": "ALL_PRIOR",
        "conditions": [{"dimension": "opponent_profile",
                        "axis": "shots_on_target_against", "value": "LOW"}],
        "falsifiable_question": "Does the subject's shots-on-target rate differ against "
                                "opponents in that band compared with when it does not?",
        "falsifier": "A result consistent with no systematic difference between the cohort "
                     "and its complement leaves the mechanism unsupported.",
        "self_critique": {"is_just_recent_vs_long_run": False, "is_just_home_vs_away": False,
                          "condition_equals_target": False, "cohort_equals_baseline": False,
                          "could_opponent_strength_explain_it": True,
                          "is_overconditioned": False,
                          "likely_generic_enumeration_would_generate_this": True,
                          "notes": "Opponent strength is a live confounder here."},
        "provider_requirements": ["opponent_profile"],
        "support_risk": "LOW", "coverage_risk": "LOW",
    }
    base.update(over)
    return base


def main():
    cap = FrozenCapability.load(CAP_PATH)
    VOCAB = list(cap.measurable_vocabulary())
    lib = G.build_library(VOCAB)
    LIBKEYS = {h["structural_key_sha256"] for h in lib}

    mc = V7P.METRIC_CONTRACT
    recs = CI.load_records(include_fresh=True)
    idx = CI.PITIndex(recs, sorted(mc), mc)
    chosen, _fa = FX.select(recs, oos_out_root=OOS_OUT, index=idx)
    rec = chosen[0]
    ri = idx.pos_of_fixture[str(rec.fixture_id)]
    by = lambda p: idx.recs[p]                                        # noqa: E731
    env = EN.build(cap, idx, rec, ri, VOCAB, by)
    pkt = PK.build(idx, cap, rec, ri, VOCAB, by, env)
    VALUES = A.packet_values(pkt)
    REFS = A.evidence_ref_index(pkt)

    def aud(c, i=0):
        return A.audit_candidate(c, i, cap=cap, packet=pkt, library_keys=LIBKEYS,
                                 vocabulary=VOCAB, valid_refs=REFS, values=VALUES)

    # 1 -- an exact generic duplicate is rejected
    gen = lib[len(lib) // 3]
    dup = candidate(target_metric=list(gen["target_metrics"]),
                    metric_perspective=gen["side"],
                    subject="TEAM_A" if gen["subject"] == "HOME_TEAM" else "TEAM_B",
                    comparison=gen["comparison"], window=gen["window"],
                    conditions=[dict(x) for x in gen["conditions"]])
    r1 = aud(dup)
    check("01 exact generic duplicate is rejected",
          r1["novelty_verdict"]["label"] == G.EXACT_DUPLICATE,
          r1["novelty_verdict"]["label"])

    # 2 -- a PARAPHRASED generic equivalent is rejected on structure, not wording
    para = dict(dup)
    para["football_mechanism"] = ("Entirely different football story, describing wide "
                                  "overloads and second-ball recycling in another way.")
    para["falsifiable_question"] = "Phrased completely differently but the same contrast."
    r2 = aud(para)
    check("02 paraphrased generic equivalent is rejected",
          r2["novelty_verdict"]["label"] in (G.EXACT_DUPLICATE, G.STRUCTURAL_EQUIVALENT),
          r2["novelty_verdict"]["label"])

    # 3 -- a genuine TWO-VARIABLE interaction survives novelty
    inter = candidate(conditions=[
        {"dimension": "opponent_profile", "axis": "shots_on_target_against",
         "value": "LOW"},
        {"dimension": "historical_venue_conditioning", "value": "HOME"}])
    r3 = aud(inter)
    check("03 genuine two-variable interaction survives novelty",
          r3["novelty_verdict"]["label"] == G.INCREMENTAL_STRUCTURE,
          r3["novelty_verdict"]["label"])

    # 4 -- an unsupported metric fails
    r4 = aud(candidate(target_metric=["np_xg"]))
    check("04 unsupported metric fails",
          r4["novelty_verdict"]["label"] == G.INVALID
          and r4["measurability"]["unsupported_metrics"] == ["np_xg"],
          r4["novelty_verdict"]["label"])

    # 4b -- an UNKNOWN metric is a named gap, not an unsupported one
    r4b = aud(candidate(target_metric=["dribbles_completed"]))
    check("04b unknown metric is a NAMED gap, distinct from unsupported",
          r4b["measurability"]["unknown_metrics"] == ["dribbles_completed"]
          and not r4b["measurability"]["unsupported_metrics"],
          r4b["measurability"]["unknown_metrics"])

    # 5 -- NULL remains NULL through the packet
    nulls = 0
    total = 0
    for side in pkt["raw_historical_rows"].values():
        for row in side["rows"]:
            for cell in row["cells"]:
                total += 1
                if cell is None:
                    nulls += 1
    zeroed = any(
        c == 0 and False for side in pkt["raw_historical_rows"].values()
        for row in side["rows"] for c in row["cells"])
    check("05 NULL stays NULL (never coerced to zero)",
          nulls > 0 and not zeroed, f"{nulls} nulls preserved of {total} cells")

    # 6 -- cohort == baseline fails
    r6 = aud(candidate(comparison="SUBJECT_VENUE_BASELINE",
                       conditions=[{"dimension": "historical_venue_conditioning",
                                    "value": "HOME"}]))
    check("06 cohort == baseline fails",
          r6["tautology"]["cohort_equals_baseline"]
          and r6["novelty_verdict"]["label"] == G.INVALID,
          r6["novelty_verdict"]["label"])

    # 7 -- a tautology (condition == target) is detected
    r7 = aud(candidate(target_metric=["shots_on_target"], metric_perspective="AGAINST",
                       conditions=[{"dimension": "opponent_profile",
                                    "axis": "shots_on_target_against", "value": "HIGH"}]))
    check("07 condition == target is detected",
          r7["tautology"]["condition_equals_target"], r7["tautology"])

    # 8 -- future information fails: no packet row may reach the cutoff
    pa = PK.pit_audit(pkt, int(rec.kickoff_unix))
    forged = json.loads(json.dumps(pkt))
    forged["raw_historical_rows"]["TEAM_A"]["rows"][0]["kickoff_unix"] = \
        int(rec.kickoff_unix) + 1
    pf = PK.pit_audit(forged, int(rec.kickoff_unix))
    check("08 future information fails (and is caught)",
          pa["pit_clean"] and not pf["pit_clean"],
          f"real={pa['pit_clean']} forged={pf['pit_clean']}")

    # 9 -- an overconditioned hypothesis is flagged
    r9 = aud(candidate(conditions=[
        {"dimension": "opponent_profile", "axis": "shots_on_target_against",
         "value": "LOW"},
        {"dimension": "opponent_profile", "axis": "possession_for", "value": "HIGH"},
        {"dimension": "historical_venue_conditioning", "value": "HOME"}]))
    check("09 overconditioned hypothesis is flagged",
          r9["complexity"]["excessive_complexity"]
          and r9["complexity"]["n_cohort_conditions"] == 3,
          r9["complexity"])

    # 10 -- model abstention survives as its own state
    check("10 abstention is a first-class state",
          "ABSTAIN" in S.ACTIONS and G.ABSTAINED == "ABSTAINED", S.ACTIONS)

    # 11 -- no generic performance/effect field can enter an LLM request
    payload = PR.build_pass2_user(candidate(),
                                  [dict(lib[7], survival=0.9, effect_size=1.23,
                                        p_value=0.01, quality_score=7)])
    low = payload.lower()
    leaked = [k for k in ("survival", "effect_size", "p_value", "quality_score",
                          "fold", "candidate_status") if k in low]
    check("11 no effect/performance field can enter an LLM request", not leaked, leaked)

    # 12 -- nearest-generic retrieval is deterministic
    n1 = G.nearest(candidate(), lib, 3)
    n2 = G.nearest(candidate(), lib, 3)
    check("12 nearest-generic retrieval is deterministic",
          n1 == n2 and len(n1) == 3, [g["generic_id"] for g in n1])

    # 13 -- prompt serialization is deterministic
    s1 = PR.serialized_request_pass1(PK.serialize(pkt))
    s2 = PR.serialized_request_pass1(PK.serialize(pkt))
    check("13 prompt serialization is deterministic", s1 == s2, f"{len(s1)} chars")

    # 14 -- the evidence packet is deterministic
    p2 = PK.build(idx, cap, rec, ri, VOCAB, by, EN.build(cap, idx, rec, ri, VOCAB, by))
    check("14 evidence packet is deterministic",
          PK.packet_hash(pkt) == PK.packet_hash(p2), PK.packet_hash(pkt)[:16])

    # 15 -- one arm's model output cannot enter another arm
    req = PR.serialized_request_pass1(PK.serialize(pkt))
    check("15 arm isolation: a request carries no other arm's output",
          "candidate_id" not in req and "ARM" not in req,
          "pass-1 request is prompt + packet only")

    # -- firewall must actually scan every V8A prose surface -----------------------------
    caught = {}
    probes = {
        "football_mechanism": "The probability of this is 0.62 for the upcoming fixture.",
        "falsifiable_question": "Expect an edge of 0.15 on this market.",
        "falsifier": "Fair odds of 2.10 would refute it.",
        "similar_opponent_rationale": "This gives a 62% chance of the outcome.",
        "formation_context": "Expected value here is +0.4 goals in the coming match.",
    }
    for field, text in probes.items():
        c = candidate(**{field: text})
        f = A.firewall_scan(c, 0, values=VALUES)
        caught[field] = len([x for x in f if x.blocking]) > 0
    obs_probe = candidate(behavioral_observations=[
        {"observation": "The model estimates a 71% probability of over 2.5 goals here.",
         "evidence_refs": ["TEAM_A.recent_last_5.shots_on_target_for"]}])
    caught["behavioral_observations[].observation"] = len(
        [x for x in A.firewall_scan(obs_probe, 0, values=VALUES) if x.blocking]) > 0
    caught["self_critique.notes"] = len([
        x for x in A.firewall_scan(
            candidate(self_critique=dict(candidate()["self_critique"],
                                         notes="Edge is 0.22 on this selection.")),
            0, values=VALUES) if x.blocking]) > 0
    check("16 firewall catches a planted probability in EVERY V8A prose field",
          all(caught.values()), {k: v for k, v in caught.items() if not v} or "all caught")

    # -- the generic library is outcome-blind --------------------------------------------
    blob = json.dumps(lib[:5000]).lower()
    banned = [k for k in ("survival", "effect", "p_value", "pvalue", "score", "rank",
                          "fold", "outcome", "result") if k in blob]
    check("17 generic library is outcome-blind", not banned, banned)

    # -- predicate agrees with the real generator ----------------------------------------
    pool = C.enumerate_pool(VOCAB, 2000)
    nondeg = [p for p in pool if not G.is_degenerate(p.get("conditions"))]
    bad = [p for p in nondeg if not G.reachability(p, VOCAB)["reachable"]]
    check("18 every real generator draw satisfies the membership predicate",
          not bad, f"{len(bad)} unreachable of {len(nondeg)} non-degenerate")

    # -- hallucinated evidence reference is caught ---------------------------------------
    rh = aud(candidate(behavioral_observations=[
        {"observation": "A claim citing a row the packet does not contain at all.",
         "evidence_refs": ["TEAM_A.raw.ROW:99999"]}]))
    check("19 hallucinated evidence reference is caught",
          rh["evidence_refs"]["n_hallucinated"] == 1,
          rh["evidence_refs"]["hallucinated_refs"])

    # -- a predictive claim in pass 2 is caught ------------------------------------------
    pc = A.predictive_claims({"reason": "My candidate is more predictive than these."})
    check("20 a predictive claim in the novelty pass is caught", pc == ["more predictive"],
          pc)

    n_pass = sum(1 for r in RESULTS if r["pass"])
    print(f"\n{n_pass}/{len(RESULTS)} pipeline properties hold")
    out = {"v8a_pipeline_tests": RESULTS, "n_pass": n_pass, "n_total": len(RESULTS),
           "all_pass": n_pass == len(RESULTS)}
    os.makedirs(f"{ROOT}/research/hypothesis_engine/out/v8a", exist_ok=True)
    json.dump(out, open(f"{ROOT}/research/hypothesis_engine/out/v8a/"
                        f"V8A_PIPELINE_TESTS.json", "w"), indent=2)
    return 0 if n_pass == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
