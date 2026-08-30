"""
Raw Stats Discovery Engine (clean run) — Steps 2/3/4/6 for FootyStats-core.

Raw observable stats ONLY. No reference to or comparison against any previously
discovered metrics.

Feature construction is TEAM-CONSISTENT and point-in-time: for each team we track
its OWN rolling rate of each stat ("for") and the rate it concedes ("against"),
regardless of home/away slot, using only that team's prior matches. This fixes the
slot-based mis-specification (team_a_* conflates team identity with venue) that the
sanity gate correctly flagged.

Reuses verbatim: src.discovery.corpus.load_discovery_set, fit_logistic_l2 and
compute_outcome (src.discovery.combination_discovery), FDRController.

Walk-forward / PIT throughout. Sanity gate per league/target BEFORE searching.
Cumulative FDR against family 23,823.
"""
from __future__ import annotations
import json, sys, time
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np
from scipy import stats as sp_stats
from scipy.special import expit

sys.path.insert(0, '/home/ubuntu')
from src.discovery.corpus import load_discovery_set
from src.discovery.combination_discovery import fit_logistic_l2, compute_outcome
from src.engine.analysis.fdr import FDRController

OUT = '/home/ubuntu/data/discovery/raw_stats_discovery.json'
CUMULATIVE_FAMILY_BEFORE = 23823
WINDOWS = (5, 10)
MIN_TRAIN, MIN_TEST = 150, 80

# Raw observable per-side fields. We read team_a_* (home) / team_b_* (away) from
# each match and attribute "for" to the acting team and "against" to the opponent.
STAT_FOR = {  # base -> (home_field, away_field)
    'goals': ('homeGoalCount', 'awayGoalCount'),
    'corners': ('team_a_corners', 'team_b_corners'),
    'yellow_cards': ('team_a_yellow_cards', 'team_b_yellow_cards'),
    'fouls': ('team_a_fouls', 'team_b_fouls'),
    'shots': ('team_a_shots', 'team_b_shots'),
    'shotsOnTarget': ('team_a_shotsOnTarget', 'team_b_shotsOnTarget'),
    'dangerous_attacks': ('team_a_dangerous_attacks', 'team_b_dangerous_attacks'),
    'attacks': ('team_a_attacks', 'team_b_attacks'),
    'possession': ('team_a_possession', 'team_b_possession'),
    'xg': ('team_a_xg', 'team_b_xg'),
    'offsides': ('team_a_offsides', 'team_b_offsides'),
}

TARGETS = {
    'goals_1.5': ('goals', 1.5), 'goals_2.5': ('goals', 2.5), 'goals_3.5': ('goals', 3.5),
    'corners_9.5': ('corners', 9.5), 'corners_10.5': ('corners', 10.5),
    'cards_3.5': ('cards', 3.5), 'cards_4.5': ('cards', 4.5),
    'btts': ('btts', None), 'clean_sheet': ('clean_sheet', None),
}


