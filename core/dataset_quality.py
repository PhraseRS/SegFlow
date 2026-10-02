"""Dataset quality snapshots and reversible split-list cleanup (no Qt)."""
from pathlib import Path
from datetime import datetime
import shutil
import os


def fingerprint(root):
    root = Path(root)
    entries = []
    for folder in ('JPEGImages', 'SegmentationClass', 'ImageSets/Segmentation'):
        for path in sorted((root / folder).rglob('*')):
            if path.is_file() and not path.name.endswith('.bak'):
                stat = path.stat()
                entries.append((str(path.relative_to(root)), stat.st_size, stat.st_mtime_ns))
    return tuple(entries)


def cleanup_plan(root, issues):
    bad = set(issues.get('fatal', {}).get('file_missing', []))
    bad.update(issues.get('fatal', {}).get('corrupt_file', []))
    plan = []
    for split in ('train', 'val', 'test'):
        path = Path(root) / 'ImageSets' / 'Segmentation' / (split + '.txt')
        raw = path.read_bytes()
        lines = raw.decode('utf-8-sig').splitlines(keepends=True)
        kept = [line for line in lines if line.strip() not in bad]
        removed = len(lines) - len(kept)
        if removed and not any(line.strip() for line in kept):
            raise ValueError('Cleanup would empty a split. Restore valid samples first.')
        if removed:
            bom = b'\xef\xbb\xbf' if raw.startswith(b'\xef\xbb\xbf') else b''
            plan.append((path, raw, bom + ''.join(kept).encode('utf-8'), removed))
    return plan


def apply_cleanup(plan):
    # Validate all inputs and back up all originals before changing any list.
    for path, original, _, _ in plan:
        if path.read_bytes() != original:
            raise ValueError('Dataset changed. Run the quality check again.')
    tag = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    backups = []
    for path, _, _, _ in plan:
        backup = path.with_name(path.name + '.' + tag + '.bak')
        shutil.copy2(path, backup)
        backups.append(backup)
    written = []
    try:
        for path, original, updated, _ in plan:
            temp = path.with_name(path.name + '.' + tag + '.tmp')
            temp.write_bytes(updated)
            os.replace(temp, path)
            written.append((path, original))
    except Exception:
        for path, original in written:
            path.write_bytes(original)
        raise
    return backups


def blocking_samples(root, issues):
    referenced = set()
    for split in ('train', 'val'):
        path = Path(root) / 'ImageSets' / 'Segmentation' / (split + '.txt')
        lines = path.read_text(encoding='utf-8-sig').splitlines()
        ids = {line.strip() for line in lines if line.strip()}
        if not ids:
            raise ValueError('A required split is empty.')
        referenced.update(ids)
    bad = set()
    for ids in issues.get('fatal', {}).values():
        bad.update(ids)
    return sorted(referenced & bad)
