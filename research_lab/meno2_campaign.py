"""MENO campaign lineage over the existing laboratory's durable invocation engine."""
import json
import math
import random
import shutil
from decimal import Decimal
from pathlib import Path

from . import engine
from .storage import canonical, digest, file_hash, read_json, write_new, lock
from .studies import default_config, validate, load_study, number
from .meno2_scoring import parse_response, score_response, SCORING_VERSION
from .meno2_analysis import summarize_rows, ANALYSIS_VERSION

CONDITIONS = ('reflection', 'sham', 'exact_facts', 'structured_audit')
CAMPAIGNS = {'A': 'Instrument validation', 'B': 'Initial observability',
             'C': 'Same-information auditing', 'D': 'Information acquisition',
             'E': 'Generalization', 'F': 'Adaptive verification (reserved)'}


def _science():
    from .meno2_cases import generate_blocks
    from .meno2_render import evidence_for, render_initial, render_continuation
    from .meno2_oracle import assess
    return generate_blocks, evidence_for, render_initial, render_continuation, assess


def _read_frozen(root):
    root = Path(root).resolve()
    frozen = read_json(root / 'campaign.json')
    if read_json(root / 'campaign.sha256.json')['sha256'] != file_hash(root / 'campaign.json'):
        raise ValueError('Campaign integrity mismatch')
    return root, frozen


