"""
Adapter: TheStatsAPI /stats + fixture score  ->  FootyStats-schema match dict.

This lets the EXACT existing model pipeline (scripts/ev_test_metrics_vs_bet365.py)
consume Championship data with NO change to the model, metrics, features, fit, or
shrinkage. Only the data source is adapted. Null stats -> None (model treats as 0
for cards/red via `or 0`; rolling-stat helper drops matches with missing features).

Produced dict fields (only those the 7 metrics + shrinkage read):
  home_name, away_name, date_unix,
  team_a_yellow_cards, team_b_yellow_cards, team_a_red_cards, team_b_red_cards,
  team_a_fouls, team_b_fouls, team_a_shotsOnTarget, team_b_shotsOnTarget,
  team_a_xg, team_b_xg, team_a_2h_cards, team_b_2h_cards,
  homeGoalCount, awayGoalCount, overallGoalCount,
  match_id, competition_id, refereeID (for characterization)
"""
import json, glob, os
from datetime import datetime

CACHE = "/home/ubuntu/data/thestatsapi/championship"
SEASON = "sn_3064530"


def _cell(stats_data, group, stat, period, side):
    grp = stats_data.get(group) or {}
    if group == "np_expected_goals":
        node = stats_data.get("np_expected_goals") or {}
    else:
        node = grp.get(stat) or {}
    per = node.get(period)
    if not isinstance(per, dict):
        return None
    return per.get(side)


def adapt_match(fixture, stats_json):
    """fixture: dict from selection (has id/date/home/away/score_home/score_away).
    stats_json: parsed /stats response (or None). Returns FootyStats-schema dict."""
    sd = (stats_json or {}).get("data", {})
    dt = datetime.fromisoformat(fixture["date"].replace("Z", "+00:00"))
    date_unix = int(dt.timestamp())

    def ov(stat, period, side):
        return _cell(sd, "overview", stat, period, side)

    yc_h = ov("yellow_cards", "all", "home")
    yc_a = ov("yellow_cards", "all", "away")
    rc_h = ov("red_cards", "all", "home")
    rc_a = ov("red_cards", "all", "away")
    fo_h = ov("fouls", "all", "home")
    fo_a = ov("fouls", "all", "away")
    sot_h = ov("shots_on_target", "all", "home")
    sot_a = ov("shots_on_target", "all", "away")
    xg_h = ov("expected_goals", "all", "home")
    xg_a = ov("expected_goals", "all", "away")
    yc2h_h = ov("yellow_cards", "second_half", "home")
    yc2h_a = ov("yellow_cards", "second_half", "away")

    gh = fixture.get("score_home")
    ga = fixture.get("score_away")
    total_goals = (gh + ga) if (gh is not None and ga is not None) else None

    return {
        "match_id": fixture["id"],
        "home_name": fixture["home"],
        "away_name": fixture["away"],
        "home_id": fixture["home_id"],
        "away_id": fixture["away_id"],
        "date_unix": date_unix,
        # cards (yellow + red per team). Red null -> 0 to mirror model's `or 0`.
        "team_a_yellow_cards": yc_h,
        "team_b_yellow_cards": yc_a,
        "team_a_red_cards": rc_h if rc_h is not None else 0,
        "team_b_red_cards": rc_a if rc_a is not None else 0,
        "team_a_fouls": fo_h,
        "team_b_fouls": fo_a,
        "team_a_shotsOnTarget": sot_h,
        "team_b_shotsOnTarget": sot_a,
        "team_a_xg": xg_h,
        "team_b_xg": xg_a,
        "team_a_2h_cards": yc2h_h,
        "team_b_2h_cards": yc2h_a,
        "homeGoalCount": gh,
        "awayGoalCount": ga,
        "overallGoalCount": total_goals,
        # richer fields for new-field candidates (all-period totals, home/away)
        "_rich": _rich_fields(sd),
    }


def _rich_fields(sd):
    """Extract the richer TheStatsAPI fields (home/away all-period) for new-field
    candidate metrics. Returns dict of name -> (home, away) or None."""
    def grab(group, stat):
        h = _cell(sd, group, stat, "all", "home")
        a = _cell(sd, group, stat, "all", "away")
        return (h, a) if (h is not None and a is not None) else None
    return {
        "corner_kicks": grab("overview", "corner_kicks"),
        "big_chances": grab("overview", "big_chances"),
        "big_chances_missed": grab("attack", "big_chances_missed"),
        "touches_in_penalty_area": grab("attack", "touches_in_penalty_area"),
        "final_third_entries": grab("passes", "final_third_entries"),
        "accurate_crosses": grab("passes", "accurate_crosses"),
        "tackles": grab("defending", "tackles"),
        "interceptions": grab("defending", "interceptions"),
        "clearances": grab("defending", "clearances"),
        "ball_recoveries": grab("defending", "ball_recoveries"),
        "np_expected_goals": (
            (_cell(sd, "np_expected_goals", None, "all", "home"),
             _cell(sd, "np_expected_goals", None, "all", "away"))
            if _cell(sd, "np_expected_goals", None, "all", "home") is not None else None),
        "fouls": grab("overview", "fouls"),
        "shots_on_target": grab("overview", "shots_on_target"),
    }


def load_adapted_matches():
    """Load all selected Championship matches as adapted FootyStats-schema dicts."""
    sel = json.load(open(f"{CACHE}/_selected_balanced_{SEASON}.json"))["selected"]
    out = []
    for fx in sel:
        spath = f"{CACHE}/stats_{fx['id']}.json"
        sj = json.load(open(spath)) if os.path.exists(spath) else None
        out.append(adapt_match(fx, sj))
    out.sort(key=lambda m: m["date_unix"])
    return out


if __name__ == "__main__":
    ms = load_adapted_matches()
    print(f"adapted {len(ms)} matches")
    ok_cards = sum(1 for m in ms if m['team_a_yellow_cards'] is not None and m['team_b_yellow_cards'] is not None)
    ok_goals = sum(1 for m in ms if m['overallGoalCount'] is not None)
    ok_xg = sum(1 for m in ms if m['team_a_xg'] is not None)
    ok_sot = sum(1 for m in ms if m['team_a_shotsOnTarget'] is not None)
    ok_2h = sum(1 for m in ms if m['team_a_2h_cards'] is not None)
    print(f"cards populated: {ok_cards}/{len(ms)}  goals: {ok_goals}  xg: {ok_xg}  sot: {ok_sot}  2h_cards: {ok_2h}")
    import statistics
    tc = [(m['team_a_yellow_cards'] or 0)+(m['team_b_yellow_cards'] or 0)+(m['team_a_red_cards'] or 0)+(m['team_b_red_cards'] or 0) for m in ms if m['team_a_yellow_cards'] is not None]
    tg = [m['overallGoalCount'] for m in ms if m['overallGoalCount'] is not None]
    print(f"mean total cards: {statistics.mean(tc):.2f}  mean total goals: {statistics.mean(tg):.2f}")
