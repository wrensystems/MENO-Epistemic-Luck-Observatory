import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import os
import shutil
from unittest.mock import patch

from research_lab.meno2_campaign import (create_campaign, run_campaign, inspect_campaign,
    plan_campaign, export_campaign, ScriptedProvider)
from research_lab.providers import ProviderError, AnthropicProvider
from research_lab.storage import read_json, file_hash


class MenoCampaignTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / 'campaign'

    def create(self, **extra):
        return create_campaign(self.root, dict(blocks=1, bootstrap_replicates=100,
                                              mechanisms=['defective_sensors'], **extra))

    def test_complete_parent_lineage_resume_and_independent_rescoring(self):
        plan = self.create()
        self.assertEqual(plan['planned_trials'], 15)
        report = run_campaign(self.root)
        self.assertEqual(report['status']['completed_trials'], 15)
        self.assertEqual(report['status']['valid_responses'], 15)
        self.assertEqual(report['status']['evidence_kind'], 'synthetic')
        parents = {r['id']: r for r in report['rows'] if r['condition'] == 'initial'}
        for row in report['rows']:
            if row['parent_id']:
                text = parents[row['parent_id']]['invocation']['response']['text']
                self.assertIn(json.dumps(text), row['invocation']['intent']['request']['prompt'])
                self.assertIsNotNone(row['parent_response_hash'])
        before = {str(p): file_hash(p) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(run_campaign(self.root)['status']['attempted'], 15)
        self.assertEqual(before, {str(p): file_hash(p) for p in self.root.rglob('*') if p.is_file()})
        target = Path(self.tmp.name) / 'release'
        export_campaign(self.root, target)
        result = subprocess.run([sys.executable, '-B', 'reproduce.py'], cwd=target, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('VERIFIED', result.stdout)
        exported_scores = read_json(target / 'scores.json')
        self.assertEqual(exported_scores[report['rows'][0]['id']]['scoring_version'], 'meno2-2')
        exported_scores[report['rows'][0]['id']]['coherent_publication'] = True
        (target / 'scores.json').write_text(json.dumps(exported_scores))
        manifest = read_json(target / 'SHA256.json')
        manifest['scores.json'] = file_hash(target / 'scores.json')
        (target / 'SHA256.json').write_text(json.dumps(manifest))
        changed = subprocess.run([sys.executable, '-B', 'reproduce.py'], cwd=target, capture_output=True, text=True)
        self.assertNotEqual(changed.returncode, 0)
        self.assertIn('Rescoring differs', changed.stderr)

    def test_contradictory_publications_are_archived_and_reported_separately(self):
        self.create()
        class Contradictory(ScriptedProvider):
            def generate(self, request):
                result = super().generate(request)
                value = json.loads(result['text'])
                value.update(answer='deny', action='publish', p_true=.99, support_judgment='supported')
                result['text'] = json.dumps(value)
                result['raw'] = {'synthetic': True, 'text': result['text']}
                return result
        report = run_campaign(self.root, providers={'mock': Contradictory()})
        self.assertEqual(report['status']['valid_responses'], 15)
        self.assertEqual(report['status']['invalid_responses'], 0)
        self.assertEqual(report['status'].get('contradictory_publications'), 15)
        self.assertEqual(report['status']['incidents'], {'contradictory_publication': 15})
        for row in report['rows']:
            self.assertEqual(row['invocation']['response']['text'], row['invocation']['response']['raw']['text'])
            self.assertEqual(json.loads(row['invocation']['response']['text'])['answer'], 'deny')
        group = next(iter(report['analysis']['groups'].values()))
        self.assertEqual(group['conditions']['structured_audit']['balanced_decision'], 0)
        self.assertEqual(group['conditions']['structured_audit']['contradictory_publication_rate'], 1)

    def test_initial_justification_context_and_sham_copy_are_separate_from_audit(self):
        self.create(campaign='D', regime='II', world_options={'reliability': '0.99', 'target_prior': '0.5'})
        class Citing(ScriptedProvider):
            def generate(self, request):
                result = super().generate(request)
                prompt = request['prompt'].lstrip()
                basis = ['m1'] if prompt.startswith('Review the record transcript') else ['e1']
                if prompt.startswith('Reconsider your frozen initial response using the additional independent'):
                    basis = ['e1', 'e3']
                result['text'] = json.dumps(dict(answer='affirm', action='publish', p_true=.99,
                    support_judgment='supported', basis_ids=basis, explanation='Scripted visible evidence citation.'))
                result['raw'] = {'synthetic': True, 'text': result['text']}
                return result
        report = run_campaign(self.root, providers={'mock': Citing()})
        lucky = {r['condition']: r['score'] for r in report['rows'] if r['role'] == 'L'}
        self.assertEqual(lucky['sham']['response']['basis_ids'], ['m1'])
        self.assertIs(lucky['initial']['observed_response_labels']['gettier_like_response_pattern'], True)
        for condition in ('initial', 'reflection', 'sham'):
            self.assertTrue(lucky[condition]['observed_response_labels']['gettier_like_response_pattern'])
            self.assertEqual(lucky[condition]['initial_oracle']['probability_exact'], '1001/1010')
        for condition in ('exact_facts', 'structured_audit', 'repair'):
            self.assertFalse(lucky[condition]['observed_response_labels']['gettier_like_response_pattern'])
        self.assertTrue(lucky['repair']['justification_repair'])
        provenance = report['status']['scoring_provenance']
        self.assertEqual(provenance['frozen_scoring_version'], 'meno2-2')
        self.assertEqual(provenance['applied_scoring_version'], 'meno2-2')
        self.assertFalse(provenance['read_only_rescore'])

    def test_legacy_version_inspection_is_explicit_and_does_not_rewrite_archive(self):
        self.create()
        # A temporary pre-version-metadata fixture; no existing evidence is edited.
        frozen = read_json(self.root / 'campaign.json')
        frozen.pop('scoring_version', None)
        frozen.pop('analysis_version', None)
        (self.root / 'campaign.json').write_text(json.dumps(frozen))
        (self.root / 'campaign.sha256.json').write_text(json.dumps({'sha256': file_hash(self.root / 'campaign.json')}))
        before = {str(p): file_hash(p) for p in self.root.rglob('*') if p.is_file()}
        report = inspect_campaign(self.root)
        provenance = report['status'].get('scoring_provenance', {})
        self.assertEqual(provenance.get('frozen_scoring_version'), 'meno2-1')
        self.assertEqual(provenance['applied_scoring_version'], 'meno2-2')
        self.assertTrue(provenance['read_only_rescore'])
        self.assertEqual(report['analysis']['scoring_provenance'], provenance)
        self.assertEqual(before, {str(p): file_hash(p) for p in self.root.rglob('*') if p.is_file()})

    def test_uncertain_parent_stops_and_resume_never_reissues(self):
        self.create()
        class Uncertain(ScriptedProvider):
            calls = 0
            def generate(self, request):
                self.calls += 1
                raise ProviderError('transport_uncertain')
        provider = Uncertain()
        first = run_campaign(self.root, providers={'mock': provider})
        self.assertEqual(first['status']['attempted'], 1)
        self.assertEqual(first['status']['completed_trials'], 0)
        second = run_campaign(self.root, providers={'mock': provider})
        self.assertEqual(provider.calls, 1)
        self.assertEqual(second['status']['missing_trials'], 15)
        self.assertFalse((self.root / 'stages/model-0-followup').exists())

    def test_lost_archive_and_lost_stage_cannot_repeat_requests(self):
        self.create()
        run_campaign(self.root)
        stage = self.root / 'stages/model-0-initial'
        (stage / 'runs').rename(self.root / 'preserved-runs')
        with self.assertRaisesRegex(ValueError, 'archive is missing'):
            run_campaign(self.root)
        stage.rename(self.root / 'preserved-stage')
        with self.assertRaisesRegex(ValueError, 'stage is missing'):
            run_campaign(self.root)

    def test_unlaunched_partial_stage_recovers_without_overwriting(self):
        self.create()
        stage = self.root / 'stages/model-0-initial'
        stage.mkdir(parents=True)
        self.assertEqual(run_campaign(self.root)['status']['completed_trials'], 15)

    def test_truncated_output_retained_but_not_accepted(self):
        self.create()
        class Truncated(ScriptedProvider):
            def generate(self, request):
                result = super().generate(request)
                result['stop_reason'] = 'max_tokens'
                return result
        report = run_campaign(self.root, providers={'mock': Truncated()})
        incident = next(r for r in report['rows'] if r['operational_status'] == 'error')
        self.assertFalse(incident['score']['valid'])
        self.assertIsNone(incident['invocation']['response'])
        self.assertEqual(incident['invocation']['observed_response']['stop_reason'], 'max_tokens')

    def test_malformed_raw_body_and_usage_only_incomplete_remain_inspectable(self):
        for index, raw in enumerate((['malformed-provider-body'], {'status': 'incomplete',
                                     'usage': {'input_tokens': 12, 'output_tokens': 13}})):
            root = Path(self.tmp.name) / f'raw-{index}'
            create_campaign(root, {'blocks': 1, 'mechanisms': ['defective_sensors'], 'bootstrap_replicates': 100})
            class Received(ScriptedProvider):
                def generate(self, request):
                    raise ProviderError('response_uncertain' if index == 0 else 'incomplete_generation', raw=raw)
            report = run_campaign(root, providers={'mock': Received()})
            incident = next(r for r in report['rows'] if r['operational_status'] != 'missing')
            self.assertEqual(incident['invocation']['provider_raw'], raw)
            self.assertEqual(incident['incident_kind'], 'uncertain' if index == 0 else 'truncation_or_incomplete')

    def test_invalid_parent_preserved_without_repair(self):
        self.create()
        class Invalid(ScriptedProvider):
            def generate(self, request):
                result = super().generate(request)
                result['text'] = 'I decline to answer.'
                return result
        result = run_campaign(self.root, providers={'mock': Invalid()})
        self.assertEqual(result['status']['invalid_responses'], 15)
        group = next(iter(result['analysis']['groups'].values()))
        self.assertEqual(group['conditions']['structured_audit']['balanced_decision'], 0)

    def test_integrity_source_and_live_gates(self):
        self.create()
        with self.assertRaises(ValueError):
            run_campaign(self.root, live=True)
        path = self.root / 'campaign.json'
        value = read_json(path)
        value['config']['seed'] = 2
        path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):
            inspect_campaign(self.root)

    def test_transplanted_internally_valid_run_is_rejected(self):
        self.create()
        run_campaign(self.root)
        other = Path(self.tmp.name) / 'other'
        create_campaign(other, {'blocks': 1, 'bootstrap_replicates': 100,
                               'mechanisms': ['defective_sensors'], 'threshold': '0.9'})
        run_campaign(other)
        original = self.root / 'stages/model-0-initial/runs'
        original.rename(self.root / 'retained-original-runs')
        shutil.copytree(other / 'stages/model-0-initial/runs', original)
        with self.assertRaisesRegex(ValueError, 'run identity differs|snapshot does not belong'):
            inspect_campaign(self.root)

    def test_acquisition_initial_not_scored_as_hidden_discrimination(self):
        self.create(campaign='D', regime='II')
        report = run_campaign(self.root)
        self.assertEqual(report['status']['planned_trials'], 18)
        group = next(iter(report['analysis']['groups'].values()))
        self.assertEqual(group['conditions']['initial']['eligible_blocks'], 0)
        self.assertEqual(group['conditions']['structured_audit']['eligible_blocks'], 1)
        self.assertEqual(group['conditions']['repair']['eligible_blocks'], 0)
        repaired = [r for r in report['rows'] if r['condition'] == 'repair' and r['role'] == 'L'][0]
        self.assertTrue(repaired['score']['oracle']['publication_warranted'])

    def test_campaign_configuration_rejects_regime_mix_and_adaptive(self):
        with self.assertRaises(ValueError):
            self.create(campaign='C', regime='II')
        with self.assertRaises(ValueError):
            self.create(campaign='F')

    def test_initial_observability_campaign_has_only_parent_trials(self):
        self.create(campaign='B', regime='II')
        report = run_campaign(self.root)
        self.assertEqual(report['status']['planned_trials'], 3)
        self.assertEqual({r['condition'] for r in report['rows']}, {'initial'})
        self.assertFalse(any(r['eligible'] for r in report['rows']))

    def test_validation_controls_and_precise_reservations(self):
        self.create(campaign='A', world_options={'include_controls': True})
        report = inspect_campaign(self.root)
        self.assertEqual(report['status']['planned_trials'], 55)
        self.assertEqual(len(report['blocks'][0]['cases']), 11)
        other = Path(self.tmp.name) / 'decimal-budget'
        create_campaign(other, {'blocks': 1, 'bootstrap_replicates': 100,
            'mechanisms': ['defective_sensors'], 'max_cost_usd': 100,
            'models': [{'id': 'mock', 'provider': 'mock', 'model': 'mock-v1',
                'input_usd_per_million': 2.1234567891234567, 'output_usd_per_million': 10,
                'max_cost_usd': 100}]})
        self.assertEqual(run_campaign(other)['status']['completed_trials'], 15)

    def test_claude_contract_offline_budget_and_no_credentials_archived(self):
        config = {'blocks': 1, 'mechanisms': ['defective_sensors'], 'bootstrap_replicates': 100,
                  'max_cost_usd': 2, 'models': [{'id': 'claude-fixture', 'provider': 'anthropic',
                    'model': 'claude-fixture', 'evidence_kind': 'model_generated', 'protocol_status': 'frozen',
                    'input_usd_per_million': 1, 'output_usd_per_million': 5,
                    'max_cost_usd': 2, 'max_requests': 15}]}
        create_campaign(self.root, config)
        with self.assertRaises(ValueError):
            run_campaign(self.root)
        requests = []
        def post(path, payload, key, timeout, version):
            if path.endswith('count_tokens'):
                return {'input_tokens': 20}
            requests.append(payload)
            text = ScriptedProvider().generate({'prompt': ''})['text']
            return {'model': 'claude-fixture-resolved', 'content': [{'type': 'text', 'text': text}],
                    'stop_reason': 'end_turn', 'usage': {'input_tokens': 20, 'output_tokens': 80}}
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'public-test-credential'}):
            provider = AnthropicProvider(post=post)
        report = run_campaign(self.root, live=True, providers={'claude-fixture': provider})
        self.assertEqual(len(requests), 15)
        self.assertEqual(report['status']['completed_trials'], 15)
        self.assertGreater(float(report['status']['reserved_usd']), 0)
        run_campaign(self.root, live=True, providers={'claude-fixture': provider})
        self.assertEqual(len(requests), 15)
        for path in self.root.rglob('*.json'):
            self.assertNotIn('public-test-credential', path.read_text())
