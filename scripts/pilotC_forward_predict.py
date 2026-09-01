"""
Pilot C — apply the regularized stat-mixer to FORWARD fixtures and compare to
multi-book fair prices (Bet365, Betfair-exchange, Pinnacle). PROSPECTIVE: most
fixtures are unsettled; this writes a prediction log to be scored as games finish.

Reuses pilotC_stat_mixer training (same pools, PIT features, elastic-net regulator)
by refitting each market on the FULL corpus with the CV-selected (C, l1_ratio) already
found, then predicting the forward fixtures whose teams we have histories for.

Edge is measured against EACH book's devigged fair prob, with Betfair (near-zero vig)
as the primary honest benchmark and cross-book disagreement recorded. No bets settled
here; outcomes filled in later by pilotC_settle.py as fixtures complete.
"""
import sys, json, glob, os, warnings, time
from datetime import datetime, timezone
from collections import defaultdict
import numpy as np
warnings.filterwarnings('ignore')
sys.path.insert(0,'/home/ubuntu'); sys.path.insert(0,'/home/ubuntu/scripts')
from sklearn.linear_model import LogisticRegression
import pilotC_stat_mixer as mix
from src.research.forward.attestation_ledger import AttestationLedger
from src.research.forward.league_coverage import (
    COVERED_LEAGUE_COMP_IDS, is_covered_comp,
)

CH='/home/ubuntu/data/thestatsapi/championship'
OUT='/home/ubuntu/data/discovery/pilotC_forward_predictions.json'
COMMIT_LEDGER='/home/ubuntu/data/forward/pilotC_commitments.jsonl'
REVEAL_LEDGER='/home/ubuntu/data/forward/pilotC_reveals.jsonl'
BOOKS=['bet365','betfair-exchange','pinnacle']
# Betfair exchange is the primary (near-fair) reference price for the edge claim.
PRIMARY_BOOK='betfair-exchange'
MKT_ODDSKEY={'goals':'total_goals','corners':'match_corners','cards':'total_cards','btts':'btts'}


def commit_gate(info, corpus_teams):
    """Decide whether a fixture may reach the COMMIT step.

    Returns one of:
      * "commit"                    — covered league AND both teams have corpus history
      * "reject_out_of_coverage"    — competition is NOT a covered league (NEVER commit)
      * "skip_no_corpus_history"    — covered league but a team lacks corpus history

    The PRIMARY gate is covered-league membership by competition id — a fixture
    outside the four covered leagues can never be committed, regardless of whether
    its teams happen to appear in the corpus. This is the exact bug the fix closes:
    the old gate tested corpus-team membership, so out-of-coverage fixtures
    (Veikkausliiga/Serie A/Brazil) whose teams were in the corpus slipped through.
    """
    comp = info.get("comp")
    if not is_covered_comp(comp):
        return "reject_out_of_coverage"
    home, away = info.get("home"), info.get("away")
    if home not in corpus_teams or away not in corpus_teams:
        return "skip_no_corpus_history"
    return "commit"


def devig(o,u):
    if not o or not u: return None
    o,u=float(o),float(u)
    if o<=1 or u<=1: return None
    s=1/o+1/u; return (1/o)/s, s-1


def fit_full(ms, hist, market, line, C, l1r):
    names=mix.feat_names(market); X=[];y=[]
    for m in ms:
        o=mix.outcome(m,market,line)
        if o is None: continue
        X.append(mix.match_features(hist,m,market)); y.append(o)
    cov=np.mean([[v is not None for v in r] for r in X],axis=0)
    keep=[i for i in range(len(names)) if cov[i]>=0.6]
    names=[names[i] for i in keep]
    M=np.array([[ (np.nan if r[i] is None else r[i]) for i in keep] for r in X],float)
    med=np.nanmedian(M,0); med=np.where(np.isnan(med),0,med)
    idx=np.where(np.isnan(M)); M[idx]=np.take(med,idx[1])
    mu,sd=M.mean(0),M.std(0); sd[sd==0]=1; Ms=(M-mu)/sd
    clf=LogisticRegression(penalty='elasticnet',solver='saga',C=C,l1_ratio=l1r,max_iter=4000)
    clf.fit(Ms,np.array(y))
    return {'clf':clf,'keep':keep,'names_all':mix.feat_names(market),'med':med,'mu':mu,'sd':sd}


