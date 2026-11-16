"""Sequential experiment batches with immutable evidence and conservative reservations."""
from decimal import Decimal
from pathlib import Path
import platform
import subprocess
import time
from uuid import uuid4

from . import __version__
from .providers import AnthropicProvider, MockProvider, ProviderError, valid_tokens
from .openai_provider import OpenAIProvider
from .storage import append_journal, file_hash, inside, lock, read_json, read_journal, utc, write_new
from .studies import load_study, plan, validate


def source_hashes():
    return {p.name: file_hash(p) for p in sorted(Path(__file__).parent.glob('*.py'))}


def cost(config, input_tokens, output_tokens):
    return (Decimal(str(config['input_usd_per_million'])) * input_tokens +
            Decimal(str(config['output_usd_per_million'])) * output_tokens) / Decimal(1_000_000)


def request_for(config, task):
    request = {**{k: config[k] for k in ('model', 'max_output_tokens', 'temperature',
                                      'timeout_seconds', 'api_version')}, 'prompt': task['prompt']}
    if 'reasoning_effort' in config:
        request['reasoning_effort'] = config['reasoning_effort']
    return request


def freeze(study, config, cases, mode):
    protocols = {name: (study / name).read_text(encoding='utf-8')
                 for name in ('protocol.md', 'hypotheses.md') if (study / name).is_file()}
    try:
        commit = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=study, capture_output=True,
                                text=True, timeout=5).stdout.strip() or None
    except (OSError, subprocess.TimeoutExpired):
        commit = None
    return {'schema_version': 2, 'config': config, 'cases': cases, 'mode': mode,
            'tasks': plan(config, cases, mode), 'protocols': protocols,
            'source_hashes': source_hashes(), 'engine_version': __version__,
            'environment': {'python': platform.python_version(), 'platform': platform.system(),
                            'git_commit': commit}, 'created_at': utc()}


def _records(directory):
    records = []
    attempts = directory / 'attempts'
    journal = read_journal(directory / 'journal.jsonl')
    if journal[0] != {'event': 'created', 'snapshot': file_hash(directory / 'snapshot.json')}:
        raise ValueError('Journal snapshot mismatch')
    registered, sealed = {}, {}
    for entry in journal[1:]:
        if set(entry) != {'event', 'attempt', 'sha256', 'sequence', 'previous'}:
            raise ValueError('Invalid journal event fields')
        name = entry['attempt']
        if entry['event'] == 'intent' and name not in registered:
            if name != f'{len(registered)+1:06d}':
                raise ValueError('Journal attempt sequence mismatch')
            registered[name] = entry['sha256']
        elif entry['event'] == 'sealed' and name in registered and name not in sealed:
            sealed[name] = entry['sha256']
        else:
            raise ValueError('Invalid journal event ordering')
    actual = {p.name for p in attempts.iterdir()} if attempts.exists() else set()
    if actual != set(registered):
        raise ValueError('Attempt inventory differs from durable reservation journal')
    if not attempts.exists():
        return records
    for path in sorted(attempts.iterdir()):
        if not path.is_dir() or path.is_symlink():
            raise ValueError('Unexpected attempt entry')
        intent = read_json(path / 'intent.json')
        if file_hash(path / 'intent.json') != registered[path.name]:
            raise ValueError('Intent differs from durable reservation journal')
        outcome = None
        if path.name in sealed:
            if not (path / 'seal.json').is_file() or file_hash(path / 'seal.json') != sealed[path.name]:
                raise ValueError('Outcome differs from journal seal hash')
            outcome = read_json(path / 'seal.json')
            if (not isinstance(outcome, dict) or set(outcome) != {'status', 'retryable', 'finished_at', 'files'}
                    or outcome['status'] not in ('success', 'error', 'uncertain')
                    or type(outcome['retryable']) is not bool or not isinstance(outcome['files'], dict)):
                raise ValueError('Invalid attempt outcome schema')
            files = set(outcome['files'])
            if not {'intent.json'} <= files or files - {'intent.json', 'response.json', 'error.json', 'provider_raw.json'}:
                raise ValueError('Invalid sealed files')
            if outcome['status'] == 'success':
                if 'response.json' not in files or 'error.json' in files or outcome['retryable']:
                    raise ValueError('Invalid successful outcome')
            elif 'error.json' not in files:
                raise ValueError('Error outcome missing error record')
        if outcome:
            expected_files = {'intent.json', 'seal.json'} | set(outcome['files'])
            if {p.name for p in path.iterdir()} != expected_files:
                raise ValueError('Unexpected or missing attempt files')
            for name, sha in outcome['files'].items():
                file = inside(path, name)
                if file.is_symlink() or file_hash(file) != sha:
                    raise ValueError('Attempt integrity mismatch')
        observed_response = read_json(path / 'response.json') if outcome and (path / 'response.json').exists() else None
        if observed_response is None and outcome and (path / 'provider_raw.json').exists():
            raw = read_json(path / 'provider_raw.json')
            usage = raw.get('usage') if isinstance(raw, dict) else None
            if isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ('input_tokens', 'output_tokens')):
                observed_response = {k: usage[k] for k in ('input_tokens', 'output_tokens')}
        response = observed_response if outcome and outcome['status'] == 'success' else None
        records.append({'path': path, 'intent': intent, 'outcome': outcome, 'response': response,
                        'observed_response': observed_response})
    return records


