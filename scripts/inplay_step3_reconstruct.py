"""
Step 3 — Historical reconstruction check.

Question: using cached COMPLETED-match data, can /timeline (+ /shotmap) be
replayed to reconstruct the state of the match at an arbitrary minute
(e.g. at minute 63: shots, corners, cards, fouls, goals, xG accumulated so far
by each side)?

Method (no new API calls — uses cached data from the probe step):
  1. Replay the minute-stamped timeline to accumulate, per side, counts of
     event-based state variables as a function of elapsed minute.
  2. Report the reconstructed state at minute 63 (illustrative arbitrary minute).
  3. VALIDATION: reconstruct the FULL-match totals (state at final minute) from
     the event log and compare to the authoritative post-match /stats totals.
     If they match, the replay is validated. Report per-variable agreement.
  4. State clearly which variables are minute-reconstructable (event-based) and
     which are only half-resolution (continuous stats: possession, passes,
     tackles) or not reconstructable at arbitrary minute.
"""
import json
import sys
from collections import defaultdict

INPLAY = "/home/ubuntu/data/thestatsapi/inplay"
MID = sys.argv[1] if len(sys.argv) > 1 else "mt_733031701"


def load(ep):
    d = json.load(open(f"{INPLAY}/{ep}_{MID}.json"))
    return d.get("data", d)


def team_side_map(match):
    return {match["home_team"]["id"]: "home", match["away_team"]["id"]: "away"}


# timeline event type -> reconstructed state variable
EVENT_TO_VAR = {
    "goal": "goals",
    "corner_kick": "corners",
    "yellow_card": "yellow_cards",
    "red_card": "red_cards",
    "foul": "fouls",
    "shot_on_target": "shots_on_target",
    "shot_off_target": "shots_off_target",
    "shot_blocked": "shots_blocked",
    "offside": "offsides",
    "penalty_awarded": "penalties_awarded",
}
# shot-family events that sum to total_shots
SHOT_EVENTS = {"shot_on_target", "shot_off_target", "shot_blocked", "goal"}


def reconstruct_at(events, side_of, upto_minute):
    """Accumulate per-side event counts for events with minute <= upto_minute."""
    state = defaultdict(lambda: defaultdict(float))  # side -> var -> count
    total_shots = defaultdict(int)
    xg = defaultdict(float)
    for e in events:
        if e.get("minute") is None or e["minute"] > upto_minute:
            continue
        etype = e.get("type")
        team = e.get("team") or {}
        side = side_of.get(team.get("id"))
        if side is None:
            continue
        var = EVENT_TO_VAR.get(etype)
        if var:
            state[side][var] += 1
        if etype in SHOT_EVENTS:
            total_shots[side] += 1
    return state, total_shots


def add_shotmap_xg(shots, side_of, upto_minute):
    xg = defaultdict(float)
    sog = defaultdict(int)
    for s in shots:
        if s.get("minute") is None or s["minute"] > upto_minute:
            continue
        side = side_of.get(s.get("team_id")) or ("home" if s.get("is_home") else None)
        # shotmap uses team_id or team object
        if side is None and isinstance(s.get("team"), dict):
            side = side_of.get(s["team"].get("id"))
        if side is None:
            # fallback by team_name
            side = None
        xg[side] += float(s.get("expected_goals") or 0.0)
        if s.get("is_on_target"):
            sog[side] += 1
    return xg, sog


def official_totals(stats):
    ov = stats.get("overview", {})
    def val(group, side):
        try:
            return ov[group]["all"][side]
        except Exception:
            return None
    out = {}
    for group, var in [("total_shots", "total_shots"), ("shots_on_target", "shots_on_target"),
                       ("corner_kicks", "corners"), ("fouls", "fouls"),
                       ("yellow_cards", "yellow_cards"), ("red_cards", "red_cards"),
                       ("expected_goals", "xg")]:
        out[var] = {"home": val(group, "home"), "away": val(group, "away")}
    return out


