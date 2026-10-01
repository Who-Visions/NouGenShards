import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from nougen_shards import dashboard_live, dynamic_api

class DashboardDiscoveryTests(unittest.TestCase):
    def test_registry_probe_preserves_missing_remote_hardware(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / 'nodes.json').write_text(json.dumps({'remote': {'name':'Remote', 'transport_node':'remote', 'ip':'old.local', 'ports':[11434]}}))
            (home / 'fleet_hosts.json').write_text(json.dumps({'nodes':{'remote':{'ip':'192.0.2.80'}}}))
            hardware = dict(gpu=None, ram='8.0 GB', temperature=None, vram_used_pct=None)
            with patch.object(dashboard_live, 'get_json', return_value=None), patch.object(dashboard_live, 'local_hardware', return_value=hardware):
                nodes = dashboard_live.fleet_nodes(home)
            remote = next(n for n in nodes if n['name']=='Remote')
            self.assertEqual(remote['ip'], '192.0.2.80')
            self.assertEqual(remote['status'], 'unreachable')
            self.assertIsNone(remote['ram'])
            self.assertIsNone(remote['player'])
            self.assertTrue(any(n['is_local'] for n in nodes))

    def test_empty_and_zero_usage_are_distinct(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(dynamic_api, 'DAILIES_DIR', directory):
            self.assertFalse(dynamic_api.get_machine_breakdown('fleet','all')['ledger_present'])
            machine=Path(directory)/'published-machine'; machine.mkdir()
            (machine/'2026-01-01.json').write_text(json.dumps({'totals':{},'invocations':0}))
            result=dynamic_api.get_machine_breakdown('fleet','all')
            self.assertTrue(result['ledger_present'])
            self.assertEqual(result['total_tokens'],0)
            self.assertIsNone(result['estimated_cost'])

    def test_usage_aggregation_has_no_invented_prices_or_requests(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(dynamic_api,'DAILIES_DIR',directory):
            machine=Path(directory)/'published-machine'; machine.mkdir()
            (machine/'2026-01-01.json').write_text(json.dumps({'totals':{'input_tokens':10,'output_tokens':20,'cache_read':30},'invocations':2,'models':{'actual-model':{'input_tokens':10,'output_tokens':20,'cache_read':30}}}))
            result=dynamic_api.get_machine_breakdown('fleet','all')
            self.assertEqual(result['total_tokens'],60)
            self.assertEqual(result['invocations'],2)
            self.assertEqual(result['by_model'][0]['model'],'actual-model')
            self.assertIsNone(result['by_model'][0]['invocations'])
            self.assertIsNone(result['by_model'][0]['estimated_cost'])
            self.assertEqual(result['cache_hit_rate'],75)

    def test_relay_preserves_actual_state(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ', {'NOUGEN_HANDOFFS_DIR':directory}):
            (Path(directory)/'open-leg.json').write_text(json.dumps({'goal':'Still working','state':'open','created_utc':'2026-01-01T00:00:00Z'}))
            row=dashboard_live.relay_feed()[0]
            self.assertEqual(row['live_status'],'open')
            self.assertIsNone(row['tasks_done'])

if __name__ == '__main__':
    unittest.main()
