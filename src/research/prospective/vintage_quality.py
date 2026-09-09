"""Vintage-quality classification for prospective captures.

The four research vintages (EARLY~T-24h, MID~T-6h, LATE~T-60m, FINAL~T-15m)
are SCHEDULING TARGETS, not fabricated timestamps. A real capture happens at
some actual retrieval time; this module classifies HOW WELL that retrieval hit
its target window and records the true age, so a T-3h observation is never
silently relabelled a T-6h (MID) observation without retaining its real age.

Classification is deterministic and tolerance-based. Tolerances are declared
constants derived from the target spacing, NOT tuned on any model performance.

Nothing here fabricates ``observed_at``: callers pass the actual retrieval time
and the fixture kickoff, and we compute ``seconds_to_kickoff`` and a quality
label.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from src.research.prospective.vintages import ProspectiveVintage


class VintageQuality(str, Enum):
    """How well an actual capture hit its target window."""

    ON_TARGET = "ON_TARGET"      # within the tight tolerance of the target
    NEAR_TARGET = "NEAR_TARGET"  # within the wide tolerance
    OFF_TARGET = "OFF_TARGET"    # captured, but far from target (still retained)
    MISSED = "MISSED"            # no capture in the window (represented explicitly)


@dataclass(frozen=True)
class VintageTolerance:
    """Deterministic tolerances (seconds) around a vintage target.

    ``on_target`` is the tight band; ``near_target`` the wider band. Both are
    fixed in advance. A capture inside ``on_target`` => ON_TARGET; inside
    ``near_target`` => NEAR_TARGET; otherwise (but still pre-kickoff and after
    the previous target) => OFF_TARGET.
    """

    on_target: float
    near_target: float


#: Fixed, pre-registered tolerances. Chosen from target spacing, not tuned:
#: - EARLY (T-24h): loose, since 24h captures are naturally sparse.
#: - MID (T-6h): moderate.
#: - LATE (T-60m): tight, this is the pre-lineup anchor.
#: - FINAL (T-15m): very tight, the last pre-kickoff anchor.
DEFAULT_TOLERANCES: dict[ProspectiveVintage, VintageTolerance] = {
    ProspectiveVintage.EARLY: VintageTolerance(on_target=3 * 3600, near_target=8 * 3600),
    ProspectiveVintage.MID: VintageTolerance(on_target=90 * 60, near_target=3 * 3600),
    ProspectiveVintage.LATE: VintageTolerance(on_target=20 * 60, near_target=45 * 60),
    ProspectiveVintage.FINAL: VintageTolerance(on_target=10 * 60, near_target=20 * 60),
}


@dataclass(frozen=True)
class VintageObservationQuality:
    """Quality metadata for one actual capture against one target vintage.

    Attributes:
        vintage: The target vintage this capture is being assessed against.
        observed_at: The ACTUAL retrieval time (unix). Never fabricated.
        kickoff_ts: Fixture kickoff (unix) known at assessment time.
        seconds_to_kickoff: kickoff_ts - observed_at (>0 pre-kickoff).
        target_seconds_to_kickoff: The vintage's target offset.
        error_seconds: |seconds_to_kickoff - target| (how far off target).
        quality: ON_TARGET / NEAR_TARGET / OFF_TARGET.
        post_kickoff: True if the capture is at/after kickoff (never valid for
            a pre-kickoff vintage).
    """

    vintage: ProspectiveVintage
    observed_at: float
    kickoff_ts: float
    seconds_to_kickoff: float
    target_seconds_to_kickoff: int
    error_seconds: float
    quality: VintageQuality
    post_kickoff: bool

    def to_dict(self) -> dict:
        return {
            "vintage": self.vintage.value,
            "observed_at": self.observed_at,
            "kickoff_ts": self.kickoff_ts,
            "seconds_to_kickoff": self.seconds_to_kickoff,
            "target_seconds_to_kickoff": self.target_seconds_to_kickoff,
            "error_seconds": self.error_seconds,
            "quality": self.quality.value,
            "post_kickoff": self.post_kickoff,
        }


def classify_capture(
    *,
    vintage: ProspectiveVintage,
    observed_at: float,
    kickoff_ts: float,
    tolerances: Optional[dict[ProspectiveVintage, VintageTolerance]] = None,
) -> VintageObservationQuality:
    """Classify an actual capture against a target vintage.

    Deterministic: the actual ``observed_at`` and ``kickoff_ts`` fully
    determine the label. A post-kickoff capture is flagged and classified
    OFF_TARGET (it is retained for provenance but is not a valid pre-kickoff
    vintage observation).
    """
    tol = (tolerances or DEFAULT_TOLERANCES)[vintage]
    seconds_to_kickoff = kickoff_ts - observed_at
    target = vintage.offset_seconds
    error = abs(seconds_to_kickoff - target)
    post_kickoff = seconds_to_kickoff <= 0

    if post_kickoff:
        quality = VintageQuality.OFF_TARGET
    elif error <= tol.on_target:
        quality = VintageQuality.ON_TARGET
    elif error <= tol.near_target:
        quality = VintageQuality.NEAR_TARGET
    else:
        quality = VintageQuality.OFF_TARGET

    return VintageObservationQuality(
        vintage=vintage,
        observed_at=float(observed_at),
        kickoff_ts=float(kickoff_ts),
        seconds_to_kickoff=float(seconds_to_kickoff),
        target_seconds_to_kickoff=target,
        error_seconds=float(error),
        quality=quality,
        post_kickoff=post_kickoff,
    )


def best_capture_for_vintage(
    *,
    vintage: ProspectiveVintage,
    observed_ats: list[float],
    kickoff_ts: float,
    tolerances: Optional[dict[ProspectiveVintage, VintageTolerance]] = None,
) -> VintageObservationQuality:
    """Pick the pre-kickoff capture nearest a vintage target, or report MISSED.

    Chooses the observation minimizing |seconds_to_kickoff - target| among
    pre-kickoff captures. If there are no pre-kickoff captures, returns a
    MISSED quality with NaN age (represented explicitly, never silently
    omitted).
    """
    pre = [o for o in observed_ats if (kickoff_ts - o) > 0]
    if not pre:
        return VintageObservationQuality(
            vintage=vintage,
            observed_at=float("nan"),
            kickoff_ts=float(kickoff_ts),
            seconds_to_kickoff=float("nan"),
            target_seconds_to_kickoff=vintage.offset_seconds,
            error_seconds=float("inf"),
            quality=VintageQuality.MISSED,
            post_kickoff=False,
        )
    target = vintage.offset_seconds
    best = min(pre, key=lambda o: abs((kickoff_ts - o) - target))
    return classify_capture(
        vintage=vintage, observed_at=best, kickoff_ts=kickoff_ts, tolerances=tolerances
    )
