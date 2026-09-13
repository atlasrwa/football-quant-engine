"""Identifier neutralization for the runtime LLM packet (patch §25, §26, §48).

The closed-world contract says identifiers are NOT evidence. The strongest way to enforce
that is to STOP SENDING real identifiers to the model at runtime: replace team display
names with TEAM_A / TEAM_B and the competition name with a neutral, environment-only id.
The LLM does not need "Manchester City" to reason about crossing, box pressure, shot
creation or formation behavior — it needs the evidence (patch §25).

DETERMINISM & VALUE PRESERVATION (critical). Neutralization is a PURE STRING SUBSTITUTION on
IDENTIFIER FIELDS ONLY. It must NOT change any numeric evidence value, sample_n, reliability,
temporal_status, cutoff, or the set of evidence ids. This is what makes the name-control and
competition-control experiments valid: the neutral packet and the real-name packet differ in
IDENTIFIERS ONLY, so any change in the emitted state is attributable to the identifier, not to
different evidence (patch §25 FAIL-CLOSED comparison).

Fields neutralized:
  * fixture.home / fixture.away              -> TEAM_A / TEAM_B
  * fixture.competition                      -> COMP_NEUTRAL (or a stable pseudo-id)
  * fixture.season                           -> SEASON_NEUTRAL
  * team_a.name / team_b.name                -> TEAM_A / TEAM_B
  * evidence[*].scope.team/opponent          -> TEAM_A / TEAM_B (by name match)
  * evidence[*].scope.competition/season     -> neutral tokens (substring replace)
  * formation_context team-name references (none by name today, but future-proofed)

Everything else (evidence ids, values, ns, provider, reliability, formation labels which are
tactical not identity, tier summaries) is preserved byte-for-byte. Evidence IDS ARE NOT
CHANGED so citations remain resolvable.

Two public entry points:
  * neutralize_packet(packet)        — default runtime transform (both teams + competition).
  * team_name_control_pair(packet)   — returns (real_named, neutral) for the name control.
  * competition_control_pair(packet) — returns (real_comp, neutral_comp) keeping team names,
                                        isolating the competition-identity effect.
"""
from __future__ import annotations
import copy
from src.research.llm_matchup.evidence import packet_hash

TEAM_A_TOKEN = "TEAM_A"
TEAM_B_TOKEN = "TEAM_B"
COMP_TOKEN = "COMP_NEUTRAL"
SEASON_TOKEN = "SEASON_NEUTRAL"


def _rehash(packet: dict) -> dict:
    packet.pop("packet_hash", None)
    packet["packet_hash"] = packet_hash(packet)
    return packet


def _sub_str(value, mapping: dict[str, str]):
    """Replace any full-string or substring identifier occurrences in a string value."""
    if not isinstance(value, str):
        return value
    out = value
    # full-string replacements first (exact identity), then substring (season embeds comp)
    for src, dst in mapping.items():
        if out == src:
            return dst
    for src, dst in mapping.items():
        if src and src in out:
            out = out.replace(src, dst)
    return out


def _neutralize_scope(scope: dict, mapping: dict[str, str]) -> dict:
    out = {}
    for k, v in scope.items():
        if isinstance(v, str):
            out[k] = _sub_str(v, mapping)
        elif isinstance(v, list):
            out[k] = [_neutralize_scope(x, mapping) if isinstance(x, dict)
                      else _sub_str(x, mapping) for x in v]
        elif isinstance(v, dict):
            out[k] = _neutralize_scope(v, mapping)
        else:
            out[k] = v
    return out


def _apply(packet: dict, mapping: dict[str, str], *, neutralize_comp: bool) -> dict:
    """Apply an identifier mapping to identifier fields only; preserve all values + ids."""
    p = copy.deepcopy(packet)

    fx = p.get("fixture", {})
    if "home" in fx:
        fx["home"] = _sub_str(fx["home"], mapping)
    if "away" in fx:
        fx["away"] = _sub_str(fx["away"], mapping)
    if neutralize_comp:
        if "competition" in fx:
            fx["competition"] = COMP_TOKEN
        if "season" in fx:
            fx["season"] = SEASON_TOKEN

    for side in ("team_a", "team_b"):
        if side in p and isinstance(p[side], dict) and "name" in p[side]:
            p[side]["name"] = _sub_str(p[side]["name"], mapping)

    comp_map = dict(mapping)
    if neutralize_comp:
        # add competition/season substring neutralization for scopes
        for e in p.get("evidence", []):
            sc = e.get("scope")
            if isinstance(sc, dict):
                if "competition" in sc and isinstance(sc["competition"], str):
                    sc["competition"] = COMP_TOKEN
                if "season" in sc and isinstance(sc["season"], str):
                    sc["season"] = SEASON_TOKEN
    for e in p.get("evidence", []):
        sc = e.get("scope")
        if isinstance(sc, dict):
            e["scope"] = _neutralize_scope(sc, mapping)

    # formation_context prematch blocks are tactical labels, not identity; only names matter
    fcx = p.get("formation_context")
    if isinstance(fcx, dict):
        for key in ("team_a_prematch_formation", "team_b_prematch_formation"):
            blk = fcx.get(key)
            if isinstance(blk, dict):
                fcx[key] = _neutralize_scope(blk, mapping)

    return _rehash(p)


def _team_mapping(packet: dict) -> dict[str, str]:
    fx = packet.get("fixture", {})
    home = fx.get("home")
    away = fx.get("away")
    mapping: dict[str, str] = {}
    if home:
        mapping[home] = TEAM_A_TOKEN
    if away:
        mapping[away] = TEAM_B_TOKEN
    return mapping


def neutralize_packet(packet: dict) -> dict:
    """Default runtime neutralization: neutral team tokens + neutral competition/season
    (patch §25 strongly-recommended runtime default). Values/ids preserved."""
    return _apply(packet, _team_mapping(packet), neutralize_comp=True)


def team_name_control_pair(packet: dict) -> tuple[dict, dict]:
    """(real_named, neutral_teams) — competition kept identical in BOTH so the ONLY thing that
    changes is the TEAM identity (patch §25). Any material state change on the neutral variant
    means the model is leaning on club-name stereotypes -> FAIL CLOSED."""
    real = _rehash(copy.deepcopy(packet))
    neutral_teams = _apply(packet, _team_mapping(packet), neutralize_comp=False)
    return real, neutral_teams


def competition_control_pair(packet: dict) -> tuple[dict, dict]:
    """(real_comp, neutral_comp) — TEAM names kept identical in BOTH; only the competition
    identity is neutralized (patch §26). Isolates league-stereotype dependence."""
    real = _rehash(copy.deepcopy(packet))
    neutral_comp = _apply(packet, {}, neutralize_comp=True)
    return real, neutral_comp


def assert_value_preserving(original: dict, neutral: dict) -> None:
    """Guard used by tests + controls: neutralization must not alter evidence VALUES, ns,
    reliability, temporal_status, or the id SET (patch §25 validity requirement)."""
    o = {e["id"]: e for e in original["evidence"]}
    n = {e["id"]: e for e in neutral["evidence"]}
    if set(o) != set(n):
        raise AssertionError("neutralization changed the evidence id set")
    for eid, oe in o.items():
        ne = n[eid]
        for field in ("value", "sample_n", "reliability", "temporal_status", "metric",
                      "cutoff_unix", "evidence_level", "shrinkage_level"):
            if oe.get(field) != ne.get(field):
                raise AssertionError(f"neutralization changed evidence[{eid}].{field}: "
                                     f"{oe.get(field)!r} -> {ne.get(field)!r}")
