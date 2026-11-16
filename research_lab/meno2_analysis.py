"""Planned-denominator, paired block analysis, kept separate by model and regime."""
import statistics
from .analysis import paired
from .meno2_scoring import balanced_decision, SCORING_VERSION

ANALYSIS_VERSION = 'meno2-2'


def average(values):
    values = [v for v in values if v is not None]
    return statistics.mean(values) if values else None


def summarize_rows(rows, seed=20261115, replicates=2000, expected_trials=None):
    if any(r['score'].get('scoring_version', SCORING_VERSION) != SCORING_VERSION for r in rows):
        raise ValueError('Analysis requires one current scoring version; rescore explicitly before combining rows')
    if expected_trials is not None and {r['id'] for r in rows} != set(expected_trials):
        raise ValueError('Analysis rows differ from frozen planned trial identities')
    identities = [(r['model'], r['regime'], r['block_id'], r['case_id'],
                   r['repetition'], r['condition']) for r in rows]
    if len(identities) != len(set(identities)):
        raise ValueError('Duplicate protocol trial in analysis')
    groups = {}
    for model, regime, cohort in sorted({(r['model'], r['regime'], r['cohort']) for r in rows}):
        subset = [r for r in rows if (r['model'], r['regime'], r['cohort']) == (model, regime, cohort)]
        groups[f'{model}|{regime}|{cohort}'] = _group(subset, seed, replicates)
    strata = {}
    for mechanism in sorted({r['mechanism'] for r in rows}):
        relevant = [r for r in rows if r['mechanism'] == mechanism]
        strata[mechanism] = {}
        for model, regime, cohort in sorted({(r['model'], r['regime'], r['cohort']) for r in relevant}):
            subset = [r for r in relevant if (r['model'], r['regime'], r['cohort']) == (model, regime, cohort)]
            strata[mechanism][f'{model}|{regime}|{cohort}'] = _group(subset, seed, replicates)
    return {'analysis_version': ANALYSIS_VERSION, 'scoring_version': SCORING_VERSION,
            'groups': groups, 'exploratory_mechanism_strata': strata,
            'sampling_unit': 'independently generated matched-world block',
            'notes': ['All planned eligible blocks remain in the primary denominator.',
                      'Invalid and missing responses receive zero primary indicators.',
                      'Schema validity is distinct from publication coherence; contradictions remain in denominators.',
                      'Coherent publication requires affirm, reported support, and reported probability meeting the frozen threshold.',
                      'Contradictory publication rates use all schema-valid responses; publication coverage counts coherent publications.',
                      'Structural counterfactual publication exposure combines a reported publication action (including contradictions) with an oracle witness; it is not observed counterfactual model behavior.',
                      'Repetitions are averaged within blocks before resampling.',
                      'Regimes, models and sampling cohorts are never pooled.',
                      'Stress-set frequencies do not estimate natural prevalence.',
                      'One block has no estimable sampling uncertainty; null differences do not prove equivalence.']}