def _load(directory):
    directory = Path(directory).resolve()
    snapshot = read_json(directory / 'snapshot.json')
    if not isinstance(snapshot, dict) or snapshot.get('schema_version') != 2:
        raise ValueError('Unsupported run archive schema; retain the matching engine/export for older archives')
    if read_json(directory / 'snapshot.sha256.json')['sha256'] != file_hash(directory / 'snapshot.json'):
        raise ValueError('Snapshot integrity mismatch')
    config = snapshot['config']
    validate(config, snapshot['cases'])
    expected_tasks = plan(config, snapshot['cases'], snapshot['mode'])
    if snapshot['tasks'] != expected_tasks:
        raise ValueError('Frozen schedule mismatch')
    tasks = {t['id']: t for t in expected_tasks}
    records = _records(directory)
    completed = set()
    counts = {}
    for index, r in enumerate(records, 1):
        intent, outcome = r['intent'], r['outcome']
        task_id = intent['task_id']
        if r['path'].name != f'{index:06d}' or task_id not in tasks or task_id in completed:
            raise ValueError('Invalid or repeated attempt ordering')
        if intent['request'] != request_for(config, tasks[task_id]):
            raise ValueError('Request differs from frozen task')
        if Decimal(intent['reserved_usd']) != cost(config, config['max_input_tokens'], config['max_output_tokens']):
            raise ValueError('Reservation differs from frozen limits')
        counts[task_id] = counts.get(task_id, 0) + 1
        if counts[task_id] > config['max_attempts']:
            raise ValueError('Attempt count exceeds frozen limit')
        if outcome and outcome['status'] == 'success':
            response = r['response']
            valid_tokens(response['input_tokens'])
            valid_tokens(response['output_tokens'])
            if response['stop_reason'] != 'end_turn' or not isinstance(response['text'], str):
                raise ValueError('Incomplete response marked successful')
            completed.add(task_id)
    if len(records) > config['max_requests']:
        raise ValueError('Request count exceeds frozen limit')
    return directory, snapshot, records


def inspect_run(directory):
    directory, snapshot, records = _load(directory)
    config = snapshot['config']
    successes = [r for r in records if r['response'] is not None]
    observations = [r['observed_response'] for r in records if r['observed_response'] is not None]
    for response in observations:
        valid_tokens(response['input_tokens'])
        valid_tokens(response['output_tokens'])
    reserved = sum((Decimal(r['intent']['reserved_usd']) for r in records), Decimal(0))
    actual = sum((cost(config, response['input_tokens'], response['output_tokens'])
                  for response in observations), Decimal(0))
    latest = {r['intent']['task_id']: r for r in records}
    uncertain = [r for r in latest.values() if not r['outcome'] or r['outcome']['status'] == 'uncertain']
    failed = [r for r in latest.values() if r['outcome'] and r['outcome']['status'] == 'error'
              and (not r['outcome']['retryable'] or
                   sum(x['intent']['task_id'] == r['intent']['task_id'] for x in records) >= config['max_attempts'])]
    if any(response['input_tokens'] > config['max_input_tokens'] or
           response['output_tokens'] > config['max_output_tokens'] for response in observations):
        status = 'usage_limit_exceeded'
    elif uncertain:
        status = 'uncertain'
    elif failed:
        status = 'failed'
    elif len(successes) == len(snapshot['tasks']):
        status = 'complete'
    elif len(records) >= config['max_requests'] or reserved + cost(config, config['max_input_tokens'], config['max_output_tokens']) > Decimal(str(config['max_cost_usd'])):
        status = 'budget_exhausted'
    else:
        status = 'pending'
    return {'run_id': directory.name, 'run_dir': str(directory), 'study': config['id'],
            'mode': snapshot['mode'], 'evidence_kind': config['evidence_kind'], 'status': status,
            'planned': len(snapshot['tasks']), 'completed': len(successes), 'requests': len(records),
            'uncertain': len(uncertain), 'failed': len(failed), 'reserved_usd': str(reserved),
            'observed_cost_usd': str(actual),
            'input_tokens': sum(response['input_tokens'] for response in observations),
            'output_tokens': sum(response['output_tokens'] for response in observations)}


def verify(directory):
    result = inspect_run(directory)
    result['integrity'] = 'verified_internal_hashes_not_provider_authenticity'
    return result


