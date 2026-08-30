"""
Stage 1 — which raw-stat combinations predict corners / goals / bookings best.

Fresh, clean build. Uses the verified team-consistent feature engine
(scripts/clean_features.py). Reuses ONLY fit_logistic_l2 from combination_discovery
as a scorer (not the slot-based feature code).

RESTRICTION RULE (documented before running):
  A candidate is admitted to the search ONLY if it has a statable football
  mechanism. We enumerate candidates by mechanism family (same-stat persistence,
  cross-stat within team, cross-team interaction, referee-conditioned, style
  composition), sizes 1-3, windows {w5,w10} (w3/std reserved to features, not
  multiplied into the family). Unrestricted all-combinations search is NOT run
  (it is a guaranteed null under correction). The fresh FDR family = exactly the
  (candidate x target x league) cells actually tested, counted live.

VALIDITY RULE:
  Per-league, walk-forward. A candidate is a FINDING only if it is significant
  WITHIN a league after fresh FDR. Pooled-only significance is reported as a
  pooling artifact, never as a finding.

Targets: match-total AND per-side for corners/goals/cards; SOT per-side; BTTS;
clean sheet per-side.
"""
from __future__ import annotations
import sys, json, time
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np
from scipy import stats as sp_stats
from scipy.special import expit

sys.path.insert(0, '/home/ubuntu'); sys.path.insert(0, '/home/ubuntu/scripts')
from src.discovery.corpus import load_discovery_set
from src.discovery.combination_discovery import fit_logistic_l2
from src.engine.analysis.fdr import FDRController
from clean_features import build_features, BASE_STATS_BROAD

OUT = '/home/ubuntu/data/discovery/clean_stage1_broad.json'
WIN = ('w5', 'w10')
MIN_TRAIN, MIN_TEST = 150, 80


# ── Targets: (name -> callable(match)->outcome in {0,1} or None) ──
def _tot(m, ha, hb, line):
    a, b = m.get(ha), m.get(hb)
    if a is None or a == -1 or b is None or b == -1:
        return None
    return 1.0 if (a + b) > line else 0.0

def _side(m, fld, line):
    v = m.get(fld)
    if v is None or v == -1:
        return None
    return 1.0 if v > line else 0.0

def _cards_tot(m, line):
    ya, yb = m.get('team_a_yellow_cards'), m.get('team_b_yellow_cards')
    if ya is None or ya == -1 or yb is None or yb == -1:
        return None
    tot = (ya or 0)+(yb or 0)+(m.get('team_a_red_cards') or 0 if m.get('team_a_red_cards',-1)>=0 else 0)+(m.get('team_b_red_cards') or 0 if m.get('team_b_red_cards',-1)>=0 else 0)
    return 1.0 if tot > line else 0.0

def _cards_side(m, side, line):
    y = m.get(f'team_{side}_yellow_cards'); r = m.get(f'team_{side}_red_cards')
    if y is None or y == -1:
        return None
    return 1.0 if ((y or 0)+(r or 0 if r not in (None,-1) else 0)) > line else 0.0

def _btts(m):
    hg, ag = m.get('homeGoalCount'), m.get('awayGoalCount')
    if hg is None or hg==-1 or ag is None or ag==-1: return None
    return 1.0 if (hg>0 and ag>0) else 0.0

def _cs(m, side):  # clean sheet for side (a=home concedes 0 -> away scored 0)
    hg, ag = m.get('homeGoalCount'), m.get('awayGoalCount')
    if hg is None or hg==-1 or ag is None or ag==-1: return None
    return 1.0 if ((ag==0) if side=='a' else (hg==0)) else 0.0

