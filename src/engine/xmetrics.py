"""Vectorized x-Metric formula engine.

Computes proprietary xC (Corner Pressure), xB (Booking Intensity),
and xO (Offsides Trap) metrics from FootyStats raw match data.
All operations are fully vectorized via pandas/numpy — no row-level loops.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class XMetricCoefficients:
    """Tunable coefficients for x-Metric formulas."""

    # xC — Corner Pressure
    xc_alpha: float = 0.45
    xc_beta: float = 0.30
    xc_gamma: float = 0.25

    # xB — Booking Intensity
    xb_delta: float = 0.02

    # xO — Offsides Engine
    xo_eta: float = 1.0


class XMetricEngine:
    """Vectorized computation engine for xC, xB, xO metrics.

    Accepts a pandas DataFrame with FootyStats raw columns and appends
    computed x-Metric columns in-place (returns the augmented DataFrame).
    """

    def __init__(self, coefficients: XMetricCoefficients | None = None) -> None:
        self.coeff = coefficients or XMetricCoefficients()

    # ------------------------------------------------------------------
    # xC — Expected Corner Pressure
    # ------------------------------------------------------------------

    def compute_xC(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute home_xC and away_xC columns.

        Formula per side:
            xC = α·(dangerous_attacks / attacks) + β·shots_off_target + γ·opponent_corners_conceded_avg

        Missing fields produce NaN; division by zero yields 0.0.
        """
        df = df.copy()

        for side, opp in [("home", "away"), ("away", "home")]:
            attacks = self._safe_col(df, f"attacks_{side}")
            dangerous = self._safe_col(df, f"dangerous_attacks_{side}")
            shots_off = self._safe_col(df, f"shots_off_target_{side}")
            opp_corners_avg = self._safe_col(df, f"corners_avg_against_{opp}")

            # Dangerous attack ratio with division-by-zero guard
            with np.errstate(divide="ignore", invalid="ignore"):
                ratio = np.where(attacks != 0, dangerous / attacks, 0.0)

            xc = (
                self.coeff.xc_alpha * ratio
                + self.coeff.xc_beta * shots_off
                + self.coeff.xc_gamma * opp_corners_avg
            )
            df[f"{side}_xC"] = xc

        n_valid = df[["home_xC", "away_xC"]].notna().all(axis=1).sum()
        logger.info("xC computed: %d/%d rows valid", n_valid, len(df))
        return df

    # ------------------------------------------------------------------
    # xB — Expected Booking Intensity
    # ------------------------------------------------------------------

    def compute_xB(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute home_xB and away_xB columns.

        Formula per side:
            xB = (fouls × referee_cards_per_foul) + δ·(100 - possession) × opponent_dribbles_faced

        Proxy: opponent_dribbles_faced ≈ opponent_xg_against × 3.5
        referee_cards_per_foul = referee_cards_per_match / league_avg_fouls (approx 22)
        """
        df = df.copy()

        referee_cpm = self._safe_col(df, "referee_cards_per_match")
        # Approximate cards-per-foul: referee_cpm / avg fouls per team per match (~11)
        ref_cards_per_foul = referee_cpm / 11.0

        for side, opp in [("home", "away"), ("away", "home")]:
            fouls = self._safe_col(df, f"fouls_{side}")
            possession = self._safe_col(df, f"possession_{side}")
            opp_xg_against = self._safe_col(df, f"xg_against_{opp}")

            # Proxy for opponent dribbles faced
            opp_dribbles = opp_xg_against * 3.5

            xb = (
                fouls * ref_cards_per_foul
                + self.coeff.xb_delta * (100.0 - possession) * opp_dribbles
            )
            df[f"{side}_xB"] = xb

        n_valid = df[["home_xB", "away_xB"]].notna().all(axis=1).sum()
        logger.info("xB computed: %d/%d rows valid", n_valid, len(df))
        return df

    # ------------------------------------------------------------------
    # xO — Expected Offsides Trap & Attack Line
    # ------------------------------------------------------------------

    def compute_xO(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute home_xO and away_xO columns.

        Formula per side:
            xO = η·(attacker_offsides × (opponent_high_line_index / league_baseline))

        Proxy: high_line_index = 1/ppda (lower PPDA → higher line → more offsides).
        League baseline = mean(1/ppda) across all rows.
        """
        df = df.copy()

        # Compute high-line indices for both sides
        ppda_home = self._safe_col(df, "ppda_home")
        ppda_away = self._safe_col(df, "ppda_away")

        with np.errstate(divide="ignore", invalid="ignore"):
            hli_home = np.where(ppda_home != 0, 1.0 / ppda_home, 0.0)
            hli_away = np.where(ppda_away != 0, 1.0 / ppda_away, 0.0)

        # League baseline: mean of all high-line indices (home + away)
        all_hli = np.concatenate([hli_home[~np.isnan(hli_home)], hli_away[~np.isnan(hli_away)]])
        league_baseline = float(np.mean(all_hli)) if len(all_hli) > 0 else 1.0

        for side, opp in [("home", "away"), ("away", "home")]:
            offsides = self._safe_col(df, f"offsides_{side}")
            opp_hli = hli_away if opp == "away" else hli_home

            ratio = np.where(league_baseline != 0, opp_hli / league_baseline, 0.0)
            xo = self.coeff.xo_eta * offsides * ratio
            df[f"{side}_xO"] = xo

        n_valid = df[["home_xO", "away_xO"]].notna().all(axis=1).sum()
        logger.info("xO computed: %d/%d rows valid", n_valid, len(df))
        return df

    # ------------------------------------------------------------------
    # Combined
    # ------------------------------------------------------------------

    def compute_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """Compute all x-Metrics (xC, xB, xO) and return augmented DataFrame."""
        df = self.compute_xC(df)
        df = self.compute_xB(df)
        df = self.compute_xO(df)
        logger.info(
            "All x-Metrics computed for %d matches. Columns added: "
            "home_xC, away_xC, home_xB, away_xB, home_xO, away_xO",
            len(df),
        )
        return df

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _safe_col(df: pd.DataFrame, col: str) -> np.ndarray:
        """Extract column as numpy array; return NaN array if missing."""
        if col in df.columns:
            return df[col].to_numpy(dtype=np.float64, na_value=np.nan)
        return np.full(len(df), np.nan)
