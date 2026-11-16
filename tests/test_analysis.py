from pathlib import Path
import tempfile
import unittest

from research_lab.analysis import wilson, paired, analyze, summarize
from research_lab.engine import run
from research_lab.studies import init_study


class AnalysisTests(unittest.TestCase):
    def test_wilson_known_case_and_empty(self):
        lo, hi = wilson(0, 20)
        self.assertAlmostEqual(lo, 0)
        self.assertAlmostEqual(hi, 0.161125158, places=7)
        self.assertIsNone(wilson(0, 0))
        with self.assertRaises(ValueError):
            wilson(3, 2)

    def test_exact_paired_null_and_direction(self):
        null = paired([1, 0], [1, 0])
        self.assertEqual(null['delta'], 0)
        self.assertEqual(null['p_exact_mcnemar'], 1)
        negative = paired([0] * 8, [1] * 8)
        self.assertEqual(negative['delta'], -1)
        self.assertEqual(negative['p_exact_mcnemar'], 0.0078125)
        self.assertEqual(negative['bootstrap_95_ci'], [-1, -1])
        with self.assertRaises(ValueError):
            paired([1], [1, 0])

    def test_analysis_labeled_synthetic_and_no_raw_changes(self):
        with tempfile.TemporaryDirectory() as tmp:
            study = init_study(Path(tmp), 'analysis-study')
            result = run(study, mode='full')
            directory = Path(result['run_dir'])
            before = {p: p.read_bytes() for p in directory.rglob('*') if p.is_file()}
            report = analyze(directory)
            self.assertEqual(report['evidence_kind'], 'synthetic')
            self.assertEqual(report['conditions']['direct']['n_scored'], 4)
            self.assertEqual(report['conditions']['direct']['mean_score'], 1)
            self.assertEqual(report['comparisons']['direct_vs_careful']['delta'], 0)
            self.assertEqual(before, {p: p.read_bytes() for p in directory.rglob('*') if p.is_file()})

    def test_missing_repetitions_excluded_from_matched_case_inference(self):
        rows = [
            {'case_id': 'case-1', 'condition': 'a', 'repetition': 0, 'observed': True, 'score': 1},
            {'case_id': 'case-1', 'condition': 'a', 'repetition': 1, 'observed': True, 'score': 0},
            {'case_id': 'case-1', 'condition': 'b', 'repetition': 0, 'observed': True, 'score': 1},
            {'case_id': 'case-1', 'condition': 'b', 'repetition': 1, 'observed': False, 'score': None},
        ]
        report = summarize(rows, {'evidence_kind': 'synthetic', 'condition_order': ['a', 'b'],
                                  'repetitions': 2, 'seed': 1})
        self.assertEqual(report['conditions']['b']['n_missing_or_unscored'], 1)
        self.assertIsNone(report['conditions']['a']['wilson_95_ci'])
        self.assertEqual(report['comparisons']['a_vs_b']['n_matched_cases'], 0)
        self.assertEqual(report['comparisons']['a_vs_b']['n_unmatched_or_incomplete_cases'], 1)


if __name__ == '__main__':
    unittest.main()
