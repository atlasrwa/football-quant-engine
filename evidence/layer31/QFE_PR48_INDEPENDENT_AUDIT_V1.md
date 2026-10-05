# QFE V2 — PR #48 Independent Audit V1

Audit hash: c0d33ba10991aae66100e2186781c6c0100657db1fea882aa9f5488d2cdba7fc

Status: **PASS WITH RESEARCH CAVEATS — DEVELOPMENT COMPONENT ELIGIBILITY ONLY**

## Preregistration

- V1 protocol was frozen before original Layer 3.1 scoring.
- V2 repaired protocol differs from V1 only in version/date binding; every scientific field is identical.
- No best-line search is allowed.
- SIDE and TOTAL are the only two primary hypotheses; line/role/competition slices are diagnostic only.

## Boundary

- DEVELOPMENT validation only.
- CALIBRATION outcomes used: **NO**.
- Exposed former-PROTECTED outcomes used: **NO**.
- Market odds used: **NO**.
- Later cached rows may be deserialized during canonical corpus reconstruction, but cannot enter Layer 3.1 model state, fold fitting, scoring or promotion logic.

## Independent byte-exact regeneration

- Full scientific artifact: **EXACT**.
- Artifact hash: 6f90e37a309e4b41de44ef1baa9ec1dbdb08edc66cec7cd385f86d21a0d19298
- Rows: **94,752**.
- Row hash: ba22bad8012b64fc3a8350eb1ea222e43693234a6fcc16f9efb015ec07c4efc9
- Compact summary bytes: **EXACT**.
- Markdown bytes: **EXACT**.
- Deterministic gzip rows: **EXACT**.
- Full compact-artifact verifier: **PASS**.

## Primary results

### SIDE corners
- 31,584 paired fixture-role-line cells across 2,632 eligible validation fixtures.
- Log Loss improvement: **+0.004739172**; 95% frozen-block CI **+0.003499461 to +0.006064100**.
- Brier improvement: **+0.001422059**; 95% CI **+0.001012509 to +0.001831743**.
- HOME and AWAY pooled role effects are both positive.
- Decision: **NB2_DEVELOPMENT_CANDIDATE**.

### TOTAL corners
- 15,792 paired fixture-line cells.
- Log Loss improvement: **+0.001543444**; CI crosses zero.
- Brier improvement: **+0.000412314**; CI crosses zero.
- Decision: **NB2_WEAK_OR_INCONCLUSIVE**.

## Exact-SHA validation

- Focused Layer 3.1 tests: **42/42 PASS**.
- Full repository: **338/338 PASS**.
- Research import sweep: **86/86 PASS**.
- Diff check: **PASS**.

## Audit caveats

1. Layer 3.1 is not an independent confirmation of NB2: the candidate was selected using the same DEVELOPMENT era in Layer 3.
2. The intensity configuration is DEVELOPMENT-selected and reused in fold OOF rather than nested inside each fold.
3. The 31,584/15,792 cells are correlated multi-line observations; uncertainty is based on 49 time blocks, not tens of thousands of independent samples.
4. The protocol label UTC_CALENDAR_WEEK is imprecise: code uses epoch-aligned fixed 7-day blocks. An audit-only ISO Monday-week sensitivity check leaves both decisions unchanged.
5. Two primary hypotheses use nominal 95% intervals without an explicit family-wise correction.
6. SIDE pooled evidence is broad, but not every line/competition diagnostic CI is strictly positive.
7. Provider-to-bookmaker corner settlement equivalence remains unverified, so none of this authorizes bookmaker corner comparison.

## Verdict

**CERTIFY PR #48 as valid DEVELOPMENT component-eligibility evidence only.**

Side-specific NB2 is eligible to enter Layer 4 as a candidate component. Match-total NB2 is **not promoted**. This audit does not authorize calibration changes, market-edge claims, commercial use, or restoration of the exposed 317-fixture cohort.

Next gate: **independent audit or clean rebuild of Layer 4 against the certified Layer 2 V3 → Layer 3 → Layer 3.1 chain.**
