"""Prospectively frozen independent campaigns; existing engine owns all requests.

Launch receipts fail closed after interruptions. No suite operation retries an
incomplete launched campaign. Derived results never modify authoritative evidence.
"""
from decimal import Decimal
from pathlib import Path
import shutil
import statistics

from . import engine
from .storage import read_json, write_new, file_hash, digest, lock, inside
from .meno2_campaign import create_campaign, inspect_campaign, run_campaign, export_campaign
from .meno2_analysis import summarize_rows

SUITE_VERSION = 'meno2-suite-1'


def budget_allows(actual, reservation, cap):
    values = [Decimal(str(v)) for v in (actual, reservation, cap)]
    if any(not v.is_finite() or v < 0 for v in values):
        raise ValueError('Costs must be finite and nonnegative')
    return values[0] + values[1] <= values[2]


def create_suite(destination, configurations, cap='10', metadata=None):
    budget_allows(0, 0, cap)
    if not configurations:
        raise ValueError('Suite requires planned blocks')
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=False)
    blocks, identities, signatures = [], set(), set()
    for i, config in enumerate(configurations, 1):
        name = f'block-{i:02d}'
        directory = root/'blocks'/name
        plan = create_campaign(directory, config)
        frozen = read_json(directory/'campaign.json')
        if len(frozen['blocks']) != 1 or len(frozen['config']['models']) != 1:
            raise ValueError('Each suite campaign requires one independent block and one model')
        cfg = frozen['config']
        signatures.add(digest({k:v for k,v in cfg.items() if k not in ('seed','mechanisms')}))
        block = frozen['blocks'][0]
        if block['id'] in identities:
            raise ValueError('Repeated block identity; use independent seeds')
        identities.add(block['id'])
        blocks.append(dict(name=name, path=f'blocks/{name}', sha256=file_hash(directory/'campaign.json'),
                           seed=cfg['seed'], mechanism=block['mechanism'], block_id=block['id'],
                           reservation_usd=plan['reservation_usd']))
    if len(signatures) != 1:
        raise ValueError('Suite settings must match except seed and mechanism')
    manifest = dict(version=SUITE_VERSION, cap_usd=str(cap), blocks=blocks,
                    source_hashes=engine.source_hashes(), metadata=metadata or {},
                    analysis_seed=2026111605, bootstrap_replicates=10000,
                    stopping='actual cost + entire next block reservation <= cap; stop on any incomplete launched block')
    write_new(root/'suite.json', manifest)
    write_new(root/'suite.sha256.json', {'sha256':file_hash(root/'suite.json')})
    return manifest


def _read(root):
    root=Path(root).resolve()
    manifest=read_json(root/'suite.json')
    if file_hash(root/'suite.json') != read_json(root/'suite.sha256.json')['sha256']:
        raise ValueError('Suite manifest integrity mismatch')
    for b in manifest['blocks']:
        directory=inside(root,b['path'])
        if file_hash(directory/'campaign.json') != b['sha256']:
            raise ValueError('Suite campaign integrity mismatch')
        campaign=read_json(directory/'campaign.json')
        if campaign['source_hashes'] != manifest['source_hashes']:
            raise ValueError('Suite source lineage mismatch')
    return root,manifest


def _summary(rows, manifest):
    if not rows:
        return None
    result=summarize_rows(rows,manifest['analysis_seed'],manifest['bootstrap_replicates'])
    if len(result['groups']) != 1:
        raise ValueError('Suite cannot pool distinct model/regime/cohort groups')
    group=next(iter(result['groups'].values()))
    families=result['exploratory_mechanism_strata']
    group['equal_observed_family_balanced_decision']={condition:statistics.mean(
        next(iter(f.values()))['conditions'][condition]['balanced_decision'] for f in families.values())
        for condition in group['conditions']}
    group['observed_families']=len(families)
    group['mechanisms']=families
    # Secondary response-level measures are averaged within block first.
    secondary={}
    for condition in sorted({r['condition'] for r in rows}):
        per_block=[]
        for bid in sorted({r['block_id'] for r in rows}):
            valid=[r['score'] for r in rows if r['block_id']==bid and r['condition']==condition and r['score']['valid']]
            if not valid:
                continue
            per_block.append({
                'unjustified_publication':statistics.mean(int(s['observed_response_labels']['unwarranted_publication_given_available_information']) for s in valid),
                'false_publication':statistics.mean(int(s['published'] and not s['oracle']['truth']) for s in valid),
                'coherent_false_publication':statistics.mean(int(s['coherent_publication'] and not s['oracle']['truth']) for s in valid),
                'nonempty_valid_citations':statistics.mean(int(bool(s['response']['basis_ids'])) for s in valid),
                'cited_valid_support':statistics.mean(int(s['cited_valid_support']) for s in valid),
                'gettier_like':statistics.mean(int(s['observed_response_labels']['gettier_like_response_pattern'] is True) for s in valid),
                'gettier_not_established':statistics.mean(int(s['observed_response_labels']['gettier_like_response_pattern'] is None) for s in valid),
                'contradictory_publication':statistics.mean(int(s['contradictory_publication'] is True) for s in valid),
                'confidence_alignment_loss':statistics.mean(s['confidence_alignment_loss'] for s in valid),
                'source_route_valid':statistics.mean(int(s['source_route_valid']) for s in valid)})
        secondary[condition]={'blocks_with_valid_responses':len(per_block),
            'block_weighted_means':{k:statistics.mean(v[k] for v in per_block) for k in per_block[0]} if per_block else {}}
    group['secondary']=secondary
    return group


