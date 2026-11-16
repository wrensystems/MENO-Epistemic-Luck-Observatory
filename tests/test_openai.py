import base64
import copy
import http.client
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from research_lab.openai_provider import OpenAIProvider, transport
from research_lab.cli import main
from research_lab.providers import ProviderError
from research_lab.studies import default_config, init_study, load_study, validate
from research_lab.engine import run, verify


REQUEST = {'model': 'gpt-6-luna', 'prompt': 'Return LAB_OK.', 'max_output_tokens': 128,
           'temperature': 0, 'timeout_seconds': 20, 'api_version': 'responses-v1'}
RESPONSE = {'id': 'resp_fixture', 'object': 'response', 'status': 'completed',
            'model': 'gpt-6-luna', 'error': None, 'incomplete_details': None,
            'output': [{'type': 'message', 'role': 'assistant', 'status': 'completed',
                        'content': [{'type': 'output_text', 'text': 'LAB_OK', 'annotations': []}]}],
            'usage': {'input_tokens': 12, 'output_tokens': 4, 'total_tokens': 16,
                      'input_tokens_details': {'cached_tokens': 0},
                      'output_tokens_details': {'reasoning_tokens': 0}}, '_request_id': 'req_fixture'}

SOL_REQUEST = dict(REQUEST, model='gpt-6.1-sol', reasoning_effort='medium',
                   temperature=None, max_output_tokens=512)
SOL_RESPONSE = copy.deepcopy(RESPONSE)
SOL_RESPONSE.update(model='gpt-6.1-sol', usage={
    'input_tokens': 12, 'output_tokens': 264, 'total_tokens': 276,
    'input_tokens_details': {'cached_tokens': 0, 'cache_write_tokens': 0},
    'output_tokens_details': {'reasoning_tokens': 260}})
SOL_RESPONSE['output'][0]['phase'] = 'final_answer'
SOL_RESPONSE['output'][:0] = [
    {'id': 'rs_fixture', 'type': 'reasoning', 'summary': [], 'encrypted_content': 'opaque-fixture'},
    {'id': 'msg_progress_fixture', 'type': 'message', 'role': 'assistant', 'status': 'completed',
     'phase': 'commentary', 'content': [{'type': 'output_text', 'text': 'Checking.', 'annotations': []}]}]


