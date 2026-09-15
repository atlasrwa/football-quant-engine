"""V7.1 provider capability contract (`v71_capability_v1`). Sections 9 and 10.

ONE deterministic layer answers "can this corpus answer this question?". No experiment module,
and certainly no LLM, may decide independently what a provider supports.

What it encodes, per metric: provider, storage block, exact provider-safe semantic definition,
FOR/AGAINST availability, temporal resolution, measured per-competition coverage, and the
resulting admissible competition set.

Three rules this layer exists to enforce, each of which has already cost a real experiment:

  * **A storage block is not a provider.** `record.base` / `.rich` / `.extra` are three places
    a single provider's values are kept. V7's first contract read them as two providers and
    pruned 33 canonical families for a provenance split that did not exist -- arm-correlated
    pruning that silently biased the primary endpoint.
  * **Unknown is not unsupported, and NULL is not zero.** A metric with no contract row is
    `UNKNOWN` (fail closed, name the gap); a contracted metric with thin coverage is
    `INSUFFICIENT_COVERAGE`. They are different findings and must not be merged.
  * **Similarly-named metrics from different providers are not poolable.** The DO_NOT_MERGE
    registry stays armed even on a single-provider corpus, because the corpus composition is
    a property of the run, not of the contract.

The restricted-universe policy is the V7.1 repair of an over-strict gate: V7 required all six
competitions at >=0.95 and therefore discarded metrics that are fully covered in a large,
well-defined subset. See `COVERAGE_POLICY` for the frozen rule and its rationale.

ZERO SPEND. Outcome-blind: nothing here reads an effect.
"""
from __future__ import annotations

import json

from src.research.hypothesis_v7 import provider as V7P

CAPABILITY_VERSION = "v71_capability_v1"

PROVIDER = V7P.THESTATSAPI
CORPUS_PROVIDER = V7P.CORPUS_PROVIDER

#: Metric semantics are REUSED verbatim from the frozen V7 contract rather than restated, so
#: the two experiments cannot drift apart on what a metric means. V7.1 changes no semantics;
#: it changes only the COVERAGE POLICY applied on top of them.
METRIC_SEMANTICS = dict(V7P.METRIC_CONTRACT)

#: Storage blocks of the single corpus provider. Asserted, never inferred from a field name.
STORAGE_BLOCKS = ("base", "rich", "extra")

#: Cross-provider hazards that must never be pooled, retained from the capability registry.
#: Armed on every run; expected never to fire while the corpus is single-provider.
DO_NOT_MERGE = (
    {"metric": "xg", "providers": ("footystats", "thestatsapi"), "correlation": 0.55},
    {"metric": "total_shots", "providers": ("footystats", "thestatsapi"),
     "correlation": 0.80},
)

# ---- statuses --------------------------------------------------------------------------
SUPPORTED = "SUPPORTED"                      # admissible on every corpus competition
RESTRICTED = "RESTRICTED"                    # admissible on a frozen SUBSET (>= policy min)
INSUFFICIENT_COVERAGE = "INSUFFICIENT_COVERAGE"
UNSUPPORTED = "UNSUPPORTED"                  # contracted but deliberately not admissible
UNKNOWN = "UNKNOWN"                          # no contract row: a NAMED capability gap

#: Coarse-to-fine ordering. A request may be no FINER than what the corpus holds.
RESOLUTION_ORDER = {"match": 0, "half": 1, "event": 2}

# ---- coverage policy -------------------------------------------------------------------
#: FROZEN coverage policy.
#:
#: `MIN_COMPETITION_COVERAGE_RATE` is carried over from V7 unchanged.
#:
#: `MIN_ADMISSIBLE_COMPETITIONS = 4` is the V7.1 change, and its rationale is structural, not
#: numerical:
#:   1. A restricted universe must remain a STRICT MAJORITY of the corpus's six competitions,
#:      so no family is ever evaluated on a minority slice of the available football.
#:   2. Four of six necessarily spans at least two of the three countries and at least two
#:      division tiers, so a restricted universe cannot be a single-country or single-tier
#:      artefact. Three of six does not guarantee either.
#:   3. Retaining >= 2/3 of the competitions keeps per-fold support within the same order of
#:      magnitude as a full-coverage family, so the frozen support minimum stays meaningful
#:      without a per-family exception.
#:
#: DISCLOSURE: the structural consequence of the threshold (how many canonical families it
#: admits) was computed on the ALREADY-VIEWED V7 universe before the threshold was fixed. That
#: quantity contains no outcome, effect or p-value -- but the ordering is recorded here rather
#: than hidden, because a reader is entitled to weigh it.
COVERAGE_POLICY = {
    "min_competition_coverage_rate": 0.95,
    "min_admissible_competitions": 4,
    "n_corpus_competitions": 6,
    "restricted_universe_allowed": True,
    "rule": ("a metric is admissible in a competition iff its measured coverage there is "
             ">= min_competition_coverage_rate; a metric is usable iff it is admissible in "
             ">= min_admissible_competitions, and the admissible set is FROZEN and reported "
             "with every result derived from it"),
    "rationale": ("strict majority of competitions; guarantees >=2 countries and >=2 tiers; "
                  "retains >=2/3 of per-fold support"),
    "coverage_is_a_function_of": "measured field population only -- never of any effect",
    "threshold_consequence_seen_before_freezing": True,
}

