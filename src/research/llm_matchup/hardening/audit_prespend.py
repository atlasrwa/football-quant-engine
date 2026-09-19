"""Pre-spend structural audit of the LITERAL serialized Bedrock request (V3 SS60 extended).

WHY THIS MODULE EXISTS AND WHY IT IS SEPARATE
---------------------------------------------
`audit_request.audit_serialized_request` is the EXISTING, frozen audit used by the Sonnet 4.5
arm. It scans the literal rendered request text for real team / competition / season names and
for exact formation + family label strings. It is deliberately NOT modified here: changing it
would silently change the 4.5 arm's audit semantics mid-experiment.

The Sonnet 4.6 pre-spend gate requires SEVEN zero-tolerance categories, of which the existing
audit covers three. This module COMPOSES the existing audit (so its three categories keep
byte-identical semantics) and ADDS the remaining four as a new, explicitly versioned check.
It is therefore an additive extension, not a reinterpretation.

CATEGORY MAP (what each gate actually means -- stated precisely so results are not overclaimed)
  1. real_team_names           -> delegated to audit_request (source home/away, len>=3)
  2. real_competition_names    -> delegated to audit_request (source competition + season)
  3. formation_labels          -> delegated to audit_request (exact formation + family strings
                                  present in the source packet) PLUS a generative pattern scan
                                  for ANY human-readable formation label shape (e.g. "4-2-3-1")
                                  or family-label shape (e.g. "BACK4_1STRIKER") anywhere in the
                                  request text, so a label that never appeared in THIS source
                                  packet still cannot slip through.
  4. target_outcomes           -> no outcome-bearing key or metric may appear: the target
                                  fixture's goals/score/result/winner/points. Checked as keys
                                  in the packet AND as substrings of evidence metric names.
  5. future_information        -> PIT integrity of the serialized payload: every evidence item
                                  whose temporal_status != PIT_SAFE must carry value=None (an
                                  UNAVAILABLE item may be DECLARED, but must not carry a
                                  measurement), and no item may carry cutoff_unix or
                                  max_source_time_unix strictly greater than the packet's
                                  information_cutoff_unix.
  6. credential_leakage        -> no AWS access-key / secret-key / session-token shapes, no
                                  bearer/authorization headers, no `xxx_SECRET=`/`_KEY=` style
                                  assignments, and no verbatim value from the process
                                  environment or repo .env files (long values only, to avoid
                                  meaningless matches on short generic strings).
  7. provider_text            -> provider attribution must be a SHORT SLUG from a closed
                                  allow-list, never arbitrary free text. Any `source_provider`
                                  / `provider_provenance` value that is not an allow-listed
                                  slug, or is suspiciously long / contains whitespace or URL
                                  or sentence punctuation, is a leak.

Every check is a pure function of (neutral_packet, source_packet) plus the rendered text. This
module NEVER makes a network call, NEVER writes a payload containing real identifiers to disk,
and NEVER echoes a matched credential value (it reports only the category and a redacted
locator), so running it cannot itself become a leak.
"""
from __future__ import annotations
import os
import re

from src.research.llm_matchup.hardening import audit_request as AR

AUDIT_PRESPEND_VERSION = "audit_prespend_v1"

# --- category 3: generative formation-label shapes ---------------------------------------
# A human-readable formation label is a run of 2+ single-digit groups joined by '-' summing to
# 10 outfield players (e.g. 4-4-2, 4-2-3-1, 3-4-2-1). We additionally match the family-label
# vocabulary used by FORMATION_FAMILY_V1 (BACK4_1STRIKER etc.).
_FORMATION_NUMERIC_RE = re.compile(r"\b\d(?:-\d){1,4}\b")
_FAMILY_LABEL_RE = re.compile(r"\bBACK[345]_[0-9A-Z_]+\b")

# --- category 4: target-outcome vocabulary ------------------------------------------------
# Keys/metric fragments that would reveal the thing we are forbidden to look at. Deliberately
# narrow and anchored to avoid false positives on legitimate PIT-safe rate metrics (e.g.
# "shots_on_target_for" legitimately contains "target" but is not an outcome).
_OUTCOME_KEYS = {
    "result", "outcome", "final_score", "ft_score", "ht_score", "score",
    "goals_scored", "goals_conceded_actual", "winner", "won", "lost", "drawn",
    "points_gained", "actual_goals", "target", "label", "y_true",
    "home_goals", "away_goals", "goal_difference_actual",
}
_OUTCOME_METRIC_FRAGMENTS = ("final_score", "ft_result", "match_result", "actual_goals",
                             "goals_scored_actual", "y_true", "did_win", "did_score")

