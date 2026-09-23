"""Dual-provider LLM context pilot: deterministic pre-kickoff fixture packet (TheStatsAPI).

Builds ONE strictly pre-kickoff, provider-labelled evidence packet for a target fixture so it
can be handed to an LLM for hypothesis generation. Exploratory research only.

  * No model fit, no outcome evaluation, no LLM call, no network (the caller supplies payloads).
  * Point-in-time: every contributing historical match has kickoff < T (the target kickoff).
    The target fixture is never normalized and its stats are never read.
  * NULL != ZERO: a missing provider cell is omitted, never emitted as 0.
  * Provider-labelled: every item says provider="thestatsapi"; nothing is blended.
  * Team identity is the provider team id (tm_...). No name-based joining.
  * Field mapping reuses the repository normalizer (TheStatsAPINormalizer); the leakage checks
    re-derive every value independently from the raw payload cells.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from src.research.thestatsapi.normalizer import TheStatsAPINormalizer, _cell, parse_iso_to_unix

PACKET_BUILDER_VERSION = "dual_provider_pilot_packet_builder_v1"
CONTRACT_VERSION = "dual_provider_llm_packet_v1"
PROVIDER = "thestatsapi"
REF_PREFIX = "tsa"

ROLES = ("HOME_TEAM", "AWAY_TEAM")
WINDOW_N = {"RECENT_5": 5, "RECENT_10": 10}
RAW_RECENT_ROWS = 10
MIN_RICH_PRIOR_MATCHES = 10

#: (canonical_concept, ResearchMatch field stem, provider path, kind)
#: kind: "count" | "pct_own" (a side's own success rate) | "pct_complementary" (the two sides'
#: values sum to ~100, so AGAINST carries no information independent of FOR).
CONCEPTS: Tuple[Tuple[str, str, str, str], ...] = (
    ("goals", "goals", "fixture.score.home|away", "count"),
    ("shots", "shots", "stats.overview.total_shots.all", "count"),
    ("shots_on_target", "shots_on_target", "stats.overview.shots_on_target.all", "count"),
    ("corners", "corners", "stats.overview.corner_kicks.all", "count"),
    ("fouls", "fouls", "stats.overview.fouls.all", "count"),
    ("possession", "possession", "stats.overview.ball_possession.all", "pct_complementary"),
    ("yellow_cards", "yellow_cards", "stats.overview.yellow_cards.all", "count"),
    ("red_cards", "red_cards", "stats.overview.red_cards.all", "count"),
    ("big_chances", "big_chances", "stats.overview.big_chances.all", "count"),
    ("shots_inside_box", "shots_inside_box", "stats.shots.shots_inside_box.all", "count"),
    ("shots_outside_box", "shots_outside_box", "stats.shots.shots_outside_box.all", "count"),
    ("blocked_shots", "blocked_shots", "stats.shots.blocked_shots.all", "count"),
    ("touches_in_box", "touches_in_box", "stats.attack.touches_in_penalty_area.all", "count"),
    ("fouled_in_final_third", "fouled_in_final_third",
     "stats.attack.fouled_in_final_third.all", "count"),
    ("final_third_entries", "final_third_entries", "stats.passes.final_third_entries.all",
     "count"),
    ("accurate_crosses", "accurate_crosses", "stats.passes.accurate_crosses.all", "count"),
    ("accurate_long_balls", "accurate_long_balls", "stats.passes.accurate_long_balls.all",
     "count"),
    ("aerial_duel_pct", "aerial_duel_pct", "stats.duels.aerial_duels_percentage.all",
     "pct_complementary"),
    ("ground_duel_pct", "ground_duel_pct", "stats.duels.ground_duels_percentage.all",
     "pct_complementary"),
    ("tackles", "tackles", "stats.defending.tackles.all", "count"),
    ("tackles_won_pct", "tackles_won_pct", "stats.defending.tackles_won_percentage.all",
     "pct_own"),
    ("interceptions", "interceptions", "stats.defending.interceptions.all", "count"),
    ("clearances", "clearances", "stats.defending.clearances.all", "count"),
    ("saves", "saves", "stats.goalkeeping.saves.all", "count"),
    ("high_claims", "high_claims", "stats.goalkeeping.high_claims.all", "count"),
)
RICH_CONCEPTS = frozenset({
    "shots_inside_box", "shots_outside_box", "blocked_shots", "big_chances", "touches_in_box",
    "final_third_entries", "fouled_in_final_third", "accurate_crosses", "accurate_long_balls",
    "aerial_duel_pct", "ground_duel_pct", "tackles", "tackles_won_pct", "interceptions",
    "clearances", "saves", "high_claims"})
#: Deliberately excluded: npxG (unsupported), xG (semantics not reconciled vs npxG),
#: goals_prevented (0% populated per the existing audit).
EXCLUDED_FIELDS = ("npxg", "home_xg", "away_xg", "goals_prevented")

_SEMANTICS = {
    "count": "Count reported by TheStatsAPI for the named side in that match. FOR = the target "
             "team's own value; AGAINST = the opponent's value in the same match (e.g. AGAINST "
             "tackles are tackles made BY the opponent).",
    "pct_own": "Percentage reported by TheStatsAPI for the named side's own actions. FOR = the "
               "target team's rate; AGAINST = the opponent's own rate in the same match.",
    "pct_complementary": "Percentage share reported by TheStatsAPI; the two sides' values are "
                         "complementary (sum to about 100), so AGAINST is not independent of "
                         "FOR.",
}
_SEMANTICS_NOTE = {
    "blocked_shots": " Provider field shots.blocked_shots attributed to the named side; whether it "
                     "counts that side's shots that were blocked or blocks it made is NOT "
                     "independently verified here.",
    "goals": " Historical completed-match goals from the fixture score (never the target match).",
}


def raw_cell(concept_path: str, side: str, fixture: Dict[str, Any],
             stats: Optional[Dict[str, Any]]) -> Any:
    """Independent re-derivation of a provider value straight from the payload."""
    if concept_path.startswith("fixture.score"):
        return (fixture.get("score") or {}).get(side)
    _, group, stat, period = concept_path.split(".")
    sd = (stats or {}).get("data") or {}
    return _cell(sd, group, stat, period, side)


def payload_sha256(obj: Any) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def fixture_identity(fx: Dict[str, Any]) -> Tuple:
    """The fields history construction depends on; used to detect conflicting duplicates."""
    sc = fx.get("score") or {}
    return (fx.get("utc_date"), (fx.get("home_team") or {}).get("id"),
            (fx.get("away_team") or {}).get("id"), sc.get("home"), sc.get("away"),
            fx.get("status"), bool(fx.get("is_neutral")), fx.get("competition_id"),
            fx.get("season_id"))


@dataclass
class HistoryMatch:
    match_id: str
    kickoff_unix: int
    fixture: Dict[str, Any]
    stats: Optional[Dict[str, Any]]
    stats_status: str               # OK | NO_STATS | CONFLICTING_PAYLOADS
    stats_payload_sha256: Optional[str]
    values: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # concept -> {home, away}
    has_rich: bool = False


def build_stats_map(payloads: Iterable[Tuple[str, Dict[str, Any]]]
                    ) -> Tuple[Dict[str, Tuple[Dict[str, Any], str]], Dict[str, List[str]]]:
    """match_id -> (payload, sha) for unambiguous payloads; conflicting ids are returned apart
    and are NEVER resolved by picking one version."""
    seen: Dict[str, Dict[str, Tuple[Dict[str, Any], str]]] = {}
    for name, d in payloads:
        mid = (d.get("data") or {}).get("match_id") if isinstance(d, dict) else None
        if not isinstance(mid, str) or not mid:
            continue
        h = payload_sha256(d.get("data"))
        seen.setdefault(mid, {}).setdefault(h, (d, name))
    ok, conflicts = {}, {}
    for mid, versions in seen.items():
        if len(versions) == 1:
            (h, (d, _)), = versions.items()
            ok[mid] = (d, h)
        else:
            conflicts[mid] = sorted(n for _, n in versions.values())
    return ok, conflicts


def normalize_history(fixtures: Dict[str, Dict[str, Any]],
                      stats_ok: Dict[str, Tuple[Dict[str, Any], str]],
                      stats_conflicts: Dict[str, List[str]]) -> Dict[str, HistoryMatch]:
    norm = TheStatsAPINormalizer()
    out: Dict[str, HistoryMatch] = {}
    for mid, fx in fixtures.items():
        s = stats_ok.get(mid)
        status = "OK" if s else ("CONFLICTING_PAYLOADS" if mid in stats_conflicts else
                                 "NO_STATS")
        rm = norm.normalize(fx, s[0] if s else None)
        if rm is None:
            continue
        hm = HistoryMatch(mid, int(rm.date_unix), fx, s[0] if s else None, status,
                          s[1] if s else None)
        for concept, stem, _path, _kind in CONCEPTS:
            if stem == "goals":
                h, a = rm.home_goals, rm.away_goals
            else:
                h, a = getattr(rm, f"{stem}_home"), getattr(rm, f"{stem}_away")
            hm.values[concept] = {"home": h, "away": a}
        hm.has_rich = any(v is not None for c in RICH_CONCEPTS
                          for v in hm.values[c].values())
        out[mid] = hm
    return out


def team_history(history: Dict[str, HistoryMatch], team_id: str, cutoff_unix: int
                 ) -> List[HistoryMatch]:
    """All completed matches involving team_id with kickoff STRICTLY before cutoff, oldest
    first, ordered by (kickoff, match_id)."""
    rows = [h for h in history.values() if h.kickoff_unix < cutoff_unix and team_id in (
        (h.fixture.get("home_team") or {}).get("id"), (h.fixture.get("away_team") or {}).get("id"))]
    return sorted(rows, key=lambda h: (h.kickoff_unix, h.match_id))


def perspective(h: HistoryMatch, team_id: str) -> Tuple[str, str, str, Dict[str, Any]]:
    """(venue, for_side, against_side, opponent) from the team's point of view."""
    home = (h.fixture.get("home_team") or {})
    away = (h.fixture.get("away_team") or {})
    if home.get("id") == team_id:
        venue, fs, ag, opp = "HOME", "home", "away", away
    elif away.get("id") == team_id:
        venue, fs, ag, opp = "AWAY", "away", "home", home
    else:
        raise ValueError(f"{team_id} not in {h.match_id}")
    if h.fixture.get("is_neutral"):
        venue = "NEUTRAL"
    return venue, fs, ag, opp


