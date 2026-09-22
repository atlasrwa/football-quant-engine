"""Frozen Item 6 Stage-1 evidence-packet provider for LIVE execution.

`item6_frozen_packet_provider_v1`. ZERO PAID INFERENCE. No network, no LLM.

At live time the paid runner must transmit EXACTLY the evidence packet that was frozen in the
materialized request set -- never an empty packet, never a live-time re-assembled packet that
could differ from what a human authorized. This provider enforces that:

  1. it loads the frozen materialized request set (which binds, per fixture, the frozen
     packet_sha256 and canonical_request_sha256) and the frozen evidence packet set (which
     carries the full packet bodies);
  2. for a given fixture it RE-MATERIALIZES the packet deterministically from the frozen
     corpus + frozen materializer, then verifies the re-materialized packet_sha256 EQUALS the
     frozen packet_sha256;  (defence: live data drift / nondeterminism -> fail closed)
  3. it verifies the frozen-set packet body's own hash matches too;
  4. it returns the verified packet body for the runner to embed.

FAIL CLOSED. Any of: fixture absent from the frozen set; empty/missing packet; re-materialized
hash != frozen hash; frozen body hash mismatch -> raises FrozenPacketError. The LIVE path must
treat that as a hard stop BEFORE CountTokens and BEFORE the attempt marker.

An EMPTY packet ({}) can never be produced here: the materializer fails closed if a fixture
has no evidence, and this provider additionally rejects any packet with zero evidence items.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

from src.research.item6.evidence import packet_materializer as PM

FROZEN_PACKET_PROVIDER_VERSION = "item6_frozen_packet_provider_v1"

DEFAULT_REQUEST_SET_REL = \
    "research/item6/out/execution/ITEM6_STAGE1_MATERIALIZED_REQUEST_SET_V1.json"
DEFAULT_PACKET_SET_REL = \
    "research/item6/out/execution/ITEM6_STAGE1_EVIDENCE_PACKET_SET_V1.json"


class FrozenPacketError(RuntimeError):
    """Raised (fail closed) when the frozen packet for a fixture cannot be verified."""


class FrozenPacketProvider:
    """Loads + verifies frozen evidence packets bound by the materialized request set."""

    def __init__(self, request_set: Dict[str, Any], packet_set: Dict[str, Any],
                 corpus: Optional[PM._Corpus] = None, data_root: str = PM.ROOT_DEFAULT):
        self._req_by_fixture = {e["fixture_id"]: e for e in request_set["entries"]}
        self._packet_by_fixture = {p["fixture_id"]: p for p in packet_set["packets"]}
        self._corpus = corpus
        self._data_root = data_root
        self.materialized_request_set_sha256 = request_set.get("materialized_request_set_sha256")
        self.evidence_packet_set_sha256 = packet_set.get("evidence_packet_set_sha256")

    @classmethod
    def from_frozen(cls, code_root: str = PM.ROOT_DEFAULT,
                    data_root: str = PM.ROOT_DEFAULT,
                    request_set_rel: str = DEFAULT_REQUEST_SET_REL,
                    packet_set_rel: str = DEFAULT_PACKET_SET_REL) -> "FrozenPacketProvider":
        req = json.load(open(f"{code_root}/{request_set_rel}"))
        pkt = json.load(open(f"{code_root}/{packet_set_rel}"))
        return cls(req, pkt, corpus=None, data_root=data_root)

    def _corpus_lazy(self) -> PM._Corpus:
        if self._corpus is None:
            self._corpus = PM.load_corpus(self._data_root)
        return self._corpus

    def frozen_packet_sha256(self, fixture_id: str) -> str:
        entry = self._req_by_fixture.get(fixture_id)
        if entry is None:
            raise FrozenPacketError(f"fixture {fixture_id} absent from frozen request set")
        return entry["packet_sha256"]

    def get_verified_packet(self, fixture: Dict[str, Any]) -> Dict[str, Any]:
        """Return the frozen, verified evidence packet for a fixture. Fail closed on any
        mismatch. Re-materializes from the frozen corpus and checks the hash matches the
        frozen binding, then returns the frozen body (which itself must hash-match)."""
        fid = fixture["fixture_id"]
        req_entry = self._req_by_fixture.get(fid)
        if req_entry is None:
            raise FrozenPacketError(f"fixture {fid} absent from frozen request set")
        frozen_sha = req_entry["packet_sha256"]

        body_entry = self._packet_by_fixture.get(fid)
        if body_entry is None:
            raise FrozenPacketError(f"fixture {fid} absent from frozen packet set")
        packet = body_entry["packet"]

        # empty-packet impossibility.
        if not isinstance(packet, dict) or not packet.get("evidence") \
                or int(packet.get("n_evidence_items", 0)) <= 0:
            raise FrozenPacketError(f"fixture {fid} frozen packet is empty (refused)")

        # frozen body self-hash must match its bound sha.
        body_sha = PM.packet_hash(packet)
        if body_sha != frozen_sha:
            raise FrozenPacketError(
                f"fixture {fid} frozen packet body hash {body_sha} != bound {frozen_sha}")

        # re-materialize deterministically and require identical hash (drift/nondeterminism).
        rematerialized = PM.materialize_item6_evidence_packet(
            fixture, fixture["kickoff_unix"], corpus=self._corpus_lazy(),
            root=self._data_root)
        if rematerialized["packet_sha256"] != frozen_sha:
            raise FrozenPacketError(
                f"fixture {fid} re-materialized packet hash "
                f"{rematerialized['packet_sha256']} != frozen {frozen_sha} (data drift)")

        return packet

    def version_stamp(self) -> Dict[str, Any]:
        return {
            "frozen_packet_provider_version": FROZEN_PACKET_PROVIDER_VERSION,
            "materialized_request_set_sha256": self.materialized_request_set_sha256,
            "evidence_packet_set_sha256": self.evidence_packet_set_sha256,
            "empty_packet_possible": False,
            "rematerialization_hash_check": True,
        }
