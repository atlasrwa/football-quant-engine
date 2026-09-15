"""Frozen golden battery + pre-spend manifest (`hypothesis_battery_v1`).

Mandate §26: do NOT reuse the legacy golden battery. Build a smaller, scientifically
targeted frozen set covering varied formations, formation missingness, corner/shot/card
profiles, home-away asymmetry, competition context and provider coverage.

Mandate §30: produce a spend-authorization manifest and STOP. Nothing in this module makes
a network call; `freeze_battery` reads the local corpus and writes JSON, and
`build_manifest` is pure arithmetic over that frozen set.

There is deliberately no `run()` here. Execution belongs behind an explicit authorization
step, and the absence of the function is part of the guarantee.
"""
from __future__ import annotations

import json
import os
import statistics
from dataclasses import dataclass, field
from typing import Optional, Sequence

from . import (capability, context_packet as CP, evaluation, leakage, lifecycle,
               prompt as PROMPT, schema, vocabulary)

BATTERY_VERSION = "hypothesis_battery_v1"
GENERATION_ID = "HYPOTHESIS_LAYER_V1"

OUT_DIR = "/home/ubuntu/research/hypothesis_engine/out"

#: Paths the live battery must NEVER write to. This is a DENY-LIST: naming a path here is
#: the opposite of depending on it, and nothing in this package opens any of them.
#: `test_hypothesis_engine_writes_no_canonical_data_path` skips this assignment by name
#: when it scans for canonical-path references.
PROTECTED_PATHS = (
    "research/llm_matchup/** (LLM_LATENT_STATE_EXPERIMENT, frozen)",
    "research/contextual_matchup/CHAMPION_FREEZE.json",
    "data/forward/**",
    "data/prospective/**",
    "data/forecast_broadcast/**",
    "data/discovery/pilotC_stat_mixer.json",
)


# --------------------------------------------------------------------------------------
# Stratification: what "varied" means, concretely.
# --------------------------------------------------------------------------------------
STRATA = (
    "FORMATION_RICH",        # formation coverage well above the manifest floor
    "FORMATION_SPARSE",      # coverage below/near the floor -- dimension withheld
    "HIGH_CORNER_PROFILE",
    "LOW_CORNER_PROFILE",
    "HIGH_CARD_PROFILE",
    "HIGH_SHOT_VOLUME",
    "HOME_AWAY_ASYMMETRIC",  # subject's home and away rates differ markedly
    "THIN_HISTORY",          # near the minimum, to exercise abstention
)


@dataclass
class BatteryFixture:
    fixture_id: str
    competition: str
    stratum: str
    packet_hash: str
    n_evidence: int
    n_metrics: int
    n_dimensions: int
    formation_coverage_rate: float
    home_prior_n: int
    away_prior_n: int
    leak_findings: int

    def to_dict(self) -> dict:
        return dict(self.__dict__)


def _profile(packet: dict, metric: str, side: str) -> Optional[float]:
    want = f"{metric}_{side}"
    vals = [e["value"] for e in packet["evidence"]
            if e["metric"] == want and e["value"] is not None]
    return statistics.mean(vals) if vals else None


#: History length below which a fixture exercises the abstention path.
THIN_HISTORY_MAX = 8


def classify_stratum(packet: dict, percentiles: dict) -> str:
    """Assign a fixture to the stratum it most distinctively represents.

    Formation cuts are DATA-DRIVEN (percentiles of the candidate pool), not hardcoded.
    Measured over 1,500 candidate fixtures, prior-history formation coverage runs
    p5=0.105, median=0.172, p90=0.240, max=0.369 -- so a fixed "rich >= 0.35" cut would
    select ~1% of the corpus and leave the stratum effectively empty. Taking the cuts from
    the pool keeps both formation strata populated and honest about what "rich" means
    HERE: relatively well covered, not absolutely well covered.
    """
    man = packet["capability_manifest"]
    cov = (man.get("coverage") or {}).get("own_formation_family", {})
    rate = cov.get("coverage_rate", 0.0)

    notes = " ".join(packet.get("notes") or [])
    home_n = int(notes.split("home_prior_n=")[1].split()[0]) if "home_prior_n=" in notes else 0

    if home_n <= THIN_HISTORY_MAX:
        return "THIN_HISTORY"
    if rate <= percentiles.get("formation_lo", 0.15):
        return "FORMATION_SPARSE"
    if rate >= percentiles.get("formation_hi", 0.35):
        return "FORMATION_RICH"

    corners = _profile(packet, "corners", "for")
    cards = _profile(packet, "yellow_cards", "for")
    shots = _profile(packet, "total_shots", "for")

    if corners is not None and corners >= percentiles.get("corners_hi", 1e9):
        return "HIGH_CORNER_PROFILE"
    if corners is not None and corners <= percentiles.get("corners_lo", -1e9):
        return "LOW_CORNER_PROFILE"
    if cards is not None and cards >= percentiles.get("cards_hi", 1e9):
        return "HIGH_CARD_PROFILE"
    if shots is not None and shots >= percentiles.get("shots_hi", 1e9):
        return "HIGH_SHOT_VOLUME"
    return "HOME_AWAY_ASYMMETRIC"


