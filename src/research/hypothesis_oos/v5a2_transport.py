"""Transport preflight and accounting (`v5a2_transport_v1`). Tasks S16, S17.

WHY THIS EXISTS -- defect D4
----------------------------
V5A.1's authorized execution made three calls, each of which died with

    AttributeError: 'BedrockRuntime' object has no attribute 'converse'

because the driver ran under the system interpreter, whose boto3 is 1.34.46 -- a version
predating the Converse API entirely. $0 was spent, the consecutive-transport-failure rule
fired correctly, and the whole authorized window was consumed by an environment mistake
that was knowable before the first call. The V3 run had hit the same class of problem, and
the V5A.1 authorization explicitly said not to repeat it. It was repeated because nothing
in the apparatus ACTUALLY CHECKED -- the requirement lived in prose.

    A REQUIREMENT THAT IS NOT ASSERTED IS NOT A REQUIREMENT.

`preflight()` asserts it, raises `TransportPreflightFailure` before any call is attempted,
and records the full environment in the execution log so a later reader can tell which
interpreter produced a result.

The check is on the CLIENT OBJECT, not on a version string: `hasattr(client, "converse")`
is the property the driver actually depends on. A version comparison would be a proxy for
it, and proxies are how D4 happened.
"""
from __future__ import annotations

import sys

TRANSPORT_VERSION = "v5a2_transport_v1"

#: The first boto3 release exposing `BedrockRuntime.converse`. Recorded for the report;
#: NOT used as the gate -- the gate is the capability itself.
FIRST_BOTO3_WITH_CONVERSE = "1.35.0"


class TransportPreflightFailure(RuntimeError):
    """Raised before the first paid call when the environment cannot make one."""


def environment_report() -> dict:
    """Everything needed to attribute a result to an interpreter, gathered defensively."""
    rep = {"python_executable": sys.executable,
           "python_version": sys.version.split()[0]}
    for mod in ("boto3", "botocore"):
        try:
            m = __import__(mod)
            rep[f"{mod}_version"] = getattr(m, "__version__", "unknown")
            rep[f"{mod}_path"] = getattr(m, "__file__", "unknown")
        except Exception as exc:                      # pragma: no cover - env dependent
            rep[f"{mod}_version"] = f"IMPORT_FAILED: {exc}"
    return rep


def preflight(client, *, require_converse: bool = True) -> dict:
    """Assert the client can do what the battery needs. Raises, or returns the report.

    MUST be called before the first Bedrock request. `_execute_v5a2.py` calls it while
    `spend_usd == 0.0` and aborts the run on failure.
    """
    rep = environment_report()
    rep["transport_version"] = TRANSPORT_VERSION
    rep["client_type"] = type(client).__name__
    rep["has_converse"] = bool(hasattr(client, "converse"))
    rep["has_converse_stream"] = bool(hasattr(client, "converse_stream"))
    rep["first_boto3_with_converse"] = FIRST_BOTO3_WITH_CONVERSE

    problems = []
    if require_converse and not rep["has_converse"]:
        problems.append(
            f"the Bedrock client exposes no `converse` method. boto3 "
            f"{rep.get('boto3_version')} at {rep.get('boto3_path')} under interpreter "
            f"{rep['python_executable']} cannot run this battery. Converse first appears "
            f"in boto3 {FIRST_BOTO3_WITH_CONVERSE}. This is defect D4 from V5A.1; the run "
            f"is aborted at zero spend rather than burning the authorization on "
            f"AttributeErrors.")
    rep["problems"] = problems
    rep["ok"] = not problems
    if problems:
        raise TransportPreflightFailure("; ".join(problems))
    return rep


class TransportAccounting:
    """Per-call transport accounting (task S17).

    Distinguishes the three outcomes V5A.1's log could not tell apart: a call that never
    reached the provider, a call that reached it and failed, and a call that returned.
    Only the third can cost money, so `spend_usd` and `n_calls_charged` move together and
    a transport failure can never inflate the spend estimate.
    """

    def __init__(self, price_in_per_1k: float, price_out_per_1k: float,
                 ceiling_usd: float):
        self.price_in_per_1k = price_in_per_1k
        self.price_out_per_1k = price_out_per_1k
        self.ceiling_usd = ceiling_usd
        self.n_attempted = 0
        self.n_charged = 0
        self.n_transport_failures = 0
        self.n_consecutive_transport_failures = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.spend_usd = 0.0
        self.events: list = []

    def record_transport_failure(self, seq, detail: str) -> None:
        self.n_attempted += 1
        self.n_transport_failures += 1
        self.n_consecutive_transport_failures += 1
        self.events.append({"seq": seq, "outcome": "TRANSPORT_FAILURE",
                            "charged": False, "detail": detail[:400]})

    def record_call(self, seq, input_tokens: int, output_tokens: int) -> float:
        self.n_attempted += 1
        self.n_charged += 1
        self.n_consecutive_transport_failures = 0
        self.total_input_tokens += input_tokens
        self.total_output_tokens += output_tokens
        cost = (input_tokens / 1000 * self.price_in_per_1k
                + output_tokens / 1000 * self.price_out_per_1k)
        self.spend_usd += cost
        self.events.append({"seq": seq, "outcome": "CHARGED", "charged": True,
                            "input_tokens": input_tokens,
                            "output_tokens": output_tokens,
                            "cost_usd": round(cost, 6),
                            "cumulative_usd": round(self.spend_usd, 6)})
        return cost

    def would_exceed_ceiling(self, projected_cost: float) -> bool:
        return (self.spend_usd + projected_cost) > self.ceiling_usd

    def to_dict(self) -> dict:
        return {"transport_version": TRANSPORT_VERSION,
                "n_attempted": self.n_attempted,
                "n_charged": self.n_charged,
                "n_transport_failures": self.n_transport_failures,
                "n_consecutive_transport_failures": self.n_consecutive_transport_failures,
                "total_input_tokens": self.total_input_tokens,
                "total_output_tokens": self.total_output_tokens,
                "spend_usd": round(self.spend_usd, 6),
                "ceiling_usd": self.ceiling_usd,
                "events": self.events}
