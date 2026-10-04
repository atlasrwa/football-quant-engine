# QFE V2 Scheduler Hygiene V1

Date: 2026-10-04 (America/Bogota)

Status: **LEGACY PROJECT SCHEDULES PAUSED**

- Active legacy/project cron jobs paused: **5**.
- Remaining active project cron lines after pause: **0**.
- Active project processes after pause: **0**.
- Historical ledgers/data deleted: **NO**.
- Change is reversible from the preserved pre-hygiene crontab snapshot.

Paused jobs:

- `quarantine_forward_loop.py`
- `sync_provider_leagues.py --refresh`
- `v371_pilot.py tick`
- `v381_paired.py tick`
- `team_corners_v1.py tick`

Crontab before hash: `776e42fd44b4c30a670480318b2ac19026a87b2e471aa896b723c4e7282fccc8`
Crontab after hash: `7a644c4d86c3a885a0f59ffa36194bd51be914f1eadd435c63e92d9c452e31a6`

These jobs belong to legacy/shared pre-certification paths and are not part of the repaired QFE V2 evidence chain. They must not be re-enabled implicitly; any restart requires an explicit versioned operating decision.
