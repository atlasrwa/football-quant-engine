"""Deterministic hardened validator (validator_v3) — patch §11-§16, §43, §44.

FAIL-CLOSED, like the frozen validator: any violation => ValidationError (the caller maps
it to LLM_OUTPUT_REJECTED). No partial salvage. This validator is STRICTLY STRONGER than
the frozen one — it re-runs every frozen check and adds the hardening constraints. It never
weakens a frozen rule (patch §43, §44).

It cannot simply call `validator.validate` because that function validates against the
frozen schema (which forbids the new `counter_evidence_search` field via
additionalProperties=false). Instead it:

  1. schema-checks against the V3 schema (closed objects, enums, the new required field);
  2. reuses the frozen per-state evidence/allow-list/PIT/orientation checks
     (`validator._check_state`) verbatim — these are the leakage-critical rules;
  3. reuses the frozen fixture/cutoff/context-honesty/banned-key/version checks;
  4. adds the NEW hardening rules:
       (§12) counter_evidence_search must be PERFORMED unless the assessment is UNKNOWN
             (then SKIPPED is allowed); empty counter_evidence_ids is valid ONLY when
             search == PERFORMED.
       (§16) counter-evidence is held to the SAME standards as support: every counter id
             must be a real packet id, PIT_SAFE, and on the mechanism allow-list (same
             normalization as support). (The frozen _check_state already requires counter
             ids to exist in the packet; we additionally require PIT_SAFE + allow-list.)
       (§15) strong UNRESOLVED counter-evidence CONSTRAINS the state: an assessment may not
             be an extreme one-sided SUPPORTED state (VERY_HIGH / STRONG_*_ADVANTAGE) while
             citing strong reliable counter-evidence unless it is downgraded to CONFLICTED.
"""
from __future__ import annotations

from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup.validator import (
    ValidationError, REJECTED, _check_state, _evidence_index,
)
from src.research.llm_matchup.hardening import schema_v3 as SCH3

# --- counter-evidence strength policy (deterministic, patch §15, §16) -----------
# A counter-evidence item is "STRONG" when it is reliable and not a tiny sample. This is the
# symmetric analogue of how support is weighted: reliability HIGH, or reliability MEDIUM with
# a non-trivial sample. Weak counter-evidence (LOW reliability / tiny n) never cancels
# support (patch §16) and never triggers the constraint.
STRONG_COUNTER_MIN_N = 6

# Extreme one-sided SUPPORTED states that strong unresolved counter-evidence must block
# (patch §15). CONFLICTED / UNKNOWN / NEUTRAL are already "resolved as uncertain" and are
# therefore always allowed.
EXTREME_SUPPORTED_LEVELS = {"VERY_HIGH", "STRONG_A_ADVANTAGE", "STRONG_B_ADVANTAGE"}


def _schema_check_v3(obj: dict):
    """Closed-world schema check against the V3 schema, reusing the frozen recursive walker
    so the additionalProperties=false guarantee is identical."""
    from src.research.llm_matchup.validator import _walk_closed, _HAVE_JSONSCHEMA
    schema = SCH3.build_schema()
    if _HAVE_JSONSCHEMA:
        import jsonschema
        try:
            jsonschema.validate(obj, schema)
        except jsonschema.ValidationError as e:
            raise ValidationError("/".join(str(p) for p in e.absolute_path) or "<root>", e.message)
        return
    _walk_closed(obj, schema, "<root>")


def _is_strong_counter(ev: dict) -> bool:
    """Deterministic 'strong counter-evidence' test (patch §15, §16). Symmetric with support:
    reliability HIGH, or MEDIUM with a non-trivial sample."""
    rel = (ev.get("reliability") or "").upper()
    n = ev.get("sample_n") or 0
    if rel == "HIGH":
        return True
    if rel == "MEDIUM" and n >= STRONG_COUNTER_MIN_N:
        return True
    return False


def _check_counter_evidence(item: dict, ev_index: dict, mech: str, path: str):
    """New hardening constraints on counter-evidence (patch §12, §15, §16)."""
    search = item.get("counter_evidence_search")
    counter = list(item.get("counter_evidence_ids", []))
    lvl = item.get("level") or item.get("assessment")

    # §12: search bookkeeping. SKIPPED only legitimate for UNKNOWN assessments.
    if search not in SCH3.COUNTER_EVIDENCE_SEARCH:
        raise ValidationError(f"{path}/counter_evidence_search", "missing/invalid enum")
    if search == "SKIPPED" and lvl != "UNKNOWN":
        raise ValidationError(f"{path}/counter_evidence_search",
                              "SKIPPED only allowed when assessment is UNKNOWN")
    # §12: empty counter list valid ONLY after a performed search. (Trivially: if SKIPPED,
    # the list must be empty too — you cannot cite counter-evidence you never searched for.)
    if search == "SKIPPED" and counter:
        raise ValidationError(f"{path}/counter_evidence_ids",
                              "counter ids present but counter_evidence_search=SKIPPED")

    # §16: counter-evidence held to the SAME standards as support — PIT_SAFE + allow-list.
    # (Existence in packet is already enforced by the frozen _check_state.)
    allow = ONT.allowed_metric_prefixes(mech)
    for eid in counter:
        ev = ev_index.get(eid)
        if ev is None:
            # frozen _check_state already raises for this; belt & braces.
            raise ValidationError(f"{path}/counter_evidence_ids", f"cited id not in packet: {eid}")
        if ev.get("temporal_status") != "PIT_SAFE":
            raise ValidationError(f"{path}/counter_evidence_ids",
                                  f"counter-evidence not PIT_SAFE: {eid}")
        if not _metric_on_allow_list(ev["metric"], allow):
            raise ValidationError(f"{path}/counter_evidence_ids",
                                  f"counter-evidence {ev['metric']} not permitted for {mech}")

    # §15: strong unresolved counter-evidence must CONSTRAIN the state. An extreme one-sided
    # SUPPORTED level cannot coexist with strong reliable counter-evidence — the model must
    # either downgrade the level or set CONFLICTED.
    if lvl in EXTREME_SUPPORTED_LEVELS:
        strong = [eid for eid in counter if _is_strong_counter(ev_index[eid])]
        if strong:
            raise ValidationError(
                f"{path}/level",
                f"extreme SUPPORTED state {lvl} with strong unresolved counter-evidence "
                f"{strong}; must downgrade or set CONFLICTED (patch §15)")


