#!/usr/bin/env python3
"""Versioned data-only snapshot format, shared with the three engine repositories.

No credentials, source code or raw collection caches enter a published bundle.
"""
import argparse
import datetime as dt
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import uuid

ENGINES = ('football', 'basketball', 'esports')
META = ('refresh-state.json', 'refresh-status.json', 'source-coverage.json')
MAX_FILE = 16 * 1024 * 1024
MAX_TOTAL = 64 * 1024 * 1024


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def load(path):
    def invalid(value):
        raise ValueError('Non-finite JSON number: ' + value)
    return json.loads(Path(path).read_text(encoding='utf-8'), parse_constant=invalid)


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.tmp-' + uuid.uuid4().hex)
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n', encoding='utf-8')
    tmp.replace(path)


def allowed(name):
    p = PurePosixPath(name)
    return (not p.is_absolute() and '..' not in p.parts and '\\' not in name
            and (name in META or len(p.parts) == 3 and p.parts[0] == 'games'
                 and p.parts[2] in ('ratings.json', 'corners_ratings.json')))


def safe_file(root, name):
    if not allowed(name):
        raise ValueError('Unexpected bundle path: ' + name)
    root = Path(root).resolve()
    path = root / name
    if any(p.is_symlink() for p in [path, *path.parents] if p != root and root in p.parents):
        raise ValueError('Bundle symlinks are forbidden: ' + name)
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError('Missing or oversized bundle file: ' + name)
    return path


def snapshot_stats(value):
    teams = value.get('teams')
    if not isinstance(teams, dict) or not teams:
        raise ValueError('Snapshot must contain nonempty teams')
    for team, stats in teams.items():
        if not isinstance(stats, dict):
            raise ValueError('Invalid team: ' + team)
        for k, v in stats.items():
            if isinstance(v, (int, float)) and (not math.isfinite(v) or k in ('gp', 'w', 'd', 'l') and v < 0):
                raise ValueError('Invalid numeric team statistic')
    dates = [str(v['last_date']) for v in teams.values() if v.get('last_date')]
    latest = value.get('last_match_date') or value.get('last_date') or max(dates, default=None)
    if latest:
        day = dt.date.fromisoformat(latest)
        if day > dt.datetime.now(dt.timezone.utc).date():
            raise ValueError('Future match date')
    matches = value.get('source_matches', value.get('updated_from'))
    if matches is not None and (not isinstance(matches, int) or matches < 0):
        raise ValueError('Invalid match count')
    semantic = {k: v for k, v in value.items() if k not in ('updated', 'built_at', 'generated_at')}
    return {'teams': len(teams), 'matches': matches, 'latest_match': latest,
            'semantic_sha256': hashlib.sha256(json.dumps(semantic, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()}


def revision(source):
    return subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True,
                                   stderr=subprocess.DEVNULL).strip()


def collection_check(source, engine, recent=True):
    source = Path(source)
    if engine == 'esports':
        state = load(source / 'refresh-status.json')
        expected = {p.parent.name for p in source.glob('games/*/ratings.json')}
        games = state.get('games') or {}
        if not expected or not expected <= set(games) or any(games[g] not in ('ok', 'stale') for g in expected):
            raise ValueError('Incomplete/failed esports collection')
        for game in expected:
            stamp = state.get('game_checked_at', {}).get(game) or state.get('checked_at')
            checked = dt.datetime.fromisoformat(stamp)
            if checked.tzinfo is None:
                raise ValueError('Collection timestamp must include timezone')
            age = (dt.datetime.now(dt.timezone.utc) - checked).total_seconds()
            if age < -600 or recent and age > 48*3600:
                raise ValueError('Stale/invalid collection timestamp')
    else:
        state = load(source / 'refresh-state.json')
        if engine == 'football':
            dates = [state['checked_through']]
        else:
            required = set()
            for path in source.glob('games/*/config.json'):
                if load(path).get('source') in ('espn', 'euroleague', 'cba'):
                    required.add(path.parent.name)
            if not state or not required <= set(state):
                raise ValueError('Missing per-league collection checkpoint')
            dates = [v['checked_through'] for v in state.values()]
        if any(dt.date.fromisoformat(day) >= dt.datetime.now(dt.timezone.utc).date() for day in dates):
            raise ValueError('Collection checkpoint is not a completed UTC day')


def create(source, destination, engine, channel, code_revision=None, kind='refresh'):
    source, destination = Path(source), Path(destination)
    if engine not in ENGINES or channel not in ('vps', 'github'):
        raise ValueError('Unknown engine/channel')
    if destination.exists():
        raise ValueError('Bundle destination must not exist')
    if kind == 'refresh':
        collection_check(source, engine)
    names = sorted(str(p.relative_to(source).as_posix()) for pattern in ('games/*/ratings.json', 'games/*/corners_ratings.json') for p in source.glob(pattern))
    names += [name for name in META if (source / name).is_file()]
    if not any(n.endswith('/ratings.json') for n in names):
        raise ValueError('No rating snapshots')
    destination.mkdir(parents=True)
    entries = {}
    for name in names:
        path = safe_file(source, name)
        value = load(path)
        entry = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size}
        if name.endswith('/ratings.json'):
            entry.update(snapshot_stats(value))
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
        entries[name] = entry
    manifest = {'schema': 1, 'engine': engine, 'channel': channel, 'kind': kind,
                'generation': dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ-') + uuid.uuid4().hex[:12],
                'created_at': now(), 'code_revision': code_revision or revision(source), 'files': entries}
    write(destination / 'manifest.json', manifest)
    verify(destination, engine)
    return manifest


