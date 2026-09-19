"""Generation-neutral core of the V3 identity / behavior-sensitivity control battery.

Extracted mechanically from `controls_v3_sonnet46.py` (which was hardwired to the Sonnet 4.6
generation, its output paths, and its cache) so the SAME control implementation can run
against a different generation via a `GenerationConfig`, instead of forking a second copy of
the scientific control logic (which would let the two arms drift). NOTHING about the control
definitions, distance metric, trip rule, self-noise reference, or gate semantics changed in
this extraction -- only the generation-specific model/paths were pulled out into `cfg`.

See `tests/research/test_controls_v3_core_equivalence.py` for a byte-level proof: replaying
the existing frozen Sonnet 4.6 controls through THIS module (100% cache-hit, zero new Bedrock
calls) reproduces the existing `golden_v3_sonnet46_controls.json` / `..._repeatability.json`
exactly (modulo the `created_unix` timestamp).

REUSED BY IMPORT (never reimplemented, so no arm can silently drift from another):
  * ablation_noise.state_distance        -- severity-ladder state distance, normalized [0,1]
  * repeatability.field_level_agreement / .summarize -- field-level self-noise
  * eligibility.MAX_IDENTITY_TRIP_RATE (0.20) / MIN_N_FOR_IDENTITY_GATE (5) /
    ._control_verdict -- exact inequality semantics: FAIL iff trip_rate > 0.20,
    n < 5 => INCONCLUSIVE, treated as NOT-PASS (fail closed, no salvage)
  * neutralize_v3.alias_team_tokens / .alias_competition_token / .alias_formation_id --
    the precommitted V3 alias-swap controls
  * counter_golden.cases / .score_case -- the frozen counter-evidence contract cases

CONTROL FAMILIES (unchanged):
  A. TEAM TOKEN INVARIANCE        TEAM_A/TEAM_B -> ENTITY_X/ENTITY_Y, evidence byte-identical
  B. COMPETITION TOKEN INVARIANCE COMP_NEUTRAL  -> COMP_X,            evidence byte-identical
  C. FORMATION TOKEN INVARIANCE   one formation_id token -> a different arbitrary token, with
                                  the structural counts sitting next to it UNCHANGED
  D. BEHAVIOR SENSITIVITY         a GENUINE football evidence change (formation ablation),
                                  which must move the state MORE than self-noise

A control "trips" for a fixture when the induced distance EXCEEDS that fixture's own
self-noise p90. Every live call is quota-safe: the instant AWS_DAILY_TOKEN_QUOTA is
classified the run stops and records the remainder as infrastructure-censored, never as
semantic failure.
"""
from __future__ import annotations
import itertools
import json
import os
import statistics
import time
from dataclasses import dataclass

from src.research.llm_matchup import phaseb_harness as H
from src.research.llm_matchup.hardening import ablation_noise as AN
from src.research.llm_matchup.hardening import atomic_io as AIO
from src.research.llm_matchup.hardening import adapter_v4 as A4
from src.research.llm_matchup.hardening import counter_golden as CG
from src.research.llm_matchup.hardening import eligibility as EL
from src.research.llm_matchup.hardening import neutralize_v3 as NZ3
from src.research.llm_matchup.hardening import repeatability as REP
from src.research.llm_matchup.hardening import resume_golden_v3 as RG
from src.research.llm_matchup.hardening import sampling as SMP

# Alias tokens: arbitrary, and the SAME ones the frozen V3 control design used for the 4.6 arm.
# Reused verbatim -- NOT redesigned for a second generation (checkpoint mandate).
TEAM_ALIAS_A, TEAM_ALIAS_B = "ENTITY_X", "ENTITY_Y"
COMP_ALIAS = "COMP_X"
FORMATION_ALIAS = "F_ZZ"

#: Version tag for the control DEFINITIONS (not the generation-specific wiring). Bump only if
#: the control design itself is deliberately revised -- never as a side effect of this refactor.
CONTROL_DEFINITION_VERSION = "v3_identity_controls_v1"


class QuotaExhausted(Exception):
    """Raised to unwind a control batch the instant a daily-token quota is classified."""


