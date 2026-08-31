"""
Pilot C — settle prospective predictions as fixtures finish, and weekly top-up.

score:  read pilotC_forward_predictions.json; for each fixture now finished, fetch its
        final score (/football/matches/{mid}) and stats (/stats) cache-first, grade each
        market line, compute the Brier contribution, and — crucially — auto-REVEAL the
        settled outcome against the prior commitment via the tamper-evident ledger.
        Betfair is the primary benchmark. Appends graded rows to pilotC_settled_log.json.
        Zero API if results already cached; otherwise fetches under the client cap.

        Only predictions that were COMMITTED before kickoff can be revealed (the ledger
        enforces this). Reveal is idempotent — a prediction already revealed is skipped.

topup:  regenerate the fixture list (future+recent w/o odds) and run pilotC_multibook_fetch
        again — cache-first, so only NEW fixtures cost budget. Run weekly.

Usage:  python scripts/pilotC_settle.py score
        python scripts/pilotC_settle.py topup [--fetch] [--max=N]
"""
import sys, json, glob, os, time
from datetime import datetime, timezone
sys.path.insert(0,'/home/ubuntu'); sys.path.insert(0,'/home/ubuntu/scripts')

from src.research.forward.attestation_ledger import AttestationLedger

CH='/home/ubuntu/data/thestatsapi/championship'
PRED='/home/ubuntu/data/discovery/pilotC_forward_predictions.json'
LOG='/home/ubuntu/data/discovery/pilotC_settled_log.json'
LIST=f'{CH}/_pilotC_fixture_list.json'
TOPUP_REPORT='/home/ubuntu/data/discovery/pilotC_topup_plan.json'
COMMIT_LEDGER='/home/ubuntu/data/forward/pilotC_commitments.jsonl'
REVEAL_LEDGER='/home/ubuntu/data/forward/pilotC_reveals.jsonl'
MARKETS_PER_FIXTURE=4  # goals 1.5/2.5/3.5 + btts (per pilotC_forward_predict)

# Finished statuses in TheStatsAPI vocabulary (defensive — accept several spellings).
_FINISHED = {"finished", "complete", "completed", "ft", "full-time", "ended"}


def _pred_id(mid, market, line):
    return f"pilotC:{mid}:{market}:{line}"


def _num(x):
    try:
        return float(x)
    except Exception:
        return None


def _score_from_match_detail(dd):
    """Extract (home_goals, away_goals) from a /football/matches/{mid} payload.

    The live API shape is not 100% pinned in cache, so try the known spellings
    defensively and return (None, None) if the final score isn't available.
    """
    if not isinstance(dd, dict):
        return None, None
    # shape A: {"score": {"home": h, "away": a}}
    sc = dd.get("score")
    if isinstance(sc, dict):
        h = _num(sc.get("home")); a = _num(sc.get("away"))
        if h is not None and a is not None:
            return h, a
        # nested {"score": {"fulltime"/"current": {"home","away"}}}
        for k in ("fulltime", "full_time", "ft", "current", "total"):
            node = sc.get(k)
            if isinstance(node, dict):
                h = _num(node.get("home")); a = _num(node.get("away"))
                if h is not None and a is not None:
                    return h, a
    # shape B: flat goal-count fields
    for hk, ak in (("homeGoalCount", "awayGoalCount"),
                   ("home_goals", "away_goals"),
                   ("home_score", "away_score"),
                   ("goals_home", "goals_away")):
        h = _num(dd.get(hk)); a = _num(dd.get(ak))
        if h is not None and a is not None:
            return h, a
    return None, None


def _stat_pair_total(stats_overview, key):
    """Sum home+away of stats_overview[key]['all'] — corners/cards live here."""
    node = (stats_overview or {}).get(key)
    if not isinstance(node, dict):
        return None
    allv = node.get("all", node)
    if not isinstance(allv, dict):
        return None
    h = _num(allv.get("home")); a = _num(allv.get("away"))
    if h is None or a is None:
        return None
    return h + a


def _fixture_status(meta, mid):
    row = meta.get(mid, {})
    return str(row.get("status", "")).lower()


