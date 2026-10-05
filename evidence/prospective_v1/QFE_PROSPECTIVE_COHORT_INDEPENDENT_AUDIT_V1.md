# QFE Prospective Cohort V1 — Independent Audit

Audit hash: 05c39363f600a8238c3c34218a1234992b123be2bd6b46193ffffedb6ba16de9

Status: **PASS — MEMBERSHIP INDEPENDENTLY AUDITED / OUTCOME-BLIND**

The frozen cohort contains 135 unique fixtures across all six frozen competitions. Membership was frozen on 2026-10-05 at 13:07:31 UTC. The earliest fixture kicks off on 2026-10-09 at 18:00 UTC, so the earliest T-6h cutoff is 2026-10-09 at 12:00 UTC. Minimum freeze buffer is 341,548 seconds (~3.95 days).

Independent reconstruction from the retained raw scheduled-fixture payloads is exact:
- raw payload hashes: PASS
- discovery manifest: exact
- cohort object/hash: exact
- fixture identities/order: exact
- duplicate fixture ids: zero

Selection integrity:
- window fixed before discovery;
- every provider-scheduled fixture in the window is included;
- no cap, subsampling, odds, market availability, model support, team-history, or outcome filter;
- membership is immutable and replacements are forbidden.

Validation:
- repository: **373/373 PASS**
- research imports: **91/91 PASS**
- diff check: **PASS**

Critical operational note: the Oct-5 incremental-history snapshot is not sufficient by itself for all later fixtures. The T-6h runner must refresh immutable football history before each prediction cutoff so football matches completed after Oct 5 can influence later fixtures when legitimately available.

No future outcomes or predictions have been opened.