def ref(role: str, *parts: str) -> str:
    return ".".join((REF_PREFIX, role) + tuple(parts))


def _reliability(sample_n: int) -> str:
    return "ADEQUATE" if sample_n >= 10 else ("LIMITED" if sample_n >= 5 else "SPARSE")


def _mean(xs: Sequence[float]) -> float:
    return round(sum(xs) / len(xs), 4)


def build_team_block(history: Dict[str, HistoryMatch], team_id: str, role: str,
                     cutoff_unix: int, normalization_version: str) -> Dict[str, Any]:
    rows = team_history(history, team_id, cutoff_unix)
    concept_meta = {c: (stem, path, kind) for c, stem, path, kind in CONCEPTS}
    # ---- raw recent rows ----
    raw_rows = []
    for h in rows[-RAW_RECENT_ROWS:][::-1]:            # newest first
        venue, fs, ag, opp = perspective(h, team_id)
        vals = {}
        for concept, (stem, path, kind) in concept_meta.items():
            for persp, side in (("FOR", fs), ("AGAINST", ag)):
                v = h.values[concept][side]
                if v is None:            # NULL != ZERO: omitted, never 0
                    continue
                vals[ref(role, "raw", h.match_id, concept, persp)] = v
        raw_rows.append({
            "provider": PROVIDER, "provider_match_id": h.match_id,
            "kickoff_unix": h.kickoff_unix, "kickoff_utc": h.fixture.get("utc_date"),
            "competition_id": h.fixture.get("competition_id"),
            "season_id": h.fixture.get("season_id"),
            "venue": venue, "opponent_id": opp.get("id"), "opponent_name": opp.get("name"),
            "stats_status": h.stats_status, "source_payload_hash": h.stats_payload_sha256,
            "team_side_in_provider_record": fs,
            "window": "RAW_RECENT_MATCH", "period": "FULL_MATCH", "values": vals})
    # ---- aggregates ----
    windows: List[Tuple[str, str, List[HistoryMatch]]] = [("ALL_PRIOR", "ALL", rows)]
    for w, n in WINDOW_N.items():
        windows.append((w, "ALL", rows[-n:]))
    for vs in ("HOME", "AWAY"):
        windows.append(("ALL_PRIOR", vs, [h for h in rows if perspective(h, team_id)[0] == vs]))
    aggs = []
    window_table = {}
    for w, vs, subset in windows:
        if subset:
            window_table[f"{w}|{vs}"] = {
                "match_ids": [h.match_id for h in subset],
                "first_kickoff_unix": subset[0].kickoff_unix,
                "last_kickoff_unix": subset[-1].kickoff_unix, "n_matches": len(subset)}
        for concept, (stem, path, kind) in concept_meta.items():
            for persp in ("FOR", "AGAINST"):
                contrib, vals = [], []
                for h in subset:
                    _, fs, ag, _ = perspective(h, team_id)
                    v = h.values[concept][fs if persp == "FOR" else ag]
                    if v is not None:
                        contrib.append(h)
                        vals.append(float(v))
                if not vals:
                    continue
                item = {
                    "evidence_ref": ref(role, concept, persp, w, vs),
                    "provider": PROVIDER, "canonical_concept": concept,
                    "provider_field": path, "team_role": role, "perspective": persp,
                    "period": "FULL_MATCH", "window": w, "venue_scope": vs,
                    "value": _mean(vals), "sample_n": len(vals),
                    "coverage": round(len(vals) / len(subset), 4),
                    "cutoff_unix": cutoff_unix,
                    "observed_at_max": max(h.kickoff_unix for h in contrib),
                    "reliability_label": _reliability(len(vals)),
                }
                cset = {h.match_id for h in contrib}
                nulls = [h.match_id for h in subset if h.match_id not in cset]
                if nulls:
                    item["null_match_ids"] = nulls
                aggs.append(item)
    # ---- coverage ----
    by_cs: Dict[str, int] = {}
    for h in rows:
        k = f"{h.fixture.get('competition_id')}|{h.fixture.get('season_id')}"
        by_cs[k] = by_cs.get(k, 0) + 1
    per_metric = {}
    for concept, (stem, path, kind) in concept_meta.items():
        n_pop = sum(1 for h in rows if h.values[concept][perspective(h, team_id)[1]] is not None)
        per_metric[concept] = {"N_POPULATED": n_pop,
                               "COVERAGE_RATE": round(n_pop / len(rows), 4) if rows else 0.0}
    names = sorted({(h.fixture.get("home_team") if perspective(h, team_id)[1] == "home"
                     else h.fixture.get("away_team")).get("name") for h in rows})
    coverage = {
        "N_PRIOR_MATCHES_TOTAL": len(rows),
        "N_PRIOR_MATCHES_WITH_RICH_STATS": sum(1 for h in rows if h.has_rich),
        "N_PRIOR_MATCHES_STATS_CONFLICT_EXCLUDED": sum(
            1 for h in rows if h.stats_status == "CONFLICTING_PAYLOADS"),
        "N_PRIOR_MATCHES_NO_STATS": sum(1 for h in rows if h.stats_status == "NO_STATS"),
        "N_RAW_RECENT_MATCHES_INCLUDED": len(raw_rows),
        "N_DISTINCT_RICH_CONCEPTS": len({c for c in RICH_CONCEPTS
                                         if per_metric[c]["N_POPULATED"] > 0}),
        "prior_matches_by_competition_season": dict(sorted(by_cs.items())),
        "first_prior_kickoff_utc": rows[0].fixture.get("utc_date") if rows else None,
        "last_prior_kickoff_utc": rows[-1].fixture.get("utc_date") if rows else None,
        "team_names_seen_for_team_id": names,
        "per_metric_FOR": per_metric,
    }
    return {"team_role": role, "team_id": team_id, "raw_recent_matches": raw_rows,
            "aggregate_evidence": aggs, "windows": window_table, "coverage": coverage,
            "_rows": rows}


