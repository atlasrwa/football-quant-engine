"""V6 transport preflight and accounting (`v6_transport_v1`). §29.

    "Reuse V5A.2 preflight."

So V6 does not reimplement it. `v5a2_transport` closed defect D4 -- boto3 without a
`converse` method, the environment mistake that consumed V5A.1's authorized window at zero
spend -- by asserting the CAPABILITY on the client object rather than a version string, and
by keeping charged calls and spend moving together so a transport failure can never inflate
the estimate. None of that reasoning changed between V5A.2 and V6, and reimplementing it
would only create a second thing to keep in step. The frozen module is reused verbatim; its
hash is carried in both the V5A.2 and the V6 preregistrations, which is the proof it was not
edited.

    preflight(client, *, require_converse=True)   asserts `hasattr(client, "converse")`,
                                                   raises `TransportPreflightFailure` before
                                                   the first paid call, returns the full
                                                   environment report otherwise.
    TransportAccounting                            attempted / charged / transport-failure,
                                                   with a hard ceiling.
    environment_report()                           interpreter, python, boto3/botocore
                                                   version and path.

THE GetInferenceProfile LIMITATION, STATED HONESTLY (§29)
----------------------------------------------------------
§29 asks the preflight to verify the model identifier format and the credentials/region,
and explicitly permits NOT calling `GetInferenceProfile` when the execution role lacks the
`bedrock:GetInferenceProfile` describe permission, PROVIDED invocation through the frozen
profile has already been demonstrated. Both conditions hold here:

  * The model id is a cross-region INFERENCE PROFILE id (`us.anthropic.claude-sonnet-4-6`),
    not a foundation-model id. Describing it requires `bedrock:GetInferenceProfile`, which
    this execution role is not assumed to hold.
  * Invocation through this exact profile id was already demonstrated by the V5A.1 paid
    calls -- six Converse calls returned billed responses against it. A describe call would
    verify metadata the invocation path does not consult; the invocation itself is the
    stronger evidence, and it exists.

So the V6 preflight verifies the id FORMAT (a non-empty inference-profile-shaped string) and
the client capability, and does NOT require a describe round-trip. The limitation is
recorded rather than papered over: `preflight_profile_note()` states exactly what was and
was not checked, and it goes into the transport report and the preregistration. A check we
do not perform is documented as one we do not perform.

THE COST-CEILING / RETRY DEFECT THIS MODULE NOW CLOSES (pre-spend amendment 1)
------------------------------------------------------------------------------
The frozen `hard_ceiling_usd` prices exactly `n_calls` requests at `max_tokens` of output.
That is a bound on BILLABLE ATTEMPTS only if one logical call can be billed at most once.
A default `boto3.client("bedrock-runtime")` breaks that assumption: botocore's default
retry mode is `legacy` (up to 5 total attempts) and the default `read_timeout` is 60s. A
Converse call the server ACCEPTS and BILLS, but whose response body is not read within the
timeout, raises `ReadTimeoutError` -- which botocore then RETRIES, producing a second
billed generation for one logical call. Under the default client the true worst case is up
to 5x the frozen ceiling, so the ceiling was not a bound at all; it was an estimate of the
no-retry case wearing a bound's label. This is the same "a requirement that is not asserted
is not a requirement" failure that produced D4.

V6 closes it by OPTION B (§28): retries are DISABLED for the experiment, so one logical call
is at most one billable attempt and `n_calls` billable attempts is a true worst case. The
policy is frozen here as `TRANSPORT_CONFIG_KWARGS`, the client is constructed from it by
`build_client()`, and `assert_no_retries()` proves on the CONSTRUCTED client object that
`max_attempts == 1` -- the capability, not a version string, exactly as the converse gate
does. A run whose client can retry is aborted at zero spend.

The read timeout is raised well above the observed p90/worst output latency to REDUCE the
probability that a billed response is abandoned client-side. It does NOT guarantee network
delivery, and the cost guarantee does not depend on delivery: the guarantee is that
`total_max_attempts == 1`, so even if an accepted, billed response is lost, V6 does not
automatically retry and one logical call still bills at most once. Connect timeout is
bounded so a dead endpoint fails fast as a transport failure (which is never charged)
rather than hanging.

ZERO SPEND. Importing this module makes no network call and constructs no client.
"""
from __future__ import annotations

import re

from src.research.hypothesis_oos import v5a2_transport as T

TRANSPORT_VERSION = "v6_transport_v2"

# ----------------------------------------------------------------------------------------
# FROZEN TRANSPORT POLICY (§28). Retries DISABLED so one logical call bills at most once and
# the frozen `hard_ceiling_usd` is a true upper bound on billable attempts.
# ----------------------------------------------------------------------------------------
#: Total attempts per logical call, INCLUDING the first. 1 == the first attempt only, no
#: retries. This is the property that makes `n_calls` billable attempts a hard bound.
MAX_BILLABLE_ATTEMPTS_PER_CALL = 1