@dataclass
class GenerationConfig:
    """The MINIMUM generation-specific wiring the control battery needs. Everything else
    (control definitions, distance metric, trip rule, gate thresholds) is shared by import,
    not duplicated per generation."""
    name: str                  # "sonnet45" | "sonnet46" -- label only, not used for branching
    gen: object                 # versions module: versions_v3 or versions_v3_sonnet46
    cache_dir: str
    manifest: dict               # frozen fixture manifest for this generation
    golden_ledger: dict           # golden-batch execution ledger (for accepted-fixture lookup)
    controls_path: str
    repeat_path: str
    counter_path: str


def content_hashes() -> dict:
    """The shared scientific content hashes (prompt/schema/ontology/neutralization/formation).
    NOT generation-specific -- both arms are built from the same frozen contract; only
    bedrock_model_id/generation_id differ (verified by golden_manifest fingerprint checks)."""
    import hashlib
    from src.research.llm_matchup import ontology as ONT
    from src.research.llm_matchup.hardening import prompt_v4 as PR4
    from src.research.llm_matchup.hardening import schema_v3 as SCH3
    from src.research.llm_matchup.hardening import formation_structure as FS
    from src.research.llm_matchup.hardening import golden_manifest as GM
    return {
        "prompt_hash": PR4.prompt_content_hash(),
        "schema_hash": SCH3.schema_content_hash(),
        "ontology_hash": hashlib.sha256(
            json.dumps(ONT.to_dict(), sort_keys=True, default=str).encode()).hexdigest(),
        "neutralization_hash": GM._sha256_file(GM.NEUTRALIZE_MODULE_PATH),
        "formation_structure_hash": FS.structure_content_hash(),
    }


def _call(cfg: GenerationConfig, packet, call_index: int = 0):
    """One generation-bound call. Raises QuotaExhausted on daily-quota so the caller stops
    immediately. `cache_dir` + `gen` bind this to exactly one generation's cache namespace --
    the cache key additionally binds model_id, so a cross-generation collision is not
    reachable even if two generations somehow shared a cache_dir."""
    res = A4.analyze_matchup_v4(packet, use_cache=True, call_index=call_index, gen=cfg.gen,
                                cache_dir=cfg.cache_dir, capture_rejected_raw=True)
    if res.status != "OK":
        err_class = RG.classify_bedrock_error(res.manifest.get("error"))
        if err_class == "AWS_DAILY_TOKEN_QUOTA":
            raise QuotaExhausted(res.manifest.get("error"))
    return res


def _usage(res):
    """Per-call record for the artifact's call_log.

    `error` / `error_class` are REPORTING-ONLY provenance (SS27 censoring-gap fix): they are
    never read by any distance, trip, rate, threshold or gate computation. Without them an
    `LLM_STATE_UNAVAILABLE` row is a black box and a READ_TIMEOUT cannot be told apart from a
    transient throttle after the fact -- which is exactly how per-call censoring became
    invisible in the artifact."""
    m = res.manifest
    return {"status": res.status, "cache_hit": m.get("cache_hit"),
            "input_tokens": m.get("input_tokens"), "output_tokens": m.get("output_tokens"),
            "latency_s": m.get("latency_s"), "reject_reason": m.get("reject_reason"),
            "resolved_model_id": m.get("resolved_model_id"),
            "error": m.get("error"),
            "error_class": (RG.classify_bedrock_error(m.get("error"))
                            if res.status == "LLM_STATE_UNAVAILABLE" else None)}


#: Reason code for a single control call lost to infrastructure. DISTINCT from the
#: fixture-level quota codes: a per-call loss removes ONE observation from ONE arm and lets
#: the batch continue, whereas AWS_DAILY_TOKEN_QUOTA halts the whole run.
CENSOR_PER_CALL_UNAVAILABLE = "PER_CALL_INFRASTRUCTURE_UNAVAILABLE"

#: Non-OK statuses that are MODEL outcomes, not infrastructure censoring. A validator
#: rejection is the model failing the contract -- it is scientific data and must never be
#: laundered into the censoring list (that would convert a model failure into an excuse).
MODEL_OUTCOME_STATUSES = ("LLM_STATE_REJECTED",)


