"""The 30-day evaluation window: set it up now so it is clean when it arrives.

Nothing this engine has published counts as evidence yet. Every forecast generated
before the corpus fix was built on a stale corpus, which means it is diagnostic
material and nothing more. Mixing those into a calibration figure would produce a
number that describes a bug rather than a model.

So the record starts at an explicit marker. :func:`open_window` records the first
post-fix forecast — its commitment hash, its generation time — into an
**append-once** epoch file. Everything generated before that instant is excluded
from the evaluation by :meth:`EvaluationWindow.includes`, and the exclusion is
structural rather than a filter someone has to remember to apply.

Three deliberate refusals in this module, all of which exist to stop the window
being quietly reinterpreted once partial results are visible:

* :func:`open_window` refuses to overwrite an existing epoch. Re-marking the start
  after seeing a few days of results would make the window meaningless.
* :meth:`EvaluationWindow.with_days` refuses to change the length of an open
  window. The window is 30 days because that was decided in advance, not because
  30 days is where the numbers look best.
* :func:`window_report` refuses to produce calibration figures before the window
  closes, and says how long is left instead.

**Most cells will be underpowered at 30 days, and that is the expected finding.**
The live minimum-sample gate suppresses any calibration figure below roughly 200
settled observations per cell, and a month of four leagues cannot deliver that per
line. The report therefore leads with the power arithmetic — how many cells cleared
the gate, and what the shortfall is — so a thin number is never mistaken for a
verdict.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

from src.research.prediction_engine.scope import (
    MIN_SETTLED_FOR_CALIBRATION,
    insufficient_sample_notice,
)

WINDOW_CONTRACT = "forecast-evaluation-window/v1"
SETTLED_CONTRACT = "forecast-settled-observation/v1"

#: Preregistered window length. Decided before any result was seen.
WINDOW_DAYS = 30

DEFAULT_WINDOW_PATH = "data/forecast_broadcast/evaluation_window.json"
DEFAULT_SETTLED_PATH = "data/forecast_broadcast/settled_forecasts.jsonl"

_RESERVED_BASENAMES = ("pilotC_", "manual_", "scanner_")


class EvaluationWindowError(RuntimeError):
    """Raised on any attempt to reopen, shorten, or peek at the window early."""


def _guard_path(path: str | Path) -> Path:
    """Refuse to point this at another pipeline's preserved record."""
    resolved = Path(path)
    base = resolved.name
    for reserved in _RESERVED_BASENAMES:
        if reserved in base:
            raise ValueError(
                f"refusing to use a reserved ledger basename {base!r}: Pilot C, the "
                "manual predictor and the scanner ledgers are preserved records and "
                "must stay structurally isolated"
            )
    if base in ("commitments.jsonl", "predictions.jsonl", "run_log.jsonl"):
        raise ValueError(f"refusing to use the bare Pipeline A ledger {base!r}")
    return resolved


# ─────────────────────────────────────────────────────────────────────────────
# The window
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class EvaluationWindow:
    """An opened evaluation window, pinned to its first post-fix forecast."""

    contract: str
    epoch_commitment_hash: str
    epoch_generated_at_utc: str
    epoch_unix: int
    window_days: int
    model_version: str
    corpus_content_hash: Optional[str]
    note: str

    @property
    def closes_at_unix(self) -> int:
        return self.epoch_unix + self.window_days * 86400

    @property
    def closes_at_utc(self) -> str:
        return datetime.fromtimestamp(self.closes_at_unix, tz=timezone.utc).isoformat()

    def includes(self, generated_at_unix: float) -> bool:
        """Whether a forecast belongs to this window's record.

        Forecasts generated before the epoch are excluded unconditionally: they
        were produced on the stale corpus and are diagnostic only.
        """
        return self.epoch_unix <= float(generated_at_unix) <= self.closes_at_unix

    def is_closed(self, now_unix: float) -> bool:
        return float(now_unix) >= self.closes_at_unix

    def days_remaining(self, now_unix: float) -> float:
        return max(0.0, (self.closes_at_unix - float(now_unix)) / 86400.0)

    def with_days(self, days: int) -> "EvaluationWindow":
        """Refuse to revise the window length after opening."""
        if days != self.window_days:
            raise EvaluationWindowError(
                f"refusing to change an open evaluation window from "
                f"{self.window_days} to {days} days. The length was preregistered; "
                "revising it after seeing partial results would invalidate the "
                "window."
            )
        return self

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": self.contract,
            "epoch_commitment_hash": self.epoch_commitment_hash,
            "epoch_generated_at_utc": self.epoch_generated_at_utc,
            "epoch_unix": self.epoch_unix,
            "window_days": self.window_days,
            "closes_at_unix": self.closes_at_unix,
            "closes_at_utc": self.closes_at_utc,
            "model_version": self.model_version,
            "corpus_content_hash": self.corpus_content_hash,
            "note": self.note,
        }


