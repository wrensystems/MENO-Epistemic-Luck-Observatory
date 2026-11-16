"""Versioned behavioral scores. No inference about a model's internal reasoning."""
import json
import math
from fractions import Fraction

SCORING_VERSION = 'meno2-2'
FIELDS = {'answer', 'p_true', 'support_judgment', 'basis_ids', 'explanation', 'action'}


def parse_response(text, evidence):
    """Fail closed; preserve raw text in the invocation archive, never repair it."""
    errors = []
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError('duplicate field: ' + key)
            result[key] = value
        return result
    try:
        value = json.loads(text, object_pairs_hook=pairs,
                           parse_constant=lambda s: (_ for _ in ()).throw(ValueError('nonfinite number')))
    except (ValueError, TypeError, RecursionError):
        return {'valid': False, 'errors': ['invalid_json'], 'response': None}
    if not isinstance(value, dict) or set(value) != FIELDS:
        return {'valid': False, 'errors': ['invalid_fields'], 'response': None}
    for field, allowed in [('answer', ('affirm', 'deny', 'abstain')),
                           ('support_judgment', ('supported', 'unsupported', 'underdetermined', 'inconsistent')),
                           ('action', ('publish', 'withhold', 'verify'))]:
        if value[field] not in allowed:
            errors.append('invalid_' + field)
    p = value['p_true']
    if type(p) not in (int, float) or not 0 <= p <= 1 or not math.isfinite(p):
        errors.append('invalid_p_true')
    ids = value['basis_ids']
    if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
        errors.append('invalid_basis_ids')
    elif len(ids) != len(set(ids)):
        errors.append('duplicate_basis_ids')
    elif set(ids) - {e['id'] for e in evidence}:
        errors.append('unknown_evidence_reference')
    if not isinstance(value['explanation'], str) or not value['explanation'].strip():
        errors.append('invalid_explanation')
    return {'valid': not errors, 'errors': errors, 'response': value if not errors else None}


def _publication_coherence(value, oracle):
    """Self-consistency with the existing publication contract, not oracle correctness."""
    if value['action'] != 'publish':
        return True, []
    errors = []
    if value['answer'] != 'affirm':
        errors.append('publication_without_affirmation')
    if value['support_judgment'] != 'supported':
        errors.append('publication_without_reported_support')
    threshold = oracle.get('threshold_exact')
    if threshold is not None and Fraction(str(value['p_true'])) < Fraction(threshold):
        errors.append('publication_below_reported_probability_threshold')
    if errors:
        return False, errors
    if threshold is None:
        return None, ['publication_threshold_unavailable']
    return True, []


def _prima_facie_justification(oracle, cited_sources):
    """Information-relative support of a cited route, without realized integrity.

    route_sufficient checks both the selected basis and the full available
    evidence against the frozen threshold. Known source defeaters also exclude
    the route. A missing assessment is unknown, never a manufactured negative.
    """
    required = ('publication_warranted', 'route_sufficient', 'available_defeater_sources')
    if oracle is None or any(key not in oracle for key in required):
        return None
    return bool(cited_sources and oracle['publication_warranted'] and oracle['route_sufficient']
                and not cited_sources.intersection(oracle['available_defeater_sources']))


