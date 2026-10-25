"""Resolve a published data generation once per read; keep configuration in code."""
import json
import os
from pathlib import Path

ENGINE = 'basketball'


def data_root():
    configured = os.environ.get('FG_DATA_DIR')
    if not configured:
        return None
    root = Path(configured).resolve(strict=True)
    manifest = json.loads((root / 'manifest.json').read_text())
    if manifest.get('schema') != 1 or manifest.get('engine') != ENGINE:
        raise ValueError('Persistent data schema/engine mismatch')
    return root


def games(default):
    root = data_root()
    return root / 'games' if root else Path(default)


def snapshot(default, code, filename='ratings.json'):
    code = str(code)
    if not code or code in ('.', '..') or '/' in code or '\\' in code:
        raise ValueError('Invalid snapshot code')
    return games(default) / code / filename


def provenance():
    root = data_root()
    if root is None:
        return {'mode': 'repository'}
    m = json.loads((root / 'manifest.json').read_text())
    return {'mode': 'persistent', **{k: m[k] for k in ('generation', 'channel', 'kind', 'created_at', 'code_revision')}}
