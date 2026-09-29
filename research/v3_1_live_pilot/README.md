# QFE V3.1 goals + BTTS prospective shadow

This is an additive successor shadow path. It **does not modify** frozen V3 tests 21–40 and it never runs or replaces the V3 corners model.

## Frozen model

`V31_FREEZE_V1.json` fixes the model, feature bundle, chronological fitting/calibration rule, market lines, disagreement thresholds, provider and Telegram labeling before live use.

The deterministic goals model uses only earlier matches: goals for/against plus prior total shots, shots on target, shots inside the box, big chances and venue context. Side goal means are fitted with regularized Poisson regression and one fixed joint calibration form. Total-goal probabilities and BTTS are derived from the same two side means. Independence between side counts remains an unvalidated assumption.

The development evidence that motivated this candidate was post-exposure and did not establish promotion. Every Telegram message therefore says `NOT VALIDATED / NOT ACTIONABLE` and V3.1 declarations do not count toward the frozen V3 40-test cohort.

## Provider and point-in-time rules

Football history and odds are TheStatsAPI-only. Historical raw stats are used only to construct features for later fixtures. A 24-hour historical feature cutoff plus a 4-hour post-match publication buffer is preserved. The target distribution is frozen before its odds payload is fetched. Missing support means abstain.

Colombia Primera A (`comp_720692`) is explicitly included in the 27-competition scope verified from the live provider catalog on 2026-09-29.

## Operations

```bash
/home/ubuntu/.venv/bin/python scripts/v31_pilot.py status
/home/ubuntu/.venv/bin/python scripts/v31_pilot.py tick --force-discovery
/home/ubuntu/.venv/bin/python scripts/v31_pilot.py settle
/home/ubuntu/.venv/bin/python scripts/v31_pilot.py telegram-test
```

The runtime reuses the immutable raw provider cache and dedicated V3 Telegram credentials, but writes V3.1 predictions, market observations, ledger events and settlements under `/home/ubuntu/data/v31_pilot`.
