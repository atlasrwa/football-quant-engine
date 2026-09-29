# Three-family evidence and research scope V1

Implements the 2026-09-29 scope decision in an isolated research branch based on frozen V3 f60ef8a. No existing V3 or production module is modified.

## Implemented

- Offline-only reader of the existing provider cache, without a provider client import.
- All provider stat leaves retained with exact paths and nulls, including half splits; 258 numeric paths observed in this cache. Unverified names are not promoted to canonical unit semantics.
- Nine raw target views: goals/corners/provider-native yellow cards, each home/away/total. Cards remain blocked from bookmaker interpretation until settlement semantics are verified.
- Neutral-site unknowns and historical manager/context fields preserved, without claiming pre-match availability.
- Full file hashes and original capture metadata, stats identity/hash checks, conflicting fixture version rejection, and deterministic output digest.
- Period reconciliation flags; extra-time/ambiguous-duration counts remain separate from regulation candidates.
- Separate research registry and validation gates for each market. No inherited promotion.

## Observed cache support

560 fixtures in one competition. Goals: 560; corners: 220; provider-native yellow cards: 216, for each team side and total. Of corner-count records, 214 have explicitly no extra time/penalties; for yellow cards, 210. These are raw coverage counts, not final training eligibility.

Twelve matches have additive half/full mismatches in the checked fields: six have unresolved/extra-time duration and six have no extra time recorded. Investigate the latter before using affected half-level features. Presence is not proof of valid half-level data.

## Execution and evidence

Run from repository root:

```bash
python3 -m unittest discover -s research/three_family_evidence -p 'test_*.py' -v
python3 research/three_family_evidence/build_evidence.py --cache /home/ubuntu/data/v3_pilot/provider_cache --output /path/to/new-output-directory
```

The output directory must not exist. Input caches are read only. Seven boundary/regression tests passed. Output digest is recorded in out/v1/coverage.json; the full immutable derived evidence is in out/v1/evidence.jsonl. Input cache misses remain missing and never trigger a network request.

## Remaining work and promotion boundaries

This is the data/research foundation, not a trained richer pilot. No lagged feature matrix, hypothesis effect estimate, trained model, calibration fit, market comparison or prospective commitment has been produced. The raw rows explicitly declare prediction_input_eligible=false. They must not be passed directly into a predictor.

Before fitting: resolve period/booking semantics, verify historical manager fidelity, define chronological lagged profiles and bounded hypotheses, and register all currently-null evaluation choices. Retrospective reconstruction cannot be represented as original point-in-time replay. Match outcomes and same-match stats are never prediction inputs for that match.

Use the accompanying SOURCE_OF_TRUTH.md and research_registry.json for independent M1/M2/M2+H evaluation. Preserve prior frozen results and do not backdate successor predictions. All markets remain DEVELOPMENT_ONLY/NOT_EVALUATED; models fitted=0, promotions=0, live calls=0. Keep production CHAMPION and capture jobs unchanged.