def create_campaign(destination, configuration=None):
    generate_blocks, _, _, _, assess = _science()
    config = {'schema_version': 1, 'campaign': 'C', 'regime': 'I', 'seed': 20261115,
              'blocks': 2, 'repetitions': 1, 'threshold': '0.95',
              'mechanisms': None, 'world_options': {}, 'bootstrap_replicates': 2000, 'arms': None,
              'mode': 'pilot', 'analysis_status': 'exploratory',
              'hypothesis': 'Structured audit improves balanced decisions over exact-facts updates.',
              'exclusions': 'None after collection; all preselected eligible blocks remain.',
              'missing_policy': 'Missing and invalid outputs contribute zero primary indicators.',
              'stopping_policy': 'Fixed planned trials; stop model on uncertain or failed transport; no retries.',
              'models': [{'id': 'mock', 'provider': 'mock', 'model': 'mock-v1'}],
              'max_cost_usd': 0}
    supplied = configuration or {}
    if set(supplied) - set(config):
        raise ValueError('Unknown campaign configuration fields')
    config.update(supplied)
    number(config['max_cost_usd'], 'campaign max_cost_usd')
    if config['campaign'] not in CAMPAIGNS or config['campaign'] == 'F':
        raise ValueError('Campaign F requires its separately specified action/cost protocol')
    if config['regime'] not in ('I', 'II') or config['mode'] not in ('pilot', 'full'):
        raise ValueError('Invalid regime or mode')
    if config['arms'] is not None and (config['campaign'] != 'C' or
            not isinstance(config['arms'], list) or not config['arms'] or
            any(arm not in CONDITIONS for arm in config['arms']) or
            len(set(config['arms'])) != len(config['arms'])):
        raise ValueError('Optional arms require Campaign C and unique known continuation names')
    if (config['campaign'] == 'C' and config['regime'] != 'I') or (config['campaign'] == 'D' and config['regime'] != 'II'):
        raise ValueError('Campaign C is regime I; Campaign D is regime II')
    for field in ('blocks', 'repetitions', 'bootstrap_replicates'):
        if type(config[field]) is not int or config[field] < (100 if field == 'bootstrap_replicates' else 1):
            raise ValueError('Invalid ' + field)
    if type(config['seed']) is not int or not Decimal('0.5') < Decimal(str(config['threshold'])) <= 1:
        raise ValueError('Invalid seed or publication threshold')
    if config['analysis_status'] not in ('exploratory', 'confirmatory'):
        raise ValueError('Invalid analysis status')
    if not all(isinstance(config[k], str) and config[k].strip() for k in ('hypothesis', 'exclusions', 'missing_policy', 'stopping_policy')):
        raise ValueError('Protocol fields must be explicit')
    if not isinstance(config['models'], list) or not config['models']:
        raise ValueError('At least one model required')
    blocks = generate_blocks(config['seed'], config['blocks'], config['regime'], config['mechanisms'], **config['world_options'])
    # Eligibility is computed before outputs and independently checked against final available evidence.
    _, evidence_for, _, _, _ = _science()
    from .meno2_cases import validate_block
    for block in blocks:
        construction_check = validate_block(block, config['threshold'])
        roles = {c['role']: c for c in block['cases']}
        s, l = roles.get('S'), roles.get('L')
        checks = [assess(c['world'], evidence_for(c, 'exact_facts', config['regime']), threshold=config['threshold']) for c in (s, l)] if s and l else []
        block['eligible'] = bool(checks and checks[0]['truth'] and checks[1]['truth'] and
                                 checks[0]['publication_warranted'] and not checks[1]['publication_warranted'])
        block['eligibility_reason'] = 'S true/warranted and L true/unwarranted under final diagnostic evidence' if block['eligible'] else 'Outside primary estimand; retained for secondary outcomes'
        block['construction_validation'] = construction_check
        block['eligibility_threshold'] = construction_check['threshold_exact']
    models = []
    for i, selected in enumerate(config['models']):
        if not isinstance(selected, dict):
            raise ValueError('Invalid model configuration')
        model = default_config(f'meno-model-{i}')
        model.update(evaluator='none', max_attempts=1, max_input_tokens=60000,
                     max_output_tokens=1024, repetitions=1)
        model.update({k: v for k, v in selected.items() if k != 'id'})
        model['id'] = selected.get('id', f'model-{i}')
        if model['max_attempts'] != 1:
            raise ValueError('MENO freezes one attempt per trial; uncertain retries require a new reviewed protocol')
        model['conditions'] = [{'id': 'request', 'instruction': ''}]
        model['evaluator'] = 'none'
        model['repetitions'] = 1
        validate(model, [{'id': 'validation', 'prompt': 'offline configuration validation'}])
        models.append(model)
    if len({m['id'] for m in models}) != len(models):
        raise ValueError('Duplicate model identity')
    config['models'] = models
    arms = [] if config['campaign'] == 'B' else list(CONDITIONS)
    if config['arms'] is not None:
        arms = list(config['arms'])
    if config['campaign'] == 'D':
        arms.append('repair')
    trials = []
    for model in models:
        for block in blocks:
            for case in block['cases']:
                for rep in range(config['repetitions']):
                    parent_id = 'trial-' + digest([model['id'], block['id'], case['id'], rep, 'initial'])[:24]
                    for arm in ['initial'] + arms:
                        trials.append({'id': parent_id if arm == 'initial' else 'trial-' + digest([parent_id, arm])[:24],
                                       'parent_id': None if arm == 'initial' else parent_id,
                                       'model': model['id'], 'block_id': block['id'], 'case_id': case['id'],
                                       'repetition': rep, 'condition': arm})
    reservation = sum((engine.cost(m, m['max_input_tokens'], m['max_output_tokens']) *
                       sum(t['model'] == m['id'] for t in trials) for m in models), Decimal(0))
    if Decimal(str(config['max_cost_usd'])) < reservation:
        raise ValueError(f'Campaign budget below full reservation {reservation}')
    for m in models:
        count = sum(t['model'] == m['id'] for t in trials)
        if m['provider'] != 'mock' and (m['max_requests'] < count or Decimal(str(m['max_cost_usd'])) < engine.cost(m, m['max_input_tokens'], m['max_output_tokens']) * count):
            raise ValueError('Model request/budget authorization below complete planned campaign')
    frozen = {'config': config, 'blocks': blocks, 'trials': trials,
              'scoring_version': SCORING_VERSION, 'analysis_version': ANALYSIS_VERSION,
              'source_hashes': engine.source_hashes(), 'reservation_usd': str(reservation),
              'evidence_kind': 'synthetic' if all(m['provider'] == 'mock' for m in models) else 'model_generated',
              'protocol_version': 'meno2-1'}
    if len({m['provider'] == 'mock' for m in models}) > 1:
        raise ValueError('Keep synthetic and real-model evidence in separate campaigns')
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=False)
    write_new(root / 'campaign.json', frozen)
    write_new(root / 'campaign.sha256.json', {'sha256': file_hash(root / 'campaign.json')})
    return plan_campaign(root)


