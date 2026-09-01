#!/usr/bin/env python3
"""On-demand fixture EDGE SCANNER — flag the lines the model considers edge, ranked
NET OF THE MARGIN HURDLE, for ONE requested fixture.

This is an EXPERIMENT run on our own fixtures. It is kept STRUCTURALLY SEPARATE from
the pre-registered Pilot C sample and from the manual_predict ledger — its own files,
its own "flagged:" prediction-id namespace, test-enforced (tests/test_scanner_exclusion).
It reuses the model EXACTLY as it stands (same saved CV-selected hyperparameters, same
fit_full/predict_one). It MEASURES the model; it never refits, retunes, or substitutes it.

════════════════════════════════════════════════════════════════════════════════
NO STAKE SIZING — PERMANENTLY (do not add this later)
════════════════════════════════════════════════════════════════════════════════
This tool does NOT and MUST NOT emit stake sizing, Kelly fractions, or bankroll
recommendations, now or in any future change. With no demonstrated edge, any staking
output is fabricated confidence, and an uncalibrated Kelly implementation was already
flagged in this project as a real liability (R06). A future contributor who is tempted
to "helpfully" add position sizing here should stop: it is deliberately absent.

════════════════════════════════════════════════════════════════════════════════
WHAT IT DOES (per the edge-scanner brief)
════════════════════════════════════════════════════════════════════════════════
 §1 Data gathering  — for a requested fixture, gather the richest available data for
     BOTH teams (recent corpus history + rich /stats fields + all-book/all-line odds),
     cache-first and quota-capped, and report data coverage HONESTLY per team.
 §2 Broad vs rich   — run the SAME fitted model twice: "broad" on corpus rolling
     features; "rich" with the richer npxG measurement substituted into the model's
     existing xG input where /stats is populated for BOTH teams. No refit. Report where
     broad and rich disagree and by how much. If they diverge materially that is
     informative in itself — the rich configuration rests on far less history.
     NOTE (data reality): the training corpus is FootyStats-keyed and carries no
     TheStatsAPI mt_ id, so historical matches cannot currently be joined to the /stats
     endpoint that holds the rich fields. The rich pass is therefore honestly reported as
     structurally unavailable (rich == broad) for corpus-history fixtures, rather than
     silently pretending; --rich is prevented from wasting budget on wrong-namespace ids.
     The mechanism is in place and activates automatically if a corpus carrying mt_ ids
     (or a join table) is added later — with no model change.
 §3 EV per line     — for EVERY corners/cards/goals/BTTS line any book offers: model p
     (broad and rich), each book's vig-adjusted fair prob with overround shown,
     edge = model − market per book, and the best available REFERENCE price identified.
 §4 Flagging        — rank by edge NET OF THE MARGIN HURDLE (required edge = overround/2),
     never raw edge. Mandatory reliability filter (adequate history for BOTH teams +
     non-extreme estimate). Report flags that PASS both AND, separately, those with edge
     that FAIL reliability.
 §5 Line shopping   — fair price (sharpest ref: Betfair > Pinnacle) and best price
     (highest odds across all books) are DISTINCT roles, never conflated. Report edge vs
     the fair reference AND the price improvement from shopping.
 §6 Cross-book cfg  — record the model's position relative to the books per flag.
 §7 Timing          — capture price at flag time and (via --recapture) near kickoff;
     record the movement so "model wrong" is distinguishable from "price disappeared".
 §9 Log + settle    — every flag goes to a SEPARATE flagged-lines log (own namespace),
     auto-settled when fixtures finish, with a running scorecard.
 §10 Pre-registration — a stopping point committed BEFORE any flag settles, hash-attested
     the same way Pilot C's was (data/forward/scanner_preregistration.json →
     scanner_preregistration_ledger.jsonl). Not revised after seeing results.
 §11 Honesty        — every output carries the caveat and the running scorecard, and
     marks soft-book-only measurements clearly.

════════════════════════════════════════════════════════════════════════════════
HARD SEPARATION FROM PILOT C AND FROM manual_predict (enforced in code, not convention)
════════════════════════════════════════════════════════════════════════════════
Pilot C enumerates its sample ONLY via hardcoded literal pilotC_* filenames (no directory
glob). This module writes to DIFFERENT literal files, none of which is a pilotC_* or a
manual_* ledger/log basename:
  * flagged lines  -> data/forward/scanner_flagged_lines.jsonl
  * commitments    -> data/forward/scanner_commitments.jsonl   (own hash chain)
  * reveals        -> data/forward/scanner_reveals.jsonl        (own hash chain)
  * settled log    -> data/forward/scanner_settled_log.json
  * scorecard      -> data/forward/scanner_scorecard.json
  * pre-reg ledger -> data/forward/scanner_preregistration_ledger.jsonl
Every scanner prediction_id uses the "flagged:" namespace prefix, never "pilotC:" or
"manual:". Because no Pilot C (or manual) reader references any of these names, a scanner
flag cannot appear in Pilot C's settled sample, per-cell counts toward 385, weeks-to-
readout, or health report. Verified by tests/test_scanner_exclusion.py.

USAGE
  # scan a fixture, flag edge lines, and COMMIT the flags (cache-first odds)
  python scripts/edge_scanner.py --fixture-id mt_466259566

  # by teams + date
  python scripts/edge_scanner.py --home "Leeds" --away "Norwich" --date 2026-09-05

  # scan without committing (inspect before it goes on record)
  python scripts/edge_scanner.py --fixture-id mt_466259566 --dry-run

  # also fetch /stats for both teams' recent matches to populate the RICH model
  # (budget-capped; cache-first). Without --rich, rich coverage is reported from cache.
  python scripts/edge_scanner.py --fixture-id mt_466259566 --rich

  # re-capture flagged prices shortly before kickoff and record movement (§7)
  python scripts/edge_scanner.py --fixture-id mt_466259566 --recapture

  # settle finished fixtures' flags and refresh the scorecard (§9)
  python scripts/edge_scanner.py --settle
  python scripts/edge_scanner.py --scorecard          # print scorecard only

  # verify scanner commitment hashes + chain
  python scripts/edge_scanner.py --verify-hash --fixture-id mt_466259566
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

# Load .env so an interactive/cron run has the API key (same pattern as the loop).
_ENV_PATH = "/home/ubuntu/.env"
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import pilotC_stat_mixer as mix
import pilotC_forward_predict as fp
from src.research.forward.attestation_ledger import (
    AttestationLedger, compute_commitment_hash,
)

# ── separate, scanner-only artifacts (NEVER a pilotC_* or manual_* ledger name) ──
CH = "/home/ubuntu/data/thestatsapi/championship"
FIXTURE_LIST = f"{CH}/_pilotC_fixture_list.json"          # read-only fixture universe
SCANNER_FLAGGED_LOG = "/home/ubuntu/data/forward/scanner_flagged_lines.jsonl"
SCANNER_COMMIT_LEDGER = "/home/ubuntu/data/forward/scanner_commitments.jsonl"
SCANNER_REVEAL_LEDGER = "/home/ubuntu/data/forward/scanner_reveals.jsonl"
SCANNER_SETTLED_LOG = "/home/ubuntu/data/forward/scanner_settled_log.json"
SCANNER_SCORECARD = "/home/ubuntu/data/forward/scanner_scorecard.json"
SCANNER_PREREG_DOC = "/home/ubuntu/data/forward/scanner_preregistration.json"
SCANNER_PREREG_LEDGER = "/home/ubuntu/data/forward/scanner_preregistration_ledger.jsonl"
# Scanner-owned cache of the deterministically-fitted models (keyed on corpus+HP
# fingerprint). Not shared with Pilot C or manual; only speeds up repeat scanner runs.
SCANNER_MODEL_CACHE = "/home/ubuntu/data/forward/scanner_model_cache_{fp}.pkl"

SCANNER_ID_PREFIX = "flagged"  # id namespace: flagged:{mid}:{market}:{line} — never pilotC/manual
STAT_MIXER_HP = "/home/ubuntu/data/discovery/pilotC_stat_mixer.json"

BOOKS = fp.BOOKS                       # ['bet365','betfair-exchange','pinnacle']
PRIMARY_BOOK = fp.PRIMARY_BOOK         # 'betfair-exchange'
MKT_ODDSKEY = fp.MKT_ODDSKEY           # {'goals':'total_goals','corners':'match_corners',...}
# Sharpest → softest reference-book priority for the FAIR benchmark (§5). Betfair
# exchange (~1% overround) first, then Pinnacle. Everything else is a SOFT book, used
# only as an execution venue / disagreement signal, never as the fair benchmark.
FAIR_REF_PRIORITY = ["betfair-exchange", "pinnacle"]
SOFT_BOOKS = [b for b in BOOKS if b not in FAIR_REF_PRIORITY]

# The lines the model was actually FITTED for (from the saved hyperparameters). A flag is
# only produced on a line the model has coefficients for — we never extrapolate the model
# to an unfitted line. Odds, however, are scanned for EVERY line the book offers so
# coverage is reported honestly.
def _fitted_cells():
    saved = json.load(open(STAT_MIXER_HP))["models"]
    return {(x["market"], (None if x["line"] in (None, "None") else float(x["line"])))
            for x in saved}

# ── flag / reliability parameters (mirrored from the pre-registration; NOT tunable
#    at runtime so the experiment stays comparable to what was registered) ──────────
NET_EDGE_FLAG_PP = 1.0          # a flag requires net_edge (raw − hurdle) ≥ this
MIN_MATCHES_PER_TEAM = 8        # reliability: adequate corpus history for BOTH teams
RELIABILITY_PROB_BOUNDS = (0.05, 0.95)   # reliability: non-extreme model estimate

# Hard per-run live-request cap (protects the monthly budget). Odds are ~1 request per
# book for one fixture; with an optional rich /stats pass this is generous headroom.
SCANNER_REQUEST_CAP = int(os.environ.get("SCANNER_REQUEST_CAP", "40"))
# Cap on how many recent /stats matches to fetch PER TEAM for the rich model (budget).
RICH_HISTORY_CAP = int(os.environ.get("SCANNER_RICH_HISTORY_CAP", "6"))

CAVEAT = (
    "CAVEAT: a single fixture demonstrates nothing about edge. The accumulated evidence "
    "is that this model has NOT beaten market prices in systematic testing (median edge "
    "0-1pp vs a 2-4pp threshold; performance degrades where model-vs-market divergence "
    "is largest, disagreement-decile correlation -0.56). Flags are HYPOTHESES being "
    "tested, not recommendations. No stake sizing is provided, by design."
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _flag_id(mid, market, line):
    return f"{SCANNER_ID_PREFIX}:{mid}:{market}:{line}"


def _load_fixture_meta():
    if not os.path.exists(FIXTURE_LIST):
        return {}
    return json.load(open(FIXTURE_LIST)).get("meta", {})


def resolve_fixture(fixture_id=None, home=None, away=None, date=None):
    """Resolve a fixture to (mid, meta_row) from the known fixture universe. Same logic
    as manual_predict.resolve_fixture."""
    meta = _load_fixture_meta()
    if fixture_id:
        row = meta.get(fixture_id)
        if row is None:
            return None, f"fixture id {fixture_id} not found in {FIXTURE_LIST}"
        return fixture_id, row
    if not home or not away:
        return None, "provide --fixture-id, or both --home and --away"
    hl, al = home.lower(), away.lower()
    target_day = None
    if date:
        try:
            target_day = datetime.fromisoformat(date).date()
        except Exception:
            return None, f"could not parse --date {date!r} (use YYYY-MM-DD)"
    cands = []
    for mid, row in meta.items():
        rh = str(row.get("home", "")).lower()
        ra = str(row.get("away", "")).lower()
        if (hl in rh or rh in hl) and (al in ra or ra in al):
            cands.append((mid, row))
    if not cands:
        return None, (f"no fixture in the universe matches home~{home!r} away~{away!r}. "
                      f"The fixture must already be in {FIXTURE_LIST}.")
    if target_day is not None:
        same_day = [(mid, r) for mid, r in cands
                    if datetime.fromtimestamp(r.get("ts", 0), timezone.utc).date() == target_day]
        if same_day:
            return same_day[0]
        return None, (f"matched {home} v {away} but none on {date}.")
    now = time.time()
    upcoming = sorted([c for c in cands if (c[1].get("ts", 0) or 0) > now],
                      key=lambda c: c[1]["ts"])
    if upcoming:
        return upcoming[0]
    return sorted(cands, key=lambda c: c[1].get("ts", 0), reverse=True)[0]


# ── §1 DATA GATHERING + coverage report ───────────────────────────────────────

def check_corpus_support(home, away):
    """(ok, (ms,hist,corpus_teams), missing[list]). Refuse a prediction the model can't
    support (either team absent from corpus history)."""
    ms = mix.load_corpus()
    hist = mix.build_histories(ms)
    corpus_teams = set(hist.keys())
    missing = [t for t in (home, away) if t not in corpus_teams]
    return (len(missing) == 0), (ms, hist, corpus_teams), missing


def gather_referee_coverage(row, hist, home, away):
    """§1 Referee coverage — 'referee assignment and their card/foul history IF available'.

    Honest reporting only: the fixture universe (_pilotC_fixture_list.json meta) carries
    no referee assignment, and the FootyStats corpus's refereeID is null throughout, so
    neither an assignment nor a referee card/foul history can be built from cached data.
    We report that explicitly rather than silently omitting referee — it matters most for
    the cards market. If a referee id/name is ever populated on the fixture row or corpus,
    this surfaces it (still without a network call). No model input depends on it (the
    fitted cards model uses team foul/card rolling features, not a referee feature)."""
    assigned = None
    for k in ("referee", "referee_name", "refereeName", "refereeID", "referee_id"):
        v = row.get(k)
        if v:
            assigned = v
            break
    # is there ANY non-null referee id across either team's corpus history?
    hist_has_ref = False
    for team in (home, away):
        for _d, mm, _r in hist.get(team, []):
            if mm.get("refereeID") not in (None, "", 0, "0"):
                hist_has_ref = True
                break
        if hist_has_ref:
            break
    return {
        "assignment_available": assigned is not None,
        "assigned_referee": assigned,
        "referee_history_available": hist_has_ref,
        "note": (
            "referee data present and assigned; surfaced for context (no model input "
            "depends on it — the cards model uses team foul/card features)"
            if assigned else
            ("no referee assignment in the fixture feed; corpus carries per-match "
             "refereeID so a history could be built, but with no assignment it cannot be "
             "tied to this fixture. Not used (cards model uses team foul/card features)"
             if hist_has_ref else
             "referee assignment not present in the fixture feed and corpus refereeID is "
             "null — no referee card/foul history can be built from cached data; reported "
             "as unavailable (the cards model uses team foul/card features, not a referee "
             "feature, so this does not silently degrade a flag)")),
    }


# Rich /stats sections and their metric lists (exact key spellings verified against a
# cached /stats payload). These are the TheStatsAPI-only fields the brief lists. Only a
# subset feed the (unchanged) model — see the rich-model note below — the rest are
# reported for COVERAGE honesty.
RICH_SECTIONS = {
    "overview": ["ball_possession", "expected_goals", "big_chances", "total_shots",
                 "shots_on_target", "goalkeeper_saves", "corner_kicks", "fouls",
                 "yellow_cards", "red_cards", "tackles"],
    "shots": ["blocked_shots", "shots_inside_box", "shots_outside_box", "hit_woodwork"],
    "attack": ["big_chances_missed", "touches_in_penalty_area", "fouled_in_final_third"],
    "passes": ["accurate_crosses", "accurate_long_balls", "final_third_entries"],
    "duels": ["duels_won_percentage", "aerial_duels_percentage", "ground_duels_percentage"],
    "defending": ["interceptions", "clearances", "ball_recoveries"],
    "goalkeeping": ["saves", "goals_prevented"],
}


def _stats_cache_key(mid):
    # SAME cache key the settle path uses, so a rich fetch and a later settle share it
    # and cost nothing twice.
    return f"pilotC_stats_{mid}"


def _match_id_of(m):
    """TheStatsAPI (``mt_``-namespaced) match id from a corpus record, or None.

    IMPORTANT id-namespace reality: the training corpus is FootyStats-sourced
    (data/discovery/corpus/league-matches_*.json) and its ``id`` field is a NUMERIC
    FootyStats id (e.g. 8223680). The TheStatsAPI ``/football/matches/{id}/stats``
    endpoint — the only source of the rich npxG/tackles/etc. fields — is keyed on a
    DIFFERENT ``mt_``-prefixed id space (e.g. mt_466259566). The two do not share a join
    key anywhere in this project, so a corpus history match cannot be resolved to a
    TheStatsAPI /stats record.

    We therefore return ONLY an ``mt_``-namespaced id if the corpus record happens to
    carry one (it currently never does). Returning the numeric FootyStats id here would
    make the rich pass fetch ``/football/matches/8223680/stats`` — a wrong-namespace id
    that wastes budget on guaranteed 404s. Refusing to do that is what keeps ``--rich``
    budget-safe AND honest: rich augmentation is reported as structurally unavailable
    rather than silently always-broad-while-burning-quota."""
    for k in ("mt_id", "thestatsapi_id", "match_id", "matchId", "fixture_id", "id"):
        v = m.get(k)
        if isinstance(v, str) and v.startswith("mt_"):
            return v
    return None


def _rich_stats_for_match(api, match_id, allow_fetch):
    """Return the /stats data dict for a match, cache-first. If allow_fetch is False,
    only returns it when already cached (zero budget). Returns None if unavailable.

    ``match_id`` must be a TheStatsAPI ``mt_`` id (see _match_id_of); anything else is
    rejected before any request so a wrong-namespace id can never spend budget."""
    if match_id is None or not str(match_id).startswith("mt_"):
        return None
    ck = _stats_cache_key(match_id)
    if not api.is_cached(ck) and not allow_fetch:
        return None
    try:
        d, _ = api.get_json(f"/football/matches/{match_id}/stats", cache_key=ck,
                            allow_status=(200, 404, 422))
    except SystemExit:
        return None
    if not d:
        return None
    data = d.get("data", d)
    return data if isinstance(data, dict) else None


def _side_val(node, side_key, split="all"):
    """node[split][side] as float, or None."""
    if not isinstance(node, dict):
        return None
    sub = node.get(split)
    if not isinstance(sub, dict):
        return None
    v = sub.get(side_key)
    try:
        return float(v)
    except Exception:
        return None


def gather_rich_coverage(api, hist, home, away, allow_fetch):
    """§1 rich-field coverage per team. For each team, take its most-recent RICH_HISTORY_CAP
    corpus matches, fetch (cache-first) their /stats, and record which rich fields were
    POPULATED vs null, plus how many matches of history and how many had /stats.

    Returns a per-team dict: {team: {matches_history, stats_matches, npxg_matches,
    field_populated:{field:count}, field_null:{field:count}}}. Honest coverage, no filling.
    """
    report = {}
    for team, side_key in ((home, None), (away, None)):
        rows = hist.get(team, [])
        n_hist = len(rows)
        recent = rows[-RICH_HISTORY_CAP:] if rows else []
        field_pop = {}
        field_null = {}
        stats_matches = 0
        npxg_matches = 0
        # how many recent history matches even carry a TheStatsAPI mt_ id we could join
        # to /stats. If this is 0 the rich fields are STRUCTURALLY unavailable for this
        # team (corpus is FootyStats-keyed; see _match_id_of), not merely "unfetched".
        joinable = sum(1 for _d, m, _r in recent if _match_id_of(m) is not None)
        for d_unix, m, role in recent:
            mid = _match_id_of(m)
            data = _rich_stats_for_match(api, mid, allow_fetch)
            if not data:
                continue
            stats_matches += 1
            side = "home" if role == "home" else "away"
            npxg = _side_val(data.get("np_expected_goals"), side)
            if npxg is not None:
                npxg_matches += 1
            for sec, metrics in RICH_SECTIONS.items():
                sec_node = data.get(sec, {})
                for metric in metrics:
                    v = _side_val(sec_node.get(metric) if isinstance(sec_node, dict) else None, side)
                    key = f"{sec}.{metric}"
                    if v is not None:
                        field_pop[key] = field_pop.get(key, 0) + 1
                    else:
                        field_null[key] = field_null.get(key, 0) + 1
            # npxG tracked separately (top-level section)
            if npxg is not None:
                field_pop["np_expected_goals"] = field_pop.get("np_expected_goals", 0) + 1
            else:
                field_null["np_expected_goals"] = field_null.get("np_expected_goals", 0) + 1
        report[team] = {
            "matches_history": n_hist,
            "recent_considered": len(recent),
            "rich_joinable_matches": joinable,
            "rich_available": joinable > 0,
            "stats_matches_available": stats_matches,
            "npxg_matches": npxg_matches,
            "rich_fields_populated": field_pop,
            "rich_fields_null": field_null,
        }
    return report


def fetch_odds(mid, dry_run=False):
    """Fetch multi-book odds for ONE fixture, cache-first and quota-capped. Reuses the
    SAME raw odds cache the pipeline uses (pilotC_odds_<mid>_<book>). Returns (books, usage)."""
    import thestatsapi_client as api
    api.MAX_LIVE_REQUESTS = min(api.MAX_LIVE_REQUESTS, SCANNER_REQUEST_CAP)
    before = api.budget_snapshot()
    usage = {"live_requests_made": 0, "cached_hits": 0,
             "monthly_remaining_before": before.get("last_monthly_remaining")}
    for bk in BOOKS:
        ck = f"pilotC_odds_{mid}_{bk}"
        if api.is_cached(ck):
            usage["cached_hits"] += 1
            continue
        if dry_run:
            continue  # dry-run must not spend budget on uncached odds
        try:
            api.get_json(f"/football/matches/{mid}/odds", params={"bookmaker": bk},
                         cache_key=ck, allow_status=(200, 404, 422))
        except SystemExit:
            usage["capped"] = True
            break
    usage["live_requests_made"] = api.live_requests_made()
    after = api.budget_snapshot()
    usage["monthly_remaining_after"] = after.get("last_monthly_remaining")
    books = fp.load_forward_books(mid)
    return books, usage


# ── model fitting (reuse EXACTLY — no refit/retune/substitution) ───────────────

def _corpus_fingerprint(ms):
    import hashlib
    max_date = max((m.get("date_unix", 0) or 0) for m in ms) if ms else 0
    hp_bytes = Path(STAT_MIXER_HP).read_bytes() if os.path.exists(STAT_MIXER_HP) else b""
    h = hashlib.sha256()
    h.update(str(len(ms)).encode()); h.update(str(int(max_date)).encode()); h.update(hp_bytes)
    return h.hexdigest()[:16]


def _fit_models(ms, hist, use_cache=True):
    """Fit each fitted market model on the FULL corpus using the SAVED CV-selected
    (C, l1_ratio). No hyperparameter search, no retune — identical to the experiment path.
    Deterministic given (corpus, saved HP), so the exact same fit is optionally cached."""
    import pickle
    saved = json.load(open(STAT_MIXER_HP))["models"]
    hp = {(x["market"], (None if x["line"] in (None, "None") else float(x["line"]))):
          (x["C"], x["l1_ratio"]) for x in saved}
    fp_key = _corpus_fingerprint(ms)
    cache_path = Path(SCANNER_MODEL_CACHE.format(fp=fp_key))
    if use_cache and cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f), hp
        except Exception:
            pass
    models = {}
    for (market, line), (C, l1r) in hp.items():
        models[(market, line)] = fp.fit_full(ms, hist, market, line, C, l1r)
    if use_cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "wb") as f:
                pickle.dump(models, f)
        except Exception:
            pass
    return models, hp


# ── §2 RICH input substitution (model UNCHANGED) ──────────────────────────────
#
# The fitted model has coefficients ONLY for corpus rolling features; there is no
# separate "rich" fitted model in this project and the brief forbids training one. The
# ONE rich field that is a strictly-better measurement of an input the model ALREADY uses
# is npxG (a cleaner version of the corpus `team_a_xg`/`team_b_xg`). The rich run builds
# an npxG-augmented history: where /stats gives npxG for a match, that match's xg field
# is replaced by npxG before the SAME model computes its SAME rolling xg feature. The
# fitted coefficients never change. Every other rich field is reported for coverage only,
# because feeding it to the model would require a refit (forbidden). Where /stats is not
# populated for BOTH teams, the rich run falls back to broad and that is reported.

def _build_rich_history(api, ms, hist, home, away, allow_fetch):
    """Return (rich_hist, info). rich_hist is a deep-ish copy of the corpus histories for
    the two teams with each match's team_a_xg/team_b_xg overwritten by that match's npxG
    where /stats provides it. Only the two fixture teams' matches are touched, so every
    other team's features are identical to broad."""
    import copy
    info = {"npxg_substitutions": 0, "matches_touched": 0,
            "home_stats_matches": 0, "away_stats_matches": 0, "both_covered": False,
            "home_joinable": 0, "away_joinable": 0, "rich_structurally_available": False,
            "unavailable_reason": None}
    # start from the shared histories; copy only the match dicts we mutate so we never
    # corrupt the broad corpus in-memory.
    rich_hist = dict(hist)
    touched_ids = {}

    def _joinable(team):
        rows = hist.get(team, [])
        recent = rows[-RICH_HISTORY_CAP:] if rows else []
        return sum(1 for _d, m, _r in recent if _match_id_of(m) is not None)

    def _augment(team, key):
        rows = hist.get(team, [])
        recent = rows[-RICH_HISTORY_CAP:] if rows else []
        n_stats = 0
        new_rows = list(rows)  # shallow copy of the list
        for i in range(len(rows) - len(recent), len(rows)):
            d_unix, m, role = rows[i]
            mid = _match_id_of(m)
            data = _rich_stats_for_match(api, mid, allow_fetch)
            if not data:
                continue
            n_stats += 1
            npxg_home = _side_val(data.get("np_expected_goals"), "home")
            npxg_away = _side_val(data.get("np_expected_goals"), "away")
            if npxg_home is None and npxg_away is None:
                continue
            mm = copy.copy(m)
            if npxg_home is not None:
                mm["team_a_xg"] = npxg_home
            if npxg_away is not None:
                mm["team_b_xg"] = npxg_away
            new_rows[i] = (d_unix, mm, role)
            info["npxg_substitutions"] += 1
            touched_ids[mid or id(m)] = True
        rich_hist[team] = new_rows
        return n_stats

    info["home_joinable"] = _joinable(home)
    info["away_joinable"] = _joinable(away)
    info["home_stats_matches"] = _augment(home, "home")
    info["away_stats_matches"] = _augment(away, "away")
    info["matches_touched"] = len(touched_ids)
    info["both_covered"] = info["home_stats_matches"] > 0 and info["away_stats_matches"] > 0
    # Distinguish "structurally impossible to join" from "joinable but not fetched yet".
    if info["home_joinable"] == 0 and info["away_joinable"] == 0:
        info["rich_structurally_available"] = False
        info["unavailable_reason"] = (
            "corpus history is FootyStats-keyed and carries no TheStatsAPI mt_ id, so "
            "recent matches cannot be joined to the /stats endpoint that holds the rich "
            "npxG/tackles/etc. fields. Rich model therefore equals broad here — this is a "
            "data-namespace limitation, not a fetch that --rich would fix. See _match_id_of.")
    else:
        info["rich_structurally_available"] = True
    return rich_hist, info


