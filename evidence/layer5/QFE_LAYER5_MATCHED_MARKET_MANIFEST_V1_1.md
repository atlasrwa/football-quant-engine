# QFE V2 Layer 5 — Matched Market Manifest V1.1

Manifest hash: `6f43bd3cc224cc9e42515d6c187b1de7bfff822324aa5cbc4a4b0cbfcb74b54f`

Status: **FROZEN MARKET METADATA / PROTECTED OUTCOMES UNOPENED**

## Bound source

- Source: `QFE_PROSPECTIVE_CAPTURE_STORE` / `thestatsapi`
- Frozen capture prefix: **56,746,004 bytes**
- Prefix SHA256: `5ac264598d89904531294bfeb0ddb32a0947858ac4c799d76e7c6eb1b1989b78`
- Retained registered T-6h rows: **58**
- Retained row semantic hash: `068d8db531dc42aeb430021b265a27eab8c7e4722b3c4384879a3eea5443aa30`
- Retained rows gzip SHA256: `cd1b8a5f8fe68e17c37cb3f0b17bf247527e0f145de8091cbe73918ddb18f126`

## Protected market coverage

- Protected fixtures: **317**
- Valid goals total 2.5 comparator: **3**
- Valid match-corner surface: **3**
- Valid team-corner market: **0**
- Invalid timestamp rows: **0**

This coverage is intentionally sparse. The registered T-6h horizon was **not relaxed** to increase sample size. Legacy alert/CLV stores were audited for coverage but are not blended into this manifest. Legacy target-aware LLM/M0 feature matrices are inadmissible as market evidence.

The market-relative protected scorecard will therefore be extremely underpowered and must be reported as such. The 317-fixture standalone p_model protected scorecard remains a separate question once the Layer 5 freeze is complete.

## Scientific boundary

No protected outcome, score, settlement or closing-line result was read to construct this manifest. Market eligibility was determined from fixture identity, capture timestamps, bookmaker hierarchy, line coverage and raw prices only.
