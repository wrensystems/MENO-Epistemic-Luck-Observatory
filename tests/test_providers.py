import io
import json
import os
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from research_lab.providers import AnthropicProvider, ProviderError, MockProvider


REQUEST = {'model': 'test-model', 'prompt': 'What is 2 + 2?', 'max_output_tokens': 16,
           'temperature': 0, 'timeout_seconds': 1, 'api_version': '2023-06-01'}


class ProviderTests(unittest.TestCase):
    def test_mock_solves_prompt_not_expected_label(self):
        result = MockProvider().generate(REQUEST)
        self.assertEqual(result['text'], '4')
        self.assertEqual(result['model'], 'mock-v1')

    def test_anthropic_payload_usage_and_request_id(self):
        seen = []
        def post(path, payload, key, timeout, version):
            seen.append((path, payload))
            if path.endswith('count_tokens'):
                return {'input_tokens': 12}
            return {'id': 'msg_fixture', 'type': 'message', 'role': 'assistant',
                    'model': 'test-model-resolved', 'content': [{'type': 'text', 'text': '4'}],
                    'stop_reason': 'end_turn', 'stop_sequence': None,
                    'usage': {'input_tokens': 12, 'output_tokens': 1}, '_request_id': 'req_fixture'}
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-only'}):
            provider = AnthropicProvider(post=post)
            self.assertEqual(provider.count_tokens(REQUEST), 12)
            result = provider.generate(REQUEST)
        self.assertEqual(result['output_tokens'], 1)
        self.assertEqual(result['request_id'], 'req_fixture')
        self.assertEqual(result['model'], 'test-model-resolved')
        self.assertEqual(seen[1][1]['messages'], [{'role': 'user', 'content': 'What is 2 + 2?'}])
        self.assertNotIn('expected', seen[1][1])
        self.assertNotIn('test-only', json.dumps(result))

    def test_http_failure_does_not_echo_secret_or_prompt(self):
        error = HTTPError('https://api.anthropic.com/v1/messages', 429,
                          'sensitive body', {'retry-after': '2'}, io.BytesIO(b'private text'))
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-only'}), \
                patch('urllib.request.OpenerDirector.open', side_effect=error):
            with self.assertRaises(ProviderError) as context:
                AnthropicProvider().generate(REQUEST)
        self.assertTrue(context.exception.retryable)
        self.assertEqual(context.exception.retry_after, 2)
        self.assertNotIn('private', str(context.exception))

    def test_missing_key_fails_without_network(self):
        with patch.dict(os.environ, {}, clear=True), self.assertRaises(ValueError):
            AnthropicProvider()

    def test_malformed_content_returns_uncertain_error_with_raw(self):
        raw = {'content': [None], 'usage': {'input_tokens': 12, 'output_tokens': 7}}
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-only'}):
            with self.assertRaises(ProviderError) as context:
                AnthropicProvider(post=lambda *args: raw).generate(REQUEST)
        self.assertEqual(context.exception.raw, raw)


if __name__ == '__main__':
    unittest.main()
