"""Check report-derived accounting only, NOT raw responses or original manifests."""
import argparse
from collections import Counter
from decimal import Decimal, InvalidOperation
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = ('false_premise_rescue', 'defective_sensors', 'dependent_corroboration',
            'stale_evidence', 'causal_reversal', 'environmental_luck',
            'conditional_evidence', 'independent_repair')
CONDITIONS = ('initial', 'exact_facts', 'structured_audit')
EXPECTED_SETTINGS = {
    'campaign': 'C', 'regime': 'I', 'threshold': '0.95', 'repetitions': 1,
    'source_complexity': 2, 'cases_per_block': 3, 'roles': ['S', 'L', 'F'],
    'conditions': list(CONDITIONS), 'model': 'gpt-6-astra', 'reasoning_effort': 'max',
    'processing': 'standard/default', 'tools': [], 'max_attempts': 1,
    'automatic_retries': False, 'max_input_tokens': 4096,
    'max_total_output_tokens': 6144, 'timeout_seconds': 1800,
    'input_usd_per_million': '10', 'output_usd_per_million': '50',
    'incremental_cap_usd': '10', 'prior_cost_excluded_usd': '1.42609',
    'reservation_usd_per_block': '3.13344', 'order_seed': 2026111603,
    'world_seed_rng_seed': 2026111604, 'analysis_seed': 2026111605,
    'bootstrap_replicates': 10000,
    'world_seed_draw': 'random.Random(seed).randrange(2**63), unique draws',
    'family_order': 'Shuffle a fresh canonical eight-family list twice with one Random(order_seed) instance',
    'all_planned_missing_policy': 'missing or invalid primary indicators equal zero',
    'analysis_status': 'exploratory'}


def require(test, description):
    if not test:
        raise ValueError(description)


def decimal(value):
    result = Decimal(str(value))
    require(result.is_finite() and result >= 0, 'Amounts/scores must be finite and nonnegative')
    return result


