"""Descriptive statistics; independent cases, not repeated calls, are paired units."""
import csv
from html import escape
import itertools
import math
from pathlib import Path
import random
import statistics

from .engine import _load, inspect_run
from .storage import write_new


def wilson(successes, n):
    if type(n) is not int or type(successes) is not int or n < 0 or not 0 <= successes <= n:
        raise ValueError('Invalid binomial counts')
    if n == 0:
        return None
    z = 1.959963984540054
    p = successes / n
    denominator = 1 + z * z / n
    center = (p + z * z / (2 * n)) / denominator
    radius = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
    return [max(0, center - radius), min(1, center + radius)]


def paired(left, right, seed=20261111, replicates=2000):
    if len(left) != len(right):
        raise ValueError('Paired samples must be aligned and equal length')
    if not left:
        return {'n_matched_cases': 0, 'delta': None, 'bootstrap_95_ci': None, 'p_exact_mcnemar': None}
    if any(not isinstance(x, (int, float)) or not math.isfinite(x) or not 0 <= x <= 1 for x in left + right):
        raise ValueError('Scores must be finite and in [0,1]')
    if type(replicates) is not int or replicates < 100:
        raise ValueError('At least 100 bootstrap replicates required')
    differences = [a - b for a, b in zip(left, right)]
    rng = random.Random(seed)
    boot = sorted(statistics.mean(rng.choices(differences, k=len(differences))) for _ in range(replicates))
    binary = all(x in (0, 1) for x in left + right)
    p = None
    if binary:
        b, c = differences.count(1), differences.count(-1)
        d = b + c
        p = min(1.0, 2 * sum(math.comb(d, k) for k in range(min(b, c) + 1)) / 2 ** d) if d else 1.0
    return {'n_matched_cases': len(left), 'delta': statistics.mean(differences),
            'bootstrap_95_ci': [boot[int(replicates * .025)], boot[int(replicates * .975) - 1]],
            'p_exact_mcnemar': p, 'bootstrap_seed': seed, 'bootstrap_replicates': replicates}


def metrics(directory):
    _, snapshot, records = _load(directory)
    by_task = {r['intent']['task_id']: r for r in records if r['response'] is not None}
    rows = []
    for task in snapshot['tasks']:
        response = by_task.get(task['id'], {}).get('response')
        score = None
        if response and snapshot['config']['evaluator'] == 'exact_match':
            score = int(response['text'].strip() == task['expected'].strip())
        rows.append({'case_id': task['case_id'], 'condition': task['condition'],
                     'repetition': task['repetition'], 'observed': response is not None, 'score': score})
    status = inspect_run(directory)
    meta = {k: status[k] for k in ('mode', 'evidence_kind', 'status', 'planned', 'completed',
                                  'requests', 'uncertain', 'failed', 'reserved_usd',
                                  'observed_cost_usd', 'input_tokens', 'output_tokens')}
    meta['repetitions'] = snapshot['config']['repetitions']
    meta['seed'] = snapshot['config']['seed']
    meta['condition_order'] = [c['id'] for c in snapshot['config']['conditions']]
    return rows, meta