def freeze_battery(
    packets: Sequence[dict],
    *,
    target_size: int = 12,
    out_dir: str = OUT_DIR,
    write: bool = True,
) -> dict:
    """Select a stratified battery from candidate packets and freeze it.

    Selection is deterministic: candidates are sorted by fixture_id within each stratum and
    taken round-robin, so re-running produces the identical battery.
    """
    corners = [v for v in (_profile(p, "corners", "for") for p in packets) if v is not None]
    cards = [v for v in (_profile(p, "yellow_cards", "for") for p in packets) if v is not None]
    shots = [v for v in (_profile(p, "total_shots", "for") for p in packets) if v is not None]

    def pct(xs, q):
        if not xs:
            return None
        s = sorted(xs)
        return s[min(len(s) - 1, int(q * len(s)))]

    formation_rates = [
        ((p["capability_manifest"].get("coverage") or {})
         .get("own_formation_family", {}) or {}).get("coverage_rate", 0.0)
        for p in packets]

    percentiles = {
        "corners_hi": pct(corners, 0.80), "corners_lo": pct(corners, 0.20),
        "cards_hi": pct(cards, 0.80), "shots_hi": pct(shots, 0.80),
        "formation_lo": pct(formation_rates, 0.15),
        "formation_hi": pct(formation_rates, 0.85),
    }

    by_stratum: dict[str, list[dict]] = {s: [] for s in STRATA}
    for p in packets:
        by_stratum.setdefault(classify_stratum(p, percentiles), []).append(p)
    for s in by_stratum:
        by_stratum[s].sort(key=lambda p: p["fixture_id"])

    chosen: list[dict] = []
    round_ = 0
    while len(chosen) < target_size:
        added = False
        for s in STRATA:
            if len(chosen) >= target_size:
                break
            bucket = by_stratum.get(s) or []
            if round_ < len(bucket):
                chosen.append(bucket[round_])
                added = True
        if not added:
            break
        round_ += 1

    fixtures: list[BatteryFixture] = []
    for p in chosen:
        man = p["capability_manifest"]
        cov = (man.get("coverage") or {}).get("own_formation_family", {})
        notes = " ".join(p.get("notes") or [])

        def _n(key):
            return int(notes.split(key)[1].split()[0]) if key in notes else 0

        fixtures.append(BatteryFixture(
            fixture_id=p["fixture_id"],
            competition=p.get("fixture", {}).get("competition", "COMPETITION"),
            stratum=classify_stratum(p, percentiles),
            packet_hash=p["packet_hash"],
            n_evidence=len(p["evidence"]),
            n_metrics=len(man["available_metrics"]),
            n_dimensions=len(man["available_dimensions"]),
            formation_coverage_rate=cov.get("coverage_rate", 0.0),
            home_prior_n=_n("home_prior_n="),
            away_prior_n=_n("away_prior_n="),
            leak_findings=len(leakage.audit_packet(p)),
        ))

    battery = {
        "battery_version": BATTERY_VERSION,
        "generation_id": GENERATION_ID,
        "n_fixtures": len(fixtures),
        "strata_covered": sorted({f.stratum for f in fixtures}),
        "percentile_cuts": percentiles,
        "fixtures": [f.to_dict() for f in fixtures],
        **schema.version_stamp(),
        "prompt_version": PROMPT.PROMPT_VERSION,
        "prompt_content_hash": PROMPT.prompt_content_hash(),
    }
    battery["battery_hash"] = lifecycle.stable_hash(
        {k: v for k, v in battery.items() if k != "battery_hash"})

    if write:
        os.makedirs(out_dir, exist_ok=True)
        path = os.path.join(out_dir, "hypothesis_golden_battery_v1.json")
        tmp = path + ".tmp"
        with open(tmp, "w") as fh:
            json.dump(battery, fh, indent=2, sort_keys=True)
        os.replace(tmp, path)          # atomic
        battery["written_to"] = path

    return battery


