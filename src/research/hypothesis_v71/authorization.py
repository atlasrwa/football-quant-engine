"""V7.1 confirmatory authorization gate (`v71_authorization_v1`). Section 21 / mission item 2.

The one-way door. The confirmatory run computes fresh out-of-sample outcomes; once it does,
V7.1 becomes live and immutable and no further tuning is legitimate. To make that crossing
IMPOSSIBLE to trip by accident -- and impossible to trip on the same turn the executor code is
edited -- the run requires TWO independent things:

  1. an explicit `--authorize` flag on the driver;
  2. a valid AUTHORIZATION ARTIFACT (`V7_1_CONFIRMATORY_AUTHORIZATION.json`) that does NOT
     exist during the closure mission and is created only by a separate, deliberate act.

The artifact is CONTENT-BOUND: it carries the exact hashes the run must match --
    * the experiment id,
    * the freeze-manifest hash,
    * the executable source-graph hash,
    * the upstream-V7 hash,
    * the fresh-content hash.
At preflight the driver recomputes all of these from disk; the run proceeds only if the token
is present, well-formed, and every expected hash equals the live one. A token minted against a
different freeze, different code, or different fresh content is refused.

Because the check is entirely a matter of the token's CONTENT, opening the door later requires
NO code change: someone mints the artifact with the then-current hashes and re-runs. That is
the point -- the executor is frozen now; only a new data artifact is added later.

This module MINTS NOTHING. `build_expected(...)` describes what a valid token must contain, and
`verify(...)` checks a supplied one. Creating the file is deliberately not implemented here.
"""
from __future__ import annotations

AUTHORIZATION_VERSION = "v71_authorization_v1"

AUTHORIZATION_ARTIFACT = "V7_1_CONFIRMATORY_AUTHORIZATION.json"

#: The fields a valid authorization token must bind. Missing or extra top-level binding fields
#: make the token malformed and the run is refused.
REQUIRED_BINDINGS = (
    "experiment",
    "freeze_manifest_sha256",
    "source_graph_sha256",
    "upstream_sha256",
    "fresh_content_sha256",
)


class AuthorizationRefused(Exception):
    """The confirmatory run is not authorized. Fails closed; nothing is computed."""


def build_expected(*, experiment, freeze_manifest_sha256, source_graph_sha256,
                   upstream_sha256, fresh_content_sha256) -> dict:
    """The binding block the driver computes LIVE at preflight. A valid token's
    `bindings` must equal this exactly."""
    return {
        "experiment": experiment,
        "freeze_manifest_sha256": freeze_manifest_sha256,
        "source_graph_sha256": source_graph_sha256,
        "upstream_sha256": upstream_sha256,
        "fresh_content_sha256": fresh_content_sha256,
    }


def verify(token: dict | None, expected: dict) -> dict:
    """Check a supplied authorization token against the live expected bindings.

    Returns a verdict dict; `authorized` is True only if the token exists, declares
    `authorization_version`, explicitly sets `authorize_confirmatory_oos` true, and every
    required binding matches the live value. Never raises on a bad token -- the driver decides
    what to do with `authorized=False` -- but a STRUCTURALLY malformed token is reported so the
    failure is legible.
    """
    problems = []
    if token is None:
        return {"authorized": False, "present": False,
                "problems": ["authorization artifact absent (expected during the closure "
                             "mission -- the confirmatory run is not authorized)"],
                "authorization_version": AUTHORIZATION_VERSION}

    if token.get("authorization_version") != AUTHORIZATION_VERSION:
        problems.append("authorization_version mismatch")
    if token.get("authorize_confirmatory_oos") is not True:
        problems.append("token does not explicitly authorize the confirmatory OOS run")

    bindings = token.get("bindings") or {}
    for field in REQUIRED_BINDINGS:
        if field not in bindings:
            problems.append(f"token missing binding: {field}")
        elif bindings[field] != expected[field]:
            problems.append(f"token binding {field} does not match the live value")
    extra = sorted(set(bindings) - set(REQUIRED_BINDINGS))
    if extra:
        problems.append(f"token carries unexpected bindings: {extra}")

    return {"authorized": not problems, "present": True, "problems": problems,
            "authorization_version": AUTHORIZATION_VERSION}


def version_stamp() -> dict:
    return {"authorization_version": AUTHORIZATION_VERSION,
            "artifact": AUTHORIZATION_ARTIFACT,
            "required_bindings": list(REQUIRED_BINDINGS),
            "requires_explicit_flag_and_valid_token": True,
            "token_is_content_bound": True,
            "opening_the_door_later_needs_no_code_change": True,
            "this_module_mints_nothing": True}