def build_team_consistent_features(matches):
    """For each match (date-sorted), attach point-in-time TEAM-CONSISTENT features:
      f_home_<stat>_for_wN, f_home_<stat>_against_wN, and same for away, plus
      referee expanding card/foul rate. Uses ONLY each team's prior matches."""
    hist = defaultdict(list)   # team -> list of dict(stat_for, stat_against)
    ref_acc = defaultdict(lambda: [0, 0.0, 0.0])
    league_acc = [0, 0.0, 0.0]

    for m in matches:
        h, a = m.get('home_name'), m.get('away_name')
        feat = {}
        for side, team in (('home', h), ('away', a)):
            recs = hist.get(team, [])
            for base in STAT_FOR:
                for w in WINDOWS:
                    if len(recs) >= w:
                        fv = [r[base + '_for'] for r in recs[-w:] if r.get(base + '_for') is not None]
                        av = [r[base + '_against'] for r in recs[-w:] if r.get(base + '_against') is not None]
                        feat[f'{side}_{base}_for_w{w}'] = float(np.mean(fv)) if len(fv) == w else None
                        feat[f'{side}_{base}_against_w{w}'] = float(np.mean(av)) if len(av) == w else None
                    else:
                        feat[f'{side}_{base}_for_w{w}'] = None
                        feat[f'{side}_{base}_against_w{w}'] = None
        # referee expanding (look-ahead-free)
        ref = m.get('refereeID')
        if ref is not None and ref_acc[ref][0] >= 5:
            feat['ref_card_rate'] = ref_acc[ref][1] / ref_acc[ref][0]
            feat['ref_foul_rate'] = ref_acc[ref][2] / ref_acc[ref][0]
        else:
            feat['ref_card_rate'] = (league_acc[1]/league_acc[0]) if league_acc[0] else 3.6
            feat['ref_foul_rate'] = (league_acc[2]/league_acc[0]) if league_acc[0] else 22.0
        m['_feat'] = feat

        # update histories AFTER emitting (PIT)
        def sval(hf, af):
            return (m.get(hf), m.get(af))
        hrec, arec = {}, {}
        for base, (hf, af) in STAT_FOR.items():
            hv, av = sval(hf, af)
            hrec[base + '_for'] = hv; hrec[base + '_against'] = av
            arec[base + '_for'] = av; arec[base + '_against'] = hv
        if h:
            hist[h].append(hrec)
        if a:
            hist[a].append(arec)
        ya = m.get('team_a_yellow_cards', 0) or 0; yb = m.get('team_b_yellow_cards', 0) or 0
        ra = m.get('team_a_red_cards', 0) or 0; rb = m.get('team_b_red_cards', 0) or 0
        fa = m.get('team_a_fouls', 0) or 0; fb = m.get('team_b_fouls', 0) or 0
        cards = ya + yb + ra + rb; fouls = fa + fb
        if ref is not None:
            ref_acc[ref][0] += 1; ref_acc[ref][1] += cards; ref_acc[ref][2] += fouls
        league_acc[0] += 1; league_acc[1] += cards; league_acc[2] += fouls


def fn(side, base, fa, w):
    return f'{side}_{base}_{fa}_w{w}'