def _fetch_final(api, mid):
    """Fetch final score + stats for a finished fixture, cache-first.

    Returns dict with home_goals/away_goals/total_corners/total_cards where available,
    or None if the fixture data can't be retrieved. Each call is cache-first, so a
    re-run of an already-settled fixture costs ZERO budget.
    """
    # match detail -> score (goals, btts)
    dm, mm = api.get_json(f"/football/matches/{mid}", cache_key=f"pilotC_match_{mid}",
                          allow_status=(200, 404, 422))
    detail = (dm or {}).get("data", dm) if dm else {}
    hg, ag = _score_from_match_detail(detail if isinstance(detail, dict) else {})

    # stats -> corners, cards
    ds, ms = api.get_json(f"/football/matches/{mid}/stats", cache_key=f"pilotC_stats_{mid}",
                          allow_status=(200, 404, 422))
    ov = (ds or {}).get("data", ds) if ds else {}
    ov = ov.get("overview", ov) if isinstance(ov, dict) else {}
    total_corners = _stat_pair_total(ov, "corner_kicks")
    yellows = _stat_pair_total(ov, "yellow_cards")
    reds = _stat_pair_total(ov, "red_cards")
    total_cards = None
    if yellows is not None:
        total_cards = yellows + (reds or 0.0)

    return {
        "home_goals": hg, "away_goals": ag,
        "total_goals": (hg + ag) if (hg is not None and ag is not None) else None,
        "total_corners": total_corners,
        "total_cards": total_cards,
    }


def _grade(market, line, final):
    """Return (actual_over_or_yes, actual_value) or (None, None) if ungradeable."""
    if market == "goals":
        t = final.get("total_goals")
        if t is None:
            return None, None
        return (1.0 if t > line else 0.0), t
    if market == "corners":
        t = final.get("total_corners")
        if t is None:
            return None, None
        return (1.0 if t > line else 0.0), t
    if market == "cards":
        t = final.get("total_cards")
        if t is None:
            return None, None
        return (1.0 if t > line else 0.0), t
    if market == "btts":
        hg, ag = final.get("home_goals"), final.get("away_goals")
        if hg is None or ag is None:
            return None, None
        return (1.0 if (hg >= 1 and ag >= 1) else 0.0), (hg, ag)
    return None, None


def _load_settled_log():
    if os.path.exists(LOG):
        try:
            return json.load(open(LOG))
        except Exception:
            return {"settled": []}
    return {"settled": []}


