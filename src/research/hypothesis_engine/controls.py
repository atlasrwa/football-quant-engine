"""Deterministic control-perturbation layer (`hypothesis_controls_v1`).

WHY THIS MODULE EXISTS
----------------------
The V1 pre-spend manifest preregistered nine controls but froze only the twelve REFERENCE
packets. The perturbed scientific inputs for the other controls (alias / formation-ablation
/ profile-perturbation / venue-flip / irrelevant-field / evidence-starvation /
unsupported-data-trap) did not exist in frozen, hash-pinned form, so V1 was drift-aborted.

This module is the fix: every control is a PURE, DETERMINISTIC packet -> packet function
with a pinned version and pinned parameters. Given the frozen reference packets it
regenerates byte-identical transformed packets, so their hashes can be pinned into the V2
manifest BEFORE any inference. No transform reads the corpus, the network, a clock or a
random source. There is deliberately NO Bedrock import here (the package-isolation test
scans for it), so this file cannot make a paid call.

INVARIANTS
  * The input packet dict is never mutated: every function deep-copies first.
  * Evidence ids stay identity-neutral (HOME_*/AWAY_*), so intent comparison is never
    confounded by an incidentally-renamed reference.
  * The packet_hash is recomputed by `context_packet.packet_hash` after every transform,
    so a transformed packet is self-consistent and independently verifiable.
  * `repeatability` is NOT here: it reuses the reference packet and hash unchanged, so it
    has no transformed scientific input to freeze.
"""
from __future__ import annotations

import copy
from typing import Optional

from . import context_packet as CP

CONTROLS_VERSION = "hypothesis_controls_v1"


# ======================================================================================
# Frozen parameters. Every knob any control uses is a module constant, so the manifest can
# quote them verbatim and nothing is chosen at runtime.
# ======================================================================================

#: identity_alias -- display-label substitutions ONLY. These are SYNTHETIC symbols, never
#: real clubs, so the control tests symbolic-identity invariance without contaminating the
#: experiment with the model's pretrained knowledge of real teams. The canonical subject
#: enum (HOME_TEAM / AWAY_TEAM) is untouched: those are structural roles, not identities.
IDENTITY_ALIAS_MAP = {
    "HOME_TEAM": "ALPHA_TEAM",
    "AWAY_TEAM": "BETA_TEAM",
    "COMPETITION": "LEAGUE_X",
}

#: formation_ablation -- the formation-bearing surfaces removed. Raw-stat evidence is left
#: fully intact; only formation CONTEXT is withdrawn.
FORMATION_DIMENSIONS = ("own_formation_family", "opponent_formation_family")
FORMATION_ABLATION_NOTE = ("formation context deliberately removed for this control; "
                           "formation-conditioned questions are expected to abstain or "
                           "disappear while raw-stat questions remain answerable")

#: profile_perturbation -- flip the OPPONENT-of-subject concession band by scaling the AWAY
#: side's DEFENSIVE (AGAINST) raw metrics on two coherent, mechanistically-linked axes.
#: corners_against and accurate_crosses_against move TOGETHER because a side that concedes
#: more wide deliveries also tends to concede more corners -- keeping the perturbed profile
#: football-coherent rather than an arbitrary single-field jolt. Two directions are frozen
#: so the six profile fixtures split deterministically into raise/lower halves.
PROFILE_PERTURBATION_AXES = ("corners_against", "accurate_crosses_against")
PROFILE_PERTURBATION_SUBJECT = "AWAY"          # perturb the away team's concession profile
PROFILE_PERTURBATION_SIDE = "AGAINST"
PROFILE_RAISE_FACTOR = 1.60                    # high-concession band
PROFILE_LOWER_FACTOR = 0.55                    # low-concession band
#: Fixtures (by battery order index) that get the RAISE direction; the rest get LOWER.
#: Frozen split so every one of the six cases is fully determined in advance.
PROFILE_RAISE_INDICES = (0, 1, 2)              # first three profile fixtures -> raise

