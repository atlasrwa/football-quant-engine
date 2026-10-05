# QFE V2 Layer 5 V1.2 — Integrity Audit

Audit hash: 5a18914704641eeaa5af7e0af8226464aee6a977d04809211515bf72991cdb0e

Status: **PASS — FROZEN FOR A NEW FUTURE PROSPECTIVE COHORT; NO NEW OUTCOMES OPENED**

- Layer 4 V3 model freeze: bce2cbdb6fd3ecf1d664439116d1666b9fc4b4172c2838bf29428d07d2713bd2
- Layer 4 V3 certification: 1a0e34e1473b22088b9d9340393034a2e2f829ad93790afbbd5f66bb7c560503
- Layer 5 V1.2 protocol: ae39008016b66f27c279bd2d47093e679ff46458fb44226d2b373983d42bb46a
- Numeric-policy fingerprint: 0871ae9c1eb92d858b5f11551b339959e63870b52a1c936069236eb493ef5e51

The numerical and selection market policy is exactly unchanged from V1.1. V1.2 changes only the repaired Layer 4 binding, cohort governance, and fail-closed corner settlement eligibility.

Validation:
- Focused Layer 5 tests: **40/40 PASS**
- Full repository: **354/354 PASS**
- Research imports: **88/88 PASS**
- Diff check: **PASS**
- Historical V1.1 matched-market manifest: **byte-exact regeneration PASS**
- Adversarial stress: **19,000 cases / 0 violations**

Scientific boundary:
- former 317-fixture cohort is diagnostic-only, never a final holdout;
- new cohort must be frozen before every fixture's T-6h cutoff;
- cohort rows are exactly fixture_id and event_time and reject outcome fields;
- goals O/U 2.5 market comparison is eligible;
- corner bookmaker comparison fails closed with SETTLEMENT_SEMANTICS_UNVERIFIED;
- bookings remain blocked;
- no new future cohort, outcome, or market-relative score has been opened.

Next: freeze a new future prospective cohort before T-6h, freeze V3 p_model predictions, and capture the registered T-6h goals market before any outcome is known.