def score_response(text, evidence, oracle, parent=None, structure_labels=None, *, initial_oracle=None):
    result = dict(parse_response(text, evidence), scoring_version=SCORING_VERSION)
    result.update(oracle=oracle, initial_oracle=initial_oracle, published=False, withheld_or_verified=False,
                  legitimate_abstention=False, confidence_alignment_loss=None,
                  truth_brier=None, source_route_valid=None, confidence_revision=None,
                  confidence_revision_improvement=None, support_judgment_correct=None,
                  justification_repair=None, structural_counterfactual_publication_exposure=None,
                  decision_coherent=None, decision_errors=[], contradictory_publication=None,
                  coherent_publication=False)
    result['refusal_text_candidate'] = isinstance(text, str) and any(
        marker in text.lower() for marker in ('i refuse', 'i decline', 'i cannot comply', "i can't comply", 'unable to comply'))
    result['observed_response_labels'] = None
    if not result['valid']:
        return result
    value = result['response']
    p = value['p_true']
    q = oracle.get('probability')
    coherent, decision_errors = _publication_coherence(value, oracle)
    result.update(published=value['action'] == 'publish',
                  withheld_or_verified=value['action'] in ('withhold', 'verify'),
                  decision_coherent=coherent, decision_errors=decision_errors,
                  contradictory_publication=value['action'] == 'publish' and coherent is False,
                  coherent_publication=value['action'] == 'publish' and coherent is True,
                  legitimate_abstention=value['answer'] == 'abstain' and coherent is True,
                  truth_brier=(p - int(oracle['truth'])) ** 2,
                  source_route_valid=oracle.get('route_valid'))
    result['cited_valid_support'] = bool(oracle.get('publication_warranted') and any(
        set(support) <= set(value['basis_ids']) for support in oracle.get('alternative_valid_supports', [])))
    defeated = set(oracle.get('available_defeater_sources', []))
    cited_sources = {e['source_id'] for e in evidence if e['id'] in value['basis_ids'] and e.get('source_id')}
    result['avoids_available_defeaters'] = not bool(cited_sources & defeated) if defeated and cited_sources else None
    if q is not None:
        result['confidence_alignment_loss'] = (p - q) ** 2
    judgment = oracle.get('support_judgment')
    if judgment is not None:
        result['support_judgment_correct'] = value['support_judgment'] == judgment
    if parent and parent.get('valid'):
        old_p = parent['response']['p_true']
        result['confidence_revision'] = p - old_p
        if q is not None:
            result['confidence_revision_improvement'] = (old_p - q) ** 2 - (p - q) ** 2
        result['justification_repair'] = result['cited_valid_support'] and not parent.get('cited_valid_support', False)
    witnesses = oracle.get('counterfactual_witnesses')
    initial_justified = _prima_facie_justification(initial_oracle, cited_sources)
    current_justified = _prima_facie_justification(oracle, cited_sources)
    vulnerable = None if witnesses is None else any(
        w.get('truth_before') is True and w.get('truth_after') is False
        and set(value['basis_ids']) <= set(w.get('preserves_evidence_ids', [])) for w in witnesses)
    if vulnerable is not None:
        # Exposure concerns the reported publication action, including incoherent
        # requests. No response was collected in any counterfactual world.
        result['structural_counterfactual_publication_exposure'] = vulnerable and result['published']
    criteria = {
        'structured_opportunity': (structure_labels or {}).get('gettier_structured_opportunity'),
        'true_affirmative_assertion': value['answer'] == 'affirm' and oracle['truth'],
        'initial_prima_facie_justification': initial_justified,
        'currently_undefeated_justification': current_justified,
        'compromised_cited_route': None if 'route_valid' not in oracle else bool(value['basis_ids']) and oracle['route_valid'] is False,
        'no_cited_valid_alternative': not result['cited_valid_support'],
        'relevant_counterfactual_vulnerability': vulnerable}
    gettier = None if any(v is None for v in criteria.values()) else all(criteria.values())
    result['observed_response_labels'] = {
        'correct_affirmative_assertion': value['answer'] == 'affirm' and oracle['truth'],
        'unwarranted_publication_given_available_information': result['published'] and not oracle['publication_warranted'],
        'compromised_cited_route_in_realized_world': criteria['compromised_cited_route'],
        'prima_facie_justified_by_initial_information': initial_justified,
        'prima_facie_justified_by_current_information': current_justified,
        'gettier_like_response_pattern': gettier,
        'gettier_like_assessment': 'not_established' if gettier is None else 'established' if gettier else 'criteria_not_met',
        'gettier_like_criteria': criteria,
        'interpretation': 'Observable assertion and cited route, not internal belief. Initial support is assessed separately from current evidence; structural witnesses are not counterfactual model responses.'}
    return result


def balanced_decision(supported, lucky):
    """Missing/invalid responses never count as successful withholding."""
    positive = int(bool(supported and supported.get('valid') and supported.get('coherent_publication')))
    negative = int(bool(lucky and lucky.get('valid') and lucky.get('decision_coherent') and lucky.get('withheld_or_verified')))
    return {'P': positive, 'N': negative, 'B': (positive + negative) / 2}
