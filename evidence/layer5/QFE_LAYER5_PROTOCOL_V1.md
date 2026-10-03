# QFE V2 Layer 5 — Market Surface / Disagreement Protocol V1

Protocol hash: `ecb72d508f421fbbcd45e4623acc50df882c178af83743365ed4be4e2dcebf65`

Status: **PREREGISTERED — PROTECTED SEALED**

## Boundary

- Frozen Layer 4 p_model: `e33af913f4c27ce33355c78792419ad8cee73e3f16ce7c685781a010d386b3ea`.
- Layer 4 integrity audit: `78f5925fc6cc1821e35724663da28a91a82390eab02c87cfdb03a0e07ed8b9e2`.
- Decision horizon: **T-6h**.
- Protected outcomes may not be opened until the complete Layer 5 implementation/policy freeze and integrity audit pass.
- Market prices cannot alter p_model or Layer 4 calibration.

## Market comparator

Primary no-vig method is **multiplicative/proportional** on complete two-sided same-bookmaker quotes. Shin is sensitivity-only; the method may never be selected because it creates a larger apparent disagreement.

For multi-line corners, at least **3 adjacent lines** are required. Raw no-vig OVER probabilities are preserved. Small incoherence may be repaired only by equal-weight non-increasing isotonic projection. A surface abstains if max repair exceeds **3 pp** or mean absolute repair exceeds **1 pp**.

## Disagreement policy

A selected line requires at least **5 pp** absolute model-market disagreement and at least **2 pp** after subtracting the worst absolute endpoint of the empirical Layer 4 calibration-bin reliability-error band. This is an eligibility diagnostic, **not** an individual-fixture confidence interval.

Corner surfaces require at least **2 adjacent corroborating lines** with at least **3 pp** same-direction gap and at least one line at **5 pp**. An opposite-direction strong gap invalidates the surface.

The system is explicitly forbidden to select the maximum gap. It selects the central corroborated market line: cleaned market probability closest to 0.50, with deterministic non-gap tie breaks.

## Initial scope

- Goals total: **2.5 only**, single-line evidence class.
- Home/away team corners: **2.5–7.5**.
- Match-total corners: **7.5–12.5**.
- Bookings: unsupported in Layer 5 V1.

## Protected evaluation

When—and only when—all Layer 5 freeze gates pass:

1. score every protected row with a valid matched market in the **global scorecard**, regardless of disagreement;
2. separately score only preregistered eligible disagreements;
3. use Log Loss/Brier/calibration/coverage as primary evidence;
4. genuine CLV and flat one-unit P&L are secondary commercial evidence;
5. hit rate is not primary and stake optimization is forbidden.
