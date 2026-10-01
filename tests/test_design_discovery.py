import importlib.util
import unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('discover',Path(__file__).resolve().parents[1]/'tools/nougendesign_discover.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

class DiscoveryTests(unittest.TestCase):
    def test_ids(self):
        self.assertEqual(m.reference('https://arxiv.org/pdf/2609.00476v1.pdf'),'2609.00476')
        self.assertEqual(m.reference('hep-th/9711200'),'hep-th/9711200')
        with self.assertRaises(ValueError): m.reference('https://example.com/2609.00476')

    def test_citations_include_plain_ids_and_deduplicate(self):
        html='<a href="https://arxiv.org/abs/2609.00476v2">paper</a><p>arXiv:2609.00476 arXiv:2106.14127</p>'
        self.assertEqual(m.citations(html),['2609.00476','2106.14127'])

    def test_bounded_cycles_and_failure_provenance(self):
        calls=[]
        def fetch(ref,kind):
            calls.append((ref,kind))
            if ref=='2106.14127': raise OSError('unreachable')
            if kind=='abs': return '<meta name="citation_title" content="Visual Design">'
            return '<p>arXiv:2609.00476 arXiv:2106.14127</p>'
        result=m.discover(['2609.00476'],fetch,depth=2,max_papers=2)
        self.assertEqual(len(result['papers']),2)
        self.assertEqual(result['papers'][1]['status'],'unavailable')
        self.assertEqual(result['papers'][1]['discovered_from'],'2609.00476')
        self.assertEqual(calls.count(('2609.00476','abs')),1)

    def test_depth_zero_never_fetches_full_text(self):
        calls=[]
        def fetch(ref,kind):
            calls.append(kind); return ''
        m.discover(['2609.00476'],fetch,depth=0)
        self.assertEqual(calls,['abs'])

if __name__=='__main__': unittest.main()
