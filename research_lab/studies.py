"""Study scaffolding, strict configuration validation and paired run schedules."""
import json
import math
from pathlib import Path
import random

from .storage import inside, read_json, slug, write_new
from .openai_provider import OPENAI_PROFILES


def default_config(name):
    return {'schema_version': 1, 'id': name, 'title': name.replace('-', ' ').title(),
            'protocol_status': 'draft', 'evidence_kind': 'synthetic',
            'dataset': 'cases.jsonl', 'provider': 'mock', 'model': 'mock-v1',
            'seed': 20261111, 'pilot_cases': 2, 'repetitions': 1,
            'conditions': [{'id': 'direct', 'instruction': 'Return only the answer.'},
                           {'id': 'careful', 'instruction': 'Check your answer; return only the answer.'}],
            'evaluator': 'exact_match', 'max_output_tokens': 64, 'max_input_tokens': 4096,
            'temperature': 0, 'max_attempts': 2, 'max_requests': 20,
            'max_cost_usd': 0, 'input_usd_per_million': 0,
            'output_usd_per_million': 0, 'timeout_seconds': 60,
            'api_version': '2023-06-01'}


def init_study(root, name):
    slug(name)
    directory = Path(root) / 'studies' / name
    directory.mkdir(parents=True, exist_ok=False)
    write_new(directory / 'study.json', default_config(name))
    cases = [{'id': f'case-{i}', 'prompt': f'What is {i} + {i}?', 'expected': str(i * 2)}
             for i in range(1, 5)]
    (directory / 'cases.jsonl').write_text(''.join(json.dumps(c) + '\n' for c in cases), encoding='utf-8')
    (directory / 'protocol.md').write_text(
        '# Draft protocol\n\nNo scientific hypothesis or research outcome is fixed.\n'
        'The arithmetic cases and two prompts are synthetic software smoke fixtures only.\n\n'
        '## Researcher to specify before data collection\n\n'
        '- Research question and hypotheses, including null and negative outcomes\n'
        '- Primary endpoint, sampling unit, sample size and stopping rule\n'
        '- Conditions, randomization, exclusions, missing-data handling\n'
        '- Evaluation rubric, blinding and inter-rater agreement where applicable\n'
        '- Analysis plan, multiplicity, uncertainty and generalization limits\n'
        '- Privacy/consent review and data retention, if humans participate\n'
        '- Freeze/version date; deviations recorded separately\n', encoding='utf-8')
    (directory / 'hypotheses.md').write_text('# Hypotheses (unfixed)\n\nTo be specified by the researcher before collection.\n', encoding='utf-8')
    (directory / 'findings.md').write_text('# Observed findings\n\nNo scientific findings recorded. Mock outputs are synthetic software evidence.\n', encoding='utf-8')
    return directory


