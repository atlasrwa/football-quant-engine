# Phase 3.2 Content Hashing Specification

## Single Implementation

All content hashing uses **one canonical utility**: `src/persistence/hashing.py`

This module produces results **identical** to the existing domain object static methods:
- `DatasetVersion.compute_content_hash()`
- `FeatureVersion.compute_content_hash()`
- `ModelVersion.compute_content_hash()`
- `BacktestRun.compute_content_hash()`

## Canonicalization Rules

1. **Algorithm**: SHA-256
2. **Encoding**: UTF-8
3. **JSON serialization**: `json.dumps(obj, sort_keys=True, separators=(",",":"))`
4. **Array ordering**: Sorted where semantically appropriate (match IDs always sorted)
5. **Numeric representation**: Python default (no explicit rounding)
6. **Null handling**: JSON `null` for Python `None`
7. **No timestamps** in hash inputs (unless they are semantic inputs — none currently are)
8. **No database-generated fields** in hash inputs (no auto-increment IDs)
9. **UUIDs as strings** when they ARE semantic inputs (e.g., `dataset_id` in feature hash)

## Hash Definitions

### Dataset Content Hash
```
Input:  sorted list of match external IDs (integers)
Format: json.dumps(sorted(match_ids), separators=(",",":"))
Example: "[1,2,3,4,5]" → SHA-256
```

### Feature Version Hash
```
Input:  {dataset_id, xg_rolling_window, form_rolling_window,
          referee_min_matches, xmetric_coefficients}
Format: json.dumps({...}, sort_keys=True, separators=(",",":"))
```

### Model Version Hash
```
Input:  {strategy_content_hash, feature_version_id,
          train_window, test_window, step_size, min_odds, max_odds}
Format: json.dumps({...}, sort_keys=True, separators=(",",":"))
```

### Backtest Run Hash
```
Input:  {model_version_id, dataset_id}
Format: json.dumps({...}, sort_keys=True, separators=(",",":"))
Note:   Hashes INPUTS only — never outputs/results
```

## Guarantees (tested)

| Property | Test |
|----------|------|
| Same input → same hash | test_deterministic |
| Different input → different hash | test_different_*_differ |
| Order-independent (where applicable) | test_order_independent |
| Matches domain object method | test_matches_domain_object |
| Output is 64-char lowercase hex | test_is_sha256 |
| Config change detected | test_config_change_differs |
| Semantic change detected | test_strategy_change_differs |

## Security

- Content hash is **NEVER** accepted from clients
- The server computes it from the canonical inputs
- Stored in CHAR(64) columns with appropriate indexing
- Used for deduplication (UNIQUE constraints or app-level checks)