def summarize(rows, meta):
    report = dict(meta, conditions={}, comparisons={})
    report['interpretation'] = ('SYNTHETIC SOFTWARE CHECK ONLY; not model or human research evidence.'
                                if meta['evidence_kind'] == 'synthetic' else
                                'Machine-generated measurements; no human-participant evidence.')
    report['analysis_notes'] = [
        'Missing/failed generations are reported, never imputed as correct or dropped silently.',
        'Wilson intervals apply only to single binary observations per independent case.',
        'Paired bootstrap resamples case means; all planned repetitions must be scored in both conditions.',
        'Comparisons are descriptive/exploratory, unadjusted for multiplicity; no automatic scientific conclusion.',
        'A null difference is retained. Non-significance does not establish equivalence.',
        'Pilot and full runs are separate; this report does not pool runs.'
    ]
    grouped = {}
    for condition in meta['condition_order']:
        subset = [r for r in rows if r['condition'] == condition]
        scored = [r['score'] for r in subset if r['score'] is not None]
        grouped[condition] = {}
        for case_id in sorted({r['case_id'] for r in subset}):
            scores = [r['score'] for r in subset if r['case_id'] == case_id]
            if len(scores) == meta['repetitions'] and all(x is not None for x in scores):
                grouped[condition][case_id] = statistics.mean(scores)
        report['conditions'][condition] = {
            'planned': len(subset), 'n_observed': sum(r['observed'] for r in subset),
            'n_scored': len(scored), 'n_missing_or_unscored': len(subset) - len(scored),
            'mean_score': statistics.mean(scored) if scored else None,
            'wilson_95_ci': wilson(sum(scored), len(scored)) if meta['repetitions'] == 1 else None,
            'complete_case_count': len(grouped[condition])}
    for a, b in itertools.combinations(meta['condition_order'], 2):
        ids = sorted(set(grouped[a]) & set(grouped[b]))
        comparison = paired([grouped[a][i] for i in ids], [grouped[b][i] for i in ids], seed=meta['seed'])
        if meta['repetitions'] != 1:
            comparison['p_exact_mcnemar'] = None
        comparison['n_unmatched_or_incomplete_cases'] = len({r['case_id'] for r in rows}) - len(ids)
        report['comparisons'][a + '_vs_' + b] = comparison
    return report


def analyze(directory):
    return summarize(*metrics(directory))


def write_figure(report, path):
    """Portable standalone vector figure; no graphics runtime required."""
    height = 135 + len(report['conditions']) * 65
    pieces = [f'<svg xmlns="http://www.w3.org/2000/svg" width="900" height="{height}" viewBox="0 0 900 {height}">',
              '<rect width="100%" height="100%" fill="#f8fafc"/>',
              '<g font-family="sans-serif" fill="#18283b">',
              '<text x="30" y="35" font-size="22">Observed exact-match scores by condition</text>',
              f'<text x="30" y="60" font-size="13">{escape(report["evidence_kind"])} | {escape(report["mode"])} | {escape(report["status"])}</text>']
    for index, (name, result) in enumerate(report['conditions'].items()):
        y = 105 + index * 65
        mean = result['mean_score']
        pieces.append(f'<text x="30" y="{y}" font-size="15">{escape(name)}</text>')
        pieces.append(f'<rect x="230" y="{y-18}" width="430" height="25" fill="#e2e8f0"/>')
        if mean is not None:
            pieces.append(f'<rect x="230" y="{y-18}" width="{430*mean:.2f}" height="25" fill="#287d8e"/>')
            ci = result['wilson_95_ci']
            if ci:
                lo, hi = (230 + 430 * x for x in ci)
                pieces.append(f'<path d="M {lo:.2f},{y-5} H {hi:.2f} M {lo:.2f},{y-12} V {y+2} M {hi:.2f},{y-12} V {y+2}" stroke="#172033" stroke-width="2"/>')
        label = f'{mean:.1%}' if mean is not None else 'unscored'
        pieces.append(f'<text x="680" y="{y}" font-size="14">{label}; n={result["n_scored"]}/{result["planned"]}</text>')
    pieces.append(f'<text x="30" y="{height-18}" font-size="12">Whiskers: 95% Wilson intervals when applicable. Missing calls excluded from scores, shown in n.</text></g></svg>')
    with Path(path).open('x', encoding='utf-8') as stream:
        stream.write('\n'.join(pieces))


def write_analysis(directory, target):
    target = Path(target)
    report = analyze(directory)
    target.mkdir(parents=True, exist_ok=False)
    write_new(target / 'summary.json', report)
    with (target / 'conditions.csv').open('x', newline='', encoding='utf-8') as stream:
        columns = ['condition', 'planned', 'n_observed', 'n_scored', 'n_missing_or_unscored', 'mean_score']
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        for name, result in report['conditions'].items():
            writer.writerow(dict(result, condition=name))
    write_figure(report, target / 'accuracy.svg')
    return report