TARGETS = {
    'corners_tot_9.5':  lambda m: _tot(m,'team_a_corners','team_b_corners',9.5),
    'corners_tot_10.5': lambda m: _tot(m,'team_a_corners','team_b_corners',10.5),
    'corners_a_4.5':    lambda m: _side(m,'team_a_corners',4.5),
    'corners_b_4.5':    lambda m: _side(m,'team_b_corners',4.5),
    'goals_tot_1.5':    lambda m: _tot(m,'homeGoalCount','awayGoalCount',1.5),
    'goals_tot_2.5':    lambda m: _tot(m,'homeGoalCount','awayGoalCount',2.5),
    'goals_tot_3.5':    lambda m: _tot(m,'homeGoalCount','awayGoalCount',3.5),
    'goals_a_1.5':      lambda m: _side(m,'homeGoalCount',1.5),
    'goals_b_1.5':      lambda m: _side(m,'awayGoalCount',1.5),
    'cards_tot_3.5':    lambda m: _cards_tot(m,3.5),
    'cards_tot_4.5':    lambda m: _cards_tot(m,4.5),
    'cards_a_1.5':      lambda m: _cards_side(m,'a',1.5),
    'cards_b_1.5':      lambda m: _cards_side(m,'b',1.5),
    'sot_a_3.5':        lambda m: _side(m,'team_a_shotsOnTarget',3.5),
    'sot_b_3.5':        lambda m: _side(m,'team_b_shotsOnTarget',3.5),
    'btts':             _btts,
    'cs_a':             lambda m: _cs(m,'a'),
    'cs_b':             lambda m: _cs(m,'b'),
}


def F(who, stat, fa, w):
    return f'{who}_{stat}_{fa}_{w}'


