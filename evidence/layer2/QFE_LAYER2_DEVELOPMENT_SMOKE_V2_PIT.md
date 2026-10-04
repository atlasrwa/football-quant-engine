# QFE V2 Layer 2 — Development Smoke Evidence

Frozen on: 2026-10-03
Bundle hash: `815b6d4d6db3f76f691f7046d840c710060d7643ea7f0b66051bf2a70f675454`

> **DEVELOPMENT ONLY.** This is not a promoted model, calibration result,
> protected OOS result, market-edge claim, or commercial validation.

## Multi-season corpus

- Matches: **5640**
- Competitions: **6**
- Seasons: **19**
- Source files: **5655**
- Corpus manifest: `bde8a51688674f0ca5d7b17426327cc55d5d44ce4106443eb1a2f5b780419e22`
- PIT manifest: `6aeb680aa82e1a9468a44396eab41e33bc7e3daefab8ace6ad17aa11ca8085e8`

## Benchmark design

The dynamic hierarchy is compared with a competition-only dynamic
climatology using the same decay/prior settings but `team_influence=0`.
Both are availability-gated at the registered T-6h horizon with a 6h
reconstructed post-match embargo, and same-kickoff batched. No odds are inputs.

The current distribution is independent Poisson and exists only as the
first conservative benchmark. Goals dependence and corners
overdispersion are later Layer 3 candidates.

## Goals

- Predictions: **5640**
- Usable outcomes: **5640**
- Missing/excluded outcomes: **0**
- Supported: **4806 (85.21%)**
- Mean effective support: **8.375**
- Side-count Poisson NLL — dynamic: **1.455382**
- Side-count Poisson NLL — climatology: **1.470946**
- NLL delta (climatology - dynamic): **+0.015564**
- Side-count MAE — dynamic: **0.905940**
- Side-count MAE — climatology: **0.926929**
- MAE delta (climatology - dynamic): **+0.020989**

### By competition

| Competition | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| comp_0256 | 647 | 1.540212 | 1.562632 | +0.022420 |
| comp_0976 | 979 | 1.438195 | 1.445197 | +0.007001 |
| comp_3039 | 800 | 1.490686 | 1.508253 | +0.017567 |
| comp_8321 | 1737 | 1.430747 | 1.444084 | +0.013337 |
| comp_8814 | 811 | 1.426685 | 1.456150 | +0.029464 |
| comp_9777 | 666 | 1.455023 | 1.462993 | +0.007971 |

### By support bucket

| Effective support | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| 0-<3 | 834 | 1.486178 | 1.493453 | +0.007276 |
| 3-<5 | 517 | 1.431589 | 1.444606 | +0.013017 |
| 5-<10 | 2112 | 1.467631 | 1.487005 | +0.019373 |
| 10+ | 2177 | 1.437351 | 1.453000 | +0.015650 |

### Weakest season deltas (preserved, not tuned away)

| Season | N | Delta |
|---|---:|---:|
| sn_3014533 | 81 | -0.006931 |
| sn_3057202 | 306 | +0.003779 |
| sn_8425423 | 462 | +0.005502 |
| sn_8437950 | 462 | +0.006101 |
| sn_3064530 | 552 | +0.008490 |

## Corners

- Predictions: **5640**
- Usable outcomes: **5609**
- Missing/excluded outcomes: **31**
- Supported: **4804 (85.18%)**
- Mean effective support: **8.306**
- Side-count Poisson NLL — dynamic: **2.402118**
- Side-count Poisson NLL — climatology: **2.429498**
- NLL delta (climatology - dynamic): **+0.027380**
- Side-count MAE — dynamic: **2.135420**
- Side-count MAE — climatology: **2.178681**
- MAE delta (climatology - dynamic): **+0.043261**

### By competition

| Competition | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| comp_0256 | 645 | 2.431116 | 2.461795 | +0.030679 |
| comp_0976 | 979 | 2.340928 | 2.348034 | +0.007106 |
| comp_3039 | 800 | 2.453281 | 2.498098 | +0.044817 |
| comp_8321 | 1716 | 2.424142 | 2.452437 | +0.028295 |
| comp_8814 | 808 | 2.379921 | 2.416867 | +0.036945 |
| comp_9777 | 661 | 2.372485 | 2.391502 | +0.019017 |

### By support bucket

| Effective support | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| 0-<3 | 834 | 2.466830 | 2.477505 | +0.010675 |
| 3-<5 | 521 | 2.416184 | 2.441338 | +0.025154 |
| 5-<10 | 2121 | 2.376591 | 2.407297 | +0.030706 |
| 10+ | 2133 | 2.398763 | 2.429911 | +0.031148 |

### Weakest season deltas (preserved, not tuned away)

| Season | N | Delta |
|---|---:|---:|
| sn_3014533 | 81 | -0.006249 |
| sn_8425423 | 462 | -0.001619 |
| sn_8437950 | 462 | +0.013057 |
| sn_3057202 | 303 | +0.017058 |
| sn_3064056 | 304 | +0.019336 |

## Interpretation

A positive NLL delta means the dynamic hierarchy had lower side-count
Poisson NLL than the competition-only climatology on this development
walk-forward. This is useful evidence that team/opponent state contains
signal, but it is not sufficient for model promotion.

Next scientific gate: freeze chronological development/calibration/protected
folds, then compare structured distribution families and candidate
hyperparameters without using protected outcomes for selection.
