"""Deterministic LLM-output validator (brief §30).

Any failure => LLM_OUTPUT_REJECTED with the offending field path(s). No partial salvage.
This is a *programmatic* provenance/temporal/ontology gate; it does not trust the LLM.

Checks:
 1. JSON schema validity (structure, enums, additionalProperties=false)
 2. every cited evidence_id exists in the packet
 3. cited evidence is ALLOWED for the mechanism (ontology.allow prefixes)
 4. every cited evidence item is temporal_status == PIT_SAFE (no future/unavailable)
 5. fixture id + cutoff match the packet
 6. context_flags honesty: formation/injury must be UNKNOWN when packet says so
 7. UNKNOWN rules: a state with zero PIT-safe evidence must be UNKNOWN/low-confidence
 8. no probability-like content (schema already forbids; belt & braces on keys)
 9. version stamps present
"""
from __future__ import annotations
from typing import Optional

try:
    import jsonschema  # optional; we fall back to a hand validator if absent
    _HAVE_JSONSCHEMA = True
except Exception:
    _HAVE_JSONSCHEMA = False

from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup import schema as SCH
from src.research.llm_matchup.evidence import valid_evidence_ids


class ValidationError(Exception):
    def __init__(self, field_path: str, reason: str):
        super().__init__(f"{field_path}: {reason}")
        self.field_path = field_path
        self.reason = reason


REJECTED = "LLM_OUTPUT_REJECTED"


def _walk_closed(obj, sch, path):
    """Recursive schema check enforcing type, enum, required, and additionalProperties=false."""
    t = sch.get("type")
    if t == "object":
        if not isinstance(obj, dict):
            raise ValidationError(path, "expected object")
        props = sch.get("properties", {})
        if sch.get("additionalProperties") is False:
            for k in obj:
                if k not in props:
                    raise ValidationError(f"{path}/{k}", "unexpected field (additionalProperties=false)")
        for req in sch.get("required", []):
            if req not in obj:
                raise ValidationError(f"{path}/{req}", "missing required field")
        for k, v in obj.items():
            if k in props:
                _walk_closed(v, props[k], f"{path}/{k}")
    elif t == "array":
        if not isinstance(obj, list):
            raise ValidationError(path, "expected array")
        mn = sch.get("minItems")
        if mn is not None and len(obj) < mn:
            raise ValidationError(path, f"minItems {mn}")
        item_sch = sch.get("items")
        if item_sch:
            for j, v in enumerate(obj):
                _walk_closed(v, item_sch, f"{path}[{j}]")
    elif t == "string":
        if not isinstance(obj, str):
            raise ValidationError(path, "expected string")
        if "enum" in sch and obj not in sch["enum"]:
            raise ValidationError(path, f"invalid enum value {obj!r}")
    elif t == "integer":
        if not isinstance(obj, int) or isinstance(obj, bool):
            raise ValidationError(path, "expected integer")


def _schema_check(obj: dict):
    schema = SCH.build_schema()
    if _HAVE_JSONSCHEMA:
        try:
            jsonschema.validate(obj, schema)
        except jsonschema.ValidationError as e:
            raise ValidationError("/".join(str(p) for p in e.absolute_path) or "<root>", e.message)
        return
    # Hand validation when jsonschema unavailable. Enforces additionalProperties=false
    # (brief §22) recursively so the closed-world guarantee does not depend on an
    # optional package.
    _walk_closed(obj, schema, "<root>")


def _evidence_index(packet: dict) -> dict:
    return {e["id"]: e for e in packet["evidence"]}


