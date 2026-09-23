# V1.2 fixture discovery recovery

The frozen live discovery runner at `5a79c8aff17e4c5dc18d9b944116019a3a5ac986` completed all provider page fetches, then failed in cleanup because `ProspectiveApiClient` does not implement `close()`.

No provider request will be retried. The staging namespace contains 54 pages covering all 12 frozen seasons, and every season has pages 1 through the provider-declared total page count. The recovery runner is zero-network and may only validate/freeze those staged first-pass payloads.

Expected first-pass evidence before recovery: 54 raw pages, 12 seasons, 4,994 finished fixture ids, 0 stats calls, 0 odds/lineup/injury calls. Any mismatch aborts recovery.

This is a transport-cleanup repair only. It does not alter season selection, fixture selection, hypotheses, thresholds, folds, target universe, CHAMPION, or any predictive rule.
