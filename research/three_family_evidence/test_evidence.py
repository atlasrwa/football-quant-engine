import copy
import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('evidence', Path(__file__).with_name('build_evidence.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = {'id': 'm', 'status': 'finished', 'utc_date': '2025-01-01T12:00:00Z',
                        'competition_id': 'c', 'season_id': 's',
                        'home_team': {'id': 'h'}, 'away_team': {'id': 'a'},
                        'score': {'regulation': {'home': 0, 'away': 1},
                                  'went_to_extra_time': False, 'went_to_penalties': False}}
        self.stats = {'data': {'match_id': 'm', 'overview': {
            'corner_kicks': {'all': {'home': 0, 'away': 3},
                             'first_half': {'home': 0, 'away': 1},
                             'second_half': {'home': 0, 'away': 2}},
            'yellow_cards': {'all': {'home': 1, 'away': None}}}}}

    def row(self):
        return module.normalize(self.fixture, self.stats, {})

    def test_nine_targets_missing_not_zero(self):
        r = self.row()
        self.assertEqual(len(r['targets']), 9)
        self.assertEqual(r['targets']['corners.home']['value'], 0)
        self.assertIsNone(r['targets']['bookings.total']['value'])
        self.assertEqual(r['targets']['goals.total']['value'], 1)

    def test_identity_binding(self):
        self.stats['data']['match_id'] = 'foreign'
        with self.assertRaises(ValueError): self.row()

    def test_extra_time_does_not_change_regulation_goal_target(self):
        self.fixture['score'].update(went_to_extra_time=True, home=5, away=4)
        r = self.row()
        self.assertEqual(r['targets']['goals.total']['value'], 1)
        self.assertEqual(r['targets']['corners.home']['period_status'], 'PERIOD_UNRESOLVED')

    def test_period_mismatch_preserved(self):
        self.stats['data']['overview']['corner_kicks']['all']['away'] = 4
        r = self.row()
        self.assertEqual(len(r['period_checks']), 1)
        self.assertEqual(r['targets']['corners.away']['value'], 4)

    def test_no_false_pit_or_promotion(self):
        r = self.row()
        self.assertFalse(r['prediction_input_eligible'])
        self.assertIsNone(r['context']['is_neutral'])
        self.assertTrue(all(t['promotion_status'] == 'NOT_EVALUATED' for t in r['targets'].values()))
        self.assertEqual(r['targets']['bookings.home']['semantic_status'], 'BOOKMAKER_RULES_UNVERIFIED')

    def test_bad_counts(self):
        for value in (True, -1, 1.2, float('nan'), float('inf'), '2'):
            self.assertIsNone(module.number(value, count=True))

    def test_deterministic_without_mutation(self):
        before = copy.deepcopy(self.stats)
        self.assertEqual(module.digest(self.row()), module.digest(self.row()))
        self.assertEqual(before, self.stats)


if __name__ == '__main__': unittest.main()
