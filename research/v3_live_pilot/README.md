# QFE V3 Prospective Pilot

This pilot appends automated prospective tests **21–40** to the existing lean ledger. Tests 1–20 are historical and are never rewritten.

## Frozen research contract

The governing artifact is `V3_FREEZE_V1.json`. Its internal contract hash is checked by code on every run. After the first prospective V3 declaration, any scientific change requires a new version rather than editing V3 in place.

Supported production-candidate research families:

- goals O/U 2.5 and 3.5: regularized Dixon–Coles + chronological Platt calibration;
- total corners: provider-native TheStatsAPI median/shrinkage model.

BTTS, bookings/cards, other goal lines and team-corner markets are excluded.

## Point-in-time firewall

The football distribution is frozen before the odds payload is fetched. If a family could not freeze before the first market observation for a fixture, that family is permanently abstained for that fixture. No post-market fitting is allowed.

Historical football observations are TheStatsAPI-only. No implicit provider blending exists on this path.

## Commercial gate

Bet365 only for this pilot. A declaration requires all three:

1. selected model probability >= 60%;
2. model minus proportional no-vig market probability >= 5 percentage points;
3. model probability exceeds the vig-loaded raw break-even probability.

Opening is reference context only. Entry is the prospectively observed `last_seen` field at our retrieval timestamp. Close is the last observation we actually captured before kickoff; a 5–20 minute capture is labelled `FINAL_5_20M`.

## Operations

The prototype secret file is `/home/ubuntu/.config/qfe-v3/prototype.env` (mode 0600, outside Git). The runner loads it explicitly so cron does not depend on interactive shell initialization.

`./scripts/v3_pilot.py status`
`./scripts/v3_pilot.py canary`
`./scripts/v3_pilot.py tick`
`./scripts/v3_pilot.py settle`
`./scripts/v3_pilot.py telegram-test`

The cron tick runs every 15 minutes, but competition discovery is internally throttled to six-hour intervals. Provider requests have a 160-call/run hard cap, 2.1-second pacing and a 10,000-request monthly reserve.

## Pilot stop

No more counting declarations are allowed after test 40. Capture/settlement may continue, but V3 remains frozen. When all 40 tests are settled an `AUDIT_READY` artifact is written. Rework happens only after the independent audit.