def build_candidates():
    """Mechanism-guided candidate list. Each = dict(target, features, mechanism)."""
    C = []
    def add(t, feats, mech, kind):
        C.append({'target': t, 'features': tuple(feats), 'mechanism': mech, 'size': len(feats), 'kind': kind})

    for w in WIN:
        # SAME-STAT PERSISTENCE (both teams' own 'for' rate of target stat)
        add('corners_tot_9.5', [F('h','corners','for',w), F('a','corners','for',w)], 'both teams corner-for rate -> total corners', 'persistence')
        add('corners_tot_10.5',[F('h','corners','for',w), F('a','corners','for',w)], 'both teams corner-for rate -> total corners', 'persistence')
        add('corners_a_4.5', [F('h','corners','for',w), F('a','corners','against',w)], 'home corner-for x away corner-conceded -> home corners', 'persistence')
        add('corners_b_4.5', [F('a','corners','for',w), F('h','corners','against',w)], 'away corner-for x home corner-conceded -> away corners', 'persistence')
        add('cards_tot_3.5', [F('h','yellow_cards','for',w), F('a','yellow_cards','for',w)], 'both teams card rate -> total cards', 'persistence')
        add('cards_tot_4.5', [F('h','yellow_cards','for',w), F('a','yellow_cards','for',w)], 'both teams card rate -> total cards', 'persistence')
        add('cards_a_1.5', [F('h','yellow_cards','for',w), F('a','fouls','for',w)], 'home card rate x away fouling -> home cards', 'cross')
        add('cards_b_1.5', [F('a','yellow_cards','for',w), F('h','fouls','for',w)], 'away card rate x home fouling -> away cards', 'cross')
        add('goals_tot_2.5',[F('h','xg','for',w), F('a','xg','for',w)], 'both teams xG -> total goals', 'persistence')
        add('goals_tot_1.5',[F('h','xg','for',w), F('a','xg','for',w)], 'both teams xG -> total goals', 'persistence')
        add('goals_tot_3.5',[F('h','xg','for',w), F('a','xg','for',w)], 'both teams xG -> total goals', 'persistence')
        add('goals_a_1.5', [F('h','xg','for',w), F('a','xg','against',w)], 'home xG-for x away xG-conceded -> home goals', 'persistence')
        add('goals_b_1.5', [F('a','xg','for',w), F('h','xg','against',w)], 'away xG-for x home xG-conceded -> away goals', 'persistence')
        add('sot_a_3.5', [F('h','shotsOnTarget','for',w), F('a','shotsOnTarget','against',w)], 'home SOT-for x away SOT-conceded -> home SOT', 'persistence')
        add('sot_b_3.5', [F('a','shotsOnTarget','for',w), F('h','shotsOnTarget','against',w)], 'away SOT-for x home SOT-conceded -> away SOT', 'persistence')
        add('btts', [F('h','xg','for',w), F('a','xg','for',w)], 'both teams attacking quality -> BTTS', 'persistence')
        add('cs_a', [F('a','xg','for',w), F('h','xg','against',w)], 'away attack x home defense -> home clean sheet', 'persistence')
        add('cs_b', [F('h','xg','for',w), F('a','xg','against',w)], 'home attack x away defense -> away clean sheet', 'persistence')

        # CROSS-STAT WITHIN TEAM -> corners / goals (do NOT require target persistence)
        add('corners_tot_9.5', [F('h','dangerous_attacks','for',w), F('a','dangerous_attacks','for',w)], 'dangerous attacks -> corners', 'cross')
        add('corners_tot_10.5',[F('h','dangerous_attacks','for',w), F('a','dangerous_attacks','for',w)], 'dangerous attacks -> corners', 'cross')
        add('corners_tot_9.5', [F('h','attacks','for',w), F('a','attacks','for',w)], 'territorial attacks -> corners', 'cross')
        add('goals_tot_2.5', [F('h','shots','for',w), F('a','shots','for',w)], 'shot volume -> goals', 'cross')
        add('goals_tot_2.5', [F('h','shotsOnTarget','for',w), F('a','shotsOnTarget','for',w)], 'SOT -> goals', 'cross')

        # CROSS-TEAM INTERACTION (different stats, both sides)
        add('cards_tot_3.5', [F('h','dangerous_attacks','for',w), F('a','fouls','for',w)], 'A pressure x B fouling -> cards', 'cross')
        add('cards_tot_4.5', [F('h','fouls','for',w), F('a','fouls','for',w)], 'mutual fouling -> cards', 'cross')
        add('goals_tot_2.5', [F('h','shots','for',w), F('a','shotsOnTarget','against',w)], 'A shots x B SOT-conceded -> goals', 'cross')
        add('corners_tot_9.5', [F('h','dangerous_attacks','for',w), F('a','corners','against',w)], 'A pressure x B corners-conceded -> corners', 'cross')

        # REFEREE-CONDITIONED
        add('cards_tot_3.5', ['ref_card_rate', F('h','fouls','for',w), F('a','fouls','for',w)], 'ref card tendency x both fouling -> cards', 'cross')
        add('cards_tot_4.5', ['ref_card_rate', F('h','fouls','for',w), F('a','fouls','for',w)], 'ref card tendency x both fouling -> cards', 'cross')

        # STYLE COMPOSITION
        add('corners_tot_9.5', [F('h','dangerous_attacks','for',w), F('h','attacks','for',w)], 'attack directness -> corners', 'cross')
        add('goals_tot_2.5', [F('h','shotsOnTarget','for',w), F('h','shots','for',w)], 'shot quality -> goals', 'cross')

    # referee alone (size-1)
    add('cards_tot_3.5', ['ref_card_rate'], 'referee card tendency alone -> cards', 'cross')
    add('cards_tot_4.5', ['ref_foul_rate'], 'referee foul tendency alone -> cards', 'cross')
    return C


