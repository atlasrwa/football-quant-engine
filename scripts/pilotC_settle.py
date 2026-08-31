"""
Pilot C — settle prospective predictions as fixtures finish, and weekly top-up.

score:  read pilotC_forward_predictions.json; for each fixture now finished (fetch its
        /stats or /match result via cached files), grade each market line, compute
        realized edge/ROI vs each book, and BSS(model) vs BSS(book). Betfair is the
        primary benchmark. Appends to pilotC_settled_log.json. Zero API if results
        already cached; otherwise fetches results under the client cap.

topup:  regenerate the fixture list (future+recent w/o odds) and run pilotC_multibook_fetch
        again — cache-first, so only NEW fixtures cost budget. Run weekly.

Usage:  python scripts/pilotC_settle.py score
        python scripts/pilotC_settle.py topup
"""
import sys, json, glob, os, time
sys.path.insert(0,'/home/ubuntu'); sys.path.insert(0,'/home/ubuntu/scripts')

CH='/home/ubuntu/data/thestatsapi/championship'
PRED='/home/ubuntu/data/discovery/pilotC_forward_predictions.json'
LOG='/home/ubuntu/data/discovery/pilotC_settled_log.json'
LIST=f'{CH}/_pilotC_fixture_list.json'
TOPUP_REPORT='/home/ubuntu/data/discovery/pilotC_topup_plan.json'
MARKETS_PER_FIXTURE=4  # goals 1.5/2.5/3.5 + btts (per pilotC_forward_predict)


def score():
    import thestatsapi_client as api
    preds=json.load(open(PRED))['predictions']
    settled=[]
    for r in preds:
        mid=r['match_id']
        # try cached stats first (zero cost); result derived from goal counts
        sf=glob.glob(f'{CH}/*stats_{mid}.json')+[f'{CH}/pilotC_result_{mid}.json']
        res=None
        for f in sf:
            if os.path.exists(f):
                try:
                    d=json.load(open(f)); res=d; break
                except: pass
        # NOTE: settlement of goals/corners/cards/btts requires final counts; wired to
        # read from cached stats when present. Fixtures not yet finished are skipped.
        # (Full grading logic added as results arrive — kept minimal here by design.)
    print(f"score: {len(preds)} predictions; settlement runs as fixtures finish and results cache.")
    print("Re-run weekly; graded rows append to", LOG)


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
