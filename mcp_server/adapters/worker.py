"""仅在选定 Python 环境执行的 Core 适配入口。"""
import argparse
import json
from pathlib import Path


def generate(payload):
    from core.framework_adapters.mmseg_trainer import MMSegTrainer
    from mmengine.config import Config
    params = payload['params']
    if not params.get('base_config'):
        import importlib.util
        from config.backbone_registry import BACKBONE_REGISTRY
        entry = next(e for e in BACKBONE_REGISTRY
                     if e.method == payload['model'] and e.backbone_key == payload['backbone'])
        spec = importlib.util.find_spec('mmseg')
        if spec is None:
            raise ValueError('训练环境没有安装 mmseg，请提供 base_config')
        package = Path(spec.origin).parent
        candidates = []
        for root in (package / '.mim' / 'configs', package.parent / 'configs'):
            candidates.extend(sorted((root / entry.config_subdir).glob(entry.config_pattern)))
        if not candidates:
            raise ValueError('找不到模型基础配置，请显式传入 base_config')
        params['base_config'] = str(candidates[0])
    path = MMSegTrainer().generate_config(params, payload['advisor'], payload['save_path'])
    cfg = Config.fromfile(path)
    # Core 默认 VOC 路径；只做输入路径适配，不重写配置生成逻辑。
    data = payload['dataset']
    def patch(node, split):
        if isinstance(node, dict):
            if 'data_prefix' in node and 'type' in node:
                node['data_prefix'] = dict(img_path=data['image_dir'], seg_map_path=data['label_dir'])
                node['ann_file'] = payload['split_files'][split]
            for value in node.values():
                patch(value, split)
        elif isinstance(node, list):
            for value in node:
                patch(value, split)
    for split in ('train', 'val', 'test'):
        patch(cfg.get(f'{split}_dataloader', {}), split)
    cfg.dump(path)
    return {'config_path': path, 'max_iters': params['max_iters']}


def train(payload):
    from core.project_module_resolver import load_custom_modules_from_files
    from mmengine.config import Config
    from mmengine.runner import Runner
    from mmseg.utils import register_all_modules
    register_all_modules(init_default_scope=True)
    loaded = load_custom_modules_from_files(payload.get('custom_module_files', []))
    if any(not item.get('loaded') for item in loaded):
        raise ImportError(str(loaded))
    cfg = Config.fromfile(payload['config_path'])
    cfg.work_dir = payload['work_dir']
    cfg.launcher = 'none'
    Runner.from_cfg(cfg).train()
    return {'work_dir': cfg.work_dir}


def infer(payload):
    # GDAL 必须先于 torch 初始化；沿用 Core 的加载顺序。
    try:
        from osgeo import gdal  # noqa: F401
    except ImportError:
        pass
    from core.inference_engine import InferenceEngine
    engine = InferenceEngine(payload['inference_model'])
    try:
        if not engine.use_real_model:
            raise RuntimeError('模型加载失败：MCP 不允许使用模拟推理结果，请检查 B 层依赖和权重')
        def progress(current, total):
            print('__RS_INFER_PROGRESS__' + json.dumps({'value': 100 * current / max(total, 1)}), flush=True)
        engine.set_progress_callback(progress)
        result = engine.large_image_block_inference(
            payload['image_path'], payload['output_path'],
            crop_size=payload['block_size'], overlap_rate=payload['overlap'],
            enable_tta=payload['enable_tta'])
        if not result.get('success'):
            raise RuntimeError(result.get('error', '推理失败或已取消'))
        if not Path(payload['output_path']).is_file():
            raise RuntimeError('推理未生成输出文件')
        return {'output_mask_path': payload['output_path']}
    finally:
        engine.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('operation', choices=['config', 'training', 'inference'])
    parser.add_argument('request')
    args = parser.parse_args()
    payload = json.loads(Path(args.request).read_text(encoding='utf-8'))
    result = {'config': generate, 'training': train, 'inference': infer}[args.operation](payload)
    print('__SEGFLOW_RESULT__' + json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
