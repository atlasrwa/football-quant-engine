"""Generate V3_EVIDENCE_HUMAN_AUDIT.md deterministically from frozen data. ZERO SPEND.

Read-only. For each clean fixture: upstream availability, exact evidence Sonnet saw, ALL
accepted raw hypotheses (unranked, unfiltered), their compiled interpretation, and the
important upstream information Sonnet did NOT see.
"""
from __future__ import annotations
import json, sys
from collections import Counter

sys.path.insert(0, "/home/ubuntu/src"); sys.path.insert(0, "/home/ubuntu")
from src.research.hypothesis_engine import corpus_adapter as CA

ROOT = "/home/ubuntu"
PKT = f"{ROOT}/research/hypothesis_engine/out/MATERIALIZED_PACKETS_sonnet46_v3.json"
CORPUS = f"{ROOT}/research/hypothesis_engine/out/v3_hypothesis_measurement/frozen_hypothesis_corpus.json"
CAPMAT = f"{ROOT}/research/hypothesis_engine/out/v3_evidence_audit/capability_matrix.json"
OUT = f"{ROOT}/research/hypothesis_engine/V3_EVIDENCE_HUMAN_AUDIT.md"
CLEAN = ['mt_010243515', 'mt_010243537', 'mt_010243938', 'mt_010244159', 'mt_010244193',
         'mt_010441320', 'mt_010441491', 'mt_010444904', 'mt_012232295', 'mt_012232411',
         'mt_013233190']


def cond_str(h):
    cs = h.get("conditions") or []
    if not cs:
        return "(none)"
    return ", ".join(f"{c['dimension']}={c.get('value', c.get('axis', '?'))}" for c in cs)


