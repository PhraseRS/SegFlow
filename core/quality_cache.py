"""Persistent certificate for the metadata database, not a second image scan."""
import json
import sqlite3
from pathlib import Path
from core.dataset_quality import fingerprint, apply_cleanup

# sqlite3's context manager commits but does not close Windows file handles.
from contextlib import contextmanager


@contextmanager
def connection(path):
    conn = sqlite3.connect(path)
    try:
        with conn:
            yield conn
    finally:
        conn.close()


def stamp(conn, snapshot):
    conn.execute('CREATE TABLE IF NOT EXISTS quality_snapshot (id INTEGER PRIMARY KEY, data TEXT)')
    conn.execute('INSERT OR REPLACE INTO quality_snapshot VALUES (1, ?)',
                 (json.dumps(snapshot),))


def certify(db_path, root):
    snapshot = fingerprint(root)
    with connection(db_path) as conn:
        stamp(conn, snapshot)
    return snapshot


def valid_cache(db_path, root, ids):
    with connection(db_path) as conn:
        conn.execute('CREATE TABLE IF NOT EXISTS quality_snapshot (id INTEGER PRIMARY KEY, data TEXT)')
        row = conn.execute('SELECT data FROM quality_snapshot WHERE id=1').fetchone()
        cached = {r[0] for r in conn.execute('SELECT sample_id FROM sample_stats')}
    return bool(row and cached == set(ids) and row[0] == json.dumps(fingerprint(root)))


def cleanup_cached(plan, db_path, root, expected):
    """Only removal of references is eligible for cache-preserving repair."""
    if fingerprint(root) != expected:
        raise ValueError('Dataset changed. Run the quality check again.')
    backups = apply_cleanup(plan)
    remaining = set()
    for split in ('train', 'val', 'test'):
        path = Path(root) / 'ImageSets' / 'Segmentation' / (split + '.txt')
        remaining.update(line.strip() for line in path.read_text(encoding='utf-8-sig').splitlines() if line.strip())
    after = fingerprint(root)
    before_files = [item for item in expected if not item[0].startswith('ImageSets')]
    after_files = [item for item in after if not item[0].startswith('ImageSets')]
    if before_files != after_files:
        raise ValueError('Dataset changed. Run the quality check again.')
    with connection(db_path) as conn:
        cached = {r[0] for r in conn.execute('SELECT sample_id FROM sample_stats')}
        if not remaining <= cached:
            raise ValueError('Dataset changed. Run the quality check again.')
        conn.executemany('DELETE FROM sample_stats WHERE sample_id=?',
                         [(sample,) for sample in cached - remaining])
        stamp(conn, after)
    return backups