def build_candidates():
    """Mechanism-restricted candidate list over TEAM-CONSISTENT raw features.
    Each = (target, feature tuple, mechanism, size). Windows w5/w10."""
    C = []
    def add(t, feats, mech):
        C.append({'target': t, 'features': tuple(feats), 'mechanism': mech, 'size': len(feats)})

    # 1) SAME-STAT PERSISTENCE: both teams' 'for' rate of the target stat
    persist = {'corners': ['corners_9.5', 'corners_10.5'],
               'yellow_cards': ['cards_3.5', 'cards_4.5'],
               'xg': ['goals_1.5', 'goals_2.5', 'goals_3.5'],
               'shotsOnTarget': ['goals_2.5'],
               'dangerous_attacks': ['corners_9.5']}
    for stat, tgts in persist.items():
        for w in WINDOWS:
            for tg in tgts:
                add(tg, [fn('home', stat, 'for', w), fn('away', stat, 'for', w)],
                    f'same-stat persistence: both teams rolling {stat}-for -> {tg}')

    # 2) FOR x AGAINST (attack vs concede): home 'for' of stat + away 'against' of stat
    fa_pairs = [('xg', 'goals_2.5', 'attack xG vs opponent xG-conceded -> goals'),
                ('shotsOnTarget', 'goals_2.5', 'SOT-for vs SOT-conceded -> goals'),
                ('corners', 'corners_9.5', 'corners-for vs corners-conceded -> corners'),
                ('dangerous_attacks', 'corners_9.5', 'dangerous attacks vs conceded -> corners')]
    for stat, tg, mech in fa_pairs:
        for w in WINDOWS:
            add(tg, [fn('home', stat, 'for', w), fn('away', stat, 'against', w)], 'for-vs-against: ' + mech)
            add(tg, [fn('away', stat, 'for', w), fn('home', stat, 'against', w)], 'for-vs-against(rev): ' + mech)

    # 3) CROSS-STAT within team
    cross = [('dangerous_attacks', 'corners_9.5', 'dangerous attacks -> corners'),
             ('dangerous_attacks', 'corners_10.5', 'dangerous attacks -> corners'),
             ('shots', 'goals_2.5', 'shot volume -> goals'),
             ('fouls', 'cards_3.5', 'fouls -> cards'),
             ('fouls', 'cards_4.5', 'fouls -> cards'),
             ('attacks', 'corners_9.5', 'territorial attacks -> corners'),
             ('offsides', 'goals_2.5', 'attacking intent -> goals')]
    for stat, tg, mech in cross:
        for w in WINDOWS:
            add(tg, [fn('home', stat, 'for', w), fn('away', stat, 'for', w)], 'cross-stat: ' + mech)

    # 4) CROSS-TEAM INTERACTION (different stats, both sides)
    inter = [('dangerous_attacks', 'fouls', 'cards_3.5', 'A pressure x B fouling -> cards'),
             ('shots', 'shotsOnTarget', 'goals_2.5', 'A shots x B SOT-conceded -> goals'),
             ('dangerous_attacks', 'corners', 'corners_9.5', 'A pressure x B corners-conceded -> corners'),
             ('fouls', 'fouls', 'cards_4.5', 'mutual fouling -> cards'),
             ('xg', 'xg', 'goals_2.5', 'combined attacking quality -> goals')]
    for sa, sb, tg, mech in inter:
        for w in WINDOWS:
            add(tg, [fn('home', sa, 'for', w), fn('away', sb, 'for', w)], 'cross-team interaction: ' + mech)

    # 5) REFEREE-CONDITIONED
    for w in WINDOWS:
        add('cards_3.5', ['ref_card_rate', fn('home', 'fouls', 'for', w), fn('away', 'fouls', 'for', w)],
            'referee card tendency x both teams foul rate -> cards')
        add('cards_4.5', ['ref_card_rate', fn('home', 'fouls', 'for', w), fn('away', 'fouls', 'for', w)],
            'referee card tendency x both teams foul rate -> cards')
    add('cards_3.5', ['ref_card_rate'], 'referee card tendency alone -> cards')
    add('cards_4.5', ['ref_foul_rate'], 'referee foul tendency alone -> cards')

    # 6) STYLE / TEMPO
    for w in WINDOWS:
        add('corners_9.5', [fn('home', 'dangerous_attacks', 'for', w), fn('home', 'attacks', 'for', w)],
            'attack directness -> corners')
        add('goals_2.5', [fn('home', 'shotsOnTarget', 'for', w), fn('home', 'shots', 'for', w)],
            'shot quality -> goals')
        add('cards_3.5', [fn('home', 'fouls', 'for', w), fn('away', 'fouls', 'for', w), fn('home', 'yellow_cards', 'for', w)],
            'match intensity -> cards')
    return C


