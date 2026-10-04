# QFE PIT Horizon Call-Path Audit V2

Audit hash: f2fc779bc388a30d209eaf7b8d6f523a2b4f3a9b179fdc59bfb3b83a2753972f

Status: **PASS — PRE-EVIDENCE-RERUN**

## Closed integrity defects

- Dynamic hierarchical state is gated by the registered T-6h decision horizon and 6h availability embargo.
- Layer 3 distribution selection cannot bypass the repaired walker through immediate process_batch updates.
- Layer 3 online distribution-parameter outcomes become eligible only under the same PIT inequality.
- Layer 4 calibration-time similar-context targets use the same PIT availability gate.
- Exact equality at source+6h == target-6h is regression-tested as admissible.

## Static call-path result

- All active DynamicHierarchicalCountBaseline research callers use walk_forward.
- No production caller invokes its immediate process_batch primitive.
- LatentTeamStateForecaster has no active production caller.
- Development similar-context OOF remains conservative at frozen fold boundaries.
- Layer 4 sequential similar-context calibration is now explicitly horizon-gated.

## Validation

- Focused integrity tests: **25 passed**.
- Full repository: **334 passed, 0 failed**.
- git diff --check: **PASS**.

## Firewall

No model evidence was regenerated in this step. No protected prediction was generated, no protected outcome was read, and no protected score was computed.

**Next gate:** version and rerun Layer 2 from this repaired current-main base. Historical evidence remains immutable and superseded where dynamic-derived.