def build_censoring_provenance(call_log: list[dict], censored: list[dict],
                               quota_stopped: bool) -> tuple[list[dict], dict]:
    """Derive complete per-call outcome provenance from an ALREADY-PERSISTED call_log.

    Pure and offline: reads only the call log, makes no Bedrock call, and returns
    (per_call_censored_entries, provenance_block). Reporting only -- it computes nothing that
    feeds a distance, trip rate, threshold or gate, so adding it cannot move a scientific
    value.

    Fixes the SS27 defect: `run_controls` recorded `infrastructure_censored` for quota stops
    and self-noise shortfalls only, so a per-call LLM_STATE_UNAVAILABLE silently reduced an
    arm's usable n with no trace in the artifact. Categories are kept strictly distinct:
    model rejection / per-call infrastructure (sub-classified, incl. READ_TIMEOUT) / quota
    stop / not-attempted-after-quota-stop / self-noise shortfall.
    """
    per_call, model_outcomes = [], []
    for r in call_log:
        status = r.get("status")
        if status == "OK":
            continue
        entry = {"fixture_id": r.get("fixture_id"), "arm": r.get("arm"),
                 "call_index": r.get("call_index"), "status": status}
        if status in MODEL_OUTCOME_STATUSES:
            model_outcomes.append({**entry, "reject_reason": r.get("reject_reason"),
                                   "classification": "MODEL_OUTCOME"})
            continue
        # A log written before the error/error_class fields existed cannot be re-classified
        # retroactively. Say so explicitly rather than emitting a bare null that reads like
        # "no error class" instead of "never recorded".
        per_call.append({**entry, "reason": CENSOR_PER_CALL_UNAVAILABLE,
                         "error_class": (r.get("error_class")
                                         or ("UNKNOWN_NOT_PERSISTED" if "error_class" not in r
                                             else "OTHER_UNAVAILABLE")),
                         "error": r.get("error"),
                         "classification": "INFRASTRUCTURE_CENSORED"})

    by_arm: dict = {}
    for r in call_log:
        a = by_arm.setdefault(r.get("arm"), {"attempted": 0, "ok": 0,
                                             "model_rejected": 0, "infra_unavailable": 0})
        a["attempted"] += 1
        st = r.get("status")
        if st == "OK":
            a["ok"] += 1
        elif st in MODEL_OUTCOME_STATUSES:
            a["model_rejected"] += 1
        else:
            a["infra_unavailable"] += 1

    prov = {
        "schema": "control_call_outcome_provenance_v1",
        "note": ("Reporting-only provenance derived from the persisted call_log. Per-call "
                 "infrastructure losses reduce an arm's usable n and are now represented "
                 "explicitly; model rejections are reported separately and are NOT censoring."),
        "per_arm_accounting": by_arm,
        "model_outcomes": model_outcomes,
        "n_model_rejected": len(model_outcomes),
        "per_call_infrastructure_censored": per_call,
        "n_per_call_infrastructure_censored": len(per_call),
        "error_class_counts": _count_by(per_call, "error_class"),
        "fixture_level_censored": list(censored),
        "n_fixture_level_censored": len(censored),
        "quota_stopped": bool(quota_stopped),
    }
    return per_call, prov


def _count_by(rows: list[dict], key: str) -> dict:
    out: dict = {}
    for r in rows:
        out[r.get(key)] = out.get(r.get(key), 0) + 1
    return out


def _self_noise(ok_states):
    """Pairwise self-noise distances + p90."""
    ds = []
    for a, b in itertools.combinations(ok_states, 2):
        d, _ = AN.state_distance(a, b)
        ds.append(d)
    p90 = sorted(ds)[int(0.9 * (len(ds) - 1))] if ds else 0.0
    return p90, ds


