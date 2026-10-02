# QFE V2 Layer 2 — Development Smoke Evidence

Frozen on: 2026-10-02
Bundle hash: `9fea7028abf12961990723aebb5008ab86d1f38ce08fbf3c3e2bb5feae9d9b0d`

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
Both are one-step-ahead and same-kickoff batched. No odds are inputs.

The current distribution is independent Poisson and exists only as the
first conservative benchmark. Goals dependence and corners
overdispersion are later Layer 3 candidates.

## Goals

- Predictions: **5640**
- Usable outcomes: **5640**
- Missing/excluded outcomes: **0**
- Supported: **4806 (85.21%)**
- Mean effective support: **8.375**
- Side-count Poisson NLL — dynamic: **1.455400**
- Side-count Poisson NLL — climatology: **1.470968**
- NLL delta (climatology - dynamic): **+0.015567**
- Side-count MAE — dynamic: **0.905955**
- Side-count MAE — climatology: **0.926961**
- MAE delta (climatology - dynamic): **+0.021007**

### By competition

| Competition | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| comp_0256 | 647 | 1.540282 | 1.562698 | +0.022415 |
| comp_0976 | 979 | 1.438048 | 1.445031 | +0.006983 |
| comp_3039 | 800 | 1.490858 | 1.508432 | +0.017574 |
| comp_8321 | 1737 | 1.430804 | 1.444160 | +0.013356 |
| comp_8814 | 811 | 1.426773 | 1.456290 | +0.029517 |
| comp_9777 | 666 | 1.454868 | 1.462770 | +0.007902 |

### By support bucket

| Effective support | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| 0-<3 | 834 | 1.486505 | 1.493842 | +0.007336 |
| 3-<5 | 517 | 1.431498 | 1.444499 | +0.013001 |
| 5-<10 | 2112 | 1.467610 | 1.486983 | +0.019372 |
| 10+ | 2177 | 1.437316 | 1.452954 | +0.015639 |

### Weakest season deltas (preserved, not tuned away)

| Season | N | Delta |
|---|---:|---:|
| sn_3014533 | 81 | -0.006922 |
| sn_3057202 | 306 | +0.003697 |
| sn_8425423 | 462 | +0.005479 |
| sn_8437950 | 462 | +0.006095 |
| sn_3064530 | 552 | +0.008512 |

## Corners

- Predictions: **5640**
- Usable outcomes: **5609**
- Missing/excluded outcomes: **31**
- Supported: **4804 (85.18%)**
- Mean effective support: **8.306**
- Side-count Poisson NLL — dynamic: **2.402073**
- Side-count Poisson NLL — climatology: **2.429458**
- NLL delta (climatology - dynamic): **+0.027386**
- Side-count MAE — dynamic: **2.135334**
- Side-count MAE — climatology: **2.178566**
- MAE delta (climatology - dynamic): **+0.043232**

### By competition

| Competition | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| comp_0256 | 645 | 2.430632 | 2.461121 | +0.030490 |
| comp_0976 | 979 | 2.341219 | 2.348404 | +0.007185 |
| comp_3039 | 800 | 2.453199 | 2.498008 | +0.044809 |
| comp_8321 | 1716 | 2.424088 | 2.452382 | +0.028294 |
| comp_8814 | 808 | 2.379851 | 2.416893 | +0.037042 |
| comp_9777 | 661 | 2.372467 | 2.391494 | +0.019027 |

### By support bucket

| Effective support | N | NLL dynamic | NLL climatology | Delta |
|---|---:|---:|---:|---:|
| 0-<3 | 834 | 2.466484 | 2.477152 | +0.010668 |
| 3-<5 | 521 | 2.416350 | 2.441567 | +0.025217 |
| 5-<10 | 2121 | 2.376562 | 2.407272 | +0.030710 |
| 10+ | 2133 | 2.398767 | 2.429914 | +0.031146 |

### Weakest season deltas (preserved, not tuned away)

| Season | N | Delta |
|---|---:|---:|
| sn_3014533 | 81 | -0.006236 |
| sn_8425423 | 462 | -0.001570 |
| sn_8437950 | 462 | +0.013169 |
| sn_3057202 | 303 | +0.017018 |
| sn_3064056 | 304 | +0.019377 |

## Interpretation

A positive NLL delta means the dynamic hierarchy had lower side-count
Poisson NLL than the competition-only climatology on this development
walk-forward. This is useful evidence that team/opponent state contains
signal, but it is not sufficient for model promotion.

Next scientific gate: freeze chronological development/calibration/protected
folds, then compare structured distribution families and candidate
hyperparameters without using protected outcomes for selection.
