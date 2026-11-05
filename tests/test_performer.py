import unittest
from nougen_shards.performer.engine import *
class TestUDCT(unittest.TestCase):
    def setUp(self):self.p=demo()
    def test_repeatable(self):self.assertEqual(evaluate(self.p,2.3),evaluate(self.p,2.3))
    def test_out_of_order(self):
        a=evaluate(self.p,4.1);evaluate(self.p,1.2);self.assertEqual(a,evaluate(self.p,4.1))
    def test_bounds(self):
        for f in frames(self.p,30):
            for k,v in f['channels'].items():
                lo,hi=LIMITS.get(k,(0,1));self.assertTrue(lo<=v<=hi,(k,v))
    def test_distinct_phonemes(self):
        self.assertGreater(evaluate(self.p,1.0)['jaw.open'],evaluate(self.p,.6)['jaw.open'])
    def test_turn(self):self.assertGreater(evaluate(self.p,4.9)['head.yaw'],0)
    def test_invalid_time(self):
        with self.assertRaises(ValueError):evaluate(self.p,7)
if __name__=='__main__':unittest.main()
