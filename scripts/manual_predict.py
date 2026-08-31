#!/usr/bin/env python3
"""Manual (ad-hoc) prediction ledger — request a prediction + EV for ONE fixture.

For social content, demos, and curiosity — WITHOUT contaminating the pre-registered
Pilot C sample. Cherry-picking which fixtures get predicted is exactly the selection
bias pre-registration exists to prevent, so manual predictions live in a physically
separate ledger and are structurally invisible to every Pilot C analysis.

────────────────────────────────────────────────────────────────────────────────
HOW THE HARD SEPARATION IS ENFORCED IN CODE (not by convention)
────────────────────────────────────────────────────────────────────────────────
Pilot C's sample is enumerated ONLY through hardcoded literal filenames — there is no
directory glob over data/forward/*.jsonl anywhere in the pipeline:

  * scripts/pilotC_settle.py grades ONLY predictions in
    data/discovery/pilotC_forward_predictions.json, reveals ONLY against
    data/forward/pilotC_commitments.jsonl, and appends ONLY to
    data/discovery/pilotC_settled_log.json.
  * scripts/pilotC_forward_loop.py health report + _per_cell_settled_counts read ONLY
    those same pilotC_* paths.

This script writes to DIFFERENT literal files:
  * commitments -> data/forward/manual_commitments.jsonl   (own hash chain)
  * reveals     -> data/forward/manual_reveals.jsonl        (own hash chain)
  * predictions -> data/forward/manual_predictions.jsonl    (append-only record)
  * settled     -> data/forward/manual_settled_log.json
and every manual prediction_id uses the "manual:" namespace prefix, never "pilotC:".
Because no Pilot C reader references any of these names, a manual record cannot appear
in Pilot C's settled sample, per-cell counts toward 385, weeks-to-readout, or health
report. This is verified by tests/test_manual_exclusion.py.

The MODEL is reused exactly as it stands (same saved CV-selected hyperparameters, same
fit_full/predict_one) — no refit search, no retune, no substitution — so manual output
is directly comparable to the experiment's. This script MEASURES the model; it never
changes it.

────────────────────────────────────────────────────────────────────────────────
USAGE
────────────────────────────────────────────────────────────────────────────────
  # by teams + date (date optional; picks the nearest matching fixture)
  python scripts/manual_predict.py --home "Leeds" --away "Norwich" --date 2026-09-05

  # by fixture id
  python scripts/manual_predict.py --fixture-id mt_466259566

  # produce the prediction + EV but DO NOT commit (check before it goes on record)
  python scripts/manual_predict.py --fixture-id mt_466259566 --dry-run

  # settle a previously-committed manual fixture once it has finished
  python scripts/manual_predict.py --fixture-id mt_466259566 --settle

  # independently re-verify a committed manual prediction's hash + chain
  python scripts/manual_predict.py --verify-hash --fixture-id mt_466259566

  # who/when requested (recorded on the commitment for provenance)
  python scripts/manual_predict.py --fixture-id mt_466259566 --requested-by "alice"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, "/home/ubuntu")
sys.path.insert(0, "/home/ubuntu/scripts")

# Load .env so an interactive/cron run has the API key (same pattern as the loop).
_ENV_PATH = "/home/ubuntu/.env"
if os.path.exists(_ENV_PATH):
    with open(_ENV_PATH) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import pilotC_stat_mixer as mix
import pilotC_forward_predict as fp
from src.research.forward.attestation_ledger import (
    AttestationLedger, compute_commitment_hash,
)

# ── separate, manual-only artifacts (NEVER a pilotC_* filename) ──────────────
CH = "/home/ubuntu/data/thestatsapi/championship"
FIXTURE_LIST = f"{CH}/_pilotC_fixture_list.json"  # read-only source of fixtures/odds cache
MANUAL_COMMIT_LEDGER = "/home/ubuntu/data/forward/manual_commitments.jsonl"
MANUAL_REVEAL_LEDGER = "/home/ubuntu/data/forward/manual_reveals.jsonl"
MANUAL_PRED_LOG = "/home/ubuntu/data/forward/manual_predictions.jsonl"
MANUAL_SETTLED_LOG = "/home/ubuntu/data/forward/manual_settled_log.json"
# Manual-owned cache of the deterministically-fitted models (keyed on corpus+HP
# fingerprint). Not shared with Pilot C; only speeds up repeat manual runs.
MANUAL_MODEL_CACHE = "/home/ubuntu/data/forward/manual_model_cache_{fp}.pkl"

MANUAL_ID_PREFIX = "manual"  # id namespace: manual:{mid}:{market}:{line} — never "pilotC:"
STAT_MIXER_HP = "/home/ubuntu/data/discovery/pilotC_stat_mixer.json"
BOOKS = fp.BOOKS
PRIMARY_BOOK = fp.PRIMARY_BOOK
MKT_ODDSKEY = fp.MKT_ODDSKEY

# The 9 pre-registered market cells (identical set the model was built for). Mirrored
# from pilotC_forward_loop.PREREG_CELLS; used only to iterate markets, not to count
# toward Pilot C's target.
MANUAL_CELLS = [("goals", 1.5), ("goals", 2.5), ("goals", 3.5),
                ("corners", 8.5), ("corners", 9.5), ("corners", 10.5),
                ("cards", 3.5), ("cards", 4.5), ("btts", None)]

# Edge threshold (percentage points) above which a market is flagged as showing edge.
# Purely a display threshold for the ad-hoc summary; it changes nothing in the model.
EDGE_THRESHOLD_PP = float(os.environ.get("MANUAL_EDGE_THRESHOLD_PP", "3.0"))

# Hard per-run live-request cap (protects the monthly budget). 9 markets share one
# fixture, so odds are ~3 requests (one per book). 12 is generous headroom.
MANUAL_REQUEST_CAP = int(os.environ.get("MANUAL_REQUEST_CAP", "12"))

CAVEAT = (
    "CAVEAT: a single prediction demonstrates nothing about edge. Whether the model or "
    "the market is right cannot be determined from one fixture — that is what the "
    "pre-registered Pilot C sample is for. This is a measurement of the model on one "
    "fixture, not evidence the model works."
)


# ── helpers ──────────────────────────────────────────────────────────────────

def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _pred_id(mid, market, line):
    return f"{MANUAL_ID_PREFIX}:{mid}:{market}:{line}"


def _load_fixture_meta():
    if not os.path.exists(FIXTURE_LIST):
        return {}
    return json.load(open(FIXTURE_LIST)).get("meta", {})


def resolve_fixture(fixture_id=None, home=None, away=None, date=None):
    """Resolve a fixture to (mid, meta_row) from the known fixture universe.

    By id: direct lookup. By teams+date: match home/away (case-insensitive substring on
    either side) and, if a date is given, pick the fixture whose kickoff day matches;
    otherwise the nearest upcoming one. Returns (mid, row) or (None, reason).
    """
    meta = _load_fixture_meta()
    if fixture_id:
        row = meta.get(fixture_id)
        if row is None:
            return None, f"fixture id {fixture_id} not found in {FIXTURE_LIST}"
        return fixture_id, row

    if not home or not away:
        return None, "provide --fixture-id, or both --home and --away"

    hl, al = home.lower(), away.lower()
    target_day = None
    if date:
        try:
            target_day = datetime.fromisoformat(date).date()
        except Exception:
            return None, f"could not parse --date {date!r} (use YYYY-MM-DD)"

    cands = []
    for mid, row in meta.items():
        rh = str(row.get("home", "")).lower()
        ra = str(row.get("away", "")).lower()
        if (hl in rh or rh in hl) and (al in ra or ra in al):
            cands.append((mid, row))
    if not cands:
        return None, (f"no fixture in the universe matches home~{home!r} away~{away!r}. "
                      f"The fixture must already be in {FIXTURE_LIST} (run discovery/top-up "
                      f"to add upcoming fixtures).")

    if target_day is not None:
        same_day = [(mid, r) for mid, r in cands
                    if datetime.fromtimestamp(r.get("ts", 0), timezone.utc).date() == target_day]
        if same_day:
            return same_day[0]
        return None, (f"matched {home} v {away} but none on {date}. Candidates: "
                      + ", ".join(datetime.fromtimestamp(r.get('ts', 0), timezone.utc)
                                  .date().isoformat() for _, r in cands[:5]))
    # nearest upcoming, else most recent
    now = time.time()
    upcoming = sorted([c for c in cands if (c[1].get("ts", 0) or 0) > now],
                      key=lambda c: c[1]["ts"])
    if upcoming:
        return upcoming[0]
    return sorted(cands, key=lambda c: c[1].get("ts", 0), reverse=True)[0]


def check_corpus_support(home, away):
    """Return (ok, corpus_teams, missing[list]). A prediction the model can't support
    (either team absent from corpus history) is refused — we say so and stop."""
    ms = mix.load_corpus()
    hist = mix.build_histories(ms)
    corpus_teams = set(hist.keys())
    missing = [t for t in (home, away) if t not in corpus_teams]
    return (len(missing) == 0), (ms, hist, corpus_teams), missing


def fetch_odds(mid, dry_run=False):
    """Fetch multi-book odds for ONE fixture, cache-first and quota-capped.

    Returns (books_dict, usage). Cached (match,book) pairs cost zero budget. Uses the
    SAME raw odds cache the pipeline uses (pilotC_odds_<mid>_<book>) — reading/writing
    that cache adds nothing to any ledger or sample.
    """
    import thestatsapi_client as api
    # local per-run cap so a manual run can never blow the budget
    api.MAX_LIVE_REQUESTS = min(api.MAX_LIVE_REQUESTS, MANUAL_REQUEST_CAP)
    before = api.budget_snapshot()
    usage = {"live_requests_made": 0, "cached_hits": 0, "monthly_remaining_before": before.get("last_monthly_remaining")}
    for bk in BOOKS:
        ck = f"pilotC_odds_{mid}_{bk}"
        if api.is_cached(ck):
            usage["cached_hits"] += 1
            continue
        if dry_run:
            # dry-run must not spend budget on a fixture with no cached odds
            continue
        try:
            api.get_json(f"/football/matches/{mid}/odds", params={"bookmaker": bk},
                         cache_key=ck, allow_status=(200, 404, 422))
        except SystemExit:
            usage["capped"] = True
            break
    usage["live_requests_made"] = api.live_requests_made()
    after = api.budget_snapshot()
    usage["monthly_remaining_after"] = after.get("last_monthly_remaining")
    books = fp.load_forward_books(mid)
    return books, usage


def _corpus_fingerprint(ms):
    """A cheap, stable fingerprint of the corpus + saved hyperparameters so a cached
    fitted model is invalidated automatically if either changes. Uses match count and
    the max date_unix (append-only corpus) plus a hash of the saved HP file bytes."""
    import hashlib
    max_date = max((m.get("date_unix", 0) or 0) for m in ms) if ms else 0
    hp_bytes = Path(STAT_MIXER_HP).read_bytes() if os.path.exists(STAT_MIXER_HP) else b""
    h = hashlib.sha256()
    h.update(str(len(ms)).encode()); h.update(str(int(max_date)).encode()); h.update(hp_bytes)
    return h.hexdigest()[:16]


def _fit_models(ms, hist, use_cache=True):
    """Fit the 9 market models on the FULL corpus using the SAVED CV-selected (C,
    l1_ratio). No hyperparameter search, no retune — identical to the experiment path.

    Fitting all 9 markets on the full corpus takes minutes; since the fit is
    deterministic given (corpus, saved hyperparameters), we optionally cache the fitted
    estimators to a MANUAL-owned pickle keyed on a corpus+HP fingerprint. This is a
    cache of the exact same fit, so it does not change the model or its comparability to
    the experiment — it only avoids recomputing identical coefficients. Delete the cache
    or pass use_cache=False to force a fresh fit.
    """
    import pickle
    saved = json.load(open(STAT_MIXER_HP))["models"]
    hp = {(x["market"], x["line"]): (x["C"], x["l1_ratio"]) for x in saved}
    fp_key = _corpus_fingerprint(ms)
    cache_path = Path(MANUAL_MODEL_CACHE.format(fp=fp_key))
    if use_cache and cache_path.exists():
        try:
            with open(cache_path, "rb") as f:
                return pickle.load(f), hp
        except Exception:
            pass  # fall through to a fresh fit on any cache read problem
    models = {}
    for (market, line), (C, l1r) in hp.items():
        models[(market, line)] = fp.fit_full(ms, hist, market, line, C, l1r)
    if use_cache:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(cache_path, "wb") as f:
                pickle.dump(models, f)
        except Exception:
            pass
    return models, hp


def build_prediction(mid, row, ms, hist, models, books):
    """Produce the per-market prediction + EV rows (no side effects)."""
    home, away = row["home"], row["away"]
    kickoff_ts = float(row.get("ts", 0) or 0)
    m = {"home_name": home, "away_name": away, "date_unix": kickoff_ts}
    markets = []
    for (market, line) in MANUAL_CELLS:
        model = models.get((market, line))
        if model is None:
            continue
        pm = fp.predict_one(model, hist, m, market)
        if pm is None:
            continue
        ok_key = MKT_ODDSKEY[market]
        entry = {"market": market, "line": line, "model_p": round(pm, 4), "books": {}}
        for bk, mk in books.items():
            if market == "btts":
                node = mk.get("btts", {})
                o = node.get("yes", {}).get("last_seen"); u = node.get("no", {}).get("last_seen")
            else:
                node = mk.get(ok_key, {}).get(str(line), {})
                o = node.get("over", {}).get("last_seen"); u = node.get("under", {}).get("last_seen")
            dv = fp.devig(o, u)
            if dv:
                fair, ovr = dv
                entry["books"][bk] = {
                    "fair_p": round(fair, 4), "overround": round(ovr, 4),
                    "edge_pp": round((pm - fair) * 100, 2),
                    "over_odds": float(o), "under_odds": float(u),
                }
        markets.append(entry)
    return {
        "fixture_id": mid, "home": home, "away": away,
        "kickoff_ts": kickoff_ts,
        "kickoff_iso": datetime.fromtimestamp(kickoff_ts, timezone.utc).isoformat() if kickoff_ts else None,
        "markets": markets,
    }


def _reference_price_for(entry):
    """Pick the reference book (Betfair primary) and build the reference_price dict that
    gets cryptographically bound into the commitment."""
    if not entry["books"]:
        return None, None
    ref_book = PRIMARY_BOOK if PRIMARY_BOOK in entry["books"] else next(iter(entry["books"]))
    ref = entry["books"][ref_book]
    return ref_book, {
        "book": ref_book, "over_odds": ref["over_odds"], "under_odds": ref["under_odds"],
        "fair_p": ref["fair_p"], "overround": ref["overround"],
    }


def commit_prediction(prediction, requested_by, dry_run=False):
    """Commit each market to the MANUAL ledger (own chain). Never backdates: if the
    fixture already kicked off the ledger refuses and we record it UNATTESTED."""
    ledger = AttestationLedger(commit_path=MANUAL_COMMIT_LEDGER, reveal_path=MANUAL_REVEAL_LEDGER)
    already = set(ledger.commitments_by_prediction().keys())
    mid = prediction["fixture_id"]
    kickoff = prediction["kickoff_ts"]
    requested_at = _now_iso()
    results = []
    for entry in prediction["markets"]:
        pred_id = _pred_id(mid, entry["market"], entry["line"])
        ref_book, reference_price = _reference_price_for(entry)
        entry["reference_book"] = ref_book
        rec = {"prediction_id": pred_id, "market": entry["market"], "line": entry["line"],
               "model_p": entry["model_p"], "reference_price": reference_price}
        if dry_run:
            rec["attested"] = False
            rec["attestation_note"] = "dry-run: not committed"
            results.append(rec)
            continue
        if pred_id in already:
            existing = ledger.commitments_by_prediction()[pred_id]
            rec["attested"] = True
            rec["commitment_hash"] = existing["commitment_hash"]
            rec["attestation_note"] = "already committed (idempotent, not re-committed)"
            results.append(rec)
            continue
        if reference_price is None:
            rec["attested"] = False
            rec["attestation_note"] = "no book odds — nothing to bind as reference price"
            results.append(rec)
            continue
        p_over = entry["model_p"]
        p_under = round(1.0 - entry["model_p"], 4)
        res = ledger.commit(
            prediction_id=pred_id, fixture_id=str(mid), model=f"{entry['market']}_{entry['line']}",
            kickoff_unix=float(kickoff), p_over=p_over,
            p_under=p_under, reference_price=reference_price,
            # Store p_over/p_under ON the record via extra so the commitment hash is
            # independently recomputable from the published record alone (the ledger's
            # own commit() binds them INTO the hash but does not otherwise persist them).
            extra={"source": "manual", "requested_by": requested_by or "unspecified",
                   "requested_at": requested_at, "p_over": p_over, "p_under": p_under},
        )
        if res.committed:
            rec["attested"] = True
            rec["commitment_hash"] = res.record["commitment_hash"]
            rec["prediction_timestamp"] = res.record["prediction_timestamp"]
        else:
            rec["attested"] = False
            rec["attestation_note"] = res.reason  # e.g. past-kickoff -> UNATTESTED, not backdated
        results.append(rec)
    return results


def _append_pred_log(prediction, commit_results, requested_by):
    """Append a manual prediction record (own file, never a pilotC_* filename)."""
    Path(MANUAL_PRED_LOG).parent.mkdir(parents=True, exist_ok=True)
    row = {
        "source": "manual",
        "requested_by": requested_by or "unspecified",
        "requested_at": _now_iso(),
        "fixture_id": prediction["fixture_id"],
        "home": prediction["home"], "away": prediction["away"],
        "kickoff_iso": prediction["kickoff_iso"],
        "markets": prediction["markets"],
        "commit_results": commit_results,
    }
    with open(MANUAL_PRED_LOG, "a") as f:
        f.write(json.dumps(row, default=str) + "\n")


# ── settle (mirrors pilotC_settle grading, but writes ONLY manual files) ─────

def settle_fixture(mid):
    """Grade a finished manual fixture and reveal outcomes against manual commitments."""
    import thestatsapi_client as api
    from pilotC_settle import _fetch_final, _grade  # reuse grading, read-only helpers

    ledger = AttestationLedger(commit_path=MANUAL_COMMIT_LEDGER, reveal_path=MANUAL_REVEAL_LEDGER)
    committed = ledger.commitments_by_prediction()
    already_revealed = set(ledger.reveals_by_prediction().keys())
    manual_for_fixture = {pid: c for pid, c in committed.items()
                          if pid.startswith(f"{MANUAL_ID_PREFIX}:{mid}:")}
    if not manual_for_fixture:
        return {"error": f"no manual commitments for fixture {mid}"}

    try:
        final = _fetch_final(api, mid)
    except SystemExit:
        return {"error": "request cap reached fetching final result"}

    settled_log = {"settled": []}
    if os.path.exists(MANUAL_SETTLED_LOG):
        try:
            settled_log = json.load(open(MANUAL_SETTLED_LOG))
        except Exception:
            pass
    logged = {r["prediction_id"] for r in settled_log["settled"]}

    out = {"fixture_id": mid, "revealed": 0, "graded": 0, "ungradeable": 0, "rows": []}
    for pid, c in manual_for_fixture.items():
        market = c["model"].rsplit("_", 1)[0]
        line_s = c["model"].rsplit("_", 1)[1]
        line = None if line_s == "None" else float(line_s)
        if pid in already_revealed:
            out["rows"].append({"prediction_id": pid, "status": "already_revealed"})
            continue
        actual, value = _grade(market, line, final)
        if actual is None:
            out["ungradeable"] += 1
            out["rows"].append({"prediction_id": pid, "status": "ungradeable_missing_result"})
            continue
        # model_p (== p_over) is persisted on the commitment record via extra.
        model_p = c.get("p_over")
        if model_p is None:
            model_p = _model_p_from_pred_log(pid)
        brier = (model_p - actual) ** 2 if model_p is not None else None
        now_iso = _now_iso()
        if pid not in logged:
            settled_log["settled"].append({
                "source": "manual", "prediction_id": pid, "match_id": mid,
                "market": market, "line": line, "model_p": model_p,
                "actual": actual, "actual_value": value,
                "brier_contribution": round(brier, 6) if brier is not None else None,
                "settled_at": now_iso,
            })
            logged.add(pid); out["graded"] += 1
        res = ledger.reveal(prediction_id=pid, fixture_id=str(mid), model=c["model"],
                            outcome={"actual": actual, "actual_value": value,
                                     "model_p": model_p, "line": line,
                                     "brier_contribution": round(brier, 6) if brier is not None else None},
                            settled_at=now_iso, extra={"source": "manual"})
        if res.committed:
            out["revealed"] += 1
            out["rows"].append({"prediction_id": pid, "status": "revealed",
                                "actual": actual, "actual_value": value})
        else:
            out["rows"].append({"prediction_id": pid, "status": "reveal_declined",
                                "reason": res.reason})
    settled_log["updated_at"] = _now_iso()
    settled_log["n_settled_total"] = len(settled_log["settled"])
    Path(MANUAL_SETTLED_LOG).parent.mkdir(parents=True, exist_ok=True)
    json.dump(settled_log, open(MANUAL_SETTLED_LOG, "w"), indent=2, default=str)
    return out


def _model_p_from_pred_log(pid):
    """Recover the model probability recorded for a prediction id from the manual
    prediction log (so the settled row reports the same p that was committed)."""
    if not os.path.exists(MANUAL_PRED_LOG):
        return None
    found = None
    with open(MANUAL_PRED_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            for e in r.get("markets", []):
                if _pred_id(r["fixture_id"], e["market"], e["line"]) == pid:
                    found = e["model_p"]
    return found


# ── independent hash verification ────────────────────────────────────────────

def verify_hash(mid=None):
    """Independently recompute each manual commitment hash from its recorded fields and
    confirm it matches, then verify the whole chain. This is the mechanism that lets a
    third party confirm a PUBLISHED hash rather than trust a displayed string.

    Recompute recipe (documented for external verifiers): the commitment hash is
        SHA-256( canonical_json({
            "prediction_id", "fixture_id", "model",
            "p_over", "p_under", "reference_price", "prediction_timestamp" }) )
    where canonical_json = json.dumps(obj, sort_keys=True, separators=(",",":")).
    """
    ledger = AttestationLedger(commit_path=MANUAL_COMMIT_LEDGER, reveal_path=MANUAL_REVEAL_LEDGER)
    rows = ledger.load_commitments()
    if mid:
        rows = [r for r in rows if r["fixture_id"] == str(mid)]
    checked = []
    for r in rows:
        # p_over/p_under are persisted on the manual record (via extra) precisely so the
        # hash is recomputable from the published record with no hidden inputs.
        recomputed = compute_commitment_hash(
            prediction_id=r["prediction_id"], fixture_id=r["fixture_id"],
            model=r["model"], p_over=r.get("p_over"), p_under=r.get("p_under"),
            reference_price=r.get("reference_price"),
            prediction_timestamp=r["prediction_timestamp"],
        )
        checked.append({"prediction_id": r["prediction_id"],
                        "stored_commitment_hash": r["commitment_hash"],
                        "recomputed_commitment_hash": recomputed,
                        "recomputed_matches": recomputed == r["commitment_hash"]})
    ok_chain, problems = ledger.verify_chain(MANUAL_COMMIT_LEDGER)
    return {"rows_checked": len(checked), "detail": checked,
            "chain_verifies": ok_chain, "chain_problems": problems[:5]}


# ── output rendering ─────────────────────────────────────────────────────────

def render_summary(prediction, commit_results, usage, requested_by, dry_run):
    mid = prediction["fixture_id"]
    lines = []
    lines.append("=" * 72)
    tag = "DRY-RUN (not committed)" if dry_run else "MANUAL PREDICTION (on the record)"
    lines.append(f"{tag} — source=manual  requested_by={requested_by or 'unspecified'}")
    lines.append("=" * 72)
    lines.append(f"Fixture : {prediction['home']} v {prediction['away']}  [{mid}]")
    lines.append(f"Kickoff : {prediction['kickoff_iso']}")
    cr_by_id = {c["prediction_id"]: c for c in commit_results}
    any_attested = any(c.get("attested") for c in commit_results)
    lines.append(f"Attested: {'yes' if any_attested else 'NO (see notes)'}"
                 + ("" if dry_run else f"  ledger={MANUAL_COMMIT_LEDGER}"))
    lines.append("")
    hdr = f"{'market':7s} {'line':>5s} {'model_p':>8s} {'book':16s} {'fair_p':>7s} {'edge_pp':>8s} {'overround':>9s}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    edges = []
    for entry in prediction["markets"]:
        line_s = "-" if entry["line"] is None else f"{entry['line']:.1f}"
        if not entry["books"]:
            lines.append(f"{entry['market']:7s} {line_s:>5s} {entry['model_p']:8.4f} "
                         f"{'(no book odds)':16s}")
            continue
        for i, (bk, b) in enumerate(entry["books"].items()):
            mk = entry["market"] if i == 0 else ""
            ln = line_s if i == 0 else ""
            mp = f"{entry['model_p']:.4f}" if i == 0 else ""
            flag = "  <= EDGE" if abs(b["edge_pp"]) >= EDGE_THRESHOLD_PP else ""
            lines.append(f"{mk:7s} {ln:>5s} {mp:>8s} {bk:16s} {b['fair_p']:7.4f} "
                         f"{b['edge_pp']:+8.2f} {b['overround']:9.4f}{flag}")
            if abs(b["edge_pp"]) >= EDGE_THRESHOLD_PP:
                edges.append((entry["market"], entry["line"], bk, b["edge_pp"]))
    lines.append("")
    if edges:
        lines.append(f"Markets showing edge >= {EDGE_THRESHOLD_PP:g}pp (display only, NOT a bet signal):")
        for mk, ln, bk, e in edges:
            lines.append(f"  {mk} {('' if ln is None else ln)} vs {bk}: {e:+.2f}pp")
    else:
        lines.append(f"No market shows edge >= {EDGE_THRESHOLD_PP:g}pp against the reference books.")
    lines.append("")
    # commitment hashes (independently verifiable)
    committed_rows = [c for c in commit_results if c.get("commitment_hash")]
    if committed_rows and not dry_run:
        lines.append("Commitment hashes (independently verifiable — see --verify-hash):")
        for c in committed_rows:
            lines.append(f"  {c['prediction_id']}  {c['commitment_hash']}")
        lines.append("")
    unattested = [c for c in commit_results if not c.get("attested") and not dry_run]
    if unattested:
        lines.append("Unattested markets (NOT backdated):")
        for c in unattested:
            lines.append(f"  {c['prediction_id']}: {c.get('attestation_note')}")
        lines.append("")
    # quota
    lines.append(f"Quota: live_requests_this_run={usage.get('live_requests_made')} "
                 f"cached_book_hits={usage.get('cached_hits')} "
                 f"monthly_remaining={usage.get('monthly_remaining_after')}")
    lines.append("")
    lines.append(CAVEAT)
    lines.append("=" * 72)
    return "\n".join(lines)


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser(description="Manual ad-hoc prediction + EV (separate from Pilot C)")
    ap.add_argument("--fixture-id")
    ap.add_argument("--home")
    ap.add_argument("--away")
    ap.add_argument("--date", help="YYYY-MM-DD (optional, with --home/--away)")
    ap.add_argument("--requested-by", help="who requested this (recorded for provenance)")
    ap.add_argument("--dry-run", action="store_true", help="predict + EV without committing")
    ap.add_argument("--settle", action="store_true", help="settle+reveal a finished manual fixture")
    ap.add_argument("--verify-hash", action="store_true", help="re-verify manual commitment hashes + chain")
    ap.add_argument("--json", action="store_true", help="emit machine-readable JSON instead of the text summary")
    args = ap.parse_args()

    if args.verify_hash:
        mid = args.fixture_id
        if not mid and args.home and args.away:
            mid, _ = resolve_fixture(home=args.home, away=args.away, date=args.date)
        result = verify_hash(mid)
        print(json.dumps(result, indent=2, default=str))
        allok = all(d["recomputed_matches"] for d in result["detail"]) and result["chain_verifies"]
        sys.exit(0 if allok else 1)

    mid, row = resolve_fixture(fixture_id=args.fixture_id, home=args.home,
                               away=args.away, date=args.date)
    if mid is None:
        print(f"ERROR: {row}", file=sys.stderr)  # row holds the reason string here
        sys.exit(2)

    if args.settle:
        result = settle_fixture(mid)
        print(json.dumps(result, indent=2, default=str))
        print("\n" + CAVEAT)
        sys.exit(0)

    home, away = row["home"], row["away"]
    ok, corpus, missing = check_corpus_support(home, away)
    if not ok:
        print(f"ERROR: cannot predict — no corpus history for: {', '.join(missing)}.",
              file=sys.stderr)
        print("The model cannot support a prediction for a team it has never seen. Stopping "
              "rather than producing an unsupported prediction.", file=sys.stderr)
        sys.exit(3)
    ms, hist, corpus_teams = corpus

    books, usage = fetch_odds(mid, dry_run=args.dry_run)
    if not books:
        note = ("no cached odds for this fixture and --dry-run does not fetch"
                if args.dry_run else
                "no odds available for this fixture from any book (cannot compute EV)")
        print(f"ERROR: {note}.", file=sys.stderr)
        sys.exit(4)

    models, hp = _fit_models(ms, hist)
    prediction = build_prediction(mid, row, ms, hist, models, books)
    commit_results = commit_prediction(prediction, args.requested_by, dry_run=args.dry_run)
    if not args.dry_run:
        _append_pred_log(prediction, commit_results, args.requested_by)

    if args.json:
        print(json.dumps({"prediction": prediction, "commit_results": commit_results,
                          "quota": usage, "caveat": CAVEAT, "dry_run": args.dry_run},
                         indent=2, default=str))
    else:
        print(render_summary(prediction, commit_results, usage, args.requested_by, args.dry_run))


if __name__ == "__main__":
    main()