class OpenAITests(unittest.TestCase):
    def test_astra_max_profile_payload_and_price_floor(self):
        config = dict(self.sol_config(), model='gpt-6-astra', reasoning_effort='max',
                      max_output_tokens=32768, max_cost_usd=2,
                      input_usd_per_million=10, output_usd_per_million=50)
        cases = [{'id': 'probe', 'prompt': 'Return LAB_OK.', 'expected': 'LAB_OK'}]
        validate(config, cases)
        for change in ({'reasoning_effort': 'medium'}, {'temperature': 0},
                       {'input_usd_per_million': 2}, {'output_usd_per_million': 10}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                validate(dict(config, **change), cases)
        raw = copy.deepcopy(SOL_RESPONSE)
        raw['model'] = 'gpt-6-astra'
        provider = self.provider(raw)
        request = dict(SOL_REQUEST, model='gpt-6-astra', reasoning_effort='max', max_output_tokens=32768)
        self.assertEqual(provider.count_tokens(request), 12)
        result = provider.generate(request)
        self.assertEqual(result['model'], 'gpt-6-astra')
        self.assertEqual(result['output_tokens'], 264)
        self.assertEqual(self.requests[-1][2]['reasoning'], {'effort': 'max'})
        self.assertNotIn('temperature', self.requests[-1][2])

    def test_malformed_auth_headers_never_reach_network_or_cli_output(self):
        for variable in ('OPENAI_API_KEY', 'OPENAI_PROJECT_ID', 'OPENAI_ORG_ID'):
            with self.subTest(variable=variable):
                output = io.StringIO()
                values = {'OPENAI_API_KEY': 'public-test-only', variable: 'PUBLIC_DUMMY_SECRET\ninvalid'}
                with patch.dict(os.environ, values), patch('http.client.HTTPSConnection.connect') as connect, patch('sys.stderr', output):
                    result = main(['check-openai'])
                self.assertEqual(result, 2)
                self.assertNotIn('PUBLIC_DUMMY_SECRET', output.getvalue())
                connect.assert_not_called()

    def test_interrupted_response_retains_partial_body_and_request_id(self):
        partial = b'{"id":"resp_offline_fixture",'
        response = MagicMock()
        response.headers = {'x-request-id': 'req_interrupted_fixture'}
        response.read.side_effect = http.client.IncompleteRead(partial, 200)
        opener = MagicMock()
        opener.open.return_value.__enter__.return_value = response
        with patch('urllib.request.build_opener', return_value=opener), self.assertRaises(ProviderError) as caught:
            transport('POST', 'responses', {'model': 'gpt-6-luna'}, 'public-test-only', 20)
        self.assertEqual(caught.exception.code, 'response_uncertain')
        self.assertFalse(caught.exception.retryable)
        self.assertEqual(caught.exception.raw['_request_id'], 'req_interrupted_fixture')
        self.assertEqual(base64.b64decode(caught.exception.raw['body_base64']), partial)

    def provider(self, raw=None):
        self.requests = []
        def transport(method, path, payload, key, timeout):
            self.requests.append((method, path, payload))
            if path == 'responses/input_tokens':
                return {'object': 'response.input_tokens', 'input_tokens': 12}
            if method == 'GET':
                return {'id': path.split('/')[-1], 'object': 'model'}
            return copy.deepcopy(RESPONSE if raw is None else raw)
        with patch.dict(os.environ, {'OPENAI_API_KEY': 'test-only'}):
            return OpenAIProvider(transport=transport)

    def test_payload_and_usage_no_tools_no_remote_storage(self):
        p = self.provider()
        self.assertEqual(p.count_tokens(REQUEST), 12)
        result = p.generate(REQUEST)
        self.assertEqual(result['text'], 'LAB_OK')
        self.assertEqual(result['output_tokens'], 4)
        self.assertEqual(result['request_id'], 'req_fixture')
        payload = self.requests[-1][2]
        self.assertEqual(payload['input'], 'Return LAB_OK.')
        self.assertEqual(payload['max_output_tokens'], 128)
        self.assertEqual(payload['reasoning'], {'effort': 'none'})
        self.assertFalse(payload['store'])
        self.assertEqual(payload['tools'], [])
        self.assertNotIn('expected', payload)
        self.assertNotIn('test-only', json.dumps(result))

    def test_read_only_model_check_cannot_generate(self):
        p = self.provider()
        self.assertEqual(p.check_model('gpt-6-luna')['id'], 'gpt-6-luna')
        self.assertEqual(self.requests, [('GET', 'models/gpt-6-luna', None)])

    def test_incomplete_and_malformed_evidence_preserved(self):
        for raw in [dict(RESPONSE, status='incomplete'), dict(RESPONSE, output=[None])]:
            with self.subTest(raw=raw), self.assertRaises(ProviderError) as caught:
                self.provider(raw).generate(REQUEST)
            self.assertEqual(caught.exception.raw, raw)

    def test_sol_count_and_generation_use_medium_without_temperature(self):
        p = self.provider(SOL_RESPONSE)
        self.assertEqual(p.count_tokens(SOL_REQUEST), 12)
        self.assertEqual(self.requests[-1][2]['reasoning'], {'effort': 'medium'})
        result = p.generate(SOL_REQUEST)
        self.assertEqual(self.requests[-1][2]['reasoning'], {'effort': 'medium'})
        self.assertNotIn('temperature', self.requests[-1][2])
        self.assertEqual(self.requests[-1][2]['max_output_tokens'], 512)
        self.assertEqual(result['text'], 'LAB_OK')
        self.assertEqual(result['output_tokens'], 264)
        self.assertEqual(result['raw'], SOL_RESPONSE)

    def test_reasoning_without_final_text_or_with_tools_is_unscored(self):
        for output in [SOL_RESPONSE['output'][:2],
                       [{'type': 'reasoning', 'id': 'bad', 'summary': None}, *RESPONSE['output']],
                       [{'type': 'function_call', 'name': 'unexpected'}, *RESPONSE['output']]]:
            raw = dict(SOL_RESPONSE, output=output)
            with self.subTest(output=output), self.assertRaises(ProviderError) as caught:
                self.provider(raw).generate(SOL_REQUEST)
            self.assertEqual(caught.exception.raw, raw)

    def sol_config(self):
        return dict(default_config('sol-fixture'), provider='openai', model='gpt-6.1-sol',
                    reasoning_effort='medium', temperature=None, evidence_kind='model_generated',
                    protocol_status='frozen', api_version='responses-v1', max_attempts=1,
                    max_requests=1, max_input_tokens=1024, max_output_tokens=512,
                    max_cost_usd=.008, input_usd_per_million=2, output_usd_per_million=10,
                    conditions=[{'id': 'technical', 'instruction': 'Return the requested text.'}])

    def test_sol_configuration_rejects_unsupported_settings_and_stale_prices(self):
        cases = [{'id': 'probe', 'prompt': 'Return LAB_OK.', 'expected': 'LAB_OK'}]
        original = self.sol_config()
        validate(original, cases)
        missing_effort = dict(original)
        del missing_effort['reasoning_effort']
        invalid = [missing_effort] + [dict(original, **{key: value}) for key, value in [
            ('reasoning_effort', 'none'), ('reasoning_effort', 'high'), ('temperature', 0),
            ('model', 'gpt-6-astra'), ('input_usd_per_million', .1),
            ('output_usd_per_million', .5), ('max_input_tokens', 272001),
            ('max_output_tokens', 128001), ('provider', 'anthropic')]]
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ValueError):
                validate(config, cases)

    def test_sol_engine_preserves_effort_reasoning_usage_and_budget(self):
        with tempfile.TemporaryDirectory() as tmp:
            study = init_study(Path(tmp), 'sol-fixture')
            config = self.sol_config()
            (study / 'study.json').write_text(json.dumps(config))
            (study / 'cases.jsonl').write_text(json.dumps(
                {'id': 'probe', 'prompt': 'Return LAB_OK.', 'expected': 'LAB_OK'}))
            with self.assertRaises(ValueError):
                run(study, provider=self.provider(SOL_RESPONSE))
            result = run(study, live=True, provider=self.provider(SOL_RESPONSE))
            self.assertEqual((result['requests'], result['completed']), (1, 1))
            self.assertEqual(result['output_tokens'], 264)
            self.assertEqual(result['reserved_usd'], '0.007168')
            self.assertEqual(result['observed_cost_usd'], '0.002664')
            directory = Path(result['run_dir'])
            intent = json.loads((directory / 'attempts/000001/intent.json').read_text())
            self.assertEqual(intent['request']['reasoning_effort'], 'medium')
            self.assertEqual(verify(directory)['status'], 'complete')
            config['max_cost_usd'] = .001
            (study / 'study.json').write_text(json.dumps(config))
            blocked = run(study, live=True, provider=self.provider(SOL_RESPONSE))
            self.assertEqual(blocked['requests'], 0)
            self.assertEqual(self.requests, [])

    def test_defaults_and_default_lookup_select_sol_without_authorizing_spend(self):
        output = io.StringIO()
        with patch('sys.stdout', output), patch('http.client.HTTPSConnection.connect', side_effect=AssertionError('network forbidden')):
            self.assertEqual(main(['openai-defaults']), 0)
        defaults = json.loads(output.getvalue())
        self.assertEqual(defaults['model'], 'gpt-6.1-sol')
        self.assertEqual(defaults['reasoning_effort'], 'medium')
        self.assertIsNone(defaults['temperature'])
        self.assertEqual((defaults['input_usd_per_million'], defaults['output_usd_per_million']), (2, 10))
        self.assertNotIn('max_cost_usd', defaults)
        self.assertNotIn('protocol_status', defaults)
        self.assertEqual(default_config('still-offline')['provider'], 'mock')
        p = self.provider()
        with patch('research_lab.openai_provider.OpenAIProvider', return_value=p), patch('sys.stdout', io.StringIO()):
            self.assertEqual(main(['check-openai']), 0)
        self.assertEqual(self.requests, [('GET', 'models/gpt-6.1-sol', None)])

    def test_openai_live_gate_budget_and_single_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            study = init_study(Path(tmp), 'openai-fixture')
            config, _ = load_study(study)
            config.update(provider='openai', model='gpt-6-luna', evidence_kind='model_generated',
                          protocol_status='frozen', api_version='responses-v1', max_attempts=1,
                          max_requests=1, max_input_tokens=1024, max_output_tokens=128,
                          max_cost_usd=.001, input_usd_per_million=.1, output_usd_per_million=.5,
                          conditions=[{'id': 'technical', 'instruction': 'Return the requested text.'}])
            (study / 'study.json').write_text(json.dumps(config))
            (study / 'cases.jsonl').write_text(json.dumps({'id': 'probe', 'prompt': 'Return LAB_OK.', 'expected': 'LAB_OK'}))
            with self.assertRaises(ValueError):
                run(study, provider=self.provider())
            result = run(study, live=True, provider=self.provider())
            self.assertEqual(result['completed'], 1)
            self.assertEqual(result['requests'], 1)
            self.assertAlmostEqual(float(result['reserved_usd']), .0001664)
            self.assertAlmostEqual(float(result['observed_cost_usd']), .0000032)
            self.assertEqual(verify(result['run_dir'])['status'], 'complete')
            self.assertEqual(run(study, resume=result['run_dir'], live=True, provider=self.provider())['requests'], 1)


if __name__ == '__main__':
    unittest.main()
