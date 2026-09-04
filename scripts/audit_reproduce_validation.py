"""
AUDIT 1 + 2 — Reproduce the cross-league validation on CACHED data (zero API) and
test whether its "features" are same-match (post-match) statistics of the fixture
being predicted (leakage), which would inflate the +6.8%/+9.6% BSS figures.

Diagnose only. No model/scope/ledger changes. Network is HARD-BLOCKED: the client
is monkeypatched so any uncached fetch raises instead of calling out.

What it does, per cached league-season:
  1. Reproduce run_robustness_check.run_walk_forward EXACTLY (import its functions),
     recording corners/cards BSS-vs-naive. -> does the published-style skill reproduce?
  2. Structural leakage check: are the model's feature fields the SAME-MATCH final
     stats of the fixture? Show contemporaneous corr(shots_total, total_corners) and
     corr(fouls_total, total_cards) within the match (should be high if leaked).
  3. Counterfactual: re-run the SAME walk-forward but ZERO OUT the same-match feature
     fields (so the model can only use intercept + team effects). If BSS collapses
     to ~0, the "skill" was coming from same-match leakage, not point-in-time form.
"""
import os, sys, json, glob
import numpy as np

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

# ── Hard-block network BEFORE importing the client, to guarantee zero API ─────
import src.research.footystats.client as fsclient

_ORIG_REQUEST = fsclient.FootyStatsResearchClient._request
def _blocked_request(self, endpoint, params=None, **kw):
    # Allow ONLY if it resolves from cache; else raise (never hit network).
    request_params = dict(params or {})
    request_params.setdefault("key", "BLOCKED")
    ck = self._cache_key(endpoint, request_params)
    cached = self._cache_get(ck)
    if cached is not None:
        return cached
    raise RuntimeError(f"ZERO-API GUARD: uncached request blocked: {endpoint} {params}")
fsclient.FootyStatsResearchClient._request = _blocked_request

import run_robustness_check as rc
from src.research.footystats.normalizer import MatchNormalizer

CACHE = "/home/ubuntu/.cache/footystats_research"


def cached_season_ids():
    ids = []
    for p in glob.glob(f"{CACHE}/league-matches_*season_id:_*.json"):
        # filename like league-matches_{...season_id:_10505}.json
        import re
        m = re.search(r"season_id:_(\d+)", p)
        if m:
            ids.append(int(m.group(1)))
    return sorted(set(ids))


def contemporaneous_corr(features):
    """Within-match Pearson corr of the leaked feature families vs the targets."""
    shots = []; corners = []; fouls = []; cards = []
    for f in features:
        tc = f.get("total_corners")
        sh = None
        if f.get("shots_home") is not None and f.get("shots_away") is not None:
            sh = f["shots_home"] + f["shots_away"]
        if tc is not None and tc >= 0 and sh is not None:
            shots.append(sh); corners.append(tc)
        tk = f.get("total_cards")
        fo = None
        if f.get("fouls_home") is not None and f.get("fouls_away") is not None:
            fo = f["fouls_home"] + f["fouls_away"]
        if tk is not None and tk >= 0 and fo is not None:
            fouls.append(fo); cards.append(tk)
    out = {}
    if len(shots) > 30:
        out["corr_sameMatch_shots_vs_corners"] = float(np.corrcoef(shots, corners)[0, 1])
        out["n_shots"] = len(shots)
    if len(fouls) > 30:
        out["corr_sameMatch_fouls_vs_cards"] = float(np.corrcoef(fouls, cards)[0, 1])
        out["n_fouls"] = len(fouls)
    return out


def zero_out_samematch_features(features, model_feature_fields):
    """Return a copy of features with every model feature field set to 0.0 (so the
    model cannot read same-match stats; only intercept + team effects remain)."""
    stripped = []
    for f in features:
        g = dict(f)
        for k in model_feature_fields:
            if k in g:
                g[k] = 0.0
        stripped.append(g)
    return stripped


