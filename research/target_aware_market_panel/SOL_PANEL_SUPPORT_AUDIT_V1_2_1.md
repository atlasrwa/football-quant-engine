# Sol V1.2.1 Outcome-Blind Evaluability Audit

**Decision:** `PASS_V1_2_1_EVALUABILITY_GATE`

No cohort target outcomes, market results, prices, model fits, calibration, or predictive OOS scores were read.

- Original scored rows: **5620**
- Frozen V1.2 prehistory fixtures: **4994**
- Training-fold coverage threshold: **60%** (unchanged)

| Family | Fold | class-C passing | similarity passing |
|---|---:|---:|---:|
| BOOKINGS | 0 | 20 | 20 |
| BOOKINGS | 1 | 20 | 20 |
| BOOKINGS | 2 | 20 | 20 |
| BOOKINGS | 3 | 20 | 20 |
| BOOKINGS | 4 | 20 | 20 |
| CORNERS | 0 | 4 | 4 |
| CORNERS | 1 | 4 | 4 |
| CORNERS | 2 | 4 | 4 |
| CORNERS | 3 | 4 | 4 |
| CORNERS | 4 | 4 | 4 |
| GOALS | 0 | 14 | 14 |
| GOALS | 1 | 14 | 14 |
| GOALS | 2 | 15 | 14 |
| GOALS | 3 | 14 | 14 |
| GOALS | 4 | 15 | 14 |
| TEAM_TOTALS | 0 | 16 | 16 |
| TEAM_TOTALS | 1 | 16 | 16 |
| TEAM_TOTALS | 2 | 16 | 16 |
| TEAM_TOTALS | 3 | 16 | 16 |
| TEAM_TOTALS | 4 | 16 | 16 |

PASS requires both counts to be greater than zero for every family in every fold. A FAIL aborts V1.2.1 before target construction; no threshold, fold, template, or extra-season rescue is permitted.