def plan_campaign(root):
    root, frozen = _read_frozen(root)
    return {'campaign_dir': str(root), 'campaign': frozen['config']['campaign'],
            'regime': frozen['config']['regime'], 'mode': frozen['config']['mode'],
            'planned_blocks': len(frozen['blocks']), 'eligible_blocks': sum(b['eligible'] for b in frozen['blocks']),
            'planned_trials': len(frozen['trials']), 'evidence_kind': frozen['evidence_kind'],
            'reservation_usd': frozen['reservation_usd'], 'max_cost_usd': frozen['config']['max_cost_usd'],
            'models': [m['id'] for m in frozen['config']['models']]}


def _case_map(frozen):
    return {(b['id'], c['id']): (b, c) for b in frozen['blocks'] for c in b['cases']}


def _stage_path(root, model_index, stage):
    return root / 'stages' / f'model-{model_index}-{stage}'


def _stage_records(stage, source_hashes=None):
    runs = sorted((stage / 'runs').glob('*')) if (stage / 'runs').exists() else []
    if len(runs) > 1:
        raise ValueError('Multiple archives for one campaign stage; refusing ambiguous lineage')
    if not runs:
        if (stage / 'launch.json').exists():
            raise ValueError('Previously launched stage archive is missing; preserve reservation and investigate')
        return {}, None
    identity = stage / 'run_identity.json'
    if identity.exists() and read_json(identity)['run_id'] != runs[0].name:
        raise ValueError('Campaign stage run identity differs')
    _, snapshot, records = engine._load(runs[0])
    config, cases = load_study(stage)
    expected = engine.freeze(stage, config, cases, snapshot['mode'])
    if any(snapshot[k] != expected[k] for k in ('config', 'cases', 'protocols', 'tasks')):
        raise ValueError('Run snapshot does not belong to frozen campaign stage')
    if source_hashes is not None and snapshot['source_hashes'] != source_hashes:
        raise ValueError('Run source differs from frozen campaign source')
    tasks = {t['id']: t for t in snapshot['tasks']}
    result = {}
    for record in records:
        trial = tasks[record['intent']['task_id']]['case_id']
        result[trial] = {'response': record['response'],
                         'observed_response': record['observed_response'],
                         'provider_raw': read_json(record['path'] / 'provider_raw.json') if (record['path'] / 'provider_raw.json').exists() else None,
                         'operational_status': record['outcome']['status'] if record['outcome'] else 'uncertain',
                         'attempt': str(record['path'].relative_to(stage)),
                         'intent': record['intent'], 'outcome': record['outcome'],
                         'raw_error': read_json(record['path'] / 'error.json') if (record['path'] / 'error.json').exists() else None}
    return result, runs[0]


def _materialize(root, frozen, model_index, stage, parents, allow_create=True):
    _, _, render_initial, render_continuation, _ = _science()
    model = frozen['config']['models'][model_index]
    selected = [t for t in frozen['trials'] if t['model'] == model['id'] and (t['condition'] == 'initial') == (stage == 'initial')]
    cases = _case_map(frozen)
    data, lineage = [], []
    for trial in selected:
        _, case = cases[(trial['block_id'], trial['case_id'])]
        parent = parents.get(trial['parent_id']) if trial['parent_id'] else None
        if trial['parent_id'] and (not parent or not parent['response']):
            raise ValueError('Follow-up requires its exact successful parent transport response')
        text = parent['response']['text'] if parent else None
        prompt = render_initial(case, frozen['config']['threshold']) if stage == 'initial' else render_continuation(case, text, trial['condition'], frozen['config']['regime'], frozen['config']['threshold'])
        data.append({'id': trial['id'], 'prompt': prompt})
        lineage.append({'trial_id': trial['id'], 'parent_trial_id': trial['parent_id'],
                        'parent_response_hash': digest(parent['response']) if parent else None,
                        'campaign_hash': file_hash(root / 'campaign.json'), 'prompt_hash': digest(prompt)})
    exact_budget = engine.cost(model, model['max_input_tokens'], model['max_output_tokens']) * len(data)
    budget = float(exact_budget)
    if Decimal(str(budget)) < exact_budget:
        budget = math.nextafter(budget, math.inf)
    config = dict(model, id=f'meno-model-{model_index}-{stage}', pilot_cases=len(data),
                  max_requests=len(data), max_cost_usd=budget,
                  seed=frozen['config']['seed'])
    validate(config, data)
    protocol = canonical({'campaign': frozen['config'], 'lineage': lineage, 'campaign_hash': file_hash(root / 'campaign.json')}).decode()
    hypotheses = frozen['config']['hypothesis']
    directory = _stage_path(root, model_index, stage)
    expected_files = {'study.json': canonical(config).decode() + '\n',
                      'cases.jsonl': ''.join(canonical(row).decode() + '\n' for row in data),
                      'protocol.md': protocol, 'hypotheses.md': hypotheses}
    started = (directory / 'launch.json').exists() or (directory / 'runs').exists()
    for name, content in expected_files.items():
        path = directory / name
        if path.exists():
            if path.read_text(encoding='utf-8') != content:
                raise ValueError('Stage differs from frozen campaign/parent lineage')
        elif allow_create and not started:
            directory.mkdir(parents=True, exist_ok=True)
            with path.open('x', encoding='utf-8', newline='') as stream:
                stream.write(content)
        else:
            raise ValueError('Incomplete frozen stage; preserve archive and investigate')
    return directory


