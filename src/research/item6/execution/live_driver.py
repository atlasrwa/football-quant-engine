"""ITEM 6 Stage-1 authentic LIVE execution driver (`item6_stage1_live_driver_v1`).

Closes blocker B1's second half: a committed entrypoint that runs the ALREADY-FROZEN Item 6
Stage-1 experiment against the authentic live Bedrock transport. It wires the real transport
(`live_transport.BedrockStage1Transport`) into the existing frozen `Stage1Runner` -- it does
NOT reimplement the runner, the spend guard, the CountTokens gate, the attempt-marker
discipline, the one-treatment rule or the receipt logic; those are frozen and reused.

FAIL-CLOSED STARTUP PREFLIGHT (refuses to begin, at zero spend, on ANY of):
  * SDK bedrock-runtime lacks Converse or CountTokens;
  * AWS credentials unresolved / region unresolved;
  * model/profile mismatch vs the frozen manifest;
  * run-manifest identity mismatch (self-hash);
  * live-transport source-hash mismatch vs the manifest;
  * live-driver source-hash mismatch vs the manifest;
  * price-table identity mismatch;
  * any scientific artifact hash mismatch (delegates to the frozen runner identity check);
  * CHAMPION mismatch;
  * human monetary ceiling unset / not explicitly authorized at run time;
  * call ledger inconsistent.

NO STAND-IN IN LIVE MODE. `run_live(...)` constructs the transport via
`BedrockStage1Transport.from_frozen_config(...)`; there is no parameter to inject an arbitrary
converse/count callable in LIVE mode. A stand-in transport is a different class path used only
by tests. Re-authorization is required after this amendment: the driver requires an explicit
`authorized_ceiling_usd` argument at call time and NEVER embeds `authorized=true`.

THIS MODULE DOES NOT RUN STAGE 1 ON IMPORT. Importing makes no network call and starts no
run. Executing the 120 treatments requires an explicit human-invoked call to `run_live(...)`
with an authorized ceiling, which is out of scope for the readiness amendment.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, Optional

from src.research.item6.execution import execution_status as ES
from src.research.item6.execution import request_builder as RB
from src.research.item6.execution.live_transport import (
    AWS_REGION, MODEL_ID, MODEL_PROFILE_ID, MODEL_PROVIDER, BedrockStage1Transport,
    LiveTransportRefused, TransportMode, sdk_capability_report)
from src.research.item6.execution.runner import (RunnerConfig, RunnerRefused,
                                                 Stage1Runner, verify_frozen_identities)

LIVE_DRIVER_VERSION = "item6_stage1_live_driver_v1"
ROOT = "/home/ubuntu"

LIVE_TRANSPORT_SRC = "src/research/item6/execution/live_transport.py"
LIVE_DRIVER_SRC = "src/research/item6/execution/live_driver.py"


class LiveDriverRefused(RuntimeError):
    """Raised before any paid call when the fail-closed startup preflight fails."""


def _sha_file(rel: str, root: str = ROOT) -> str:
    with open(f"{root}/{rel}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _canon(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _verify_manifest_self_hash(manifest: Dict[str, Any]) -> bool:
    m = dict(manifest)
    recorded = m.pop("run_manifest_sha256", None)
    if not recorded:
        return False
    return hashlib.sha256(_canon(m)).hexdigest() == recorded


@dataclass
class LivePreflightReport:
    ok: bool
    problems: list
    capability: Dict[str, Any]
    aws_credentials_resolved: bool
    aws_region: Optional[str]
    manifest_self_hash_ok: bool
    transport_hash_ok: bool
    driver_hash_ok: bool
    price_table_ok: bool
    champion_ok: bool
    scientific_ok: bool
    human_ceiling_ok: bool

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__


def preflight(manifest_path: str, *, authorized_ceiling_usd: Optional[float],
              root: str = ROOT, region: str = AWS_REGION) -> LivePreflightReport:
    """Fail-closed startup preflight. Returns a report; raises LiveDriverRefused if not ok.
    Makes no paid call. (Credential resolution and service-model capability are offline.)"""
    problems: list = []
    manifest = json.load(open(f"{root}/{manifest_path}"))

    # 1. SDK capability (from constructed client service model; offline).
    cap = sdk_capability_report(region=region)
    if not cap.has_converse:
        problems.append("SDK bedrock-runtime lacks Converse")
    if not cap.has_count_tokens:
        problems.append("SDK bedrock-runtime lacks CountTokens")

    # 2. credentials + region resolvable (no API call).
    creds_ok = False
    resolved_region = None
    try:
        import boto3
        session = boto3.session.Session()
        creds_ok = session.get_credentials() is not None
        resolved_region = session.region_name or region
    except Exception as e:  # noqa: BLE001
        problems.append(f"AWS session/credential resolution failed: {type(e).__name__}")
    if not creds_ok:
        problems.append("AWS credentials unresolved")
    if not resolved_region:
        problems.append("AWS region unresolved")

    # 3. model/profile match vs manifest.
    if manifest.get("model_profile_id") != MODEL_PROFILE_ID:
        problems.append("model profile mismatch vs manifest")
    if manifest.get("model_id") != MODEL_ID:
        problems.append("model id mismatch vs manifest")
    if manifest.get("model_provider") != MODEL_PROVIDER:
        problems.append("model provider mismatch vs manifest")

    # 4. manifest self-hash.
    manifest_self_ok = _verify_manifest_self_hash(manifest)
    if not manifest_self_ok:
        problems.append("run-manifest self-hash mismatch")

    # 5. live transport + driver source hashes vs manifest.
    transport_hash_ok = _sha_file(LIVE_TRANSPORT_SRC, root) == \
        manifest.get("live_transport_source_sha256")
    driver_hash_ok = _sha_file(LIVE_DRIVER_SRC, root) == \
        manifest.get("live_driver_source_sha256")
    if not transport_hash_ok:
        problems.append("live transport source-hash mismatch vs manifest")
    if not driver_hash_ok:
        problems.append("live driver source-hash mismatch vs manifest")

    # 6. price table identity.
    price_rel = manifest["execution_artifact_paths"]["price_table"]
    price_table_ok = _sha_file(price_rel, root) == \
        manifest["execution_artifact_hashes"]["price_table"]
    if not price_table_ok:
        problems.append("price-table identity mismatch vs manifest")

    # 7. scientific artifacts + cohort + CHAMPION (delegate to frozen runner identity check).
    scientific_ok = True
    champion_ok = True
    try:
        verify_frozen_identities(root)
    except RunnerRefused as e:
        msg = str(e)
        if "CHAMPION" in msg:
            champion_ok = False
        scientific_ok = False
        problems.append(f"frozen-identity check failed: {msg[:200]}")

    # additionally confirm the manifest's recorded scientific hashes match on-disk files.
    for key, rel in manifest["scientific_artifact_paths"].items():
        if _sha_file(rel, root) != manifest["scientific_artifact_hashes"][key]:
            scientific_ok = False
            problems.append(f"scientific artifact drift: {key}")

    # 8. human ceiling must be explicitly authorized at run time (NOT embedded).
    human_ceiling_ok = (isinstance(authorized_ceiling_usd, (int, float))
                        and authorized_ceiling_usd is not None
                        and authorized_ceiling_usd > 0)
    if not human_ceiling_ok:
        problems.append("human monetary ceiling not explicitly authorized at run time")
    else:
        max_reserved = manifest["worst_case_reservation"][
            "max_reserved_stage1_generation_spend_usd"]
        if authorized_ceiling_usd + 1e-9 < max_reserved:
            problems.append(
                f"authorized ceiling {authorized_ceiling_usd} < worst-case reservation "
                f"{max_reserved}; a full run could be blocked mid-way")

    report = LivePreflightReport(
        ok=not problems, problems=problems, capability=cap.to_dict(),
        aws_credentials_resolved=creds_ok, aws_region=resolved_region,
        manifest_self_hash_ok=manifest_self_ok, transport_hash_ok=transport_hash_ok,
        driver_hash_ok=driver_hash_ok, price_table_ok=price_table_ok,
        champion_ok=champion_ok, scientific_ok=scientific_ok,
        human_ceiling_ok=human_ceiling_ok)
    if problems:
        raise LiveDriverRefused("; ".join(problems))
    return report


def build_live_runner(manifest_path: str, *, authorized_ceiling_usd: float,
                      out_dir: str, root: str = ROOT,
                      region: str = AWS_REGION) -> Stage1Runner:
    """Run the fail-closed preflight, then construct a Stage1Runner wired to the AUTHENTIC
    live Bedrock transport. No stand-in path is reachable here. Constructs the transport
    (offline) but transmits nothing until `run_live` iterates fixtures."""
    preflight(manifest_path, authorized_ceiling_usd=authorized_ceiling_usd,
              root=root, region=region)
    manifest = json.load(open(f"{root}/{manifest_path}"))
    transport = BedrockStage1Transport.from_frozen_config(region=region)
    if transport.mode != TransportMode.LIVE_BEDROCK:
        raise LiveDriverRefused("live runner requires a LIVE_BEDROCK transport")
    price_rel = manifest["execution_artifact_paths"]["price_table"]
    cfg = RunnerConfig(
        out_dir=out_dir,
        human_authorized_ceiling_usd=float(authorized_ceiling_usd),
        price_table_path=f"{root}/{price_rel}",
        root=root,
        verify_identities=True,
        count_tokens_fn=transport.count_tokens,
    )
    runner = Stage1Runner(cfg)
    runner._item6_live_transport = transport   # bind for converse + authenticity checks
    return runner


def run_live(manifest_path: str, *, authorized_ceiling_usd: float, out_dir: str,
             root: str = ROOT, region: str = AWS_REGION) -> Dict[str, Any]:
    """Execute the frozen Stage-1 run LIVE. NOT invoked by the readiness amendment or any
    test; requires an explicit human call with an authorized ceiling. Iterates the frozen
    cohort, transmitting at most one authentic Converse treatment per fixture under the
    frozen runner's caps. Returns a reconciliation summary. (Left here as the committed
    entrypoint; the readiness amendment does not call it.)"""
    runner = build_live_runner(manifest_path, authorized_ceiling_usd=authorized_ceiling_usd,
                               out_dir=out_dir, root=root, region=region)
    transport = runner._item6_live_transport
    manifest = json.load(open(f"{root}/{manifest_path}"))
    cohort = json.load(open(f"{root}/{manifest['scientific_artifact_paths']['cohort_manifest']}"))
    results = []
    for fx in cohort["fixtures"]:
        if not runner.guard.call_cap_ok():
            break
        res = runner.run_fixture(fx, transport.converse)
        results.append(res.to_dict())
    return {
        "live_driver_version": LIVE_DRIVER_VERSION,
        "n_fixtures": len(cohort["fixtures"]),
        "results": results,
        "spend_ledger": runner.guard.to_dict(),
        "count_tokens_counters": runner.count_counters.to_dict(),
        "transport": transport.version_stamp(),
    }


def version_stamp() -> Dict[str, Any]:
    return {
        "live_driver_version": LIVE_DRIVER_VERSION,
        "wraps_runner": True,
        "no_standin_in_live_mode": True,
        "requires_explicit_runtime_ceiling": True,
        "embeds_authorized_true": False,
        "fail_closed_preflight": True,
    }
