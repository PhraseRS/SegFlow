"""无 Qt 数据清单；质检直接复用 skill_sample_analysis。"""
import random
from collections import Counter
from pathlib import Path

from mcp_server.session import session

EXTENSIONS = {'.png', '.jpg', '.jpeg', '.tif', '.tiff', '.bmp'}


def _index(directory):
    result = {}
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix.lower() in EXTENSIONS:
            if path.stem in result:
                raise ValueError(f"同名样本有多个扩展名: {path.stem}")
            result[path.stem] = str(path)
    return result


def import_dataset(dataset_root: str, split_ratio: list[float] | None = None) -> dict:
    """导入 VOC 或 images/labels；优先读取现有 split，否则按固定种子划分。

    不修改源数据集。split_ratio 默认 [0.8, 0.1, 0.1]。
    """
    project = session.require_project()
    root = Path(dataset_root).expanduser().resolve()
    ratio = split_ratio if split_ratio is not None else [0.8, 0.1, 0.1]
    if len(ratio) != 3 or any(not 0 <= r <= 1 for r in ratio) or abs(sum(ratio) - 1) > 1e-6:
        raise ValueError("split_ratio 必须是总和为 1 的三个非负比例")
    image_dir, label_dir = root / 'JPEGImages', root / 'SegmentationClass'
    if not image_dir.is_dir():
        image_dir, label_dir = root / 'images', root / 'labels'
    if not image_dir.is_dir() or not label_dir.is_dir():
        raise ValueError("需要 JPEGImages/SegmentationClass 或 images/labels 目录")
    images, labels = _index(image_dir), _index(label_dir)
    if not images:
        raise ValueError("数据集没有可用影像")
    split_root = root / 'ImageSets' / 'Segmentation'
    if not split_root.is_dir():
        split_root = root
    splits = {}
    if any((split_root / f'{s}.txt').exists() for s in ('train', 'val', 'test')):
        for split in ('train', 'val', 'test'):
            file = split_root / f'{split}.txt'
            splits[split] = file.read_text(encoding='utf-8-sig').split() if file.exists() else []
        seen = set()
        for ids in splits.values():
            for sample_id in ids:
                if sample_id not in images or sample_id in seen:
                    raise ValueError(f"划分包含缺失或重复样本: {sample_id}")
                seen.add(sample_id)
    else:
        ids = sorted(images)
        random.Random(42).shuffle(ids)
        n_train, n_val = int(len(ids) * ratio[0]), int(len(ids) * ratio[1])
        splits = dict(train=ids[:n_train], val=ids[n_train:n_train+n_val], test=ids[n_train+n_val:])
    samples = [dict(sample_id=sid, split=split, image_path=images[sid],
                    label_path=labels.get(sid, '')) for split, ids in splits.items() for sid in ids]
    project.inputs.dataset_root = str(root)
    project.task_config['mcp_dataset'] = {'samples': samples, 'image_dir': str(image_dir),
                                          'label_dir': str(label_dir)}
    project.task_config.pop('mcp_stats', None)
    session.save()
    return {'total_samples': len(samples), 'splits': {k: len(v) for k, v in splits.items()},
            'missing_labels': sum(not s['label_path'] for s in samples),
            'unassigned_images': len(images) - len(samples)}


def list_samples(split: str = 'all', limit: int = 100, offset: int = 0) -> dict:
    """分页读取样本，limit 最大 1000。"""
    if split not in ('all', 'train', 'val', 'test') or not 1 <= limit <= 1000 or offset < 0:
        raise ValueError("无效的 split、limit 或 offset")
    data = session.require_project().task_config.get('mcp_dataset')
    if data is None:
        raise ValueError("请先 import_dataset")
    samples = [s for s in data['samples'] if split == 'all' or s['split'] == split]
    return {'total': len(samples), 'samples': samples[offset:offset+limit]}


def analyze_dataset() -> dict:
    """复用现有质检规则，汇总类别像素、覆盖率与问题计数。"""
    from skills.skill_sample_analysis import analyze_sample_fully
    project = session.require_project()
    data = project.task_config.get('mcp_dataset')
    if data is None:
        raise ValueError("请先 import_dataset")
    pixels, counts, issues, health = Counter(), Counter(), Counter(), Counter()
    total = 0
    for s in data['samples']:
        result = analyze_sample_fully((s['sample_id'], s['split'], s['image_path'], s['label_path']))
        health[result['status']] += 1
        issues.update(result['issues'])
        if result['status'] != 'error' and result['stats']:
            stats = result['stats']
            pixels.update(stats['class_pixels'])
            counts.update(stats['class_pixels'].keys())
            total += stats['total_pixels']
    summary = {'total_samples': len(data['samples']), 'pixel_distribution': dict(pixels),
               'pixel_ratios': {k: v / total for k, v in pixels.items()} if total else {},
               'image_counts': dict(counts), 'health': dict(health), 'issues': dict(issues),
               'total_pixels': total,
               'note': '采用现有 skill_sample_analysis 的类别 ID 与健康检查规则'}
    project.task_config['mcp_stats'] = summary
    session.save()
    return summary