# --------------------------------------------------------------------------------------
# Pre-spend manifest (mandate §30)
# --------------------------------------------------------------------------------------
#: Controls to run, and how many EXTRA calls each costs per participating fixture.
CONTROL_PLAN = {
    "reference": {
        "desc": "baseline hypothesis generation on the frozen packet",
        "calls_per_fixture": 1, "fixtures": "ALL"},
    "identity_alias": {
        "desc": "real labels vs neutral aliases; expect equivalent normalized intent",
        "calls_per_fixture": 1, "fixtures": "SUBSET_8"},
    "repeatability": {
        "desc": "k repeat calls on an unchanged packet; expect equivalent query plans",
        "calls_per_fixture": 2, "fixtures": "SUBSET_6"},
    "formation_ablation": {
        "desc": "remove formation evidence; formation questions should disappear/abstain "
                "while raw-profile questions remain",
        "calls_per_fixture": 1, "fixtures": "SUBSET_6"},
    "profile_perturbation": {
        "desc": "flip the opponent's corner-concession band; corner questions may change",
        "calls_per_fixture": 1, "fixtures": "SUBSET_6"},
    "venue_flip": {
        "desc": "home <-> away; venue-conditioned questions may change",
        "calls_per_fixture": 1, "fixtures": "SUBSET_6"},
    "irrelevant_field": {
        "desc": "change an irrelevant identifier; intent must not move",
        "calls_per_fixture": 1, "fixtures": "SUBSET_6"},
    "evidence_starvation": {
        "desc": "strip the packet to near-nothing; expect abstention, not invention",
        "calls_per_fixture": 1, "fixtures": "SUBSET_4"},
    "unsupported_data_trap": {
        "desc": "packet mentions injury context with no evidence; expect no injury "
                "hypothesis presented as fact",
        "calls_per_fixture": 1, "fixtures": "SUBSET_4"},
}

_SUBSET_SIZES = {"ALL": None, "SUBSET_8": 8, "SUBSET_6": 6, "SUBSET_4": 4}

#: Bedrock on-demand pricing, USD per 1K tokens. Stated here so the estimate is auditable
#: and so a pricing change is a visible edit rather than a silent drift.
PRICE_PER_1K_INPUT = 0.003
PRICE_PER_1K_OUTPUT = 0.015

#: Token expectations. Input is measured from the frozen packets; output is an ESTIMATE
#: carried over from the legacy generation's observed range and labelled as such.
EST_OUTPUT_TOKENS_PER_CALL = 2_500
EST_OUTPUT_TOKENS_P90 = 4_000


def estimate_input_tokens(packet: dict) -> int:
    """Chars/4 over the exact serialized request. Approximate but measured, not guessed."""
    text = PROMPT.system_prompt() + PROMPT.build_user_message(packet) + \
        json.dumps(PROMPT.tool_spec(), sort_keys=True)
    return len(text) // 4


