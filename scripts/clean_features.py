"""
Clean, team-consistent, point-in-time feature engine — built fresh.

NOT derived from any existing rolling-feature code. Keyed on TEAM IDENTITY
(homeID/awayID), never on fixture slot. For each fixture we emit, for both the
home and away team, that team's rolling/expanding rate of each raw stat computed
ONLY from that team's own PRIOR matches (home or away), plus:
  - "for" (the team's own rate) and "against" (what it concedes)
  - explicit home-only / away-only splits (labelled)
  - referee expanding card & foul rates (look-ahead-free)

Windows: w3, w5, w10, and season-to-date (expanding, min 3 matches).
Emit-before-update guarantees no look-ahead.

Public:
  BASE_STATS_BROAD, BASE_STATS_RICH
  build_features(matches, base_stats) -> annotates each match dict with m['_f'] = {featname: value|None}
     feature naming: {who}_{stat}_{fa}_{window}
       who  in {h, a}           (home team of THIS fixture / away team of THIS fixture)
       fa   in {for, against, home, away}   (home/away = venue-split of the team's own 'for' rate)
       window in {w3, w5, w10, std}
     plus refereeID-based: ref_card_rate, ref_foul_rate
"""
from __future__ import annotations
from collections import defaultdict
import numpy as np

# Broad tier: FootyStats per-side raw observables. (home_field, away_field)
BASE_STATS_BROAD = {
    'goals':             ('homeGoalCount', 'awayGoalCount'),
    'corners':           ('team_a_corners', 'team_b_corners'),
    'yellow_cards':      ('team_a_yellow_cards', 'team_b_yellow_cards'),
    'fouls':             ('team_a_fouls', 'team_b_fouls'),
    'shots':             ('team_a_shots', 'team_b_shots'),
    'shotsOnTarget':     ('team_a_shotsOnTarget', 'team_b_shotsOnTarget'),
    'shotsOffTarget':    ('team_a_shotsOffTarget', 'team_b_shotsOffTarget'),
    'dangerous_attacks': ('team_a_dangerous_attacks', 'team_b_dangerous_attacks'),
    'attacks':           ('team_a_attacks', 'team_b_attacks'),
    'possession':        ('team_a_possession', 'team_b_possession'),
    'xg':                ('team_a_xg', 'team_b_xg'),
    'offsides':          ('team_a_offsides', 'team_b_offsides'),
}

# Rich tier adds TheStatsAPI-only fields (already merged onto the match dict as
# team_a_<f>/team_b_<f> by the rich loader). home/away field pairs:
RICH_ONLY = {
    'tackles', 'tackles_won_pct', 'interceptions', 'clearances', 'ball_recoveries',
    'blocked_shots', 'shots_inside_box', 'shots_outside_box', 'hit_woodwork',
    'big_chances', 'big_chances_missed', 'touches_in_box', 'fouled_in_final_third',
    'accurate_crosses', 'accurate_long_balls', 'ground_duels_won', 'aerial_duels_won',
    'duels_won_pct', 'dispossessed', 'dribbles', 'saves', 'goals_prevented',
    'high_claims', 'npxg',
}
BASE_STATS_RICH = dict(BASE_STATS_BROAD)
for r in RICH_ONLY:
    BASE_STATS_RICH[r] = (f'team_a_{r}', f'team_b_{r}')

WINDOWS = ('w3', 'w5', 'w10', 'std')
WIN_N = {'w3': 3, 'w5': 5, 'w10': 10}


