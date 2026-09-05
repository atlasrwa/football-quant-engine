"""Declared broadcast scope — leagues, markets, and the line-selection rule.

Scope is **declared in a config file and version-hashed**. It is never chosen at
send time, never inferred from a model's output, and never influenced by a posted
price. The broadcaster reads this file, publishes everything in it, and has no
opinion about which fixtures are worth publishing.

THE CHANGE GATE IS FAIL-CLOSED
==============================
The scope version hash is the SHA-256 of the config file's canonical JSON, computed
per the rules in :mod:`src.persistence.hashing` (sorted keys, compact separators,
UTF-8, server-computed and never supplied by a caller).

:func:`load_scope_config` refuses to return a config whose hash is not already
recorded in the append-only scope change log. That is the mechanism enforcing
"if scope changes, log the change with a timestamp and reason **before** it takes
effect": an operator who edits the file and runs the broadcaster gets a
:class:`ScopeChangeUnrecorded` error, not a silent scope change. Recording is an
explicit, reasoned act — :func:`record_scope_change` requires a non-empty reason.

The change log is append-only. A superseded scope version is never edited or
deleted; the log is the history of what scope was in force when.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

#: Contract string this loader understands. A different contract is refused rather
#: than best-effort parsed — a misread scope declaration is a coverage bug.
SCOPE_CONFIG_CONTRACT = "forecast-broadcast-scope/v1"

#: The only supported line-selection rule: the line is the literal value declared
#: in config. Any other rule is refused, because a per-fixture or price-derived
#: line is line shopping and would make the published record incomparable.
FIXED_DECLARED_LINE = "FIXED_DECLARED_LINE"

#: Quiet-hours policy: suppression may DELAY a send, never cancel it.
DELAY_NEVER_CANCEL = "DELAY_NEVER_CANCEL"

_HOME = Path("/home/ubuntu")
DEFAULT_CONFIG_PATH = _HOME / "config" / "forecast_broadcast_scope.json"
DEFAULT_CHANGELOG_PATH = _HOME / "data" / "forecast_broadcast" / "scope_changes.jsonl"


class ScopeConfigError(ValueError):
    """The scope declaration is missing, malformed, or internally inconsistent."""


class ScopeChangeUnrecorded(ScopeConfigError):
    """The scope file's hash is not recorded in the change log.

    Raised instead of proceeding, so a scope change can never take effect before it
    has been logged with a timestamp and a reason.
    """


def _canonical_json(obj: Any) -> str:
    """Canonical JSON per :mod:`src.persistence.hashing` rules."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _sha256(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def canonical_hash(obj: Any) -> str:
    """64-char lowercase SHA-256 over an object's canonical JSON."""
    return _sha256(_canonical_json(obj))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ─────────────────────────────────────────────────────────────────────────────
# Declared scope
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class LeagueSpec:
    """One in-scope competition."""

    comp_id: str
    label: str


@dataclass(frozen=True, slots=True)
class MarketSpec:
    """One in-scope market at its declared line, with both side labels.

    Both labels are mandatory. A market that can only name one side would let a
    message surface the over without the under, which is exactly the asymmetry that
    turns a probability into an implied recommendation.
    """

    market: str
    line: Optional[float]
    over_label: str
    under_label: str

    @property
    def cell(self) -> tuple[str, Optional[float]]:
        """The ``(market, line)`` cell this spec names in the model artifact."""
        return (self.market, self.line)


@dataclass(frozen=True, slots=True)
class ConfidenceLabelRule:
    """A fixed confidence-band rule, applied identically to every fixture.

    Absent this rule (the default), no confidence label is emitted anywhere. When
    present, the bands are applied to every market of every fixture with no
    exceptions, so a label can never be a per-fixture editorial judgement.
    """

    #: Ascending probability thresholds paired with their label.
    bands: tuple[tuple[float, str], ...]

    def label_for(self, probability: float) -> str:
        """Return the band label for ``probability`` (identical rule for all)."""
        chosen = self.bands[0][1]
        for threshold, label in self.bands:
            if probability >= threshold:
                chosen = label
        return chosen