def concept_semantics() -> Dict[str, Dict[str, Any]]:
    """Per-concept field table (stated once; items reference it by canonical_concept)."""
    return {c: {"provider_field": p, "kind": k, "rich": c in RICH_CONCEPTS,
                "provider_semantics": _SEMANTICS[k] + _SEMANTICS_NOTE.get(c, "")}
            for c, _, p, k in CONCEPTS}


def select_fixture(scheduled: Sequence[Dict[str, Any]], history: Dict[str, HistoryMatch],
                   as_of_unix: int) -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    """Mechanical rule: future kickoff; both teams >= MIN_RICH_PRIOR_MATCHES prior matches with
    rich stats; sort (kickoff, provider fixture id); first."""
    audit = []
    cands = []
    for fx in scheduled:
        if str(fx.get("status")).lower() != "scheduled":
            continue
        k = parse_iso_to_unix(fx.get("utc_date"))
        if k is None or k <= as_of_unix:
            continue
        n = [sum(1 for h in team_history(history, (fx.get(s) or {}).get("id"), k) if h.has_rich)
             for s in ("home_team", "away_team")]
        ok = min(n) >= MIN_RICH_PRIOR_MATCHES
        cands.append((k, fx["id"], fx, n, ok))
    cands.sort(key=lambda t: (t[0], t[1]))
    for k, i, fx, n, ok in cands[:10]:
        audit.append({"provider_fixture_id": i, "kickoff_unix": k,
                      "rich_prior_home": n[0], "rich_prior_away": n[1], "eligible": ok})
    for k, i, fx, n, ok in cands:
        if ok:
            return fx, audit
    return None, audit


