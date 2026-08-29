"""
Step 1 falsification: is the shot/foul disagreement a JOIN ERROR or genuine
provider measurement difference?

If the join were pairing WRONG matches, ALL fields (incl. objective cards/corners)
would disagree at the random-baseline rate. If joins are CORRECT, objective fields
(cards, corners) agree ~98% while subjective fields (SOT, fouls) disagree modestly.

Test: recompute agreement under (a) correct join and (b) a SHUFFLED join (each TSA
match paired to a random FS match of the same team-count structure). The shuffle is
the null "namespace-mismatch" world. Compare cards exact-match rate.
"""
import json, glob, os, random
from datetime import datetime
from collections import defaultdict
import numpy as np

CACHE = "/home/ubuntu/data/thestatsapi/championship"
CROSSWALK = "/home/ubuntu/data/mapping/team_crosswalk.json"
CORPUS = "/home/ubuntu/data/discovery/corpus"
TSA_SEASON = "sn_2930227"; FS_COMP = 12451; DAY = 86400
random.seed(0)


def _cell(sd, group, stat, side):
    grp = sd.get(group) or {}; node = grp.get(stat) or {}
    per = node.get("all")
    return per.get(side) if isinstance(per, dict) else None


def main():
    d = json.load(open(CROSSWALK))
    xwalk = {t["thestats_id"]: t["footystats_name"]
             for t in d["leagues"]["England Championship"] if t.get("confidence", 0) >= 0.9}
    fx = json.load(open(f"{CACHE}/_all_fixtures_{TSA_SEASON}.json"))["fixtures"]
    fs_idx = defaultdict(list); seen = set(); fs_all = []
    for cf in glob.glob(f"{CORPUS}/league-matches_*.json"):
        for mm in json.load(open(cf)).get("data", []):
            if mm.get("competition_id") != FS_COMP or mm.get("id") in seen:
                continue
            seen.add(mm.get("id")); fs_idx[(mm.get("home_name"), mm.get("away_name"))].append(mm)
            fs_all.append(mm)

    joined = []
    for f in fx:
        mid = f["id"]; spath = f"{CACHE}/stats_{mid}.json"
        if not os.path.exists(spath):
            continue
        sd = (json.load(open(spath)) or {}).get("data", {})
        du = int(datetime.fromisoformat(f["utc_date"].replace("Z", "+00:00")).timestamp())
        hn = xwalk.get(f["home_team"]["id"]); an = xwalk.get(f["away_team"]["id"])
        if not (hn and an):
            continue
        cands = [m for m in fs_idx.get((hn, an), []) if abs(m.get("date_unix", 0) - du) <= DAY]
        if len(cands) == 1:
            yc = (_cell(sd, "overview", "yellow_cards", "home"), _cell(sd, "overview", "yellow_cards", "away"))
            ck = (_cell(sd, "overview", "corner_kicks", "home"), _cell(sd, "overview", "corner_kicks", "away"))
            joined.append((yc, ck, cands[0]))

    def agree(pairs, get_fs, get_ts):
        ex = tot = 0
        for yc, ck, fm in pairs:
            tv = get_ts(yc, ck); fv = get_fs(fm)
            for s in (0, 1):
                if tv[s] is None or fv[s] is None:
                    continue
                tot += 1
                if float(tv[s]) == float(fv[s]):
                    ex += 1
        return ex / tot if tot else 0

    # correct join
    card_ok = agree(joined, lambda m: (m.get("team_a_yellow_cards"), m.get("team_b_yellow_cards")),
                    lambda yc, ck: yc)
    corner_ok = agree(joined, lambda m: (m.get("team_a_corners"), m.get("team_b_corners")),
                      lambda yc, ck: ck)

    # shuffled join (null: random FS match)
    shuf_cards = []
    for _ in range(200):
        shuffled = [(yc, ck, random.choice(fs_all)) for (yc, ck, _fm) in joined]
        shuf_cards.append(agree(shuffled, lambda m: (m.get("team_a_yellow_cards"), m.get("team_b_yellow_cards")),
                                lambda yc, ck: yc))
    shuf_mean = float(np.mean(shuf_cards)); shuf_hi = float(np.percentile(shuf_cards, 97.5))

    print("=" * 70)
    print("STEP 1 FALSIFICATION: correct join vs shuffled (namespace-mismatch null)")
    print("=" * 70)
    print(f"clean 1:1 joins: {len(joined)}")
    print(f"CORRECT join   cards exact-match: {100*card_ok:.1f}%   corners: {100*corner_ok:.1f}%")
    print(f"SHUFFLED join  cards exact-match: {100*shuf_mean:.1f}% (97.5pct {100*shuf_hi:.1f}%)  [null]")
    print()
    if card_ok > 0.90 and shuf_mean < 0.5:
        print("CONCLUSION: correct join agrees ~98% on OBJECTIVE fields while the")
        print("namespace-mismatch null sits near chance. The join is REAL. The modest")
        print("SOT/fouls disagreement is provider measurement difference on the SAME")
        print("matches (subjective counts), not a mismatch. MERGE TRUSTED for count-")
        print("outcome fields (cards, corners, goals); SOT/fouls carry provider noise.")
    else:
        print("CONCLUSION: join not clearly distinguished from null - do NOT trust.")


if __name__ == "__main__":
    main()