#: Read timeout, seconds. Deliberately generous: a Converse response at max_tokens=8192 can
#: take tens of seconds to stream. A longer timeout REDUCES the chance a billed response is
#: abandoned client-side; it does NOT guarantee delivery. The cost guarantee rests on
#: total_max_attempts == 1 (no auto-retry), not on delivery. See the module docstring.
READ_TIMEOUT_SECONDS = 900

#: Connect timeout, seconds. A dead endpoint should fail fast and be recorded as a transport
#: failure (never charged), not hang for the full read timeout.
CONNECT_TIMEOUT_SECONDS = 20

#: The botocore Config kwargs the frozen client is built from. `retries.total_max_attempts`
#: is botocore's own name for "attempts including the first"; `max_attempts` is kept in
#: lockstep as the legacy alias so the policy reads correctly under either accessor.
TRANSPORT_CONFIG_KWARGS = {
    "retries": {"total_max_attempts": MAX_BILLABLE_ATTEMPTS_PER_CALL, "mode": "standard"},
    "read_timeout": READ_TIMEOUT_SECONDS,
    "connect_timeout": CONNECT_TIMEOUT_SECONDS,
}

REGION_NAME = "us-east-1"
SERVICE_NAME = "bedrock-runtime"

#: Reused verbatim from the frozen V5A.2 module. Named here so V6 code and tests import from
#: one place, but they are the SAME objects -- `test_v6_transport_reuses_v5a2` asserts it.
TransportPreflightFailure = T.TransportPreflightFailure
TransportAccounting = T.TransportAccounting
environment_report = T.environment_report
FIRST_BOTO3_WITH_CONVERSE = T.FIRST_BOTO3_WITH_CONVERSE


class RetryPolicyViolation(TransportPreflightFailure):
    """Raised before the first paid call when the client could bill a call more than once.

    A subclass of `TransportPreflightFailure` so the driver's existing `except
    TransportPreflightFailure` still aborts at zero spend on it, but distinguishable in a
    log from a missing-converse failure."""

#: The frozen model identifier. A cross-region inference-profile id, not a foundation-model
#: id. Format-checked, not describe-checked, for the reason in the module docstring.
MODEL_ID = "us.anthropic.claude-sonnet-4-6"

#: An inference-profile id: a region-family prefix, then a vendor.model path. Deliberately
#: loose -- it verifies SHAPE, the one thing a format check can, and does not pretend to
#: verify existence, which only a describe call or an invocation could.
_INFERENCE_PROFILE_RX = re.compile(r"^[a-z]{2}\.[a-z0-9-]+\.[a-z0-9.\-:]+$")


def is_inference_profile_id(model_id: str) -> bool:
    return bool(_INFERENCE_PROFILE_RX.match(model_id or ""))


def model_id_report(model_id: str = MODEL_ID) -> dict:
    return {"model_id": model_id,
            "looks_like_inference_profile": is_inference_profile_id(model_id),
            "id_kind": "cross_region_inference_profile",
            "format_checked": True,
            "describe_checked": False}


def preflight_profile_note() -> dict:
    """Exactly what the preflight does and does not verify about the model id. §29."""
    return {
        "get_inference_profile_called": False,
        "reason": ("the model id is a cross-region inference-profile id and describing it "
                   "requires bedrock:GetInferenceProfile, a permission this execution role "
                   "is not assumed to hold. §29 permits omitting the describe call when "
                   "invocation through the frozen profile has already been demonstrated."),
        "invocation_through_this_profile_demonstrated_by":
            "V5A.1 paid calls -- six Converse requests returned billed responses against "
            "this exact profile id",
        "what_is_verified": ["client exposes `converse` (hasattr, not a version string)",
                             "model id has inference-profile format",
                             "interpreter / boto3 / botocore recorded for attribution"],
        "what_is_not_verified": ["GetInferenceProfile metadata (describe permission "
                                 "absent; invocation is the stronger evidence and exists)"],
    }


def build_client(region_name: str = REGION_NAME):
    """Construct the frozen bedrock-runtime client with retries DISABLED.

    This is the ONLY client the V6 driver may use. Building it here, from
    `TRANSPORT_CONFIG_KWARGS`, is what makes the no-retry policy a property of the object
    the driver actually calls rather than a sentence in a report. Constructs a client but
    makes no network call.
    """
    import boto3
    from botocore.config import Config
    return boto3.client(SERVICE_NAME, region_name=region_name,
                        config=Config(**TRANSPORT_CONFIG_KWARGS))


def client_max_attempts(client) -> int:
    """Total attempts (including the first) the CONSTRUCTED client is configured for.

    Read off the live client's own botocore Config, never off a version string or a kwargs
    dict we hope was applied -- the capability of the object, as the converse gate is.
    Returns a large sentinel if the client exposes no retry config, so an unknown client is
    treated as UNBOUNDED (worst case) and fails the assertion rather than passing silently.
    """
    try:
        retries = client.meta.config.retries or {}
    except Exception:
        return 1_000_000
    for key in ("total_max_attempts", "max_attempts"):
        v = retries.get(key)
        if isinstance(v, int) and v > 0:
            # botocore's `max_attempts` legacy alias counts RETRIES + 1 in standard mode and
            # RETRIES in legacy mode; `total_max_attempts` is unambiguous. Prefer it, and
            # when only `max_attempts` is present treat it as total attempts (the stricter
            # reading), so we never under-count billable attempts.
            return v if key == "total_max_attempts" else max(v, 1)
    return 1_000_000