def open_window(
    *,
    commitment_hash: str,
    generated_at_utc: str,
    generated_at_unix: int,
    model_version: str,
    corpus_content_hash: Optional[str] = None,
    window_days: int = WINDOW_DAYS,
    path: str | Path = DEFAULT_WINDOW_PATH,
) -> EvaluationWindow:
    """Mark the first post-fix forecast. Append-once; never overwritten.

    Idempotent for the *same* commitment hash so a retried run cannot fail, but
    any attempt to move the epoch to a different forecast is refused.
    """
    resolved = _guard_path(path)
    if window_days < 1:
        raise ValueError("window_days must be at least 1")

    existing = load_window(resolved)
    if existing is not None:
        if existing.epoch_commitment_hash == commitment_hash:
            return existing
        raise EvaluationWindowError(
            "an evaluation window is already open, pinned to commitment "
            f"{existing.epoch_commitment_hash} at {existing.epoch_generated_at_utc}. "
            "Refusing to re-mark the epoch: moving the start after publication "
            "began would let the window be chosen to suit the results."
        )

    window = EvaluationWindow(
        contract=WINDOW_CONTRACT,
        epoch_commitment_hash=commitment_hash,
        epoch_generated_at_utc=generated_at_utc,
        epoch_unix=int(generated_at_unix),
        window_days=window_days,
        model_version=model_version,
        corpus_content_hash=corpus_content_hash,
        note=(
            "First forecast published on the corrected corpus. Everything generated "
            "before this instant was built on the stale corpus and is excluded from "
            "any evaluation of this engine."
        ),
    )
    resolved.parent.mkdir(parents=True, exist_ok=True)
    resolved.write_text(json.dumps(window.to_dict(), indent=2, sort_keys=True) + "\n")
    return window


def load_window(path: str | Path = DEFAULT_WINDOW_PATH) -> Optional[EvaluationWindow]:
    resolved = Path(path)
    if not resolved.exists():
        return None
    payload = json.loads(resolved.read_text())
    if payload.get("contract") != WINDOW_CONTRACT:
        raise EvaluationWindowError(
            f"unsupported evaluation window contract {payload.get('contract')!r}"
        )
    return EvaluationWindow(
        contract=payload["contract"],
        epoch_commitment_hash=payload["epoch_commitment_hash"],
        epoch_generated_at_utc=payload["epoch_generated_at_utc"],
        epoch_unix=int(payload["epoch_unix"]),
        window_days=int(payload["window_days"]),
        model_version=payload.get("model_version", ""),
        corpus_content_hash=payload.get("corpus_content_hash"),
        note=payload.get("note", ""),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Settled observations
# ─────────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True, slots=True)
class SettledObservation:
    """One settled published line: what was stated and what happened."""

    fixture_id: str
    league: str
    family: str
    line: Optional[float]
    p_over: float
    outcome: float
    commitment_hash: str
    generated_at_unix: int
    kickoff_unix: int

    def cell(self) -> tuple[str, str, Optional[float]]:
        return (self.league, self.family, self.line)

    def to_dict(self) -> dict[str, object]:
        return {
            "contract": SETTLED_CONTRACT,
            "fixture_id": self.fixture_id,
            "league": self.league,
            "family": self.family,
            "line": self.line,
            "p_over": self.p_over,
            "outcome": self.outcome,
            "commitment_hash": self.commitment_hash,
            "generated_at_unix": self.generated_at_unix,
            "kickoff_unix": self.kickoff_unix,
        }


def record_settled(
    observation: SettledObservation,
    *,
    path: str | Path = DEFAULT_SETTLED_PATH,
) -> None:
    """Append one settled observation. Hit or miss, always recorded."""
    resolved = _guard_path(path)
    resolved.parent.mkdir(parents=True, exist_ok=True)
    with resolved.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(observation.to_dict(), sort_keys=True) + "\n")


def load_settled(
    path: str | Path = DEFAULT_SETTLED_PATH,
) -> list[SettledObservation]:
    resolved = Path(path)
    if not resolved.exists():
        return []
    observations: list[SettledObservation] = []
    for raw in resolved.read_text().splitlines():
        line = raw.strip()
        if not line:
            continue
        payload = json.loads(line)
        observations.append(
            SettledObservation(
                fixture_id=str(payload["fixture_id"]),
                league=str(payload["league"]),
                family=str(payload["family"]),
                line=(None if payload.get("line") is None else float(payload["line"])),
                p_over=float(payload["p_over"]),
                outcome=float(payload["outcome"]),
                commitment_hash=str(payload.get("commitment_hash", "")),
                generated_at_unix=int(payload["generated_at_unix"]),
                kickoff_unix=int(payload.get("kickoff_unix", 0)),
            )
        )
    return observations