def _check_state(item, ev_index, side_label, path):
    mech = item.get("mechanism")
    if mech not in ONT.MECHANISMS:
        raise ValidationError(f"{path}/mechanism", f"unknown mechanism {mech}")
    allow = ONT.allowed_metric_prefixes(mech)
    cited = list(item.get("evidence_ids", [])) + list(item.get("supporting_evidence_ids", []))
    counter = list(item.get("counter_evidence_ids", []))
    pit_safe_cited = 0
    for eid in cited + counter:
        if eid not in ev_index:
            raise ValidationError(f"{path}/evidence_ids", f"cited id not in packet: {eid}")
    for eid in cited:
        ev = ev_index[eid]
        if ev["temporal_status"] != "PIT_SAFE":
            raise ValidationError(f"{path}/evidence_ids", f"cited non-PIT-safe evidence: {eid}")
        metric = ev["metric"]
        # Direct allow-list hit (covers formation mechanisms that explicitly list fc_/fmx_/
        # formation_delta prefixes).
        if any(metric == a or metric.startswith(a) or a in metric for a in allow):
            pit_safe_cited += 1
            continue
        # Otherwise normalize: strip the formation-conditioning prefix so a formation
        # metric is validated against the SAME allow-list as its underlying base metric
        # (e.g. fmx_crosses_against -> crosses_against -> CROSS_ALLOWANCE), then apply the
        # Phase-A base-name matching. This keeps FOR/AGAINST orientation intact.
        core = metric
        for pfx in ("formation_delta_", "fmx_", "fc_"):
            if core.startswith(pfx):
                core = core[len(pfx):]
                break
        # The packet uses the `_against` suffix for conceded metrics while some defensive
        # allow-lists use the `_allowed` vocabulary. Treat them as equivalent so a conceded
        # metric can be cited for a suppression/allowance mechanism (orientation preserved:
        # it is still a defensive/against metric).
        is_against = core.endswith("_against")
        base = core.replace("_for", "").replace("_against", "").replace("_2h_shift", "")\
                   .replace("league_", "").replace("_env", "")
        allow_bases = set()
        for p in allow:
            allow_bases.add(p)
            allow_bases.add(p.replace("_allowed", "").replace("_against", ""))
        matched = any(base.startswith(p) or p.startswith(base) or p in core for p in allow)
        if not matched and is_against:
            matched = any(base.startswith(ab) or ab.startswith(base) for ab in allow_bases)
        if not matched:
            raise ValidationError(f"{path}/evidence_ids",
                                  f"evidence {metric} not permitted for {mech} (allow={allow})")
        pit_safe_cited += 1
    # UNKNOWN rule: no supporting PIT-safe evidence => must be UNKNOWN + low-ish confidence
    lvl = item.get("level") or item.get("assessment")
    if pit_safe_cited == 0 and lvl not in ("UNKNOWN", "CONFLICTED", "NEUTRAL"):
        raise ValidationError(f"{path}/level", "non-UNKNOWN state with zero PIT-safe evidence")
    if item.get("confidence") not in ONT.CONFIDENCE:
        raise ValidationError(f"{path}/confidence", "invalid confidence enum")


def validate(obj: dict, packet: dict, version_stamp: dict) -> dict:
    """Return the object if valid; raise ValidationError otherwise."""
    _schema_check(obj)

    # 5. fixture id + cutoff
    if str(obj["fixture_id"]) != str(packet["fixture"]["fixture_id"]):
        raise ValidationError("fixture_id", "does not match packet")
    if int(obj["information_cutoff_unix"]) != int(packet["information_cutoff_unix"]):
        raise ValidationError("information_cutoff_unix", "does not match packet cutoff")

    # 6. closed-world honesty on unsupported context
    us = packet.get("unsupported_context", {})
    cf = obj["context_flags"]
    fc = packet.get("formation_context", {})
    # The two-concept formation model (formation_policy_v1) supersedes the legacy single
    # formation_status flag. When the packet carries formation_context, the authoritative
    # honesty check is on prematch_formation_status (below); the legacy flag is only
    # enforced for pure Phase-A packets that lack formation_context.
    if not fc and us.get("formation_status") == "FORMATION_UNKNOWN" \
            and cf.get("formation_status") != "FORMATION_UNKNOWN":
        raise ValidationError("context_flags/formation_status", "must be FORMATION_UNKNOWN per packet")
    if us.get("injury_status") == "INJURY_STATUS_UNKNOWN" and cf.get("injury_status") != "INJURY_STATUS_UNKNOWN":
        raise ValidationError("context_flags/injury_status", "must be INJURY_STATUS_UNKNOWN per packet")

    # 6b. Phase B two-concept formation honesty (formation_policy_v1). The packet declares
    # both the historical RESOLUTION status and the PRE-MATCH status; the output must
    # mirror them exactly when present, so the LLM cannot silently upgrade an UNKNOWN
    # pre-match formation into a known one (the core leakage boundary, brief §2, §3, §43).
    if "resolution_status" in fc and cf.get("formation_resolution_status") is not None \
            and cf.get("formation_resolution_status") != fc["resolution_status"]:
        raise ValidationError("context_flags/formation_resolution_status",
                              f"must be {fc['resolution_status']} per packet")
    if "prematch_status" in fc and cf.get("prematch_formation_status") is not None \
            and cf.get("prematch_formation_status") != fc["prematch_status"]:
        raise ValidationError("context_flags/prematch_formation_status",
                              f"must be {fc['prematch_status']} per packet")

    ev_index = _evidence_index(packet)
    for i, it in enumerate(obj["team_a_states"]):
        _check_state(it, ev_index, "A", f"team_a_states[{i}]")
    for i, it in enumerate(obj["team_b_states"]):
        _check_state(it, ev_index, "B", f"team_b_states[{i}]")
    for i, it in enumerate(obj["matchup_states"]):
        _check_state(it, ev_index, "M", f"matchup_states[{i}]")

    # 8. belt & braces: forbid probability-like leakage keys anywhere
    banned = {"probability", "prob", "p_over", "odds", "prediction", "recommended_bet"}
    def _scan(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in banned:
                    raise ValidationError(f"{path}/{k}", "probability/betting content forbidden")
                _scan(v, f"{path}/{k}")
        elif isinstance(o, list):
            for j, v in enumerate(o):
                _scan(v, f"{path}[{j}]")
    _scan(obj)

    # 9. version stamps must be attached by caller before persist
    for vk in ("ontology_version", "schema_version", "prompt_version"):
        if vk not in version_stamp:
            raise ValidationError(vk, "missing version stamp")
    return obj