# ── §3 EV across EVERY available line ──────────────────────────────────────────

def _iter_book_lines(books):
    """Yield (market, line, {book: (over_odds, under_odds)}) for EVERY line ANY book
    offers across goals/corners/cards/btts — not a fixed cell set (§3).

    line is a float for over/under markets, or None for BTTS. Odds strings are kept raw;
    devig converts them. A book that does not offer a given line simply doesn't appear in
    that line's dict."""
    # collect the union of lines each market exposes across books
    market_lines = {"goals": set(), "corners": set(), "cards": set()}
    per_book_market = {}
    for bk, mk in books.items():
        per_book_market[bk] = mk
        for market, okey in (("goals", "total_goals"), ("corners", "match_corners"),
                             ("cards", "total_cards")):
            node = mk.get(okey, {})
            if isinstance(node, dict):
                for ln in node.keys():
                    market_lines[market].add(ln)
    # over/under markets
    for market, okey in (("goals", "total_goals"), ("corners", "match_corners"),
                         ("cards", "total_cards")):
        for ln in sorted(market_lines[market], key=lambda s: float(s)):
            book_odds = {}
            for bk, mk in per_book_market.items():
                node = mk.get(okey, {}).get(ln, {})
                o = node.get("over", {}).get("last_seen")
                u = node.get("under", {}).get("last_seen")
                if o and u:
                    book_odds[bk] = (o, u)
            if book_odds:
                yield market, float(ln), book_odds
    # BTTS (single line)
    btts_odds = {}
    for bk, mk in per_book_market.items():
        node = mk.get("btts", {})
        o = node.get("yes", {}).get("last_seen")
        u = node.get("no", {}).get("last_seen")
        if o and u:
            btts_odds[bk] = (o, u)
    if btts_odds:
        yield "btts", None, btts_odds