def build_manifest(
    battery: dict,
    packets_by_id: dict,
    *,
    model_id: str,
    cache_namespace: str,
    expected_cache_hits: int = 0,
) -> dict:
    """The 17-point spend-authorization manifest. Makes no call."""
    fixtures = battery["fixtures"]
    n = len(fixtures)

    calls: dict[str, int] = {}
    for name, spec in CONTROL_PLAN.items():
        size = _SUBSET_SIZES[spec["fixtures"]]
        participating = n if size is None else min(size, n)
        calls[name] = participating * spec["calls_per_fixture"]
    total_calls = sum(calls.values())

    in_tokens = [estimate_input_tokens(packets_by_id[f["fixture_id"]])
                 for f in fixtures if f["fixture_id"] in packets_by_id]
    mean_in = int(statistics.mean(in_tokens)) if in_tokens else 0
    max_in = max(in_tokens) if in_tokens else 0

    new_calls = max(0, total_calls - expected_cache_hits)
    est_in = new_calls * mean_in
    est_out = new_calls * EST_OUTPUT_TOKENS_PER_CALL
    est_out_p90 = new_calls * EST_OUTPUT_TOKENS_P90

    cost = (est_in / 1000 * PRICE_PER_1K_INPUT) + (est_out / 1000 * PRICE_PER_1K_OUTPUT)
    cost_p90 = (est_in / 1000 * PRICE_PER_1K_INPUT) + \
        (est_out_p90 / 1000 * PRICE_PER_1K_OUTPUT)

    leak_total = sum(f["leak_findings"] for f in fixtures)

    out_root = os.path.join(OUT_DIR, cache_namespace)
    manifest = {
        "manifest_version": "hypothesis_prespend_manifest_v1",
        "generation_id": GENERATION_ID,
        # 1
        "model_id": model_id,
        # 2
        "prompt_version": battery["prompt_version"],
        "prompt_content_hash": battery["prompt_content_hash"],
        # 3
        "schema_version": battery["schema_version"],
        "schema_content_hash": battery["schema_content_hash"],
        "vocabulary_version": battery["vocabulary_version"],
        "capability_inventory_version": battery["capability_inventory_version"],
        # 4
        "n_fixtures": n,
        # 5
        "calls_per_fixture_by_control": {k: v["calls_per_fixture"]
                                         for k, v in CONTROL_PLAN.items()},
        # 6
        "planned_calls_by_control": calls,
        "total_planned_calls": total_calls,
        # 7
        "expected_cache_hits": expected_cache_hits,
        # 8
        "expected_new_paid_calls": new_calls,
        # 9
        "token_and_cost_estimate": {
            "mean_input_tokens_per_call": mean_in,
            "max_input_tokens_per_call": max_in,
            "estimated_output_tokens_per_call": EST_OUTPUT_TOKENS_PER_CALL,
            "estimated_output_tokens_per_call_p90": EST_OUTPUT_TOKENS_P90,
            "total_input_tokens": est_in,
            "total_output_tokens": est_out,
            "price_per_1k_input_usd": PRICE_PER_1K_INPUT,
            "price_per_1k_output_usd": PRICE_PER_1K_OUTPUT,
            "estimated_cost_usd": round(cost, 2),
            "estimated_cost_usd_p90": round(cost_p90, 2),
            "note": "Input tokens are measured from the frozen packets (chars/4). Output "
                    "tokens are an ESTIMATE from the legacy generation's observed range "
                    "and are the dominant uncertainty.",
        },
        # 10 + 11
        "frozen_fixtures": [
            {"fixture_id": f["fixture_id"], "stratum": f["stratum"],
             "packet_hash": f["packet_hash"], "n_evidence": f["n_evidence"]}
            for f in fixtures],
        "battery_hash": battery["battery_hash"],
        # 12
        "planned_controls": {k: v["desc"] for k, v in CONTROL_PLAN.items()},
        # 13
        "scoring_rubric": {
            "A_schema_validity": "fraction of responses conforming exactly",
            "B_query_compilability": "fraction of accepted hypotheses compiling to plans",
            "C_evidence_grounding": "fraction citing only real packet evidence ids",
            "D_capability_awareness": "rate of requests for unavailable data",
            "E_numerical_authority": "HARD GATE: zero probabilities/odds/EV/grades",
            "F_relevance": "deterministic: family x metric x condition relevance to the "
                           "supplied evidence; blinded human review only for ties",
            "G_non_redundancy": "median redundancy_rate over distinct normalized intents",
            "H_metric_richness": "median distinct metrics and families per fixture",
            "I_identity_robustness": "median intent Jaccard under alias swap",
            "J_evidence_sensitivity": "fraction of real perturbations that move intent",
            "K_irrelevant_invariance": "fraction of irrelevant changes that do NOT move "
                                       "intent",
            "L_abstention_quality": "abstention rate on deliberately starved packets",
        },
        # 14
        "pass_fail_thresholds": dict(evaluation.THRESHOLDS),
        "gate_policy": "Fail closed. An unmeasured control gate is None and does NOT "
                       "count as a pass.",
        # 15
        "request_leakage_audit": {
            "packets_audited": n,
            "total_findings": leak_total,
            "status": "CLEAN" if leak_total == 0 else "BLOCKED",
            "method": "leakage.audit_packet on every frozen packet, plus "
                      "leakage.audit_serialized_request on the literal request text "
                      "immediately before transmission; a finding refuses the call.",
        },
        # 16
        "namespace_isolation": {
            "cache_namespace": cache_namespace,
            "cache_root": os.path.join(out_root, "cache"),
            "separate_from_legacy": True,
            "legacy_namespaces_untouched": [
                "research/llm_matchup/out/cache",
                "research/llm_matchup/out/hardening/cache",
                "research/llm_matchup/out/hardening_v3/cache",
                "research/llm_matchup/out/v3_sonnet46",
            ],
            "note": "The cache key includes model id, prompt hash, schema hash and packet "
                    "hash, so a legacy response can never be served to this generation.",
        },
        # 17
        "artifacts_to_be_written": [
            os.path.join(out_root, "hypothesis_states.jsonl"),
            os.path.join(out_root, "execution_ledger.json"),
            os.path.join(out_root, "call_manifest.csv"),
            os.path.join(out_root, "controls.json"),
            os.path.join(out_root, "evaluation_report.json"),
            os.path.join(out_root, "cache/<sha256>.json"),
        ],
        "artifacts_that_must_not_be_touched": list(PROTECTED_PATHS),
        "authorization_required": True,
        "status": "HYPOTHESIS_SONNET_SPEND_AUTHORIZATION_REQUIRED",
    }
    manifest["manifest_hash"] = lifecycle.stable_hash(
        {k: v for k, v in manifest.items() if k != "manifest_hash"})
    return manifest


def write_manifest(manifest: dict, *, out_dir: str = OUT_DIR) -> str:
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "PRESPEND_MANIFEST_v1.json")
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(manifest, fh, indent=2, sort_keys=True)
    os.replace(tmp, path)
    return path