def settled_counts(
    observations: Iterable[SettledObservation],
    window: Optional[EvaluationWindow] = None,
) -> dict[tuple[str, str, Optional[float]], int]:
    """Settled count per cell, with pre-epoch observations excluded.

    The count is the thing to look at first and is surfaced everywhere, because it
    is what decides whether any figure beside it means anything.
    """
    counts: dict[tuple[str, str, Optional[float]], int] = {}
    for observation in observations:
        if window is not None and not window.includes(observation.generated_at_unix):
            continue
        key = observation.cell()
        counts[key] = counts.get(key, 0) + 1
    return counts


# ─────────────────────────────────────────────────────────────────────────────
# The report
# ─────────────────────────────────────────────────────────────────────────────
def _bin_members(
    probabilities: Sequence[float],
    outcomes: Sequence[float],
    index: int,
    bins: int,
) -> list[tuple[float, float]]:
    """Members of one reliability bin. The last bin is closed on both ends."""
    low = index / bins
    high = (index + 1) / bins
    if index == bins - 1:
        return [(p, y) for p, y in zip(probabilities, outcomes) if low <= p <= high]
    return [(p, y) for p, y in zip(probabilities, outcomes) if low <= p < high]


def _ece(probabilities: Sequence[float], outcomes: Sequence[float], bins: int) -> float:
    if not probabilities:
        return float("nan")
    total = len(probabilities)
    error = 0.0
    for index in range(bins):
        selected = _bin_members(probabilities, outcomes, index, bins)
        if not selected:
            continue
        mean_p = sum(p for p, _ in selected) / len(selected)
        rate = sum(y for _, y in selected) / len(selected)
        error += (len(selected) / total) * abs(mean_p - rate)
    return error


def _reliability(
    probabilities: Sequence[float], outcomes: Sequence[float], bins: int
) -> list[dict[str, object]]:
    curve: list[dict[str, object]] = []
    for index in range(bins):
        selected = _bin_members(probabilities, outcomes, index, bins)
        curve.append(
            {
                "bin_lower": round(index / bins, 4),
                "bin_upper": round((index + 1) / bins, 4),
                "n": len(selected),
                "mean_predicted": (
                    round(sum(p for p, _ in selected) / len(selected), 6)
                    if selected
                    else None
                ),
                "observed_rate": (
                    round(sum(y for _, y in selected) / len(selected), 6)
                    if selected
                    else None
                ),
            }
        )
    return curve