def score(feats, target_fn, matches):
    n = len(matches)
    X = np.zeros((n, len(feats))); valid = np.ones(n, bool)
    for j, f in enumerate(feats):
        for i in range(n):
            v = matches[i]['_f'].get(f)
            if v is None:
                valid[i] = False
            else:
                X[i, j] = v
    split = int(n*0.6)
    trm = valid.copy(); trm[split:] = False
    tem = valid.copy(); tem[:split] = False
    if trm.sum() < MIN_TRAIN or tem.sum() < MIN_TEST:
        return None
    Xtr, Xte = X[trm], X[tem]
    mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1
    Xtr = (Xtr-mu)/sd; Xte = (Xte-mu)/sd
    ytr = np.array([target_fn(matches[i]) for i in np.where(trm)[0]], dtype=object)
    yte = np.array([target_fn(matches[i]) for i in np.where(tem)[0]], dtype=object)
    tv = np.array([v is not None for v in ytr]); ev = np.array([v is not None for v in yte])
    if tv.sum() < MIN_TRAIN or ev.sum() < MIN_TEST:
        return None
    Xtr, ytr = Xtr[tv], ytr[tv].astype(float); Xte, yte = Xte[ev], yte[ev].astype(float)
    if len(set(ytr.tolist())) < 2 or len(set(yte.tolist())) < 2:
        return None
    beta = fit_logistic_l2(Xtr, ytr, lam=1.0)
    probs = np.clip(expit(np.column_stack([Xte, np.ones(len(Xte))]) @ beta), 0.01, 0.99)
    brier = float(np.mean((probs-yte)**2)); base = float(yte.mean())
    nb = float(np.mean((base-yte)**2)); bss = (1-brier/nb)*100 if nb > 0 else 0.0
    ece = 0.0
    for b in range(10):
        lo, hi = b/10, (b+1)/10
        mk = (probs>=lo)&(probs<hi if b<9 else probs<=hi)
        if mk.sum()>0: ece += (mk.sum()/len(probs))*abs(probs[mk].mean()-yte[mk].mean())
    ll_m = float(np.sum(yte*np.log(probs)+(1-yte)*np.log(1-probs)))
    p0 = np.clip(base,0.01,0.99); ll0 = float(np.sum(yte*np.log(p0)+(1-yte)*np.log(1-p0)))
    p = float(sp_stats.chi2.sf(max(2*(ll_m-ll0),0), len(feats)))
    return {'bss_pct': round(bss,4), 'brier': round(brier,5), 'ece': round(ece,4),
            'p_value': p, 'n_test': int(ev.sum()), 'base_rate': round(base,4)}


def gate(target_name, target_fn, matches):
    """Known-good instrument per target stat; corners persistence expected to fail."""
    fam = target_name.split('_')[0]
    inst = {'corners': (F('h','corners','for','w5'), F('a','corners','for','w5')),
            'goals':   (F('h','xg','for','w5'), F('a','xg','for','w5')),
            'cards':   (F('h','yellow_cards','for','w5'), F('a','yellow_cards','for','w5')),
            'sot':     (F('h','shotsOnTarget','for','w5'), F('a','shotsOnTarget','for','w5')),
            'btts':    (F('h','xg','for','w5'), F('a','xg','for','w5')),
            'cs':      (F('h','xg','for','w5'), F('a','xg','for','w5'))}.get(fam)
    r = score(inst, target_fn, matches)
    if r is None:
        return {'passed': False, 'reason': 'insufficient_n', 'detail': None}
    return {'passed': bool(r['bss_pct'] > 0 and r['p_value'] < 0.05), 'detail': r}


