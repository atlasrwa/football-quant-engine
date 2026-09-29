"""Offline three-family evidence inventory. No predictor or promotion claim.

Consumes existing V3 cache bytes without importing a live provider client.
Raw source paths remain provider-specific. Retrospective records are not PIT replay.
"""
import argparse
from collections import Counter
import datetime as dt
import hashlib
import json
import math
from pathlib import Path

SIDES = ('home', 'away')
PERIODS = ('all', 'first_half', 'second_half')
TARGET_PATHS = {'corners': 'overview.corner_kicks',
                'bookings': 'overview.yellow_cards'}
ADDITIVE = ('overview.corner_kicks', 'overview.total_shots',
            'overview.shots_on_target', 'overview.yellow_cards',
            'shots.blocked_shots', 'shots.shots_inside_box',
            'passes.accurate_crosses', 'passes.final_third_entries')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    default=str).encode()).hexdigest()


def timestamp(value):
    parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is None:
        raise ValueError('timezone required')
    return parsed.timestamp()


def number(value, count=False):
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        return None
    if not math.isfinite(value) or value < 0 or (count and int(value) != value):
        return None
    return value


def flatten(node, prefix=''):
    """Preserve nulls and exact provider paths; no inferred unit conversions."""
    if isinstance(node, dict):
        out = {}
        for key, value in sorted(node.items()):
            out.update(flatten(value, f'{prefix}.{key}' if prefix else key))
        return out
    return {prefix: node}


def stat_value(flat, path, period, side):
    return number(flat.get(f'{path}.{period}.{side}'), count=True)


def normalize(fixture, stats, provenance):
    if fixture.get('status') != 'finished':
        raise ValueError('finished fixture required')
    data = (stats or {}).get('data') or {}
    if stats is not None and data.get('match_id') != fixture['id']:
        raise ValueError('stats/fixture identity mismatch')
    flat = flatten(data)
    score = fixture.get('score') or {}
    # Extra time or ambiguous duration must not silently enter regulation targets.
    regulation_only = (score.get('went_to_extra_time') is False
                       and score.get('went_to_penalties') is False
                       and score.get('after_extra_time') is None)
    targets = {}
    for family in ('goals', 'corners', 'bookings'):
        pair = {}
        for side in SIDES:
            if family == 'goals':
                value = number((score.get('regulation') or {}).get(side), count=True)
                basis = 'score.regulation'
            else:
                value = stat_value(flat, TARGET_PATHS[family], 'all', side)
                basis = TARGET_PATHS[family] + '.all'
            pair[side] = value
            targets[f'{family}.{side}'] = {
                'value': value, 'basis': basis,
                'period_status': ('EXPLICIT_REGULATION' if family == 'goals'
                                  else 'NO_EXTRA_TIME_RECORDED' if regulation_only
                                  else 'PERIOD_UNRESOLVED'),
                'semantic_status': ('BOOKMAKER_RULES_UNVERIFIED' if family == 'bookings'
                                    else 'PROVIDER_NATIVE'),
                'research_status': 'AVAILABLE_RAW' if value is not None else 'UNSUPPORTED',
                'promotion_status': 'NOT_EVALUATED',
            }
        total = None if None in pair.values() else pair['home'] + pair['away']
        targets[f'{family}.total'] = dict(targets[f'{family}.home'], value=total,
            basis=basis + ':home+away',
            research_status='AVAILABLE_RAW' if total is not None else 'UNSUPPORTED')
    checks = []
    for path in ADDITIVE:
        for side in SIDES:
            values = [stat_value(flat, path, period, side) for period in PERIODS]
            if None not in values and values[0] != values[1] + values[2]:
                checks.append({'path': path, 'side': side,
                               'all': values[0], 'half_sum': values[1] + values[2],
                               'status': 'PERIOD_RECONCILIATION_REQUIRED'})
    return {
        'provider': 'THESTATSAPI_ONLY', 'match_id': fixture['id'],
        'kickoff': fixture['utc_date'], 'kickoff_ts': timestamp(fixture['utc_date']),
        'competition_id': fixture['competition_id'], 'season_id': fixture['season_id'],
        'home_id': fixture['home_team']['id'], 'away_id': fixture['away_team']['id'],
        'context': {key: fixture.get(key) for key in (
            'is_neutral', 'home_manager', 'away_manager', 'matchday', 'stage_name',
            'group_label', 'venue', 'xg_available')},
        'context_status': 'HISTORICAL_RECORD_NOT_ASOF_TARGET_CONTEXT',
        'raw_stats': flat, 'targets': targets, 'period_checks': checks,
        'provenance': provenance, 'availability_mode': 'RETROSPECTIVE_RECONSTRUCTION',
        'prediction_input_eligible': False,
    }


