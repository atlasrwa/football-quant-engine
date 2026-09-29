import importlib.util
from pathlib import Path
import unittest
import numpy as np
loader=importlib.util.spec_from_file_location('candidate',Path(__file__).with_name('run.py'))
module=importlib.util.module_from_spec(loader);loader.loader.exec_module(module)

class Tests(unittest.TestCase):
    def test_btts_joint_identity_and_symmetry(self):
        a=module.events([1.,2.],'goals');b=module.events([2.,1.],'goals')
        self.assertAlmostEqual(a['btts'],(1-np.exp(-1))*(1-np.exp(-2)))
        self.assertEqual(a['btts'],b['btts']);self.assertEqual(a['total'],b['total'])
        self.assertEqual(module.events([0,2],'goals')['btts'],0)
    def test_corners_excluded(self):
        with self.assertRaises(ValueError):module.events([3,5],'corners')
    def test_market_guards(self):
        p={'fixture_id':'f','market':'btts','side':'yes','period':'FT','line':None,'settlement_verified':True,
           'binary_no_push':True,'freeze_ts':100,'kickoff_ts':200,'p_model':.6}
        q={**p,'observed_at':99,'selected_odds':2.,'opposite_odds':2.}
        result=module.compare_quote(p,q,10)
        self.assertAlmostEqual(result['disagreement_pp'],10)
        self.assertAlmostEqual(result['ev_before_costs'],.2)
        for change in ({'observed_at':101},{'line':2.5},{'settlement_verified':False},{'selected_odds':1},{'observed_at':80}):
            with self.assertRaises(ValueError):module.compare_quote(p,{**q,**change},10)
    def test_calibration_is_bounded_and_positive(self):
        means=np.array([[1.,2.],[2.,1.],[1.,1.],[2.,2.]])
        theta=module.calibrate(means,means)
        self.assertAlmostEqual(theta[2],1.,places=4)
        self.assertTrue(np.all(np.exp(theta[:2]+theta[2]*np.log(means))>0))

if __name__=='__main__':unittest.main()