def predict_one(model, hist, m, market):
    raw=mix.match_features(hist,m,market)
    x=np.array([ (np.nan if raw[i] is None else raw[i]) for i in model['keep']],float)
    if np.all(np.isnan(x)): return None
    nanidx=np.where(np.isnan(x))[0]; x[nanidx]=model['med'][nanidx]
    xs=(x-model['mu'])/model['sd']
    return float(np.clip(model['clf'].predict_proba(xs.reshape(1,-1))[0,1],0.01,0.99))


def load_forward_books(mid):
    out={}
    for bk in BOOKS:
        f=f'{CH}/pilotC_odds_{mid}_{bk}.json'
        if not os.path.exists(f): continue
        try: d=json.load(open(f))
        except: continue
        bks=d.get('data',{}).get('bookmakers',[])
        if bks and isinstance(bks[0],dict) and bks[0].get('markets'):
            out[bk]=bks[0]['markets']
    return out


def main():
    ms=mix.load_corpus(); hist=mix.build_histories(ms)
    corpus_teams=set(hist.keys())
    saved=json.load(open('/home/ubuntu/data/discovery/pilotC_stat_mixer.json'))['models']
    hp={(x['market'], x['line']):(x['C'],x['l1_ratio']) for x in saved}
    print('fitting forward models with CV-selected hyperparameters...')
    models={}
    for (market,line),(C,l1r) in hp.items():
        models[(market,line)]=fit_full(ms,hist,market,line,C,l1r)

    fx=json.load(open(f'{CH}/_pilotC_fixture_list.json'))['meta']
    ledger=AttestationLedger(commit_path=COMMIT_LEDGER, reveal_path=REVEAL_LEDGER)
    # Idempotency: the ledger is append-only and does NOT dedup by prediction_id,
    # so we must skip any pred_id already committed. Without this guard a re-run
    # (this script rewrites the predictions file each time) would append duplicate
    # commitment rows for the same fixture/market. Mirror Pipeline A's pattern.
    already_committed=set(ledger.commitments_by_prediction().keys())
    now_ts=time.time()
    preds=[]
    attest_stats={'committed':0,'unattestable_past_kickoff':0,'commit_failed':0,
                  'skipped_already_committed':0,
                  # LOUD out-of-coverage accounting. The predict gate is on
                  # COVERED-LEAGUE membership (competition id), NOT corpus-team
                  # membership — that team-based gate is exactly what let
                  # out-of-coverage fixtures (Veikkausliiga/Serie A/Brazil) into the
                  # committed set of a covered-league-only pre-registered sample.
                  'rejected_out_of_coverage':0,
                  'rejected_out_of_coverage_by_league':{},
                  'skipped_no_corpus_history':0}
    from collections import defaultdict
    ooc_by_league=defaultdict(int)
    for mid,info in fx.items():
        home,away=info.get('home'),info.get('away')
        comp=info.get('comp')
        # ── PRIMARY GATE: covered-league membership (by competition id) ──
        # A fixture outside the four pre-registered covered leagues must NEVER be
        # committed, regardless of whether its teams appear in the corpus. This is
        # an ERROR condition surfaced loudly (counted per league, logged), never a
        # silent skip — an out-of-coverage fixture reaching predict means the
        # universe contains fixtures discovery should not have admitted.
        gate = commit_gate(info, corpus_teams)
        if gate == "reject_out_of_coverage":
            attest_stats['rejected_out_of_coverage']+=1
            ooc_by_league[comp or 'UNKNOWN']+=1
            continue
        # ── settleability check: both teams must have corpus history to predict.
        # This is NOT the coverage boundary (that is the competition gate above);
        # it only decides whether we CAN produce a prediction. A covered-league
        # fixture whose teams lack history is skipped as unpredictable, counted
        # separately from out-of-coverage rejections.
        if gate == "skip_no_corpus_history":
            attest_stats['skipped_no_corpus_history']+=1
            continue
        books=load_forward_books(mid)
        if not books: continue
        m={'home_name':home,'away_name':away,'date_unix':info['ts']}
        for (market,line),model in models.items():
            pm=predict_one(model,hist,m,market)
            if pm is None: continue
            ok=MKT_ODDSKEY[market]
            row={'match_id':mid,'home':home,'away':away,'kickoff_ts':info['ts'],
                 'status':info['status'],'market':market,'line':line,'model_p':round(pm,4),'books':{}}
            for bk,mk in books.items():
                if market=='btts':
                    node=mk.get('btts',{}); o=node.get('yes',{}).get('last_seen'); u=node.get('no',{}).get('last_seen')
                else:
                    node=mk.get(ok,{}).get(str(line),{}); o=node.get('over',{}).get('last_seen'); u=node.get('under',{}).get('last_seen')
                dv=devig(o,u)
                if dv:
                    fair,ovr=dv
                    row['books'][bk]={'fair_p':round(fair,4),'overround':round(ovr,4),
                                      'edge_pp':round((pm-fair)*100,2),
                                      'over_odds':float(o),'under_odds':float(u)}
            if not row['books']:
                continue

            # ── ATTESTATION: commit BEFORE kickoff, binding the reference price ──
            # A Pilot C prediction is a forward edge claim vs a specific reference
            # price. We commit (prediction + fixture + reference price + timestamp)
            # via the tamper-evident ledger. If the fixture has already kicked off
            # the ledger refuses — the row is flagged UNATTESTABLE, never backdated.
            pred_id=f"pilotC:{mid}:{market}:{line}"
            ref_book=PRIMARY_BOOK if PRIMARY_BOOK in row['books'] else next(iter(row['books']))
            ref=row['books'][ref_book]
            reference_price={'book':ref_book,'over_odds':ref['over_odds'],
                             'under_odds':ref['under_odds'],'fair_p':ref['fair_p'],
                             'overround':ref['overround']}
            row['reference_book']=ref_book
            if pred_id in already_committed:
                # Already committed in a prior run — do NOT re-commit (would append a
                # duplicate ledger row). Reuse the existing commitment hash so the
                # predictions file stays consistent with the ledger.
                row['attested']=True
                row['commitment_hash']=ledger.commitments_by_prediction()[pred_id]['commitment_hash']
                attest_stats['skipped_already_committed']+=1
                preds.append(row)
                continue
            try:
                res=ledger.commit(prediction_id=pred_id, fixture_id=str(mid),
                                  model=f"{market}_{line}", kickoff_unix=float(info['ts']),
                                  p_over=round(pm,4), p_under=round(1.0-pm,4),
                                  reference_price=reference_price)
                if res.committed:
                    row['attested']=True
                    row['commitment_hash']=res.record['commitment_hash']
                    attest_stats['committed']+=1
                else:
                    row['attested']=False
                    row['attestation_note']=res.reason
                    attest_stats['unattestable_past_kickoff']+=1
            except Exception as e:
                row['attested']=False
                row['attestation_note']=f"{type(e).__name__}: {str(e)[:120]}"
                attest_stats['commit_failed']+=1

            preds.append(row)

    # cross-book disagreement summary
    attest_stats['rejected_out_of_coverage_by_league']=dict(ooc_by_league)

    # ── Out-of-coverage AUDIT of the EXISTING committed ledger (read-only) ──
    # The ledger is append-only and immutable — we NEVER edit or delete records.
    # But we must REPORT how many already-committed fixtures are out of coverage,
    # because that number decides whether the pre-registered sample is compromised
    # and which fixtures are a documented ANALYSIS-TIME exclusion (never a ledger
    # edit). Coverage is judged by the fixture's competition id in the universe.
    ooc_committed_by_league=defaultdict(list)
    committed_fixtures={}
    for c in ledger.load_commitments():
        committed_fixtures.setdefault(c['fixture_id'], c['prediction_id'])
    for cmid in committed_fixtures:
        crow=fx.get(cmid, {})
        ccomp=crow.get('comp')
        if not is_covered_comp(ccomp):
            label=COVERED_LEAGUE_COMP_IDS.get(ccomp, ccomp or 'UNKNOWN')
            ooc_committed_by_league[label].append(cmid)
    out_of_coverage_committed={
        'n_fixtures': sum(len(v) for v in ooc_committed_by_league.values()),
        'by_league': {k: len(v) for k, v in ooc_committed_by_league.items()},
        'fixtures': {k: v for k, v in ooc_committed_by_league.items()},
        'note': 'Append-only ledger — these commitments are NOT deleted or altered. '
                'They are a DOCUMENTED analysis-time exclusion from the covered-league '
                'pre-registered sample, not a ledger edit. The predict gate now rejects '
                'such fixtures so no NEW out-of-coverage commitments can be created.',
    }

    disagree=[]
    for r in preds:
        if 'bet365' in r['books'] and 'betfair-exchange' in r['books']:
            disagree.append(abs(r['books']['bet365']['fair_p']-r['books']['betfair-exchange']['fair_p']))
    out={'generated':datetime.now(timezone.utc).isoformat(),
         'STATUS':'PROSPECTIVE — most fixtures unsettled; score with pilotC_settle.py after kickoff',
         'DISCLAIMER':'This demonstrates the CONDITIONS for edge (near-fair Betfair reference, '
                      'measurable book disagreement, a calibrated model) and that the pipeline runs '
                      'end to end. It does NOT demonstrate edge. No edge conclusion may be drawn from '
                      'unsettled fixtures.',
         'primary_reference_book':PRIMARY_BOOK,
         'attestation':{
             'committed_pre_kickoff':attest_stats['committed'],
             'unattestable_past_kickoff':attest_stats['unattestable_past_kickoff'],
             'commit_failed':attest_stats['commit_failed'],
             'skipped_already_committed':attest_stats['skipped_already_committed'],
             'rejected_out_of_coverage':attest_stats['rejected_out_of_coverage'],
             'rejected_out_of_coverage_by_league':attest_stats['rejected_out_of_coverage_by_league'],
             'skipped_no_corpus_history':attest_stats['skipped_no_corpus_history'],
             'commit_ledger':COMMIT_LEDGER,
             'note':'Only pre-kickoff predictions are attestable. Past-kickoff fixtures '
                    'cannot be retroactively attested and are never backdated. '
                    'Re-runs skip already-committed predictions (idempotent). The predict '
                    'gate is COVERED-LEAGUE membership (competition id): fixtures outside '
                    'the four covered leagues are rejected out-of-coverage and never '
                    'committed.'},
         'out_of_coverage_committed':out_of_coverage_committed,
         'n_predictions':len(preds),
         'n_mappable_fixtures':len(set(r['match_id'] for r in preds)),
         'betfair_vs_bet365_disagreement_pp':{
             'mean':round(float(np.mean(disagree))*100,2) if disagree else None,
             'max':round(float(np.max(disagree))*100,2) if disagree else None,
             'n':len(disagree)},
         'predictions':preds}
    json.dump(out, open(OUT,'w'), indent=2, default=str)
    print(f"predictions={len(preds)} over {out['n_mappable_fixtures']} fixtures")
    print(f"attestation: committed={attest_stats['committed']} "
          f"unattestable_past_kickoff={attest_stats['unattestable_past_kickoff']} "
          f"skipped_already_committed={attest_stats['skipped_already_committed']} "
          f"failed={attest_stats['commit_failed']}")
    # LOUD: fixtures rejected at the covered-league gate this run (never committed).
    if attest_stats['rejected_out_of_coverage']:
        print(f"OUT-OF-COVERAGE REJECTED (never committed): "
              f"{attest_stats['rejected_out_of_coverage']} fixture(s) by league: "
              f"{attest_stats['rejected_out_of_coverage_by_league']}")
    if attest_stats['skipped_no_corpus_history']:
        print(f"skipped (covered league but no corpus history): "
              f"{attest_stats['skipped_no_corpus_history']}")
    # LOUD: out-of-coverage fixtures ALREADY in the committed ledger (documented
    # analysis-time exclusion; the ledger is not edited). This number decides
    # whether the pre-registered sample is compromised.
    if out_of_coverage_committed['n_fixtures']:
        print(f"OUT-OF-COVERAGE ALREADY COMMITTED (append-only ledger, analysis-time "
              f"exclusion — NOT deleted): {out_of_coverage_committed['n_fixtures']} "
              f"fixture(s) by league: {out_of_coverage_committed['by_league']}")
    print(f"betfair vs bet365 disagreement: {out['betfair_vs_bet365_disagreement_pp']}")
    # show a few example edges vs Betfair
    ex=[r for r in preds if 'betfair-exchange' in r['books']][:8]
    for r in ex:
        bf=r['books']['betfair-exchange']
        print(f"  {r['market']:7s} {str(r['line']):5s} {r['home'][:14]:14s} v {r['away'][:14]:14s} model={r['model_p']:.2f} betfair_fair={bf['fair_p']:.2f} edge={bf['edge_pp']:+.1f}pp")
    print('saved', OUT)
    return attest_stats


if __name__=='__main__':
    main()