def verify(directory, engine=None):
    directory = Path(directory)
    manifest_path = directory / 'manifest.json'
    if manifest_path.is_symlink() or manifest_path.stat().st_size > MAX_FILE:
        raise ValueError('Invalid manifest')
    manifest = load(manifest_path)
    if manifest.get('schema') != 1 or manifest.get('engine') not in ENGINES or engine and manifest['engine'] != engine:
        raise ValueError('Bundle schema/engine mismatch')
    if manifest.get('channel') not in ('vps', 'github') or manifest.get('kind') not in ('seed', 'refresh'):
        raise ValueError('Invalid bundle provenance')
    created = dt.datetime.fromisoformat(manifest['created_at'])
    if created.tzinfo is None or created > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10):
        raise ValueError('Invalid bundle timestamp')
    if not manifest.get('generation') or not manifest.get('code_revision'):
        raise ValueError('Missing version')
    entries = manifest.get('files')
    if not isinstance(entries, dict) or not entries or len(entries) > 1024:
        raise ValueError('Missing or excessive file list')
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*')
              if (p.is_file() or p.is_symlink()) and p.relative_to(directory).parts[0] != '.git'}
    if actual != set(entries) | {'manifest.json'}:
        raise ValueError('Undeclared or missing bundle files')
    total = 0
    ratings = 0
    for name, expected in entries.items():
        path = safe_file(directory, name)
        raw = path.read_bytes()
        total += len(raw)
        if total > MAX_TOTAL or len(raw) != expected['bytes'] or hashlib.sha256(raw).hexdigest() != expected['sha256']:
            raise ValueError('Bundle checksum/size mismatch: ' + name)
        value = load(path)
        if name.endswith('/ratings.json'):
            ratings += 1
            stats = snapshot_stats(value)
            if any(expected.get(k) != v for k, v in stats.items()):
                raise ValueError('Incorrect snapshot summary: ' + name)
    if not ratings:
        raise ValueError('No rating snapshots')
    return manifest


def restore(bundle, source, engine):
    manifest = verify(bundle, engine)
    source = Path(source).resolve()
    for name in manifest['files']:
        target = source / name
        if any(p.is_symlink() for p in (target, *target.parents) if source in p.parents):
            raise ValueError('Refuse to restore through symlink')
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(Path(bundle) / name, target)
    return manifest


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('create', 'verify', 'restore'))
    parser.add_argument('--engine', choices=ENGINES, required=True)
    parser.add_argument('--source', type=Path, default=Path('.'))
    parser.add_argument('--bundle', type=Path, required=True)
    args = parser.parse_args()
    if args.command == 'create':
        result = create(args.source, args.bundle, args.engine, 'github')
    elif args.command == 'restore':
        result = restore(args.bundle, args.source, args.engine)
    else:
        result = verify(args.bundle, args.engine)
    print(json.dumps({k: v for k, v in result.items() if k != 'files'}, ensure_ascii=False))
