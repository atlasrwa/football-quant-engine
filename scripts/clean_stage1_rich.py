"""
Stage 1 — RICH tier (TheStatsAPI slice: Championship / La Liga 2 / Ligue 2).

Self-contained: features built by the verified clean engine on rich match dicts
(clean_rich_loader). Adds rich-field mechanism candidates on top of the core set.
Same discipline: mechanism-guided, per-league walk-forward, within-league
significance required, fresh FDR family for this tier's tested cells.
"""
from __future__ import annotations
import sys, json, time
from collections import defaultdict
from datetime import datetime, timezone
import numpy as np

sys.path.insert(0, '/home/ubuntu'); sys.path.insert(0, '/home/ubuntu/scripts')
from clean_features import build_features, BASE_STATS_RICH
from clean_rich_loader import load_rich_matches
from clean_stage1 import TARGETS, F, score, gate
from src.engine.analysis.fdr import FDRController

OUT = '/home/ubuntu/data/discovery/clean_stage1_rich.json'
WIN = ('w5', 'w10')


def build_rich_candidates():
    C = []
    def add(t, feats, mech, kind):
        C.append({'target': t, 'features': tuple(feats), 'mechanism': mech, 'size': len(feats), 'kind': kind})
    for w in WIN:
        # core persistence (rich tier has bigger n)
        add('corners_tot_9.5', [F('h','corners','for',w), F('a','corners','for',w)], 'both corner-for -> total corners', 'persistence')
        add('corners_tot_10.5',[F('h','corners','for',w), F('a','corners','for',w)], 'both corner-for -> total corners', 'persistence')
        add('corners_b_4.5', [F('a','corners','for',w), F('h','corners','against',w)], 'away corner-for x home corner-conceded', 'persistence')
        add('corners_a_4.5', [F('h','corners','for',w), F('a','corners','against',w)], 'home corner-for x away corner-conceded', 'persistence')
        add('cards_tot_3.5', [F('h','yellow_cards','for',w), F('a','yellow_cards','for',w)], 'both card rate -> total cards', 'persistence')
        add('cards_tot_4.5', [F('h','yellow_cards','for',w), F('a','yellow_cards','for',w)], 'both card rate -> total cards', 'persistence')
        add('goals_tot_2.5',[F('h','xg','for',w), F('a','xg','for',w)], 'both xG -> total goals', 'persistence')
        add('goals_tot_1.5',[F('h','xg','for',w), F('a','xg','for',w)], 'both xG -> total goals', 'persistence')
        add('goals_tot_3.5',[F('h','xg','for',w), F('a','xg','for',w)], 'both xG -> total goals', 'persistence')
        add('sot_a_3.5', [F('h','shotsOnTarget','for',w), F('a','shotsOnTarget','against',w)], 'home SOT-for x away SOT-conceded', 'persistence')
        add('sot_b_3.5', [F('a','shotsOnTarget','for',w), F('h','shotsOnTarget','against',w)], 'away SOT-for x home SOT-conceded', 'persistence')
        add('btts', [F('h','xg','for',w), F('a','xg','for',w)], 'both xG -> BTTS', 'persistence')

        # ── RICH-ONLY mechanisms (the point of this tier) ──
        # crosses x aerial duels -> corners
        add('corners_tot_9.5', [F('h','accurate_crosses','for',w), F('a','aerial_duels_won','for',w)], 'RICH: crosses x opp aerial duel% -> corners', 'cross')
        add('corners_tot_10.5',[F('h','accurate_crosses','for',w), F('a','aerial_duels_won','for',w)], 'RICH: crosses x opp aerial duel% -> corners', 'cross')
        # final third entries -> SOT
        add('sot_a_3.5', [F('h','final_third_entries','for',w), F('a','tackles','for',w)], 'RICH: final-third entries x opp tackles -> SOT', 'cross')
        # touches in box -> goals
        add('goals_tot_2.5', [F('h','touches_in_box','for',w), F('a','touches_in_box','for',w)], 'RICH: touches in box -> goals', 'cross')
        add('goals_a_1.5', [F('h','touches_in_box','for',w), F('a','clearances','for',w)], 'RICH: home box touches x away clearances -> home goals', 'cross')
        # blocked shots -> corners
        add('corners_tot_9.5', [F('h','blocked_shots','for',w), F('a','blocked_shots','for',w)], 'RICH: blocked shots -> corners', 'cross')
        # big chances -> goals
        add('goals_tot_2.5', [F('h','big_chances','for',w), F('a','big_chances','for',w)], 'RICH: big chances -> goals', 'cross')
        # shots x saves/goals-prevented -> goals
        add('goals_a_1.5', [F('h','shots','for',w), F('a','goals_prevented','for',w)], 'RICH: home shots x away GK goals-prevented -> home goals', 'cross')
        add('goals_a_1.5', [F('h','big_chances','for',w), F('a','saves','for',w)], 'RICH: home big chances x away saves -> home goals', 'cross')
        # tackles x dribbles -> fouls/cards
        add('cards_tot_3.5', [F('h','tackles','for',w), F('a','dribbles','for',w)], 'RICH: home tackles x away dribbles -> cards', 'cross')
        add('cards_tot_4.5', [F('h','tackles','for',w), F('a','dribbles','for',w)], 'RICH: home tackles x away dribbles -> cards', 'cross')
        # shots inside vs outside box composition -> goals
        add('goals_tot_2.5', [F('h','shots_inside_box','for',w), F('a','shots_inside_box','for',w)], 'RICH: shots inside box -> goals', 'cross')
        # npxg -> goals
        add('goals_tot_2.5', [F('h','npxg','for',w), F('a','npxg','for',w)], 'RICH: npxG -> goals', 'cross')
        add('goals_tot_2.5', [F('h','big_chances','for',w), F('a','npxg','for',w)], 'RICH: big chances + npxG -> goals', 'cross')
        # low-block proxy: clearances/interceptions -> concede corners
        add('corners_a_4.5', [F('h','corners','for',w), F('a','clearances','for',w)], 'RICH: home corner-for x away clearances(low-block) -> home corners', 'cross')
        # referee-conditioned still available (core fouls)
        add('cards_tot_3.5', ['ref_card_rate', F('h','fouls','for',w), F('a','fouls','for',w)], 'ref card x both fouling -> cards', 'cross')
        add('cards_tot_4.5', ['ref_card_rate', F('h','fouls','for',w), F('a','fouls','for',w)], 'ref card x both fouling -> cards', 'cross')
    add('cards_tot_3.5', ['ref_card_rate'], 'referee card tendency alone -> cards', 'cross')
    return C