def _pick_fair_reference(book_fair):
    """§5 FAIR reference: sharpest book present (Betfair > Pinnacle). If neither sharp
    book is present, fall back to a soft book but mark soft_only=True. book_fair maps
    book -> {fair_p, overround, over_odds, under_odds}. Returns (ref_book, soft_only)."""
    for b in FAIR_REF_PRIORITY:
        if b in book_fair:
            return b, False
    # no sharp reference — least trustworthy; label soft-only
    return (next(iter(book_fair)) if book_fair else None), True


def _best_price(book_fair, side):
    """§5 EXECUTION: highest decimal odds offered on `side` ('over'/'under', or 'yes'/'no'
    handled by caller mapping) across all books. Returns (book, odds) or (None, None)."""
    best_bk, best_odds = None, None
    key = "over_odds" if side == "over" else "under_odds"
    for bk, b in book_fair.items():
        o = b.get(key)
        if o is None:
            continue
        if best_odds is None or o > best_odds:
            best_odds, best_bk = o, bk
    return best_bk, best_odds


def _cross_book_config(model_p, book_fair, ref_book, side_over):
    """§6 Record the model's position relative to the books — one of the four
    configurations the brief enumerates:
      * model_agrees_with_sharp_both_disagree_with_soft
      * model_disagrees_with_both_books_which_agree
      * model_between_books_that_disagree
      * books_disagree_model_sides_with_sharp / ..._with_soft
    plus operational fallbacks (single_book_only). All probabilities are taken on the
    MODEL'S side (over/yes if side_over else under/no).

    Design notes making the classification boundary-stable:
      * TOL is a single 'meaningful disagreement' threshold (1pp; Pilot C measured mean
        book disagreement ~1.3pp). Two numbers are 'the same' iff within TOL.
      * Softs are summarised by their mean side-prob (they are execution/disagreement
        venues; there is usually one soft book here anyway). 'Books agree' means the
        sharp and the soft summary are within TOL.
      * 'Between' requires the model to be strictly inside the (sharp, soft) interval by
        more than TOL on BOTH sides — otherwise it is classified as siding with the
        nearer book, so a model sitting essentially ON one book is not mislabelled
        'between'."""
    def side_p(b):
        fp_over = b["fair_p"]  # fair_p is always P(over/yes)
        return fp_over if side_over else (1.0 - fp_over)

    sharp = book_fair.get(ref_book)
    softs = {b: v for b, v in book_fair.items() if b != ref_book}
    if not sharp or not softs:
        return "single_book_only"

    TOL = 0.01  # 1pp meaningful-disagreement threshold
    sharp_p = side_p(sharp)
    soft_ps = [side_p(v) for v in softs.values()]
    soft_p = sum(soft_ps) / len(soft_ps)          # soft summary
    m = model_p if side_over else (1.0 - model_p)

    books_agree = abs(sharp_p - soft_p) < TOL

    if books_agree:
        if abs(m - sharp_p) < TOL:
            return "model_agrees_with_both_books"
        return "model_disagrees_with_both_books_which_agree"

    # Books disagree meaningfully. Order the two poles.
    lo, hi = min(sharp_p, soft_p), max(sharp_p, soft_p)
    # Strictly inside the interval (by > TOL on both sides) => genuinely between.
    if (m > lo + TOL) and (m < hi - TOL):
        return "model_between_books_that_disagree"
    # Otherwise the model is at/beyond one pole — it sides with the nearer book.
    if abs(m - sharp_p) <= abs(m - soft_p):
        # model close to sharp; if it is also ~equal to sharp and both books straddle,
        # this is the 'agrees with sharp, both disagree with soft' configuration.
        if abs(m - sharp_p) < TOL:
            return "model_agrees_with_sharp_both_disagree_with_soft"
        return "books_disagree_model_sides_with_sharp"
    return "books_disagree_model_sides_with_soft"