#: venue_flip -- swap home/away display labels AND the paired FOR/AGAINST evidence between
#: the two subjects, so "home team" and "away team" are coherently exchanged. Formation
#: distribution keys are swapped to match.
VENUE_FLIP_NOTE = ("home/away roles deliberately swapped for this control; venue-"
                   "conditioned questions may legitimately change, non-venue questions "
                   "should not")

#: irrelevant_field -- change ONLY a provably-irrelevant metadata tag. `notes` is free-text
#: commentary that is NOT part of normalized intent, the capability manifest, the evidence,
#: the vocabulary or the query plan, so altering it must not move scientific intent.
IRRELEVANT_FIELD_TAG = "batch_tag=IRRELEVANT_CONTROL_A7F3"

#: evidence_starvation -- keep only this many evidence items, chosen deterministically as
#: the first-by-sorted-id items, and blank their values so no cohort is estimable. A valid
#: packet capable of testing abstention/narrowing, not a malformed one.
STARVATION_KEEP_N = 4

#: unsupported_data_trap -- add a NOTE that dangles unavailable context (injuries, expected
#: formation) WITHOUT adding any evidence item or capability for it. Tests whether the model
#: invents an injury/expected-formation hypothesis. No evidence is fabricated.
UNSUPPORTED_DATA_TRAP_NOTE = (
    "pre-match chatter mentions possible absences and a rumoured starting shape for the "
    "upcoming fixture; NONE of this is present as evidence and no capability supports it")


# ======================================================================================
# Helpers
# ======================================================================================
def _rehash(packet: dict) -> dict:
    """Recompute the self-consistent packet_hash after a transform."""
    packet.pop("packet_hash", None)
    packet["packet_hash"] = CP.packet_hash(packet)
    return packet


def _subject_of(evidence_id: str) -> str:
    return evidence_id.split("_", 1)[0]


# ======================================================================================
# Controls
# ======================================================================================
def identity_alias(packet: dict) -> dict:
    """Replace SYNTHETIC display identities only. Evidence, manifest, vocabulary,
    formation VALUES and the canonical subject enum are untouched."""
    p = copy.deepcopy(packet)
    fx = p.get("fixture", {})
    for role in ("home", "away", "competition"):
        v = fx.get(role)
        if v in IDENTITY_ALIAS_MAP:
            fx[role] = IDENTITY_ALIAS_MAP[v]
    # formation_distribution is keyed by the canonical subject role (HOME_TEAM/AWAY_TEAM),
    # which is a structural enum, NOT a display identity -- leave it exactly as is so the
    # alias control changes ONLY the free display labels.
    return _rehash(p)


def formation_ablation(packet: dict) -> dict:
    """Remove formation context only. Raw-stat evidence preserved verbatim."""
    p = copy.deepcopy(packet)
    man = p.get("capability_manifest") or {}
    man["available_dimensions"] = [d for d in (man.get("available_dimensions") or [])
                                   if d not in FORMATION_DIMENSIONS]
    cov = man.get("coverage") or {}
    for d in FORMATION_DIMENSIONS:
        cov.pop(d, None)
    man["coverage"] = cov
    p["capability_manifest"] = man
    p["formation_distribution"] = {}
    notes = list(p.get("notes") or [])
    notes.append(FORMATION_ABLATION_NOTE)
    p["notes"] = notes
    return _rehash(p)


def profile_perturbation(packet: dict, *, raise_band: bool) -> tuple[dict, list[dict]]:
    """Scale the away side's concession on two mechanistically-linked wide-play axes.

    raise_band=True  -> multiply by PROFILE_RAISE_FACTOR  (high-concession opponent)
    raise_band=False -> multiply by PROFILE_LOWER_FACTOR  (low-concession opponent)

    Only AWAY corners_against / accurate_crosses_against move, and they move TOGETHER, so
    the perturbed profile stays internally coherent (a side that concedes more wide
    deliveries also concedes more corners). Values are rounded to 4dp to match the packet's
    own precision. Returns (perturbed_packet, list_of_before_after_changes); the changes are
    provenance recorded in the manifest and are NOT written into the packet the model sees.
    """
    p = copy.deepcopy(packet)
    factor = PROFILE_RAISE_FACTOR if raise_band else PROFILE_LOWER_FACTOR
    changed: list[dict] = []
    for e in p.get("evidence") or []:
        if (_subject_of(e["id"]) == PROFILE_PERTURBATION_SUBJECT
                and e.get("metric") in PROFILE_PERTURBATION_AXES
                and e.get("value") is not None):
            before = e["value"]
            after = round(before * factor, 4)
            changed.append({"id": e["id"], "metric": e["metric"],
                            "before": before, "after": after, "factor": factor})
            e["value"] = after
    return _rehash(p), changed


