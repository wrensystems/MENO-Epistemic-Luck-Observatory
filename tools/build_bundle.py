"""Build a clean ZIP and SHA-256 inventory without network or third-party modules."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMIT = '566b4e7a93c882dcd1532991872ffc26cc345fd6'
OMIT = {'__pycache__', '.git', '.venv', 'runs', 'exports'}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory():
    files = []
    for path in sorted(ROOT.rglob('*')):
        relative = path.relative_to(ROOT)
        if any(part in OMIT for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError('Symlinks are not permitted in the release')
        if not path.is_file():
            continue
        if path.suffix in {'.pyc', '.pyo', '.key', '.pem', '.zip'} or path.name.startswith('.env'):
            raise ValueError('Unsafe/unexpected artifact: ' + str(relative))
        files.append(path)
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--source', type=Path,
                        help='Optional original snapshot root to record selected-file provenance')
    args = parser.parse_args()
    if ROOT == args.out.resolve() or ROOT in args.out.resolve().parents:
        parser.error('ZIP output must be outside the release folder')
    if args.source:
        entries = []
        for path in inventory():
            relative = path.relative_to(ROOT)
            original = args.source/relative
            if relative.parts[0] == 'examples' and relative.name != 'offline-demo.json':
                original = args.source/'docs'/'meno2'/'examples'/relative.name
            elif str(relative) == 'docs/technical/PROTOCOL.md':
                original = args.source/'docs'/'meno2'/'ASTRA_SUITE_PROTOCOL.md'
            if original.is_file():
                entries.append({'release_path': relative.as_posix(),
                                'source_path': original.relative_to(args.source).as_posix(),
                                'source_sha256': sha(original), 'release_sha256': sha(path),
                                'byte_identical': sha(original) == sha(path)})
        (ROOT/'SOURCE_PROVENANCE.json').write_text(json.dumps({
            'source_commit': COMMIT,
            'scope': 'Selected public files only; original private repository and history excluded',
            'original_raw_archives_included': False, 'files': entries}, indent=2)+'\n',
            encoding='utf-8')
    manifest = {p.relative_to(ROOT).as_posix(): sha(p) for p in inventory()
                if p.name != 'SHA256.json'}
    (ROOT/'SHA256.json').write_text(json.dumps(manifest, indent=2)+'\n', encoding='utf-8')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.out, 'w', zipfile.ZIP_DEFLATED) as bundle:
        for path in inventory():
            bundle.write(path, 'MENO/'+path.relative_to(ROOT).as_posix())
    with zipfile.ZipFile(args.out) as bundle:
        if bundle.testzip() is not None:
            raise ValueError('ZIP integrity check failed')
    print(json.dumps({'zip': str(args.out.resolve()), 'files': len(inventory()),
                      'sha256': sha(args.out), 'bytes': args.out.stat().st_size}, indent=2))


if __name__ == '__main__':
    main()

