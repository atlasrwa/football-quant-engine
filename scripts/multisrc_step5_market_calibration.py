"""
STEP 5 (model-independent) — Bet365 market calibration for Ligue 2 & La Liga 2.

Zero FDR survivors came out of Step 4, so there is nothing to EV-test at the
candidate level. This module reports the part of Step 5 that stands on its own:
the MARKET's own BSS vs the naive base-rate predictor, per league/market/line,
with overround. It also documents ODDS-COVERAGE GAPS explicitly (do not substitute).

Balanced odds subsets (per-team balanced, calendar-spread), most recent complete
season per league: Ligue 2 108 matches (12/team), La Liga 2 110 (10/team).

Method mirrors championship_step34_analysis market-calibration: vig removed
multiplicatively, market implied P(over) vs realized outcome, BSS = 1 - BS/BS_naive.
Benchmark caveat: Bet365 is a comparatively SHARP book; any "market ~ naive" result
is a conservative bound on softer books (e.g. bc.game). Not overstated (untested
without bc.game odds), but flagged.
"""
import json, glob, os
import numpy as np
import sys
sys.path.insert(0, os.path.dirname(__file__))
import ev_test_metrics_vs_bet365 as ev
import multisrc_corpus as corpus

CACHE = "/home/ubuntu/data/thestatsapi/championship"
OUT = "/home/ubuntu/data/results/multisrc_market_calibration.json"

SEASON = {"ligue2": "sn_3064056", "laliga2": "sn_8437950"}
COMP_MARKETS = {"total_goals": ["0.5","1.5","2.5","3.5","4.5","5.5"],
                "total_cards": ["2.5","3.5","4.5","5.5"],
                "match_corners": ["8.5","9.5","10.5","11.5","12.5"]}


def actual_for(m, market):
    if market == "total_goals":
        return m["overallGoalCount"]
    if market == "total_cards":
        if m["team_a_yellow_cards"] is None or m["team_b_yellow_cards"] is None:
            return None
        return ((m["team_a_yellow_cards"] or 0) + (m["team_b_yellow_cards"] or 0)
                + (m["team_a_red_cards"] or 0) + (m["team_b_red_cards"] or 0))
    if market == "match_corners":
        pair = m["_rich"].get("corner_kicks")
        return None if pair is None else (pair[0] + pair[1])
    return None


def load_odds(tag, mid):
    p = f"{CACHE}/{tag}_odds_{mid}.json"
    if not os.path.exists(p):
        return None
    d = json.load(open(p))
    for b in d.get("data", {}).get("bookmakers", []):
        if str(b.get("bookmaker", "")).lower().startswith("bet365"):
            return b.get("markets", {})
    return None


def main():
    out = {"leagues": {}, "benchmark_caveat":
           "Bet365 is a comparatively sharp book; market-BSS~0 is a CONSERVATIVE "
           "lower bound vs softer books (e.g. bc.game, untested here). A candidate "
           "that merely ties Bet365 could plausibly be +EV at a softer book."}
    for tag, sid in SEASON.items():
        matches = {m["match_id"]: m for m in corpus.load_season(tag, sid)}
        ids = json.load(open(f"{CACHE}/_odds_ids_{tag}.json"))
        odds = {mid: load_odds(tag, mid) for mid in ids}
        odds = {k: v for k, v in odds.items() if v}
        print(f"\n{'='*72}\n{tag} {sid}: {len(odds)} matches with Bet365 odds\n{'='*72}")
        lg = {"season": sid, "n_odds": len(odds), "markets": {},
              "market_availability": {}}
        # market availability count
        for market in COMP_MARKETS:
            present = sum(1 for mk in odds.values() if market in mk and mk[market])
            lg["market_availability"][market] = present
        print("  market availability:", lg["market_availability"])

        for market, lines in COMP_MARKETS.items():
            lg["markets"][market] = {}
            for line in lines:
                L = float(line)
                fair, outs, orrs = [], [], []
                for mid, mk in odds.items():
                    ld = mk.get(market, {}).get(line)
                    act = actual_for(matches.get(mid, {}), market) if mid in matches else None
                    if not ld or act is None:
                        continue
                    try:
                        o = float(ld["over"]["last_seen"]); u = float(ld["under"]["last_seen"])
                    except (KeyError, TypeError, ValueError):
                        continue
                    if o <= 1 or u <= 1:
                        continue
                    fo, _ = ev.devig_multiplicative(o, u)
                    fair.append(float(fo)); outs.append(1.0 if act > L else 0.0)
                    orrs.append(ev.compute_overround(o, u))
                n = len(fair)
                if n < 10:
                    lg["markets"][market][line] = {"n": n, "status": "insufficient/absent"}
                    continue
                fair = np.array(fair); outs = np.array(outs)
                bs = np.mean((fair - outs) ** 2)
                base = np.mean(outs)
                bn = np.mean((base - outs) ** 2)
                mbss = None if bn == 0 else (1 - bs / bn)
                lg["markets"][market][line] = {
                    "n": n, "base_rate_over": float(base),
                    "overround_mean_pct": float(np.mean(orrs) * 100),
                    "market_bss_vs_naive_pct": None if mbss is None else float(mbss * 100),
                    "market_mean_implied_over": float(np.mean(fair)),
                }
                r = lg["markets"][market][line]
                print(f"  {market:14s}@{line:>4}: n={n:3d} baseOver={base:.2f} "
                      f"orr={np.mean(orrs)*100:4.1f}% "
                      f"mktBSS_vs_naive={'n/a' if mbss is None else format(mbss*100,'+6.2f')+'%'}")
        out["leagues"][tag] = lg

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(out, open(OUT, "w"), indent=2, default=str)
    print(f"\nsaved: {OUT}")
    # Gap summary
    print("\nODDS-COVERAGE GAPS:")
    for tag in SEASON:
        av = out["leagues"][tag]["market_availability"]
        print(f"  {tag}: total_cards market present on {av.get('total_cards',0)} matches "
              f"(goals {av.get('total_goals',0)}, corners {av.get('match_corners',0)})")


if __name__ == "__main__":
    main()
