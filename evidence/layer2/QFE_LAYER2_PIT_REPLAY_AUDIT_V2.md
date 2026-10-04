# QFE V2 Layer 2 — PIT Horizon Replay Audit V2

Audit hash: e69229c1cfc6bee09d29a92a202fd5c0a412e238b864a512bd8e15b48b25198d

Status: PASS — DEVELOPMENT REPLAY ONLY

- Corpus manifest identical: True
- PIT manifest identical: True
- Successor artifact rebuild: EXACT
- Protected outcomes read: False
- Market odds used: False

## Goals
- Dynamic NLL: 1.455400496 -> 1.455381817 (delta -0.000018679)
- Dynamic-vs-climatology NLL advantage: 0.015567260 -> 0.015564462 (delta -0.000002798)

## Corners
- Dynamic NLL: 2.402072704 -> 2.402117846 (delta +0.000045141)
- Dynamic-vs-climatology NLL advantage: 0.027385756 -> 0.027380117 (delta -0.000005640)

## Interpretation
The repaired horizon has a very small numerical effect at Layer 2, but the successor artifact is the valid basis for downstream replay. No threshold, hyperparameter, or model choice was changed after observing these results.

Next gate: Layer 3 replay under the repaired PIT semantics.