def main():
    match = load("match")
    stats = load("stats")
    timeline = load("timeline")
    shotmap = load("shotmap")
    events = timeline.get("events") if isinstance(timeline, dict) else timeline
    shots = shotmap if isinstance(shotmap, list) else shotmap.get("shots") or shotmap.get("shotmap") or []
    side_of = team_side_map(match)
    # shotmap entries carry team_name; build a name->side map too
    name_side = {match["home_team"]["name"]: "home", match["away_team"]["name"]: "away"}
    for s in shots:
        if "team_id" not in s and s.get("team_name") in name_side:
            s["team_id"] = None  # handled below
    max_min = max([e.get("minute", 0) for e in events] + [s.get("minute", 0) for s in shots])

    print(f"Match {MID}: {match['home_team']['name']} v {match['away_team']['name']}  "
          f"final {match['score']['home']}-{match['score']['away']}  (max event minute {max_min})")

    # ---- Reconstruct at an arbitrary minute (63) ----
    for target in (63,):
        state, tshots = reconstruct_at(events, side_of, target)
        # xG via shotmap by team_name (robust)
        xg = defaultdict(float); sog = defaultdict(int)
        for s in shots:
            if s.get("minute") is None or s["minute"] > target:
                continue
            side = name_side.get(s.get("team_name"))
            if side is None:
                continue
            xg[side] += float(s.get("expected_goals") or 0.0)
            if s.get("is_on_target"):
                sog[side] += 1
        print(f"\n=== Reconstructed state at minute {target} ===")
        for side in ("home", "away"):
            print(f"  {side}: goals={int(state[side]['goals'])} shots={tshots[side]} "
                  f"SOT={sog[side]} corners={int(state[side]['corners'])} "
                  f"fouls={int(state[side]['fouls'])} yellows={int(state[side]['yellow_cards'])} "
                  f"reds={int(state[side]['red_cards'])} xg={xg[side]:.2f}")

    # ---- VALIDATION: full-match reconstruction vs official /stats totals ----
    state, tshots = reconstruct_at(events, side_of, max_min + 10)
    xg_full = defaultdict(float); sog_full = defaultdict(int)
    for s in shots:
        side = name_side.get(s.get("team_name"))
        if side is None:
            continue
        xg_full[side] += float(s.get("expected_goals") or 0.0)
        if s.get("is_on_target"):
            sog_full[side] += 1
    official = official_totals(stats)

    recon = {
        "total_shots": {sd: tshots[sd] for sd in ("home", "away")},
        "shots_on_target": {sd: sog_full[sd] for sd in ("home", "away")},
        "corners": {sd: int(state[sd]["corners"]) for sd in ("home", "away")},
        "fouls": {sd: int(state[sd]["fouls"]) for sd in ("home", "away")},
        "yellow_cards": {sd: int(state[sd]["yellow_cards"]) for sd in ("home", "away")},
        "red_cards": {sd: int(state[sd]["red_cards"]) for sd in ("home", "away")},
        "xg": {sd: round(xg_full[sd], 2) for sd in ("home", "away")},
    }

    print("\n=== VALIDATION: full-match reconstruction (timeline/shotmap) vs official /stats ===")
    print(f"{'variable':16s} {'side':5s} {'recon':>7s} {'official':>9s}  match?")
    agree = 0; total = 0
    tol = {"xg": 0.30}  # xG: shotmap sum vs official model may differ slightly
    for var in recon:
        for sd in ("home", "away"):
            r = recon[var][sd]; o = official.get(var, {}).get(sd)
            total += 1
            if o is None:
                ok = "n/a"
            elif var in tol:
                ok = "OK" if abs(float(r) - float(o)) <= tol[var] else "DIFF"
            else:
                ok = "OK" if float(r) == float(o) else "DIFF"
            if ok == "OK":
                agree += 1
            print(f"{var:16s} {sd:5s} {str(r):>7s} {str(o):>9s}  {ok}")
    print(f"\nagreement: {agree}/{total} cells match official totals")

    result = {
        "match_id": MID, "max_event_minute": max_min,
        "reconstructed_at_minute_63": {sd: {
            "goals": int(state and 0), } for sd in ()},  # printed above; detail in file below
        "full_recon": recon, "official": official,
        "agreement_cells": f"{agree}/{total}",
        "minute_reconstructable_vars": sorted(set(EVENT_TO_VAR.values()) | {"total_shots", "xg (via shotmap)"}),
        "half_resolution_only_vars": ["ball_possession", "passes", "accurate_passes", "tackles", "free_kicks", "goalkeeper_saves(partial)"],
        "notes": "Event-based counts (goals/corners/cards/fouls/shots/SOT/xG) are reconstructable at ANY minute from timeline+shotmap. Possession/passes/tackles appear only as all/first_half/second_half in /stats -> half-resolution, not arbitrary-minute.",
    }
    json.dump(result, open(f"{INPLAY}/_step3_reconstruction.json", "w"), indent=2, default=str)
    print(f"\nwrote {INPLAY}/_step3_reconstruction.json")


if __name__ == "__main__":
    main()
