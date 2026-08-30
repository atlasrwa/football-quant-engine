"""
Rich-tier loader: assemble self-contained match dicts from the TheStatsAPI slice
(Championship / La Liga 2 / Ligue 2) in the shape the clean feature engine expects.

Each match dict carries: id, homeID, awayID, date_unix, _league, competition_id,
homeGoalCount, awayGoalCount, and per-side team_a_<f>/team_b_<f> for BOTH the core
stats (corners, cards, fouls, shots, SOT, possession, dangerous_attacks(->via attacks
proxy n/a), xg, offsides) AND the rich-only fields. Values are the 'all' home/away
figures from the stats sections.

Outcomes (goals) come from the fixture score. Per-side corners/cards/SOT come from the
stats overview. All raw observables, no invented composites.
"""
from __future__ import annotations
import json, glob, os
from datetime import datetime

CH_DIR = '/home/ubuntu/data/thestatsapi/championship'

# map our stat name -> (section, field) in the stats JSON; value at [section][field]['all'][home|away]
CORE_MAP = {
    'goals':            None,   # from fixture score
    'corners':          ('overview', 'corner_kicks'),
    'yellow_cards':     ('overview', 'yellow_cards'),
    'red_cards':        ('overview', 'red_cards'),
    'fouls':            ('overview', 'fouls'),
    'shots':            ('overview', 'total_shots'),
    'shotsOnTarget':    ('overview', 'shots_on_target'),
    'possession':       ('overview', 'ball_possession'),
    'xg':               ('overview', 'expected_goals'),
}
RICH_MAP = {
    'tackles':            ('overview', 'tackles'),
    'tackles_won_pct':    ('defending', 'tackles_won_percentage'),
    'interceptions':      ('defending', 'interceptions'),
    'clearances':         ('defending', 'clearances'),
    'ball_recoveries':    ('defending', 'ball_recoveries'),
    'blocked_shots':      ('shots', 'blocked_shots'),
    'shots_inside_box':   ('shots', 'shots_inside_box'),
    'shots_outside_box':  ('shots', 'shots_outside_box'),
    'hit_woodwork':       ('shots', 'hit_woodwork'),
    'big_chances':        ('overview', 'big_chances'),
    'big_chances_missed': ('attack', 'big_chances_missed'),
    'touches_in_box':     ('attack', 'touches_in_penalty_area'),
    'fouled_in_final_third': ('attack', 'fouled_in_final_third'),
    'accurate_crosses':   ('passes', 'accurate_crosses'),
    'accurate_long_balls':('passes', 'accurate_long_balls'),
    'duels_won_pct':      ('duels', 'duels_won_percentage'),
    'dispossessed':       ('duels', 'dispossessed'),
    'dribbles':           ('duels', 'dribbles_percentage'),
    'ground_duels_won':   ('duels', 'ground_duels_percentage'),
    'aerial_duels_won':   ('duels', 'aerial_duels_percentage'),
    'saves':              ('goalkeeping', 'saves'),
    'goals_prevented':    ('goalkeeping', 'goals_prevented'),
    'high_claims':        ('goalkeeping', 'high_claims'),
    'npxg':               ('np_expected_goals', None),  # section itself has ['all']
    'offsides':           ('attack', 'offsides'),
    'final_third_entries':('passes', 'final_third_entries'),
}


def _cell(stats, section, field):
    if section == 'np_expected_goals':
        node = stats.get('np_expected_goals')
    else:
        sec = stats.get(section, {})
        node = sec.get(field) if isinstance(sec, dict) else None
    if not isinstance(node, dict):
        return None, None
    allv = node.get('all')
    if not isinstance(allv, dict):
        return None, None
    return allv.get('home'), allv.get('away')


def _league_of(path):
    b = os.path.basename(path)
    if b.startswith('laliga2_'):
        return 'La Liga 2', 'laliga2_'
    if b.startswith('ligue2_'):
        return 'Ligue 2', 'ligue2_'
    return 'England Championship (2nd tier)', ''


def _mid_of(path):
    b = os.path.basename(path)
    for pre in ('laliga2_', 'ligue2_'):
        b = b.replace(pre, '')
    return b.replace('stats_', '').replace('.json', '')


def load_rich_matches():
    # fixture index: mt_id -> meta
    idmap = {}
    for fx in glob.glob(f'{CH_DIR}/*matches*.json') + glob.glob(f'{CH_DIR}/fixtures_*.json'):
        try:
            data = json.load(open(fx)).get('data', [])
        except Exception:
            continue
        if not isinstance(data, list):
            continue
        for m in data:
            mid = m.get('id')
            if not mid:
                continue
            ht = m.get('home_team', {}) or {}; at = m.get('away_team', {}) or {}
            sc = m.get('score', {}) or {}
            idmap[mid] = {'h': ht.get('id'), 'a': at.get('id'), 'date': m.get('utc_date'),
                          'hg': sc.get('home'), 'ag': sc.get('away'),
                          'comp': m.get('competition_id')}

    matches = []
    for p in glob.glob(f'{CH_DIR}/*stats_mt_*.json'):
        mid = _mid_of(p)
        meta = idmap.get(mid)
        if not meta or meta['h'] is None or meta['hg'] is None:
            continue
        try:
            stats = json.load(open(p)).get('data', {})
        except Exception:
            continue
        league, _ = _league_of(p)
        try:
            du = int(datetime.fromisoformat(meta['date'].replace('Z', '+00:00')).timestamp())
        except Exception:
            du = 0
        rec = {'id': mid, 'homeID': meta['h'], 'awayID': meta['a'], 'date_unix': du,
               '_league': league, 'competition_id': meta.get('comp'),
               'homeGoalCount': meta['hg'], 'awayGoalCount': meta['ag']}
        # core + rich per-side
        for name, loc in {**CORE_MAP, **RICH_MAP}.items():
            if loc is None:
                continue
            hv, av = _cell(stats, loc[0], loc[1])
            rec[f'team_a_{name}'] = hv if hv is not None else -1
            rec[f'team_b_{name}'] = av if av is not None else -1
        # dangerous_attacks / attacks not in TheStatsAPI -> mark missing so those
        # broad-tier candidates are simply not testable in rich tier
        for missing in ('dangerous_attacks', 'attacks', 'shotsOffTarget'):
            rec[f'team_a_{missing}'] = -1
            rec[f'team_b_{missing}'] = -1
        matches.append(rec)
    matches.sort(key=lambda m: m.get('date_unix', 0))
    return matches


if __name__ == '__main__':
    ms = load_rich_matches()
    from collections import Counter
    print('rich matches:', len(ms))
    print('by league:', Counter(m['_league'] for m in ms))
    s = ms[len(ms)//2]
    print('sample keys with values:', {k: s[k] for k in list(s)[:14]})