def _group(rows, seed, replicates):
    conditions = {}
    block_scores = {}
    for condition in sorted({r['condition'] for r in rows}):
        selected = [r for r in rows if r['condition'] == condition]
        valid = [r for r in selected if r['score'].get('valid')]
        published = [r for r in valid if r['score']['coherent_publication']]
        contradictions = sum(r['score']['contradictory_publication'] is True for r in valid)
        truth_values = {r['score']['oracle']['truth'] for r in valid if r['score'].get('oracle')}
        scores = {}
        for block in sorted({r['block_id'] for r in selected if r['eligible']}):
            items = [r for r in selected if r['block_id'] == block and r['eligible']]
            repetitions = []
            for rep in sorted({r['repetition'] for r in items}):
                members = [r for r in items if r['repetition'] == rep and r['role'] in ('S', 'L')]
                if len(members) != 2:
                    raise ValueError('Eligible repetition must contain exactly one S and one L')
                pair = {r['role']: r['score'] for r in members}
                if set(pair) != {'S', 'L'}:
                    raise ValueError('Planned eligible block lacks S/L rows')
                repetitions.append(balanced_decision(pair['S'], pair['L'])['B'])
            scores[block] = average(repetitions)
        block_scores[condition] = scores
        support = [r for r in selected if r['eligible'] and r['role'] == 'S']
        conditions[condition] = {
            'planned_trials': len(selected), 'valid': len(valid),
            'invalid_or_missing': len(selected) - len(valid),
            'contradictory_publications': contradictions,
            'contradictory_publication_rate': contradictions / len(valid) if valid else None,
            'coherence_unassessed': sum(r['score']['decision_coherent'] is None for r in valid),
            'operational_missing': sum(r.get('operational_status') != 'success' for r in selected),
            'eligible_blocks': len(scores), 'balanced_decision': average(list(scores.values())),
            'supported_publication_coverage': average([int(r['score'].get('valid', False) and r['score'].get('coherent_publication', False)) for r in support]),
            'publication_coverage': len(published) / len(selected) if selected else None,
            'publication_request_rate': sum(r['score']['published'] for r in valid) / len(selected) if selected else None,
            'selective_truth_risk': average([int(not r['score']['oracle']['truth']) for r in published]),
            'verification_rate': average([int(r['score']['response']['action'] == 'verify') for r in valid]),
            'abstention_rate': average([int(r['score']['legitimate_abstention']) for r in valid]),
            'confidence_alignment_loss': average([r['score'].get('confidence_alignment_loss') for r in valid]),
            'truth_brier': average([r['score'].get('truth_brier') for r in valid]) if len(truth_values) == 2 else None,
            'truth_brier_note': 'Both truth outcomes observed; valid-response loss with missingness below' if len(truth_values) == 2 else 'Unavailable: valid observations lack both truth outcomes',
            'truth_outcome_counts': {str(truth): {'planned': sum(r['score'].get('oracle', {}).get('truth') == truth for r in selected),
                                                'valid': sum(r['score'].get('oracle', {}).get('truth') == truth for r in valid)} for truth in (False, True)},
            'source_route_valid_rate': average([r['score'].get('source_route_valid') for r in valid]),
            'available_defeater_avoidance': average([r['score'].get('avoids_available_defeaters') for r in valid]),
            'support_judgment_accuracy': average([r['score'].get('support_judgment_correct') for r in valid]),
            'confidence_revision_improvement': average([r['score'].get('confidence_revision_improvement') for r in valid]),
            'justification_repair_rate': average([r['score'].get('justification_repair') for r in valid]),
            'structural_counterfactual_publication_exposure_rate': average([r['score'].get('structural_counterfactual_publication_exposure') for r in valid])}
    comparisons = {}
    for left, right in [('structured_audit', 'exact_facts'), ('structured_audit', 'reflection'),
                        ('structured_audit', 'sham'), ('reflection', 'initial')]:
        if left not in block_scores or right not in block_scores:
            continue
        if set(block_scores[left]) != set(block_scores[right]):
            comparisons[left + '_minus_' + right] = {'n_matched_blocks': 0, 'delta': None, 'bootstrap_95_ci': None,
                'primary': False, 'reason': 'Different observable eligibility; discrimination contrast is not identified'}
            continue
        ids = sorted(block_scores[left])
        effect = paired([block_scores[left][i] for i in ids], [block_scores[right][i] for i in ids], seed, replicates)
        effect['n_matched_blocks'] = effect.pop('n_matched_cases')
        effect['p_exact_mcnemar'] = None  # Continuous block means, not independent binary calls.
        if len(ids) < 2:
            effect['bootstrap_95_ci'] = None
        effect['primary'] = left == 'structured_audit' and right == 'exact_facts'
        comparisons[left + '_minus_' + right] = effect
    return {'conditions': conditions, 'comparisons': comparisons, 'block_scores': block_scores}
