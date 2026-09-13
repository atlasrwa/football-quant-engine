"""neutralize_for_llm_v2 -- the V3 identity-neutral packet transform (V3 patch SS3-SS23).

V2's `neutralize.py` (hardening/neutralize.py) already replaced real team/competition/season
NAMES with fixture-local neutral tokens (TEAM_A/TEAM_B/COMP_NEUTRAL/SEASON_NEUTRAL) -- that
logic is REUSED here unchanged (SS1: preserve what works). What V2 never did is touch
FORMATION identity: the exact formation string ("4-2-3-1") and the human-readable family
label ("BACK4_1STRIKER") passed straight through V2's "neutral" packet, which is exactly what
the identity controls caught (75% formation-label trip rate, PRE_PHASE_C_HARDENING.md SS10).

This module adds formation neutralization on top of V2's team/competition pass and produces
a distinctly-TYPED packet (`packet_kind = NEUTRALIZED_LLM_EVIDENCE_PACKET`,
`packet_schema_version = neutral_llm_evidence_packet_v1`) so the V4 Bedrock adapter can
structurally refuse anything that isn't this type (SS20-SS23) instead of relying on caller
discipline.

Guarantees (SS20, mirrored from V2's neutralize.py + assert_value_preserving):
  * deterministic, pure, no external calls, no mutation of the source packet;
  * versioned (NEUTRALIZATION_POLICY_VERSION, FORMATION_STRUCTURE_VERSION);
  * every evidence VALUE, sample_n, reliability, temporal_status, cutoff, and the evidence id
    SET are preserved byte-for-byte -- only IDENTIFIER fields are transformed;
  * both `source_evidence_packet_hash` (the original PIT-safe packet) and
    `neutral_llm_packet_hash` (this transform's output) are persisted so any LLM input can be
    traced back to the exact source evidence that produced it (SS21).

Fixture-local team tokens (TEAM_A/TEAM_B, SS6) are inherited from V2. Formation ids
(F_07, FF_03) are DELIBERATELY stable/global, not fixture-local: unlike a specific team, a
formation SHAPE is a small, closed, recurring taxonomy that every fixture in the corpus draws
from (the same role FORMATION_FAMILY_V1.json's family names already play) -- reusing the same
formation_id for the same shape across fixtures carries no team-identity risk and is exactly
what the exact-formation / family CONDITIONING KEY has always been (formation_policy_v1).
"""
from __future__ import annotations
import copy
import hashlib
import json
from typing import Optional

from src.research.llm_matchup.evidence import packet_hash as _source_packet_hash
from src.research.llm_matchup.hardening import neutralize as NZ
from src.research.llm_matchup.hardening import formation_structure as FS
from src.research.llm_matchup.hardening import versions_v3 as V3

PACKET_KIND = "NEUTRALIZED_LLM_EVIDENCE_PACKET"

_FORMATION_SCOPE_KEYS = {
    "prematch_formation": "prematch",
    "team_formation": "team",
    "opp_formation": "opp",
}
_FAMILY_SCOPE_KEYS = {
    "formation_family": "prematch",
    "team_family": "team",
    "opp_family": "opp",
}

_STRUCT_FIELDS = ("back_line_count", "holding_midfield_count", "advanced_midfield_count",
                  "midfield_count", "forward_line_count")


def _neutralize_formation_scope(scope: dict) -> dict:
    """Replace formation-identity scope keys with neutral id + structural attributes.
    Leaves every other key (team/opponent/venue/side/competition/season/tier_summary/...)
    untouched -- those are handled by V2's generic team/competition substitution, and
    tier_summary/evidence_level entries are already tier NAMES (EXACT_FORMATION, FAMILY, ...),
    not formation VALUES, so they carry no identity."""
    if not isinstance(scope, dict):
        return scope
    out = dict(scope)
    for key, prefix in _FORMATION_SCOPE_KEYS.items():
        if key not in out:
            continue
        st = FS.formation_structure(out.pop(key))
        out[f"{prefix}_formation_id"] = st["formation_id"]
        for f in _STRUCT_FIELDS:
            out[f"{prefix}_{f}"] = st[f]
    for key, prefix in _FAMILY_SCOPE_KEYS.items():
        if key in out:
            out[f"{prefix}_formation_family_id"] = FS.family_id(out.pop(key))
    return out


