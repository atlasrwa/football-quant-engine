# QFE successor research worktree

Read QUANT_FOOTBALL_SOURCE_OF_TRUTH.md before changing research behavior.
That document is the governing architecture for all future QFE development in this worktree.

The successor QFE is deterministic/statistical and market-disagreement focused.
Do not introduce an LLM into the probability, feature, hypothesis, calibration,
selection, or production path. The independent p_model must remain odds-blind.

Historical experiments, frozen bindings, ledgers, manifests, LLM research and
result artifacts are immutable evidence. Do not rewrite or relabel them to match
the successor architecture. A superseded experiment remains part of project history.

Default new development is offline/cached-data-only unless a later explicitly
authorized prospective phase says otherwise. Do not call provider, bookmaker,
exchange or LLM APIs merely to make a development test pass. Cache misses and
unsupported provider semantics must fail or abstain explicitly.

QFE V2 is the sole active product on `main`. The legacy CHAMPION is deprecated:
do not import, extend, deploy, publish, or recreate it as an alternative product
path. Frozen V3/V3.7/V3.8 worktrees are historical/prospective experiment
runtimes only and must remain isolated from QFE V2 development.

Optimize probability quality first (chronological OOS log loss, calibration,
Brier, coverage), then evaluate a separately frozen deterministic
market-disagreement policy against timestamp-matched no-vig market probabilities.

Do not maximize disagreement magnitude, hit rate, retrospective ROI or exposed
pilot performance. Do not change a frozen experiment after seeing protected results.