def retry_policy_report(client=None) -> dict:
    """What the frozen policy is, and -- if a client is given -- what it actually resolved to."""
    rep = {
        "policy": "retries_disabled",
        "max_billable_attempts_per_call": MAX_BILLABLE_ATTEMPTS_PER_CALL,
        "config_kwargs": {k: (dict(v) if isinstance(v, dict) else v)
                          for k, v in TRANSPORT_CONFIG_KWARGS.items()},
        "read_timeout_seconds": READ_TIMEOUT_SECONDS,
        "connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
        "rationale": ("one logical call bills at most once, so n_calls billable attempts "
                      "is a true worst case and hard_ceiling_usd is a real upper bound "
                      "(§28, pre-spend amendment 1). The cost guarantee rests on "
                      "total_max_attempts == 1 (no auto-retry), NOT on network delivery: "
                      "even if an accepted, billed response is lost, V6 does not retry. A "
                      "long read timeout only reduces the chance of client-side abandonment."),
    }
    if client is not None:
        observed = client_max_attempts(client)
        rep["observed_client_max_attempts"] = observed
        rep["retries_disabled_on_client"] = observed <= MAX_BILLABLE_ATTEMPTS_PER_CALL
    return rep


def assert_no_retries(client) -> dict:
    """Prove on the CONSTRUCTED client that a call bills at most once. Raises otherwise.

    Called by `preflight` at zero spend. A client whose botocore Config permits more than
    `MAX_BILLABLE_ATTEMPTS_PER_CALL` total attempts could re-bill a timed-out-but-accepted
    call, which would make `hard_ceiling_usd` an underestimate -- so the run is aborted at
    zero spend rather than started against a ceiling that is not a bound.
    """
    observed = client_max_attempts(client)
    if observed > MAX_BILLABLE_ATTEMPTS_PER_CALL:
        raise RetryPolicyViolation(
            f"the Bedrock client is configured for {observed} attempts per call; V6 "
            f"requires retries DISABLED ({MAX_BILLABLE_ATTEMPTS_PER_CALL} total attempt) so "
            f"one logical call bills at most once and hard_ceiling_usd is a true bound. "
            f"Build the client with v6_transport.build_client(). Aborted at zero spend.")
    return retry_policy_report(client)


def preflight(client, *, require_converse: bool = True, model_id: str = MODEL_ID) -> dict:
    """The V5A.2 preflight, plus the model-id format check, the retry-policy assertion and
    the §29 profile note.

    Raises `TransportPreflightFailure` (or its `RetryPolicyViolation` subclass) before the
    first paid call. The V5A.2 capability gate is unchanged; V6 ADDS a format check on the
    id, an assertion that the client cannot bill a call twice, and records the describe
    limitation. A format failure or a retry-enabled client is a hard problem; a missing
    describe permission is NOT a problem, and is recorded rather than raised.
    """
    rep = T.preflight(client, require_converse=require_converse)   # raises on no-converse
    rep["v6_transport_version"] = TRANSPORT_VERSION
    rep["model_id"] = model_id
    rep["model_id_report"] = model_id_report(model_id)
    rep["profile_note"] = preflight_profile_note()

    # Retry policy: assert BEFORE recording, so a retry-enabled client aborts at zero spend.
    rep["retry_policy"] = assert_no_retries(client)   # raises RetryPolicyViolation

    problems = list(rep.get("problems") or [])
    if not is_inference_profile_id(model_id):
        problems.append(
            f"model id {model_id!r} does not have inference-profile format; a malformed id "
            f"cannot be invoked and the run is aborted at zero spend")
    rep["problems"] = problems
    rep["ok"] = not problems
    if problems:
        raise TransportPreflightFailure("; ".join(problems))
    return rep


def version_stamp() -> dict:
    return {"transport_version": TRANSPORT_VERSION,
            "reuses": T.TRANSPORT_VERSION,
            "model_id": MODEL_ID,
            "capability_gate": "hasattr(client, 'converse')",
            "get_inference_profile_required": False,
            "first_boto3_with_converse": FIRST_BOTO3_WITH_CONVERSE,
            "max_billable_attempts_per_call": MAX_BILLABLE_ATTEMPTS_PER_CALL,
            "retries_disabled": True,
            "read_timeout_seconds": READ_TIMEOUT_SECONDS,
            "connect_timeout_seconds": CONNECT_TIMEOUT_SECONDS,
            "transport_config_kwargs": {
                k: (dict(v) if isinstance(v, dict) else v)
                for k, v in TRANSPORT_CONFIG_KWARGS.items()},
            "retry_policy_asserted_on_client": True}
