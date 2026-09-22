"""ITEM 6 Stage-1 deterministic point-in-time (PIT) evidence packet materializer.

`item6_evidence_packet_materializer_v1`. ZERO PAID INFERENCE. Importing or running this
module makes NO network call and NO LLM call. It is a pure deterministic function of:

    * the frozen fixture identity (from the frozen Stage-1 cohort manifest),
    * the frozen point-in-time cutoff (== the fixture's frozen kickoff_unix),
    * the frozen FootyStats discovery corpus content on disk,
    * this frozen materializer source.

WHY THIS EXISTS
The frozen Item 6 mechanism prompt tells the model it receives "(a) a deterministic
pre-target evidence packet and (b) abstract baseline-coverage statements", and its HARD
RULES require every mechanism to cite `evidence_ref` ids drawn from that packet and to
reference only observables present in the packet's vocabulary. The frozen live path shipped
with an EMPTY evidence_packet ({}), which is scientifically invalid: it cannot test grounded
mechanism discovery. This materializer builds the intended packet, PIT-safely, from
provider-supported historical data, WITHOUT changing the prompt, schema, gate, or cohort.

PROVIDER POLICY (single provider, no cross-provider merge)
The Item 6 cohort is keyed on FootyStats numeric match ids (cohort.source_fixture_id ==
record.id in data/discovery/corpus/league-matches_*.json). FootyStats and TheStatsAPI share
no join key in this project and their identically-named fields are non-equivalent
(capability.DO_NOT_MERGE). So the packet is built end-to-end from ONE provider: FootyStats.
np_expected_goals (npxG) is TheStatsAPI-only and excluded upstream; `xg` is not in the Item 6
provider vocabulary and the two providers' xg are non-equivalent. Neither is ever surfaced.

POINT-IN-TIME DISCIPLINE (fail-closed)
The cutoff for a fixture is EXACTLY its frozen kickoff_unix. Every observation contributing
to the packet is a completed match with date_unix STRICTLY LESS THAN the cutoff. The target
match itself, any same/later-kickoff match, and any market/lineup/future data are never read.
The target's own record is used ONLY for neutralized identity (team ids, competition,
kickoff) -- never for any statistic.

DETERMINISM
Aggregates are means over strictly-prior populated observations (NULL != ZERO; the FootyStats
-1 sentinel is treated as missing). Values are rounded to 3 decimals. Evidence items are
ordered by a frozen VALUE-INDEPENDENT canonical key (team_role, then metric alphabetically
from a frozen registry, then perspective, period, venue_scope, window) -- never by value,
sample size, variance, or any salience. The packet is canonicalized (sorted keys, tight
separators) and content-hashed.

WHAT THE PACKET NEVER CONTAINS
candidate ids, deterministic salience/rank, OOS outcomes, market/odds, p_model, numeric
reliability/shrinkage weights, LLM similarity scores, the target's own statistics, or any
future information. See ITEM6_STAGE1_EVIDENCE_PACKET_CONTRACT_V1.json.
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

MATERIALIZER_VERSION = "item6_evidence_packet_materializer_v1"
PROVIDER = "footystats"
PROVIDER_NORMALIZATION_VERSION = "item6_evidence_footystats_pit_v1"
CONTRACT_VERSION = "item6_stage1_evidence_packet_contract_v1"

ROOT_DEFAULT = "/home/ubuntu"
CORPUS_GLOB = "data/discovery/corpus/league-matches_*.json"

NULL_SENTINEL = -1

# --- frozen canonical metric registry (value-neutral ascending alphabetical) --------------
# Only metrics with a genuine FootyStats source AND membership in the frozen Item 6 provider
# vocabulary appear here. TheStatsAPI-only vocab metrics and formation/lineup are omitted.
METRIC_REGISTRY: Tuple[str, ...] = (
    "cards_2h",
    "corner_kicks",
    "fouls",
    "goals",
    "offsides",
    "possession",
    "red_cards",
    "shots",
    "shots_on_target",
    "yellow_cards",
)

# canonical metric -> FootyStats per-side field base (team_a_<base> / team_b_<base>) and the
# resolution/half fields it supports. "__goals__" is special-cased (uses goal-count fields).
FULL_MATCH_FIELD: Dict[str, str] = {
    "shots": "shots",
    "shots_on_target": "shotsOnTarget",
    "corner_kicks": "corners",
    "possession": "possession",
    "fouls": "fouls",
    "yellow_cards": "yellow_cards",
    "red_cards": "red_cards",
    "offsides": "offsides",
    "goals": "__goals__",
    "cards_2h": "2h_cards",
}
# metrics that also support first/second-half aggregates, with their half field bases.
HALF_FIELDS: Dict[str, Dict[str, str]] = {
    "corner_kicks": {"FIRST_HALF": "fh_corners", "SECOND_HALF": "2h_corners"},
    "goals": {"FIRST_HALF": "__ht_goals__", "SECOND_HALF": "__2h_goals__"},
}
# cards_2h is itself a second-half construction; expose it only as SECOND_HALF FULL count.
CARDS_2H_PERIOD = "SECOND_HALF"

WINDOW_ALL = "ALL_PRIOR"
WINDOW_RECENT = "RECENT_5"
RECENT_N = 5

PERSPECTIVE_FOR = "FOR"
PERSPECTIVE_AGAINST = "AGAINST"
PERSPECTIVE_NEUTRAL = "NEUTRAL"

VENUE_ALL = "ALL"
VENUE_HOME = "HOME"
VENUE_AWAY = "AWAY"

TEAM_A = "TEAM_A"
TEAM_B = "TEAM_B"
COMPETITION_CONTEXT = "COMPETITION_CONTEXT"

# canonical order tokens (frozen; value-independent)
_TEAM_ROLE_ORDER = {TEAM_A: 0, TEAM_B: 1, COMPETITION_CONTEXT: 2}
_PERSPECTIVE_ORDER = {PERSPECTIVE_FOR: 0, PERSPECTIVE_AGAINST: 1, PERSPECTIVE_NEUTRAL: 2}
_PERIOD_ORDER = {"FULL_MATCH": 0, "FIRST_HALF": 1, "SECOND_HALF": 2}
_VENUE_ORDER = {VENUE_ALL: 0, VENUE_HOME: 1, VENUE_AWAY: 2}
_WINDOW_ORDER = {WINDOW_ALL: 0, WINDOW_RECENT: 1}
_METRIC_ORDER = {m: i for i, m in enumerate(METRIC_REGISTRY)}


class MaterializationError(RuntimeError):
    """Raised (fail closed) when a fixture cannot be materialized into a valid PIT packet."""


# ------------------------------- corpus loading -------------------------------------------
@dataclass
class _Corpus:
    by_id: Dict[str, dict]
    by_team: Dict[str, List[dict]]  # team_id -> chronological completed matches


def _is_complete(m: dict) -> bool:
    return str(m.get("status")) == "complete" and m.get("date_unix") is not None \
        and m.get("homeID") is not None and m.get("awayID") is not None


def load_corpus(root: str = ROOT_DEFAULT) -> _Corpus:
    """Load the FootyStats discovery corpus into deterministic indices. No network, no LLM."""
    by_id: Dict[str, dict] = {}
    for f in sorted(glob.glob(f"{root}/{CORPUS_GLOB}")):
        try:
            d = json.load(open(f))
        except Exception:  # noqa: BLE001
            continue
        data = d.get("data") if isinstance(d, dict) else d
        if not isinstance(data, list):
            continue
        for m in data:
            mid = str(m.get("id"))
            if mid and mid not in by_id:
                by_id[mid] = m
    by_team: Dict[str, List[dict]] = {}
    for m in by_id.values():
        if not _is_complete(m):
            continue
        for tid in (str(m["homeID"]), str(m["awayID"])):
            by_team.setdefault(tid, []).append(m)
    # deterministic chronological order; tie-break by numeric id for stability.
    for tid in by_team:
        by_team[tid].sort(key=lambda x: (int(x["date_unix"]), int(x["id"])))
    return _Corpus(by_id=by_id, by_team=by_team)


# ------------------------------- value extraction -----------------------------------------
def _clean(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f == NULL_SENTINEL:
        return None
    return f


def _side_of(m: dict, team_id: str) -> Optional[str]:
    """Return 'a' if team is the home side (team_a), 'b' if away side (team_b), else None."""
    if str(m.get("homeID")) == team_id:
        return "a"
    if str(m.get("awayID")) == team_id:
        return "b"
    return None


def _full_match_value(m: dict, side: str, metric: str, perspective: str) -> Optional[float]:
    """FULL_MATCH FOR/AGAINST value for a metric from one team's viewpoint in match m.

    FOR reads the team's own side; AGAINST reads the opponent's side (what was conceded/
    allowed). goals uses homeGoalCount/awayGoalCount; other metrics use team_a_/team_b_.
    """
    own = side
    opp = "b" if side == "a" else "a"
    read_side = own if perspective == PERSPECTIVE_FOR else opp
    if metric == "goals":
        key = "homeGoalCount" if read_side == "a" else "awayGoalCount"
        return _clean(m.get(key))
    base = FULL_MATCH_FIELD[metric]
    return _clean(m.get(f"team_{read_side}_{base}"))


def _half_value(m: dict, side: str, metric: str, perspective: str,
                period: str) -> Optional[float]:
    """FIRST_HALF/SECOND_HALF value for metrics that genuinely support halves."""
    own = side
    opp = "b" if side == "a" else "a"
    read_side = own if perspective == PERSPECTIVE_FOR else opp
    if metric == "goals":
        if period == "FIRST_HALF":
            key = f"ht_goals_team_{read_side}"
        else:  # SECOND_HALF
            key = f"goals_2hg_team_{read_side}"
        return _clean(m.get(key))
    if metric == "corner_kicks":
        base = HALF_FIELDS["corner_kicks"][period]
        return _clean(m.get(f"team_{read_side}_{base}"))
    return None


def _cards_2h_value(m: dict, side: str, perspective: str) -> Optional[float]:
    own = side
    opp = "b" if side == "a" else "a"
    read_side = own if perspective == PERSPECTIVE_FOR else opp
    return _clean(m.get(f"team_{read_side}_2h_cards"))


# ------------------------------- aggregation ----------------------------------------------
def _reliability(n: int) -> str:
    if n < 5:
        return "THIN"
    if n < 12:
        return "MODERATE"
    return "AMPLE"


def _mean(values: List[float]) -> float:
    return round(sum(values) / len(values), 3)


@dataclass
class _Cell:
    metric: str
    perspective: str
    period: str
    venue_scope: str
    window: str
    value: float
    sample_n: int


def _prior_matches(corpus: _Corpus, team_id: str, cutoff_unix: int) -> List[dict]:
    """Strictly-prior completed matches for the team, chronological. PIT-safe by construction."""
    return [m for m in corpus.by_team.get(team_id, []) if int(m["date_unix"]) < cutoff_unix]


def _venue_filter(matches: List[dict], team_id: str, venue: str) -> List[dict]:
    if venue == VENUE_ALL:
        return matches
    want_home = venue == VENUE_HOME
    out = []
    for m in matches:
        is_home = str(m.get("homeID")) == team_id
        if is_home == want_home:
            out.append(m)
    return out


def _value_for(m: dict, team_id: str, metric: str, perspective: str,
               period: str) -> Optional[float]:
    side = _side_of(m, team_id)
    if side is None:
        return None
    if metric == "cards_2h":
        return _cards_2h_value(m, side, perspective)
    if period == "FULL_MATCH":
        return _full_match_value(m, side, metric, perspective)
    return _half_value(m, side, metric, perspective, period)


def _iter_metric_specs() -> List[Tuple[str, str]]:
    """Yield (metric, period) pairs the contract permits, in registry order."""
    specs: List[Tuple[str, str]] = []
    for metric in METRIC_REGISTRY:
        if metric == "cards_2h":
            specs.append((metric, CARDS_2H_PERIOD))
            continue
        specs.append((metric, "FULL_MATCH"))
        for period in ("FIRST_HALF", "SECOND_HALF"):
            if metric in HALF_FIELDS and period in HALF_FIELDS[metric]:
                specs.append((metric, period))
    return specs


def _scope_grid(metric: str, period: str, perspective: str) -> List[Tuple[str, str]]:
    """Frozen, value-independent (venue_scope, window) grid per (metric, period, perspective).

    Principled compact scope set that preserves representational richness while bounding
    packet bytes (chosen STRUCTURALLY, never from any outcome):
      * FULL_MATCH, FOR:     ALLxALL_PRIOR, HOMExALL_PRIOR, AWAYxALL_PRIOR, ALLxRECENT_5
                             (own production with venue + recency context).
      * FULL_MATCH, AGAINST: ALLxALL_PRIOR, ALLxRECENT_5
                             (concession level + concession form; venue splits omitted on the
                             AGAINST side to bound size, since attack venue-context already
                             exposes venue behavior).
      * FIRST_HALF/SECOND_HALF (incl. cards_2h): ALLxALL_PRIOR for BOTH FOR and AGAINST
                             (within-match state, both perspectives, no venue/recency split).
    This keeps: both teams, attack (FOR) AND defense (AGAINST), venue context, recency
    context, half/state context, and all metric families -- enabling cross-metric and
    cross-perspective reasoning -- without a full combinatorial cross-product.
    """
    if period == "FULL_MATCH":
        if perspective == PERSPECTIVE_FOR:
            return [(VENUE_ALL, WINDOW_ALL), (VENUE_HOME, WINDOW_ALL),
                    (VENUE_AWAY, WINDOW_ALL), (VENUE_ALL, WINDOW_RECENT)]
        return [(VENUE_ALL, WINDOW_ALL), (VENUE_ALL, WINDOW_RECENT)]
    return [(VENUE_ALL, WINDOW_ALL)]


def _window_matches(venue_matches: List[dict], window: str) -> List[dict]:
    if window == WINDOW_RECENT:
        return venue_matches[-RECENT_N:]
    return venue_matches


def _team_cells(corpus: _Corpus, team_id: str, cutoff_unix: int) -> List[_Cell]:
    """All non-empty evidence cells for a team, PIT-safe. Perspectives FOR & AGAINST over a
    frozen compact (venue_scope, window) grid per (metric, period)."""
    prior_all = _prior_matches(corpus, team_id, cutoff_unix)
    cells: List[_Cell] = []
    perspectives = (PERSPECTIVE_FOR, PERSPECTIVE_AGAINST)
    for metric, period in _iter_metric_specs():
        for perspective in perspectives:
            for venue, window in _scope_grid(metric, period, perspective):
                venue_matches = _venue_filter(prior_all, team_id, venue)
                win_matches = _window_matches(venue_matches, window)
                vals = [v for m in win_matches
                        if (v := _value_for(m, team_id, metric, perspective, period)) is not None]
                if vals:
                    cells.append(_Cell(metric, perspective, period, venue, window,
                                       _mean(vals), len(vals)))
    return cells


def _competition_cells(corpus: _Corpus, competition_id: str, cutoff_unix: int,
                       metrics_present: set) -> List[_Cell]:
    """Competition-environment reference means (NEUTRAL perspective, FULL_MATCH, ALL venue,
    ALL_PRIOR) computed over all strictly-prior matches in the same competition. Only for
    metrics already present in at least one team's cells (no fabricated capability)."""
    prior = [m for m in corpus.by_id.values()
             if _is_complete(m) and str(m.get("competition_id")) == str(competition_id)
             and int(m["date_unix"]) < cutoff_unix]
    cells: List[_Cell] = []
    for metric in METRIC_REGISTRY:
        if metric not in metrics_present:
            continue
        if metric == "cards_2h":
            period = CARDS_2H_PERIOD
        else:
            period = "FULL_MATCH"
        # environment mean = mean over BOTH sides' FOR values (per-team-match production).
        vals: List[float] = []
        for m in prior:
            for side_team in (str(m.get("homeID")), str(m.get("awayID"))):
                v = _value_for(m, side_team, metric, PERSPECTIVE_FOR, period)
                if v is not None:
                    vals.append(v)
        if vals:
            cells.append(_Cell(metric, PERSPECTIVE_NEUTRAL, period, VENUE_ALL, WINDOW_ALL,
                               _mean(vals), len(vals)))
    return cells


