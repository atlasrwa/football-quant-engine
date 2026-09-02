"""Calibrated prediction engine — the project's validated deliverable.

WHAT THIS IS
============
This package is the product. The market-beating objective is **closed** — the
edge ceiling was measured directly, not assumed (median edge 0-1pp against a
2-4pp requirement; the market's realized rate sits inside the 95% CI of its price
in every well-populated bucket; five hypotheses were tested and honestly killed).
What survived that scrutiny, and what this package delivers, is a **calibrated
prediction engine**: when the model says 65%, the outcome happens about 65% of
the time.

Calibration is the claim. It is provable, checkable, and honest. This package
does NOT claim accuracy (favourites win often, so "we called 62% right" is
meaningless without context) and it does NOT claim discrimination alone (a model
can discriminate well and still be badly calibrated). The primary metrics are
**ECE and reliability curves**, with Brier and BSS-vs-naive as supporting
figures. Every published number carries its sample size.

SCOPE IS A FEATURE, NOT A LIMITATION
====================================
A model that states where it does NOT work is more trustworthy than one claiming
universal coverage. Validated status is explicit per market and per league (see
:mod:`src.research.prediction_engine.scope`):

* **Corners** — validated; best-calibrated. Included.
* **Cards** — validated, EXCEPT the Championship, where disciplinary persistence
  is confirmed absent across three seasons (yellow-rate -> cards association
  -0.044 / +0.033 / +0.012, all p >= 0.37). Included elsewhere; excluded there.
* **Goals, BTTS** — roughly at par with the naive base rate. Shown only with an
  explicit "no demonstrated skill over base rate" label. Never presented as
  predictions worth acting on.

HONEST FRAMING — REQUIRED OF EVERY USER-FACING ARTIFACT
=======================================================
Every user-facing artifact built on this engine MUST state:

1. These are **calibrated probability estimates, not betting advice**.
2. The model has **NOT** been shown to beat bookmaker prices. That was tested
   extensively and the finding is documented (see the failure ledger).
3. The **per-league scope**, including where the model does not work. The primary
   claim is calibrated probabilities for corners and cards; directional calls are
   a separate, mostly-unvalidated claim (they beat the home-advantage baseline in
   only one market/league) and are gated/suppressed accordingly.
4. **No profit claims, no implied profitability, no staking guidance of any
   kind.**

The canonical framing text lives in :data:`HONEST_FRAMING` and helpers in
:mod:`src.research.prediction_engine.scope` so it cannot drift between artifacts.

NO STAKE SIZING, EVER
=====================
Do not add stake sizing, Kelly fractions, or bankroll recommendations to this
package, now or later. This is a deliberate, permanent constraint — not an
oversight for a future contributor to "helpfully" fill in. Sizing turns a
calibrated estimate into betting advice, which this engine explicitly does not
give. The deprecated EV layer (:mod:`src.research._ev_deprecation`) retains such
constructs for Pilot C and internal research only; none of it may be re-exported
here.

WHAT IS REUSED (do not refit or replace)
========================================
* The count-regression models with team-level shrinkage
  (:class:`src.research.asymmetric.directional_model.DirectionalCountModel`,
  :class:`src.research.models.count_regression.CountRegressionModel`,
  :class:`src.research.models.dixon_coles.DixonColesModel`) — the validated
  engine.
* The five feature-verification checks
  (:class:`src.research.asymmetric.gates.FeatureVerificationGate`) — mandatory
  before any modelling.
* Walk-forward, point-in-time discipline, within-league significance, and the
  failure ledger.

This ``__init__`` re-exports the small, stable public surface. It performs only
light imports of this package's own modules.
"""

from __future__ import annotations

from src.research.prediction_engine.scope import (
    HONEST_FRAMING,
    MIN_SETTLED_FOR_CALIBRATION,
    DIRECTIONAL_MAX_ECE,
    DirectionalEvidence,
    DirectionalStatus,
    MarketStatus,
    ValidatedScope,
    directional_status,
    honest_framing_lines,
    market_status,
)
from src.research.prediction_engine.calibration_metrics import (
    BSSResult,
    CalibrationReport,
    base_rate_collapse,
    brier_skill_score,
    calibration_report,
    naive_base_rate_brier,
)
from src.research.prediction_engine.directional import (
    DirectionalCall,
    directional_call,
    directional_probabilities,
)
from src.research.prediction_engine.fixture import (
    FixtureReadout,
    MarketReadout,
    build_fixture_readout,
)
from src.research.prediction_engine.attestation import (
    CALIBRATED_COMMIT_LEDGER,
    CALIBRATED_ID_PREFIX,
    CALIBRATED_REVEAL_LEDGER,
    CALIBRATED_SETTLED_LOG,
    VERIFICATION_RECIPE,
    CalibratedAttestationLedger,
    calibrated_prediction_id,
    verify_commitment,
)
from src.research.prediction_engine.reliability import (
    ReliabilityBucket,
    ReliabilityCell,
    ReliabilityReport,
    build_reliability_cell,
    build_reliability_report,
)

__all__ = [
    # scope + framing
    "HONEST_FRAMING",
    "MIN_SETTLED_FOR_CALIBRATION",
    "DIRECTIONAL_MAX_ECE",
    "DirectionalEvidence",
    "DirectionalStatus",
    "MarketStatus",
    "ValidatedScope",
    "directional_status",
    "honest_framing_lines",
    "market_status",
    # calibration metrics
    "BSSResult",
    "CalibrationReport",
    "base_rate_collapse",
    "brier_skill_score",
    "calibration_report",
    "naive_base_rate_brier",
    # directional calls
    "DirectionalCall",
    "directional_call",
    "directional_probabilities",
    # fixture readout
    "FixtureReadout",
    "MarketReadout",
    "build_fixture_readout",
    # attestation (isolated calibrated ledger)
    "CALIBRATED_COMMIT_LEDGER",
    "CALIBRATED_ID_PREFIX",
    "CALIBRATED_REVEAL_LEDGER",
    "CALIBRATED_SETTLED_LOG",
    "VERIFICATION_RECIPE",
    "CalibratedAttestationLedger",
    "calibrated_prediction_id",
    "verify_commitment",
    # public reliability reporting
    "ReliabilityBucket",
    "ReliabilityCell",
    "ReliabilityReport",
    "build_reliability_cell",
    "build_reliability_report",
]