def main():
    t0 = time.time()
    print("Loading rich slice + building verified features (rich tier)...")
    allms = load_rich_matches()
    build_features(allms, BASE_STATS_RICH)
    by_league = defaultdict(list)
    for m in allms:
        by_league[m['_league']].append(m)
    candidates = build_rich_candidates()
    print(f"Rich-tier candidates (per league): {len(candidates)}")

    results = {}
    fresh_family = 0
    all_p, all_key = [], []
    pooled_gates = {t: gate(t, TARGETS[t], allms) for t in TARGETS if t in TARGETS}

    for lg in sorted(by_league.keys()):
        ms = by_league[lg]
        if len(ms) < 260:
            results[lg] = {'status': 'insufficient_matches', 'n': len(ms)}; continue
        gates = {t: gate(t, TARGETS[t], ms) for t in set(c['target'] for c in candidates)}
        rows = []
        for c in candidates:
            g = gates.get(c['target'], {})
            base = {k: c[k] for k in ('target','features','mechanism','size','kind')}
            if c['kind'] == 'persistence' and not g.get('passed'):
                rows.append({**base, 'status': 'skipped_gate_failed'}); continue
            r = score(c['features'], TARGETS[c['target']], ms)
            if r is None:
                rows.append({**base, 'status': 'insufficient_n'}); continue
            fresh_family += 1
            all_p.append(r['p_value']); all_key.append((lg, len(rows)))
            rows.append({**base, 'status': 'tested', **r})
        nt = sum(1 for r in rows if r.get('status')=='tested')
        npass = sum(1 for gg in gates.values() if gg.get('passed'))
        results[lg] = {'status':'searched','n':len(ms),'gates':gates,'candidates':rows}
        print(f"  {lg:32s} n={len(ms):4d} gates={npass} tested={nt}")

    fdr = FDRController(alpha=0.05)
    fres = fdr.correct(all_p) if all_p else []
    survivors = []
    for i, fr in enumerate(fres):
        if fr.rejected:
            lg, ri = all_key[i]; row = results[lg]['candidates'][ri]
            survivors.append({'league': lg, 'target': row['target'], 'mechanism': row['mechanism'],
                              'features': row['features'], 'bss_pct': row['bss_pct'],
                              'p_value': row['p_value'], 'n_test': row['n_test'], 'kind': row['kind']})

    out = {'analysis_date': datetime.now(timezone.utc).isoformat(),
           'tier': 'rich (TheStatsAPI slice: Championship / La Liga 2 / Ligue 2)',
           'scope': 'raw observable stats incl TheStatsAPI-only fields; team-consistent verified features; FRESH FDR family for this tier',
           'windows': list(WIN), 'candidates_per_league': len(candidates),
           'fresh_fdr_family_size': fresh_family,
           'fdr_within_league_survivors': survivors, 'n_within_league_survivors': len(survivors),
           'leagues': results, 'duration_sec': round(time.time()-t0, 1)}
    with open(OUT, 'w') as f:
        json.dump(out, f, indent=2, default=str)

    print(f"\nRich fresh FDR family: {fresh_family}  within-league survivors: {len(survivors)}")
    for s in sorted(survivors, key=lambda x:-x['bss_pct'])[:20]:
        tag = 'RICH' if 'RICH' in s['mechanism'] else 'core'
        print(f"  [{tag}] {s['league'][:20]:20s} {s['target']:16s} BSS={s['bss_pct']:+6.2f}% p={s['p_value']:.2e} n={s['n_test']} | {s['mechanism'][:44]}")
    tested = [{'league':lg, **c} for lg,r in results.items() if isinstance(r,dict) and r.get('status')=='searched'
              for c in r['candidates'] if c.get('status')=='tested']
    tested.sort(key=lambda x:-x['bss_pct'])
    print("\nTop 15 rich-tier by within-league BSS (uncorrected):")
    for t in tested[:15]:
        tag='RICH' if 'RICH' in t['mechanism'] else 'core'
        print(f"  [{tag}] {t['league'][:20]:20s} {t['target']:16s} BSS={t['bss_pct']:+6.2f}% p={t['p_value']:.4f} n={t['n_test']} | {t['mechanism'][:40]}")
    print(f"\nSaved: {OUT}")
    return out


if __name__ == '__main__':
    main()