class ScriptedProvider:
    """Synthetic execution fixture; no access to truth, oracle or case labels."""
    name = 'mock'

    def count_tokens(self, request):
        return len(request['prompt'].encode('utf-8'))

    def generate(self, request):
        # Intentionally conservative fixed behavior: demonstrates plumbing, not performance.
        text = json.dumps({'answer': 'abstain', 'p_true': .5, 'support_judgment': 'underdetermined',
                           'basis_ids': [], 'explanation': 'Synthetic transport fixture; no scientific inference.', 'action': 'verify'})
        return {'text': text, 'model': 'mock-v1', 'input_tokens': self.count_tokens(request),
                'output_tokens': len(text), 'request_id': None, 'stop_reason': 'end_turn',
                'raw': {'synthetic': True, 'text': text}}


def run_campaign(root, live=False, providers=None):
    root, frozen = _read_frozen(root)
    if frozen['source_hashes'] != engine.source_hashes():
        raise ValueError('Source changed since campaign freeze; create a new campaign')
    real = frozen['evidence_kind'] != 'synthetic'
    if live != real:
        raise ValueError('Real model campaigns require --live; mock campaigns forbid it')
    with lock(root / '.campaign.lock'):
        order = list(range(len(frozen['config']['models'])))
        random.Random(frozen['config']['seed']).shuffle(order)
        for index in order:
            model = frozen['config']['models'][index]
            provider = (providers or {}).get(model['id'])
            if provider is None and model['provider'] == 'mock':
                provider = ScriptedProvider()
            parents = {}
            for stage in ('initial', 'followup'):
                if stage == 'followup' and frozen['config']['campaign'] == 'B':
                    continue
                expected_stage = _stage_path(root, index, stage)
                registry = root / (expected_stage.name + '.launch.json')
                if registry.exists() and not (expected_stage / 'launch.json').exists():
                    raise ValueError('Registered campaign stage is missing; refusing to repeat requests')
                directory = _materialize(root, frozen, index, stage, parents)
                _, existing = _stage_records(directory, frozen['source_hashes'])
                launch = directory / 'launch.json'
                if not launch.exists():
                    launch_record = {'campaign_hash': file_hash(root / 'campaign.json'),
                                     'stage': directory.name, 'planned_requests': load_study(directory)[0]['max_requests']}
                    write_new(registry, launch_record)
                    write_new(launch, launch_record)
                try:
                    status = engine.run(directory, mode=frozen['config']['mode'], resume=existing, live=live, provider=provider)
                finally:
                    archives = list((directory / 'runs').glob('*'))
                    if len(archives) == 1 and not (directory / 'run_identity.json').exists():
                        write_new(directory / 'run_identity.json', {'run_id': archives[0].name})
                if status['status'] != 'complete':
                    break
                if stage == 'initial':
                    parents, _ = _stage_records(directory, frozen['source_hashes'])
    return inspect_campaign(root)