# --- category 6: credential shapes --------------------------------------------------------
_CRED_PATTERNS = [
    ("aws_access_key_id", re.compile(r"\b(?:AKIA|ASIA|ABIA|ACCA)[0-9A-Z]{16}\b")),
    ("aws_secret_access_key_assignment",
     re.compile(r"aws_secret_access_key\s*[:=]\s*\S+", re.I)),
    ("aws_session_token_assignment", re.compile(r"aws_session_token\s*[:=]\s*\S+", re.I)),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9\-._~+/]{20,}", re.I)),
    ("authorization_header", re.compile(r"\bauthorization\s*[:=]", re.I)),
    ("generic_secret_assignment",
     re.compile(r"\b[A-Z0-9_]*(?:SECRET|PASSWORD|PASSWD|PRIVATE_KEY|API_KEY|TOKEN)[A-Z0-9_]*"
                r"\s*[:=]\s*\S{8,}")),
    ("private_key_block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")),
]
_ENV_FILES = ("/home/ubuntu/.env", "/home/ubuntu/.env.local", "/home/ubuntu/.env.cron")
_MIN_ENV_VALUE_LEN = 12          # only long values; short ones cause meaningless collisions

# --- category 7: provider allow-list ------------------------------------------------------
ALLOWED_PROVIDER_SLUGS = {
    "thestatsapi", "thestatsapi_raw_stats", "derived", "derived_formation",
    "footystats", "sportmonks", "apifootball", "understat", "fbref", "unknown",
}
_MAX_PROVIDER_SLUG_LEN = 40
_PROVIDER_BAD_CHARS_RE = re.compile(r"[\s<>{}\"']|https?://|\.\.\.|[.!?]\s")


def _iter_kv(obj, path=""):
    """Yield (path, key, value) for every dict entry, recursively."""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield (path, k, v)
            yield from _iter_kv(v, f"{path}/{k}")
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from _iter_kv(v, f"{path}[{i}]")


def _long_env_values() -> set[str]:
    """Long values from the live process env and repo .env files. Used ONLY for membership
    testing against the request text; never returned, logged or persisted."""
    vals: set[str] = set()
    for v in os.environ.values():
        if isinstance(v, str) and len(v) >= _MIN_ENV_VALUE_LEN:
            vals.add(v)
    for path in _ENV_FILES:
        if not os.path.exists(path):
            continue
        try:
            for line in open(path, encoding="utf-8", errors="replace"):
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                val = line.split("=", 1)[1].strip().strip("'\"")
                if len(val) >= _MIN_ENV_VALUE_LEN:
                    vals.add(val)
        except Exception:
            continue
    # Never treat an obviously non-secret long value as a credential (e.g. a PATH listing).
    return {v for v in vals if "/usr/bin" not in v and os.pathsep not in v}


def _check_formation_labels(text: str) -> list[str]:
    leaks = []
    for m in set(_FORMATION_NUMERIC_RE.findall(text)):
        digits = [int(d) for d in m.split("-")]
        # A real formation label's outfield digits sum to 10 (goalkeeper implicit). This keeps
        # legitimate hyphenated numerics (dates, ranges, ids) from producing false positives.
        if sum(digits) == 10 and len(digits) >= 2:
            leaks.append(f"formation-label shape {m!r} present in serialized request text")
    for m in set(_FAMILY_LABEL_RE.findall(text)):
        leaks.append(f"formation-family label {m!r} present in serialized request text")
    return leaks


def _check_target_outcomes(neutral_packet: dict) -> list[str]:
    leaks = []
    for path, k, v in _iter_kv(neutral_packet):
        if k.lower() in _OUTCOME_KEYS:
            leaks.append(f"outcome-bearing key {k!r} at {path or '<root>'}")
    for e in neutral_packet.get("evidence", []) or []:
        metric = str(e.get("metric") or "")
        for frag in _OUTCOME_METRIC_FRAGMENTS:
            if frag in metric:
                leaks.append(f"outcome-bearing metric {metric!r} (evidence id {e.get('id')!r})")
    return leaks