def build_scan(mid, row, hist, rich_hist, models, books, rich_info, referee_coverage=None):
    """§3/§4/§5/§6 — produce per-line rows with broad+rich model p, per-book fair probs,
    edge, net edge, fair reference, best price, and cross-book config. No side effects."""
    home, away = row["home"], row["away"]
    kickoff_ts = float(row.get("ts", 0) or 0)
    m = {"home_name": home, "away_name": away, "date_unix": kickoff_ts}
    fitted = _fitted_cells()

    # reliability: adequate history for BOTH teams
    n_home = len(hist.get(home, []))
    n_away = len(hist.get(away, []))
    hist_ok = n_home >= MIN_MATCHES_PER_TEAM and n_away >= MIN_MATCHES_PER_TEAM

    lines = []
    for market, line, book_odds in _iter_book_lines(books):
        cell = (market, line)
        model = models.get(cell)
        fitted_line = cell in fitted and model is not None
        # broad + rich model probabilities (rich = same model, npxG-augmented inputs)
        pm_broad = fp.predict_one(model, hist, m, market) if fitted_line else None
        pm_rich = fp.predict_one(model, rich_hist, m, market) if fitted_line else None
        # per-book devigged fair probs (§3) — fair_p is always P(over/yes)
        book_fair = {}
        for bk, (o, u) in book_odds.items():
            dv = fp.devig(o, u)
            if not dv:
                continue
            fair, ovr = dv
            book_fair[bk] = {"fair_p": round(fair, 4), "overround": round(ovr, 4),
                             "over_odds": float(o), "under_odds": float(u)}
        if not book_fair:
            continue

        ref_book, soft_only = _pick_fair_reference(book_fair)
        ref = book_fair.get(ref_book) if ref_book else None

        entry = {
            "market": market, "line": line,
            "model_p_broad": round(pm_broad, 4) if pm_broad is not None else None,
            "model_p_rich": round(pm_rich, 4) if pm_rich is not None else None,
            "fitted_line": fitted_line,
            "fair_reference_book": ref_book,
            "soft_book_only_reference": soft_only,
            "reference_fair_p": ref["fair_p"] if ref else None,
            "reference_overround": ref["overround"] if ref else None,
            "books": book_fair,
            "broad_rich_disagreement_pp": (
                round(abs(pm_broad - pm_rich) * 100, 2)
                if (pm_broad is not None and pm_rich is not None) else None),
        }

        # edge per book (§3) — computed on the BROAD model p (the registered, more-history
        # configuration); rich edge recorded too for divergence analysis.
        if pm_broad is not None:
            for bk, b in book_fair.items():
                b["edge_pp_broad"] = round((pm_broad - b["fair_p"]) * 100, 2)
                if pm_rich is not None:
                    b["edge_pp_rich"] = round((pm_rich - b["fair_p"]) * 100, 2)

        # §4/§5 edge, net edge, side, best price — only meaningful when the line is fitted
        if pm_broad is not None and ref is not None:
            raw_edge = (pm_broad - ref["fair_p"]) * 100.0   # pp vs the FAIR reference
            side_over = raw_edge >= 0                        # model favours over/yes if p>fair
            # required edge from THIS line's overround = the per-side share of the take
            required_edge = (ref["overround"] * 100.0) / 2.0
            net_edge = abs(raw_edge) - required_edge
            # best available PRICE on the model's side (§5)
            price_side = "over" if side_over else "under"
            bp_book, bp_odds = _best_price(book_fair, price_side)
            ref_side_odds = ref["over_odds"] if side_over else ref["under_odds"]
            # price improvement from shopping, as % of the reference price
            price_improve_pct = (round((bp_odds - ref_side_odds) / ref_side_odds * 100, 2)
                                 if (bp_odds and ref_side_odds) else None)
            # realized edge = model p vs fair p, executed at the best price (expressed as
            # the EV per unit staked at the best price on the model's side)
            model_side_p = pm_broad if side_over else (1.0 - pm_broad)
            realized_ev_pct = (round((model_side_p * bp_odds - 1.0) * 100, 2)
                               if bp_odds else None)
            entry.update({
                "side": ("over" if market != "btts" else "yes") if side_over
                        else ("under" if market != "btts" else "no"),
                "raw_edge_pp": round(raw_edge, 2),
                "abs_edge_pp": round(abs(raw_edge), 2),
                "required_edge_pp": round(required_edge, 2),
                "net_edge_pp": round(net_edge, 2),
                "best_price_book": bp_book,
                "best_price_odds": bp_odds,
                "reference_side_odds": ref_side_odds,
                "price_improvement_pct": price_improve_pct,
                "realized_ev_at_best_price_pct": realized_ev_pct,
                "cross_book_config": _cross_book_config(pm_broad, book_fair, ref_book, side_over),
            })
            # §4 reliability: non-extreme estimate for BOTH broad and (if present) rich
            est_ok = (RELIABILITY_PROB_BOUNDS[0] <= pm_broad <= RELIABILITY_PROB_BOUNDS[1])
            entry["reliability"] = {
                "history_ok": hist_ok, "n_home": n_home, "n_away": n_away,
                "min_matches_required": MIN_MATCHES_PER_TEAM,
                "estimate_non_extreme": est_ok,
                "prob_bounds": list(RELIABILITY_PROB_BOUNDS),
                "passes": bool(hist_ok and est_ok),
            }
            entry["is_flag"] = bool(net_edge >= NET_EDGE_FLAG_PP)
        else:
            entry["is_flag"] = False
        lines.append(entry)

    return {
        "fixture_id": mid, "home": home, "away": away,
        "kickoff_ts": kickoff_ts,
        "kickoff_iso": datetime.fromtimestamp(kickoff_ts, timezone.utc).isoformat() if kickoff_ts else None,
        "reliability_history": {"n_home": n_home, "n_away": n_away,
                                "min_required": MIN_MATCHES_PER_TEAM, "both_ok": hist_ok},
        "rich_info": rich_info,
        "referee_coverage": referee_coverage or {},
        "lines": lines,
    }