def inspect_campaign(root):
    root, frozen = _read_frozen(root)
    _, evidence_for, _, _, assess = _science()
    observed, run_statuses = {}, []
    for index, model in enumerate(frozen['config']['models']):
        parents = {}
        for stage in ('initial', 'followup'):
            directory = _stage_path(root, index, stage)
            registry = root / (directory.name + '.launch.json')
            if registry.exists() and not (directory / 'launch.json').exists():
                raise ValueError('Registered campaign stage is missing')
            if not directory.exists():
                continue
            # Rebuild only in memory to validate current evidence and parent lineage.
            _materialize(root, frozen, index, stage, parents, allow_create=False)
            records, run = _stage_records(directory, frozen['source_hashes'])
            observed.update(records)
            if run:
                run_statuses.append(engine.inspect_run(run))
            if stage == 'initial':
                parents = records
    cases = _case_map(frozen)
    rows, scores = [], {}
    for trial in frozen['trials']:
        block, case = cases[(trial['block_id'], trial['case_id'])]
        evidence = case['initial_evidence'] if trial['condition'] == 'initial' else evidence_for(case, trial['condition'], frozen['config']['regime'])
        record = observed.get(trial['id'], {})
        response = record.get('response')
        parsed = parse_response(response['text'], evidence) if response else {'valid': False}
        basis = parsed['response']['basis_ids'] if parsed.get('valid') else []
        oracle = assess(case['world'], evidence, basis, frozen['config']['threshold'])
        # Evaluate THIS response's cited route against the initial information,
        # independently of later diagnostic/repair records. Sham transcript IDs
        # refer to the original observation and add no new information.
        initial_basis = list(dict.fromkeys(e.get('copied_from_record', e['id']) for e in evidence if e['id'] in basis))
        initial_oracle = oracle if trial['condition'] == 'initial' else assess(
            case['world'], case['initial_evidence'], initial_basis, frozen['config']['threshold'])
        score = score_response(response['text'] if response else None, evidence, oracle,
                               scores.get(trial['parent_id']), case['structure_labels'], initial_oracle=initial_oracle)
        scores[trial['id']] = score
        observable_eligibility = block['eligible'] and trial['condition'] != 'repair' and not (
            block['regime'] == 'II' and trial['condition'] in ('initial', 'reflection', 'sham'))
        received = [value for value in (record.get('observed_response'), record.get('provider_raw')) if isinstance(value, dict)]
        incident_kind = record.get('operational_status', 'missing')
        if any(value.get('stop_reason') == 'max_tokens' or value.get('status') == 'incomplete' for value in received):
            incident_kind = 'truncation_or_incomplete'
        elif any(value.get('stop_reason') == 'refusal' for value in received):
            incident_kind = 'provider_refusal'
        elif response and not score['valid']:
            incident_kind = 'refusal_text_candidate' if score['refusal_text_candidate'] else 'invalid_schema'
        elif score['contradictory_publication']:
            incident_kind = 'contradictory_publication'
        rows.append(dict(trial, role=case['role'], eligible=observable_eligibility, incident_kind=incident_kind,
                         regime=block['regime'], mechanism=block['mechanism'], cohort=block['cohort'],
                         score=score, evidence=evidence, operational_status=record.get('operational_status', 'missing'),
                         attempt=record.get('attempt'), invocation=record,
                         parent_response_hash=digest(observed[trial['parent_id']]['response']) if trial['parent_id'] in observed and observed[trial['parent_id']]['response'] else None))
    scoring_provenance = {
        'frozen_scoring_version': frozen.get('scoring_version', 'meno2-1'),
        'applied_scoring_version': SCORING_VERSION,
        'frozen_analysis_version': frozen.get('analysis_version', 'meno2-1'),
        'applied_analysis_version': ANALYSIS_VERSION,
        'read_only_rescore': (frozen.get('scoring_version', 'meno2-1') != SCORING_VERSION
                              or frozen.get('analysis_version', 'meno2-1') != ANALYSIS_VERSION)}
    completed = sum(r['operational_status'] == 'success' for r in rows)
    status = dict(plan_campaign(root), completed_trials=completed, missing_trials=len(rows) - completed,
                  completed_blocks=sum(all(r['operational_status'] == 'success' for r in rows if r['block_id'] == b['id']) for b in frozen['blocks']),
                  valid_responses=sum(r['score']['valid'] for r in rows),
                  invalid_responses=sum(r['operational_status'] == 'success' and not r['score']['valid'] for r in rows),
                  contradictory_publications=sum(r['score']['contradictory_publication'] is True for r in rows),
                  scoring_provenance=scoring_provenance,
                  attempted=sum(s['requests'] for s in run_statuses),
                  reserved_usd=str(sum((Decimal(s['reserved_usd']) for s in run_statuses), Decimal(0))),
                  observed_cost_usd=str(sum((Decimal(s['observed_cost_usd']) for s in run_statuses), Decimal(0))),
                  status='complete' if completed == len(rows) else 'incomplete',
                  incidents={kind: sum(r['incident_kind'] == kind for r in rows) for kind in sorted({r['incident_kind'] for r in rows})},
                  source_matches=frozen['source_hashes'] == engine.source_hashes())
    analysis = summarize_rows(rows, frozen['config']['seed'], frozen['config']['bootstrap_replicates'], [t['id'] for t in frozen['trials']])
    analysis['scoring_provenance'] = scoring_provenance
    return {'status': status, 'protocol': frozen['config'], 'blocks': frozen['blocks'],
            'rows': rows, 'runs': run_statuses,
            'analysis': analysis,
            'campaign_sha256': file_hash(root / 'campaign.json')}