@dataclass(frozen=True, slots=True)
class ScopeConfig:
    """The full declared scope, plus the content hash identifying this version."""

    scope_version_hash: str
    horizon_hours_before_kickoff: int
    leagues: tuple[LeagueSpec, ...]
    markets: tuple[MarketSpec, ...]
    line_selection_rule: str
    confidence_label_rule: Optional[ConfidenceLabelRule]
    quiet_hours_start_hour: int
    quiet_hours_end_hour: int
    quiet_hours_policy: str
    source_path: str

    @property
    def horizon_seconds(self) -> int:
        return self.horizon_hours_before_kickoff * 3600

    @property
    def comp_ids(self) -> frozenset[str]:
        return frozenset(lg.comp_id for lg in self.leagues)

    def league_label(self, comp_id: Optional[str]) -> Optional[str]:
        for lg in self.leagues:
            if lg.comp_id == comp_id:
                return lg.label
        return None

    def is_in_scope(self, comp_id: Optional[str]) -> bool:
        """Membership is by declared competition id. Never by team, never by model."""
        return comp_id in self.comp_ids

    @property
    def emits_confidence_label(self) -> bool:
        return self.confidence_label_rule is not None

    def provenance(self) -> dict[str, Any]:
        """Compact, loggable description of the scope in force."""
        return {
            "scope_version_hash": self.scope_version_hash,
            "horizon_hours_before_kickoff": self.horizon_hours_before_kickoff,
            "leagues": [lg.comp_id for lg in self.leagues],
            "markets": [
                {"market": m.market, "line": m.line} for m in self.markets
            ],
            "line_selection_rule": self.line_selection_rule,
            "confidence_label_rule": (
                None if self.confidence_label_rule is None
                else [list(b) for b in self.confidence_label_rule.bands]
            ),
        }


# ─────────────────────────────────────────────────────────────────────────────
# Parsing / validation
# ─────────────────────────────────────────────────────────────────────────────
def _require(raw: dict, key: str) -> Any:
    if key not in raw:
        raise ScopeConfigError(f"scope config lacks required key: {key!r}")
    return raw[key]


def _parse_confidence_rule(raw: Any) -> Optional[ConfidenceLabelRule]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ScopeConfigError("confidence_label_rule must be null or an object")
    if raw.get("rule") != "FIXED_BANDS":
        raise ScopeConfigError(
            "confidence_label_rule.rule must be 'FIXED_BANDS' — a confidence label "
            "is only permitted when its rule is fixed in config and therefore "
            "applied identically to every fixture"
        )
    bands_raw = raw.get("bands")
    if not isinstance(bands_raw, list) or not bands_raw:
        raise ScopeConfigError("confidence_label_rule.bands must be a non-empty list")
    bands: list[tuple[float, str]] = []
    for entry in bands_raw:
        if (not isinstance(entry, (list, tuple))) or len(entry) != 2:
            raise ScopeConfigError(
                "each confidence band must be [threshold, label]"
            )
        bands.append((float(entry[0]), str(entry[1])))
    bands.sort(key=lambda b: b[0])
    if bands[0][0] > 0.0:
        raise ScopeConfigError(
            "confidence bands must cover every probability from 0.0 upward, so the "
            "rule applies to every fixture without exception"
        )
    return ConfidenceLabelRule(bands=tuple(bands))