def rank_flags(scan):
    """§4 Split scanned lines into (passing_flags, edge_but_failing_reliability, other),
    each ranked by NET EDGE descending (never raw edge). Only lines with net_edge≥threshold
    are 'flags'; among them the reliability filter separates trustworthy from not."""
    flags_pass, flags_fail = [], []
    for e in scan["lines"]:
        if not e.get("is_flag"):
            continue
        rel = e.get("reliability", {})
        (flags_pass if rel.get("passes") else flags_fail).append(e)
    flags_pass.sort(key=lambda e: e["net_edge_pp"], reverse=True)
    flags_fail.sort(key=lambda e: e["net_edge_pp"], reverse=True)
    return flags_pass, flags_fail


# ── §9 commit flags to the SEPARATE flagged-lines log + ledger ─────────────────

def _reference_price_dict(entry):
    ref_book = entry.get("fair_reference_book")
    if not ref_book:
        return None, None
    b = entry["books"][ref_book]
    return ref_book, {
        "book": ref_book, "over_odds": b["over_odds"], "under_odds": b["under_odds"],
        "fair_p": b["fair_p"], "overround": b["overround"],
        "soft_book_only": bool(entry.get("soft_book_only_reference")),
    }


def commit_flags(scan, flags, requested_by, dry_run=False):
    """Commit each PASSING flag to the scanner ledger (own chain, 'flagged:' namespace).
    Never backdates: past-kickoff → UNATTESTED. Returns per-flag commit results."""
    ledger = AttestationLedger(commit_path=SCANNER_COMMIT_LEDGER, reveal_path=SCANNER_REVEAL_LEDGER)
    already = set(ledger.commitments_by_prediction().keys())
    mid = scan["fixture_id"]
    kickoff = scan["kickoff_ts"]
    requested_at = _now_iso()
    results = []
    for entry in flags:
        pid = _flag_id(mid, entry["market"], entry["line"])
        ref_book, reference_price = _reference_price_dict(entry)
        rec = {"prediction_id": pid, "market": entry["market"], "line": entry["line"],
               "model_p_broad": entry["model_p_broad"], "model_p_rich": entry["model_p_rich"],
               "net_edge_pp": entry["net_edge_pp"], "side": entry.get("side"),
               "reference_price": reference_price}
        if dry_run:
            rec["attested"] = False
            rec["attestation_note"] = "dry-run: not committed"
            results.append(rec); continue
        if pid in already:
            existing = ledger.commitments_by_prediction()[pid]
            rec["attested"] = True
            rec["commitment_hash"] = existing["commitment_hash"]
            rec["attestation_note"] = "already committed (idempotent, not re-committed)"
            results.append(rec); continue
        if reference_price is None:
            rec["attested"] = False
            rec["attestation_note"] = "no reference price to bind"
            results.append(rec); continue
        # p_over/p_under bound into the hash use the BROAD model p (the registered config)
        p_over = entry["model_p_broad"]
        p_under = round(1.0 - p_over, 4)
        res = ledger.commit(
            prediction_id=pid, fixture_id=str(mid),
            model=f"{entry['market']}_{entry['line']}", kickoff_unix=float(kickoff),
            p_over=p_over, p_under=p_under, reference_price=reference_price,
            extra={"source": "scanner", "requested_by": requested_by or "unspecified",
                   "requested_at": requested_at, "p_over": p_over, "p_under": p_under,
                   "model_p_rich": entry["model_p_rich"], "side": entry.get("side"),
                   "best_price_book": entry.get("best_price_book"),
                   "best_price_odds": entry.get("best_price_odds"),
                   "net_edge_pp": entry["net_edge_pp"],
                   "cross_book_config": entry.get("cross_book_config"),
                   "soft_book_only_reference": entry.get("soft_book_only_reference")},
        )
        if res.committed:
            rec["attested"] = True
            rec["commitment_hash"] = res.record["commitment_hash"]
            rec["prediction_timestamp"] = res.record["prediction_timestamp"]
        else:
            rec["attested"] = False
            rec["attestation_note"] = res.reason
        results.append(rec)
    return results


