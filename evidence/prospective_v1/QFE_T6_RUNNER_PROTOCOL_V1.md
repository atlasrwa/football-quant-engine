# QFE Prospective V1 — T-6h Runner Protocol

Protocol hash: 08e87b0a7ca4922a67f699c0ae57336a377548438066fd7fa3ecf6eb78e1fdc0

Status: **FROZEN BEFORE RUNNER IMPLEMENTATION OR LIVE EXECUTION**

The runner executes every 5 minutes. A new prediction is attempted only when its registered T-6h cutoff is 20–30 minutes away.

Execution order is a hard firewall:
1. refresh complete six-competition football history;
2. verify frozen schedule identity;
3. freeze every due p_model bundle;
4. only after every due prediction is frozen, request odds;
5. append timestamped goals O/U 2.5 market snapshots until cutoff.

A prediction or market snapshot is never backfilled after cutoff. Cohort membership, model parameters, calibration and market thresholds are immutable.

Prior cohort results may enter later fixture state only through the frozen history-update path once legitimately available; they may not be scored or used to redesign the live experiment.
