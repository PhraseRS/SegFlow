"""模型注册表、参数建议和 Core 配置生成适配。"""
import math
import uuid
from dataclasses import asdict, fields
from pathlib import Path

from config.backbone_registry import BACKBONE_REGISTRY
from core.config_advisor import ConfigAdvisor, DatasetInsights
from core.framework_registry import get_framework_spec
from core.project_manager import ProjectManager
from mcp_server.adapters.requests import submit
from mcp_server.session import existing_file, session


def list_available_models(framework: str = 'mmseg') -> dict:
    """列出仓库模型/骨干注册项，不代表训练环境已安装。"""
    spec = get_framework_spec(framework)
    if spec is None:
        raise ValueError(f'不支持的框架: {framework}')
    return {'framework': spec.display_name, 'models': [asdict(e) for e in BACKBONE_REGISTRY]}


def get_config_advice(dataset_stats: dict | None = None, hardware_info: dict | None = None) -> dict:
    """调用规则式 ConfigAdvisor；hardware_info 仅回显，不虚构硬件建议。

    dataset_stats 可来自 analyze_dataset() 的输出或手动传入；
    DatasetInsights 的必填字段若在 stats 中缺失将使用空默认值。
    """
    stats = dataset_stats if dataset_stats is not None else session.require_project().task_config.get('mcp_stats', {})
    allowed = {f.name for f in fields(DatasetInsights)}
    # DatasetInsights 有部分必填字段（class_names、pixel_distribution 等）无默认值；
    # analyze_dataset() 不提供 class_names/suggested_class_weights，故此处补齐安全默认值，
    # 避免在 stats 中缺失时引发 TypeError。
    required_defaults = {
        'class_names': [],
        'pixel_distribution': {},
        'pixel_ratios': {},
        'image_counts': {},
        'suggested_class_weights': {},
    }
    merged = {**required_defaults, **{k: v for k, v in stats.items() if k in allowed}}
    advisor = ConfigAdvisor(DatasetInsights(**merged))
    return {'loss_config': advisor.recommend_loss_config(),
            'augmentation': advisor.recommend_augmentation(), 'rs_params': advisor.recommend_rs_params(),
            'summary': advisor.get_summary(), 'hardware_info': hardware_info or {},
            'note': '现有 Core 顾问为数据规则推荐，尚无硬件自动调参模型'}


def preview_config(config_path: str) -> dict:
    """只读配置文本，不执行配置。"""
    path = Path(existing_file(config_path))
    if path.stat().st_size > 1024 * 1024:
        raise ValueError('配置文件超过 1 MiB')
    return {'config_path': str(path), 'content': path.read_text(encoding='utf-8')}


def set_pretrain_weights(weights_path: str) -> dict:
    """设置下次生成配置使用的预训练权重；不修改已有配置。空字符串清除。"""
    project = session.require_project()
    project.task_config['mcp_pretrained'] = existing_file(weights_path) if weights_path else ''
    session.save()
    return {'weights_path': project.task_config['mcp_pretrained'], 'applies_to': 'next_generate_config'}


async def generate_config(model: str, backbone: str, epochs: int = 100, batch_size: int = 2,
                          lr: float = 0.0001, base_config: str = '', pretrain_weights: str = '',
                          class_names: list[str] | None = None, num_workers: int = 0,
                          python_env_path: str = '') -> dict:
    """在指定 Python 环境复用 MMSegTrainer 生成配置（需 mmengine）。

    需要已导入数据集；模型名称与 backbone_key 见 list_available_models。
    可用 base_config 显式指定可信的基础 Python 配置。
    """
    project = session.require_project()
    if epochs < 1 or batch_size < 1 or not math.isfinite(lr) or lr <= 0 or num_workers < 0:
        raise ValueError('epochs、batch_size、lr 必须为正，num_workers 不得为负')
    aliases = {'r50': 'resnet50', 'r101': 'resnet101'}
    backbone = aliases.get(backbone.lower(), backbone)
    entry = next((e for e in BACKBONE_REGISTRY if e.method.lower() == model.lower()
                  and backbone.lower() in (e.backbone_key.lower(), e.backbone_display.lower())), None)
    if entry is None:
        raise ValueError('不支持的模型/骨干组合，请查询 list_available_models')
    data = project.task_config.get('mcp_dataset')
    if not data:
        raise ValueError('请先 import_dataset')
    splits = {s: [r['sample_id'] for r in data['samples'] if r['split'] == s]
              for s in ('train', 'val', 'test')}
    if not splits['train'] or not splits['val']:
        raise ValueError('训练集和验证集不能为空')
    if any(not row['label_path'] for row in data['samples']):
        raise ValueError('数据集包含缺失标签')
    names = class_names or []
    if not names or len(set(names)) != len(names) or any(not n.strip() for n in names):
        raise ValueError('请提供有序且唯一的 class_names（索引即标签 ID）')
    img_suffixes = {Path(s['image_path']).suffix for s in data['samples']}
    label_suffixes = {Path(s['label_path']).suffix for s in data['samples']}
    if len(img_suffixes) != 1 or len(label_suffixes) != 1:
        raise ValueError('Core 数据加载器要求图像和标签各自使用统一扩展名')
    directory = Path(project.model.work_dir) / 'mcp_configs' / uuid.uuid4().hex
    directory.mkdir(parents=True)
    split_files = {}
    for split, ids in splits.items():
        file = directory / f'{split}.txt'
        file.write_text('\n'.join(ids) + '\n', encoding='utf-8')
        split_files[split] = str(file)
    weights = pretrain_weights or project.task_config.get('mcp_pretrained', '')
    params = dict(base_config=existing_file(base_config) if base_config else '',
                  max_iters=epochs * math.ceil(len(splits['train']) / batch_size),
                  batch_size=batch_size, lr=lr, num_workers=num_workers,
                  data_root=project.inputs.dataset_root, num_classes=len(names), class_names=names,
                  img_suffix=next(iter(img_suffixes)), seg_map_suffix=next(iter(label_suffixes)),
                  pretrained=existing_file(weights) if weights else None)
    payload = dict(params=params, advisor={'crop_size': [entry.default_crop_size] * 2},
                   save_path=str(directory / 'config.py'), dataset=data, split_files=split_files,
                   model=entry.method, backbone=entry.backbone_key)
    task = submit('config', payload, str(directory), python_env_path)
    await task.runner
    if task.status != 'completed':
        raise RuntimeError(f"{task.error}\n" + '\n'.join(line for _, line in task.logs)[-6000:])
    project.model.config = task.result['config_path']
    project.custom_modules = ProjectManager().infer_custom_modules(project.model.config)
    session.save()
    return task.result