def seal(path, status, retryable=False):
    files = {p.name: file_hash(p) for p in sorted(path.iterdir()) if p.is_file()}
    write_new(path / 'seal.json', {'status': status, 'retryable': retryable,
                                 'finished_at': utc(), 'files': files})
    append_journal(path.parent.parent / 'journal.jsonl',
                   {'event': 'sealed', 'attempt': path.name, 'sha256': file_hash(path / 'seal.json')})


def run(study, mode='pilot', resume=None, live=False, retry_uncertain=False,
        provider=None, sleep=time.sleep):
    study = Path(study).resolve()
    config, cases = load_study(study)
    if live != (config['provider'] != 'mock'):
        raise ValueError('Paid providers require --live; --live is invalid for mock studies')
    if resume:
        directory = Path(resume).resolve()
        if directory.parent != (study / 'runs').resolve():
            raise ValueError('Resume must belong to this study')
        _, old, _ = _load(directory)
        current = freeze(study, config, cases, old['mode'])
        if any(old[k] != current[k] for k in ('config', 'cases', 'protocols', 'source_hashes', 'tasks')):
            raise ValueError('Study or engine changed; create a new run instead of rewriting history')
    else:
        directory = study / 'runs' / (utc().replace(':', '').replace('+', '-') + '-' + uuid4().hex[:8])
        directory.mkdir(parents=True, exist_ok=False)
        write_new(directory / 'snapshot.json', freeze(study, config, cases, mode))
        write_new(directory / 'snapshot.sha256.json', {'sha256': file_hash(directory / 'snapshot.json')})
        write_new(directory / 'journal.jsonl', {'event': 'created', 'snapshot': file_hash(directory / 'snapshot.json')})
    with lock(directory / '.lock'):
        _, snapshot, records = _load(directory)
        initial = inspect_run(directory)
        if initial['status'] in ('complete', 'failed', 'usage_limit_exceeded', 'budget_exhausted'):
            return initial
        if initial['status'] == 'uncertain' and not retry_uncertain:
            return initial
        provider = provider or {'anthropic': AnthropicProvider, 'openai': OpenAIProvider, 'mock': MockProvider}[config['provider']]()
        if provider.name != config['provider']:
            raise ValueError('Provider does not match the frozen configuration')
        for task in snapshot['tasks']:
            previous = [r for r in records if r['intent']['task_id'] == task['id']]
            if any(r['response'] for r in previous):
                continue
            for _ in range(len(previous), config['max_attempts']):
                state = inspect_run(directory)
                if state['requests'] >= config['max_requests'] or Decimal(state['reserved_usd']) + cost(config, config['max_input_tokens'], config['max_output_tokens']) > Decimal(str(config['max_cost_usd'])):
                    return state
                request = request_for(config, task)
                # Count endpoint is non-generative. Never send expected answers.
                tokens = valid_tokens(provider.count_tokens(request))
                if tokens > config['max_input_tokens']:
                    raise ValueError('Input token count exceeds configured maximum; no generation sent')
                path = directory / 'attempts' / f'{state["requests"]+1:06d}'
                write_new(path / 'intent.json', {'task_id': task['id'], 'started_at': utc(),
                    'request': request, 'counted_input_tokens': tokens,
                    'reserved_usd': str(cost(config, config['max_input_tokens'], config['max_output_tokens'])),
                    'retry_uncertain_authorized': retry_uncertain})
                append_journal(directory / 'journal.jsonl',
                               {'event': 'intent', 'attempt': path.name, 'sha256': file_hash(path / 'intent.json')})
                try:
                    response = provider.generate(request)
                    write_new(path / 'response.json', response)
                    valid_tokens(response['input_tokens'])
                    valid_tokens(response['output_tokens'])
                    if response['stop_reason'] != 'end_turn':
                        raise ProviderError('incomplete_generation')
                    seal(path, 'success')
                except ProviderError as exc:
                    if exc.raw is not None:
                        write_new(path / 'provider_raw.json', exc.raw)
                    write_new(path / 'error.json', {'code': exc.code, 'retryable': exc.retryable,
                                                   'retry_after': exc.retry_after})
                    uncertain = 'uncertain' in exc.code
                    seal(path, 'uncertain' if uncertain else 'error', exc.retryable)
                    if uncertain or not exc.retryable:
                        return inspect_run(directory)
                    # Respect provider backoff; no hidden provider retries.
                    sleep(max(exc.retry_after, min(2 ** _, 30)))
                _, _, records = _load(directory)
                if response_exists_success(path):
                    if inspect_run(directory)['status'] == 'usage_limit_exceeded':
                        return inspect_run(directory)
                    break
            else:
                return inspect_run(directory)
        return inspect_run(directory)


def response_exists_success(path):
    return read_json(path / 'seal.json')['status'] == 'success'