def main():
    print("AUDIT 1+2 — reproduce cross-league validation on CACHED data (zero API)")
    print(f"model feature fields (corners): {rc.create_corners_model().__dict__.get('_feature_fields')}")
    print(f"model feature fields (cards):   {rc.create_cards_model().__dict__.get('_feature_fields')}")
    print()

    client = fsclient.FootyStatsResearchClient(api_key="BLOCKED", cache_dir=rc.CACHE_DIR)
    normalizer = MatchNormalizer()

    sids = cached_season_ids()
    print(f"cached season files: {len(sids)}")

    corners_field_set = rc.create_corners_model()._CountRegressionModel__dict__ if False else None
    # feature fields for zeroing
    cm = rc.create_corners_model(); km = rc.create_cards_model()
    corners_feats = list(cm._feature_fields)
    cards_feats = list(km._feature_fields)
    all_feat_fields = sorted(set(corners_feats + cards_feats))

    rows = []
    n_done = 0
    for sid in sids:
        if n_done >= 8:   # a representative sample of league-seasons is enough to diagnose
            break
        try:
            features, notes = rc.load_season_features(client, normalizer, sid)
        except Exception as e:
            print(f"  season {sid}: load failed ({str(e)[:50]})")
            continue
        if len(features) < rc.MIN_TRAIN + 30:
            continue

        # (1) reproduce the published-style walk-forward with SAME-MATCH features
        wf_leaked = rc.run_walk_forward(features)
        # (3) counterfactual: zero out same-match features
        stripped = zero_out_samematch_features(features, all_feat_fields)
        wf_stripped = rc.run_walk_forward(stripped)
        # (2) contemporaneous leakage correlations
        corr = contemporaneous_corr(features)

        if wf_leaked is None:
            continue
        row = {
            "season_id": sid, "n": len(features),
            "corners_bss_leaked": wf_leaked.get("corners_vs_naive_pct"),
            "corners_bss_stripped": (wf_stripped or {}).get("corners_vs_naive_pct"),
            "cards_bss_leaked": wf_leaked.get("cards_vs_naive_pct"),
            "cards_bss_stripped": (wf_stripped or {}).get("cards_vs_naive_pct"),
            **corr,
        }
        rows.append(row)
        n_done += 1
        print(f"  season {sid}: n={len(features):4d}  "
              f"corners BSS leaked={_f(row['corners_bss_leaked'])} stripped={_f(row['corners_bss_stripped'])}  |  "
              f"cards BSS leaked={_f(row['cards_bss_leaked'])} stripped={_f(row['cards_bss_stripped'])}")
        if "corr_sameMatch_shots_vs_corners" in row:
            print(f"            same-match corr: shots->corners={row['corr_sameMatch_shots_vs_corners']:+.3f}  "
                  f"fouls->cards={row.get('corr_sameMatch_fouls_vs_cards', float('nan')):+.3f}")

    # ── Aggregate verdict ─────────────────────────────────────────────────────
    def mean(key):
        vals = [r[key] for r in rows if r.get(key) is not None]
        return float(np.mean(vals)) if vals else None

    print("\n" + "=" * 78)
    print("AGGREGATE (sampled cached league-seasons)")
    print("=" * 78)
    print(f"  corners BSS  leaked features : mean {_f(mean('corners_bss_leaked'))}")
    print(f"  corners BSS  same-match zeroed: mean {_f(mean('corners_bss_stripped'))}")
    print(f"  cards   BSS  leaked features : mean {_f(mean('cards_bss_leaked'))}")
    print(f"  cards   BSS  same-match zeroed: mean {_f(mean('cards_bss_stripped'))}")
    print(f"  same-match corr shots->corners: mean {_f2(mean('corr_sameMatch_shots_vs_corners'))}")
    print(f"  same-match corr fouls->cards  : mean {_f2(mean('corr_sameMatch_fouls_vs_cards'))}")
    json.dump(rows, open("/home/ubuntu/data/results/audit_reproduce_validation.json", "w"), indent=2)
    print("\nsaved: /home/ubuntu/data/results/audit_reproduce_validation.json")


def _f(x):
    return "N/A" if x is None else f"{x:+.2f}%"

def _f2(x):
    return "N/A" if x is None else f"{x:+.3f}"


if __name__ == "__main__":
    main()
