# V1.2.4 Strong-Baseline OOS Evaluation

- Frozen primary fixtures: **3057**
- Strict unseen-team robustness fixtures: **396**
- Families passing the frozen primary gate: **none**

| Family | Delta log loss M0-M1 | 95% CI | Holm p | ECE M0 | ECE M1 | Gate |
|---|---:|---:|---:|---:|---:|---|
| GOALS | -0.001893 | [-0.004204, 0.000151] | 1.000000 | 0.024939 | 0.023906 | FAIL |
| CORNERS | 0.000918 | [-0.001392, 0.004020] | 0.829500 | 0.049533 | 0.049390 | FAIL |
| TEAM_TOTALS | -0.000480 | [-0.002436, 0.001415] | 1.000000 | 0.040042 | 0.040158 | FAIL |
| BOOKINGS | 0.002407 | [-0.002013, 0.006827] | 0.558000 | 0.026478 | 0.027791 | FAIL |

This is a retrospective transferability screen. Prospective validation remains mandatory before any feature promotion or CHAMPION change.

Evaluation artifact SHA256: df9882e64ac9a9c265ae8c74d9ac94e96d0598a72e62dd5c91f188ebffcdda00
CHAMPION unchanged.
