"""Offline: report FootyStats crosswalk join rate for the 200-match slice.
Join = mapped(home)+mapped(away)+date within +-1 day to a FootyStats corpus match.
This is a REPORTING metric only; the analysis runs on TheStatsAPI data regardless."""
import json, glob, os
from datetime import datetime, timezone

CACHE = "/home/ubuntu/data/thestatsapi/championship"
CROSSWALK = "/home/ubuntu/data/mapping/team_crosswalk.json"
CORPUS = "/home/ubuntu/data/discovery/corpus"
SEASON = "sn_3064530"


def load_crosswalk():
    d = json.load(open(CROSSWALK))
    m = {}
    for league, teams in d.get("leagues", {}).items():
        for t in teams:
            if t.get("confidence", 0) >= 0.9:
                m.setdefault(t["thestats_id"], t["footystats_name"])
    return m


def load_corpus_index():
    idx = {}  # (home_name, away_name) -> list of date_unix
    n = 0
    for cf in glob.glob(f"{CORPUS}/league-matches_*.json"):
        data = json.load(open(cf))
        for mm in data.get("data", []):
            n += 1
            key = (mm.get("home_name", ""), mm.get("away_name", ""))
            idx.setdefault(key, []).append(mm.get("date_unix", 0))
    return idx, n


def main():
    xwalk = load_crosswalk()
    sel = json.load(open(f"{CACHE}/_selected_balanced_{SEASON}.json"))["selected"]
    corpus_idx, corpus_n = load_corpus_index()

    mapped_both = 0
    joined = 0
    for m in sel:
        hn = xwalk.get(m["home_id"])
        an = xwalk.get(m["away_id"])
        if hn and an:
            mapped_both += 1
            du = int(datetime.fromisoformat(m["date"].replace("Z", "+00:00")).timestamp())
            cand = corpus_idx.get((hn, an), [])
            if any(abs(c - du) <= 86400 for c in cand):
                joined += 1

    n = len(sel)
    print(f"selected matches: {n}")
    print(f"both teams mapped in crosswalk (conf>=0.9): {mapped_both}/{n}")
    print(f"joined to FootyStats corpus (mapped pair + date +-1d): {joined}/{n}")
    print(f"(FootyStats corpus size: {corpus_n} matches across cached leagues/seasons)")
    print("NOTE: FootyStats corpus is EPL/La Liga 24/25-era; 25/26 Championship is")
    print("      not expected to be present. Join rate is reported for completeness;")
    print("      the Championship analysis uses TheStatsAPI data directly and does")
    print("      NOT depend on this join.")
    out = {"n_selected": n, "both_mapped": mapped_both, "joined": joined,
           "corpus_n": corpus_n}
    json.dump(out, open(f"{CACHE}/_join_rate_{SEASON}.json", "w"), indent=2)


if __name__ == "__main__":
    main()