def build(cache):
    sources, fixtures, conflicts = [], {}, []
    files = sorted((cache / 'matches').rglob('*.json'))
    if not files:
        raise ValueError('CACHE_MISS: no cached match lists')
    for path in files:
        raw = path.read_bytes()
        source = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                  'observed_at': float(path.name.split('_', 1)[0])}
        sources.append(source)
        for fixture in json.loads(raw).get('data', []):
            if fixture.get('status') != 'finished':
                continue
            key = fixture['id']
            if key in fixtures and digest(fixtures[key][0]) != digest(fixture):
                conflicts.append(key)
            # Stable choice retained for audit only; conflicts are quarantined below.
            fixtures.setdefault(key, (fixture, source))
    if conflicts:
        raise ValueError('CONFLICTING_FIXTURE_VERSIONS: ' + ','.join(sorted(set(conflicts))))
    records = []
    for key, (fixture, source) in sorted(fixtures.items()):
        path = cache / 'finished_stats' / f'{key}.json'
        stats, stat_source = None, None
        if path.exists():
            raw = path.read_bytes()
            wrapped = json.loads(raw)
            stats = wrapped['payload']
            if digest(stats)[:16] != wrapped['payload_hash']:
                raise ValueError('STATS_HASH_MISMATCH: ' + key)
            observed = number(wrapped['observed_at'])
            if observed is None:
                raise ValueError('invalid observed_at')
            stat_source = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest(),
                           'payload_hash': wrapped['payload_hash'], 'observed_at': observed}
            sources.append(stat_source)
        records.append(normalize(fixture, stats, {'fixture': source, 'stats': stat_source}))
    records.sort(key=lambda row: (row['kickoff_ts'], row['match_id']))
    coverage = {}
    for key in records[0]['targets'] if records else []:
        eligible = [row['targets'][key] for row in records]
        coverage[key] = {
            'fixtures': len(records), 'available_raw': sum(x['value'] is not None for x in eligible),
            'period_resolved_raw': sum(x['value'] is not None and x['period_status'] != 'PERIOD_UNRESOLVED'
                                       for x in eligible),
            'status': 'DEVELOPMENT_ONLY', 'promotion': 'NOT_EVALUATED',
            'market_semantics_verified': False,
        }
    fields = Counter()
    for row in records:
        fields.update(k for k, v in row['raw_stats'].items() if number(v) is not None)
    report = {
        'version': 'THREE_FAMILY_EVIDENCE_V1', 'mode': 'OFFLINE_ONLY',
        'fixtures': len(records), 'stats_payloads': sum(r['provenance']['stats'] is not None for r in records),
        'competitions': dict(Counter(r['competition_id'] for r in records)),
        'targets': coverage, 'numeric_field_coverage': dict(sorted(fields.items())),
        'fixtures_with_period_mismatches': sum(bool(r['period_checks']) for r in records),
        'period_mismatch_cells': sum(len(r['period_checks']) for r in records),
        'corpus_sha256': digest(records), 'sources': sources,
        'live_calls': 0, 'models_fitted': 0, 'promoted_markets': [],
        'limitations': ['Raw coverage is not validation or calibration.',
                       'Retrospective cache captures do not prove pre-match availability.',
                       'Half totals require reconciliation before conditional modelling.',
                       'Yellow cards are not automatically bookmaker bookings.',
                       'npxG retained as raw evidence only; no change to exclusions.',
                       'Manager values require historical fidelity checks.',
                       'No hypothesis effect or model probability is estimated here.'],
    }
    return records, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve().is_relative_to(args.cache.resolve()):
        raise ValueError('output must be outside immutable input cache')
    rows, report = build(args.cache)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'evidence.jsonl').write_text(''.join(json.dumps(r, sort_keys=True) + '\n' for r in rows))
    (args.output / 'coverage.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: report[k] for k in ('fixtures', 'stats_payloads', 'targets',
          'fixtures_with_period_mismatches', 'corpus_sha256', 'models_fitted')}, indent=2))


if __name__ == '__main__':
    main()