def export_campaign(root, destination, reviewed=False):
    report = inspect_campaign(root)
    if report['status']['evidence_kind'] != 'synthetic' and not reviewed:
        raise ValueError('Real-model export requires disclosure review')
    root, frozen = _read_frozen(root)
    target = Path(destination).resolve()
    if target.is_relative_to(root):
        raise ValueError('Export must be outside authoritative campaign')
    if not report['status']['source_matches']:
        raise ValueError('Export requires matching frozen source for independent rescoring')
    target.mkdir(parents=True, exist_ok=False)
    # Explicit allowlist includes raw synthetic evidence or disclosure-reviewed model evidence.
    for path in root.rglob('*'):
        if path.is_file() and (path.parent == root and path.name.endswith('.launch.json') or path.name in {'campaign.json', 'campaign.sha256.json', 'study.json', 'cases.jsonl',
                                            'protocol.md', 'hypotheses.md', 'snapshot.json', 'snapshot.sha256.json',
                                            'journal.jsonl', 'intent.json', 'response.json', 'error.json', 'provider_raw.json', 'seal.json',
                                            'launch.json', 'run_identity.json'}):
            out = target / 'campaign' / path.relative_to(root)
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, out)
    package = target / 'research_lab'
    package.mkdir()
    for source in Path(__file__).parent.glob('*.py'):
        shutil.copyfile(source, package / source.name)
    write_new(target / 'analysis.json', report['analysis'])
    write_new(target / 'scores.json', {r['id']: r['score'] for r in report['rows']})
    (target / 'reproduce.py').write_text('''from pathlib import Path
from research_lab.storage import read_json, file_hash, inside, digest
from research_lab.meno2_campaign import inspect_campaign
root = Path(__file__).resolve().parent
for name, sha in read_json(root / 'SHA256.json').items():
    if file_hash(inside(root, name)) != sha:
        raise SystemExit('Integrity failure: ' + name)
report = inspect_campaign(root / 'campaign')
if digest({r['id']: r['score'] for r in report['rows']}) != digest(read_json(root / 'scores.json')):
    raise SystemExit('Rescoring differs')
if report['analysis'] != read_json(root / 'analysis.json'):
    raise SystemExit('Rescoring or analysis differs')
print('VERIFIED: archived requests, response rescoring and block analysis replay; not provider authenticity')
''', encoding='utf-8')
    write_new(target / 'SHA256.json', {p.relative_to(target).as_posix(): file_hash(p) for p in target.rglob('*') if p.is_file()})
    return {'export_dir': str(target), 'scope': 'raw_response_rescoring_and_block_analysis',
            'scoring_version': SCORING_VERSION, 'analysis_version': ANALYSIS_VERSION,
            'evidence_kind': frozen['evidence_kind']}
