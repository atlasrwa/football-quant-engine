"""Immutable read-only prospective evidence warehouse for QFE V2.

The warehouse snapshots already-running external experiments. It does not train
QFE V2 and does not modify the source runtimes. Every normalized declaration is
bound to source event hashes, freeze hashes and source-file fingerprints.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from math import log
from pathlib import Path
from typing import Any, Literal

from src.research.dataset.manifest import canonical_json, sha256_json

SNAPSHOT_VERSION = "qfe-prospective-evidence-snapshot-v1"
SourceKind = Literal["SINGLE", "PAIRED", "TEAM_CORNERS"]


@dataclass(frozen=True, slots=True)
class ExperimentSourceSpec:
    experiment_id: str
    kind: SourceKind
    data_root: Path
    runtime_root: Path
    logical_source_id: str
    model_freeze_relpath: str
    spec_relpath: str


@dataclass(frozen=True, slots=True)
class SourceFingerprint:
    logical_path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]: return asdict(self)


@dataclass(frozen=True, slots=True)
class NormalizedDeclaration:
    record_id: str
    experiment_id: str
    arm: str | None
    source_event_hash: str
    settlement_event_hash: str | None
    fixture_id: str
    fixture: str | None
    kickoff_utc: str | None
    family: str
    role: str | None
    line: float
    side: str
    bookmaker: str | None
    provider: str | None
    model_version: str | None
    freeze_hash: str
    declared_at_utc: str
    entry_market_observed_at_utc: str | None
    p_model: float
    p_market: float
    disagreement: float
    price_decimal: float
    raw_break_even: float
    settlement_status: str
    settled_value: float | None
    selection_result: str | None
    outcome_selected_wins: bool | None
    brier: float | None
    log_loss: float | None
    unit_pnl: float | None
    clv_status: str | None
    closing_market_p: float | None
    movement_toward_selection: float | None
    market_snapshots: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        d=asdict(self)
        d["market_snapshots"]=[dict(x) for x in self.market_snapshots]
        return d


@dataclass(frozen=True, slots=True)
class ExperimentAudit:
    experiment_id: str
    logical_source_id: str
    kind: str
    ledger_events: int
    market_observations: int
    declarations: int
    normalized_records: int
    settled_records: int
    chain_head: str
    ledger_chain_valid: bool
    market_hashes_valid: bool
    state_head_matches: bool
    source_files: tuple[SourceFingerprint, ...]
    source_bundle_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            **{k:v for k,v in asdict(self).items() if k!="source_files"},
            "source_files":[x.to_dict() for x in self.source_files],
        }


@dataclass(frozen=True, slots=True)
class ProspectiveEvidenceSnapshot:
    version: str
    frozen_on: str
    scientific_status: str
    experiments: tuple[ExperimentAudit, ...]
    declarations: tuple[NormalizedDeclaration, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "version":self.version,
            "frozen_on":self.frozen_on,
            "scientific_status":self.scientific_status,
            "experiments":[x.to_dict() for x in self.experiments],
            "declarations":[x.to_dict() for x in self.declarations],
        }

    @property
    def snapshot_hash(self) -> str: return sha256_json(self.to_dict())


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text().splitlines() if x.strip()]


def _hash_event(row: dict[str, Any]) -> str:
    body={k:v for k,v in row.items() if k!="event_hash"}
    raw=json.dumps(body,sort_keys=True,separators=(",",":"),default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def _hash_market(row: dict[str, Any]) -> str:
    body={k:v for k,v in row.items() if k!="market_observation_hash"}
    raw=json.dumps(body,sort_keys=True,separators=(",",":"),default=str).encode()
    return hashlib.sha256(raw).hexdigest()


def verify_event_chain(rows: list[dict[str, Any]], state_head: str | None=None) -> str:
    prev=""
    for i,row in enumerate(rows):
        if row.get("prev_hash")!=prev:
            raise ValueError(f"broken prev_hash at event {i}")
        if row.get("event_hash")!=_hash_event(row):
            raise ValueError(f"broken event_hash at event {i}")
        prev=str(row["event_hash"])
    if state_head is not None and state_head!=prev:
        raise ValueError("state chain_head does not match ledger head")
    return prev


def verify_market_hashes(rows: list[dict[str, Any]]) -> None:
    for i,row in enumerate(rows):
        if row.get("market_observation_hash")!=_hash_market(row):
            raise ValueError(f"broken market_observation_hash at row {i}")


def _fingerprint(path: Path, logical_path: str) -> SourceFingerprint:
    payload=path.read_bytes()
    return SourceFingerprint(logical_path,hashlib.sha256(payload).hexdigest(),len(payload))


def _source_files(spec: ExperimentSourceSpec) -> tuple[SourceFingerprint,...]:
    files=[]
    for name in ("ledger.jsonl","market_observations.jsonl","fixtures.jsonl","state.json"):
        p=spec.data_root/name
        if p.exists(): files.append(_fingerprint(p,f"{spec.logical_source_id}/{name}"))
    freeze_root=spec.data_root/"prediction_freezes"
    if freeze_root.exists():
        for p in sorted(freeze_root.glob("*/*.json")):
            files.append(_fingerprint(p,f"{spec.logical_source_id}/prediction_freezes/{p.parent.name}/{p.name}"))
    for rel in (spec.model_freeze_relpath,spec.spec_relpath):
        p=spec.runtime_root/rel
        if p.exists(): files.append(_fingerprint(p,f"{spec.logical_source_id}/runtime/{rel}"))
    return tuple(files)


def _selection_result(side: str, line: float, value: float) -> str:
    if abs(line*2-round(line*2))>1e-9 or float(line).is_integer():
        raise ValueError(f"snapshot v1 supports half-line binary declarations only: {line}")
    if side=="OVER": return "WIN" if value>line else "LOSS"
    if side=="UNDER": return "WIN" if value<line else "LOSS"
    raise ValueError(f"unsupported side {side}")


def _proper_scores(p: float, result: str) -> tuple[bool,float,float]:
    y=result=="WIN"; q=min(max(float(p),1e-12),1-1e-12)
    return y,(q-float(y))**2,-log(q if y else 1-q)


def _unit_pnl(price: float, result: str) -> float:
    return float(price-1.0 if result=="WIN" else -1.0)


def _freeze_payload(spec: ExperimentSourceSpec, fixture_id: str) -> dict[str, Any] | None:
    root=spec.data_root/"prediction_freezes"/fixture_id
    if not root.exists(): return None
    files=sorted(root.glob("*.json"))
    return json.loads(files[0].read_text()) if files else None


def _model_version_from_freeze(spec: ExperimentSourceSpec, fixture_id: str, family: str, arm: str | None) -> str | None:
    f=_freeze_payload(spec,fixture_id)
    if not f: return None
    if spec.kind=="PAIRED" and arm:
        node=(f.get(arm) or {}).get(family) or {}
        return node.get("version")
    if spec.kind=="TEAM_CORNERS":
        sides=f.get("sides") or {}
        # version is generally repeated on side distributions; declaration itself is authoritative when present.
        for node in sides.values():
            if isinstance(node,dict) and node.get("model_version"): return node.get("model_version")
    node=f.get(family) or {}
    return node.get("version") if isinstance(node,dict) else None


def _market_history_single(markets, declaration):
    out=[]; fam=declaration["family"]; line=float(declaration["line"]); side=declaration["side"]
    for row in markets:
        if row.get("fixture_id")!=declaration["fixture_id"]: continue
        for c in row.get("comparisons",[]):
            if c.get("market_family")!=fam or float(c.get("line",-999))!=line: continue
            p=float(c["p_market_novig_selected"])
            comp_side=str(c["side"])
            if comp_side!=side: p=1.0-p
            out.append({"vintage":row.get("vintage"),"observed_at_utc":row.get("observed_at_utc"),"market_observation_hash":row.get("market_observation_hash"),"p_market_declared_side":p,"odds_payload_hash":row.get("odds_payload_hash")})
    return tuple(sorted(out,key=lambda x:str(x.get("observed_at_utc") or "")))


def _market_history_paired(markets,declaration,arm):
    out=[]; fam=declaration["family"]; line=float(declaration["line"]); side=str(declaration[arm]["side"])
    for row in markets:
        if row.get("fixture_id")!=declaration["fixture_id"]: continue
        for c in ((row.get("families") or {}).get(fam) or {}).get(arm,[]):
            if float(c.get("line",-999))!=line: continue
            p=float(c["p_market"])
            if str(c["side"])!=side: p=1.0-p
            out.append({"vintage":row.get("vintage"),"observed_at_utc":row.get("observed_at_utc"),"market_observation_hash":row.get("market_observation_hash"),"p_market_declared_side":p,"odds_payload_hash":row.get("odds_payload_hash")})
    return tuple(sorted(out,key=lambda x:str(x.get("observed_at_utc") or "")))


def _market_history_team(markets,declaration):
    out=[]; role=declaration["role"]; line=float(declaration["line"]); side=declaration["side"]
    for row in markets:
        if row.get("fixture_id")!=declaration["fixture_id"]: continue
        for c in row.get("comparisons",[]):
            if c.get("role")!=role or float(c.get("line",-999))!=line: continue
            p=float(c["market_over"] if side=="OVER" else c["market_under"])
            out.append({"vintage":row.get("vintage"),"observed_at_utc":row.get("observed_at_utc"),"market_observation_hash":row.get("market_observation_hash"),"p_market_declared_side":p,"odds_payload_hash":row.get("odds_payload_hash")})
    return tuple(sorted(out,key=lambda x:str(x.get("observed_at_utc") or "")))


def _normalize_one(spec, declaration, settlement, markets, *, arm=None) -> NormalizedDeclaration:
    if spec.kind=="PAIRED":
        node=declaration[arm]
        side=str(node["side"]); p_model=float(node["p_model"]); p_market=float(node["p_market"]); delta=float(node["delta"]); price=float(node["price"]); raw=float(node["raw_break_even"])
        freeze_hash=str(declaration["pair_freeze_hash"]); model_version=_model_version_from_freeze(spec,declaration["fixture_id"],declaration["family"],arm)
        history=_market_history_paired(markets,declaration,arm)
        clv=(settlement.get("clv") or {}).get(arm) if settlement else None
    else:
        side=str(declaration["side"]); p_model=float(declaration["p_model"]); p_market=float(declaration["p_market"]); delta=float(declaration["delta"]); price=float(declaration["price_decimal"]); raw=float(declaration["raw_break_even"])
        freeze_hash=str(declaration["freeze_hash"]); model_version=declaration.get("model_version") or _model_version_from_freeze(spec,declaration["fixture_id"],declaration.get("family","corners"),None)
        history=_market_history_team(markets,declaration) if spec.kind=="TEAM_CORNERS" else _market_history_single(markets,declaration)
        clv=settlement.get("clv") if settlement else None
    value=float(settlement["value"]) if settlement and settlement.get("value") is not None else None
    result=None; outcome=None; brier=None; ll=None; pnl=None
    if value is not None:
        result=_selection_result(side,float(declaration["line"]),value)
        if settlement.get("result") is not None and settlement.get("result")!=result:
            raise ValueError(f"source settlement result mismatch {spec.experiment_id} {declaration['fixture_id']}")
        outcome,brier,ll=_proper_scores(p_model,result); pnl=_unit_pnl(price,result)
    clv=clv if isinstance(clv,dict) else {}
    return NormalizedDeclaration(
        record_id=f"{spec.experiment_id}:{declaration['event_hash']}:{arm or 'single'}",
        experiment_id=spec.experiment_id,arm=arm,source_event_hash=declaration["event_hash"],settlement_event_hash=settlement.get("event_hash") if settlement else None,
        fixture_id=declaration["fixture_id"],fixture=declaration.get("fixture"),kickoff_utc=declaration.get("kickoff_utc"),family=declaration.get("family","corners"),role=declaration.get("role"),line=float(declaration["line"]),side=side,
        bookmaker=declaration.get("bookmaker"),provider=declaration.get("provider"),model_version=model_version,freeze_hash=freeze_hash,declared_at_utc=declaration.get("declared_at_utc") or declaration["recorded_at_utc"],entry_market_observed_at_utc=declaration.get("market_observed_at_utc"),
        p_model=p_model,p_market=p_market,disagreement=delta,price_decimal=price,raw_break_even=raw,
        settlement_status="SETTLED" if settlement else "OPEN",settled_value=value,selection_result=result,outcome_selected_wins=outcome,brier=brier,log_loss=ll,unit_pnl=pnl,
        clv_status=clv.get("status"),closing_market_p=clv.get("closing_market_p"),movement_toward_selection=(clv.get("movement_toward_selection") if "movement_toward_selection" in clv else (clv.get("market_move_pp")/100.0 if clv.get("market_move_pp") is not None else None)),market_snapshots=history,
    )


def build_snapshot(specs: tuple[ExperimentSourceSpec,...], *, frozen_on: str) -> ProspectiveEvidenceSnapshot:
    audits=[]; normalized=[]
    for spec in specs:
        source_files_before=_source_files(spec)
        ledger=_read_jsonl(spec.data_root/"ledger.jsonl"); markets=_read_jsonl(spec.data_root/"market_observations.jsonl")
        state=json.loads((spec.data_root/"state.json").read_text())
        head=verify_event_chain(ledger,state.get("chain_head")); verify_market_hashes(markets)
        if spec.kind=="PAIRED": decl_type="PAIRED_DECLARATION"; settle_type="FAMILY_SETTLED"
        elif spec.kind=="TEAM_CORNERS": decl_type="DECLARATION"; settle_type="TEAM_SIDE_SETTLED"
        else: decl_type="DECLARATION"; settle_type="FAMILY_SETTLED"
        declarations=[x for x in ledger if x.get("event_type")==decl_type]; settlements=[x for x in ledger if x.get("event_type")==settle_type]
        for d in declarations:
            if spec.kind=="TEAM_CORNERS": matches=[s for s in settlements if s.get("fixture_id")==d.get("fixture_id") and s.get("role")==d.get("role")]
            else: matches=[s for s in settlements if s.get("fixture_id")==d.get("fixture_id") and s.get("family")==d.get("family")]
            if len(matches)>1: raise ValueError(f"multiple settlements for declaration {d['event_hash']}")
            settlement=matches[0] if matches else None
            if spec.kind=="PAIRED":
                for arm in ("control","challenger"): normalized.append(_normalize_one(spec,d,settlement,markets,arm=arm))
            else: normalized.append(_normalize_one(spec,d,settlement,markets))
        files=_source_files(spec)
        if files != source_files_before:
            raise RuntimeError(f"source bundle changed during snapshot: {spec.experiment_id}")
        bundle_hash=sha256_json([x.to_dict() for x in files])
        audits.append(ExperimentAudit(spec.experiment_id,spec.logical_source_id,spec.kind,len(ledger),len(markets),len(declarations),sum(1 for x in normalized if x.experiment_id==spec.experiment_id),sum(1 for x in normalized if x.experiment_id==spec.experiment_id and x.settlement_status=="SETTLED"),head,True,True,True,files,bundle_hash))
    normalized=sorted(normalized,key=lambda x:(x.declared_at_utc,x.experiment_id,x.record_id))
    return ProspectiveEvidenceSnapshot(SNAPSHOT_VERSION,frozen_on,"EXTERNAL_PROSPECTIVE_EVIDENCE_ONLY_NOT_V2_TRAINING_DATA",tuple(audits),tuple(normalized))


def render_snapshot_markdown(snapshot: ProspectiveEvidenceSnapshot) -> str:
    lines=["# QFE V2 — Prospective Experiment Evidence Snapshot","",f"Frozen on: {snapshot.frozen_on}",f"Snapshot hash: `{snapshot.snapshot_hash}`","","> External/prospective evidence only. This snapshot is not V2 training data.",""]
    for a in snapshot.experiments:
        lines += [f"## {a.experiment_id}","",f"- Source: `{a.logical_source_id}`",f"- Ledger events: **{a.ledger_events}**",f"- Market observations: **{a.market_observations}**",f"- Normalized declaration-arm records: **{a.normalized_records}**",f"- Settled normalized records: **{a.settled_records}**",f"- Source bundle hash: `{a.source_bundle_hash}`",""]
    settled=[x for x in snapshot.declarations if x.settlement_status=="SETTLED"]
    lines += ["## Snapshot totals","",f"- Declaration-arm records: **{len(snapshot.declarations)}**",f"- Settled: **{len(settled)}**",f"- Open: **{len(snapshot.declarations)-len(settled)}**",""]
    return "\n".join(lines)


def write_snapshot(json_path: Path, markdown_path: Path, jsonl_path: Path, snapshot: ProspectiveEvidenceSnapshot) -> None:
    payloads=((Path(json_path),canonical_json(snapshot.to_dict())+'\n'),(Path(markdown_path),render_snapshot_markdown(snapshot)),(Path(jsonl_path),''.join(canonical_json(x.to_dict())+'\n' for x in snapshot.declarations)))
    for path,payload in payloads:
        if path.exists():
            if path.read_text()!=payload: raise FileExistsError(f"prospective evidence artifact differs: {path}")
            continue
        path.parent.mkdir(parents=True,exist_ok=True); path.write_text(payload)