FORBIDDEN_TOKENS = ("odds", "p_model", "npxg", "np_expected", "closing", "settlement",
                    "\"score\"", "xg_available", "manager")


def leakage_checks(packet: Dict[str, Any], history: Dict[str, HistoryMatch],
                   target_id: str) -> Dict[str, Any]:
    """Independent re-derivation of every emitted number from raw payload cells."""
    T = packet["cutoff_unix"]
    concept_meta = {c: (stem, path, kind) for c, stem, path, kind in CONCEPTS}
    n_after, n_untrace, n_null_zero, n_npxg = 0, 0, 0, 0
    refs: List[str] = []
    for role in ROLES:
        tid = packet["fixture"][role.lower()]["provider_team_id"]
        for row in packet["raw_recent_matches"][role]:
            h = history.get(row["provider_match_id"])
            if h is None or h.kickoff_unix >= T:
                n_after += 1
                continue
            _, fs, ag, _ = perspective(h, tid)
            emitted = set()
            for r_, val in row["values"].items():
                refs.append(r_)
                parts = r_.split(".")
                if parts[:4] != [REF_PREFIX, role, "raw", h.match_id] or len(parts) != 6 or \
                        parts[4] not in concept_meta:
                    n_untrace += 1
                    continue
                concept, persp = parts[4], parts[5]
                emitted.add((concept, persp))
                raw = raw_cell(concept_meta[concept][1], fs if persp == "FOR" else ag,
                               h.fixture, h.stats)
                if raw is None:
                    n_null_zero += 1
                elif float(raw) != float(val):
                    n_untrace += 1
            # every non-null raw cell of this row must have been emitted (nothing hidden)
            for concept in concept_meta:
                for persp, side in (("FOR", fs), ("AGAINST", ag)):
                    if raw_cell(concept_meta[concept][1], side, h.fixture, h.stats) is not None \
                            and (concept, persp) not in emitted:
                        n_untrace += 1
        for a in (x for x in packet["aggregate_evidence"] if x["team_role"] == role):
            refs.append(a["evidence_ref"])
            path = concept_meta[a["canonical_concept"]][1]
            vals = []
            win = packet["windows"][role][f"{a['window']}|{a['venue_scope']}"]["match_ids"]
            nulls = set(a.get("null_match_ids", []))
            for mid in win:
                h = history.get(mid)
                if h is None or h.kickoff_unix >= T:
                    n_after += 1
                    continue
                _, fs, ag, _ = perspective(h, tid)
                raw = raw_cell(path, fs if a["perspective"] == "FOR" else ag, h.fixture, h.stats)
                if (raw is None) != (mid in nulls):
                    n_null_zero += 1       # a null counted as data, or data hidden as null
                elif raw is not None:
                    vals.append(float(raw))
            if not vals or round(sum(vals) / len(vals), 4) != a["value"] or \
                    len(vals) != a["sample_n"]:
                n_untrace += 1
    # `fixture` and `selection_rule` legitimately name the target id (identity + selection
    # audit, no outcome); every other section must never mention it.
    # The required boolean declaration flags (e.g. p_model_included=false) are the only
    # sanctioned mentions of forbidden concepts and are checked for being False instead.
    flags = ("target_outcome_included", "market_data_included", "p_model_included")
    if any(packet.get(f) is not False for f in flags):
        raise ValueError("a declaration flag is not False")
    body = json.dumps({k: v for k, v in packet.items()
                       if k not in ("fixture", "selection_rule") + flags}, ensure_ascii=False)
    sel = json.dumps(packet.get("selection_rule", {}), ensure_ascii=False).lower()
    lowered = body.lower()
    forbidden_hits = {t: lowered.count(t) + sel.count(t) for t in FORBIDDEN_TOKENS
                      if t in lowered or t in sel}
    n_npxg += lowered.count("npxg") + lowered.count("np_expected")
    target_mentions = body.count(target_id)
    return {
        "TARGET_OUTCOME_INCLUDED": False if target_mentions == 0 else True,
        "TARGET_POSTMATCH_STATS_INCLUDED": target_mentions != 0,
        "MARKET_DATA_INCLUDED": any(t in forbidden_hits for t in ("odds", "closing",
                                                                   "settlement")),
        "P_MODEL_INCLUDED": "p_model" in forbidden_hits,
        "FUTURE_MATCH_OBSERVATIONS_INCLUDED": n_after != 0,
        "N_HISTORY_ROWS_AT_OR_AFTER_TARGET_KICKOFF": n_after,
        "N_DUPLICATE_EVIDENCE_REFS": len(refs) - len(set(refs)),
        "N_UNTRACEABLE_NUMERIC_EVIDENCE_ITEMS": n_untrace,
        "N_NPXG_ITEMS": n_npxg,
        "N_NULLS_COERCED_TO_ZERO": n_null_zero,
        "N_TARGET_ID_MENTIONS_OUTSIDE_FIXTURE": target_mentions,
        "FORBIDDEN_TOKEN_HITS": forbidden_hits,
        "N_EVIDENCE_REFS_CHECKED": len(refs),
    }


def leakage_ok(checks: Dict[str, Any]) -> bool:
    return (not checks["TARGET_OUTCOME_INCLUDED"] and not checks["TARGET_POSTMATCH_STATS_INCLUDED"]
            and not checks["MARKET_DATA_INCLUDED"] and not checks["P_MODEL_INCLUDED"]
            and not checks["FUTURE_MATCH_OBSERVATIONS_INCLUDED"]
            and checks["N_HISTORY_ROWS_AT_OR_AFTER_TARGET_KICKOFF"] == 0
            and checks["N_DUPLICATE_EVIDENCE_REFS"] == 0
            and checks["N_UNTRACEABLE_NUMERIC_EVIDENCE_ITEMS"] == 0
            and checks["N_NPXG_ITEMS"] == 0 and checks["N_NULLS_COERCED_TO_ZERO"] == 0
            and not checks["FORBIDDEN_TOKEN_HITS"])
