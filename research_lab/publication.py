"""Allowlisted metric-only publication bundles; never copy source study directories."""
from pathlib import Path
import shutil

from .analysis import metrics, summarize, write_figure
from .storage import file_hash, write_new


REPRODUCE = '''"""Offline numeric replay and bundle integrity verification. No model calls."""
from pathlib import Path
from research_lab.storage import read_json, file_hash, inside
from research_lab.analysis import summarize

root = Path(__file__).resolve().parent
manifest = read_json(root / 'SHA256.json')
for name, sha in manifest.items():
    if file_hash(inside(root, name)) != sha:
        raise SystemExit('Integrity failure: ' + name)
report = summarize(read_json(root / 'metrics.json'), read_json(root / 'metadata.json'))
if report != read_json(root / 'summary.json'):
    raise SystemExit('Recomputed statistics differ')
print('VERIFIED: hashes and numerical analysis replay; not provider authenticity or raw-response re-scoring')
'''


def export_run(directory, destination, reviewed_public=False):
    rows, meta = metrics(directory)
    if meta['evidence_kind'] != 'synthetic' and not reviewed_public:
        raise ValueError('Model metrics need disclosure review: pass --reviewed-public only after review')
    destination = Path(destination).resolve()
    source_run = Path(directory).resolve()
    if destination.is_relative_to(source_run):
        raise ValueError('Export must be outside the raw run archive')
    destination.mkdir(parents=True, exist_ok=False)
    # Replace case identifiers; preserve matching, never carry prompts/responses/labels.
    case_ids = {name: f'unit-{i+1:06d}' for i, name in enumerate(sorted({r['case_id'] for r in rows}))}
    rows = [dict(r, case_id=case_ids[r['case_id']]) for r in rows]
    report = summarize(rows, meta)
    write_new(destination / 'metrics.json', rows)
    write_new(destination / 'metadata.json', meta)
    write_new(destination / 'summary.json', report)
    write_figure(report, destination / 'accuracy.svg')
    package = destination / 'research_lab'
    package.mkdir()
    for source in sorted(Path(__file__).parent.glob('*.py')):
        shutil.copyfile(source, package / source.name)
    (destination / 'reproduce.py').write_text(REPRODUCE, encoding='utf-8')
    (destination / 'README.md').write_text(
        '# Research metric replay bundle\n\n'
        f'Evidence: **{meta["evidence_kind"]}**. Mode: **{meta["mode"]}**.\n\n'
        'Run `python reproduce.py` with Python 3.11+. No packages, key or network needed.\n\n'
        'This bundle replays numeric analysis from exported scores. It does not independently\n'
        're-score raw responses. Raw requests, responses, expected answers, private data, study\n'
        'protocols and credentials are excluded. The private source archive remains authoritative.\n'
        'Hashes establish internal consistency, not authenticity. Preserve the original bundle.\n\n'
        'Before publication: review all files, add the actual protocol, verified citations,\n'
        'limitations and appropriately consented/sanitized evidence. Choose licensing explicitly.\n'
        'Synthetic output is a software demonstration, never a scientific finding.\n'
        'No public repository is created automatically.\n', encoding='utf-8')
    (destination / 'paper.md').write_text(
        '# Investigation title (researcher to supply)\n\n'
        '## Abstract\n\nNo scientific claims supplied by the laboratory.\n\n'
        '## Research question and prior work\n\nInsert verified citations only.\n\n'
        '## Hypotheses and methods\n\nDescribe frozen protocol, sampling unit, conditions, '
        'model/version, exclusions and deviations.\n\n'
        '## Results\n\nReport null and negative outcomes, missing data and uncertainty. '
        'Identify synthetic fixtures explicitly.\n\n'
        '## Limitations and ethics\n\nDistinguish model measurements from human evidence.\n\n'
        '## Reproducibility\n\nDescribe the evidence included and excluded from this bundle.\n', encoding='utf-8')
    write_new(destination / 'SHA256.json', {p.relative_to(destination).as_posix(): file_hash(p)
              for p in sorted(destination.rglob('*')) if p.is_file()})
    return {'export_dir': str(destination), 'evidence_kind': meta['evidence_kind'],
            'scope': 'metric_only_replay', 'files': len(list(destination.rglob('*')))}
