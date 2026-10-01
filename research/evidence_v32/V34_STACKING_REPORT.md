# QFE V3.4 — Exact-reference stacking audit

Status: **DEVELOPMENT_ONLY / NO PRODUCTION PROMOTION**

Frozen specification: `b20381e`  
Frozen exact-reference apparatus: `379b0d0`  
Parallelization-only implementation commit: `eed773a`

No market prices were used for fitting or stack-weight selection. No live provider,
bookmaker, LLM or Telegram calls were made. Stack weights were learned on each
fold's calibration segment only and applied unchanged to the chronological test
segment.

After an Ubuntu update broke the Python virtualenv interpreter link, the
environment was restored to Python 3.12.3. The relevant suite passed 24/24 and
`pip check` reported no broken requirements. The full V3.4 experiment was then
rerun from scratch. Both output files were byte-identical to the pre-repair run:

- `results.json`: `4414d921efa7150aa19b5b7018075cc8cfe81757c9cb9b5631e9704277de31c3`
- `summary.json`: `244aeb39edf505167cf4cdfce3b11b11b0a7d0ba93eb122479bd6c26bb6e34d5`

## Question

Do the existing frozen V3 models contain complementary information that should
be blended with the new evidence models?

The preregistered stack is a bounded convex blend in **logit probability space**:

`logit(p_stack) = (1-w) logit(p_V3) + w logit(p_challenger)`

with `0 <= w <= 1`. A separate weight is fitted for each family, market line
and chronological fold using the calibration segment only. There is no
test-set weight tuning, intercept or extra slope parameter.
## Goals O/U — do not stack

Reference: `QFE_GOALS_V3_DC_CALIBRATED`  
Challenger: `VENUE_DEEP_POISSON`

The exact historical V3 replay is reconstructible for 2,035 requested fixtures;
70 fail closed because the required prior-season calibrator has insufficient
history. The common OOS comparison contains 1,778 test fixtures.

| Market | V3 log loss | Venue-deep log loss | Stack log loss | V3 Brier | Venue-deep Brier | Stack Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| O2.5 | 0.687538 | **0.680339** | 0.681594 | 0.247193 | **0.243748** | 0.244320 |
| O3.5 | 0.589848 | **0.585625** | 0.589034 | 0.200502 | **0.198790** | 0.200361 |

For O2.5 the venue-deep challenger improves aggregate log loss over V3 by about
0.00720. Blending V3 back into venue-deep **worsens** log loss by about 0.00126
and worsens Brier by about 0.00057 relative to the challenger.

For O3.5 the venue-deep challenger improves aggregate log loss over V3 by about
0.00422. The stack then loses about 0.00341 versus venue-deep. The paired
week-block interval for stack versus challenger is fully negative
[-0.007802, -0.000331], so in this development experiment the blend is clearly
inferior to the venue-deep parent at O3.5.

Calibration also does not justify the blend. At O3.5 the diagnostic slope is:

- V3: 0.813
- venue-deep: **0.870**
- stack: 0.751

The fold weights are unstable and often hit the challenger boundary, another
sign that the V3 probability does not contribute stable incremental information
once venue-deep is present.

**Decision:** do not average the two goals models. Keep
`VENUE_DEEP_POISSON` as a separate prospective shadow challenger against the
unchanged V3 reference. Any future replacement requires genuinely prospective
proper-score/calibration evidence and market-adjusted incremental value.
## Corners O/U — stacking is worth carrying forward

Reference: `QFE_CORNERS_V3_TSA_MEDIAN`  
Challenger: `CORNERS_PRESSURE_POISSON`

The V3 reference replay supports 2,146 requested fixtures and fails closed on 73.
The common OOS test comparison contains 1,821 fixtures.

| Market | V3 LL | Pressure LL | Stack LL | V3 Brier | Pressure Brier | Stack Brier |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| O8.5 | 0.670002 | 0.669996 | **0.669127** | 0.238483 | 0.238438 | **0.238057** |
| O9.5 | 0.688557 | 0.687767 | **0.687529** | 0.247735 | 0.247143 | **0.247020** |
| O10.5 | 0.654138 | 0.654666 | **0.653280** | 0.230938 | 0.230747 | **0.230115** |

Unlike goals, the corner stack has the lowest aggregate log loss **and** Brier at
all three tested lines.

Calibration also moves in the correct direction:

- O8.5 slope: V3 0.640 → pressure 0.699 → **stack 0.795**
- O9.5 slope: V3 0.708 → pressure 0.792 → **stack 0.843**
- O10.5 slope: V3 0.755 → pressure 0.773 → **stack 0.914**

That is important because the standalone pressure model's main V3.3 weakness was
calibration. Combining it with the old V3 model recovers some of that weakness.

However, the evidence is still not strong enough for promotion. The paired
week-block intervals for stack versus V3 all cross zero:

- O8.5: [-0.004483, +0.005582]
- O9.5: [-0.005266, +0.007166]
- O10.5: [-0.005555, +0.007489]

Fold-specific challenger weights are also unstable, ranging roughly from 0.30
to almost 1.00. Therefore the aggregate improvement is a **development signal
of complementarity**, not proof of a production improvement.

**Decision:** retain the calibrated V3 + pressure stack as the next prospective
corner challenger, while keeping `QFE_CORNERS_V3_TSA_MEDIAN` unchanged as the
operational/reference model.
## Architectural interpretation

The two families behave differently and should not be forced into one ensemble
policy.

For goals, venue-conditioned raw evidence largely subsumes what the current V3
Dixon-Coles path contributes at the tested O/U lines. Mixing the old reference
back in dilutes the better development challenger.

For corners, the old V3 model and the raw pressure model appear to encode
different information. V3 contributes stable historical corner-rate structure;
the pressure arm contributes attacking/defensive process information. Their
calibration-only logit stack improves aggregate proper scores and calibration
relative to either parent.

The correct next move is therefore:

1. **Goals:** shadow V3 and `VENUE_DEEP_POISSON` separately. No ensemble.
2. **Corners:** preregister a single point-in-time stack-weight protocol, freeze
   it before new outcomes, and shadow the stack beside unchanged V3.
3. Compare all future probabilities to timestamped no-vig market probabilities,
   genuine close and settlement. Do not promote from these exposed results.
4. Do not reuse or average the five exposed fold weights as if they were a
   production coefficient. Their instability is itself evidence that the
   forward calibration protocol needs to be fixed prospectively.

## Environment repair finding

The Ubuntu update did not delete the scientific package files. It changed the
system `python3` target from Python 3.12 to Python 3.14, while the existing venv
had been created for 3.12. This made the venv resolve to the wrong interpreter
and appear to have lost NumPy/SciPy/pytest/etc.

The venv interpreter link was restored to `/usr/bin/python3.12`. The existing
package versions then imported successfully, including NumPy 1.26.4, SciPy
1.12.0, pandas 2.2.1, scikit-learn 1.9.0, pytest 8.0.2, Hypothesis, FastAPI and
the pinned boto3/botocore pair.

A separate reproducibility defect remains: scikit-learn is imported by the
modeling code but is not declared in `pyproject.toml`. That dependency should
be pinned before the next environment rebuild.
