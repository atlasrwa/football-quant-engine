"""Projects the ~1000-fixture V8B.1 Sonnet-arm economics from the attempt-3 canary evidence.

Operational projection only -- NO scientific score, NO target outcome, NO model call. Purely
arithmetic over the 3 attempt-3 per-fixture accounting records.

Caveats baked into the output:
  * n=3 is a tiny sample; p95/max are weak. The projection is a planning estimate, not a
    guarantee. A conservative hard ceiling is provided separately.
  * Only the Sonnet arm spends: control arms R (matched blind) and H (deterministic heuristic)
    make ZERO model calls (controls.py docstring: "ZERO SPEND. No network."). So a ~1000-fixture
    experiment is ~1000 Sonnet calls, not ~3000.
  * Bedrock on-demand Claude Sonnet pricing used: $3.00 / 1M input tokens, $15.00 / 1M output
    tokens (confirmed against multiple 2026 pricing sources; matches adapter_v4.estimate_cost_usd).
    Prompt caching is NOT used by the runner, so no cache-read discount is assumed.
"""
from __future__ import annotations

import json
import statistics

ROOT = "/home/ubuntu"
N_TARGET = 1000

PRICE_INPUT_PER_1K = 0.003
PRICE_OUTPUT_PER_1K = 0.015
PRICE_SOURCE = ("Bedrock on-demand Claude Sonnet: $3/1M input, $15/1M output; verify against the "
                "live AWS Bedrock pricing page and the account's actual tier before spending.")


def _pctl(xs, p):
    xs = sorted(xs)
    if not xs:
        return None
    if len(xs) == 1:
        return xs[0]
    k = (len(xs) - 1) * p
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def build() -> dict:
    res = json.load(open(f"{ROOT}/research/hypothesis_engine/V8B1_CANARY_RESULTS.json"))
    rows = [r["manifest"] for r in res["results"] if r["status"] in ("OK", "OK_ABSTAIN")]
    n = len(rows)

    inp = [m["usage"]["inputTokens"] for m in rows]
    out = [m["usage"]["outputTokens"] for m in rows]
    tot = [m["usage"]["totalTokens"] for m in rows]
    searches = [m["search_calls"] for m in rows]
    converses = [m["converse_calls"] for m in rows]
    lat = [m["latency_s"] for m in rows]

    def dist(xs):
        return {"n": len(xs), "min": min(xs), "p50": _pctl(xs, 0.50),
                "p95": _pctl(xs, 0.95), "max": max(xs), "mean": round(statistics.mean(xs), 1)}

    per_fixture = {
        "input_tokens": dist(inp), "output_tokens": dist(out), "total_tokens": dist(tot),
        "search_calls": dist(searches), "converse_calls": dist(converses),
        "latency_s": dist(lat),
    }

    def cost(i, o):
        return round(i / 1000.0 * PRICE_INPUT_PER_1K + o / 1000.0 * PRICE_OUTPUT_PER_1K, 2)

    # Central estimate uses the observed MEAN per fixture x N.
    mean_in = statistics.mean(inp)
    mean_out = statistics.mean(out)
    est_total_input = int(round(mean_in * N_TARGET))
    est_total_output = int(round(mean_out * N_TARGET))
    est_cost_central = cost(est_total_input, est_total_output)

    # Conservative planning ceiling: use the observed MAX per fixture x N, then a x1.5 safety
    # margin on top for the tiny-sample uncertainty and possible heavier fixtures at scale.
    ceil_in = max(inp) * N_TARGET
    ceil_out = max(out) * N_TARGET
    est_cost_ceiling_raw = cost(ceil_in, ceil_out)
    hard_cost_ceiling = round(est_cost_ceiling_raw * 1.5, 2)

    # Wall clock: serial vs modest parallelism. Latency ~133-145s/fixture observed.
    mean_lat = statistics.mean(lat)
    serial_hours = round(mean_lat * N_TARGET / 3600.0, 1)
    parallel_8_hours = round(mean_lat * N_TARGET / 8 / 3600.0, 1)

    projection = {
        "projection_version": "v8b1_economics_projection_v1",
        "basis": "attempt-3 canary (v2 bounded-search-then-forced-submit), 3 fixtures, all OK",
        "n_calibration_fixtures": n,
        "n_target_fixtures": N_TARGET,
        "SMALL_SAMPLE_CAVEAT": ("n=3 calibration fixtures: p95/max are weak and the true "
                                "per-fixture distribution at 1000 scale is unknown. Treat the "
                                "central estimate as indicative and the hard ceiling as the "
                                "planning bound."),
        "arms_note": ("Only the Sonnet arm spends. Control arms R (matched blind) and H "
                      "(deterministic heuristic) make ZERO model calls, so ~1000 fixtures = "
                      "~1000 Sonnet sessions, not ~3000."),
        "pricing": {"input_per_1k_usd": PRICE_INPUT_PER_1K,
                    "output_per_1k_usd": PRICE_OUTPUT_PER_1K, "source": PRICE_SOURCE,
                    "prompt_caching_used": False},
        "per_fixture_distributions": per_fixture,
        "central_estimate_1000": {
            "method": "mean per-fixture usage x 1000",
            "est_total_input_tokens": est_total_input,
            "est_total_output_tokens": est_total_output,
            "est_cost_usd": est_cost_central,
        },
        "conservative_ceiling_1000": {
            "method": "max observed per-fixture usage x 1000, then x1.5 safety margin",
            "est_total_input_tokens_before_margin": ceil_in,
            "est_total_output_tokens_before_margin": ceil_out,
            "est_cost_usd_before_margin": est_cost_ceiling_raw,
            "hard_cost_ceiling_usd": hard_cost_ceiling,
        },
        "wall_clock": {
            "mean_latency_s_per_fixture": round(mean_lat, 1),
            "serial_hours": serial_hours,
            "parallel_8way_hours": parallel_8_hours,
            "note": "runner is single-call-per-fixture serial internally; parallelism is across "
                    "fixtures. 8-way is illustrative; actual concurrency is bounded by Bedrock "
                    "throughput/quota and any run lock.",
        },
        "attempt2_vs_attempt3": {
            "attempt2_unbounded_input_tokens_3fix": 1309669,
            "attempt3_bounded_input_tokens_3fix": sum(inp),
            "input_token_reduction_factor": round(1309669 / max(sum(inp), 1), 2),
            "attempt2_termination_rate": "1/3 OK (2/3 non-terminating)",
            "attempt3_termination_rate": "3/3 OK deterministic",
        },
        "no_model_call_made_by_this_script": True,
        "no_target_outcome_viewed": True,
        "research_experiment_started": False,
    }
    return projection


if __name__ == "__main__":
    out = build()
    path = f"{ROOT}/research/hypothesis_engine/V8B1_ECONOMICS_PROJECTION.json"
    with open(path, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
    print(f"wrote {path}")
    c = out["central_estimate_1000"]
    h = out["conservative_ceiling_1000"]
    print(f"central 1000-fixture est: {c['est_total_input_tokens']} in / "
          f"{c['est_total_output_tokens']} out -> ${c['est_cost_usd']}")
    print(f"hard cost ceiling: ${h['hard_cost_ceiling_usd']}")
    print(f"wall clock serial {out['wall_clock']['serial_hours']}h / "
          f"8-way {out['wall_clock']['parallel_8way_hours']}h")