# ------------------------------- evidence items -------------------------------------------
def _evidence_ref(team_role: str, cell: _Cell) -> str:
    return (f"E:{team_role}:{cell.metric}:{cell.perspective}:{cell.period}:"
            f"{cell.venue_scope}:{cell.window}")


_RELIABILITY_CODE = {"THIN": 0, "MODERATE": 1, "AMPLE": 2}


def _canonical_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def packet_hash(packet_body: Dict[str, Any]) -> str:
    body = {k: v for k, v in packet_body.items() if k != "packet_sha256"}
    return hashlib.sha256(_canonical_bytes(body)).hexdigest()


def _source_summary(prior_matches: List[dict]) -> Dict[str, Any]:
    if not prior_matches:
        return {"provider": PROVIDER, "normalization_version": PROVIDER_NORMALIZATION_VERSION,
                "n_source_matches": 0, "min_source_kickoff_unix": None,
                "max_source_kickoff_unix": None}
    kos = [int(m["date_unix"]) for m in prior_matches]
    return {
        "provider": PROVIDER,
        "normalization_version": PROVIDER_NORMALIZATION_VERSION,
        "n_source_matches": len(prior_matches),
        "min_source_kickoff_unix": min(kos),
        "max_source_kickoff_unix": max(kos),
    }


