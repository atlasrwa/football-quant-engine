# QFE V2.1 — Corner-Side Calibration Prospective Shadow V1.1

Status: **PREREGISTERED PROSPECTIVE SHADOW / ACTIVE**

V1.1 supersedes V1 before any shadow prediction existed. The repair binds the prediction feature cutoff to **T−6h (21,600 seconds)**. Every shadow record must use `prediction_cutoff_ts = kickoff_ts - 21600` and all model state/features must be available by that cutoff. Late-discovered fixtures abstain rather than shifting the horizon. All other candidate, stopping, scoring and anti-drift rules are unchanged.