def _append_flag_log(scan, flags_pass, flags_fail, commit_results, requested_by):
    """§9 Append a flagged-lines record to the SEPARATE scanner log (own file). Records
    both the passing flags (with commitment) and the edge-but-failing-reliability list."""
    Path(SCANNER_FLAGGED_LOG).parent.mkdir(parents=True, exist_ok=True)
    cr_by_id = {c["prediction_id"]: c for c in commit_results}
    now = _now_iso()

    def _flag_record(entry, committed):
        ref_book, reference_price = _reference_price_dict(entry)
        cr = cr_by_id.get(_flag_id(scan["fixture_id"], entry["market"], entry["line"]), {})
        return {
            "prediction_id": _flag_id(scan["fixture_id"], entry["market"], entry["line"]),
            "fixture_id": scan["fixture_id"], "home": scan["home"], "away": scan["away"],
            "kickoff_iso": scan["kickoff_iso"],
            "market": entry["market"], "line": entry["line"], "side": entry.get("side"),
            "model_p_broad": entry["model_p_broad"], "model_p_rich": entry["model_p_rich"],
            "broad_rich_disagreement_pp": entry.get("broad_rich_disagreement_pp"),
            "fair_reference_book": ref_book,
            "reference_price": reference_price,
            "soft_book_only_reference": entry.get("soft_book_only_reference"),
            "overround": entry.get("reference_overround"),
            "raw_edge_pp": entry.get("raw_edge_pp"),
            "required_edge_pp": entry.get("required_edge_pp"),
            "net_edge_pp": entry.get("net_edge_pp"),
            "best_price_book": entry.get("best_price_book"),
            "best_price_odds": entry.get("best_price_odds"),
            "price_improvement_pct": entry.get("price_improvement_pct"),
            "realized_ev_at_best_price_pct": entry.get("realized_ev_at_best_price_pct"),
            "cross_book_config": entry.get("cross_book_config"),
            "reliability": entry.get("reliability"),
            "reliability_status": "pass" if entry.get("reliability", {}).get("passes") else "fail",
            "committed": committed,
            "attested": cr.get("attested", False),
            "commitment_hash": cr.get("commitment_hash"),
            "attestation_note": cr.get("attestation_note"),
            # §7 price at flag time; movement filled in by --recapture
            "price_at_flag_time": {"best_price_book": entry.get("best_price_book"),
                                   "best_price_odds": entry.get("best_price_odds"),
                                   "reference_side_odds": entry.get("reference_side_odds"),
                                   "captured_at": now},
            "price_near_kickoff": None,
            "price_movement": None,
            "logged_at": now,
        }
    row = {
        "source": "scanner", "requested_by": requested_by or "unspecified",
        "logged_at": now, "fixture_id": scan["fixture_id"],
        "home": scan["home"], "away": scan["away"], "kickoff_iso": scan["kickoff_iso"],
        "flags_passing_reliability": [_flag_record(e, True) for e in flags_pass],
        "flags_edge_but_failing_reliability": [_flag_record(e, False) for e in flags_fail],
    }
    with open(SCANNER_FLAGGED_LOG, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")
    return row


def _iter_logged_flags(only_fixture=None):
    """Yield every logged passing flag record (across all scanner-log rows). Passing flags
    are the committed hypotheses; failing-reliability ones are recorded but not settled as
    part of the primary sample."""
    if not os.path.exists(SCANNER_FLAGGED_LOG):
        return
    with open(SCANNER_FLAGGED_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            if only_fixture and r.get("fixture_id") != only_fixture:
                continue
            for fr in r.get("flags_passing_reliability", []):
                yield r, fr


# ── §7 re-capture prices near kickoff ──────────────────────────────────────────

def recapture_prices(mid):
    """§7 Re-capture the flagged best price shortly before kickoff (cache-first, minimal
    cost) and record the movement. Rewrites the scanner log rows for this fixture in place
    with price_near_kickoff + price_movement populated on each passing flag.

    NOTE: cache-first fetch will only see NEW prices if the odds cache has been refreshed
    since the flag was made (a fresh fetch requires the raw cache to be re-pulled, which is
    a deliberate budget decision made outside this tool). We record what the cache holds
    now versus flag time and compute the movement honestly, including 'no_change' when the
    cache is unchanged."""
    if not os.path.exists(SCANNER_FLAGGED_LOG):
        return {"error": "no scanner flag log yet"}
    books, usage = fetch_odds(mid, dry_run=False)
    # rebuild current best price per (market,line,side) from the current cache
    current = {}
    for market, line, book_odds in _iter_book_lines(books):
        book_fair = {}
        for bk, (o, u) in book_odds.items():
            dv = fp.devig(o, u)
            if dv:
                book_fair[bk] = {"over_odds": float(o), "under_odds": float(u)}
        for side in ("over", "under"):
            bk, odds = _best_price(book_fair, side)
            current[(market, line, side)] = (bk, odds)

    rows = []
    with open(SCANNER_FLAGGED_LOG) as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    now = _now_iso()
    updated = 0
    for r in rows:
        if r.get("fixture_id") != mid:
            continue
        for fr in r.get("flags_passing_reliability", []):
            side = fr.get("side")
            ou = "over" if side in ("over", "yes") else "under"
            key = (fr["market"], fr["line"], ou)
            bk, odds = current.get(key, (None, None))
            flag_odds = (fr.get("price_at_flag_time") or {}).get("best_price_odds")
            movement = None
            if odds is not None and flag_odds is not None:
                delta = round(odds - flag_odds, 4)
                # "toward the model" = model backs `side`; longer odds (higher) means the
                # market moved AWAY from the model's side; shorter odds means TOWARD it.
                if delta == 0:
                    direction = "no_change"
                elif delta < 0:
                    direction = "toward_model"   # price shortened on the backed side
                else:
                    direction = "away_from_model"  # price drifted (lengthened)
                movement = {"delta_odds": delta, "direction": direction,
                            "flag_odds": flag_odds, "kickoff_odds": odds,
                            "held": bool(odds >= flag_odds)}
            fr["price_near_kickoff"] = {"best_price_book": bk, "best_price_odds": odds,
                                        "captured_at": now}
            fr["price_movement"] = movement
            updated += 1
    with open(SCANNER_FLAGGED_LOG, "w") as f:
        for r in rows:
            f.write(json.dumps(r, default=str) + "\n")
    return {"fixture_id": mid, "flags_updated": updated, "quota": usage}


# ── §9 settle flags + scorecard ────────────────────────────────────────────────

def settle_flags(only_fixture=None):
    """Grade finished fixtures' flags and reveal outcomes against scanner commitments.
    Writes ONLY scanner files. Mirrors pilotC_settle grading via its read-only helpers."""
    import thestatsapi_client as api
    from pilotC_settle import _fetch_final, _grade

    ledger = AttestationLedger(commit_path=SCANNER_COMMIT_LEDGER, reveal_path=SCANNER_REVEAL_LEDGER)
    committed = ledger.commitments_by_prediction()
    already_revealed = set(ledger.reveals_by_prediction().keys())

    settled_log = {"settled": []}
    if os.path.exists(SCANNER_SETTLED_LOG):
        try:
            settled_log = json.load(open(SCANNER_SETTLED_LOG))
        except Exception:
            pass
    logged = {r["prediction_id"] for r in settled_log["settled"]}

    # collect flag metadata (best price, config, etc.) from the flag log by prediction_id
    flag_meta = {}
    for _row, fr in _iter_logged_flags(only_fixture):
        flag_meta[fr["prediction_id"]] = fr

    out = {"revealed": 0, "graded": 0, "ungradeable": 0, "rows": []}
    final_cache = {}
    for pid, c in committed.items():
        if not pid.startswith(f"{SCANNER_ID_PREFIX}:"):
            continue
        mid = c["fixture_id"]
        if only_fixture and mid != only_fixture:
            continue
        if pid in already_revealed:
            out["rows"].append({"prediction_id": pid, "status": "already_revealed"})
            continue
        market = c["model"].rsplit("_", 1)[0]
        line_s = c["model"].rsplit("_", 1)[1]
        line = None if line_s == "None" else float(line_s)
        try:
            if mid not in final_cache:
                final_cache[mid] = _fetch_final(api, mid)
            final = final_cache[mid]
        except SystemExit:
            out["rows"].append({"prediction_id": pid, "status": "cap_reached"})
            break
        actual, value = _grade(market, line, final)
        if actual is None:
            out["ungradeable"] += 1
            out["rows"].append({"prediction_id": pid, "status": "ungradeable_missing_result"})
            continue
        model_p = c.get("p_over")            # == broad P(over/yes)
        side = c.get("side") or "over"
        # did the flagged SIDE win? actual is P(over/yes) as 1.0/0.0
        side_over = side in ("over", "yes")
        side_won = 1.0 if ((actual == 1.0) == side_over) else 0.0
        meta = flag_meta.get(pid, {})
        best_odds = meta.get("best_price_odds") or c.get("best_price_odds")
        # realized return of a 1-unit back bet at the flagged best price
        realized_return = None
        if best_odds:
            realized_return = round((best_odds - 1.0) if side_won else -1.0, 4)
        brier = (model_p - actual) ** 2 if model_p is not None else None
        now_iso = _now_iso()
        if pid not in logged:
            settled_log["settled"].append({
                "source": "scanner", "prediction_id": pid, "match_id": mid,
                "market": market, "line": line, "side": side,
                "model_p_broad": model_p, "model_p_rich": c.get("model_p_rich"),
                "actual_over_or_yes": actual, "actual_value": value,
                "side_won": side_won,
                "best_price_book": meta.get("best_price_book") or c.get("best_price_book"),
                "best_price_odds": best_odds,
                "realized_return_at_best_price": realized_return,
                "brier_contribution": round(brier, 6) if brier is not None else None,
                "net_edge_pp": c.get("net_edge_pp"),
                "soft_book_only_reference": c.get("soft_book_only_reference"),
                "cross_book_config": c.get("cross_book_config"),
                "price_held_to_kickoff": (meta.get("price_movement") or {}).get("held"),
                "settled_at": now_iso,
            })
            logged.add(pid); out["graded"] += 1
        res = ledger.reveal(prediction_id=pid, fixture_id=str(mid), model=c["model"],
                            outcome={"actual_over_or_yes": actual, "actual_value": value,
                                     "side": side, "side_won": side_won,
                                     "model_p_broad": model_p,
                                     "realized_return_at_best_price": realized_return,
                                     "brier_contribution": round(brier, 6) if brier is not None else None},
                            settled_at=now_iso, extra={"source": "scanner"})
        if res.committed:
            out["revealed"] += 1
            out["rows"].append({"prediction_id": pid, "status": "revealed",
                                "side_won": side_won, "realized_return": realized_return})
        else:
            out["rows"].append({"prediction_id": pid, "status": "reveal_declined",
                                "reason": res.reason})
    settled_log["updated_at"] = _now_iso()
    settled_log["n_settled_total"] = len(settled_log["settled"])
    Path(SCANNER_SETTLED_LOG).parent.mkdir(parents=True, exist_ok=True)
    json.dump(settled_log, open(SCANNER_SETTLED_LOG, "w"), indent=2, default=str)
    build_scorecard()
    return out


def _bootstrap_ci(values, n_boot=10000, seed=42):
    """95% bootstrap CI of the mean (seed fixed to match the pre-registration)."""
    if not values:
        return None, None
    import random
    rng = random.Random(seed)
    n = len(values)
    means = []
    for _ in range(n_boot):
        s = sum(values[rng.randrange(n)] for _ in range(n))
        means.append(s / n)
    means.sort()
    lo = means[int(0.025 * n_boot)]
    hi = means[int(0.975 * n_boot)]
    return round(lo, 4), round(hi, 4)


def build_scorecard():
    """§9 Running scorecard: flags made/settled, hit rate, realized return + CI, broken
    down by near-fair vs soft-book-only, broad vs rich, cross-book config, and whether the
    price held to kickoff. Reads the pre-registration to show the stopping threshold and
    whether it has been reached — but NEVER computes an early verdict."""
    # flags made (from the flag log)
    flags_made = 0
    for _row, _fr in _iter_logged_flags():
        flags_made += 1

    settled = []
    if os.path.exists(SCANNER_SETTLED_LOG):
        try:
            settled = json.load(open(SCANNER_SETTLED_LOG)).get("settled", [])
        except Exception:
            settled = []

    n_settled = len(settled)
    wins = [r for r in settled if r.get("side_won") == 1.0]
    returns = [r["realized_return_at_best_price"] for r in settled
               if r.get("realized_return_at_best_price") is not None]

    def _bucket(pred):
        b_settled = [r for r in settled if pred(r)]
        b_ret = [r["realized_return_at_best_price"] for r in b_settled
                 if r.get("realized_return_at_best_price") is not None]
        n = len(b_settled)
        w = sum(1 for r in b_settled if r.get("side_won") == 1.0)
        return {"n_settled": n, "hit_rate": round(w / n, 4) if n else None,
                "mean_realized_return": round(sum(b_ret) / len(b_ret), 4) if b_ret else None}

    prereg = {}
    if os.path.exists(SCANNER_PREREG_DOC):
        try:
            prereg = json.load(open(SCANNER_PREREG_DOC))
        except Exception:
            prereg = {}
    min_flags = (prereg.get("minimum_sample_and_stopping_rule", {})
                 .get("minimum_settled_flags_before_evaluation"))
    reached = (min_flags is not None and n_settled >= min_flags)

    lo, hi = (_bootstrap_ci(returns) if reached else (None, None))

    scorecard = {
        "generated": _now_iso(),
        "experiment": "on-demand edge scanner (structurally separate from Pilot C)",
        "preregistration": {
            "document": SCANNER_PREREG_DOC, "ledger": SCANNER_PREREG_LEDGER,
            "minimum_settled_flags_before_evaluation": min_flags,
            "primary_question": (prereg.get("primary_question", {}) or {}).get("statement"),
        },
        "flags_made": flags_made,
        "flags_settled": n_settled,
        "hit_rate": round(len(wins) / n_settled, 4) if n_settled else None,
        "mean_realized_return_at_best_price": (round(sum(returns) / len(returns), 4)
                                               if returns else None),
        "stopping_threshold_reached": reached,
        "primary_realized_return_ci95": (
            {"lower": lo, "upper": hi, "note": "confirmatory readout — computed only "
             "because the settled-flag threshold has been reached"} if reached else
            {"lower": None, "upper": None,
             "note": (f"WITHHELD — {n_settled}/{min_flags} settled flags. The primary "
                      "realized-return CI is the confirmatory readout and is NOT computed "
                      "before the pre-registered threshold, to avoid concluding from noise.")}),
        "breakdown": {
            "reference_type": {
                "near_fair": _bucket(lambda r: not r.get("soft_book_only_reference")),
                "soft_book_only": _bucket(lambda r: bool(r.get("soft_book_only_reference"))),
            },
            "model": {
                "broad_and_rich_agree": _bucket(
                    lambda r: r.get("model_p_rich") is None or
                    abs((r.get("model_p_broad") or 0) - (r.get("model_p_rich") or 0)) < 0.02),
                "broad_and_rich_diverge": _bucket(
                    lambda r: r.get("model_p_rich") is not None and
                    abs((r.get("model_p_broad") or 0) - (r.get("model_p_rich") or 0)) >= 0.02),
            },
            "cross_book_config": {
                cfg: _bucket(lambda r, c=cfg: r.get("cross_book_config") == c)
                for cfg in sorted({r.get("cross_book_config") for r in settled
                                   if r.get("cross_book_config")})
            },
            "price_held_to_kickoff": {
                "held": _bucket(lambda r: r.get("price_held_to_kickoff") is True),
                "moved": _bucket(lambda r: r.get("price_held_to_kickoff") is False),
                "unknown": _bucket(lambda r: r.get("price_held_to_kickoff") is None),
            },
        },
        "caveat": CAVEAT,
        "publication_rule": "If shared publicly, ALL settled flags are reported whether "
                            "they won or lost. Publishing only hits makes a record worthless.",
    }
    Path(SCANNER_SCORECARD).parent.mkdir(parents=True, exist_ok=True)
    json.dump(scorecard, open(SCANNER_SCORECARD, "w"), indent=2, default=str)
    return scorecard


# ── independent hash verification ──────────────────────────────────────────────

def verify_hash(mid=None):
    ledger = AttestationLedger(commit_path=SCANNER_COMMIT_LEDGER, reveal_path=SCANNER_REVEAL_LEDGER)
    rows = ledger.load_commitments()
    if mid:
        rows = [r for r in rows if r["fixture_id"] == str(mid)]
    checked = []
    for r in rows:
        recomputed = compute_commitment_hash(
            prediction_id=r["prediction_id"], fixture_id=r["fixture_id"],
            model=r["model"], p_over=r.get("p_over"), p_under=r.get("p_under"),
            reference_price=r.get("reference_price"),
            prediction_timestamp=r["prediction_timestamp"],
        )
        checked.append({"prediction_id": r["prediction_id"],
                        "stored_commitment_hash": r["commitment_hash"],
                        "recomputed_commitment_hash": recomputed,
                        "recomputed_matches": recomputed == r["commitment_hash"]})
    ok_chain, problems = ledger.verify_chain(SCANNER_COMMIT_LEDGER)
    return {"rows_checked": len(checked), "detail": checked,
            "chain_verifies": ok_chain, "chain_problems": problems[:5]}


# ── output rendering (§11) ──────────────────────────────────────────────────────

def render_summary(scan, flags_pass, flags_fail, commit_results, usage, rich_coverage,
                   requested_by, dry_run):
    L = []
    A = L.append
    mid = scan["fixture_id"]
    A("=" * 78)
    tag = "DRY-RUN (flags NOT committed)" if dry_run else "EDGE SCAN (flags on the record)"
    A(f"{tag} — source=scanner  requested_by={requested_by or 'unspecified'}")
    A("=" * 78)
    A(f"Fixture : {scan['home']} v {scan['away']}  [{mid}]")
    A(f"Kickoff : {scan['kickoff_iso']}")
    A("")

    # §1 data coverage per team (honest)
    A("DATA COVERAGE (per team) — how much the flags rest on:")
    rh = scan["reliability_history"]
    A(f"  corpus match history: {scan['home']}={rh['n_home']}  {scan['away']}={rh['n_away']}  "
      f"(min required for reliability: {rh['min_required']})")
    if rh["n_home"] < rh["min_required"] or rh["n_away"] < rh["min_required"]:
        thinner = scan['home'] if rh['n_home'] <= rh['n_away'] else scan['away']
        A(f"  ** {thinner} has materially thin history — flags for this fixture are less reliable. **")
    for team, cov in (rich_coverage or {}).items():
        npop = len(cov.get("rich_fields_populated", {}))
        nnull = len(cov.get("rich_fields_null", {}))
        A(f"  rich /stats [{team}]: joinable={cov.get('rich_joinable_matches', 0)}/"
          f"{cov['recent_considered']} recent matches carry a TheStatsAPI mt_ id; "
          f"{cov['stats_matches_available']} had /stats; npxG in {cov['npxg_matches']}; "
          f"rich fields populated={npop} null-only={nnull}")
    ri = scan.get("rich_info", {})
    A(f"  rich model inputs: npxG substituted into xG for {ri.get('npxg_substitutions', 0)} "
      f"match-rows; both teams covered={ri.get('both_covered', False)} "
      f"({'RICH ACTIVE' if ri.get('both_covered') else 'rich falls back to broad'})")
    if not ri.get("rich_structurally_available", False) and ri.get("unavailable_reason"):
        A(f"  ** RICH UNAVAILABLE (structural): {ri['unavailable_reason']}")
    ref_cov = scan.get("referee_coverage", {})
    if ref_cov:
        if ref_cov.get("assignment_available"):
            A(f"  referee: assigned={ref_cov.get('assigned_referee')} "
              f"history_available={ref_cov.get('referee_history_available')}")
        elif ref_cov.get("referee_history_available"):
            A("  referee: NO assignment in the fixture feed — corpus does carry per-match "
              "refereeID (a history could be built) but with no assignment it cannot be "
              "tied to this fixture. Not used (the cards model uses team foul/card features).")
        else:
            A(f"  referee: UNAVAILABLE — {ref_cov.get('note')}")
    A("")

    # scanned lines (§3) — compact per market/line, one line per book
    A("SCANNED LINES (every line any book offers; edge on BROAD model vs each book's fair):")
    hdr = (f"{'mkt':6s} {'line':>5s} {'p_brd':>6s} {'p_rich':>6s} {'book':15s} "
           f"{'fair':>6s} {'ovr%':>5s} {'edge':>6s} {'net':>6s}")
    A(hdr); A("-" * len(hdr))
    for e in scan["lines"]:
        ln = "-" if e["line"] is None else f"{e['line']:.1f}"
        pb = f"{e['model_p_broad']:.3f}" if e["model_p_broad"] is not None else "  -  "
        pr = f"{e['model_p_rich']:.3f}" if e["model_p_rich"] is not None else "  -  "
        first = True
        for bk, b in e["books"].items():
            edge = b.get("edge_pp_broad")
            edge_s = f"{edge:+.2f}" if edge is not None else "  -  "
            # net edge is a per-line (reference) quantity; show it on the ref book row
            net_s = (f"{e['net_edge_pp']:+.2f}"
                     if (bk == e.get("fair_reference_book") and e.get("net_edge_pp") is not None)
                     else "")
            soft = " (soft)" if bk in SOFT_BOOKS else ""
            refmk = " *ref" if bk == e.get("fair_reference_book") else ""
            A(f"{(e['market'] if first else ''):6s} {(ln if first else ''):>5s} "
              f"{(pb if first else ''):>6s} {(pr if first else ''):>6s} "
              f"{bk+soft:15s} {b['fair_p']:6.3f} {b['overround']*100:5.1f} "
              f"{edge_s:>6s} {net_s:>6s}{refmk}")
            first = False
    A("")

    # §2 broad vs rich divergence
    div = [e for e in scan["lines"] if e.get("broad_rich_disagreement_pp")]
    if div:
        A("BROAD vs RICH divergence (rich rests on far less history — divergence is informative):")
        for e in sorted(div, key=lambda x: x["broad_rich_disagreement_pp"], reverse=True)[:8]:
            ln = "-" if e["line"] is None else f"{e['line']:.1f}"
            A(f"  {e['market']} {ln}: broad={e['model_p_broad']:.3f} rich={e['model_p_rich']:.3f} "
              f"Δ={e['broad_rich_disagreement_pp']:.2f}pp")
        A("")

    # §4 ranked flags (net of hurdle), passing reliability
    A("FLAGS — ranked by EDGE NET OF THE MARGIN HURDLE (never raw edge). Reliability: PASS")
    if flags_pass:
        for e in flags_pass:
            _render_flag_line(A, e)
    else:
        A("  (none pass both the net-edge threshold and the reliability filter)")
    A("")
    # flags with edge but FAILING reliability — reported separately, not dropped
    A("FLAGS with edge but FAILING the reliability filter (recorded, NOT in the primary sample):")
    if flags_fail:
        for e in flags_fail:
            _render_flag_line(A, e, failed=True)
    else:
        A("  (none)")
    A("")

    # commitment hashes
    committed_rows = [c for c in commit_results if c.get("commitment_hash")]
    if committed_rows and not dry_run:
        A("Commitment hashes (independently verifiable — see --verify-hash):")
        for c in committed_rows:
            A(f"  {c['prediction_id']}  {c['commitment_hash']}")
        A("")
    unattested = [c for c in commit_results if not c.get("attested") and not dry_run]
    if unattested:
        A("Flags NOT attested (never backdated):")
        for c in unattested:
            A(f"  {c['prediction_id']}: {c.get('attestation_note')}")
        A("")

    # quota
    A(f"Quota: live_requests_this_run={usage.get('live_requests_made')} "
      f"cached_book_hits={usage.get('cached_hits')} "
      f"monthly_remaining={usage.get('monthly_remaining_after')}")
    A("")

    # §11 scorecard so any single flag is seen against the record so far
    sc = build_scorecard()
    A("RUNNING SCORECARD (so any single flag is seen against the record so far):")
    A(f"  flags made={sc['flags_made']}  settled={sc['flags_settled']}  "
      f"hit_rate={sc['hit_rate']}  mean_realized_return={sc['mean_realized_return_at_best_price']}")
    A(f"  pre-registered stopping threshold: {sc['preregistration']['minimum_settled_flags_before_evaluation']} "
      f"settled flags  (reached={sc['stopping_threshold_reached']})")
    A(f"  primary realized-return CI95: {sc['primary_realized_return_ci95']['note']}")
    A("")
    A(CAVEAT)
    A("=" * 78)
    return "\n".join(L)


def _render_flag_line(A, e, failed=False):
    ln = "-" if e["line"] is None else f"{e['line']:.1f}"
    soft = "  [SOFT-BOOK-ONLY REF — least trustworthy]" if e.get("soft_book_only_reference") else ""
    rel = e.get("reliability", {})
    relnote = "" if not failed else (
        f"  [reliability FAIL: "
        f"{'thin history' if not rel.get('history_ok') else ''}"
        f"{' & ' if (not rel.get('history_ok') and not rel.get('estimate_non_extreme')) else ''}"
        f"{'extreme estimate' if not rel.get('estimate_non_extreme') else ''}]")
    A(f"  {e['market']} {ln} {e.get('side','')}: "
      f"model_broad={e['model_p_broad']:.3f} vs fair={e['reference_fair_p']:.3f} "
      f"({e.get('fair_reference_book')})")
    A(f"      raw_edge={e['raw_edge_pp']:+.2f}pp  hurdle={e['required_edge_pp']:.2f}pp  "
      f"NET_EDGE={e['net_edge_pp']:+.2f}pp  overround={e['reference_overround']*100:.1f}%")
    A(f"      best price {e.get('best_price_odds')} @ {e.get('best_price_book')} "
      f"(ref side odds {e.get('reference_side_odds')}; "
      f"shopping +{e.get('price_improvement_pct')}%); "
      f"realized EV @ best price {e.get('realized_ev_at_best_price_pct')}%")
    A(f"      cross-book: {e.get('cross_book_config')}{soft}{relnote}")


# ── main ────────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="On-demand fixture edge scanner (separate from Pilot C)")
    ap.add_argument("--fixture-id")
    ap.add_argument("--home"); ap.add_argument("--away")
    ap.add_argument("--date", help="YYYY-MM-DD (optional, with --home/--away)")
    ap.add_argument("--requested-by", help="who requested this (recorded for provenance)")
    ap.add_argument("--dry-run", action="store_true", help="scan + flag without committing")
    ap.add_argument("--rich", action="store_true",
                    help="fetch /stats for both teams' recent matches to populate the rich model (budget-capped)")
    ap.add_argument("--recapture", action="store_true",
                    help="re-capture flagged prices near kickoff and record movement (§7)")
    ap.add_argument("--settle", action="store_true", help="settle finished fixtures' flags + refresh scorecard")
    ap.add_argument("--scorecard", action="store_true", help="print the running scorecard only")
    ap.add_argument("--verify-hash", action="store_true", help="re-verify scanner commitment hashes + chain")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = ap.parse_args()

    if args.scorecard:
        print(json.dumps(build_scorecard(), indent=2, default=str))
        print("\n" + CAVEAT)
        sys.exit(0)

    if args.verify_hash:
        mid = args.fixture_id
        if not mid and args.home and args.away:
            mid, _ = resolve_fixture(home=args.home, away=args.away, date=args.date)
        result = verify_hash(mid)
        print(json.dumps(result, indent=2, default=str))
        allok = all(d["recomputed_matches"] for d in result["detail"]) and result["chain_verifies"]
        sys.exit(0 if allok else 1)

    if args.settle:
        only = args.fixture_id
        if not only and args.home and args.away:
            only, _ = resolve_fixture(home=args.home, away=args.away, date=args.date)
        result = settle_flags(only_fixture=only)
        print(json.dumps(result, indent=2, default=str))
        print("\n" + CAVEAT)
        sys.exit(0)

    mid, row = resolve_fixture(fixture_id=args.fixture_id, home=args.home,
                               away=args.away, date=args.date)
    if mid is None:
        print(f"ERROR: {row}", file=sys.stderr)
        sys.exit(2)

    if args.recapture:
        result = recapture_prices(mid)
        print(json.dumps(result, indent=2, default=str))
        print("\n" + CAVEAT)
        sys.exit(0)

    home, away = row["home"], row["away"]
    ok, corpus, missing = check_corpus_support(home, away)
    if not ok:
        print(f"ERROR: cannot scan — no corpus history for: {', '.join(missing)}.", file=sys.stderr)
        print("The model cannot support a prediction for a team it has never seen. Stopping.",
              file=sys.stderr)
        sys.exit(3)
    ms, hist, corpus_teams = corpus

    books, usage = fetch_odds(mid, dry_run=args.dry_run)
    if not books:
        note = ("no cached odds for this fixture and --dry-run does not fetch"
                if args.dry_run else
                "no odds available for this fixture from any book (cannot compute EV)")
        print(f"ERROR: {note}.", file=sys.stderr)
        sys.exit(4)

    models, hp = _fit_models(ms, hist)

    # §1/§2 rich data gathering + npxG-augmented history (cache-first; fetch only with --rich)
    import thestatsapi_client as api
    rich_coverage = gather_rich_coverage(api, hist, home, away, allow_fetch=args.rich)
    rich_hist, rich_info = _build_rich_history(api, ms, hist, home, away, allow_fetch=args.rich)
    referee_coverage = gather_referee_coverage(row, hist, home, away)
    # refresh quota after any rich fetches
    usage["live_requests_made"] = api.live_requests_made()
    usage["monthly_remaining_after"] = api.budget_snapshot().get("last_monthly_remaining")

    scan = build_scan(mid, row, hist, rich_hist, models, books, rich_info, referee_coverage)
    flags_pass, flags_fail = rank_flags(scan)
    commit_results = commit_flags(scan, flags_pass, args.requested_by, dry_run=args.dry_run)
    if not args.dry_run:
        _append_flag_log(scan, flags_pass, flags_fail, commit_results, args.requested_by)

    if args.json:
        print(json.dumps({"scan": scan, "flags_passing": flags_pass,
                          "flags_failing_reliability": flags_fail,
                          "commit_results": commit_results,
                          "rich_coverage": rich_coverage,
                          "referee_coverage": referee_coverage, "quota": usage,
                          "scorecard": build_scorecard(), "caveat": CAVEAT,
                          "dry_run": args.dry_run}, indent=2, default=str))
    else:
        print(render_summary(scan, flags_pass, flags_fail, commit_results, usage,
                             rich_coverage, args.requested_by, args.dry_run))


if __name__ == "__main__":
    main()
