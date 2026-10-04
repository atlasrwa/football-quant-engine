# QFE V2 Layer 2 — Development Smoke Evidence

Frozen on: 2026-10-04
Bundle hash: `bc1f02f7f39450c0e71025fc0b7af814ae80b4e7bd2c247a3e611e1144ec3ef7`

> **DEVELOPMENT ONLY.** This is not a promoted model, calibration result,
> protected OOS result, market-edge claim, or commercial validation.

## Multi-season corpus

- Matches: **5640**
- Competitions: **6**
- Seasons: **19**
- Source files: **5655**
- Corpus manifest: bde8a51688674f0ca5d7b17426327cc55d5d44ce4106443eb1a2f5b780419e22
- PIT manifest: 6aeb680aa82e1a9468a44396eab41e33bc7e3daefab8ace6ad17aa11ca8085e8
- WARMUP state-only matches: **552**
- DEVELOPMENT scored matches: **3812**
- CALIBRATION excluded from replay input: **959**
- EXPOSED former-PROTECTED excluded from replay input: **317**

## Benchmark design

The dynamic hierarchy is compared with a competition-only dynamic
climatology using the same decay/prior settings but `team_influence=0`.
Both are availability-gated at the registered T-6h horizon with a 6h
reconstructed post-match embargo, and same-kickoff batched. WARMUP may
update state, only DEVELOPMENT outcomes are scored, and CALIBRATION plus
the exposed former-PROTECTED cohort are absent from the replay input.
No odds are inputs.

The current distribution is independent Poisson and exists only as the
first conservative benchmark. Goals dependence and corners
overdispersion are later Layer 3 candidates.

## Goals

- Predictions: **3812**
- Usable outcomes: **3812**
- Missing/excluded outcomes: **0**
- Supported: **3182 (83.47%)**
- Mean effective support: **7.640**
- Side-count Poisson NLL — dynamic: **1.450090**
- Side-count Poisson NLL — climatology: **1.465711**
- NLL delta (climatology - dynamic): **+0.015621**
- Side-count MAE — dynamic: **0.899138**
- Side-count MAE — climatology: **0.919917**
- MAE delta (climatology - dynamic): **+0.020780**

### By competition

| Competition | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| comp_0256 | 481 | 1.547142 | 1.572725 | +0.025583 |
| comp_0976 | 720 | 1.428875 | 1.431837 | +0.002962 |
| comp_3039 | 615 | 1.500733 | 1.519365 | +0.018631 |
| comp_8321 | 907 | 1.403798 | 1.418060 | +0.014262 |
| comp_8814 | 594 | 1.419055 | 1.450510 | +0.031455 |
| comp_9777 | 495 | 1.445785 | 1.449887 | +0.004102 |

### By support bucket

| Effective support | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| 0-<3 | 630 | 1.475356 | 1.484379 | +0.009024 |
| 3-<5 | 447 | 1.431318 | 1.445424 | +0.014107 |
| 5-<10 | 1604 | 1.461268 | 1.478583 | +0.017315 |
| 10+ | 1131 | 1.427583 | 1.445074 | +0.017491 |

### Weakest season deltas (preserved, not tuned away)

| Season | N | Delta |
|---|---:|---:|
| sn_8437950 | 258 | -0.001585 |
| sn_3064530 | 355 | +0.003030 |
| sn_3057202 | 306 | +0.003779 |
| sn_3064056 | 189 | +0.004624 |
| sn_8425423 | 462 | +0.005502 |

## Corners

- Predictions: **3812**
- Usable outcomes: **3783**
- Missing/excluded outcomes: **29**
- Supported: **3180 (83.42%)**
- Mean effective support: **7.562**
- Side-count Poisson NLL — dynamic: **2.394946**
- Side-count Poisson NLL — climatology: **2.421781**
- NLL delta (climatology - dynamic): **+0.026835**
- Side-count MAE — dynamic: **2.126283**
- Side-count MAE — climatology: **2.169269**
- MAE delta (climatology - dynamic): **+0.042986**

### By competition

| Competition | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| comp_0256 | 479 | 2.420094 | 2.448574 | +0.028480 |
| comp_0976 | 720 | 2.347124 | 2.349652 | +0.002528 |
| comp_3039 | 615 | 2.478584 | 2.525906 | +0.047322 |
| comp_8321 | 887 | 2.369202 | 2.396750 | +0.027548 |
| comp_8814 | 591 | 2.381921 | 2.422712 | +0.040791 |
| comp_9777 | 491 | 2.397967 | 2.415092 | +0.017125 |

### By support bucket

| Effective support | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| 0-<3 | 630 | 2.465740 | 2.476755 | +0.011016 |
| 3-<5 | 451 | 2.399564 | 2.424487 | +0.024923 |
| 5-<10 | 1610 | 2.372762 | 2.402393 | +0.029632 |
| 10+ | 1092 | 2.384905 | 2.417532 | +0.032627 |

### Weakest season deltas (preserved, not tuned away)

| Season | N | Delta |
|---|---:|---:|
| sn_8425423 | 462 | -0.001619 |
| sn_8437950 | 258 | +0.009954 |
| sn_3057202 | 303 | +0.017058 |
| sn_3064056 | 188 | +0.017233 |
| sn_3064530 | 344 | +0.019607 |

## Interpretation

A positive NLL delta means the dynamic hierarchy had lower side-count
Poisson NLL than the competition-only climatology on this development
walk-forward. This is useful evidence that team/opponent state contains
signal, but it is not sufficient for model promotion.

Next scientific gate: freeze chronological development/calibration/protected
folds, then compare structured distribution families and candidate
hyperparameters without using protected outcomes for selection.
