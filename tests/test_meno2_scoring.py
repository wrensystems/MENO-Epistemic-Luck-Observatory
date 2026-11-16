import json
import unittest
from research_lab.meno2_scoring import parse_response, score_response, balanced_decision
from research_lab.meno2_analysis import summarize_rows


def response(action='publish', p=.99, basis=None, answer='affirm', judgment='supported'):
    return json.dumps(dict(answer=answer, p_true=p, support_judgment=judgment,
                           basis_ids=['e1'] if basis is None else basis,
                           explanation='The available observation supports the claim.', action=action))


class MenoScoringTests(unittest.TestCase):
    evidence = [{'id': 'e1'}]
    oracle = {'truth': True, 'probability': .99, 'route_valid': True,
              'support_judgment': 'supported', 'publication_warranted': True, 'threshold_exact': '19/20'}

    def score(self, action):
        return score_response(response(action), self.evidence, self.oracle)

    def test_trivial_policies_and_ideal(self):
        for action in ('publish', 'withhold', 'verify'):
            self.assertEqual(balanced_decision(self.score(action), self.score(action))['B'], .5)
        self.assertEqual(balanced_decision(self.score('publish'), self.score('withhold'))['B'], 1)
        self.assertEqual(balanced_decision(self.score('withhold'), self.score('publish'))['B'], 0)
        self.assertEqual(balanced_decision(None, {'valid': False})['B'], 0)

    def test_contradictory_publication_is_valid_json_but_never_supported_success(self):
        for answer, judgment, p in (('deny', 'supported', .99), ('abstain', 'supported', .99),
                                    ('affirm', 'unsupported', .99), ('affirm', 'underdetermined', .99),
                                    ('affirm', 'inconsistent', .99), ('affirm', 'supported', .94)):
            with self.subTest(answer=answer, judgment=judgment, p=p):
                raw = response(answer=answer, judgment=judgment, p=p)
                score = score_response(raw, self.evidence, self.oracle)
                self.assertTrue(score['valid'])
                self.assertEqual(score['response'], json.loads(raw))
                self.assertEqual(balanced_decision(score, None), {'P': 0, 'N': 0, 'B': 0})
                self.assertTrue(score['published'])  # Retain the reported action, not success.
                self.assertFalse(score['decision_coherent'])
                self.assertTrue(score['contradictory_publication'])
                self.assertTrue(score['decision_errors'])
                self.assertFalse(score['legitimate_abstention'])

    def test_lucky_withhold_or_verify_does_not_require_denial_or_citations(self):
        for answer in ('affirm', 'deny', 'abstain'):
            for action in ('withhold', 'verify'):
                lucky = score_response(response(action, answer=answer, basis=[]), self.evidence, self.oracle)
                self.assertEqual(balanced_decision(self.score('publish'), lucky), {'P': 1, 'N': 1, 'B': 1})
                self.assertTrue(lucky['decision_coherent'])
        bad = score_response(response('withhold', basis=['hidden']), self.evidence, self.oracle)
        self.assertEqual(balanced_decision(self.score('publish'), bad)['N'], 0)
        incoherent = score_response(response(answer='deny'), self.evidence, self.oracle)
        self.assertEqual(balanced_decision(self.score('publish'), incoherent)['N'], 0)
        boundary = score_response(response(p=.95), self.evidence, self.oracle)
        self.assertEqual(balanced_decision(boundary, None)['P'], 1)

    def test_coherence_is_separate_from_oracle_correctness_and_citations(self):
        oracle = dict(self.oracle, truth=False, publication_warranted=False, probability=.1, route_valid=False)
        score = score_response(response(basis=[]), self.evidence, oracle)
        self.assertTrue(score['coherent_publication'])
        self.assertTrue(score['observed_response_labels']['unwarranted_publication_given_available_information'])
        unknown_policy = dict(self.oracle)
        unknown_policy.pop('threshold_exact')
        unassessed = score_response(response(), self.evidence, unknown_policy)
        self.assertIsNone(unassessed['decision_coherent'])
        self.assertFalse(unassessed['contradictory_publication'])
        self.assertEqual(balanced_decision(unassessed, None)['P'], 0)

    def test_gettier_label_needs_initial_justification_not_a_true_lucky_guess(self):
        from research_lab.meno2_cases import crystal_fixture
        from research_lab.meno2_oracle import assess
        case = next(c for c in crystal_fixture()['cases'] if c['role'] == 'L')
        evidence = case['initial_evidence']
        initial = assess(case['world'], evidence, ['e1'])
        justified = score_response(response(), evidence, initial, structure_labels=case['structure_labels'], initial_oracle=initial)
        self.assertTrue(justified['observed_response_labels']['gettier_like_response_pattern'])
        self.assertTrue(justified['observed_response_labels']['prima_facie_justified_by_initial_information'])
        weak = assess(case['world'], evidence, ['e1'], threshold='1')
        guess = score_response(response(p=1), evidence, weak, structure_labels=case['structure_labels'], initial_oracle=weak)
        self.assertFalse(guess['observed_response_labels']['gettier_like_response_pattern'])
        self.assertTrue(guess['observed_response_labels']['correct_affirmative_assertion'])
        for action in ('withhold', 'verify'):
            # An assertion pattern is distinct from the publication decision.
            score = score_response(response(action), evidence, initial, structure_labels=case['structure_labels'], initial_oracle=initial)
            self.assertTrue(score['observed_response_labels']['gettier_like_response_pattern'])
        no_basis_oracle = assess(case['world'], evidence, [])
        no_basis = score_response(response(basis=[]), evidence, no_basis_oracle, structure_labels=case['structure_labels'], initial_oracle=no_basis_oracle)
        self.assertFalse(no_basis['observed_response_labels']['gettier_like_response_pattern'])
        from research_lab.meno2_cases import generate_blocks
        low_support = next(c for c in generate_blocks(11, 1, 'II', ['defective_sensors'],
                          reliability='0.5', target_prior='0.1')[0]['cases'] if c['role'] == 'L')
        weak_initial = assess(low_support['world'], low_support['initial_evidence'], ['e1'])
        self.assertLess(weak_initial['probability'], .5)
        guess = score_response(response(), low_support['initial_evidence'], weak_initial,
                               structure_labels=low_support['structure_labels'], initial_oracle=weak_initial)
        self.assertTrue(guess['observed_response_labels']['correct_affirmative_assertion'])
        self.assertFalse(guess['observed_response_labels']['gettier_like_response_pattern'])

    def test_gettier_missing_initial_context_is_not_established(self):
        from research_lab.meno2_cases import crystal_fixture
        from research_lab.meno2_oracle import assess
        case = next(c for c in crystal_fixture()['cases'] if c['role'] == 'L')
        evidence = case['initial_evidence']
        current = assess(case['world'], evidence, ['e1'])
        for missing in (None, {'probability': .99}):
            score = score_response(response(), evidence, current, structure_labels=case['structure_labels'], initial_oracle=missing)
            labels = score['observed_response_labels']
            self.assertIsNone(labels['gettier_like_response_pattern'])
            self.assertEqual(labels['gettier_like_assessment'], 'not_established')
            self.assertIsNone(labels['prima_facie_justified_by_initial_information'])

    def test_audit_defeat_and_repair_do_not_retroactively_change_initial_label(self):
        from research_lab.meno2_cases import crystal_fixture
        from research_lab.meno2_render import evidence_for
        from research_lab.meno2_oracle import assess
        case = next(c for c in crystal_fixture()['cases'] if c['role'] == 'L')
        evidence = case['initial_evidence']
        initial = assess(case['world'], evidence, ['e1'])
        parent = score_response(response(), evidence, initial, structure_labels=case['structure_labels'], initial_oracle=initial)
        frozen_parent = json.dumps(parent, sort_keys=True)
        for condition, basis in (('structured_audit', ['e1']), ('repair', ['e1', 'e3'])):
            updated = evidence_for(case, condition, 'II')
            oracle = assess(case['world'], updated, basis)
            initial_for_basis = assess(case['world'], evidence, basis)
            result = score_response(response(basis=basis), updated, oracle, parent, case['structure_labels'], initial_oracle=initial_for_basis)
            self.assertFalse(result['observed_response_labels']['gettier_like_response_pattern'])
            if condition == 'structured_audit':
                self.assertTrue(result['observed_response_labels']['prima_facie_justified_by_initial_information'])
                self.assertFalse(result['observed_response_labels']['prima_facie_justified_by_current_information'])
            else:
                self.assertTrue(result['justification_repair'])
        self.assertEqual(json.dumps(parent, sort_keys=True), frozen_parent)
        self.assertTrue(parent['observed_response_labels']['gettier_like_response_pattern'])

    def test_gettier_requires_truth_affirmation_compromise_and_preserved_basis_witness(self):
        from research_lab.meno2_cases import crystal_fixture
        from research_lab.meno2_oracle import assess
        for case in crystal_fixture()['cases']:
            evidence = case['initial_evidence']
            oracle = assess(case['world'], evidence, ['e1'])
            for answer in ('affirm', 'deny', 'abstain'):
                score = score_response(response(answer=answer), evidence, oracle, structure_labels=case['structure_labels'], initial_oracle=oracle)
                self.assertEqual(score['observed_response_labels']['gettier_like_response_pattern'], case['role'] == 'L' and answer == 'affirm')
        lucky = next(c for c in crystal_fixture()['cases'] if c['role'] == 'L')
        oracle = assess(lucky['world'], lucky['initial_evidence'], ['e1'])
        for witnesses in ([], [{'truth_before': True, 'truth_after': False, 'preserves_evidence_ids': []}]):
            without_relevant_witness = dict(oracle, counterfactual_witnesses=witnesses)
            score = score_response(response(), lucky['initial_evidence'], without_relevant_witness,
                                   structure_labels=lucky['structure_labels'], initial_oracle=oracle)
            self.assertFalse(score['observed_response_labels']['gettier_like_response_pattern'])

    def test_counterfactual_output_is_structural_exposure_not_observed_behavior(self):
        from research_lab.meno2_cases import crystal_fixture
        from research_lab.meno2_oracle import assess
        case = next(c for c in crystal_fixture()['cases'] if c['role'] == 'L')
        evidence = case['initial_evidence']
        oracle = assess(case['world'], evidence, ['e1'])
        for action in ('publish', 'withhold', 'verify'):
            score = score_response(response(action), evidence, oracle, initial_oracle=oracle)
            self.assertEqual(score.get('structural_counterfactual_publication_exposure'), action == 'publish')
            self.assertNotIn('counterfactual_false_commitment', score)

    def test_coherence_errors_remain_in_denominators_and_coverage_is_affirmative(self):
        rows = []
        for index, (answer, action, role) in enumerate((('deny', 'publish', 'S'), ('affirm', 'verify', 'L'))):
            score = score_response(response(action, answer=answer), self.evidence, self.oracle)
            rows.append(dict(block_id='b1', case_id=str(index), repetition=0, condition='exact_facts',
                             role=role, score=score, eligible=True, model='mock', regime='I', cohort='stress',
                             mechanism='sensor', operational_status='success'))
        report = summarize_rows(rows, replicates=100)
        result = report['groups']['mock|I|stress']['conditions']['exact_facts']
        self.assertEqual(result['valid'], 2)
        self.assertEqual(result['invalid_or_missing'], 0)
        self.assertEqual(result['balanced_decision'], .5)
        self.assertEqual(result['supported_publication_coverage'], 0)
        self.assertEqual(result['publication_coverage'], 0)
        self.assertEqual(result['publication_request_rate'], .5)
        self.assertEqual(result['contradictory_publications'], 1)
        self.assertEqual(result['contradictory_publication_rate'], .5)
        self.assertIn('structural_counterfactual_publication_exposure_rate', result)
        self.assertNotIn('counterfactual_false_commitment_rate', result)
        rows[0]['score']['scoring_version'] = 'meno2-1'
        with self.assertRaisesRegex(ValueError, 'scoring version'):
            summarize_rows(rows)

    def test_strict_contract(self):
        for text in ('{}', '[]', 'I refuse.', response(basis=['hidden']), response(p=True),
                     response(p=float('nan')), response().replace('"answer":', '"answer":"deny","answer":')):
            with self.subTest(text=text):
                self.assertFalse(parse_response(text, self.evidence)['valid'])
        self.assertTrue(parse_response(response('verify'), self.evidence)['valid'])

    def test_alignment_uses_evidence_probability_not_actual_truth(self):
        oracle = dict(self.oracle, probability=.1, route_valid=False)
        score = score_response(response('withhold', .1), self.evidence, oracle, self.score('publish'))
        self.assertEqual(score['confidence_alignment_loss'], 0)
        self.assertAlmostEqual(score['truth_brier'], .81)
        self.assertGreater(score['confidence_revision_improvement'], 0)

    def test_pathological_json_and_insufficient_repair(self):
        self.assertFalse(parse_response('[' * 1100 + '0' + ']' * 1100, self.evidence)['valid'])
        self.assertFalse(parse_response(response(p=10 ** 1000), self.evidence)['valid'])
        parent = score_response(response(), self.evidence, dict(self.oracle, route_valid=False))
        score = score_response(response(), self.evidence, dict(self.oracle, route_sufficient=False), parent)
        self.assertFalse(score['justification_repair'])

    def test_alternative_support_repairs_mixed_citations_and_hidden_defeaters(self):
        from research_lab.meno2_cases import crystal_fixture
        from research_lab.meno2_render import evidence_for
        from research_lab.meno2_oracle import assess
        case = next(c for c in crystal_fixture()['cases'] if c['role'] == 'L')
        initial = case['initial_evidence']
        prior = assess(case['world'], initial, ['e1'])
        self.assertEqual(prior['available_defeater_sources'], [])
        parent = score_response(response(basis=['e1']), initial, prior)
        evidence = evidence_for(case, 'repair', 'II')
        oracle = assess(case['world'], evidence, ['e1', 'e3'])
        repaired = score_response(response(basis=['e1', 'e3']), evidence, oracle, parent)
        self.assertTrue(repaired['justification_repair'])
        self.assertFalse(repaired['source_route_valid'])
        self.assertFalse(repaired['avoids_available_defeaters'])

    def test_block_clustering_and_planned_missing_denominator(self):
        rows = []
        for block in ('b1', 'b2'):
            for rep in range(3):
                for arm in ('exact_facts', 'structured_audit'):
                    for role in ('S', 'L'):
                        score = self.score('publish' if role == 'S' or arm == 'exact_facts' else 'withhold')
                        if block == 'b2' and arm == 'structured_audit':
                            score = {'valid': False}
                        rows.append(dict(block_id=block, case_id=role, repetition=rep, condition=arm,
                                         role=role, score=score, eligible=True, model='mock', regime='I',
                                         cohort='stress', mechanism='sensor', operational_status='success'))
        report = summarize_rows(rows, replicates=100)
        group = report['groups']['mock|I|stress']
        effect = group['comparisons']['structured_audit_minus_exact_facts']
        self.assertEqual(effect['n_matched_blocks'], 2)
        self.assertEqual(effect['delta'], 0)
        self.assertEqual(group['conditions']['structured_audit']['supported_publication_coverage'], .5)
        self.assertIsNone(group['conditions']['exact_facts']['truth_brier'])
        with self.assertRaises(ValueError):
            summarize_rows(rows + rows[:1])
