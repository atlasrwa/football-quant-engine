# Phase 3.4 Broadcast Trust Model

## Core Principle

A prediction is NOT automatically broadcastable. Broadcast eligibility MUST be derived from authoritative persisted state.

## Trust Gate Flow

```
prediction exists
      ↓
prediction belongs to authenticated user (ownership check)
      ↓
prediction's strategy/version has quarantine record
      ↓
quarantine status = PROMOTED (90 days + PASSED validation)
      ↓
channel is supported
      ↓
broadcast allowed
```

## What the Client Controls

- Which prediction to broadcast (prediction_id)
- Which channel to target (channel)
- Where to deliver (destination)

## What the Server Derives

- payload_hash (canonical SHA-256 of prediction content)
- deep_link (stable URL: `/predictions/{id}`)
- proof_hash (from existing prediction record)
- dispatch result (from channel adapter)
- audit event (BROADCAST_DISPATCHED or BROADCAST_FAILED)

## What the Client CANNOT Assert

- fdr_validated
- promoted status
- proof_hash
- closing_odds
- settlement outcome
- CLV
- P&L
- validation status
- payload_hash
- any trust-sensitive field

## Broadcast Lifecycle

```
PREDICTION
     │
     ├── Channel: web      → status: DELIVERED
     ├── Channel: mobile   → status: DISPATCHED
     ├── Channel: telegram → status: DISPATCHED (or FAILED if no destination)
     ├── Channel: discord  → status: DISPATCHED (or FAILED if no destination)
     ├── Channel: email    → status: DISPATCHED (or FAILED if no destination)
     └── Channel: webhook  → status: DISPATCHED (or FAILED if no destination)
```

## Idempotency

One broadcast per (prediction_id, channel, destination). The combination is unique:
- Same prediction to "web" with no destination → one record
- Same prediction to "telegram" with "@channel1" → one record
- Same prediction to "telegram" with "@channel2" → different record

Duplicate requests return the existing record without side effects.

## Payload Canonicalization

The broadcast payload hash is computed from:

```json
{
  "confidence": <float>,
  "direction": "<string>",
  "entry_odds": <float|null>,
  "match_id": <int>,
  "prediction_id": "<uuid>",
  "prediction_timestamp": "<iso8601>",
  "proof_hash": "<64-char-hex>",
  "strategy_id": "<uuid>",
  "strategy_version": <int>
}
```

Rules:
- sort_keys=True
- separators=(",",":")
- UTF-8 encoding
- SHA-256 hex digest

Equivalent payloads ALWAYS produce identical hashes.