def score(feats, target_name, matches):
    tgt, line = TARGETS[target_name]
    n = len(matches)
    X = np.zeros((n, len(feats))); valid = np.ones(n, bool)
    for j, f in enumerate(feats):
        for i in range(n):
            fe = matches[i]['_feat']
            v = fe.get(f)
            if v is None:
                valid[i] = False
            else:
                X[i, j] = v
    split = int(n * 0.6)
    trm = valid.copy(); trm[split:] = False
    tem = valid.copy(); tem[:split] = False
    if trm.sum() < MIN_TRAIN or tem.sum() < MIN_TEST:
        return None
    Xtr, Xte = X[trm], X[tem]
    mu, sd = Xtr.mean(0), Xtr.std(0); sd[sd == 0] = 1
    Xtr = (Xtr - mu)/sd; Xte = (Xte - mu)/sd
    ytr = np.array([compute_outcome(matches[i], tgt, line) for i in np.where(trm)[0]], float)
    yte = np.array([compute_outcome(matches[i], tgt, line) for i in np.where(tem)[0]], float)
    tv = ~np.isnan(ytr); ev = ~np.isnan(yte)
    if tv.sum() < MIN_TRAIN or ev.sum() < MIN_TEST:
        return None
    Xtr, ytr, Xte, yte = Xtr[tv], ytr[tv], Xte[ev], yte[ev]
    beta = fit_logistic_l2(Xtr, ytr, lam=1.0)
    probs = np.clip(expit(np.column_stack([Xte, np.ones(len(Xte))]) @ beta), 0.01, 0.99)
    brier = float(np.mean((probs - yte)**2))
    base = float(yte.mean()); nb = float(np.mean((base - yte)**2))
    bss = (1 - brier/nb)*100 if nb > 0 else 0.0
    ece = 0.0
    for b in range(10):
        lo, hi = b/10, (b+1)/10
        mk = (probs >= lo) & (probs < hi if b < 9 else probs <= hi)
        if mk.sum() > 0:
            ece += (mk.sum()/len(probs))*abs(probs[mk].mean() - yte[mk].mean())
    ll_m = float(np.sum(yte*np.log(probs)+(1-yte)*np.log(1-probs)))
    p0 = np.clip(base, 0.01, 0.99)
    ll0 = float(np.sum(yte*np.log(p0)+(1-yte)*np.log(1-p0)))
    p = float(sp_stats.chi2.sf(max(2*(ll_m-ll0), 0), len(feats)))
    return {'bss_pct': round(bss,4), 'brier': round(brier,5), 'ece': round(ece,4),
            'p_value': p, 'n_test': int(ev.sum()), 'base_rate': round(base,4)}


def gate(target_name, matches):
    """Known-good instrument per target: both teams' 'for' rate of the OWN target stat."""
    tgt, _ = TARGETS[target_name]
    inst = {'corners': ('home_corners_for_w5', 'away_corners_for_w5'),
            'cards': ('home_yellow_cards_for_w5', 'away_yellow_cards_for_w5'),
            'goals': ('home_xg_for_w5', 'away_xg_for_w5'),
            'btts': ('home_xg_for_w5', 'away_xg_for_w5'),
            'clean_sheet': ('home_xg_for_w5', 'away_xg_for_w5')}.get(tgt)
    r = score(inst, target_name, matches)
    if r is None:
        return {'passed': False, 'reason': 'insufficient_n', 'instrument': inst, 'detail': None}
    passed = r['bss_pct'] > 0 and r['p_value'] < 0.05
    return {'passed': passed, 'instrument': inst, 'detail': r,
            'reason': None if passed else 'known-good instrument undetectable at this league/target n'}