def parse_scope_config(raw: dict, *, source_path: str = "<memory>") -> ScopeConfig:
    """Validate a scope declaration and compute its version hash.

    Validation is fail-closed throughout: an unrecognised contract, an unsupported
    line-selection rule, a duplicated market cell, or a market missing a side label
    raises rather than degrading to a partial scope. A partially-read scope would
    silently under-cover the declared fixture set.

    Args:
        raw: the parsed config object.
        source_path: path recorded on the result for provenance.

    Returns:
        The validated :class:`ScopeConfig`, carrying ``scope_version_hash``.

    Raises:
        ScopeConfigError: if the declaration is malformed or inconsistent.
    """
    if not isinstance(raw, dict):
        raise ScopeConfigError("scope config must be a JSON object")

    contract = raw.get("config_contract")
    if contract != SCOPE_CONFIG_CONTRACT:
        raise ScopeConfigError(
            f"unsupported config_contract {contract!r}; expected "
            f"{SCOPE_CONFIG_CONTRACT!r}"
        )

    horizon = _require(raw, "horizon_hours_before_kickoff")
    if not isinstance(horizon, int) or isinstance(horizon, bool) or horizon <= 0:
        raise ScopeConfigError(
            "horizon_hours_before_kickoff must be a positive integer number of hours"
        )

    leagues_raw = _require(raw, "leagues")
    if not isinstance(leagues_raw, list) or not leagues_raw:
        raise ScopeConfigError("leagues must be a non-empty list")
    leagues: list[LeagueSpec] = []
    seen_comp: set[str] = set()
    for entry in leagues_raw:
        if not isinstance(entry, dict):
            raise ScopeConfigError("each league must be an object")
        comp_id = str(_require(entry, "comp_id"))
        label = str(_require(entry, "label"))
        if comp_id in seen_comp:
            raise ScopeConfigError(f"duplicate league comp_id: {comp_id!r}")
        seen_comp.add(comp_id)
        leagues.append(LeagueSpec(comp_id=comp_id, label=label))

    markets_raw = _require(raw, "markets")
    if not isinstance(markets_raw, list) or not markets_raw:
        raise ScopeConfigError("markets must be a non-empty list")
    markets: list[MarketSpec] = []
    seen_cell: set[tuple[str, Optional[float]]] = set()
    for entry in markets_raw:
        if not isinstance(entry, dict):
            raise ScopeConfigError("each market must be an object")
        market = str(_require(entry, "market"))
        line_raw = entry.get("line", None)
        line = None if line_raw is None else float(line_raw)
        over_label = str(_require(entry, "over_label")).strip()
        under_label = str(_require(entry, "under_label")).strip()
        if not over_label or not under_label:
            raise ScopeConfigError(
                f"market {market!r} must declare BOTH over_label and under_label — a "
                "market that can name only one side cannot be published as a "
                "two-sided probability"
            )
        cell = (market, line)
        if cell in seen_cell:
            raise ScopeConfigError(f"duplicate market cell: {cell!r}")
        seen_cell.add(cell)
        markets.append(
            MarketSpec(
                market=market, line=line,
                over_label=over_label, under_label=under_label,
            )
        )

    rule_raw = _require(raw, "line_selection_rule")
    if not isinstance(rule_raw, dict):
        raise ScopeConfigError("line_selection_rule must be an object")
    rule = rule_raw.get("rule")
    if rule != FIXED_DECLARED_LINE:
        raise ScopeConfigError(
            f"unsupported line_selection_rule {rule!r}; only {FIXED_DECLARED_LINE!r} "
            "is supported — a per-fixture or price-derived line is line shopping"
        )

    quiet_raw = _require(raw, "quiet_hours_utc")
    if not isinstance(quiet_raw, dict):
        raise ScopeConfigError("quiet_hours_utc must be an object")
    start_hour = int(_require(quiet_raw, "start_hour"))
    end_hour = int(_require(quiet_raw, "end_hour"))
    for hour in (start_hour, end_hour):
        if not 0 <= hour <= 23:
            raise ScopeConfigError("quiet hours must be UTC hours in [0, 23]")
    policy = str(quiet_raw.get("policy", DELAY_NEVER_CANCEL))
    if policy != DELAY_NEVER_CANCEL:
        raise ScopeConfigError(
            f"unsupported quiet_hours_utc.policy {policy!r}; only "
            f"{DELAY_NEVER_CANCEL!r} is supported — quiet hours may delay a send but "
            "must never cancel it"
        )

    confidence_rule = _parse_confidence_rule(raw.get("confidence_label_rule"))

    return ScopeConfig(
        scope_version_hash=canonical_hash(raw),
        horizon_hours_before_kickoff=horizon,
        leagues=tuple(leagues),
        markets=tuple(markets),
        line_selection_rule=FIXED_DECLARED_LINE,
        confidence_label_rule=confidence_rule,
        quiet_hours_start_hour=start_hour,
        quiet_hours_end_hour=end_hour,
        quiet_hours_policy=policy,
        source_path=source_path,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Append-only scope change log
# ─────────────────────────────────────────────────────────────────────────────
def read_scope_changes(
    changelog_path: Path = DEFAULT_CHANGELOG_PATH,
) -> list[dict[str, Any]]:
    """Read the append-only scope change log oldest-first (malformed lines skipped)."""
    if not changelog_path.exists():
        return []
    out: list[dict[str, Any]] = []
    with open(changelog_path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                out.append(obj)
    return out


def recorded_scope_hashes(
    changelog_path: Path = DEFAULT_CHANGELOG_PATH,
) -> frozenset[str]:
    """Every scope version hash that has been recorded with a timestamp and reason."""
    return frozenset(
        str(rec.get("new_scope_version_hash"))
        for rec in read_scope_changes(changelog_path)
        if rec.get("new_scope_version_hash")
    )


def record_scope_change(
    config: ScopeConfig,
    reason: str,
    *,
    changelog_path: Path = DEFAULT_CHANGELOG_PATH,
    now_iso: Optional[str] = None,
) -> dict[str, Any]:
    """Append a scope change to the log, with a timestamp and a reason.

    This must happen *before* the new scope takes effect;
    :func:`load_scope_config` enforces that by refusing an unrecorded hash. The log
    is append-only — a superseded scope version is never edited or removed, so the
    record of which scope was in force when survives every later change.

    Args:
        config: the newly declared scope to bring into effect.
        reason: why scope changed. A blank reason is refused.
        changelog_path: append-only JSONL log path.
        now_iso: injectable timestamp (tests pass a frozen clock).

    Returns:
        The record appended.

    Raises:
        ScopeConfigError: if ``reason`` is blank, or the hash is already recorded.
    """
    reason = (reason or "").strip()
    if not reason:
        raise ScopeConfigError(
            "a scope change requires a reason — an unexplained change to declared "
            "scope is indistinguishable from silently reshaping coverage"
        )

    existing = read_scope_changes(changelog_path)
    if any(
        rec.get("new_scope_version_hash") == config.scope_version_hash
        for rec in existing
    ):
        raise ScopeConfigError(
            f"scope version {config.scope_version_hash[:16]} is already recorded; "
            "the log is append-only and a version is recorded exactly once"
        )

    previous = existing[-1].get("new_scope_version_hash") if existing else None
    record = {
        "changed_at_utc": now_iso or _now_iso(),
        "previous_scope_version_hash": previous,
        "new_scope_version_hash": config.scope_version_hash,
        "reason": reason,
        "scope": config.provenance(),
        "source_path": config.source_path,
    }
    changelog_path.parent.mkdir(parents=True, exist_ok=True)
    with open(changelog_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    return record


# ─────────────────────────────────────────────────────────────────────────────
# Loading
# ─────────────────────────────────────────────────────────────────────────────
def load_scope_config(
    config_path: Path = DEFAULT_CONFIG_PATH,
    *,
    changelog_path: Path = DEFAULT_CHANGELOG_PATH,
    require_recorded_change: bool = True,
) -> ScopeConfig:
    """Load and validate the declared scope, enforcing the change-log gate.

    Args:
        config_path: the scope declaration.
        changelog_path: the append-only scope change log.
        require_recorded_change: when True (the default, and the only setting used
            in production) a scope version whose hash is not in the change log is
            refused. Setting this False is for inspecting a candidate scope; it must
            not be used on a send path.

    Returns:
        The validated :class:`ScopeConfig`.

    Raises:
        ScopeConfigError: the declaration is missing or malformed.
        ScopeChangeUnrecorded: the declaration is valid but its version has not been
            recorded with a timestamp and reason.
    """
    if not config_path.exists():
        raise ScopeConfigError(f"scope config not found: {config_path}")
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ScopeConfigError(f"scope config is not valid JSON: {exc}") from exc

    config = parse_scope_config(raw, source_path=str(config_path))

    if require_recorded_change:
        recorded = recorded_scope_hashes(changelog_path)
        if config.scope_version_hash not in recorded:
            raise ScopeChangeUnrecorded(
                f"scope version {config.scope_version_hash} is not recorded in "
                f"{changelog_path}. Scope changes must be logged with a timestamp "
                "and a reason BEFORE they take effect. Record it with:\n"
                "  python3 scripts/forecast_broadcast.py --record-scope-change "
                '--reason "<why scope changed>"'
            )
    return config