def venue_flip(packet: dict) -> dict:
    """Swap home/away roles coherently: display labels, evidence subject prefixes, and
    formation-distribution keys are all exchanged HOME<->AWAY."""
    p = copy.deepcopy(packet)
    fx = p.get("fixture", {})
    fx["home"], fx["away"] = fx.get("away"), fx.get("home")

    # swap evidence subject prefix HOME_<->AWAY_ ; ids must stay unique and neutral
    for e in p.get("evidence") or []:
        subj = _subject_of(e["id"])
        rest = e["id"].split("_", 1)[1]
        if subj == "HOME":
            e["id"] = f"AWAY_{rest}"
        elif subj == "AWAY":
            e["id"] = f"HOME_{rest}"
        sc = e.get("scope") or {}
        if sc.get("subject") == "HOME":
            sc["subject"] = "AWAY"
        elif sc.get("subject") == "AWAY":
            sc["subject"] = "HOME"

    fd = p.get("formation_distribution") or {}
    if "HOME_TEAM" in fd or "AWAY_TEAM" in fd:
        p["formation_distribution"] = {
            "HOME_TEAM": fd.get("AWAY_TEAM", {}),
            "AWAY_TEAM": fd.get("HOME_TEAM", {}),
        }
    notes = list(p.get("notes") or [])
    notes.append(VENUE_FLIP_NOTE)
    p["notes"] = notes
    return _rehash(p)


def irrelevant_field(packet: dict) -> dict:
    """Change only a provably-irrelevant metadata tag (a note). Nothing that feeds
    normalized intent, the manifest, the evidence or the vocabulary is touched."""
    p = copy.deepcopy(packet)
    notes = list(p.get("notes") or [])
    notes.append(IRRELEVANT_FIELD_TAG)
    p["notes"] = notes
    return _rehash(p)


def evidence_starvation(packet: dict) -> dict:
    """Deterministically strip to STARVATION_KEEP_N items and blank their values, leaving a
    structurally valid packet on which abstention/narrowing is the correct behaviour."""
    p = copy.deepcopy(packet)
    ev = sorted(p.get("evidence") or [], key=lambda e: e["id"])[:STARVATION_KEEP_N]
    for e in ev:
        e["value"] = None
        e["sample_n"] = 0
        e["reliability"] = "LOW"
        e["temporal_status"] = "UNAVAILABLE"
    p["evidence"] = ev
    dq = p.get("data_quality") or {}
    dq["n_evidence"] = len(ev)
    dq["n_pit_safe"] = 0
    dq["n_unavailable"] = len(ev)
    p["data_quality"] = dq
    notes = list(p.get("notes") or [])
    notes.append("evidence deliberately starved for this control; abstention or a small "
                 "number of narrow, well-hedged questions is the correct response")
    p["notes"] = notes
    return _rehash(p)


def unsupported_data_trap(packet: dict) -> dict:
    """Dangle unavailable context in a NOTE without adding any evidence or capability."""
    p = copy.deepcopy(packet)
    notes = list(p.get("notes") or [])
    notes.append(UNSUPPORTED_DATA_TRAP_NOTE)
    p["notes"] = notes
    # capability_manifest.unsupported_context already lists injuries / expected_formation /
    # minute_level_events as UNSUPPORTED -- we do NOT change it. The trap is purely the note.
    return _rehash(p)
