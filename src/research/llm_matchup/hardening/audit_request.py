"""Audit the ACTUAL SERIALIZED Bedrock request text (V3 patch SS60).

Patch SS60 is explicit: "Unit tests on Python objects are not sufficient... Capture or
deterministically render the exact request payload that would be sent to Bedrock." This
module renders the literal system + user message strings adapter_v4 would send (same
functions, same content) and scans THAT TEXT -- not the Python dict -- for leaked real
identifiers. It never sends anything over the network and never logs credentials; it is a
pure string-rendering + scanning utility.
"""
from __future__ import annotations
import json

from src.research.llm_matchup import ontology as ONT
from src.research.llm_matchup.hardening import prompt_v4 as PR4
from src.research.llm_matchup.hardening import schema_v3 as SCH3
from src.research.llm_matchup.hardening import neutralize_v3 as NZ3


def render_request_text(neutral_packet: dict) -> str:
    """The exact system + user text adapter_v4.analyze_matchup_v4 would send for this packet
    (same prompt/user_message/schema functions -- no separate rendering logic to drift)."""
    tool_schema = SCH3.build_schema()
    user = PR4.user_message(neutral_packet, ONT.to_dict(), tool_schema)
    return PR4.SYSTEM_PROMPT_V4 + "\n\n" + user


def audit_serialized_request(neutral_packet: dict, source_packet: dict) -> list[str]:
    """Render the literal request text and scan it (not the Python dict) for every real
    identifier present in `source_packet` (team names, competition, season, exact formation
    strings, family names). Returns the list of leaks found (empty = clean). Reuses the same
    blocklist-construction logic as neutralize_v3.find_identity_leaks so the two checks stay
    consistent, but operates on the SERIALIZED TEXT."""
    text = render_request_text(neutral_packet)
    fx = source_packet.get("fixture", {})
    blocklist: set[str] = set()
    for v in (fx.get("home"), fx.get("away"), fx.get("competition"), fx.get("season")):
        if isinstance(v, str) and len(v) >= 3:
            blocklist.add(v)

    def _collect_formation_strings(pkt):
        found = set()
        for e in pkt.get("evidence", []):
            sc = e.get("scope") or {}
            for k in ("prematch_formation", "team_formation", "opp_formation",
                     "formation_family", "team_family", "opp_family"):
                if isinstance(sc.get(k), str):
                    found.add(sc[k])
        fcx = pkt.get("formation_context") or {}
        for key in ("team_a_prematch_formation", "team_b_prematch_formation"):
            d = fcx.get(key) or {}
            if isinstance(d, dict):
                for k in ("formation", "formation_family"):
                    if isinstance(d.get(k), str):
                        found.add(d[k])
                dist = d.get("distribution")
                if isinstance(dist, dict):
                    found.update(k for k in dist if isinstance(k, str))
        return {f for f in found if len(f) >= 3}

    blocklist |= _collect_formation_strings(source_packet)

    leaks = []
    for real in sorted(blocklist):
        if real in text:
            leaks.append(f"{real!r} found in serialized request text")
    return leaks


def render_and_check(source_packet: dict) -> dict:
    """Convenience: neutralize + render + audit in one call. Returns a small report dict
    suitable for persisting as a research diagnostic (SS60: persist only safe diagnostics,
    never the raw payload with real identifiers)."""
    neutral = NZ3.neutralize_for_llm_v2(source_packet)
    leaks = audit_serialized_request(neutral, source_packet)
    text = render_request_text(neutral)
    return {
        "fixture_id": source_packet.get("fixture", {}).get("fixture_id"),
        "neutral_llm_packet_hash": neutral.get("neutral_llm_packet_hash"),
        "source_evidence_packet_hash": neutral.get("source_evidence_packet_hash"),
        "request_text_sha256": __import__("hashlib").sha256(text.encode()).hexdigest(),
        "request_text_length": len(text),
        "leaks": leaks,
        "clean": leaks == [],
    }
