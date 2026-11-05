import unittest
from nougen_shards.performer.engine import LIMITS, demo, evaluate, frames
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
class TestReview(unittest.TestCase):
    def test_frames_stay_in_range(self):
        import dataclasses; p=dataclasses.replace(demo(),duration=6.01)
        self.assertLessEqual(frames(p)[-1]['time'],p.duration)
    def test_signed_channels_keep_sign(self):
        p=demo(); vals=[evaluate(p,t/10)['hair.idle'] for t in range(0,60)]
        self.assertTrue(min(vals)<0<max(vals))
if __name__=='__main__':unittest.main()