def score(verbose=True):
    """Grade finished fixtures and reveal outcomes against prior commitments.

    Idempotent: fixtures already revealed are skipped; result fetches are cache-first.
    Returns a stats dict for the orchestrator/health report.
    """
    import thestatsapi_client as api
    stats = {
        "predictions_examined": 0,
        "fixtures_finished": 0,
        "graded": 0,
        "revealed": 0,
        "reveal_declined_no_commitment": 0,
        "skipped_not_finished": 0,
        "skipped_already_revealed": 0,
        "ungradeable_missing_result": 0,
        "errors": [],
        "per_cell_settled_added": {},
    }

    if not os.path.exists(PRED):
        if verbose:
            print("no predictions file yet:", PRED)
        return stats

    preds = json.load(open(PRED)).get("predictions", [])
    meta = json.load(open(LIST)).get("meta", {}) if os.path.exists(LIST) else {}

    ledger = AttestationLedger(commit_path=COMMIT_LEDGER, reveal_path=REVEAL_LEDGER)
    committed = ledger.commitments_by_prediction()
    already_revealed = set(ledger.reveals_by_prediction().keys())

    settled_log = _load_settled_log()
    logged_ids = {r["prediction_id"] for r in settled_log["settled"]}

    # cache final results per fixture within this run (avoid double fetch across markets)
    final_cache = {}

    for r in preds:
        stats["predictions_examined"] += 1
        mid = r["match_id"]; market = r["market"]; line = r["line"]
        pred_id = _pred_id(mid, market, line)

        if pred_id in already_revealed:
            stats["skipped_already_revealed"] += 1
            continue

        # Settlement candidacy: a fixture is a candidate if the list marks it
        # finished OR its kickoff is comfortably in the past (>~3h), since the list
        # status is refreshed lazily and often lags reality. The AUTHORITATIVE check
        # is the fetched final result — if the API has no final score/stats yet,
        # grading returns None and we count it ungradeable (retry next run).
        status = _fixture_status(meta, mid) or str(r.get("status", "")).lower()
        kickoff_ts = float(r.get("kickoff_ts", 0) or meta.get(mid, {}).get("ts", 0) or 0)
        likely_over = kickoff_ts > 0 and (kickoff_ts + 3 * 3600) < time.time()
        if status not in _FINISHED and not likely_over:
            stats["skipped_not_finished"] += 1
            continue
        stats["fixtures_finished"] += 1

        # Only predictions with a prior pre-kickoff commitment can be revealed.
        if pred_id not in committed:
            stats["reveal_declined_no_commitment"] += 1
            continue

        try:
            if mid not in final_cache:
                final_cache[mid] = _fetch_final(api, mid)
            final = final_cache[mid]
        except SystemExit:
            # client hit the request cap — stop cleanly, keep what we have
            stats["errors"].append("request cap reached during settlement fetch")
            if verbose:
                print("CAP reached during settlement — halting cleanly.")
            break
        except Exception as e:
            stats["errors"].append(f"fetch {mid}: {type(e).__name__}: {str(e)[:80]}")
            continue

        actual, value = _grade(market, line, final)
        if actual is None:
            stats["ungradeable_missing_result"] += 1
            continue

        p_over = float(r.get("model_p", 0.0))
        brier = (p_over - actual) ** 2
        cell = f"{market}@{line}"
        now_iso = datetime.now(timezone.utc).isoformat()

        # Append graded row (once) to the settled log.
        if pred_id not in logged_ids:
            settled_log["settled"].append({
                "prediction_id": pred_id,
                "match_id": mid, "market": market, "line": line,
                "model_p": p_over, "actual": actual, "actual_value": value,
                "brier_contribution": round(brier, 6),
                "reference_book": r.get("reference_book"),
                "books": r.get("books", {}),
                "settled_at": now_iso,
            })
            logged_ids.add(pred_id)
            stats["graded"] += 1
            stats["per_cell_settled_added"][cell] = \
                stats["per_cell_settled_added"].get(cell, 0) + 1

        # ── ATTESTATION: auto-reveal, binding outcome to the commitment ──
        try:
            res = ledger.reveal(
                prediction_id=pred_id, fixture_id=str(mid),
                model=f"{market}_{line}",
                outcome={"actual": actual, "actual_value": value,
                         "model_p": p_over, "line": line,
                         "brier_contribution": round(brier, 6)},
                settled_at=now_iso,
            )
            if res.committed:
                already_revealed.add(pred_id)
                stats["revealed"] += 1
            else:
                stats["errors"].append(f"reveal declined {pred_id}: {res.reason}")
        except Exception as e:
            stats["errors"].append(f"reveal failed {pred_id}: {type(e).__name__}: {str(e)[:80]}")

    settled_log["updated_at"] = datetime.now(timezone.utc).isoformat()
    settled_log["n_settled_total"] = len(settled_log["settled"])
    json.dump(settled_log, open(LOG, "w"), indent=2, default=str)

    if verbose:
        print(f"score: examined={stats['predictions_examined']} finished={stats['fixtures_finished']} "
              f"graded={stats['graded']} revealed={stats['revealed']} "
              f"already_revealed={stats['skipped_already_revealed']} "
              f"not_finished={stats['skipped_not_finished']} "
              f"no_commitment={stats['reveal_declined_no_commitment']} "
              f"ungradeable={stats['ungradeable_missing_result']}")
        if stats["errors"]:
            print("  settlement errors:", stats["errors"][:5])
        print("graded rows appended to", LOG)
    return stats