# ------------------------------- public API -----------------------------------------------
def materialize_item6_evidence_packet(fixture: Dict[str, Any], cutoff_unix: int,
                                      corpus: Optional[_Corpus] = None,
                                      root: str = ROOT_DEFAULT) -> Dict[str, Any]:
    """Deterministically materialize the PIT evidence packet for one Stage-1 fixture.

    `fixture` is the frozen cohort entry (fixture_id, source_fixture_id, home_id, away_id,
    competition, kickoff_unix). `cutoff_unix` MUST equal fixture['kickoff_unix'] (the frozen
    target kickoff) -- passing anything else is a fail-closed error, since the cutoff is a
    frozen property of the fixture, not a live-time choice.

    Returns a JSON-serializable packet dict carrying its own packet_sha256. Never calls an
    LLM; never reads the target's own statistics, any market, or any future data.
    """
    if corpus is None:
        corpus = load_corpus(root)

    fx_kickoff = int(fixture["kickoff_unix"])
    if int(cutoff_unix) != fx_kickoff:
        raise MaterializationError(
            f"{fixture.get('fixture_id')}: cutoff {cutoff_unix} != frozen kickoff {fx_kickoff}; "
            "the PIT cutoff must equal the frozen target kickoff.")
    cutoff = fx_kickoff

    home_id = str(fixture["home_id"])
    away_id = str(fixture["away_id"])
    competition_id = str(fixture.get("competition", "")).replace("comp_", "")

    # PIT-safe prior matches per team (strictly before cutoff).
    home_prior = _prior_matches(corpus, home_id, cutoff)
    away_prior = _prior_matches(corpus, away_id, cutoff)
    if not home_prior or not away_prior:
        raise MaterializationError(
            f"{fixture.get('fixture_id')}: insufficient strictly-prior matches "
            f"(home={len(home_prior)}, away={len(away_prior)}).")

    home_cells = _team_cells(corpus, home_id, cutoff)
    away_cells = _team_cells(corpus, away_id, cutoff)
    if not home_cells or not away_cells:
        raise MaterializationError(
            f"{fixture.get('fixture_id')}: no populated evidence cells for a team side.")

    metrics_present = {c.metric for c in home_cells} | {c.metric for c in away_cells}
    comp_cells = _competition_cells(corpus, competition_id, cutoff, metrics_present)

    # frozen value-independent canonical ordering over ALL cells (for evidence_order + refs).
    def _cell_sort_key(pair: Tuple[str, _Cell]) -> Tuple:
        role, c = pair
        return (_TEAM_ROLE_ORDER[role], _METRIC_ORDER[c.metric],
                _PERSPECTIVE_ORDER[c.perspective], _PERIOD_ORDER[c.period],
                _VENUE_ORDER[c.venue_scope], _WINDOW_ORDER[c.window])

    ordered_pairs: List[Tuple[str, _Cell]] = (
        [(TEAM_A, c) for c in home_cells]
        + [(TEAM_B, c) for c in away_cells]
        + [(COMPETITION_CONTEXT, c) for c in comp_cells])
    ordered_pairs.sort(key=_cell_sort_key)

    ref_index: Dict[str, Dict[str, Any]] = {}
    evidence_map: Dict[str, List[Any]] = {}
    evidence_order: List[str] = []
    for role, c in ordered_pairs:
        ref = _evidence_ref(role, c)
        if ref in evidence_map:
            raise MaterializationError(
                f"{fixture.get('fixture_id')}: duplicate evidence_ref {ref} (fail closed).")
        evidence_map[ref] = [c.value, c.sample_n, _RELIABILITY_CODE[_reliability(c.sample_n)]]
        evidence_order.append(ref)
        ref_index[ref] = {
            "evidence_ref": ref, "team_role": role, "metric": c.metric,
            "perspective": c.perspective, "period": c.period,
            "venue_scope": c.venue_scope, "window": c.window,
            "value": c.value, "sample_n": c.sample_n,
            "reliability": _reliability(c.sample_n),
        }

    # observable vocabulary = metrics that actually produced >=1 evidence item.
    observable_vocabulary = sorted({v["metric"] for v in ref_index.values()})

    packet_body: Dict[str, Any] = {
        "packet_version": MATERIALIZER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "provider": PROVIDER,
        "provider_normalization_version": PROVIDER_NORMALIZATION_VERSION,
        "fixture_id": fixture["fixture_id"],
        "information_cutoff_unix": cutoff,
        "legend": {
            "note": ("Each entry in `evidence` maps a unique evidence_ref to a compact tuple "
                     "[value, sample_n, reliability_code]. value is a deterministic historical "
                     "MEAN of a provider metric over strictly-pre-kickoff matches (NULL!=ZERO) "
                     "-- a descriptive average ONLY, never a probability, effect, odds, or "
                     "prediction. Cite evidence_ref ids in your mechanisms. `evidence_order` "
                     "lists refs in the frozen value-neutral order."),
            "evidence_tuple_positions": ["value", "sample_n", "reliability_code"],
            "reliability_code": {"0": "THIN (sample_n<5)", "1": "MODERATE (5<=sample_n<12)",
                                 "2": "AMPLE (sample_n>=12)"},
            "evidence_ref_format": ("E:<team_role>:<metric>:<perspective>:<period>:"
                                    "<venue_scope>:<window>"),
            "team_role": {"TEAM_A": "target home team", "TEAM_B": "target away team",
                          "COMPETITION_CONTEXT": "competition environment reference"},
            "perspective": {"FOR": "produced by the team",
                            "AGAINST": "conceded/allowed by the team",
                            "NEUTRAL": "competition environment reference mean"},
            "period": {"FULL_MATCH": "whole match", "FIRST_HALF": "first half",
                       "SECOND_HALF": "second half"},
            "window": {"ALL_PRIOR": "all strictly-prior matches",
                       "RECENT_5": "5 most recent strictly-prior matches"},
            "venue_scope": {"ALL": "all venues", "HOME": "home matches only",
                            "AWAY": "away matches only"},
            "ordering": ("value-independent canonical: team_role, then metric (alphabetical "
                         "registry), perspective, period, venue_scope, window"),
        },
        "provenance": {
            "provider": PROVIDER,
            "normalization_version": PROVIDER_NORMALIZATION_VERSION,
            "information_cutoff_unix": cutoff,
            "TEAM_A": _source_summary(home_prior),
            "TEAM_B": _source_summary(away_prior),
            "COMPETITION_CONTEXT": {
                "provider": PROVIDER, "normalization_version": PROVIDER_NORMALIZATION_VERSION,
                "context_scope": "competition_environment", "competition_id": competition_id,
            } if comp_cells else None,
        },
        "fixture_identity": {
            "team_a_is_home": True,
            "competition_id": competition_id,
            "kickoff_unix": cutoff,
        },
        "observable_vocabulary": observable_vocabulary,
        "metric_registry_order": list(METRIC_REGISTRY),
        "ordering_rule": "ANTI_SALIENCE_NEUTRAL_CANONICAL",
        "n_evidence_items": len(evidence_map),
        "evidence_order": evidence_order,
        "evidence": evidence_map,
        "reads_no_target_outcome": True,
        "reads_no_future_fixture": True,
        "reads_no_market": True,
        "contains_no_candidate_ids": True,
        "contains_no_salience_or_rank": True,
    }
    packet_body["packet_sha256"] = packet_hash(packet_body)

    # fail-closed PIT self-check: no source observation at or after cutoff.
    assert_no_target_or_future_leak(packet_body, fixture, corpus)
    # attach decoded ref_index out-of-band (NOT part of the hashed/sent body) for audit/resolve.
    return packet_body


