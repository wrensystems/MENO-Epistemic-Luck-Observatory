import json
from pathlib import Path
import tempfile
import threading
import unittest
import urllib.request
import urllib.error

from research_lab.meno2_campaign import create_campaign, run_campaign
from research_lab.meno2_observatory import make_server
from research_lab.storage import file_hash


class ObservatoryTests(unittest.TestCase):
    def test_completed_mock_inspection_views_and_no_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'campaign'
            create_campaign(root, {'blocks': 1, 'bootstrap_replicates': 100, 'mechanisms': ['defective_sensors']})
            run_campaign(root)
            before = {str(p): file_hash(p) for p in root.rglob('*') if p.is_file()}
            server = make_server(root, 0)
            worker = threading.Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                url = f'http://127.0.0.1:{server.server_port}'
                with urllib.request.urlopen(url) as stream:
                    page = stream.read().decode()
                for text in ('Case microscope', 'Comparison explorer', 'Incidents &amp; lineage', 'Campaign overview'):
                    self.assertIn(text, page)
                with urllib.request.urlopen(url + '/api/report') as stream:
                    report = json.load(stream)
                self.assertEqual(report['status']['completed_trials'], 15)
                self.assertEqual(report['status']['scoring_provenance']['applied_scoring_version'], 'meno2-2')
                condition = next(iter(next(iter(report['analysis']['groups'].values()))['conditions'].values()))
                self.assertEqual(condition['contradictory_publications'], 0)
                self.assertEqual(condition['structural_counterfactual_publication_exposure_rate'], 0)
                with urllib.request.urlopen(url + '/api/report?perspective=model') as stream:
                    visible = json.load(stream)
                for row in visible['rows']:
                    self.assertNotIn('oracle', row)
                    self.assertNotIn('role', row)
                    self.assertNotIn('world', row)
                    self.assertIsNotNone(row['request'])
                with self.assertRaises(urllib.error.HTTPError) as caught:
                    urllib.request.urlopen(urllib.request.Request(url + '/api/report', data=b'{}', method='POST'))
                self.assertEqual(caught.exception.code, 501)
            finally:
                server.shutdown()
                server.server_close()
                worker.join()
            self.assertEqual(before, {str(p): file_hash(p) for p in root.rglob('*') if p.is_file()})
