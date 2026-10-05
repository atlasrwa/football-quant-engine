# QFE Prospective V1 — Odds Price Movement Scanner Deployment

Deployment hash: 107f40d41d4f6115980597e38fc8af94568124f2415de94d666c6debf5ac5d9f

Status: **DEPLOYED / ENABLED / ACTIVE / ZERO-ELIGIBLE VERIFIED**

- canonical main at deployment: 83ab3e0a7e1595c595e72e91d3f6c494a0b1b1d9
- scanner certification: 87c8122bfaa6997163528f7405f456807cedbd0b03d96875ea4bdf0295cc1544
- scanner service hash: 9b8a7ef2e86d0c7fec8033c0ae581aac918cd50364cffa95b7b4c900a0991383
- scanner timer hash: c2f52e446cbee31ddbd38923da86a970651fb01cf40a5d0d19b4638e5f86dcc1
- both T-6 prediction and price-movement timers are enabled and active on a 5-minute cadence.
- private environment file is referenced without storing secret values.
- manual scanner service run: success / zero eligible / zero price side effects.
- first automatic scanner tick at 18:25:04 UTC: success / zero eligible / zero price side effects.
- post-merge repository: 390/390 tests PASS.

No live p_model, post-T6 price path, operational close, or future outcome has been observed yet.

From the first frozen prediction onward, the scanner will passively record Goals O/U 2.5 until the frozen kickoff and finalize the preregistered operational close without feeding any price back into p_model.
