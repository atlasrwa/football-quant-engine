"""
Feature verification harness — all 5 checks, reported BEFORE any searching.
If any check fails, STOP and report (do not proceed with a caveat).

Checks:
 1. Team-identity trace: pick teams, trace a fixture's rolling feature to source
    matches; confirm all involve that team and include home+away appearances.
 2. Known-signal: goals-scored persistence >0, cards persistence >0 (league-dep),
    xG->goals >~0.10.
 3. Orientation: home-team ('h') features align with home outcomes, not away.
 4. Look-ahead: feature excludes current + later matches.
 5. Shuffle null: permuting feature->outcome collapses predictive corr to ~0.
"""
from __future__ import annotations
import sys, json
from collections import defaultdict
import numpy as np

sys.path.insert(0, '/home/ubuntu'); sys.path.insert(0, '/home/ubuntu/scripts')
from src.discovery.corpus import load_discovery_set
from clean_features import build_features, BASE_STATS_BROAD


def col(matches, fn):
    return np.array([m['_f'].get(fn) if m['_f'].get(fn) is not None else np.nan for m in matches])


def main():
    print("Loading discovery corpus (older season; held-out untouched)...")
    ms = load_discovery_set()
    ms.sort(key=lambda m: m.get('date_unix', 0))
    build_features(ms, BASE_STATS_BROAD)
    n = len(ms)
    report = {}

    # ── CHECK 1: team-identity trace ──
    print("\n=== CHECK 1: team-identity trace ===")
    trace_ok = True
    traces = []
    # find a fixture late in the season for a few teams so history exists
    seen = set(); picks = []
    for i in range(n - 1, -1, -1):
        tid = ms[i].get('homeID')
        if tid in seen:
            continue
        seen.add(tid); picks.append(i)
        if len(picks) >= 4:
            break
    for i in picks:
        m = ms[i]; tid = m['homeID']
        # reconstruct: that team's prior matches (home or away) before date
        prior = [k for k in range(i) if ms[k].get('homeID') == tid or ms[k].get('awayID') == tid]
        last5 = prior[-5:]
        # feature h_corners_for_w5 should equal mean of that team's own corners in last5
        own = []
        for k in last5:
            mk = ms[k]
            if mk.get('homeID') == tid:
                own.append(mk.get('team_a_corners'))
            else:
                own.append(mk.get('team_b_corners'))
        # replicate builder missing-value handling: -1/None => missing; require all 5 present
        own_clean = [o for o in own if o is not None and o != -1]
        recomputed = float(np.mean(own_clean)) if len(own_clean) == 5 else None
        n_home = sum(1 for k in last5 if ms[k].get('homeID') == tid)
        n_away = len(last5) - n_home
        feat = m['_f'].get('h_corners_for_w5')
        match_ok = (feat is not None and recomputed is not None
                    and abs(feat - recomputed) < 1e-6) or (feat is None and recomputed is None)
        all_involve = all(ms[k].get('homeID') == tid or ms[k].get('awayID') == tid for k in last5)
        traces.append({'team_id': tid, 'fixture_idx': i, 'feature_h_corners_for_w5': feat,
                       'recomputed_from_source': recomputed, 'n_source': len(last5),
                       'n_home_appearances': n_home, 'n_away_appearances': n_away,
                       'all_sources_involve_team': all_involve, 'match': match_ok})
        print(f"  team {tid}: feature={feat} recomputed={recomputed} "
              f"sources={len(last5)}(home {n_home}/away {n_away}) allInvolve={all_involve} match={match_ok}")
        if not (match_ok and all_involve):
            trace_ok = False
    report['check1_team_identity_trace'] = {'passed': trace_ok, 'traces': traces}

    # ── CHECK 2: known-signal ──
    print("\n=== CHECK 2: known-signal ===")
    def corr_next(feat_for_home, feat_for_away, outcome_home_field, outcome_away_field):
        # correlate team's own rolling 'for' rate with its OWN next-match outcome, pooled over both sides
        xs, ys = [], []
        for m in ms:
            fh = m['_f'].get(feat_for_home); fa = m['_f'].get(feat_for_away)
            oh = m.get(outcome_home_field); oa = m.get(outcome_away_field)
            if fh is not None and oh is not None and oh != -1:
                xs.append(fh); ys.append(float(oh))
            if fa is not None and oa is not None and oa != -1:
                xs.append(fa); ys.append(float(oa))
        if len(xs) < 100:
            return None, len(xs)
        return float(np.corrcoef(xs, ys)[0, 1]), len(xs)
    goals_c, gn = corr_next('h_goals_for_w5', 'a_goals_for_w5', 'homeGoalCount', 'awayGoalCount')
    cards_c, cn = corr_next('h_yellow_cards_for_w5', 'a_yellow_cards_for_w5', 'team_a_yellow_cards', 'team_b_yellow_cards')
    xg_c, xn = corr_next('h_xg_for_w5', 'a_xg_for_w5', 'homeGoalCount', 'awayGoalCount')
    print(f"  goals-scored persistence corr = {goals_c:.4f} (n={gn})")
    print(f"  cards persistence corr        = {cards_c:.4f} (n={cn})")
    print(f"  xG(for) -> goals-scored corr  = {xg_c:.4f} (n={xn})")
    c2 = (goals_c is not None and goals_c > 0.05 and cards_c is not None and cards_c > 0.02
          and xg_c is not None and xg_c > 0.08)
    report['check2_known_signal'] = {'passed': bool(c2),
        'goals_persistence': goals_c, 'cards_persistence': cards_c, 'xg_to_goals': xg_c,
        'thresholds': {'goals>0.05': goals_c > 0.05, 'cards>0.02': cards_c > 0.02, 'xg>0.08': xg_c > 0.08}}
    print(f"  PASS={c2}")

    # ── CHECK 3: orientation ──
    print("\n=== CHECK 3: orientation ===")
    # h_* features must correlate more strongly with HOME outcome than AWAY outcome
    xs_h, y_home, y_away = [], [], []
    for m in ms:
        v = m['_f'].get('h_xg_for_w5')
        if v is not None and m.get('homeGoalCount') is not None and m.get('awayGoalCount') is not None:
            xs_h.append(v); y_home.append(float(m['homeGoalCount'])); y_away.append(float(m['awayGoalCount']))
    ch_home = float(np.corrcoef(xs_h, y_home)[0, 1])
    ch_away = float(np.corrcoef(xs_h, y_away)[0, 1])
    print(f"  corr(h_xg_for_w5, home goals)={ch_home:.4f}  vs  corr(h_xg_for_w5, away goals)={ch_away:.4f}")
    c3 = ch_home > ch_away
    report['check3_orientation'] = {'passed': bool(c3), 'corr_h_feature_home_outcome': ch_home,
                                    'corr_h_feature_away_outcome': ch_away}
    print(f"  PASS={c3} (home-team feature aligns with home outcome)")

    # ── CHECK 4: look-ahead ──
    print("\n=== CHECK 4: look-ahead ===")
    # For a sample fixture, the w5 feature must not change if we corrupt the CURRENT match's
    # own stat (i.e. it doesn't use current), and must equal recompute from strictly-prior only.
    c4 = True; details = []
    import random; random.seed(0)
    sample_idx = random.sample(range(200, n), 20)
    for i in sample_idx:
        m = ms[i]; tid = m['homeID']
        prior = [k for k in range(i) if ms[k].get('homeID') == tid or ms[k].get('awayID') == tid][-5:]
        own = []
        for k in prior:
            mk = ms[k]
            own.append(mk.get('team_a_corners') if mk.get('homeID') == tid else mk.get('team_b_corners'))
        own_clean = [o for o in own if o is not None and o != -1]
        recomputed = float(np.mean(own_clean)) if len(own_clean) == 5 else None
        feat = m['_f'].get('h_corners_for_w5')
        if feat is not None and recomputed is not None and abs(feat - recomputed) > 1e-6:
            c4 = False; details.append({'idx': i, 'feat': feat, 'recomputed': recomputed})
        elif (feat is None) != (recomputed is None):
            c4 = False; details.append({'idx': i, 'feat': feat, 'recomputed': recomputed, 'nullmismatch': True})
    report['check4_look_ahead'] = {'passed': bool(c4), 'n_sampled': len(sample_idx), 'mismatches': details}
    print(f"  sampled {len(sample_idx)} fixtures; strictly-prior recompute matches feature: PASS={c4}")

    # ── CHECK 5: shuffle null ──
    print("\n=== CHECK 5: shuffle null ===")
    xs, ys = [], []
    for m in ms:
        v = m['_f'].get('h_xg_for_w5'); o = m.get('homeGoalCount')
        if v is not None and o is not None and o != -1:
            xs.append(v); ys.append(float(o))
    xs = np.array(xs); ys = np.array(ys)
    true_corr = float(np.corrcoef(xs, ys)[0, 1])
    rng = np.random.default_rng(0)
    shuffled = []
    for _ in range(50):
        ysh = ys.copy(); rng.shuffle(ysh)
        shuffled.append(abs(float(np.corrcoef(xs, ysh)[0, 1])))
    max_shuf = max(shuffled); mean_shuf = float(np.mean(shuffled))
    print(f"  true |corr|={abs(true_corr):.4f}  shuffled mean|corr|={mean_shuf:.4f} max={max_shuf:.4f}")
    c5 = abs(true_corr) > 5 * max_shuf
    report['check5_shuffle_null'] = {'passed': bool(c5), 'true_corr': true_corr,
                                     'shuffled_mean_abs': mean_shuf, 'shuffled_max_abs': max_shuf}
    print(f"  PASS={c5} (true signal >> shuffled)")

    all_pass = all(report[k]['passed'] for k in report)
    report['ALL_PASS'] = all_pass
    with open('/home/ubuntu/data/discovery/clean_feature_verification.json', 'w') as f:
        json.dump(report, f, indent=2, default=str)
    print(f"\n{'='*60}\nALL 5 CHECKS PASS = {all_pass}")
    print("Saved: data/discovery/clean_feature_verification.json")
    if not all_pass:
        print("STOP: feature verification failed. Do not search.")
        sys.exit(1)
    return report


if __name__ == '__main__':
    main()