def inspect_suite(root):
    root,m=_read(root)
    all_rows,launched_rows,complete_rows,blocks=[],[],[],[]
    actual=Decimal(0)
    coverage={}
    attempted=0
    for b in m['blocks']:
        report=inspect_campaign(root/b['path'])
        status=report['status']
        receipt=root/'launches'/(b['name']+'.json')
        launched=receipt.exists()
        if launched:
            expected=read_json(receipt)
            if (expected.get('campaign_sha256')!=b['sha256'] or
                    expected.get('reservation_usd')!=b['reservation_usd']):
                raise ValueError('Invalid suite launch receipt')
        if status['attempted'] and not launched:
            raise ValueError('Campaign launched outside suite budget authority')
        # Successful response counts alone do not establish a safe completion:
        # the engine may retain an over-limit final response as evidence.
        complete=(launched and status['status']=='complete' and bool(report['runs'])
                  and all(run['status']=='complete' for run in report['runs']))
        all_rows.extend(report['rows'])
        if launched: launched_rows.extend(report['rows'])
        if complete: complete_rows.extend(report['rows'])
        actual+=Decimal(status['observed_cost_usd'])
        attempted+=status['attempted']
        count=coverage.setdefault(b['mechanism'],dict(planned=0,launched=0,completed=0))
        count['planned']+=1;count['launched']+=int(launched);count['completed']+=int(complete)
        blocks.append(dict(b,status=status,run_statuses=[run['status'] for run in report['runs']],
                           launched=launched,complete=complete))
    incomplete=any(b['launched'] and not b['complete'] for b in blocks)
    next_block=next((b for b in blocks if not b['launched']),None)
    reason=('operational_failure' if incomplete else 'complete' if next_block is None else
            'budget_stop' if not budget_allows(actual,next_block['reservation_usd'],m['cap_usd']) else 'ready')
    return dict(version=SUITE_VERSION,cap_usd=m['cap_usd'],observed_cost_usd=str(actual),
        planned_blocks=len(blocks),launched_blocks=sum(b['launched'] for b in blocks),
        completed_blocks=sum(b['complete'] for b in blocks),unexecuted_blocks=sum(not b['launched'] for b in blocks),
        attempted=attempted,completed_trials=sum(b['status']['completed_trials'] for b in blocks),
        stop_reason=reason,coverage=coverage,blocks=blocks,
        planned=_summary(all_rows,m),launched=_summary(launched_rows,m),completed=_summary(complete_rows,m))


def run_suite(root, live=False, providers=None):
    root,m=_read(root)
    if m['source_hashes']!=engine.source_hashes():
        raise ValueError('Source changed since suite freeze')
    with lock(root/'.suite.lock'):
        while True:
            report=inspect_suite(root)
            if report['stop_reason']!='ready':
                return report
            b=next(b for b in report['blocks'] if not b['launched'])
            # Durable before any call: a crash here intentionally stops the suite.
            write_new(root/'launches'/(b['name']+'.json'),dict(campaign_sha256=b['sha256'],
                actual_before_usd=report['observed_cost_usd'],reservation_usd=b['reservation_usd'],cap_usd=m['cap_usd']))
            run_campaign(root/b['path'],live=live,providers=providers)


def export_suite(root,destination,reviewed=False):
    root,m=_read(root)
    report=inspect_suite(root)
    target=Path(destination).resolve()
    if target.is_relative_to(root):
        raise ValueError('Export must be outside authoritative suite')
    target.mkdir(parents=True,exist_ok=False)
    for b in m['blocks']:
        export_campaign(root/b['path'],target/'packages'/b['name'],reviewed)
        out=target/'suite'/b['path']
        out.parent.mkdir(parents=True,exist_ok=True)
        shutil.copytree(target/'packages'/b['name']/'campaign',out)
    for name in ('suite.json','suite.sha256.json'):
        shutil.copyfile(root/name,target/'suite'/name)
    if (root/'launches').exists(): shutil.copytree(root/'launches',target/'suite'/'launches')
    shutil.copytree(target/'packages'/m['blocks'][0]['name']/'research_lab',target/'research_lab')
    write_new(target/'analysis.json',report)
    (target/'reproduce.py').write_text('''from pathlib import Path
import subprocess, sys
from research_lab.storage import read_json, file_hash, inside, digest
from research_lab.meno2_suite import inspect_suite
root=Path(__file__).resolve().parent
for name,sha in read_json(root/'SHA256.json').items():
    if file_hash(inside(root,name)) != sha: raise SystemExit('Integrity failure: '+name)
for package in sorted((root/'packages').iterdir()):
    subprocess.run([sys.executable,'-B',str(package/'reproduce.py')],check=True)
observed=inspect_suite(root/'suite')
expected=read_json(root/'analysis.json')
for report in (observed,expected):
    for block in report['blocks']: block['status'].pop('campaign_dir',None)
if digest(observed)!=digest(expected): raise SystemExit('Suite analysis differs')
print('VERIFIED suite: all scores and cross-campaign analysis independently replayed')
''',encoding='utf-8')
    write_new(target/'SHA256.json',{p.relative_to(target).as_posix():file_hash(p) for p in target.rglob('*') if p.is_file()})
    return {'export_dir':str(target),'planned_blocks':len(m['blocks'])}
