# QFE V2 Worktree Hygiene Inventory V1

Generated: 2026-10-04T15:47:10.396492+00:00

## Canonical active repository

- Path: `/srv/qfe/football-quant-engine`
- Branch: `chore/qfe-v2-foundation-hygiene-v2`
- HEAD: `8c7e6346aaa5326955914d49194d218c45b0dad0`
- Type: standalone clone; future active QFE work must use this path.

## Cleanup performed

- Dead linked-worktree metadata pruned: **5**.
- Registered old linked worktrees remaining: **38**.
- Worktrees with tracked or untracked dirt: **9**.
- Local `main` synchronized to `origin/main`: `c5f7b66b3c04826dff9fdc06dc510bddb31d21c0`.
- Active QFE research/test processes at inventory time: **0**.
- No surviving historical worktree was deleted or modified.

## Classification counts

- `CERTIFIED_REPAIR_READONLY`: **1**
- `HISTORICAL_OR_SUPPORT_READONLY`: **5**
- `HISTORICAL_QFE_READONLY`: **18**
- `HOLD_UNCOMMITTED_REPLAY`: **1**
- `LEGACY_RESEARCH_READONLY`: **7**
- `MERGED_REPLAY_READONLY_PENDING_CERT`: **3**
- `OBSOLETE_DIRTY_QUARANTINE`: **1**
- `QUARANTINE_HIGH_RISK_HOME_ROOT`: **1**
- `SEALED_PROTECTED_DRAFT_QUARANTINE`: **1**

## Critical quarantine bindings

- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_CALIBRATED_ROWS_V2_PIT.jsonl.gz` — `73a2f47e363e456633e4306f7a254697b215f60b7371e7cf1e941b9ce7773a57`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_CALIBRATION_V2_PIT.json` — `9faa1351dabac401525f03a7e9672ca3e5ec1b98acf20b69da765bf6ce25cbf2`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_CALIBRATION_V2_PIT.md` — `2ff11b5b380ecf93eb71be56e55629e0f0b74f679510461f7046eb50ee016cdf`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_ENSEMBLE_SELECTION_V2_PIT.json` — `777192c75771215ea8fdec92986a3e82515d471f69cf60a349657f2660435a48`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_ENSEMBLE_SELECTION_V2_PIT.md` — `47853bea33e636f2b9a68e02c89ec4608385cd7bddd0a44568435aea4549bb2f`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_EXECUTION_CONTRACT_V2_PIT.json` — `d26526740264019f6f4d2f23edefaae61706fb201ac2be3dc85d6ada778f667d`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_MODEL_FREEZE_V2_PIT.json` — `3c0e6d83ce6c87f251c15e8dde1e081fc40159ac0df83ce81ad65599b6e4f776`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_MODEL_FREEZE_V2_PIT.md` — `3756038330318470582359820282380635a03c91c218cfa0e7733f992566d162`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_PROTOCOL_AUDIT_V2_PIT.json` — `b70b085342aff2585449e3facdbe6b1a03e1f464476a636f775244f17ec83cdc`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_PROTOCOL_AUDIT_V2_PIT.md` — `2b48195d6b66f6b218e17686c47f87b78dddbd13d8b7ced846083f2df17f3681`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_PROTOCOL_V2_PIT.json` — `3a8e41f417e2505f13f54b6ae295cbf6b6b6a7c227d4727ecacd7687302342b1`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_RAW_CALIBRATION_ROWS_V2_PIT.jsonl.gz` — `48cf45bb5c784544394cf374f5eadf9a643f8f415f29e71fc1c0f2c209341c17`
- Layer 4 HOLD: `evidence/layer4/QFE_LAYER4_RAW_CALIBRATION_V2_PIT.json` — `bc735c1d58a4967ae2810055a8bf6935a9c03aeb0ba7796d5f4855fefe849a91`
- Protected obsolete draft: `src/research/protected/predictions.py` — `67676f148172fc517f01cfbeb314b0c45115581ba9e19edcc2c1fd5756078399` — **NOT EXECUTED**

## Operating rule

Do not use `/home/ubuntu` as an active QFE repository root. It remains a quarantined linked-worktree hub until historical worktrees are retired deliberately. No bulk deletion is authorized by this inventory.
