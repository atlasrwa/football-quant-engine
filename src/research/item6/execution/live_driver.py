"""ITEM 6 Stage-1 authentic LIVE execution driver (`item6_stage1_live_driver_v3`).

Closes blocker B1's second half: a committed entrypoint that runs the ALREADY-FROZEN Item 6
Stage-1 experiment against the authentic live Bedrock transport. It wires the real transport
(`live_transport.BedrockStage1Transport`) into the existing frozen `Stage1Runner` -- it does
NOT reimplement the runner, the spend guard, the CountTokens gate, the attempt-marker
discipline, the one-treatment rule or the receipt logic; those are frozen and reused.

EXACT EXECUTION HEAD IS EXTERNAL (v3). The manifest never self-declares the runtime HEAD:
an artifact committed at a given commit cannot non-circularly name that commit, and V5's
`execution_head_expected` consequently named the PARENT commit (the one WITHOUT the evidence
apparatus). V6+ manifests bind `apparatus_provenance_commit` (historical fact) and declare
`exact_execution_head_source = EXTERNAL_HUMAN_AUTHORIZATION`; the authorizing human supplies
`authorized_execution_head` at call time and this driver verifies it equals the actual git
HEAD BEFORE any CountTokens or Converse call. A recorded apparatus commit can never
substitute for that authorization.

FAIL-CLOSED STARTUP PREFLIGHT (refuses to begin, at zero spend, on ANY of):
  * authorized execution HEAD missing, malformed, or != actual git HEAD;
  * manifest still carrying a self-referential `execution_head_expected` field, or not
    declaring `exact_execution_head_source = EXTERNAL_HUMAN_AUTHORIZATION`;
  * any manifest artifact failing scheme-aware hash verification (unknown scheme included);
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
from src.research.item6.execution import provenance as PROV
from src.research.item6.execution import request_builder as RB
from src.research.item6.evidence.frozen_packet_provider import (
    FrozenPacketError, FrozenPacketProvider)
from src.research.item6.execution.live_transport import (
    AWS_REGION, MODEL_ID, MODEL_PROFILE_ID, MODEL_PROVIDER, BedrockStage1Transport,
    LiveTransportRefused, TransportMode, sdk_capability_report)
from src.research.item6.execution.runner import (RunnerConfig, RunnerRefused,
                                                 Stage1Runner, verify_frozen_identities)

LIVE_DRIVER_VERSION = "item6_stage1_live_driver_v3"
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
    execution_head_policy_ok: bool = False
    authorized_head_ok: bool = False
    actual_git_head: Optional[str] = None
    apparatus_provenance_commit: Optional[str] = None
    artifact_hash_index_ok: Optional[bool] = None

    def to_dict(self) -> Dict[str, Any]:
        return self.__dict__


def preflight(manifest_path: str, *, authorized_ceiling_usd: Optional[float],
              authorized_execution_head: Optional[str] = None,
              root: str = ROOT, region: str = AWS_REGION) -> LivePreflightReport:
    """Fail-closed startup preflight. Returns a report; raises LiveDriverRefused if not ok.
    Makes no paid call. (Credential resolution and service-model capability are offline.)

    `authorized_execution_head` is the EXTERNALLY supplied commit sha the authorizing human
    bound when releasing spend. It defaults to None so that omitting it REFUSES the run
    (fail closed) rather than raising a TypeError; it is never defaulted to a manifest field.
    """
    problems: list = []
    manifest = json.load(open(f"{root}/{manifest_path}"))

    # 0a. execution-head POLICY: the manifest may bind the historical apparatus commit but
    #     must not self-declare the runtime HEAD. Runs before every other check so a policy
    #     violation is refused at zero spend, long before CountTokens.
    execution_head_policy_ok = True
    apparatus_commit = None
    try:
        apparatus_commit, _ = PROV.assert_execution_head_policy(manifest)
    except PROV.ProvenanceError as e:
        execution_head_policy_ok = False
        problems.append(f"execution-head policy: {e}")

    # 0b. the EXACT execution head must come from external human authorization and match the
    #     actual git HEAD. An apparatus provenance commit never substitutes for it.
    actual_head = PROV.resolve_git_head(root)
    authorized_head_ok = True
    try:
        PROV.require_authorized_execution_head(authorized_execution_head, root=root,
                                               actual_head=actual_head)
    except PROV.AuthorizedHeadError as e:
        authorized_head_ok = False
        problems.append(f"authorized execution head: {e}")

    # 0c. scheme-aware artifact verification (V6+ manifests carry an artifact_hash_index;
    #     an unknown hash scheme or any digest mismatch fails closed).
    artifact_index_ok = None
    if "artifact_hash_index" in manifest:
        try:
            report = PROV.verify_manifest_artifacts(manifest, root=root)
            artifact_index_ok = bool(report["ok"])
            if not artifact_index_ok:
                detail = "; ".join(report["problems"][:5]) or (
                    f"{report['n_unknown_hash_schemes']} unknown hash scheme(s)")
                problems.append(f"artifact hash index: {detail}")
        except PROV.ProvenanceError as e:
            artifact_index_ok = False
            problems.append(f"artifact hash index: {e}")

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
        human_ceiling_ok=human_ceiling_ok,
        execution_head_policy_ok=execution_head_policy_ok,
        authorized_head_ok=authorized_head_ok,
        actual_git_head=actual_head,
        apparatus_provenance_commit=apparatus_commit,
        artifact_hash_index_ok=artifact_index_ok)
    if problems:
        raise LiveDriverRefused("; ".join(problems))
    return report


def build_live_runner(manifest_path: str, *, authorized_ceiling_usd: float,
                      authorized_execution_head: Optional[str],
                      out_dir: str, root: str = ROOT,
                      region: str = AWS_REGION) -> Stage1Runner:
    """Run the fail-closed preflight, then construct a Stage1Runner wired to the AUTHENTIC
    live Bedrock transport. No stand-in path is reachable here. Constructs the transport
    (offline) but transmits nothing until `run_live` iterates fixtures. The externally
    authorized execution HEAD is verified inside the preflight, before the transport (and
    therefore before CountTokens) exists."""
    preflight(manifest_path, authorized_ceiling_usd=authorized_ceiling_usd,
              authorized_execution_head=authorized_execution_head,
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


def _load_frozen_packet_provider(manifest: Dict[str, Any], root: str,
                                 data_root: str) -> "FrozenPacketProvider":
    """Load + integrity-check the frozen evidence packet + materialized request sets bound by
    the run manifest. Fail closed on any set-hash mismatch. (V5 manifests bind these; older
    manifests without them cannot drive the populated LIVE path.)"""
    ev = manifest.get("evidence_input")
    if not ev:
        raise LiveDriverRefused(
            "run manifest does not bind an evidence_input block; a populated LIVE run "
            "requires a V5+ manifest that freezes the evidence packet + materialized request "
            "sets (empty-skeleton path is not authorized).")
    provider = FrozenPacketProvider.from_frozen(
        code_root=root, data_root=data_root,
        request_set_rel=ev["materialized_request_set_path"],
        packet_set_rel=ev["evidence_packet_set_path"])
    if provider.materialized_request_set_sha256 != ev["materialized_request_set_sha256"]:
        raise LiveDriverRefused("materialized request set sha mismatch vs manifest")
    if provider.evidence_packet_set_sha256 != ev["evidence_packet_set_sha256"]:
        raise LiveDriverRefused("evidence packet set sha mismatch vs manifest")
    return provider


def run_live(manifest_path: str, *, authorized_ceiling_usd: float,
             authorized_execution_head: Optional[str], out_dir: str,
             root: str = ROOT, region: str = AWS_REGION,
             data_root: Optional[str] = None) -> Dict[str, Any]:
    """Execute the frozen Stage-1 run LIVE with the FROZEN POPULATED evidence packet per
    fixture. NOT invoked by this amendment or any test; requires an explicit human call with
    an authorized ceiling. For each frozen cohort fixture it loads+verifies the frozen
    evidence packet (empty/missing/hash-mismatch => fail closed BEFORE CountTokens and BEFORE
    the attempt marker) and transmits at most one authentic Converse treatment under the
    frozen runner's caps. Returns a reconciliation summary."""
    runner = build_live_runner(manifest_path, authorized_ceiling_usd=authorized_ceiling_usd,
                               authorized_execution_head=authorized_execution_head,
                               out_dir=out_dir, root=root, region=region)
    transport = runner._item6_live_transport
    manifest = json.load(open(f"{root}/{manifest_path}"))
    data_root = data_root or root
    provider = _load_frozen_packet_provider(manifest, root=root, data_root=data_root)
    cohort = json.load(open(f"{root}/{manifest['scientific_artifact_paths']['cohort_manifest']}"))
    results = []
    for fx in cohort["fixtures"]:
        if not runner.guard.call_cap_ok():
            break
        # FAIL CLOSED before any paid work: obtain the verified frozen populated packet.
        packet = provider.get_verified_packet(fx)   # raises FrozenPacketError on any problem
        res = runner.run_fixture(fx, transport.converse, fixture_packet=packet)
        results.append(res.to_dict())
    return {
        "live_driver_version": LIVE_DRIVER_VERSION,
        "authorized_execution_head": authorized_execution_head,
        "apparatus_provenance_commit": manifest.get("apparatus_provenance_commit"),
        "n_fixtures": len(cohort["fixtures"]),
        "results": results,
        "spend_ledger": runner.guard.to_dict(),
        "count_tokens_counters": runner.count_counters.to_dict(),
        "transport": transport.version_stamp(),
        "frozen_packet_provider": provider.version_stamp(),
    }


def version_stamp() -> Dict[str, Any]:
    return {
        "live_driver_version": LIVE_DRIVER_VERSION,
        "wraps_runner": True,
        "no_standin_in_live_mode": True,
        "requires_explicit_runtime_ceiling": True,
        "embeds_authorized_true": False,
        "fail_closed_preflight": True,
        "requires_frozen_populated_evidence_packet": True,
        "live_empty_evidence_packet_allowed": False,
        "live_packet_hash_enforced": True,
        "requires_external_authorized_execution_head": True,
        "exact_execution_head_source": PROV.EXACT_EXECUTION_HEAD_SOURCE,
        "self_referential_execution_head_accepted": False,
        "scheme_aware_artifact_verification": True,
    }