def _val(m, field):
    v = m.get(field)
    if v is None or v == -1:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def build_features(matches, base_stats):
    """Annotate each match (must be date-sorted) with m['_f'] team-consistent PIT features.
    Returns the list of feature names produced."""
    # per-team history of dicts: {stat_for, stat_against, is_home}
    hist = defaultdict(list)
    ref_acc = defaultdict(lambda: [0, 0.0, 0.0])   # ref -> [n, cards_sum, fouls_sum]
    league_ref = defaultdict(lambda: [0, 0.0, 0.0])  # per-competition fallback

    stats = list(base_stats.keys())

    def roll(recs, key, win):
        if win == 'std':
            vals = [r[key] for r in recs if r.get(key) is not None]
            return float(np.mean(vals)) if len(vals) >= 3 else None
        n = WIN_N[win]
        if len(recs) < n:
            return None
        vals = [r[key] for r in recs[-n:] if r.get(key) is not None]
        return float(np.mean(vals)) if len(vals) == n else None

    def roll_venue(recs, key, win, want_home):
        sub = [r for r in recs if r['is_home'] == want_home]
        if win == 'std':
            vals = [r[key] for r in sub if r.get(key) is not None]
            return float(np.mean(vals)) if len(vals) >= 3 else None
        n = WIN_N[win]
        if len(sub) < n:
            return None
        vals = [r[key] for r in sub[-n:] if r.get(key) is not None]
        return float(np.mean(vals)) if len(vals) == n else None

    feat_names = set()
    for m in matches:
        hid, aid = m.get('homeID'), m.get('awayID')
        f = {}
        for who, tid in (('h', hid), ('a', aid)):
            recs = hist.get(tid, [])
            for st in stats:
                for w in WINDOWS:
                    ff = f'{who}_{st}_for_{w}'
                    fa = f'{who}_{st}_against_{w}'
                    f[ff] = roll(recs, st + '_for', w)
                    f[fa] = roll(recs, st + '_against', w)
                    feat_names.add(ff); feat_names.add(fa)
                # explicit venue split of the team's OWN 'for' rate (w5, std)
                for w in ('w5', 'std'):
                    fh = f'{who}_{st}_home_{w}'
                    fw = f'{who}_{st}_away_{w}'
                    f[fh] = roll_venue(recs, st + '_for', w, True)
                    f[fw] = roll_venue(recs, st + '_for', w, False)
                    feat_names.add(fh); feat_names.add(fw)
        # referee expanding rates (look-ahead-free), competition fallback
        ref = m.get('refereeID'); comp = m.get('competition_id')
        if ref is not None and ref_acc[ref][0] >= 5:
            f['ref_card_rate'] = ref_acc[ref][1] / ref_acc[ref][0]
            f['ref_foul_rate'] = ref_acc[ref][2] / ref_acc[ref][0]
        else:
            la = league_ref[comp]
            f['ref_card_rate'] = (la[1]/la[0]) if la[0] >= 10 else 3.6
            f['ref_foul_rate'] = (la[2]/la[0]) if la[0] >= 10 else 22.0
        feat_names.add('ref_card_rate'); feat_names.add('ref_foul_rate')
        m['_f'] = f

        # ── update histories AFTER emitting (PIT) ──
        hrec, arec = {'is_home': True}, {'is_home': False}
        for st, (hf, af) in base_stats.items():
            hv, av = _val(m, hf), _val(m, af)
            hrec[st + '_for'] = hv; hrec[st + '_against'] = av
            arec[st + '_for'] = av; arec[st + '_against'] = hv
        if hid is not None:
            hist[hid].append(hrec)
        if aid is not None:
            hist[aid].append(arec)
        # referee/league accumulators
        ya = _val(m, 'team_a_yellow_cards') or 0; yb = _val(m, 'team_b_yellow_cards') or 0
        ra = _val(m, 'team_a_red_cards') or 0; rb = _val(m, 'team_b_red_cards') or 0
        fa_ = _val(m, 'team_a_fouls') or 0; fb = _val(m, 'team_b_fouls') or 0
        cards = ya + yb + ra + rb; fouls = fa_ + fb
        if ref is not None:
            ref_acc[ref][0] += 1; ref_acc[ref][1] += cards; ref_acc[ref][2] += fouls
        league_ref[comp][0] += 1; league_ref[comp][1] += cards; league_ref[comp][2] += fouls

    return sorted(feat_names)