def assert_no_target_or_future_leak(packet: Dict[str, Any], fixture: Dict[str, Any],
                                    corpus: _Corpus) -> None:
    """Fail-closed verification that the packet used only strictly-prior source matches and
    never the target fixture's own record. Re-derives source windows from the corpus."""
    cutoff = int(packet["information_cutoff_unix"])
    if cutoff != int(fixture["kickoff_unix"]):
        raise MaterializationError("packet cutoff != frozen target kickoff")
    # every team source window max kickoff must be strictly before cutoff.
    prov = packet.get("provenance", {})
    for role in (TEAM_A, TEAM_B):
        src = prov.get(role) or {}
        mx = src.get("max_source_kickoff_unix")
        if mx is not None and int(mx) >= cutoff:
            raise MaterializationError(
                f"leakage: {role} source observation at/after cutoff ({mx} >= {cutoff}).")
    # the target's own match id must not appear among any team's prior matches.
    tgt = str(fixture["source_fixture_id"])
    for tid in (str(fixture["home_id"]), str(fixture["away_id"])):
        for m in _prior_matches(corpus, tid, cutoff):
            if str(m.get("id")) == tgt:
                raise MaterializationError("leakage: target match present in prior window.")


def allowed_evidence_refs(packet: Dict[str, Any]) -> List[str]:
    """The set of evidence_ref ids presented in the packet (for formalizer grounding checks)."""
    return list(packet.get("evidence", {}).keys())


def resolve_evidence_ref(ref: str) -> Dict[str, str]:
    """Deterministically decode an evidence_ref into its structured fields. Raises on a ref
    that does not match the frozen format (unresolvable)."""
    parts = ref.split(":")
    if len(parts) != 7 or parts[0] != "E":
        raise MaterializationError(f"unresolvable evidence_ref: {ref}")
    _, team_role, metric, perspective, period, venue_scope, window = parts
    return {"team_role": team_role, "metric": metric, "perspective": perspective,
            "period": period, "venue_scope": venue_scope, "window": window}


def version_stamp() -> Dict[str, Any]:
    return {
        "materializer_version": MATERIALIZER_VERSION,
        "contract_version": CONTRACT_VERSION,
        "provider": PROVIDER,
        "provider_normalization_version": PROVIDER_NORMALIZATION_VERSION,
        "n_registry_metrics": len(METRIC_REGISTRY),
        "windows": [WINDOW_ALL, WINDOW_RECENT],
        "venue_scopes": [VENUE_ALL, VENUE_HOME, VENUE_AWAY],
        "calls_llm": False,
        "reads_market": False,
        "reads_future": False,
        "single_provider": True,
    }
