"""Boundary tests only; synthetic rows are not empirical evidence."""
import copy
import importlib.util
import unittest
from pathlib import Path
import numpy as np

spec=importlib.util.spec_from_file_location('development',Path(__file__).with_name('run_development.py'))
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)


def fixture(index):
    side={'value':1,'period_status':'NO_EXTRA_TIME_RECORDED'}
    return {'match_id':str(index),'kickoff_ts':1600000000+index*7*86400,
            'kickoff':'2020-09-13T12:00:00Z','home_id':'a','away_id':'b',
            'context':{'is_neutral':False},'raw_stats':{path+'.all.'+s:2 for path in m.MAP.values() for s in ('home','away')},
            'targets':{f+'.'+s:dict(side) for f in ('goals','corners','bookings') for s in ('home','away')},'period_checks':[]}


class Tests(unittest.TestCase):
    def test_current_and_future_outcomes_do_not_change_earlier_features(self):
        rows=[fixture(i) for i in range(7)];a,_=m.features(rows)
        for row in rows[4:]:
            for target in row['targets'].values():target['value']=100
            row['raw_stats']={k:100 for k in row['raw_stats']}
        b,_=m.features(rows)
        for i in range(5):
            for family in m.BUNDLES:self.assertEqual(a[i]['families'][family]['sides'],b[i]['families'][family]['sides'])

    def test_cutoff_equality_excluded(self):
        a,b=fixture(0),fixture(1)
        b['kickoff_ts']=a['kickoff_ts']+28*3600
        panel,_=m.features([a,b]);self.assertEqual(panel[1]['source_match_ids'],[])

    def test_no_same_fixture_self_input(self):
        panel,_=m.features([fixture(i) for i in range(6)])
        for row in panel:
            self.assertNotIn(row['match_id'],row['source_match_ids'])
            if row['max_source_kickoff'] is not None:self.assertLess(row['max_source_kickoff']+4*3600,row['cutoff_ts'])

    def test_semantic_quarantine(self):
        row=fixture(0);row['period_checks']=[{'path':'overview.yellow_cards','side':'home'}]
        values,_=m.semantics(row)
        self.assertIsNone(values['home']['yellow_card_proxy'])
        self.assertEqual(values['away']['yellow_card_proxy'],1)
        for side in ('home','away'):row['targets']['corners.'+side]['period_status']='PERIOD_UNRESOLVED'
        values,_=m.semantics(row)
        self.assertEqual(values['home']['goals'],1)
        self.assertIsNone(values['home']['shots'])
        self.assertIsNone(values['home']['corners'])

    def test_duplicate_and_half_conflicts(self):
        row=fixture(0);row['raw_stats']['shots.total_shots.all.home']=3
        values,_=m.semantics(row);self.assertIsNone(values['home']['shots'])
        row=fixture(0)
        row['raw_stats'].update({'overview.big_chances.first_half.home':0,'overview.big_chances.second_half.home':0})
        values,_=m.semantics(row);self.assertIsNone(values['home']['big'])

    def test_training_only_transform(self):
        model=m.Fit([[1,None],[2,4],[3,6],[4,None]],[1,1,2,2])
        before=model.median.copy();mean=model.mean.copy()
        model.predict([[1e3,1e3]])
        np.testing.assert_array_equal(model.median,before);np.testing.assert_array_equal(model.mean,mean)

    def test_supported_zero_and_unknown_neutral(self):
        row=fixture(0);row['targets']['goals.home']['value']=0
        self.assertEqual(m.semantics(row)[0]['home']['goals'],0)
        row['context']['is_neutral']=None
        panel,_=m.features([row]);self.assertIsNone(panel[0]['families']['goals']['sides']['home']['M1'][-1])

    def test_features_do_not_mutate_source(self):
        rows=[fixture(i) for i in range(5)];before=copy.deepcopy(rows)
        m.features(rows);self.assertEqual(rows,before)


if __name__=='__main__':unittest.main()
