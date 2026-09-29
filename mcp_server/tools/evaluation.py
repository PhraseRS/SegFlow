"""复用现有评估入口，逐个比较权重以控制 GPU 占用。"""
import json
import uuid
from pathlib import Path

from mcp_server.adapters.async_training import interpreter, launch
from mcp_server.adapters.requests import custom_modules
from mcp_server.session import existing_file, session


async def evaluate_checkpoint(config_path: str, checkpoint_path: str,
                              python_env_path: str = '', work_dir: str = '') -> dict:
    """等待评估完成并返回 Core 原始 metrics；不伪造缺失的 per-class IoU。"""
    config, checkpoint = existing_file(config_path), existing_file(checkpoint_path)
    directory = Path(work_dir).expanduser().resolve() if work_dir else Path(checkpoint).parent / 'mcp_evaluations' / uuid.uuid4().hex
    directory.mkdir(parents=True, exist_ok=True)
    modules = custom_modules(config)
    command = [interpreter(python_env_path), '-u', '-m', 'core.mmseg_test_runner_entry',
               '--test-config', config, '--checkpoint', checkpoint, '--work-dir', str(directory),
               '--custom-module-files-json', json.dumps(modules)]
    task = launch('evaluation', str(directory), command, [str(Path(f).parent) for f in modules])
    task.progress['checkpoint_path'] = checkpoint
    await task.runner
    if task.status != 'completed':
        raise RuntimeError(f'{task.error}; task_id={task.task_id}')
    return {'task_id': task.task_id, 'checkpoint_path': checkpoint, **task.result}


async def compare_checkpoints(checkpoint_list: list[str], config_path: str,
                              python_env_path: str = '') -> dict:
    """依次评估 1–20 个权重，返回原始指标表。"""
    if not 1 <= len(checkpoint_list) <= 20:
        raise ValueError('checkpoint_list 长度应为 1–20')
    for path in checkpoint_list:
        existing_file(path)
    return {'results': [await evaluate_checkpoint(config_path, path, python_env_path)
                        for path in checkpoint_list]}
