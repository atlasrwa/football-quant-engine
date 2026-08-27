# Phase 3.4 Attestation Model

## Purpose

Web3-ready attestation infrastructure that works fully offline from blockchain. Enables cryptographic proof that predictions were made before outcomes were known, without requiring any blockchain dependency.

## Lifecycle

```
PREDICTION CREATED
      ↓
COMMITMENT CREATED (server-generated hash, before settlement)
      ↓
PREDICTION PENDING (awaiting match outcome)
      ↓
SETTLEMENT (outcome determined)
      ↓
REVEAL CREATED (settlement data bound to commitment)
      ↓
OPTIONAL FUTURE ON-CHAIN ATTESTATION
```

## Commitment

### What It Proves

A commitment cryptographically binds a prediction to its authoritative inputs BEFORE settlement. This proves the prediction existed before the outcome was known.

### Content

```json
{
  "entry_odds": <float|null>,
  "prediction_id": "<uuid>",
  "prediction_timestamp": "<iso8601>",
  "proof_hash": "<64-char-hex>",
  "strategy_id": "<uuid>",
  "strategy_version": <int>
}
```

The commitment REFERENCES the existing `proof_hash` from `PredictionEvent.compute_proof_hash()`. It does NOT replace or modify it.

### Constraints

- Server-generated (client cannot provide commitment_hash)
- Must be created BEFORE settlement
- One per prediction (UNIQUE constraint)
- Idempotent (duplicate returns existing)
- Cross-user operations blocked

## Reveal

### What It Proves

A reveal links the pre-settlement commitment to the post-settlement outcome, completing the cryptographic chain.

### Content

```json
{
  "clv_pct": <float|null>,
  "closing_odds": <float|null>,
  "commitment_hash": "<64-char-hex>",
  "entry_odds": <float|null>,
  "outcome": "<WIN|LOSS|VOID|PUSH>",
  "prediction_id": "<uuid>",
  "profit_loss": <float>,
  "settled_at": "<iso8601>",
  "settlement_id": "<uuid>"
}
```

### Constraints

- Requires existing commitment (cannot reveal without prior commit)
- Requires existing settlement (cannot reveal before settlement)
- Settlement fields are SERVER-DERIVED (client cannot forge outcome, closing_odds, P&L, CLV)
- One per commitment (UNIQUE constraint)
- Idempotent (duplicate returns existing)
- Cross-user operations blocked

## Rejected Operations

| Operation | Reason |
|-----------|--------|
| Reveal without commitment | Lifecycle violation |
| Reveal before settlement | Lifecycle violation |
| Commitment after settlement | Timing violation |
| Client-supplied commitment_hash | Trust violation |
| Client-supplied outcome | Trust violation |
| Client-supplied closing_odds | Trust violation |
| Client-supplied P&L | Trust violation |
| Client-supplied CLV | Trust violation |
| Cross-user commitment | Ownership violation |
| Cross-user reveal | Ownership violation |

## Web3 Readiness

Blockchain fields on both tables are nullable:
- `chain_id` — target chain identifier
- `contract_address` — attestation contract
- `tx_hash` — transaction hash
- `block_number` — block number

These remain NULL until on-chain submission occurs. The platform functions fully without blockchain infrastructure.

## Provenance Chain

```
strategy_version → model_version → feature_version → dataset_version
                                                           ↓
                                                         match
                                                           ↓
                                                       prediction
                                                           ↓
                                                   attestation_commitment
                                                           ↓
                                                       settlement
                                                           ↓
                                                   attestation_reveal
                                                           ↓
                                                       broadcast
```

All relationships are queryable through foreign keys. No redundant copies of authoritative data.