def _metric_on_allow_list(metric: str, allow: list[str]) -> bool:
    """Same normalization the frozen _check_state uses for support, applied to counter ids so
    the standard is symmetric (patch §16). Formation-prefix stripping + against/allowed
    equivalence + base-name matching."""
    if any(metric == a or metric.startswith(a) or a in metric for a in allow):
        return True
    core = metric
    for pfx in ("formation_delta_", "fmx_", "fc_"):
        if core.startswith(pfx):
            core = core[len(pfx):]
            break
    is_against = core.endswith("_against")
    base = core.replace("_for", "").replace("_against", "").replace("_2h_shift", "") \
               .replace("league_", "").replace("_env", "")
    allow_bases = set()
    for p in allow:
        allow_bases.add(p)
        allow_bases.add(p.replace("_allowed", "").replace("_against", ""))
    matched = any(base.startswith(p) or p.startswith(base) or p in core for p in allow)
    if not matched and is_against:
        matched = any(base.startswith(ab) or ab.startswith(base) for ab in allow_bases)
    return matched


def validate_v3(obj: dict, packet: dict, version_stamp: dict) -> dict:
    """Return the object if valid; raise ValidationError otherwise. STRICTLY STRONGER than
    the frozen validator (patch §43, §44)."""
    # 1. V3 closed-world schema check (adds counter_evidence_search).
    _schema_check_v3(obj)

    # 2-3. Frozen leakage-critical checks: fixture/cutoff, context honesty, per-state
    #      evidence existence/allow-list/PIT/orientation/UNKNOWN, banned keys, version stamps.
    #      We inline the frozen orchestration (it lives in validator.validate but that also
    #      re-runs the FROZEN schema which forbids the new field). We call its building blocks
    #      directly so every frozen rule is preserved verbatim.
    if str(obj["fixture_id"]) != str(packet["fixture"]["fixture_id"]):
        raise ValidationError("fixture_id", "does not match packet")
    if int(obj["information_cutoff_unix"]) != int(packet["information_cutoff_unix"]):
        raise ValidationError("information_cutoff_unix", "does not match packet cutoff")

    us = packet.get("unsupported_context", {})
    cf = obj["context_flags"]
    fc = packet.get("formation_context", {})
    if not fc and us.get("formation_status") == "FORMATION_UNKNOWN" \
            and cf.get("formation_status") != "FORMATION_UNKNOWN":
        raise ValidationError("context_flags/formation_status", "must be FORMATION_UNKNOWN per packet")
    if us.get("injury_status") == "INJURY_STATUS_UNKNOWN" and cf.get("injury_status") != "INJURY_STATUS_UNKNOWN":
        raise ValidationError("context_flags/injury_status", "must be INJURY_STATUS_UNKNOWN per packet")
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
        _check_counter_evidence(it, ev_index, it["mechanism"], f"team_a_states[{i}]")
    for i, it in enumerate(obj["team_b_states"]):
        _check_state(it, ev_index, "B", f"team_b_states[{i}]")
        _check_counter_evidence(it, ev_index, it["mechanism"], f"team_b_states[{i}]")
    for i, it in enumerate(obj["matchup_states"]):
        _check_state(it, ev_index, "M", f"matchup_states[{i}]")
        _check_counter_evidence(it, ev_index, it["mechanism"], f"matchup_states[{i}]")

    # banned probability/betting keys anywhere (frozen rule, re-run).
    banned = {"probability", "prob", "p_over", "odds", "prediction", "recommended_bet",
              # patch §47: also forbid hidden-reasoning fields if a model tries to smuggle them.
              "reasoning_trace", "analysis_notes", "thinking", "chain_of_thought"}

    def _scan(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in banned:
                    raise ValidationError(f"{path}/{k}", "forbidden probability/reasoning content")
                _scan(v, f"{path}/{k}")
        elif isinstance(o, list):
            for j, v in enumerate(o):
                _scan(v, f"{path}[{j}]")

    _scan(obj)

    for vk in ("ontology_version", "schema_version", "prompt_version"):
        if vk not in version_stamp:
            raise ValidationError(vk, "missing version stamp")
    return obj