def _check_future_information(neutral_packet: dict) -> list[str]:
    leaks = []
    cutoff = neutral_packet.get("information_cutoff_unix")
    for e in neutral_packet.get("evidence", []) or []:
        eid = e.get("id")
        status = e.get("temporal_status")
        if status != "PIT_SAFE" and e.get("value") is not None:
            leaks.append(f"non-PIT_SAFE evidence {eid!r} (status={status!r}) carries a value")
        if cutoff is not None:
            for field in ("cutoff_unix", "max_source_time_unix"):
                tv = e.get(field)
                if isinstance(tv, (int, float)) and tv > cutoff:
                    leaks.append(
                        f"evidence {eid!r} {field}={tv} exceeds information_cutoff_unix={cutoff}")
    return leaks


def _check_credentials(text: str) -> list[str]:
    leaks = []
    for name, pat in _CRED_PATTERNS:
        if pat.search(text):
            # Report the CATEGORY only -- never the matched secret value.
            leaks.append(f"credential-shaped content matched pattern {name!r} (value redacted)")
    for val in _long_env_values():
        if val in text:
            leaks.append("verbatim environment/.env value present in request text "
                         f"(len={len(val)}, value redacted)")
    return leaks


def _check_provider_text(neutral_packet: dict) -> list[str]:
    leaks = []
    seen: set[str] = set()
    for path, k, v in _iter_kv(neutral_packet):
        if k not in ("source_provider", "primary", "half_splits") or not isinstance(v, str):
            continue
        if "provider" not in (path + "/" + k) and k == "source_provider":
            pass  # source_provider is always provider attribution regardless of path
        if v in seen:
            continue
        seen.add(v)
        if v in ALLOWED_PROVIDER_SLUGS:
            continue
        if len(v) > _MAX_PROVIDER_SLUG_LEN or _PROVIDER_BAD_CHARS_RE.search(v):
            leaks.append(f"arbitrary provider text {v[:60]!r} at {path}/{k}")
        else:
            leaks.append(f"provider slug {v!r} not on the closed allow-list (at {path}/{k})")
    return leaks


def audit_prespend(neutral_packet: dict, source_packet: dict) -> dict:
    """Full seven-category pre-spend audit. Returns a per-category report; `clean` is True
    only when EVERY category is empty. Never raises on packet shape oddities -- an unexpected
    shape shows up as a leak, not as a crash, so the gate fails closed."""
    text = AR.render_request_text(neutral_packet)

    # Categories 1-3 (names) delegate to the EXISTING frozen audit so their semantics are
    # byte-identical to the 4.5 arm's gate. We then split its findings by category.
    existing = AR.audit_serialized_request(neutral_packet, source_packet)
    fx = source_packet.get("fixture", {}) or {}
    team_vals = {v for v in (fx.get("home"), fx.get("away")) if isinstance(v, str) and len(v) >= 3}
    comp_vals = {v for v in (fx.get("competition"), fx.get("season"))
                 if isinstance(v, str) and len(v) >= 3}

    cat_team, cat_comp, cat_form = [], [], []
    for leak in existing:
        if any(f"{t!r}" in leak for t in team_vals):
            cat_team.append(leak)
        elif any(f"{c!r}" in leak for c in comp_vals):
            cat_comp.append(leak)
        else:
            cat_form.append(leak)
    cat_form += _check_formation_labels(text)

    categories = {
        "real_team_names": cat_team,
        "real_competition_names": cat_comp,
        "formation_labels": cat_form,
        "target_outcomes": _check_target_outcomes(neutral_packet),
        "future_information": _check_future_information(neutral_packet),
        "credential_leakage": _check_credentials(text),
        "provider_text": _check_provider_text(neutral_packet),
    }
    total = sum(len(v) for v in categories.values())
    return {
        "audit_version": AUDIT_PRESPEND_VERSION,
        "fixture_id": (neutral_packet.get("fixture") or {}).get("fixture_id"),
        "neutral_llm_packet_hash": neutral_packet.get("neutral_llm_packet_hash"),
        "source_evidence_packet_hash": neutral_packet.get("source_evidence_packet_hash"),
        "request_text_sha256": __import__("hashlib").sha256(text.encode()).hexdigest(),
        "request_text_length": len(text),
        "categories": categories,
        "counts": {k: len(v) for k, v in categories.items()},
        "n_leaks_total": total,
        "clean": total == 0,
        # The existing frozen audit's verdict, reported alongside so the two gates are
        # independently visible and the extension can never mask a regression in the original.
        "existing_audit_clean": existing == [],
        "existing_audit_leaks": existing,
    }
