#!/usr/bin/env python3
"""Zero-API runner for the hierarchical line-set evaluation.

Reads the static corpus and the cache-only expanded-league registry. Makes no API
calls and never edits corpus files. Writes three artifacts:

* ``data/results/hierarchical_line_evaluation.json`` — the full walk-forward report:
  every league x market x line cell, calibration first, the fresh BH family, and
  every insufficient cell with its reason.
* ``data/results/hierarchical_market_coverage.json`` — per-league coverage of every
  family, which is what decides whether the first-half markets are buildable.
* ``data/results/hierarchical_dispersion_audit.json`` — measured variance/mean per
  family, per league and pooled, so the negative-binomial choice is a finding
  rather than an assumption.

Nothing here promotes anything. The report deliberately cannot support a skill
claim: its primary endpoint is a miscalibration test, and every cell carries
``skill_claim_blocked``.

Usage::

    python scripts/hierarchical_forecast_eval.py
    python scripts/hierarchical_forecast_eval.py --families corners goals --leagues 6
    python scripts/hierarchical_forecast_eval.py --coverage-only
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.discovery.corpus import (  # noqa: E402
    CORPUS_MANIFEST_FILE,
    CORPUS_SEASONS,
    load_discovery_set,
    load_heldout_set,
)
from src.research.evaluation.hierarchical_lines import (  # noqa: E402
    HierarchicalEvalConfig,
    HierarchicalLineEvaluator,
)
from src.research.footystats.corpus_expansion import (  # noqa: E402
    DEFAULT_EXPANSION_REGISTRY,
    load_expanded_completed_matches,
    load_expanded_league_names,
)
from src.research.models.hierarchical_market_model import HierarchicalConfig  # noqa: E402
from src.research.models.market_family import (  # noqa: E402
    ALL_FAMILY_NAMES,
    audit_dispersion,
    audit_family_coverage,
    buildable_leagues,
    default_market_families,
    family_by_name,
)
from src.research.models.side_rows import (  # noqa: E402
    assert_no_same_match_leakage,
    build_fixture_rows,
)

RESULTS_DIR = REPO_ROOT / "data" / "results"
REPORT_PATH = RESULTS_DIR / "hierarchical_line_evaluation.json"
COVERAGE_PATH = RESULTS_DIR / "hierarchical_market_coverage.json"
DISPERSION_PATH = RESULTS_DIR / "hierarchical_dispersion_audit.json"


def _sha256(path: Path) -> str | None:
    if not path.exists():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _deduplicate(matches: Sequence[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for match in matches:
        identifier = match.get("id") or match.get("match_id")
        if identifier is not None:
            key = f"id:{identifier}"
        else:
            key = "payload:" + hashlib.sha256(
                json.dumps(match, sort_keys=True, default=str).encode("utf-8")
            ).hexdigest()
        seen.setdefault(key, match)
    return list(seen.values())


def _load_corpus(args: argparse.Namespace) -> tuple[list[dict], dict]:
    discovery = load_discovery_set()
    heldout = [] if args.discovery_only else load_heldout_set()
    expanded: list[dict] = []
    expanded_names: tuple[str, ...] = ()
    registry = Path(args.expanded_registry)
    if not args.no_expanded_registry and registry.exists():
        expanded = load_expanded_completed_matches(registry)
        expanded_names = load_expanded_league_names(registry)

    matches = _deduplicate([*discovery, *heldout, *expanded])
    declared = tuple(dict.fromkeys((*CORPUS_SEASONS, *expanded_names)))

    if args.leagues:
        keep = set(sorted({str(m.get("_league") or "") for m in matches})[: args.leagues])
        matches = [m for m in matches if str(m.get("_league") or "") in keep]
        declared = tuple(name for name in declared if name in keep)

    provenance = {
        "manifest": str(CORPUS_MANIFEST_FILE),
        "manifest_sha256": _sha256(Path(CORPUS_MANIFEST_FILE)),
        "expansion_registry": str(registry),
        "expansion_registry_sha256": _sha256(registry),
        "registered_leagues": list(declared),
        "n_loaded_completed_fixtures": len(matches),
        "discovery_only": args.discovery_only,
        "zero_api": True,
    }
    return matches, provenance


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--families",
        nargs="+",
        default=list(ALL_FAMILY_NAMES),
        choices=list(ALL_FAMILY_NAMES),
        help="market families to evaluate (default: all)",
    )
    parser.add_argument("--leagues", type=int, default=0, help="limit to N leagues")
    parser.add_argument("--discovery-only", action="store_true")
    parser.add_argument("--no-expanded-registry", action="store_true")
    parser.add_argument(
        "--expanded-registry", default=str(DEFAULT_EXPANSION_REGISTRY)
    )
    parser.add_argument("--refit-every", type=int, default=100)
    parser.add_argument("--min-global-train", type=int, default=2000)
    parser.add_argument("--min-cell-predictions", type=int, default=100)
    parser.add_argument("--bootstrap-draws", type=int, default=1000)
    parser.add_argument(
        "--bootstrap-block", default="league_week", choices=("date", "league_week")
    )
    parser.add_argument(
        "--coverage-only",
        action="store_true",
        help="write the coverage and dispersion audits and stop",
    )
    parser.add_argument(
        "--skip-leakage-assertion",
        action="store_true",
        help="skip the independent prior-only re-derivation (slow on the full corpus)",
    )
    args = parser.parse_args(argv)

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    started = time.time()

    print("loading static corpus (zero API calls)...", flush=True)
    matches, corpus_provenance = _load_corpus(args)
    print(
        f"  {corpus_provenance['n_loaded_completed_fixtures']} completed fixtures, "
        f"{len(corpus_provenance['registered_leagues'])} declared leagues",
        flush=True,
    )

    all_families = default_market_families()

    # ── coverage: decides which families are buildable, per league ──────────
    print("auditing per-league family coverage...", flush=True)
    coverage = audit_family_coverage(matches, all_families)
    coverage_payload = {
        "schema_version": "hierarchical-market-coverage/v1",
        "corpus": corpus_provenance,
        "policy": (
            "a family is excluded for a league where the provider does not populate "
            "its target, rather than zero-filled; the -1 sentinel is treated as "
            "missing, never as zero"
        ),
        "half_split_note": (
            "half-split fields were confirmed per-half rather than cumulative in the "
            "schema audit; population rates are measured here per league because they "
            "vary by provider"
        ),
        "families": [
            {
                "name": family.name,
                "requires_half_split": family.requires_half_split,
                "min_coverage": family.min_coverage,
                "lines": list(family.lines),
                "line_rationale": family.line_rationale,
                "buildable_leagues": list(buildable_leagues(coverage, family.name)),
                "excluded_leagues": [
                    report.league
                    for report in coverage
                    if report.family == family.name and not report.buildable
                ],
            }
            for family in all_families
        ],
        "cells": [report.to_dict() for report in coverage],
    }
    COVERAGE_PATH.write_text(json.dumps(coverage_payload, indent=2, sort_keys=True) + "\n")
    print(f"  wrote {COVERAGE_PATH.relative_to(REPO_ROOT)}", flush=True)
    for family in all_families:
        built = buildable_leagues(coverage, family.name)
        total = len({report.league for report in coverage})
        print(f"    {family.name:22s} buildable in {len(built)}/{total} leagues")

    # ── dispersion: verified per family and per league, never assumed ───────
    print("auditing dispersion...", flush=True)
    dispersion = audit_dispersion(matches, all_families)
    dispersion_payload = {
        "schema_version": "hierarchical-dispersion-audit/v1",
        "corpus": corpus_provenance,
        "measured_on": "side counts (one observation per team per fixture)",
        "note": (
            "this is MARGINAL variance/mean. The model selects Poisson versus "
            "negative binomial on RESIDUAL dispersion after conditioning on "
            "features and random effects, which is the correct conditional test; "
            "both ratios are reported in the fit reports of the evaluation report."
        ),
        "cells": [report.to_dict() for report in dispersion],
    }
    DISPERSION_PATH.write_text(
        json.dumps(dispersion_payload, indent=2, sort_keys=True) + "\n"
    )
    print(f"  wrote {DISPERSION_PATH.relative_to(REPO_ROOT)}", flush=True)
    for report in dispersion:
        if report.league == "POOLED":
            verdict = "overdispersed" if report.overdispersed else "≈ Poisson"
            print(
                f"    {report.family:22s} pooled var/mean "
                f"{report.variance_mean_ratio:5.3f}  {verdict}"
            )

    if args.coverage_only:
        print(f"done in {time.time() - started:.1f}s (coverage only)")
        return 0

    # ── build rows and evaluate ─────────────────────────────────────────────
    families = [family_by_name(name) for name in args.families]
    print(f"building strictly-prior side rows for {len(families)} families...", flush=True)
    fixtures = build_fixture_rows(matches, families)
    for family in families:
        print(f"    {family.name:22s} {len(fixtures[family.name])} fixtures")

    if not args.skip_leakage_assertion:
        print("re-deriving every feature from an independent history...", flush=True)
        for family in families:
            assert_no_same_match_leakage(matches, fixtures[family.name], [family])
        print("    no same-match leakage", flush=True)

    config = HierarchicalEvalConfig(
        min_global_train=args.min_global_train,
        refit_every_kickoff_batches=args.refit_every,
        min_cell_predictions=args.min_cell_predictions,
        bootstrap_draws=args.bootstrap_draws,
        bootstrap_block=args.bootstrap_block,
    )
    print("running expanding walk-forward evaluation...", flush=True)
    evaluator = HierarchicalLineEvaluator(config, model_config=HierarchicalConfig())
    report = evaluator.evaluate(
        fixtures,
        families,
        preregistered_leagues=corpus_provenance["registered_leagues"] or None,
    )
    report["corpus"] = corpus_provenance
    report["coverage_artifact"] = str(COVERAGE_PATH.relative_to(REPO_ROOT))
    report["dispersion_artifact"] = str(DISPERSION_PATH.relative_to(REPO_ROOT))
    report["runtime_seconds"] = round(time.time() - started, 1)

    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(f"  wrote {REPORT_PATH.relative_to(REPO_ROOT)}", flush=True)

    _summarise(report)
    print(f"done in {time.time() - started:.1f}s")
    return 0


def _summarise(report: dict) -> None:
    cells = report["cells"]
    tested = [cell for cell in cells if cell["status"] == "tested"]
    insufficient = [cell for cell in cells if cell["status"] == "insufficient"]
    miscalibrated = [cell for cell in tested if cell["fdr"]["reject"]]

    print()
    print("─" * 74)
    print("MONOTONICITY")
    monotonicity = report["monotonicity"]
    print(
        f"  {monotonicity['fixtures_checked']} fixtures checked, "
        f"{monotonicity['violations']} violations"
    )
    print()
    print("FDR FAMILY (fresh, every league x market x line)")
    governance = report["governance"]
    print(f"  preregistered cells : {governance['preregistered_cell_count']}")
    print(f"  valid family size   : {governance['valid_family_size']}")
    print(f"  q                   : {governance['fdr_q']}")
    print(f"  a finding means     : {governance['finding_means']}")
    print(f"  tested              : {len(tested)}")
    print(f"  insufficient        : {len(insufficient)}")
    print(f"  miscalibrated (BH)  : {len(miscalibrated)}")
    print()

    print("CALIBRATION BY FAMILY (median ECE across tested cells)")
    by_family: dict[str, list[float]] = {}
    for cell in tested:
        by_family.setdefault(cell["family"], []).append(cell["calibration"]["ece"])
    for family_name in sorted(by_family):
        values = sorted(by_family[family_name])
        median = values[len(values) // 2]
        flagged = sum(
            1
            for cell in miscalibrated
            if cell["family"] == family_name
        )
        print(
            f"  {family_name:22s} n_cells={len(values):3d}  median ECE={median:.4f}  "
            f"flagged={flagged}"
        )
    print()

    if insufficient:
        reasons: dict[str, int] = {}
        for cell in insufficient:
            for reason in cell["insufficient_reasons"]:
                reasons[reason] = reasons.get(reason, 0) + 1
        print("INSUFFICIENT CELL REASONS")
        for reason, count in sorted(reasons.items(), key=lambda item: -item[1]):
            print(f"  {reason:34s} {count}")
        print()

    btts = report["btts_contrast"]
    print("BTTS: DERIVED FROM THE GOALS FIT vs A DIRECT CLASSIFIER")
    if btts.get("status") == "tested":
        print(
            f"  derived  ECE={btts['derived']['ece']:.4f}  "
            f"Brier={btts['derived']['brier']:.4f}  "
            f"logloss={btts['derived']['log_loss']:.4f}"
        )
        print(
            f"  direct   ECE={btts['direct']['ece']:.4f}  "
            f"Brier={btts['direct']['brier']:.4f}  "
            f"logloss={btts['direct']['log_loss']:.4f}"
        )
        print(
            f"  derived preferred in {btts['leagues_where_derived_preferred_on_log_loss']}"
            f"/{btts['leagues_tested']} leagues on log loss; kept={btts['derived_kept']}"
        )
    else:
        print(f"  {btts.get('reason')}")
    print()
    print("SKILL")
    print(f"  {governance['skill_claims']} — {report['config']['skill_status']}")
    print("─" * 74)


if __name__ == "__main__":
    raise SystemExit(main())