def window_report(
    *,
    now_unix: float,
    window: Optional[EvaluationWindow] = None,
    observations: Optional[Sequence[SettledObservation]] = None,
    window_path: str | Path = DEFAULT_WINDOW_PATH,
    settled_path: str | Path = DEFAULT_SETTLED_PATH,
    minimum: int = MIN_SETTLED_FOR_CALIBRATION,
    bins: int = 10,
    allow_open_window: bool = False,
) -> dict[str, object]:
    """Report the window. Refuses to publish figures before the window closes.

    ``allow_open_window`` exists only so an operator can check *sample counts*
    mid-window; even then no calibration figure is computed, because the point of
    a preregistered window is that the numbers are not consulted while there is
    still time to change what is published.
    """
    window = window or load_window(window_path)
    if window is None:
        return {
            "status": "not_opened",
            "detail": (
                "no evaluation window has been opened; the first forecast published "
                "on the corrected corpus will open it"
            ),
            "window_days": WINDOW_DAYS,
            "minimum_settled_for_calibration": minimum,
        }

    observations = (
        list(observations) if observations is not None else load_settled(settled_path)
    )
    in_window = [
        observation
        for observation in observations
        if window.includes(observation.generated_at_unix)
    ]
    excluded = len(observations) - len(in_window)
    counts = settled_counts(in_window, window)
    closed = window.is_closed(now_unix)

    header: dict[str, object] = {
        "window": window.to_dict(),
        "closed": closed,
        "days_remaining": round(window.days_remaining(now_unix), 2),
        "n_settled_in_window": len(in_window),
        "n_excluded_pre_epoch": excluded,
        "exclusion_rule": (
            "forecasts generated before the epoch were produced on the stale "
            "corpus and are diagnostic only"
        ),
        "minimum_settled_for_calibration": minimum,
        "settled_per_cell": {
            f"{league}|{family}|{line}": count
            for (league, family, line), count in sorted(
                counts.items(), key=lambda item: str(item[0])
            )
        },
        "cells_at_or_above_gate": sum(
            1 for count in counts.values() if count >= minimum
        ),
        "cells_below_gate": sum(1 for count in counts.values() if count < minimum),
    }

    if not closed and not allow_open_window:
        return {
            "status": "window_open",
            "detail": (
                f"the evaluation window closes at {window.closes_at_utc}, in "
                f"{window.days_remaining(now_unix):.1f} days. No calibration figure "
                "is produced before then: evaluating a preregistered window early "
                "is how a window stops being preregistered."
            ),
            **header,
        }
    if not closed:
        return {
            "status": "window_open_counts_only",
            "detail": (
                "sample counts only. No calibration figure is computed while the "
                "window is open."
            ),
            **header,
        }

    cells: list[dict[str, object]] = []
    by_cell: dict[tuple[str, str, Optional[float]], list[SettledObservation]] = {}
    for observation in in_window:
        by_cell.setdefault(observation.cell(), []).append(observation)

    for key in sorted(by_cell, key=str):
        league, family, line = key
        records = by_cell[key]
        probabilities = [record.p_over for record in records]
        outcomes = [record.outcome for record in records]
        n_settled = len(records)
        entry: dict[str, object] = {
            "league": league,
            "family": family,
            "line": line,
            "n_settled": n_settled,
            "gate_met": n_settled >= minimum,
            "skill_claim_blocked": True,
        }
        if n_settled < minimum:
            entry["calibration"] = None
            entry["reliability_curve"] = []
            entry["gate_notice"] = insufficient_sample_notice(n_settled, minimum)
            entry["shortfall"] = minimum - n_settled
        else:
            entry["calibration"] = {
                "ece": round(_ece(probabilities, outcomes, bins), 6),
                "mean_predicted": round(sum(probabilities) / n_settled, 6),
                "observed_rate": round(sum(outcomes) / n_settled, 6),
                "brier": round(
                    sum((p - y) ** 2 for p, y in zip(probabilities, outcomes))
                    / n_settled,
                    6,
                ),
            }
            entry["reliability_curve"] = _reliability(probabilities, outcomes, bins)
        cells.append(entry)

    powered = [cell for cell in cells if cell["gate_met"]]
    return {
        "status": "closed",
        **header,
        "cells": cells,
        "power_summary": {
            "n_cells": len(cells),
            "n_cells_with_enough_settled": len(powered),
            "n_cells_underpowered": len(cells) - len(powered),
            "verdict_available": bool(powered),
            "expectation": (
                "most cells were expected to be underpowered at 30 days. A cell "
                f"needs about {minimum} settled observations before an ECE means "
                "anything, and a month of a handful of leagues does not deliver "
                "that per line."
            ),
            "honest_reading": (
                "this is a sample-size report first and a calibration report second"
                if len(powered) < len(cells)
                else "every cell cleared the minimum-sample gate"
            ),
        },
    }


def projected_power(
    *,
    n_leagues: int,
    fixtures_per_league_per_month: int,
    n_cells_per_fixture: int,
    minimum: int = MIN_SETTLED_FOR_CALIBRATION,
    window_days: int = WINDOW_DAYS,
) -> dict[str, object]:
    """State up front how underpowered the window will be, before it opens.

    Worth computing in advance precisely because the answer is discouraging: if a
    month cannot fill a single cell, that is better known now than discovered at
    the end and rationalised.
    """
    fixtures = n_leagues * fixtures_per_league_per_month * (window_days / 30.0)
    per_cell = fixtures / max(1, n_leagues)  # one cell is one league x market x line
    return {
        "window_days": window_days,
        "n_leagues": n_leagues,
        "expected_fixtures_in_window": round(fixtures, 1),
        "expected_settled_per_cell": round(per_cell, 1),
        "minimum_settled_for_calibration": minimum,
        "expected_cells_clearing_gate": (
            "all" if per_cell >= minimum else "none"
        ),
        "shortfall_per_cell": max(0, int(round(minimum - per_cell))),
        "months_to_fill_one_cell": (
            round(minimum / per_cell, 1) if per_cell > 0 else None
        ),
        "reading": (
            "per-league-per-line calibration is not reachable in one 30-day window; "
            "the window's honest output is a sample-count report plus per-market "
            "figures pooled across lines where that is enough"
            if per_cell < minimum
            else "cells are expected to clear the gate"
        ),
    }
