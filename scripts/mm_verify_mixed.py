"""
Re-run the 5 feature verification checks on the MIXED (broad+rich) feature pool
built on the 3,189-match rich corpus. Must pass before the per-market search.

Mixed pool = full TheStatsAPI field set (core observables + rich-only fields), which
is how both 'tiers' are combined into one pool on this corpus. (FootyStats-exclusive
fields — xG-prematch, penalties, half-split set-pieces — are not uniformly available
across all three rich leagues, so they are out of scope for the mixed pool; noted.)
"""
from __future__ import annotations
import sys, json
import numpy as np
sys.path.insert(0, '/home/ubuntu'); sys.path.insert(0, '/home/ubuntu/scripts')
from clean_features import build_features, BASE_STATS_RICH
from clean_rich_loader import load_rich_matches

OUT = '/home/ubuntu/data/discovery/mm_mixed_verification.json'


def main():
    print("Loading rich corpus + building MIXED (core+rich) features...")
    ms = load_rich_matches()
    build_features(ms, BASE_STATS_RICH)
    report = {}

    # 1. team-identity trace on a RICH field (tackles) to prove rich fields are team-keyed too
    print("\n=== CHECK 1: team-identity trace (rich field: tackles) ===")
    ok1 = True; traces = []
    seen = set(); picks = []
    for i in range(len(ms) - 1, -1, -1):
        tid = ms[i].get('homeID')
        if tid in seen: continue
        seen.add(tid); picks.append(i)
        if len(picks) >= 4: break
    for i in picks:
        m = ms[i]; tid = m['homeID']
        prior = [k for k in range(i) if ms[k].get('homeID') == tid or ms[k].get('awayID') == tid][-5:]
        own = []
        for k in prior:
            mk = ms[k]
            own.append(mk.get('team_a_tackles') if mk.get('homeID') == tid else mk.get('team_b_tackles'))
        own_c = [o for o in own if o is not None and o != -1]
        recomputed = float(np.mean(own_c)) if len(own_c) == 5 else None
        feat = m['_f'].get('h_tackles_for_w5')
        match_ok = (feat is None and recomputed is None) or (feat is not None and recomputed is not None and abs(feat-recomputed) < 1e-6)
        n_home = sum(1 for k in prior if ms[k].get('homeID') == tid)
        traces.append({'team': tid, 'feature': feat, 'recomputed': recomputed, 'n_home': n_home,
                       'n_away': len(prior)-n_home, 'match': match_ok})
        print(f"  team {tid}: h_tackles_for_w5={feat} recomputed={recomputed} (home {n_home}/away {len(prior)-n_home}) match={match_ok}")
        if not match_ok: ok1 = False
    report['check1_trace_rich_field'] = {'passed': ok1, 'traces': traces}

    # 2. known-signal on mixed pool (goals persistence, cards persistence, xG->goals)
    print("\n=== CHECK 2: known-signal ===")
    def corr(fh, fa, oh, ofield_a):
        xs, ys = [], []
        for m in ms:
            for feat, ofld in ((fh, oh), (fa, ofield_a)):
                v = m['_f'].get(feat); o = m.get(ofld)
                if v is not None and o is not None and o != -1:
                    xs.append(v); ys.append(float(o))
        return float(np.corrcoef(xs, ys)[0, 1]) if len(xs) > 100 else None
    g = corr('h_goals_for_w5','a_goals_for_w5','homeGoalCount','awayGoalCount')
    c = corr('h_yellow_cards_for_w5','a_yellow_cards_for_w5','team_a_yellow_cards','team_b_yellow_cards')
    x = corr('h_xg_for_w5','a_xg_for_w5','homeGoalCount','awayGoalCount')
    # rich known-signal: SOT persistence
    s = corr('h_shotsOnTarget_for_w5','a_shotsOnTarget_for_w5','team_a_shotsOnTarget','team_b_shotsOnTarget')
    print(f"  goals={g:.4f} cards={c:.4f} xG->goals={x:.4f} SOT-persist={s:.4f}")
    ok2 = g>0.05 and c>0.02 and x>0.08 and s>0.05
    report['check2_known_signal'] = {'passed': bool(ok2), 'goals': g, 'cards': c, 'xg_goals': x, 'sot': s}
    print(f"  PASS={ok2}")

    # 3. orientation
    print("\n=== CHECK 3: orientation ===")
    xs, yh, ya = [], [], []
    for m in ms:
        v = m['_f'].get('h_xg_for_w5')
        if v is not None and m.get('homeGoalCount') not in (None,-1) and m.get('awayGoalCount') not in (None,-1):
            xs.append(v); yh.append(float(m['homeGoalCount'])); ya.append(float(m['awayGoalCount']))
    chh = float(np.corrcoef(xs, yh)[0,1]); cha = float(np.corrcoef(xs, ya)[0,1])
    ok3 = chh > cha
    print(f"  corr(h_xg,home)={chh:.4f} vs corr(h_xg,away)={cha:.4f} PASS={ok3}")
    report['check3_orientation'] = {'passed': bool(ok3), 'home': chh, 'away': cha}

    # 4. look-ahead (rich field)
    print("\n=== CHECK 4: look-ahead (tackles) ===")
    import random; random.seed(0)
    ok4 = True; mism = 0
    for i in random.sample(range(200, len(ms)), 20):
        m = ms[i]; tid = m['homeID']
        prior = [k for k in range(i) if ms[k].get('homeID')==tid or ms[k].get('awayID')==tid][-5:]
        own = [ms[k].get('team_a_tackles') if ms[k].get('homeID')==tid else ms[k].get('team_b_tackles') for k in prior]
        own_c = [o for o in own if o is not None and o != -1]
        rec = float(np.mean(own_c)) if len(own_c)==5 else None
        feat = m['_f'].get('h_tackles_for_w5')
        if not ((feat is None and rec is None) or (feat is not None and rec is not None and abs(feat-rec)<1e-6)):
            ok4 = False; mism += 1
    print(f"  20 sampled, mismatches={mism} PASS={ok4}")
    report['check4_look_ahead'] = {'passed': bool(ok4), 'mismatches': mism}

    # 5. shuffle null
    print("\n=== CHECK 5: shuffle null ===")
    xs, ys = [], []
    for m in ms:
        v = m['_f'].get('h_xg_for_w5'); o = m.get('homeGoalCount')
        if v is not None and o not in (None,-1): xs.append(v); ys.append(float(o))
    xs = np.array(xs); ys = np.array(ys)
    tc = abs(float(np.corrcoef(xs, ys)[0,1]))
    rng = np.random.default_rng(0)
    shuf = np.array([abs(float(np.corrcoef(xs, rng.permutation(ys))[0,1])) for _ in range(200)])
    mx = float(shuf.max()); mn = float(shuf.mean()); ssd = float(shuf.std()) or 1e-9
    z = (tc - mn) / ssd
    emp_p = float((shuf >= tc).mean())   # empirical p: fraction of shuffles >= true
    # principled pass: true signal is far outside the shuffled null (z>5 AND none of 200 shuffles reach it)
    ok5 = z > 5 and emp_p == 0.0
    print(f"  true|corr|={tc:.4f} shuffled mean={mn:.4f} max={mx:.4f} z={z:.1f} emp_p={emp_p:.3f} PASS={ok5}")
    report['check5_shuffle'] = {'passed': bool(ok5), 'true': tc, 'shuffled_mean': mn,
                                'shuffled_max': mx, 'z': z, 'empirical_p': emp_p}

    allp = all(report[k]['passed'] for k in report)
    report['ALL_PASS'] = allp
    json.dump(report, open(OUT,'w'), indent=2, default=str)
    print(f"\n{'='*50}\nALL 5 PASS ON MIXED POOL = {allp}\nSaved: {OUT}")
    if not allp:
        sys.exit(1)


if __name__ == '__main__':
    main()
