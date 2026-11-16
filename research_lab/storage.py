"""Small durable storage primitives. Hashes detect changes, not authenticity."""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re


def utc():
    return datetime.now(timezone.utc).isoformat()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False,
                      separators=(',', ':')).encode('utf-8')


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_json(path):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'),
                          parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s)))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Invalid JSON: {Path(path).name}') from exc


def write_new(path, value):
    """Exclusive create: an existing evidence file can never be overwritten."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = canonical(value) + b'\n'
    with path.open('xb') as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())


def read_journal(path):
    try:
        data = Path(path).read_text(encoding='utf-8')
        if not data.endswith('\n'):
            raise ValueError('Incomplete journal write; preserve archive for recovery')
        entries = [json.loads(line) for line in data.splitlines()]
        if not entries or any(not isinstance(e, dict) for e in entries):
            raise ValueError('Invalid journal')
        for index, entry in enumerate(entries[1:], 1):
            if entry.get('sequence') != index or entry.get('previous') != digest(entries[index - 1]):
                raise ValueError('Journal chain mismatch')
        return entries
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError('Missing or malformed journal; preserve archive for recovery') from exc


def append_journal(path, event):
    entries = read_journal(path)
    event = dict(event, sequence=len(entries), previous=digest(entries[-1]))
    with Path(path).open('ab') as stream:
        stream.write(canonical(event) + b'\n')
        stream.flush()
        os.fsync(stream.fileno())


def slug(value):
    reserved = {'con', 'prn', 'aux', 'nul'} | {f'{p}{i}' for p in ('com', 'lpt') for i in range(1, 10)}
    if not isinstance(value, str) or not re.fullmatch(r'[a-z][a-z0-9-]{0,79}', value) or value in reserved:
        raise ValueError('Use a portable lowercase slug (letters, digits, hyphens)')
    return value


def inside(root, relative):
    root = Path(root).resolve()
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ValueError('Expected a relative portable path')
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or path == root:
        raise ValueError('Path escapes its study/run')
    return path


@contextmanager
def lock(path):
    path = Path(path)
    try:
        write_new(path, {'pid': os.getpid(), 'started': utc()})
    except FileExistsError as exc:
        raise ValueError('Run is locked; inspect the owner before removing a stale .lock') from exc
    try:
        yield
    finally:
        path.unlink()