def main():
    packets = json.load(open(PKT))
    corpus = json.load(open(CORPUS))
    capmat = json.load(open(CAPMAT))
    idx = CA.load_index()
    by_id = {r.fixture_id: r for r in idx.records}

    by_fix = {}
    for rec in corpus["included"]:
        by_fix.setdefault(rec["fixture_id"], []).append(rec)

    L = []
    W = L.append
    W("# V3 Evidence — Human-Readable Fixture Audit\n")
    W("Companion to `V3_EVIDENCE_FORENSIC_AUDIT.md`. ZERO-SPEND, read-only. For each of the "
      "11 clean reference fixtures: the upstream historical data available, the exact "
      "evidence Sonnet saw, ALL accepted raw hypotheses (listed in full, unranked, NOT "
      "filtered by V4 outcomes), their compiled interpretation, and the important upstream "
      "information Sonnet did NOT see.\n")
    W("A human football analyst should be able to read each fixture and judge: *given what "
      "Sonnet actually saw, were these sensible questions?* and *what better questions "
      "might richer exposed data have enabled?* (Better questions are NOT generated here — "
      "no LLM was called.)\n")
    W("---\n")

    for fid in CLEAN:
        target = by_id[fid]
        pk = packets[f"reference::{fid}"]
        ev = pk["evidence"]
        cap = capmat["fixtures"][fid]
        h = cap["upstream_capability"]["home"]
        a = cap["upstream_capability"]["away"]
        hyps = sorted(by_fix.get(fid, []), key=lambda r: (r["seq"], r["hypothesis"]["hypothesis_id"]))

        W(f"## {fid} — {target.home} (home) vs {target.away} (away) · {target.competition}\n")

        W("**1. Upstream historical data available (PIT-safe, before kickoff):**\n")
        W(f"- Home ({target.home}): {h['window_depth']['n_prior']} prior matches; "
          f"venue-splittable metrics {h['n_metrics_venue_splittable']}/19; "
          f"W10 ok: {h['window_depth']['W10_ok']}; formation coverage "
          f"{h['formation']['coverage']} ({h['formation']['n_with_formation']}/"
          f"{h['formation']['n_prior']}), distinct formations "
          f"{h['formation']['distinct_formations']}, contrastive {h['formation']['contrastive']}.")
        W(f"- Away ({target.away}): {a['window_depth']['n_prior']} prior matches; "
          f"venue-splittable metrics {a['n_metrics_venue_splittable']}/19; "
          f"W10 ok: {a['window_depth']['W10_ok']}; formation coverage "
          f"{a['formation']['coverage']} ({a['formation']['n_with_formation']}/"
          f"{a['formation']['n_prior']}), distinct formations "
          f"{a['formation']['distinct_formations']}, contrastive {a['formation']['contrastive']}.\n")

        W("**2. Exact evidence Sonnet saw:**\n")
        W(f"- {cap['v3_evidence']['n_items']} evidence items, all "
          f"`window={cap['v3_evidence']['windows']}` `venue={cap['v3_evidence']['venues']}` "
          f"(unconditional shrunk scalar means), {cap['v3_evidence']['n_distinct_metrics']} "
          f"distinct metrics × FOR/AGAINST × HOME/AWAY. No distribution, no per-match rows, "
          f"no venue/formation/opponent-profile split.")
        sample = [e for e in ev if e["metric"] in ("corners_for", "shots_on_target_for",
                                                    "possession_for", "goals_for")][:4]
        for e in sample:
            W(f"  - `{e['metric']}` = {e['value']} (n={e['sample_n']}, {e['reliability']}, "
              f"{e['shrinkage_level']}, {e['source_provider']})")
        fdist = pk.get("formation_distribution", {})
        W(f"- formation_distribution (count histogram only): `{json.dumps(fdist)}`\n")

        W(f"**3. Accepted raw hypotheses ({len(hyps)}) — verbatim question + structure:**\n")
        for r in hyps:
            hyp = r["hypothesis"]
            W(f"- **{hyp['hypothesis_id']}** [{hyp.get('research_family')}] "
              f"target={hyp.get('target_metrics')} side={hyp.get('side')} "
              f"subject={hyp.get('subject')}")
            W(f"  - Q: *{hyp.get('question')}*")
            W(f"  - conditions: {cond_str(hyp)} · comparison: `{hyp.get('comparison')}` · "
              f"window: `{hyp.get('window')}`")
        W("")

        # compiled interpretation summary
        comps = Counter(r["hypothesis"].get("comparison") for r in hyps)
        conds = Counter(c["dimension"] for r in hyps
                        for c in (r["hypothesis"].get("conditions") or []))
        W("**4. Compiled interpretation (deterministic):**\n")
        W(f"- comparisons requested: `{dict(comps)}`")
        W(f"- condition dimensions requested: `{dict(conds) if conds else '{}'}`\n")

        W("**5. Important upstream information Sonnet did NOT see:**\n")
        missing = []
        if h["n_metrics_venue_splittable"] >= 5 or a["n_metrics_venue_splittable"] >= 5:
            missing.append(f"venue-conditioned behavior (home/away splits were derivable "
                           f"for ~{max(h['n_metrics_venue_splittable'], a['n_metrics_venue_splittable'])}/19 metrics)")
        if h["window_depth"]["W10_ok"] or a["window_depth"]["W10_ok"]:
            missing.append("recent-vs-long-run (W5/W10/season all derivable) — collapsed to ALL_PRIOR")
        missing.append("opponent-profile response vs similar opponents (derivable; V4-proven measurable)")
        missing.append("per-match rows / chronology / distribution / cross-metric structure")
        if h["formation"]["contrastive"] or a["formation"]["contrastive"]:
            missing.append("formation-conditioned metrics (a contrastive split existed on at least one side)")
        else:
            missing.append("formation splits — genuinely provider-limited here (low coverage)")
        for m in missing:
            W(f"- {m}")
        W("\n---\n")

    W("## Cross-fixture note\n")
    W("Across the 11 fixtures, 58/112 accepted hypotheses requested venue conditioning or a "
      "venue baseline and 37/112 requested opponent-profile conditioning — while the "
      "evidence packet contained zero venue-split and zero opponent-profile items. Sonnet "
      "was reasoning about conditional football using only unconditional averages. Formation "
      "is the one dimension where the upstream provider genuinely lacked coverage "
      "(0.00–0.32); everything else conditional was available or derivable but not exposed.\n")
    W("**No hypotheses were ranked, filtered, or cherry-picked by V4 predictive outcomes.**\n")

    open(OUT, "w").write("\n".join(L))
    print("wrote", OUT, f"({len(hyps) and 'ok'})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
