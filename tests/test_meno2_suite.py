import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from research_lab.meno2_campaign import create_campaign, run_campaign, ScriptedProvider
from research_lab.storage import read_json, write_new
from research_lab.providers import ProviderError


class SuiteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def config(self, seed=1):
        return dict(blocks=1, seed=seed, mechanisms=['defective_sensors'],
                    bootstrap_replicates=100, arms=['exact_facts', 'structured_audit'])

    def test_selected_arms_and_defaults(self):
        self.assertEqual(create_campaign(self.root/'selected', self.config())['planned_trials'], 9)
        result = run_campaign(self.root/'selected')
        self.assertEqual(result['status']['completed_trials'], 9)
        self.assertEqual({r['condition'] for r in result['rows']}, {'initial','exact_facts','structured_audit'})
        for args, n in [({},15), ({'campaign':'B'},3), ({'campaign':'D','regime':'II'},18)]:
            c = self.config(); c.pop('arms'); c.update(args)
            self.assertEqual(create_campaign(self.root/str(n), c)['planned_trials'], n)

    def test_invalid_arms(self):
        for arms in ([], ['initial'], ['repair'], ['exact_facts']*2, 'exact_facts'):
            with self.assertRaises(ValueError):
                create_campaign(self.root/'bad', dict(self.config(), arms=arms))
        with self.assertRaises(ValueError):
            create_campaign(self.root/'bad', dict(self.config(), campaign='B'))

    def test_decimal_budget_and_nonfinite_rejected(self):
        from research_lab.meno2_suite import budget_allows
        self.assertTrue(budget_allows('6.86656', '3.13344', '10'))
        self.assertFalse(budget_allows('6.866561', '3.13344', '10'))
        for bad in ('NaN', '-1', 'Infinity'):
            with self.assertRaises(ValueError):
                budget_allows(bad, '1', '10')

    def test_suite_replay_and_unequal_coverage(self):
        from research_lab.meno2_suite import create_suite, run_suite, inspect_suite, export_suite
        root = self.root/'suite'
        create_suite(root, [self.config(1),self.config(2)], cap='0', metadata={'test':True})
        report=run_suite(root)
        self.assertEqual(report['completed_blocks'], 2)
        self.assertEqual(report['attempted'], 18)
        self.assertEqual(report['completed']['conditions']['initial']['balanced_decision'], .5)
        self.assertEqual(report['coverage']['defective_sensors']['completed'], 2)
        export_suite(root,self.root/'export')
        import subprocess,sys
        replay=subprocess.run([sys.executable,'-B',str(self.root/'export'/'reproduce.py')],capture_output=True,text=True)
        self.assertEqual(replay.returncode,0,replay.stderr)
        self.assertIn('VERIFIED',replay.stdout)
        self.assertEqual(run_suite(root),report)
        (root/'blocks'/'block-01'/'campaign.json').write_text('{}')
        with self.assertRaises(ValueError): inspect_suite(root)

    def test_uncertain_launch_stops_never_retries(self):
        from research_lab.meno2_suite import create_suite, run_suite
        class Uncertain(ScriptedProvider):
            calls=0
            def generate(self,request):
                self.calls+=1
                raise ProviderError('transport_uncertain')
        p=Uncertain();root=self.root/'suite'
        create_suite(root,[self.config(1),self.config(2)],cap='0')
        first=run_suite(root,providers={'mock':p})
        self.assertEqual(first['stop_reason'],'operational_failure')
        self.assertEqual(first['launched_blocks'],1)
        run_suite(root,providers={'mock':p})
        self.assertEqual(p.calls,1)
        self.assertEqual(first['unexecuted_blocks'],1)

    def test_missing_launched_campaign_fails_closed(self):
        from research_lab.meno2_suite import create_suite, run_suite
        root=self.root/'suite'
        create_suite(root,[self.config()],cap='0')
        write_new(root/'launches'/'block-01.json', {'reservation_usd':'0'})
        with self.assertRaises(ValueError): run_suite(root)

    def test_usage_limit_incident_stops_despite_complete_responses(self):
        from research_lab import meno2_suite as suite
        root=self.root/'suite'
        suite.create_suite(root,[self.config(1),self.config(2)],cap='0')
        original=suite.inspect_campaign
        def inspect(path):
            report=original(path)
            if report['status']['status']=='complete':
                report['runs'][0]['status']='usage_limit_exceeded'
            return report
        with patch.object(suite,'inspect_campaign',side_effect=inspect):
            result=suite.run_suite(root)
        self.assertEqual(result['stop_reason'],'operational_failure')
        self.assertEqual(result['launched_blocks'],1)
        self.assertEqual(result['completed_blocks'],0)

    def test_actual_spending_gate_and_unexecuted_denominators(self):
        from research_lab import meno2_suite as suite
        root=self.root/'suite'
        second=dict(self.config(2),mechanisms=['causal_reversal'])
        suite.create_suite(root,[self.config(1),second],cap='0')
        original=suite.inspect_campaign
        def inspect(path):
            report=original(path)
            if report['status']['attempted']:
                report['status']['observed_cost_usd']='0.00001'
            return report
        with patch.object(suite,'inspect_campaign',side_effect=inspect):
            result=suite.run_suite(root)
        self.assertEqual(result['stop_reason'],'budget_stop')
        self.assertEqual(result['attempted'],9)
        self.assertEqual(result['completed']['conditions']['initial']['balanced_decision'],.5)
        self.assertEqual(result['planned']['conditions']['initial']['balanced_decision'],.25)
        self.assertEqual(result['coverage']['causal_reversal']['completed'],0)
        self.assertFalse((root/'launches'/'block-02.json').exists())

    def test_equal_family_and_block_weighted_are_distinct(self):
        from research_lab.meno2_suite import _summary
        from research_lab.meno2_campaign import inspect_campaign
        import copy
        create_campaign(self.root/'one',self.config(1))
        run_campaign(self.root/'one')
        rows=inspect_campaign(self.root/'one')['rows']
        combined=[]
        for i,family in enumerate(('family-a','family-a','family-b')):
            block=copy.deepcopy(rows)
            for r in block:
                r['id']+=str(i);r['block_id']+=str(i);r['case_id']+=str(i)
                r['mechanism']=family
                if i==2 and r['role']=='S':
                    r['score']['coherent_publication']=True
            combined.extend(block)
        result=_summary(combined,{'analysis_seed':1,'bootstrap_replicates':100})
        self.assertAlmostEqual(result['conditions']['initial']['balanced_decision'],2/3)
        self.assertEqual(result['equal_observed_family_balanced_decision']['initial'],.75)
