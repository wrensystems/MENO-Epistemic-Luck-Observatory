import json
from pathlib import Path
import tempfile
import unittest

from research_lab.engine import run, verify, inspect_run
from research_lab.providers import MockProvider, ProviderError
from research_lab.studies import init_study


class Flaky(MockProvider):
    def __init__(self):
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        if self.calls == 1:
            raise ProviderError('rate_limit', retryable=True)
        return super().generate(request)


class Crash(MockProvider):
    def generate(self, request):
        raise KeyboardInterrupt()


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.study = init_study(Path(self.tmp.name), 'example')

    def edit(self, **values):
        path = self.study / 'study.json'
        config = json.loads(path.read_text())
        config.update(values)
        path.write_text(json.dumps(config))

    def test_complete_archive_and_idempotent_resume(self):
        result = run(self.study)
        directory = Path(result['run_dir'])
        self.assertEqual(result['completed'], 4)
        self.assertEqual(result['status'], 'complete')
        self.assertEqual(result['evidence_kind'], 'synthetic')
        before = {str(p): p.read_bytes() for p in directory.rglob('*.json')}
        resumed = run(self.study, resume=directory)
        self.assertEqual(resumed['requests'], 4)
        self.assertEqual(before, {str(p): p.read_bytes() for p in directory.rglob('*.json')})
        self.assertEqual(verify(directory)['completed'], 4)

    def test_retry_preserves_each_attempt(self):
        result = run(self.study, provider=Flaky(), sleep=lambda _: None)
        self.assertEqual(result['completed'], 4)
        self.assertEqual(result['requests'], 5)
        self.assertEqual(len(list(Path(result['run_dir']).glob('attempts/*/error.json'))), 1)

    def test_request_limit_respected_across_resume(self):
        self.edit(max_requests=2)
        result = run(self.study)
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(result['completed'], 2)
        self.assertEqual(run(self.study, resume=Path(result['run_dir']))['requests'], 2)

    def test_ambiguous_crash_requires_explicit_retry_and_keeps_reservation(self):
        with self.assertRaises(KeyboardInterrupt):
            run(self.study, provider=Crash())
        directory = next((self.study / 'runs').iterdir())
        result = run(self.study, resume=directory)
        self.assertEqual(result['status'], 'uncertain')
        result = run(self.study, resume=directory, retry_uncertain=True)
        self.assertEqual(result['requests'], 5)
        self.assertEqual(result['completed'], 4)

    def test_snapshot_change_refuses_resume(self):
        result = run(self.study)
        self.edit(seed=7)
        with self.assertRaises(ValueError):
            run(self.study, resume=Path(result['run_dir']))

    def test_tampering_detected(self):
        result = run(self.study)
        directory = Path(result['run_dir'])
        response = next(directory.glob('attempts/*/response.json'))
        response.write_text('{}')
        with self.assertRaises(ValueError):
            verify(directory)

    def test_live_flag_does_not_change_mock_to_real(self):
        with self.assertRaises(ValueError):
            run(self.study, live=True)

    def test_live_budget_before_generate_and_no_key_without_activation(self):
        self.edit(provider='anthropic', evidence_kind='model_generated', model='test-model',
                  protocol_status='frozen', max_cost_usd=0.001,
                  input_usd_per_million=1, output_usd_per_million=5)
        with self.assertRaises(ValueError):
            run(self.study)

        class CountOnly(MockProvider):
            name = 'anthropic'
            def generate(self, request):
                raise AssertionError('Budget must block this')

        result = run(self.study, live=True, provider=CountOnly())
        self.assertEqual(result['status'], 'budget_exhausted')
        self.assertEqual(result['requests'], 0)

    def test_terminal_failure_is_visible_and_not_retried_on_resume(self):
        class Failed(MockProvider):
            def generate(self, request):
                raise ProviderError('authentication', retryable=False)
        result = run(self.study, provider=Failed())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['completed'], 0)
        self.assertEqual(result['requests'], 1)
        self.assertEqual(run(self.study, resume=Path(result['run_dir']))['requests'], 1)

    def test_lock_prevents_second_writer(self):
        result = run(self.study)
        directory = Path(result['run_dir'])
        (directory / '.lock').write_text('{}')
        with self.assertRaises(ValueError):
            run(self.study, resume=directory)

    def test_truncated_generation_preserves_usage_but_is_not_scored(self):
        class Truncated(MockProvider):
            def generate(self, request):
                result = super().generate(request)
                result.update(stop_reason='max_tokens', output_tokens=64)
                return result
        result = run(self.study, provider=Truncated())
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['completed'], 0)
        self.assertEqual(result['output_tokens'], 64)

    def test_uncertain_retry_at_attempt_limit_never_appears_pending(self):
        self.edit(max_attempts=1)
        with self.assertRaises(KeyboardInterrupt):
            run(self.study, provider=Crash())
        directory = next((self.study / 'runs').iterdir())
        result = run(self.study, resume=directory, retry_uncertain=True)
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(result['requests'], 1)

    def test_over_input_limit_refuses_generation(self):
        self.edit(max_input_tokens=1)
        with self.assertRaises(ValueError):
            run(self.study)
        directory = next((self.study / 'runs').iterdir())
        self.assertEqual(inspect_run(directory)['requests'], 0)

    def test_source_change_refuses_resume(self):
        from unittest.mock import patch
        result = run(self.study)
        with patch('research_lab.engine.source_hashes', return_value={'engine.py': 'changed'}):
            with self.assertRaises(ValueError):
                run(self.study, resume=Path(result['run_dir']))

    def test_missing_attempt_suffix_or_directory_fails_closed(self):
        for whole_directory in (False, True):
            with self.subTest(whole_directory=whole_directory):
                result = run(self.study)
                directory = Path(result['run_dir'])
                missing = directory / 'attempts' if whole_directory else sorted((directory / 'attempts').iterdir())[-1]
                missing.rename(directory / 'removed-evidence')
                with self.assertRaises(ValueError):
                    verify(directory)
                with self.assertRaises(ValueError):
                    run(self.study, resume=directory)

    def test_changed_seal_status_is_detected_even_when_valid(self):
        for status in ('succes', 'error', 'uncertain'):
            with self.subTest(status=status):
                result = run(self.study)
                directory = Path(result['run_dir'])
                path = sorted(directory.glob('attempts/*/seal.json'))[-1]
                seal = json.loads(path.read_text())
                seal['status'] = status
                path.write_text(json.dumps(seal))
                with self.assertRaises(ValueError):
                    verify(directory)

    def test_failed_provider_parse_preserves_raw_and_known_usage(self):
        from unittest.mock import patch
        import os
        from research_lab.providers import AnthropicProvider
        self.edit(provider='anthropic', evidence_kind='model_generated', model='test-model',
                  protocol_status='frozen', max_cost_usd=1,
                  input_usd_per_million=1, output_usd_per_million=5)
        raw = {'model': 'test-model', 'content': [{'type': 'unknown', 'payload': 'RETAIN_RAW'}],
               'usage': {'input_tokens': 12, 'output_tokens': 7}, 'stop_reason': 'end_turn'}
        def post(path, *args):
            return {'input_tokens': 12} if path.endswith('count_tokens') else raw
        with patch.dict(os.environ, {'ANTHROPIC_API_KEY': 'test-only'}):
            result = run(self.study, live=True, provider=AnthropicProvider(post=post))
        directory = Path(result['run_dir'])
        self.assertEqual(result['status'], 'uncertain')
        self.assertEqual(result['completed'], 0)
        self.assertEqual(result['input_tokens'], 12)
        self.assertEqual(result['output_tokens'], 7)
        self.assertAlmostEqual(float(result['observed_cost_usd']), 0.000047)
        preserved = list(directory.glob('attempts/*/provider_raw.json'))
        self.assertEqual(len(preserved), 1)
        self.assertEqual(json.loads(preserved[0].read_text()), raw)


if __name__ == '__main__':
    unittest.main()