def _neutral_formation_input(d) -> dict | None:
    """Neutralize one `formation_context.team_{a,b}_prematch_formation` block (a
    FormationInput.to_dict()). Replaces `formation` -> structural attrs + formation_id,
    `formation_family` -> family_id, and remaps `distribution` keys (which are raw formation
    strings -- SS16: audit ALL fields, not just the obvious ones) to formation ids too."""
    if not isinstance(d, dict):
        return d
    st = FS.formation_structure(d.get("formation"))
    dist = d.get("distribution")
    neutral_dist = None
    if isinstance(dist, dict):
        neutral_dist = {FS.formation_structure(k)["formation_id"]: v for k, v in dist.items()}
    return {
        "formation_id": st["formation_id"],
        **{f: st[f] for f in _STRUCT_FIELDS},
        "structure_known": st["structure_known"],
        "formation_family_id": FS.family_id(d.get("formation_family")),
        "source_type": d.get("source_type"),
        "confidence": d.get("confidence"),
        "source_version": d.get("source_version"),
        "distribution_by_formation_id": neutral_dist,
        "policy_version": d.get("policy_version"),
        "family_version": d.get("family_version"),
        "structure_version": FS.FORMATION_STRUCTURE_VERSION,
    }


def neutralize_for_llm_v2(source_packet: dict) -> dict:
    """The full V3 identity-neutral transform. Pure function of `source_packet`."""
    src_hash = source_packet.get("packet_hash") or _source_packet_hash(source_packet)

    # Stage 1: reuse V2's team/competition/season neutralization verbatim.
    p = NZ.neutralize_packet(source_packet)

    # Stage 2: formation identity (NEW in V3) -- evidence scopes + formation_context.
    for e in p.get("evidence", []):
        sc = e.get("scope")
        if isinstance(sc, dict):
            e["scope"] = _neutralize_formation_scope(sc)

    fcx = p.get("formation_context")
    if isinstance(fcx, dict):
        for key in ("team_a_prematch_formation", "team_b_prematch_formation"):
            if key in fcx:
                fcx[key] = _neutral_formation_input(fcx[key])
        fcx["formation_structure_version"] = FS.FORMATION_STRUCTURE_VERSION

    # Stage 3: type/version tagging + rehash + provenance hashes (SS20-SS23).
    p.pop("packet_hash", None)
    p["packet_kind"] = PACKET_KIND
    p["packet_schema_version"] = V3.PACKET_SCHEMA_VERSION
    p["neutralization_policy_version"] = V3.NEUTRALIZATION_POLICY_VERSION
    p["formation_structure_version"] = FS.FORMATION_STRUCTURE_VERSION
    p["source_evidence_packet_hash"] = src_hash
    neutral_hash = hashlib.sha256(
        json.dumps({k: v for k, v in p.items() if k != "packet_hash"},
                   sort_keys=True, default=str).encode()).hexdigest()
    p["packet_hash"] = neutral_hash
    p["neutral_llm_packet_hash"] = neutral_hash
    return p


def is_neutralized(packet: dict) -> bool:
    """The predicate the V4 adapter's hard interface guard checks (SS22)."""
    return (isinstance(packet, dict)
            and packet.get("packet_kind") == PACKET_KIND
            and packet.get("packet_schema_version") == V3.PACKET_SCHEMA_VERSION
            and bool(packet.get("source_evidence_packet_hash"))
            and bool(packet.get("neutral_llm_packet_hash")))