def number(value, name, minimum=0, integer=False):
    if type(value) not in ((int,) if integer else (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f'Invalid {name}')


def validate(config, cases):
    if not isinstance(config, dict):
        raise ValueError('Manifest must be an object')
    required = set(default_config('example'))
    optional = {'reasoning_effort'} if config.get('provider') == 'openai' else set()
    differing = (required - set(config)) | (set(config) - required - optional)
    if differing:
        raise ValueError(f'Manifest fields differ: {sorted(differing)}')
    slug(config['id'])
    if type(config['schema_version']) is not int or config['schema_version'] != 1:
        raise ValueError('Unsupported schema version')
    for key in ('title', 'model', 'api_version'):
        if not isinstance(config[key], str) or not config[key].strip():
            raise ValueError(f'Invalid {key}')
    if config['protocol_status'] not in ('draft', 'frozen'):
        raise ValueError('protocol_status must be draft or frozen')
    if (config['provider'], config['evidence_kind']) not in (('mock', 'synthetic'), ('anthropic', 'model_generated'), ('openai', 'model_generated')):
        raise ValueError('Provider/evidence mismatch; human data must stay outside the model engine')
    if config['evaluator'] not in ('exact_match', 'none'):
        raise ValueError('Unsupported evaluator')
    for key in ('seed', 'pilot_cases', 'repetitions', 'max_output_tokens', 'max_input_tokens', 'max_attempts', 'max_requests'):
        number(config[key], key, 0 if key == 'seed' else 1, integer=True)
    for key in ('max_cost_usd', 'input_usd_per_million', 'output_usd_per_million'):
        number(config[key], key)
    if config['provider'] == 'openai' and config['model'] in ('gpt-6.1-sol', 'gpt-6-astra'):
        if config['temperature'] is not None:
            raise ValueError('Reasoning profiles require temperature null; temperature is not sent')
    else:
        number(config['temperature'], 'temperature')
        if config['temperature'] > 1:
            raise ValueError('temperature must be <= 1')
    number(config['timeout_seconds'], 'timeout_seconds', 1)
    if config['max_attempts'] > 10:
        raise ValueError('max_attempts must be <= 10')
    conditions = config['conditions']
    if not isinstance(conditions, list) or not conditions:
        raise ValueError('At least one condition required')
    ids = []
    for c in conditions:
        if not isinstance(c, dict) or set(c) != {'id', 'instruction'} or not isinstance(c['instruction'], str):
            raise ValueError('Invalid condition')
        ids.append(slug(c['id']))
    if len(set(ids)) != len(ids):
        raise ValueError('Duplicate condition')
    if not cases:
        raise ValueError('Dataset is empty')
    seen = set()
    for c in cases:
        if not isinstance(c, dict) or set(c) - {'id', 'prompt', 'expected'} or not {'id', 'prompt'} <= set(c):
            raise ValueError('Invalid case fields')
        slug(c['id'])
        if c['id'] in seen or not isinstance(c['prompt'], str) or not c['prompt'].strip():
            raise ValueError('Duplicate or invalid case')
        if config['evaluator'] == 'exact_match' and not isinstance(c.get('expected'), str):
            raise ValueError('exact_match requires string expected values')
        seen.add(c['id'])
    if config['provider'] != 'mock':
        if config['protocol_status'] != 'frozen' or config['model'] == 'mock-v1':
            raise ValueError('Live experiments need a frozen protocol and explicit model')
        if any(config[k] <= 0 for k in ('max_cost_usd', 'input_usd_per_million', 'output_usd_per_million')):
            raise ValueError('Live experiments need positive budget and reviewed token prices')
    if config['provider'] == 'openai':
        if config['api_version'] != 'responses-v1':
            raise ValueError('OpenAI requires api_version responses-v1')
        profile = OPENAI_PROFILES.get(config['model'])
        if profile is None or config.get('reasoning_effort', 'none') != profile['reasoning_effort']:
            raise ValueError('Supported OpenAI profiles: gpt-6-astra max, gpt-6.1-sol medium, gpt-6-luna none')
        if config['max_input_tokens'] > 272000 or config['max_output_tokens'] > 128000:
            raise ValueError('OpenAI limits: <=272000 input and <=128000 total output tokens')
        if any(config[k] < profile[k] for k in ('input_usd_per_million', 'output_usd_per_million')):
            raise ValueError('Token prices are below the reviewed model rates; update prices before planning')


def load_study(directory):
    directory = Path(directory)
    config = read_json(directory / 'study.json')
    if not isinstance(config, dict):
        raise ValueError('Manifest must be an object')
    dataset = inside(directory, config.get('dataset'))
    try:
        cases = [json.loads(line) for line in dataset.read_text(encoding='utf-8').splitlines() if line.strip()]
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid JSONL dataset') from exc
    validate(config, cases)
    return config, cases


def plan(config, cases, mode):
    if mode not in ('pilot', 'full'):
        raise ValueError('Mode must be pilot or full')
    chosen = list(cases)
    rng = random.Random(config['seed'])
    rng.shuffle(chosen)
    if mode == 'pilot':
        chosen = chosen[:config['pilot_cases']]
    tasks = []
    for case in chosen:
        for rep in range(config['repetitions']):
            for condition in config['conditions']:
                tasks.append({'id': f'task-{len(tasks)+1:06d}', 'case_id': case['id'],
                              'repetition': rep, 'condition': condition['id'],
                              'prompt': condition['instruction'] + '\n\n' + case['prompt'],
                              'expected': case.get('expected')})
    rng.shuffle(tasks)
    return tasks
