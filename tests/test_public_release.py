"""Public-entrypoint regression tests: real subprocesses, no provider calls."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class PublicReleaseTests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, '-B', '-m', 'meno', *map(str, args)],
                              cwd=ROOT, capture_output=True, text=True)

    def test_public_help_exposes_meno_commands(self):
        result = self.cli('--help')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('python -m meno', result.stdout)
        self.assertIn('suite-create', result.stdout)
        self.assertNotIn('2.0', result.stdout)

    def test_public_entrypoint_runs_and_replays_synthetic_campaign(self):
        with tempfile.TemporaryDirectory() as tmp:
            campaign, export = Path(tmp)/'campaign', Path(tmp)/'export'
            for args in [('create', campaign, '--config', ROOT/'examples'/'offline-demo.json'),
                         ('plan', campaign), ('run', campaign), ('verify', campaign),
                         ('export', campaign, export)]:
                result = self.cli(*args)
                self.assertEqual(result.returncode, 0, result.stderr)
            status = self.cli('status', campaign)
            value = json.loads(status.stdout)
            self.assertEqual(value['evidence_kind'], 'synthetic')
            self.assertEqual(value['completed_trials'], 9)
            replay = subprocess.run([sys.executable, '-B', str(export/'reproduce.py')],
                                    capture_output=True, text=True)
            self.assertEqual(replay.returncode, 0, replay.stderr)
            self.assertIn('VERIFIED', replay.stdout)

    def test_invalid_path_returns_handled_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = self.cli('status', Path(tmp)/'missing')
            self.assertEqual(result.returncode, 2)
            self.assertIn('Error:', result.stderr)
            self.assertNotIn('Traceback', result.stderr)