def main():
    t0 = time.time()
    print("Loading discovery corpus (older season; held-out untouched)...")
    allms = load_discovery_set()
    allms.sort(key=lambda m: m.get('date_unix', 0))
    print("Building team-consistent point-in-time features (global history)...")
    build_team_consistent_features(allms)   # global team history across leagues

    by_league = defaultdict(list)
    for m in allms:
        by_league[m['_league']].append(m)

    candidates = build_candidates()
    print(f"Mechanism-restricted candidates per league: {len(candidates)}")

    # POOLED gate first (proves the instrument detects known-good signal)
    pooled_gates = {t: gate(t, allms) for t in TARGETS}
    print("Pooled sanity gate:")
    for t, g in pooled_gates.items():
        d = g['detail']
        print(f"  {t:12s} passed={g['passed']} " + (f"BSS={d['bss_pct']:+.2f}% p={d['p_value']:.2e} n={d['n_test']}" if d else g['reason']))

    results = {'_pooled_gates': pooled_gates}
    all_p, all_idx = [], []
    total_tested = 0

    # ── POOLED SEARCH (where the instrument has power). Gate-passed targets only. ──
    # Per-league is reported as a diagnostic breakdown for each candidate, but the
    # search/FDR is done pooled because per-league n lacks power (gate fails per-league).
    pooled_rows = []
    pooled_p, pooled_idx = [], []
    for c in candidates:
        g = pooled_gates.get(c['target'], {})
        base = {k: c[k] for k in ('target', 'features', 'mechanism', 'size')}
        if not g.get('passed'):
            pooled_rows.append({**base, 'status': 'skipped_gate_failed'})
            continue
        r = score(c['features'], c['target'], allms)
        if r is None:
            pooled_rows.append({**base, 'status': 'insufficient_n'})
            continue
        # per-league diagnostic breakdown
        per_lg = {}
        for lg in sorted(by_league.keys()):
            ms = by_league[lg]
            if len(ms) < 260:
                continue
            rr = score(c['features'], c['target'], ms)
            if rr:
                per_lg[lg] = {'bss_pct': rr['bss_pct'], 'p_value': rr['p_value'], 'n_test': rr['n_test']}
        pooled_p.append(r['p_value']); pooled_idx.append(len(pooled_rows))
        pooled_rows.append({**base, 'status': 'tested', **r, 'per_league': per_lg})
    # cumulative FDR is computed on the POOLED search family
    all_p = pooled_p; all_idx = [('POOLED', i) for i in pooled_idx]
    total_tested = len(pooled_p)
    results['_pooled_search'] = {'n_matches': len(allms), 'candidates': pooled_rows}

    for lg in sorted(by_league.keys()):
        ms = by_league[lg]
        if len(ms) < 260:
            results[lg] = {'status': 'insufficient_matches', 'n': len(ms)}
            continue
        gates = {t: gate(t, ms) for t in TARGETS}
        npass = sum(1 for g in gates.values() if g.get('passed'))
        results[lg] = {'status': 'searched', 'n': len(ms), 'gates': gates,
                       'per_league_gates_passed': npass}
        print(f"  {lg:28s} n={len(ms):4d} per-league gates_passed={npass}/{len(TARGETS)}")

    run_count = total_tested
    cum_after = CUMULATIVE_FAMILY_BEFORE + run_count
    fdr = FDRController(alpha=0.05)
    run_fdr = fdr.correct(all_p) if all_p else []
    run_surv = [(all_idx[i], all_p[i]) for i, fr in enumerate(run_fdr) if fr.rejected]
    cum_thr = 0.05/cum_after if cum_after else 0.0
    cum_surv = [(all_idx[i], all_p[i]) for i, p in enumerate(all_p) if p <= cum_thr]

    out = {
        'analysis_date': datetime.now(timezone.utc).isoformat(),
        'scope': 'raw observable stats only; team-consistent PIT features; no prior-metric reference',
        'windows': list(WINDOWS), 'candidates_per_league': len(candidates),
        'run_candidate_count_tested': run_count,
        'cumulative_family_before': CUMULATIVE_FAMILY_BEFORE,
        'cumulative_family_after': cum_after,
        'fdr': {'run_level_bh_survivors': len(run_surv),
                'cumulative_rank1_threshold': cum_thr,
                'cumulative_survivors': [{'league': l, 'p': p} for (l, _), p in cum_surv]},
        'pooled_gates': pooled_gates,
        'leagues': {k: v for k, v in results.items() if k != '_pooled_gates'},
        'duration_sec': round(time.time()-t0, 1),
    }
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2, default=str)

    print(f"\nRun candidates tested: {run_count}  cumulative: {CUMULATIVE_FAMILY_BEFORE} -> {cum_after}")
    print(f"Run-level BH survivors: {len(run_surv)}  |  cumulative rank-1 p<={cum_thr:.2e}: {len(cum_surv)}")

    tested = [{**c} for c in pooled_rows if c.get('status') == 'tested']
    tested.sort(key=lambda x: -x['bss_pct'])
    print("\nTop 20 raw-stat relationships by pooled out-of-sample BSS (uncorrected):")
    for t in tested[:20]:
        print(f"  {t['target']:12s} BSS={t['bss_pct']:+6.2f}% p={t['p_value']:.2e} n={t['n_test']:4d} | {t['mechanism'][:52]}")
    print(f"\nSaved: {OUT}")
    return out


if __name__ == '__main__':
    main()