#: Metrics excluded by CONTRACT (semantics), independent of coverage. Kept from V7.
CONTRACT_EXCLUDED = {
    "np_xg": "per-side home/away split semantics are unaudited",
    "cards": "ambiguous (yellow vs total); must resolve to yellow_cards or red_cards",
}


class CapabilityContract:
    """The frozen, queryable capability surface. Built once from a measured coverage matrix."""

    def __init__(self, coverage_matrix: dict, policy: dict | None = None):
        self.policy = dict(policy or COVERAGE_POLICY)
        self.coverage = coverage_matrix
        self._metrics = coverage_matrix.get("metrics", {})
        self.competitions = tuple(sorted(
            {c for row in self._metrics.values()
             for c in (row.get("competition_coverage") or {})}))

    # ---- provenance invariants ---------------------------------------------------------
    def provider_of(self, metric: str) -> str:
        """Every contracted metric in this corpus comes from ONE provider. A storage block is
        never returned here -- that is the whole point of the method."""
        if metric not in METRIC_SEMANTICS:
            raise KeyError(f"no capability row for metric {metric!r}")
        return CORPUS_PROVIDER

    def storage_block_of(self, metric: str):
        return METRIC_SEMANTICS[metric].get("block")

    def resolution_of(self, metric: str):
        """The FINEST temporal resolution this corpus can answer for `metric`."""
        row = METRIC_SEMANTICS.get(metric)
        return (row or {}).get("resolution")

    def resolution_supports(self, metric: str, requested: str) -> bool:
        """True iff `requested` is no finer than what the corpus holds for `metric`.

        A match-level aggregate can never answer a half-level or event-level question. V7 had
        no such check: a half-state hypothesis about a match-level metric would have been
        answered with match aggregates, silently changing the football question.
        """
        have = self.resolution_of(metric)
        if have is None:
            return False
        return RESOLUTION_ORDER.get(str(requested).lower(), 99) <= \
            RESOLUTION_ORDER.get(str(have).lower(), -1)

    def assert_block_is_not_provider(self) -> None:
        """Regression guard: no storage-block name may ever be used as a provider name."""
        for block in STORAGE_BLOCKS:
            if block in (CORPUS_PROVIDER, V7P.FOOTYSTATS):
                raise AssertionError(f"storage block {block!r} collides with a provider name")

    def pooling_guard(self, providers_present) -> dict:
        """Fires iff a DO_NOT_MERGE pair would actually be pooled in THIS corpus."""
        present = set(providers_present)
        fired = [h for h in DO_NOT_MERGE if set(h["providers"]) <= present]
        return {"armed": True, "fired": bool(fired), "hazards": fired,
                "providers_present": sorted(present)}

    # ---- coverage ----------------------------------------------------------------------
    def admissible_competitions(self, metric: str) -> frozenset:
        row = self._metrics.get(metric)
        if not row:
            return frozenset()
        thr = self.policy["min_competition_coverage_rate"]
        return frozenset(c for c, v in (row.get("competition_coverage") or {}).items()
                         if v is not None and v >= thr)

    def classify_metric(self, metric: str):
        """-> (status, human-readable detail). The single source of truth for measurability."""
        if metric in CONTRACT_EXCLUDED:
            return (UNSUPPORTED, CONTRACT_EXCLUDED[metric])
        if metric not in METRIC_SEMANTICS:
            return (UNKNOWN, "no capability row: this corpus has never characterised the "
                             "metric; unknown is not the same as unsupported")
        row = METRIC_SEMANTICS[metric]
        if not row.get("block") or not row.get("field"):
            return (UNSUPPORTED, "contracted but has no corpus binding")
        if not row.get("audited", False):
            return (UNSUPPORTED, "per-side semantics are not audited for research use")
        adm = self.admissible_competitions(metric)
        n_all = len(self.competitions) or self.policy["n_corpus_competitions"]
        if len(adm) >= n_all:
            return (SUPPORTED, f"admissible in all {n_all} competitions")
        if len(adm) >= self.policy["min_admissible_competitions"]:
            return (RESTRICTED,
                    f"admissible in {len(adm)}/{n_all} competitions: {sorted(adm)}")
        return (INSUFFICIENT_COVERAGE,
                f"admissible in only {len(adm)}/{n_all} competitions "
                f"(minimum {self.policy['min_admissible_competitions']}): {sorted(adm)}")

    def admissible_universe(self, metrics) -> frozenset:
        """The competitions on which EVERY listed metric is admissible. A multi-metric
        hypothesis is measurable only where all of its metrics are."""
        sets = [self.admissible_competitions(m) for m in metrics]
        if not sets:
            return frozenset()
        out = sets[0]
        for s in sets[1:]:
            out = out & s
        return out

    def classify_metrics(self, metrics):
        """-> (status, admissible_competitions, per-metric detail) for a metric SET."""
        details = {m: self.classify_metric(m) for m in metrics}
        if any(s == UNKNOWN for s, _ in details.values()):
            return (UNKNOWN, frozenset(), details)
        if any(s == UNSUPPORTED for s, _ in details.values()):
            return (UNSUPPORTED, frozenset(), details)
        adm = self.admissible_universe(metrics)
        n_all = len(self.competitions) or self.policy["n_corpus_competitions"]
        if len(adm) >= n_all:
            return (SUPPORTED, adm, details)
        if len(adm) >= self.policy["min_admissible_competitions"]:
            return (RESTRICTED, adm, details)
        return (INSUFFICIENT_COVERAGE, adm, details)

    # ---- the generator-facing envelope (section 10) ------------------------------------
    def envelope(self) -> dict:
        """The machine-readable capability envelope a FUTURE generator may be shown.

        Contains semantics and coverage only. It carries NO out-of-sample outcome, NO effect
        estimate and NO ranking, so exposing it cannot leak results into hypothesis
        generation. V7.1 does NOT regenerate V6.1's hypotheses with it -- that would change
        the treatment universe to improve measurability, which the design forbids.
        """
        metrics = {}
        for m in sorted(METRIC_SEMANTICS):
            status, detail = self.classify_metric(m)
            row = METRIC_SEMANTICS[m]
            metrics[m] = {
                "status": status, "detail": detail,
                "provider": CORPUS_PROVIDER,
                "storage_block": row.get("block"),
                "semantic": row.get("semantic"),
                "unit": row.get("unit"),
                "temporal_resolution": row.get("resolution"),
                "perspectives": ["FOR", "AGAINST"],
                "admissible_competitions": sorted(self.admissible_competitions(m)),
            }
        return {"capability_version": CAPABILITY_VERSION,
                "provider": CORPUS_PROVIDER,
                "competitions": list(self.competitions),
                "policy": self.policy,
                "filter_dimensions_supported": None,   # filled by the freeze driver
                "metrics": metrics,
                "contains_outcomes": False,
                "contains_effect_estimates": False}

    def spec(self) -> dict:
        env = self.envelope()
        env["do_not_merge"] = [dict(h, providers=list(h["providers"])) for h in DO_NOT_MERGE]
        env["storage_blocks"] = list(STORAGE_BLOCKS)
        env["contract_excluded"] = dict(CONTRACT_EXCLUDED)
        return env


def version_stamp() -> dict:
    return {"capability_version": CAPABILITY_VERSION,
            "provider": CORPUS_PROVIDER,
            "metric_semantics_source": V7P.PROVIDER_VERSION,
            "n_metrics": len(METRIC_SEMANTICS),
            "storage_blocks": list(STORAGE_BLOCKS),
            "coverage_policy": COVERAGE_POLICY,
            "statuses": [SUPPORTED, RESTRICTED, INSUFFICIENT_COVERAGE, UNSUPPORTED, UNKNOWN],
            "unknown_is_not_unsupported": True,
            "null_is_not_zero": True,
            "reads_outcomes": False}
