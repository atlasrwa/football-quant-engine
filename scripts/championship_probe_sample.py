"""Probe: how many usable predictions per metric/line under point-in-time rolling
windows, using the EXACT ev pipeline functions on the adapted Championship slice."""
import os, sys, json
sys.path.insert(0, os.path.dirname(__file__))
import ev_test_metrics_vs_bet365 as ev
import championship_adapter as adapt

matches = adapt.load_adapted_matches()
th = ev.build_team_histories(matches)
# matched dict: mid -> match (all of them are their own 'footystats' match here)
matched = {m['match_id']: m for m in matches}

for metric_id, mdef in ev.METRICS.items():
    preds = ev.compute_metric_predictions(mdef, matched, th, matches)
    n = 0 if preds is None else len(preds)
    print(f"{metric_id:26s} target={mdef['target']:12s} usable_predictions={n}")
