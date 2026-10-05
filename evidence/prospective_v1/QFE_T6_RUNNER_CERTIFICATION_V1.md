# QFE Prospective V1 — T-6h Runner Certification

Certification hash: 43fd1a0b4464479ae0b49cead68cf810874a18f3d2fb9c7b923ffec33297b1fa

Status: **PASS — TIMER-READY / NO LIVE PREDICTIONS WRITTEN**

Bindings:
- cohort: f3d5bb667f8849b33baf29fb9666400427a17c4cf02f47e9dc0e0a098af6f8f0
- runner protocol: 08e87b0a7ca4922a67f699c0ae57336a377548438066fd7fa3ecf6eb78e1fdc0
- runner amendment: e43ff668c756b35c35970a16f0d11c311798d43bea11c9bac50b1c2c4bc4a575
- Layer 4 V3 model freeze: bce2cbdb6fd3ecf1d664439116d1666b9fc4b4172c2838bf29428d07d2713bd2
- Layer 5 V1.2: ae39008016b66f27c279bd2d47093e679ff46458fb44226d2b373983d42bb46a

Execution guarantees:
- run every 5 minutes;
- prediction begins only from the registered pre-cutoff execution window;
- complete six-competition history refresh must finish before the due cutoff;
- all due p_model bundles freeze before the first odds request;
- late first wakeups never backfill predictions;
- on-time operational failures may retry only before cutoff;
- schedule changes are terminal abstentions with no replacement;
- only goals O/U 2.5 are normalized into the market capture store;
- raw provider odds payloads are retained unchanged for provenance;
- cohort/model/calibration/market thresholds remain frozen.

Validation:
- T6 runner adversarial tests: **8/8 PASS**
- full prospective subsystem: **59/59 PASS**
- full repository: **381/381 PASS**
- research imports: **92/92 PASS**
- diff check: **PASS**

Live dry run on 2026-10-05:
- due fixtures: 0
- predictions: 0
- market captures: 0
- new history snapshots: 0
- provider-side effects: **0**

No live prospective prediction or market price has been opened yet.

Next gate: merge, install the 5-minute systemd timer from canonical main, verify one zero-due service invocation, then leave the predictive stack unchanged until the first registered T-6h window.