def _pick_formation_id(neutral_packet: dict) -> str | None:
    """Any formation_id token actually present in the neutral packet, so control C perturbs a
    token the model can actually see. Prefers a real (non-unknown) shape."""
    found = []
    for e in neutral_packet.get("evidence", []) or []:
        sc = e.get("scope") or {}
        for k, v in sc.items():
            if k.endswith("formation_id") and isinstance(v, str):
                found.append(v)
    fcx = neutral_packet.get("formation_context") or {}
    for key in ("team_a_prematch_formation", "team_b_prematch_formation"):
        d = fcx.get(key) or {}
        if isinstance(d, dict) and isinstance(d.get("formation_id"), str):
            found.append(d["formation_id"])
    for f in found:
        if f and "UNK" not in f.upper():
            return f
    return found[0] if found else None


def _trip(distance, noise_p90):
    return bool(distance > noise_p90)


def build_control_manifest(cfg: GenerationConfig, chosen_fixtures: list[str], k: int) -> dict:
    """Deterministically materialize the COMPLETE intended control battery -- fixture ids,
    perturbation definitions, and every packet hash that will be sent -- BEFORE any paid call.
    Hashing this before spend (and refusing to silently overwrite it, see
    `freeze_control_manifest_if_absent`) proves the control selection could not have been
    influenced by live results, mirroring `golden_manifest`'s fixture-manifest freeze."""
    import hashlib
    sp = cfg.manifest["generation_fingerprint"]["sampling_params"]
    ctx = H.HarnessContext(enrich_halves=False)
    picks = {p.fixture_id: p for p in SMP.select_stratified(ctx, n=sp["n"],
                                                            max_scan=sp["max_scan"])}
    rows = []
    for fid in chosen_fixtures:
        cand = picks[fid].candidate
        src_full = ctx.build_packet(cand, include_formation=True, projected=True)
        neu = NZ3.neutralize_for_llm_v2(src_full)
        src_abl = ctx.build_packet(cand, include_formation=False, projected=True)
        neu_abl = NZ3.neutralize_for_llm_v2(src_abl)
        old_formation_id = _pick_formation_id(neu)
        rows.append({
            "fixture_id": fid,
            "source_packet_hash": neu.get("source_evidence_packet_hash"),
            "neutral_packet_hash": neu.get("packet_hash"),
            "team_alias_control": {"from": ["TEAM_A", "TEAM_B"],
                                   "to": [TEAM_ALIAS_A, TEAM_ALIAS_B]},
            "competition_alias_control": {"to": COMP_ALIAS},
            "formation_alias_control": {"from": old_formation_id, "to": FORMATION_ALIAS},
            "behavior_sensitivity_control": {
                "perturbation": "formation_ablation(include_formation=False)",
                "neutral_packet_hash": neu_abl.get("packet_hash")},
            "k_self_noise_calls": k,
        })
    manifest = {
        "study": f"golden_v3_{cfg.name}_control_manifest",
        "generation_id": cfg.gen.GENERATION_ID,
        "model_id": cfg.gen.DEFAULT_BEDROCK_MODEL_ID,
        "control_definition_version": CONTROL_DEFINITION_VERSION,
        "fixture_manifest_hash": cfg.manifest["fixture_manifest_hash"],
        "content_hashes": content_hashes(),
        "k_self_noise_calls": k,
        "fixture_ids": list(chosen_fixtures),
        "rows": rows,
    }
    manifest["control_manifest_hash"] = hashlib.sha256(
        json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()
    return manifest


def freeze_control_manifest_if_absent(manifest: dict, path: str) -> str:
    """Persist ONLY if no control manifest exists yet at `path` -- never silently overwrite a
    prior frozen control selection (same contract as `golden_manifest.save_manifest_if_absent`)."""
    if os.path.exists(path):
        return "EXISTS_UNCHANGED"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    json.dump(manifest, open(path, "w"), indent=2, default=str)
    return "CREATED"


def load_control_manifest(path: str) -> dict | None:
    if not os.path.exists(path):
        return None
    return json.load(open(path))


def accepted_fixture_ids(cfg: GenerationConfig) -> list[str]:
    """Fixture ids ACCEPTED (status SUCCESS) in this generation's golden batch, in frozen
    manifest order -- deterministic given the ledger, never resampled."""
    return [f for f in cfg.manifest["fixture_ids"]
            if (cfg.golden_ledger.get("fixtures", {}).get(f) or {}).get("status") == "SUCCESS"]


def run_controls(cfg: GenerationConfig, fixtures: list[str] | None = None, n_fixtures: int = 8,
                 k: int = 3, persist: bool = True) -> dict:
    """Controls A-D + repeatability, on fixtures ACCEPTED in this generation's golden batch.

    Per fixture: k identical calls (self-noise + repeatability; call_index 0 is already
    cached from the golden batch so only k-1 are new), then one call each for the
    team-alias, competition-alias, formation-alias and formation-ablation packets.
    """
    sp = cfg.manifest["generation_fingerprint"]["sampling_params"]
    accepted = accepted_fixture_ids(cfg)
    chosen = fixtures or accepted[:n_fixtures]

    ctx = H.HarnessContext(enrich_halves=False)
    picks = {p.fixture_id: p for p in SMP.select_stratified(ctx, n=sp["n"],
                                                            max_scan=sp["max_scan"])}

    team_rows, comp_rows, form_rows, abl_rows = [], [], [], []
    repeat_field_rows, per_fixture_repeat = [], []
    call_log = []
    quota_hit = False
    censored = []

    for fid in chosen:
        try:
            cand = picks[fid].candidate
            src_full = ctx.build_packet(cand, include_formation=True, projected=True)
            neu = NZ3.neutralize_for_llm_v2(src_full)

            # --- k identical calls: self-noise + field-level repeatability -----------
            results = [_call(cfg, neu, call_index=i) for i in range(k)]
            for i, r in enumerate(results):
                call_log.append({"fixture_id": fid, "arm": "self_noise",
                                 "call_index": i, **_usage(r)})
            ok_states = [r.state for r in results if r.status == "OK"]
            if len(ok_states) < 2:
                censored.append({"fixture_id": fid, "reason": "FEWER_THAN_2_OK_SELF_NOISE_CALLS",
                                 "n_ok": len(ok_states)})
                continue

            noise_p90, noise_ds = _self_noise(ok_states)
            frows = REP.field_level_agreement([r.state for r in results])
            for fr in frows:
                repeat_field_rows.append({"fixture_id": fid, **fr})
            per_fixture_repeat.append({
                "fixture_id": fid, "k": k, "n_ok": len(ok_states),
                "self_noise_p90": round(noise_p90, 4),
                "self_noise_mean": round(statistics.fmean(noise_ds), 4) if noise_ds else 0.0,
                "self_noise_distances": [round(d, 4) for d in noise_ds],
                **REP.summarize(frows),
            })
            ref = ok_states[0]

            # --- A. team token invariance -------------------------------------------
            p_team = NZ3.alias_team_tokens(neu, TEAM_ALIAS_A, TEAM_ALIAS_B)
            r_team = _call(cfg, p_team)
            call_log.append({"fixture_id": fid, "arm": "team_alias", **_usage(r_team)})
            if r_team.status == "OK":
                d, _ = AN.state_distance(ref, r_team.state)
                team_rows.append({"fixture_id": fid, "distance": d,
                                  "self_noise_p90": round(noise_p90, 4),
                                  "exceeds_noise": _trip(d, noise_p90),
                                  "flag": ("TEAM_TOKEN_SENSITIVITY" if _trip(d, noise_p90)
                                           else "OK")})

            # --- B. competition token invariance ------------------------------------
            p_comp = NZ3.alias_competition_token(neu, COMP_ALIAS)
            r_comp = _call(cfg, p_comp)
            call_log.append({"fixture_id": fid, "arm": "competition_alias", **_usage(r_comp)})
            if r_comp.status == "OK":
                d, _ = AN.state_distance(ref, r_comp.state)
                comp_rows.append({"fixture_id": fid, "distance": d,
                                  "self_noise_p90": round(noise_p90, 4),
                                  "exceeds_noise": _trip(d, noise_p90),
                                  "flag": ("COMPETITION_TOKEN_SENSITIVITY"
                                           if _trip(d, noise_p90) else "OK")})

            # --- C. formation token invariance --------------------------------------
            old_fid = _pick_formation_id(neu)
            if old_fid:
                p_form = NZ3.alias_formation_id(neu, old_fid, FORMATION_ALIAS)
                r_form = _call(cfg, p_form)
                call_log.append({"fixture_id": fid, "arm": "formation_alias",
                                 "aliased_formation_id": old_fid, **_usage(r_form)})
                if r_form.status == "OK":
                    d, _ = AN.state_distance(ref, r_form.state)
                    form_rows.append({"fixture_id": fid, "aliased_formation_id": old_fid,
                                      "distance": d, "self_noise_p90": round(noise_p90, 4),
                                      "exceeds_noise": _trip(d, noise_p90),
                                      "flag": ("FORMATION_TOKEN_SENSITIVITY"
                                               if _trip(d, noise_p90) else "OK")})

            # --- D. behavior sensitivity (GENUINE evidence change) -------------------
            src_abl = ctx.build_packet(cand, include_formation=False, projected=True)
            neu_abl = NZ3.neutralize_for_llm_v2(src_abl)
            r_abl = _call(cfg, neu_abl)
            call_log.append({"fixture_id": fid, "arm": "formation_ablation", **_usage(r_abl)})
            if r_abl.status == "OK":
                d, _ = AN.state_distance(ref, r_abl.state)
                abl_rows.append({"fixture_id": fid, "distance": d,
                                 "self_noise_p90": round(noise_p90, 4),
                                 "exceeds_noise": _trip(d, noise_p90),
                                 "flag": ("SENSITIVE_TO_FOOTBALL_EVIDENCE"
                                          if _trip(d, noise_p90) else "INSENSITIVE")})

        except QuotaExhausted as e:
            quota_hit = True
            censored.append({"fixture_id": fid, "reason": "AWS_DAILY_TOKEN_QUOTA",
                             "error": str(e)[:300]})
            break

    if quota_hit:
        for f in chosen[chosen.index(censored[-1]["fixture_id"]) + 1:]:
            censored.append({"fixture_id": f, "reason": "NOT_ATTEMPTED_AFTER_QUOTA_STOP"})

    # SS27 censoring-gap fix (reporting only): per-call infrastructure losses reduce usable n
    # and must be visible in the artifact. Appended AFTER the quota block above, which indexes
    # censored[-1]. Model rejections are deliberately NOT added here.
    _per_call_censored, _censor_provenance = build_censoring_provenance(
        call_log, censored, quota_hit)
    censored = censored + _per_call_censored

    def rate(rows, flag):
        trips = sum(1 for r in rows if r["flag"] == flag)
        ds = [r["distance"] for r in rows]
        return {"n": len(rows), "n_tripped": trips,
                "trip_rate": round(trips / len(rows), 4) if rows else None,
                "mean_distance": round(statistics.fmean(ds), 4) if ds else None,
                "median_distance": round(statistics.median(ds), 4) if ds else None,
                "max_distance": max(ds) if ds else None}

    team = rate(team_rows, "TEAM_TOKEN_SENSITIVITY")
    comp = rate(comp_rows, "COMPETITION_TOKEN_SENSITIVITY")
    form = rate(form_rows, "FORMATION_TOKEN_SENSITIVITY")
    abl = rate(abl_rows, "SENSITIVE_TO_FOOTBALL_EVIDENCE")

    # --- the global identity gate, using the EXISTING inequality semantics -----------
    verdicts = {"team_token_control": EL._control_verdict(team),
                "competition_token_control": EL._control_verdict(comp),
                "formation_token_control": EL._control_verdict(form)}
    failed = [k_ for k_, v in verdicts.items() if v["status"] != "PASS"]
    gate = {
        "gate": "identity_controls_global_gate",
        "generation_id": cfg.gen.GENERATION_ID,
        "threshold": {"max_trip_rate": EL.MAX_IDENTITY_TRIP_RATE,
                      "min_n": EL.MIN_N_FOR_IDENTITY_GATE,
                      "inequality": "FAIL iff trip_rate > max_trip_rate (strictly greater)",
                      "source": "eligibility.MAX_IDENTITY_TRIP_RATE / "
                                "eligibility._control_verdict (unchanged, imported)"},
        "verdicts": verdicts,
        "failed_controls": failed,
        "identity_gate_passed": len(failed) == 0,
    }

    # --- honest interpretation guard ---------------------------------------------------
    noise_means = [r["self_noise_mean"] for r in per_fixture_repeat]
    interpretation = {
        "alias_distances_within_noise": (
            (team["trip_rate"] == 0 if team["trip_rate"] is not None else None),
            (comp["trip_rate"] == 0 if comp["trip_rate"] is not None else None),
            (form["trip_rate"] == 0 if form["trip_rate"] is not None else None)),
        "behavior_sensitivity_exceeds_noise_rate": abl["trip_rate"],
        "mean_self_noise": (round(statistics.fmean(noise_means), 4) if noise_means else None),
        "degenerate_near_constant": bool(
            abl["trip_rate"] is not None and abl["trip_rate"] == 0
            and (team["trip_rate"] == 0 if team["trip_rate"] is not None else False)),
        "degenerate_note": (
            "TRUE means the model passed identity invariance while ALSO failing to respond to "
            "a genuine football evidence change -- i.e. it may be emitting near-constant "
            "states. That is NOT a success; identity invariance is necessary but insufficient "
            "(mandate SS19)."),
    }

    out = {
        "study": f"golden_v3_{cfg.name}_controls",
        "generation_id": cfg.gen.GENERATION_ID,
        "model_id": cfg.gen.DEFAULT_BEDROCK_MODEL_ID,
        "control_definition_version": CONTROL_DEFINITION_VERSION,
        "fixture_manifest_hash": cfg.manifest["fixture_manifest_hash"],
        "content_hashes": content_hashes(),
        "k_self_noise_calls": k,
        "fixtures_requested": chosen,
        "n_fixtures_with_usable_self_noise": len(per_fixture_repeat),
        "aliases": {"team": [TEAM_ALIAS_A, TEAM_ALIAS_B], "competition": COMP_ALIAS,
                    "formation": FORMATION_ALIAS},
        "controls": {
            "A_team_token_invariance": {**team, "rows": team_rows},
            "B_competition_token_invariance": {**comp, "rows": comp_rows},
            "C_formation_token_invariance": {**form, "rows": form_rows},
            "D_behavior_sensitivity_formation_ablation": {**abl, "rows": abl_rows},
        },
        "identity_gate": gate,
        "interpretation": interpretation,
        "infrastructure_censored": censored,
        "censoring_provenance": _censor_provenance,
        "quota_stopped": quota_hit,
        "n_calls_logged": len(call_log),
        "call_log": call_log,
        "created_unix": int(time.time()),
    }
    repeat = {
        "study": f"golden_v3_{cfg.name}_repeatability",
        "generation_id": cfg.gen.GENERATION_ID,
        "model_id": cfg.gen.DEFAULT_BEDROCK_MODEL_ID,
        "k": k,
        "n_fixtures": len(per_fixture_repeat),
        "per_fixture": per_fixture_repeat,
        "pooled": REP.summarize([{k2: v for k2, v in r.items() if k2 != "fixture_id"}
                                 for r in repeat_field_rows]) if repeat_field_rows else {},
        "field_rows": repeat_field_rows,
        "self_noise_pooled": {
            "mean": (round(statistics.fmean(noise_means), 4) if noise_means else None),
            "median": (round(statistics.median(noise_means), 4) if noise_means else None),
            "min": min(noise_means) if noise_means else None,
            "max": max(noise_means) if noise_means else None,
        },
        "created_unix": int(time.time()),
    }
    if persist:
        AIO.atomic_write_json(cfg.controls_path, out)
        AIO.atomic_write_json(cfg.repeat_path, repeat)
    return {"controls": out, "repeatability": repeat}


def run_counter_evidence(cfg: GenerationConfig, k: int = 1, persist: bool = True) -> dict:
    """Counter-evidence contract on the EXISTING golden contradiction cases A-F.

    Reuses counter_golden.cases() and counter_golden.score_case() verbatim -- the objective
    criteria (recall of the SPECIFICALLY planted counter id, whether the state was
    CONSTRAINED, and case F's false-opposition control) are unchanged. Counter-evidence
    QUANTITY is deliberately not rewarded.
    """
    cases = CG.cases()
    rows, call_log = [], []
    quota_hit = False
    for cid, case in cases.items():
        if quota_hit:
            rows.append({"case": cid, "status": "NOT_ATTEMPTED_AFTER_QUOTA_STOP"})
            continue
        # adapter_v4 structurally requires a NEUTRALIZED packet; these synthetic packets are
        # already identity-neutral by construction, so this only retypes/rehashes them.
        neutral = NZ3.neutralize_for_llm_v2(case["packet"])
        scored = []
        try:
            for i in range(k):
                r = _call(cfg, neutral, call_index=i)
                call_log.append({"case": cid, "call_index": i, **_usage(r)})
                if r.status == "OK":
                    scored.append(CG.score_case(cid, case, r.state))
                else:
                    scored.append({"case": cid, "mechanism": case["target_mechanism"],
                                   "mechanism_present": False, "pass": False,
                                   "note": f"{r.status}: {r.manifest.get('reject_reason') or r.manifest.get('error')}"})
        except QuotaExhausted as e:
            quota_hit = True
            rows.append({"case": cid, "status": "AWS_DAILY_TOKEN_QUOTA", "error": str(e)[:200]})
            continue

        oks = [s for s in scored if s.get("mechanism_present")]
        recalls = [s["counter_recall"] for s in oks if s.get("counter_recall") is not None]
        rows.append({
            "case": cid, "target_mechanism": case["target_mechanism"],
            "counter_expected": case["expect"]["counter_expected"], "k_calls": k,
            "n_ok": len(oks),
            "min_explicit_recall": (min(recalls) if recalls else None),
            "mean_explicit_recall": (round(statistics.fmean(recalls), 4) if recalls else None),
            "any_false_opposition": any(s.get("false_opposition") for s in oks),
            "all_state_constrained": bool(oks) and all(s.get("state_constrained") for s in oks),
            "all_uncertainty_ok": bool(oks) and all(s.get("uncertainty_ok") for s in oks),
            "all_search_performed": bool(oks) and all(s.get("counter_search_performed")
                                                      for s in oks),
            "statuses": "|".join(str(s.get("status")) for s in oks),
            "constraint_pass": bool(oks) and all(s["pass"] for s in oks),
            "notes": [s.get("note") for s in scored if s.get("note")],
        })

    scored_rows = [r for r in rows if "constraint_pass" in r]
    n_pass = sum(1 for r in scored_rows if r["constraint_pass"])
    out = {
        "study": f"golden_v3_{cfg.name}_counter_evidence",
        "generation_id": cfg.gen.GENERATION_ID,
        "model_id": cfg.gen.DEFAULT_BEDROCK_MODEL_ID,
        "k_calls": k,
        "n_cases": len(cases),
        "n_cases_scored": len(scored_rows),
        "n_constraint_pass": n_pass,
        "constraint_pass_rate": (round(n_pass / len(scored_rows), 4) if scored_rows else None),
        "n_explicit_recall_any": sum(1 for r in scored_rows
                                     if (r.get("min_explicit_recall") or 0) > 0),
        "n_false_opposition": sum(1 for r in scored_rows if r.get("any_false_opposition")),
        "quota_stopped": quota_hit,
        "rows": rows,
        "call_log": call_log,
        "note": ("Pass gate is the CONSTRAINT contract (counter-evidence must constrain the "
                 "state), evaluated worst-case across k calls. Explicit recall is reported "
                 "separately and is NOT part of the gate. Case F is the false-opposition "
                 "control: inventing opposition where none was planted counts AGAINST."),
        "created_unix": int(time.time()),
    }
    if persist:
        os.makedirs(os.path.dirname(cfg.counter_path), exist_ok=True)
        json.dump(out, open(cfg.counter_path, "w"), indent=2, default=str)
    return out