def topup(max_fixtures=40, run_fetch=False):
    """Covered-league-biased weekly top-up.

    Builds a prioritised fetch plan (upcoming fixtures in already-covered leagues
    first; no new leagues), reports the projected settleable sample and the date a
    meaningfully-powered sample would exist, and prints the capped fetch command.
    Pass run_fetch=True to actually invoke the biased, capped fetch.
    """
    import pilotC_stat_mixer as mix
    from src.research.forward.covered_league_topup import (
        build_topup_plan, project_settleable_sample,
    )
    ms = mix.load_corpus(); hist = mix.build_histories(ms)
    corpus_teams = set(hist.keys())
    fx = json.load(open(LIST)); meta = fx['meta']
    now = time.time()
    plan = build_topup_plan(meta, fx['match_ids'], corpus_teams, now)

    # Report actual quota remaining (dynamic — read from the client's budget snapshot).
    try:
        import thestatsapi_client as api
        remaining = api.budget_snapshot().get('last_monthly_remaining')
    except Exception:
        remaining = None

    # Requests this run are capped: min(cap, fixtures_to_fetch) * n_books.
    n_books = 3
    fixtures_this_run = min(max_fixtures, len(plan.ordered_match_ids))
    projected_requests = fixtures_this_run * n_books

    proj = project_settleable_sample(
        plan, markets_per_fixture=MARKETS_PER_FIXTURE,
        weekly_covered_upcoming=plan.n_upcoming_both_covered,
    )
    # Date a powered sample would exist (per market/line), given the weekly rate.
    weeks = proj["estimated_weeks_to_power_per_market_line"]
    powered_date = None
    if weeks is not None:
        powered_date = time.strftime(
            "%Y-%m-%d", time.gmtime(now + weeks * 7 * 86400))

    report = {
        "generated": time.strftime("%Y-%m-%dT%H:%M:%SUTC", time.gmtime(now)),
        "policy": "Bias top-up toward UPCOMING fixtures in leagues with existing "
                  "team history. Do NOT broaden the corpus to new leagues.",
        "corpus_teams": len(corpus_teams),
        "plan": {
            "n_total_fixtures": plan.n_total,
            "n_covered_competitions": plan.detail["n_covered_competitions"],
            "upcoming_both_covered": plan.n_upcoming_both_covered,
            "upcoming_one_covered": plan.n_upcoming_one_covered,
            "finished_both_covered_backlog": plan.n_settle_finished_covered,
            "excluded_new_league": plan.n_excluded_new_league,
            "excluded_past_or_uncovered": plan.n_excluded_past_uncovered,
            "ordered_fixtures_in_plan": len(plan.ordered_match_ids),
        },
        "quota": {
            "actual_remaining_reported_by_client": remaining,
            "max_fixtures_this_run": max_fixtures,
            "fixtures_attempted_this_run": fixtures_this_run,
            "books_per_fixture": n_books,
            "projected_requests_this_run_worst_case": projected_requests,
            "note": "Cache-first: only NEW (match,book) pairs cost budget; cached "
                    "pairs are free. Worst case assumes all pairs uncached.",
        },
        "projection": proj,
        "powered_sample_date_estimate_per_market_line": powered_date,
        "honest_framing": "Reaching a powered sample only ENABLES a conclusion; it "
                          "does not imply edge. No edge conclusion from unsettled fixtures.",
        "fetch_command": (
            f"PILOTC_COVERED_ONLY=1 PILOTC_MAX_FIXTURES={max_fixtures} "
            f"THESTATS_MAX_REQUESTS={projected_requests} "
            f"python3 scripts/pilotC_multibook_fetch.py"),
    }
    json.dump(report, open(TOPUP_REPORT, 'w'), indent=2, default=str)

    print("=== Pilot C covered-league top-up plan ===")
    print(json.dumps(report, indent=2, default=str))
    print(f"\nsaved {TOPUP_REPORT}")

    if run_fetch:
        os.environ['PILOTC_COVERED_ONLY'] = '1'
        os.environ['PILOTC_MAX_FIXTURES'] = str(max_fixtures)
        os.environ.setdefault('THESTATS_MAX_REQUESTS', str(projected_requests))
        import pilotC_multibook_fetch as fetch
        fetch.main()
    else:
        print("\nDry run (plan only). To fetch, run:")
        print("  " + report["fetch_command"])
    return report


if __name__=='__main__':
    cmd=sys.argv[1] if len(sys.argv)>1 else 'score'
    if cmd=='topup':
        run_fetch='--fetch' in sys.argv[2:]
        maxfx=40
        for a in sys.argv[2:]:
            if a.startswith('--max='):
                maxfx=int(a.split('=',1)[1])
        topup(max_fixtures=maxfx, run_fetch=run_fetch)
    else:
        score()