# ---------------------------------------------------------------------------
# Alias-swap controls (V3 patch SS24-SS26): perturb an ALREADY-neutral packet's arbitrary
# tokens only, holding every measured value/id/structure fixed. Pure string remap over the
# neutral packet -- never touches the source packet, never changes a numeric value.
# ---------------------------------------------------------------------------
def _remap_strings(obj, mapping: dict[str, str]):
    if isinstance(obj, str):
        return mapping.get(obj, obj)
    if isinstance(obj, dict):
        return {k: _remap_strings(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_remap_strings(v, mapping) for v in obj]
    return obj


def _rehash_neutral(p: dict) -> dict:
    p = dict(p)
    p.pop("packet_hash", None)
    p.pop("neutral_llm_packet_hash", None)
    h = hashlib.sha256(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()
    p["packet_hash"] = h
    p["neutral_llm_packet_hash"] = h
    return p


def alias_team_tokens(neutral_packet: dict, new_a: str = "ENTITY_X",
                      new_b: str = "ENTITY_Y") -> dict:
    """Control #1 (SS24): swap the arbitrary team tokens for different arbitrary tokens.
    Behavior/evidence/structure are byte-identical; only the fixture-local alias changes."""
    mapping = {NZ.TEAM_A_TOKEN: new_a, NZ.TEAM_B_TOKEN: new_b}
    return _rehash_neutral(_remap_strings(neutral_packet, mapping))


def alias_competition_token(neutral_packet: dict, new_comp: str = "COMP_X") -> dict:
    """Control #2 (SS25): swap the arbitrary competition token for a different one."""
    mapping = {NZ.COMP_TOKEN: new_comp}
    return _rehash_neutral(_remap_strings(neutral_packet, mapping))


def alias_formation_id(neutral_packet: dict, old_id: str, new_id: str) -> dict:
    """Control #3 (SS26): swap one arbitrary formation_id token for a different one, holding
    structural attributes and behavioral evidence fixed. Only touches the id STRING; the
    structural counts sitting next to it are untouched, so this isolates whether the anonymous
    TOKEN itself (as opposed to the structure it names) carries influence."""
    return _rehash_neutral(_remap_strings(neutral_packet, {old_id: new_id}))


# ---------------------------------------------------------------------------
# Defense-in-depth identity-leak audit (SS16, SS43-SS45, SS60): scan the FULLY neutralized
# packet for any real identifier that should never have survived the transform.
# ---------------------------------------------------------------------------
def _all_strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _all_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _all_strings(v)


def find_identity_leaks(neutral_packet: dict, source_packet: dict) -> list[str]:
    """Return every real identifier string found verbatim inside the neutralized packet.
    Empty list = clean. Checks: real home/away team names, real competition, real season,
    every exact formation string and family name actually present in the source packet
    (evidence scopes + formation_context), so a bug in formation neutralization specifically
    (not just team/competition) is caught too."""
    fx = source_packet.get("fixture", {})
    blocklist: set[str] = set()
    for v in (fx.get("home"), fx.get("away"), fx.get("competition"), fx.get("season")):
        if isinstance(v, str) and v:
            blocklist.add(v)

    def _collect_formation_strings(pkt):
        found = set()
        for e in pkt.get("evidence", []):
            sc = e.get("scope") or {}
            for k in ("prematch_formation", "team_formation", "opp_formation"):
                if isinstance(sc.get(k), str):
                    found.add(sc[k])
            for k in ("formation_family", "team_family", "opp_family"):
                if isinstance(sc.get(k), str):
                    found.add(sc[k])
        fcx = pkt.get("formation_context") or {}
        for key in ("team_a_prematch_formation", "team_b_prematch_formation"):
            d = fcx.get(key) or {}
            if isinstance(d, dict):
                if isinstance(d.get("formation"), str):
                    found.add(d["formation"])
                if isinstance(d.get("formation_family"), str):
                    found.add(d["formation_family"])
                dist = d.get("distribution")
                if isinstance(dist, dict):
                    found.update(k for k in dist if isinstance(k, str))
        return found

    blocklist |= _collect_formation_strings(source_packet)
    # only flag NON-trivial identifiers (avoid false positives on short generic tokens that
    # could coincidentally be a substring of something benign, e.g. a single-letter season).
    blocklist = {b for b in blocklist if len(b) >= 3}

    leaks = []
    for s in _all_strings(neutral_packet):
        for real in blocklist:
            if real in s:
                leaks.append(f"{real!r} found in string {s!r}")
    return leaks
