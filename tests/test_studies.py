import json
from pathlib import Path
import tempfile
import unittest

from research_lab.studies import init_study, load_study, plan


class StudyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.study = init_study(self.root, 'example-study')

    def test_independent_init_and_no_overwrite(self):
        other = init_study(self.root, 'other-study')
        self.assertNotEqual(self.study, other)
        with self.assertRaises(FileExistsError):
            init_study(self.root, 'example-study')
        self.assertEqual(load_study(self.study)[0]['protocol_status'], 'draft')

    def test_reject_escaping_or_windows_reserved_slug(self):
        for slug in ['../escape', '/abs', 'CON', 'foo/bar', 'a.b', 'nul']:
            with self.subTest(slug=slug), self.assertRaises(ValueError):
                init_study(self.root, slug)

    def test_pilot_balanced_and_full_reproducible(self):
        config, cases = load_study(self.study)
        pilot = plan(config, cases, 'pilot')
        full = plan(config, cases, 'full')
        self.assertEqual(len(pilot), 4)
        self.assertEqual(len(full), 8)
        self.assertEqual(full, plan(config, cases, 'full'))
        self.assertEqual({t['condition'] for t in pilot}, {'direct', 'careful'})
        self.assertEqual(len({t['id'] for t in full}), 8)

    def test_invalid_configuration_fails_closed(self):
        path = self.study / 'study.json'
        original = json.loads(path.read_text())
        for key, value in [('dataset', '../outside.jsonl'), ('max_attempts', 0),
                           ('max_requests', True), ('max_cost_usd', float('nan')),
                           ('unknown_typo', 3), ('evidence_kind', 'human_participant')]:
            config = dict(original, **{key: value})
            path.write_text(json.dumps(config))
            with self.subTest(key=key), self.assertRaises(ValueError):
                load_study(self.study)

    def test_duplicate_cases_rejected(self):
        path = self.study / 'cases.jsonl'
        line = path.read_text().splitlines()[0]
        path.write_text(line + '\n' + line + '\n')
        with self.assertRaises(ValueError):
            load_study(self.study)


if __name__ == '__main__':
    unittest.main()
