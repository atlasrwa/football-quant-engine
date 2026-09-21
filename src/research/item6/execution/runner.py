"""ITEM 6 Stage-1 minimal research-only live runner (execution amendment).

`item6_stage1_runner_v1`. ZERO SPEND on import and in all tests. The runner performs a paid
call ONLY when handed a real Bedrock `converse` client AND after the attempt-marker,
call-cap, byte-budget, and monetary-reservation checks pass. Tests inject deterministic
local stand-ins, so `LIVE_SONNET_CALLS` stays 0.

FROZEN SEMANTICS ENFORCED (B1-B4)
  * exact request-set binding: each fixture's request is rebuilt from the frozen prompt body
    + tool schema + inference config + fixture identity, re-hashed, and checked against the
    frozen request-set skeleton hash and the per-request byte budget;
  * attempt marker BEFORE transmission: a durable marker is written, then the call is made;
  * ONE attempt per fixture: MAX_RETRIES_PER_FIXTURE == 0; a marker without a trustworthy
    receipt on resume is UNCERTAIN_ATTEMPT_NOT_RETRIED, never retried;
  * 120 absolute paid-call cap: enforced by the spend guard's call cap before transmission;
  * monetary reservation before call: the spend guard reserves the call's cost against the
    human-authorized ceiling before transmission, using the AUTHORITATIVE AWS Bedrock
    CountTokens input-token count (v2) plus the frozen MAX output reserve; over-ceiling =>
    CALL_BLOCKED_BY_SPEND_CAP;
  * authoritative pre-inference token count (v2): immediately before each paid call the
    runner calls CountTokens for the EXACT request that would be transmitted; a non-ok count
    (unavailable / error / malformed / request-mismatch / missing tool schema) =>
    CALL_BLOCKED_BY_TOKEN_COUNT and nothing transmits (fail closed, no optimistic estimate);
    CountTokens is an execution-control call, NOT a model treatment, and never consumes one
    of the 120 paid-treatment slots;
  * byte ceiling retained: MAX_REQUEST_UTF8_BYTES remains an INDEPENDENT constraint enforced
    before counting (REQUEST_INTEGRITY_FAILURE if exceeded);
  * receipt/raw-response persistence + provider-envelope verification;
  * resume idempotency: a fixture with a persisted terminal record is skipped;
  * unknown status FAILS CLOSED: stops the active runner;
  * artifact/cohort/CHAMPION hash guards: refuses to run if any frozen identity drifted;
  * NO CHAMPION dependency: CHAMPION is only hash-checked for integrity, never read into logic.

The runner NEVER decides science. It produces per-fixture raw responses; the frozen Item 6
harness/gate consume them separately and unchanged.
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

from src.research.item6.execution import execution_status as ES
from src.research.item6.execution import request_builder as RB
from src.research.item6.execution import token_counter as TC
from src.research.item6.execution.spend_guard import (
    CallCapExceeded, PriceTable, SpendCapExceeded, SpendGuard)

RUNNER_VERSION = "item6_stage1_runner_v2"
ROOT = "/home/ubuntu"

# Frozen identities the runner refuses to run without (drift => refuse).
SCIENTIFIC_HASHES = {
    "research/item6/ITEM6_RESEARCH_PROTOCOL_V1.md": "4ba1c40f9fc047e0247944c0c5cb29355c90b196952bc8dcbdf0392301cb4839",
    "research/item6/DETERMINISTIC_BASELINE_COVERAGE_SPEC_V1.md": "05fd187979f2dba866b8ed55974ce7ea0e532cb68d0649fdbc0ccb480a438542",
    "research/item6/ITEM6_MECHANISM_PROMPT_V1.md": "36b98540db4beb4ee8f7c70f919a179019f450ec3ebce96d9a28b50f95e171f0",
    "research/item6/ITEM6_MECHANISM_SCHEMA_V1.md": "13b0296d14bf4d63cc23ff0b10b67eb90a7fc8ed7fdd5aa097370e21ec0e34da",
    "src/research/item6/baseline_equivalence.py": "e85527015d351a90c29a60294e4e839b400d8c6c002f7307d40587ed83817993",
    "src/research/item6/formalizer.py": "212a14a90ba31f950b69238aba8340c9859150f2f46affacc5f6d14252d71936",
    "research/item6/STAGE1_QUALITY_PROTOCOL_V1.md": "24c1d810b3e3471071ee69d678fab766b1038085ee9020dbac7894e17686bfcb",
    "research/item6/STAGE1_GATE_V1.md": "ef0b0d9566c707200ad4af699314165d555c54fa38119f74f40e3b157aa653a4",
    "research/item6/STAGE1_POWER_AND_COST_V1.md": "a2d31d1d1c71e71ad3a4ba482962453e7a93ea3358b1b11247f3524462b8d80b",
}
COHORT_PATH = "research/item6/ITEM6_STAGE1_COHORT_MANIFEST_V1.json"
COHORT_SHA256 = "f92cd6a23c1bc3a8e7f8fe5eabff9d1bf643802f42c6261ba069f128bfeaf54b"
CHAMPION_PATH = "data/discovery/pilotC_stat_mixer.json"
CHAMPION_SHA256 = "0b8f5ff3dc4ddf15363d17989330b6f010197265ce8d2ee892cdc7ca410c00c9"


class RunnerRefused(RuntimeError):
    """Raised before any call when a frozen identity drifted or integrity is uncertain."""


class RunnerFailClosed(RuntimeError):
    """Raised to STOP the active runner on unknown status / integrity failure."""


def _sha_file(root: str, rel: str) -> str:
    with open(f"{root}/{rel}", "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def verify_frozen_identities(root: str = ROOT) -> Dict[str, str]:
    """Refuse to run unless every frozen scientific artifact + cohort + CHAMPION matches.
    CHAMPION is only hash-checked (integrity), never read into runner logic."""
    problems: List[str] = []
    for rel, want in SCIENTIFIC_HASHES.items():
        got = _sha_file(root, rel)
        if got != want:
            problems.append(f"SCIENTIFIC_DRIFT {rel}: {got} != {want}")
    cg = _sha_file(root, COHORT_PATH)
    if cg != COHORT_SHA256:
        problems.append(f"COHORT_DRIFT: {cg} != {COHORT_SHA256}")
    ch = _sha_file(root, CHAMPION_PATH)
    if ch != CHAMPION_SHA256:
        problems.append(f"CHAMPION_DRIFT: {ch} != {CHAMPION_SHA256}")
    if problems:
        raise RunnerRefused("; ".join(problems))
    return {"scientific_ok": "true", "cohort_ok": "true", "champion_ok": "true"}


@dataclass
class RunnerConfig:
    out_dir: str                         # dedicated Item 6 execution output directory
    human_authorized_ceiling_usd: float  # 0.0 => nothing may transmit (not yet authorized)
    price_table_path: str = f"{ROOT}/research/item6/ITEM6_STAGE1_PRICE_TABLE_V1.json"
    root: str = ROOT
    verify_identities: bool = True
    # v2: the AWS Bedrock CountTokens callable, fn(modelId=..., input=...) -> {"inputTokens":n}.
    # None => the authoritative provider token count is UNAVAILABLE and every paid inference is
    # BLOCKED before transmission (fail closed; never an optimistic estimate). Tests inject a
    # deterministic local stand-in; production binds bedrock_runtime_client.count_tokens.
    count_tokens_fn: Optional[Callable[..., Dict]] = None


@dataclass
class FixtureResult:
    fixture_id: str
    status: str
    request_sha256: str
    receipt_present: bool
    transmitted: bool
    reservation_usd: float = 0.0
    realized_cost_usd: Optional[float] = None
    provider_counted_input_tokens: Optional[int] = None
    count_status: str = ""
    detail: str = ""

    def to_dict(self) -> Dict[str, object]:
        return {k: v for k, v in self.__dict__.items()}


class Stage1Runner:
    """Enforces the frozen execution semantics. `converse_fn(request)->raw_response` is the
    ONLY thing that can touch the network; tests pass a deterministic local stand-in."""

    def __init__(self, cfg: RunnerConfig):
        self.cfg = cfg
        if cfg.verify_identities:
            verify_frozen_identities(cfg.root)
        os.makedirs(self.attempts_dir, exist_ok=True)
        os.makedirs(self.receipts_dir, exist_ok=True)
        price = PriceTable.from_json(cfg.price_table_path)
        self.guard = SpendGuard.load_or_new(
            ceiling_usd=cfg.human_authorized_ceiling_usd,
            call_cap=ES.ABSOLUTE_MAX_PAID_CALLS,
            price=price,
            ledger_path=f"{cfg.out_dir}/spend_ledger.json")
        self.system_text = RB.load_frozen_system_text(cfg.root)
        # v2: execution-control CountTokens accounting. NOT scientific model treatments; never
        # increments paid-treatment / generation-call counters.
        self.count_counters = TC.CountTokensCounters()

    # ---- paths ------------------------------------------------------------------------
    @property
    def attempts_dir(self) -> str:
        return f"{self.cfg.out_dir}/attempts"

    @property
    def receipts_dir(self) -> str:
        return f"{self.cfg.out_dir}/receipts"

    def _attempt_path(self, fx: str) -> str:
        return f"{self.attempts_dir}/{fx}.json"

    def _receipt_path(self, fx: str) -> str:
        return f"{self.receipts_dir}/{fx}.json"

    # ---- durability -------------------------------------------------------------------
    @staticmethod
    def _atomic_write(path: str, obj: Dict) -> None:
        d = os.path.dirname(path)
        os.makedirs(d, exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w") as f:
            json.dump(obj, f, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)

    def _write_attempt_marker(self, fx: str, request_sha256: str) -> None:
        """DURABLE marker written BEFORE any transmission."""
        self._atomic_write(self._attempt_path(fx), {
            "fixture_id": fx,
            "request_sha256": request_sha256,
            "attempt_marker_written": True,
            "transmitted": False,
            "status": ES.UNKNOWN_EXECUTION_STATUS,
            "receipt_present": False,
            "runner_version": RUNNER_VERSION,
        })

    def _update_attempt(self, fx: str, **kw) -> None:
        p = self._attempt_path(fx)
        rec = json.load(open(p)) if os.path.exists(p) else {"fixture_id": fx}
        rec.update(kw)
        self._atomic_write(p, rec)

    # ---- resume ------------------------------------------------------------------------
    def _resume_status(self, fx: str) -> Optional[str]:
        """Return a terminal status for a fixture already processed (idempotent skip), or
        None if it should be attempted. A marker WITHOUT a receipt is uncertain -> not
        retried."""
        ap = self._attempt_path(fx)
        if not os.path.exists(ap):
            return None
        rec = json.load(open(ap))
        receipt = os.path.exists(self._receipt_path(fx))
        if receipt:
            return ES.TRANSPORT_OK
        if rec.get("attempt_marker_written"):
            return ES.UNCERTAIN_ATTEMPT_NOT_RETRIED
        return None

    # ---- provider-envelope verification -----------------------------------------------
    @staticmethod
    def _verify_envelope(raw: Dict) -> bool:
        """A trustworthy Converse envelope must carry an output message and a usage block."""
        if not isinstance(raw, dict):
            return False
        out = raw.get("output", {})
        msg = out.get("message") if isinstance(out, dict) else None
        usage = raw.get("usage")
        return bool(msg) and isinstance(usage, dict) and \
            "inputTokens" in usage and "outputTokens" in usage

    # ---- one fixture ------------------------------------------------------------------
    def run_fixture(self, fixture: Dict, converse_fn: Optional[Callable[[Dict], Dict]],
                    fixture_packet: Optional[Dict] = None) -> FixtureResult:
        fx = fixture["fixture_id"]

        # 0. idempotent resume: already handled?
        resumed = self._resume_status(fx)
        if resumed is not None:
            return FixtureResult(fx, resumed, request_sha256="",
                                 receipt_present=os.path.exists(self._receipt_path(fx)),
                                 transmitted=(resumed == ES.TRANSPORT_OK),
                                 detail="resumed")

        # 1. rebuild the exact request + integrity checks (byte budget). The byte ceiling is
        #    RETAINED as an INDEPENDENT safety constraint and is enforced BEFORE any counting.
        req = RB.canonical_request(fixture, self.system_text, evidence_packet=fixture_packet)
        rsha = RB.request_sha256(req)
        if not RB.within_byte_budget(req):
            self._update_attempt(fx, status=ES.REQUEST_INTEGRITY_FAILURE,
                                 request_sha256=rsha, attempt_marker_written=False)
            raise RunnerFailClosed(
                f"{fx}: request exceeds MAX_REQUEST_UTF8_BYTES ({RB.request_byte_len(req)})")

        # 2. PRE-CALL call-cap gate, BEFORE any transmission (and before counting spends
        #    nothing scientific).
        if not self.guard.call_cap_ok():
            return FixtureResult(fx, ES.CALL_BLOCKED_BY_CALL_CAP, rsha, False, False,
                                 detail="call cap reached")

        # 3. AUTHORITATIVE provider token count (execution-control CountTokens; NOT inference).
        #    The count targets the EXACT request that would be transmitted. Any non-ok count
        #    (unavailable / error / malformed / request-mismatch / missing tool schema) BLOCKS
        #    the paid inference before transmission -- fail closed, never an optimistic estimate.
        count = TC.count_input_tokens(req, self.cfg.count_tokens_fn, self.count_counters)
        if not count.ok:
            return FixtureResult(fx, ES.CALL_BLOCKED_BY_TOKEN_COUNT, rsha, False, False,
                                 provider_counted_input_tokens=None,
                                 count_status=count.status,
                                 detail=f"token count blocked: {count.status}")
        provider_tokens = count.input_tokens

        # 3b. request immutability after count: the request we counted MUST be the request we
        #     are about to reserve for and transmit. (Recount/RE-derive would be required if it
        #     changed; here the request is rebuilt deterministically and re-hashed.)
        if count.inference_request_sha256 != rsha:
            return FixtureResult(fx, ES.CALL_BLOCKED_BY_TOKEN_COUNT, rsha, False, False,
                                 provider_counted_input_tokens=provider_tokens,
                                 count_status=TC.PRECALL_TOKEN_COUNT_REQUEST_MISMATCH,
                                 detail="request changed after count")

        # 4. PRE-CALL monetary reservation using the AUTHORITATIVE provider input-token count
        #    plus the frozen MAX output reserve, checked against the human ceiling.
        if not self.guard.spend_cap_ok_for_input_tokens(provider_tokens, RB.MAX_TOKENS):
            return FixtureResult(fx, ES.CALL_BLOCKED_BY_SPEND_CAP, rsha, False, False,
                                 provider_counted_input_tokens=provider_tokens,
                                 count_status=count.status,
                                 detail="reservation would exceed ceiling")

        # 5. reserve (durable) THEN write attempt marker (durable) THEN transmit. Reserving
        #    first means a crash after reserve/marker can never under-count spend or retry.
        try:
            reservation = self.guard.reserve_with_provider_count(
                fixture_id=fx, provider_counted_input_tokens=provider_tokens,
                max_output_tokens=RB.MAX_TOKENS)
        except CallCapExceeded:
            return FixtureResult(fx, ES.CALL_BLOCKED_BY_CALL_CAP, rsha, False, False,
                                 provider_counted_input_tokens=provider_tokens,
                                 count_status=count.status)
        except SpendCapExceeded:
            return FixtureResult(fx, ES.CALL_BLOCKED_BY_SPEND_CAP, rsha, False, False,
                                 provider_counted_input_tokens=provider_tokens,
                                 count_status=count.status)

        self._write_attempt_marker(fx, rsha)

        if converse_fn is None:
            # No transport supplied => nothing transmits. The reservation + marker persist,
            # so this fixture's single attempt is considered spent (uncertain), never retried.
            self._update_attempt(fx, transmitted=False,
                                 status=ES.UNCERTAIN_ATTEMPT_NOT_RETRIED)
            return FixtureResult(fx, ES.UNCERTAIN_ATTEMPT_NOT_RETRIED, rsha, False, False,
                                 reservation_usd=reservation,
                                 provider_counted_input_tokens=provider_tokens,
                                 count_status=count.status,
                                 detail="no transport supplied")

        # 6. transmit exactly once.
        self._update_attempt(fx, transmitted=True)
        try:
            raw = converse_fn(req)
        except TimeoutError as e:
            self._update_attempt(fx, status=ES.MODEL_TIMEOUT)
            return FixtureResult(fx, ES.MODEL_TIMEOUT, rsha, False, True,
                                 reservation_usd=reservation,
                                 provider_counted_input_tokens=provider_tokens,
                                 count_status=count.status, detail=str(e)[:200])
        except ConnectionError as e:
            self._update_attempt(fx, status=ES.MODEL_TRANSPORT_FAILURE)
            return FixtureResult(fx, ES.MODEL_TRANSPORT_FAILURE, rsha, False, True,
                                 reservation_usd=reservation,
                                 provider_counted_input_tokens=provider_tokens,
                                 count_status=count.status, detail=str(e)[:200])
        except Exception as e:  # noqa: BLE001  provider-side error
            self._update_attempt(fx, status=ES.MODEL_PROVIDER_ERROR)
            return FixtureResult(fx, ES.MODEL_PROVIDER_ERROR, rsha, False, True,
                                 reservation_usd=reservation,
                                 provider_counted_input_tokens=provider_tokens,
                                 count_status=count.status, detail=str(e)[:200])

        # 7. verify + persist receipt. A response that fails envelope verification is a
        #    RECEIPT_VERIFICATION_FAILED terminal (no retry): transmission happened, we just
        #    cannot trust the envelope.
        if not self._verify_envelope(raw):
            self._update_attempt(fx, status=ES.RECEIPT_VERIFICATION_FAILED)
            return FixtureResult(fx, ES.RECEIPT_VERIFICATION_FAILED, rsha, False, True,
                                 reservation_usd=reservation,
                                 provider_counted_input_tokens=provider_tokens,
                                 count_status=count.status, detail="bad provider envelope")

        usage = raw["usage"]
        realized = self.guard.reconcile(
            fixture_id=fx, actual_input_tokens=int(usage["inputTokens"]),
            actual_output_tokens=int(usage["outputTokens"]))
        self._atomic_write(self._receipt_path(fx), {
            "fixture_id": fx,
            "request_sha256": rsha,
            "raw_response": raw,
            "resolved_model_id": raw.get("_resolved_model_id") or raw.get("modelId"),
            "usage": usage,
            "provider_counted_input_tokens": provider_tokens,
            "count_input_sha256": count.count_input_sha256,
            "runner_version": RUNNER_VERSION,
        })
        # A trustworthy response exists => the fixture received its treatment. We do NOT retry
        # on <K mechanisms, duplicates, baseline-equivalence, abstention, or later
        # formalization failure: those are scientific observations for the harness/gate.
        self._update_attempt(fx, status=ES.TRANSPORT_OK, receipt_present=True)
        return FixtureResult(fx, ES.TRANSPORT_OK, rsha, True, True,
                             reservation_usd=reservation, realized_cost_usd=realized,
                             provider_counted_input_tokens=provider_tokens,
                             count_status=count.status, detail="received")

    # ---- integrity check across ledger + receipts -------------------------------------
    def integrity_ok(self) -> bool:
        """The number of TRANSPORT_OK receipts must not exceed reserved/charged calls, and
        charged calls must not exceed reserved calls. Inconsistency => fail closed."""
        n_receipts = len([f for f in os.listdir(self.receipts_dir)
                          if f.endswith(".json")]) if os.path.isdir(self.receipts_dir) else 0
        if self.guard.n_calls_charged > self.guard.n_calls_reserved:
            return False
        if n_receipts > self.guard.n_calls_charged:
            return False
        return True

    def assert_integrity(self) -> None:
        if not self.integrity_ok():
            raise RunnerFailClosed(
                "attempt ledger / reception counter inconsistent (fail closed)")


def version_stamp() -> Dict[str, object]:
    return {
        "runner_version": RUNNER_VERSION,
        "enforces_attempt_marker_before_transmission": True,
        "max_retries_per_fixture": ES.MAX_RETRIES_PER_FIXTURE,
        "absolute_max_paid_calls": ES.ABSOLUTE_MAX_PAID_CALLS,
        "precall_spend_reservation": True,
        "hard_monetary_stop": True,
        "call_cap_stop": True,
        "resume_idempotent": True,
        "unknown_status_fails_closed": True,
        "champion_dependency": False,
        # v2 amendment
        "provider_token_count_precall": True,
        "count_tokens_matches_actual_request": True,
        "count_tokens_failure_blocks_inference": True,
        "request_immutable_after_count": True,
        "byte_ceiling_retained": True,
        "count_tokens_consumes_treatment_slot": False,
    }