def main():
    t0 = time.time()
    print("Loading discovery corpus + building verified features (broad tier)...")
    allms = load_discovery_set(); allms.sort(key=lambda m: m.get('date_unix', 0))
    build_features(allms, BASE_STATS_BROAD)
    by_league = defaultdict(list)
    for m in allms:
        by_league[m['_league']].append(m)

    candidates = build_candidates()
    print(f"Mechanism-guided candidates (per league): {len(candidates)}")

    results = {}
    fresh_family_cells = 0          # (candidate x league) cells actually tested
    all_p = []; all_key = []
    pooled_rows = []

    # POOLED gate (instrument validity)
    pooled_gates = {t: gate(t, TARGETS[t], allms) for t in TARGETS}

    for lg in sorted(by_league.keys()):
        ms = by_league[lg]
        if len(ms) < 260:
            results[lg] = {'status': 'insufficient_matches', 'n': len(ms)}
            continue
        gates = {t: gate(t, TARGETS[t], ms) for t in TARGETS}
        rows = []
        for c in candidates:
            g = gates.get(c['target'], {})
            base = {k: c[k] for k in ('target','features','mechanism','size','kind')}
            # persistence candidates require the target's same-stat persistence gate;
            # cross/interaction/referee candidates do NOT (per spec: cross-stat corners
            # predictors are tested even though corners persistence fails).
            if c['kind'] == 'persistence' and not g.get('passed'):
                rows.append({**base, 'status': 'skipped_gate_failed'}); continue
            r = score(c['features'], TARGETS[c['target']], ms)
            if r is None:
                rows.append({**base, 'status': 'insufficient_n'}); continue
            fresh_family_cells += 1
            all_p.append(r['p_value']); all_key.append((lg, len(rows)))
            rows.append({**base, 'status': 'tested', **r})
        npass = sum(1 for gg in gates.values() if gg.get('passed'))
        nt = sum(1 for r in rows if r.get('status')=='tested')
        results[lg] = {'status':'searched','n':len(ms),'gates':gates,'candidates':rows}
        print(f"  {lg:26s} n={len(ms):4d} gates={npass}/{len(TARGETS)} tested={nt}")

    # ── FRESH FDR over this run's within-league tested cells ──
    fdr = FDRController(alpha=0.05)
    fdr_res = fdr.correct(all_p) if all_p else []
    survivors = []
    for i, fr in enumerate(fdr_res):
        if fr.rejected:
            lg, ri = all_key[i]
            row = results[lg]['candidates'][ri]
            survivors.append({'league': lg, 'target': row['target'], 'mechanism': row['mechanism'],
                              'features': row['features'], 'bss_pct': row['bss_pct'],
                              'p_value': row['p_value'], 'n_test': row['n_test']})

    out = {
        'analysis_date': datetime.now(timezone.utc).isoformat(),
        'tier': 'broad (FootyStats, 25 leagues)',
        'scope': 'raw observable stats only; team-consistent verified features; no prior-metric reference; FRESH FDR family (does NOT inherit 23,869)',
        'restriction_rule': 'mechanism-guided candidates only; windows w5/w10; per-league walk-forward; within-league significance required',
        'windows': list(WIN), 'candidates_per_league': len(candidates),
        'fresh_fdr_family_size': fresh_family_cells,
        'fdr_within_league_survivors': survivors,
        'n_within_league_survivors': len(survivors),
        'pooled_gates': pooled_gates,
        'leagues': results,
        'duration_sec': round(time.time()-t0, 1),
    }
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2, default=str)

    print(f"\nFresh FDR family (within-league cells tested): {fresh_family_cells}")
    print(f"Within-league FDR survivors: {len(survivors)}")
    for s in sorted(survivors, key=lambda x:-x['bss_pct'])[:20]:
        print(f"  {s['league'][:20]:20s} {s['target']:16s} BSS={s['bss_pct']:+6.2f}% p={s['p_value']:.2e} n={s['n_test']} | {s['mechanism'][:40]}")
    # top uncorrected by BSS for context
    tested = [{'league':lg, **c} for lg,r in results.items() if isinstance(r,dict) and r.get('status')=='searched'
              for c in r['candidates'] if c.get('status')=='tested']
    tested.sort(key=lambda x:-x['bss_pct'])
    print("\nTop 15 by within-league BSS (uncorrected):")
    for t in tested[:15]:
        print(f"  {t['league'][:20]:20s} {t['target']:16s} BSS={t['bss_pct']:+6.2f}% p={t['p_value']:.4f} n={t['n_test']} | {t['mechanism'][:36]}")
    print(f"\nSaved: {OUT}")
    return out


if __name__ == '__main__':
    main()
