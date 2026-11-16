"""Reject inconsistent report-derived accounting; never infer absent raw scores."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReportedSummaryTests(unittest.TestCase):
    def run_verifier(self, path):
        return subprocess.run([sys.executable, '-B', str(ROOT/'tools'/'verify_reported_summary.py'),
                               str(path)], capture_output=True, text=True)

    def test_checked_report_summary_has_executable_accounting(self):
        result = self.run_verifier(ROOT/'data'/'reported_suite_summary.json')
        self.assertEqual(result.returncode, 0, result.stderr)
        value = json.loads(result.stdout)
        self.assertEqual(value['observed_cost_usd'], '6.94651')
        self.assertEqual(value['next_gate_usd'], '10.07995')
        self.assertEqual(value['complete_ledger_rows'], 14)
        self.assertEqual(value['planned_ledger_rows'], 16)
        self.assertFalse(value['raw_response_replay'])

    def test_inconsistent_cost_seed_order_counts_and_settings_are_rejected(self):
        value = json.loads((ROOT/'data'/'reported_suite_summary.json').read_text())
        variants = []
        bad = copy.deepcopy(value); bad['blocks'][0]['observed_cost_usd'] = '0.48469'; variants.append(bad)
        bad = copy.deepcopy(value); bad['blocks'][1]['world_seed'] += 1; variants.append(bad)
        bad = copy.deepcopy(value); bad['blocks'][0]['family'] = 'stale_evidence'; variants.append(bad)
        bad = copy.deepcopy(value); bad['blocks'][0]['gate_usd'] = '0'; variants.append(bad)
        bad = copy.deepcopy(value); bad['blocks'][14]['attempts'] = 9; variants.append(bad)
        bad = copy.deepcopy(value); bad['reported_totals']['completed_requests'] = 125; variants.append(bad)
        bad = copy.deepcopy(value); bad['reported_frozen_settings']['regime'] = 'II'; variants.append(bad)
        bad = copy.deepcopy(value); bad['blocks'][0]['balanced_decision']['initial'] = '0'; variants.append(bad)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'changed.json'
            for i, variant in enumerate(variants):
                with self.subTest(mutation=i):
                    path.write_text(json.dumps(variant))
                    result = self.run_verifier(path)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn('ERROR:', result.stderr)

