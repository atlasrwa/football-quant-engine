# QFE Prospective V1 — Odds Price Movement Scanner Certification

Certification hash: 87c8122bfaa6997163528f7405f456807cedbd0b03d96875ea4bdf0295cc1544

Status: **PASS — DEPLOYMENT READY / NO LIVE PRICE MOVEMENT CAPTURED**

The scanner is passive evaluation instrumentation. It cannot call or modify the probability model.

Certified behavior:
- scan only fixtures with an already frozen prospective prediction;
- no odds capture before T-6 or at/after kickoff;
- retain immutable raw provider payloads but normalize only Goals O/U 2.5;
- fixed bookmaker hierarchy and recency select the close; price attractiveness cannot;
- operational close is the latest valid pre-kickoff bundle no more than 600 seconds old;
- schedule changes abstain rather than redefine the close horizon;
- first post-kickoff tick finalizes only from already captured pre-kickoff evidence and makes no provider request;
- T-6 entry, frozen prediction and cohort membership remain immutable.

Validation:
- scanner adversarial tests: **9/9 PASS**
- prospective subsystem: **68/68 PASS**
- full repository: **390/390 PASS**
- research imports: **93/93 PASS**
- live zero-eligible dry run: **PASS / zero price side effects**

No live prospective prediction, post-T6 price path, closing line, or outcome has been observed yet.