def verify(value, source_report=None):
    require(value['schema'] == 'meno-reported-suite-summary-1', 'Unsupported summary schema')
    require(value['evidence_status'] == 'REPORTED_AGGREGATES_RECONSTRUCTED_FROM_CHECKED_IN_REPORT',
            'Report-derived provenance label required')
    require(value['raw_response_corpus_included'] is False and
            value['original_suite_manifest_included'] is False, 'Raw-data limitations must be explicit')
    settings = value['reported_frozen_settings']
    require(settings == EXPECTED_SETTINGS, 'Reconstructed settings differ from reported frozen settings')
    blocks, totals = value['blocks'], value['reported_totals']
    require(len(blocks) == 16, 'Expected all 16 planned ledger rows')
    rng = random.Random(settings['order_seed'])
    order = []
    for _ in range(2):
        one_pass = list(FAMILIES); rng.shuffle(one_pass); order.extend(one_pass)
    seed_rng = random.Random(settings['world_seed_rng_seed'])
    seeds = []
    while len(seeds) < 16:
        seed = seed_rng.randrange(2**63)
        if seed not in seeds:
            seeds.append(seed)
    requests_per_block = settings['cases_per_block'] * len(CONDITIONS) * settings['repetitions']
    reservation = requests_per_block * (
        settings['max_input_tokens'] * decimal(settings['input_usd_per_million']) +
        settings['max_total_output_tokens'] * decimal(settings['output_usd_per_million'])) / 1_000_000
    require(reservation == decimal(settings['reservation_usd_per_block']), 'Reservation arithmetic differs')
    cap = decimal(settings['incremental_cap_usd'])
    cumulative = Decimal(0)
    for i, block in enumerate(blocks):
        require(block['id'] == f'block-{i+1:02d}', 'Block order/identifier differs')
        require(block['family'] == order[i], 'Seeded family order differs')
        require(type(block['world_seed']) is int and block['world_seed'] == seeds[i], 'World seed differs')
        launched = i < 14
        require(block['launched'] is launched and block['complete'] is launched, 'Launch/completion ledger differs')
        require(block['attempts'] == block['completed_requests'] == (9 if launched else 0),
                'Attempt/completed request ledger differs')
        cost = decimal(block['observed_cost_usd'])
        if launched:
            gate = cumulative + reservation
            require(decimal(block['gate_usd']) == gate and gate <= cap, 'Launch reservation/gate differs')
            require(cost > 0, 'Completed model block must have reported positive cost')
            require(set(block['balanced_decision']) == set(CONDITIONS), 'Reported condition means missing')
            require(all(decimal(block['balanced_decision'][c]) <= 1 for c in CONDITIONS), 'Score out of bounds')
        else:
            require(cost == 0 and block['gate_usd'] is None and block['balanced_decision'] is None,
                    'Unlaunched blocks cannot contain observed outcomes')
        cumulative += cost
    require(cumulative == decimal(totals['observed_cost_usd']) == Decimal('6.94651'), 'Total block cost differs')
    expected_counts = {'planned_blocks': 16, 'launched_blocks': 14, 'completed_blocks': 14,
                       'unexecuted_blocks': 2, 'planned_requests': 144, 'attempts': 126,
                       'completed_requests': 126, 'schema_valid_responses': 126, 'invalid_schemas': 0}
    for key, expected in expected_counts.items():
        require(type(totals[key]) is int and totals[key] == expected, 'Reported count differs: '+key)
    require(sum(b['attempts'] for b in blocks) == totals['attempts'], 'Ledger attempt sum differs')
    require(sum(b['completed_requests'] for b in blocks) == totals['completed_requests'], 'Ledger completion sum differs')
    require(16 * requests_per_block == totals['planned_requests'], 'Planned request arithmetic differs')
    usage_cost = (totals['input_tokens'] * decimal(settings['input_usd_per_million']) +
                  totals['output_tokens'] * decimal(settings['output_usd_per_million'])) / 1_000_000
    require(usage_cost == cumulative, 'Reported token-usage cost differs')
    require(0 <= totals['reasoning_tokens'] <= totals['output_tokens'] and totals['cached_input_tokens'] == 0,
            'Reported token accounting differs')
    next_gate = cumulative + reservation
    require(next_gate == decimal(totals['next_gate_usd']) == Decimal('10.07995') and next_gate > cap,
            'Budget stop arithmetic differs')
    require(totals['next_block'] == 'block-15' and totals['stop_reason'] == 'budget_stop', 'Stopping status differs')
    means = {}
    for condition in CONDITIONS:
        score_sum = sum((decimal(b['balanced_decision'][condition]) for b in blocks if b['complete']), Decimal(0))
        complete_mean, planned_mean = score_sum / 14, score_sum / 16
        require(complete_mean == decimal(totals['completed_mean_balanced_decision'][condition]) == 1,
                'Reported completed mean differs')
        require(planned_mean == decimal(totals['all_planned_mean_balanced_decision'][condition]) == Decimal('.875'),
                'Reported all-planned mean differs')
        means[condition] = {'completed': str(complete_mean), 'all_planned': str(planned_mean)}
    require(decimal(totals['completed_audit_minus_facts']) == 0 and
            decimal(totals['all_planned_audit_minus_facts']) == 0, 'Reported contrast differs')
    provenance = value['provenance']
    require(provenance['source_report_sha256'] == '72c12c39e38c5a9cd784ab13157f503867e61e5e15c252fc43e92b3ecdf7c73f',
            'Source report fingerprint differs')
    if source_report:
        data = Path(source_report).read_bytes()
        require(hashlib.sha256(data).hexdigest() == provenance['source_report_sha256'], 'Source report SHA-256 mismatch')
        rows = [line for line in data.decode('utf-8').splitlines() if line.startswith('| block-')]
        require(len(rows) == 16, 'Source report ledger inventory differs')
        for line, block in zip(rows, blocks):
            cells = [cell.strip() for cell in line.strip('|').split('|')]
            require(cells == [block['id'], block['family'], str(block['world_seed']),
                             str(block['attempts']), str(block['completed_requests']), block['observed_cost_usd'],
                             str(block['complete']), block['gate_usd'] or 'not launched'],
                    'JSON transcription differs from source report ledger')
    planned = Counter(b['family'] for b in blocks)
    completed = Counter(b['family'] for b in blocks if b['complete'])
    return {'check': 'REPORT-DERIVED ACCOUNTING ONLY', 'raw_response_replay': False,
            'original_manifest_reconstructed': False, 'source_report_bytes_checked': bool(source_report),
            'planned_ledger_rows': 16, 'complete_ledger_rows': 14, 'attempts': 126,
            'observed_cost_usd': str(cumulative), 'reservation_usd': str(reservation),
            'next_gate_usd': str(next_gate), 'seeded_order_and_all_16_seeds_match': True,
            'reported_balanced_decision_means': means,
            'coverage': {f: {'planned': planned[f], 'complete': completed[f]} for f in FAMILIES},
            'limitation': 'Arithmetic and deterministic schedule checks do not establish raw-response authenticity or reproduce response scoring.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('summary', nargs='?', type=Path, default=ROOT/'data'/'reported_suite_summary.json')
    parser.add_argument('--source-report', type=Path, help='Optional original checked-in manuscript bytes')
    args = parser.parse_args()
    try:
        print(json.dumps(verify(json.loads(args.summary.read_text(encoding='utf-8')), args.source_report), indent=2))
    except (ValueError, OSError, KeyError, TypeError, InvalidOperation) as exc:
        print('ERROR: '+str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
