"""训练控制与非破坏性游标日志读取。"""
import json
from pathlib import Path

from mcp_server.adapters.async_training import stop
from mcp_server.adapters.requests import custom_modules, submit
from mcp_server.session import existing_file, session


async def start_training(config_path: str, work_dir: str, python_env_path: str = '') -> dict:
    """在 B 层启动真实 MMSeg Runner，立即返回任务 ID。仅执行可信配置。"""
    config = existing_file(config_path)
    directory = str(Path(work_dir).expanduser().resolve())
    task = submit('training', dict(config_path=config, work_dir=directory,
                  custom_module_files=custom_modules(config)), directory, python_env_path)
    return task.snapshot()


def get_training_status(task_id: str) -> dict:
    """返回 iter/max_iter/loss/mIoU/eta（日志提供时）与任务状态。"""
    return session.task(task_id, 'training').snapshot()


def stream_training_logs(task_id: str, cursor: int = 0, limit: int = 200) -> dict:
    """增量读取任意任务日志；以 next_cursor 轮询，不会消费其他读者日志。"""
    if cursor < 0 or not 1 <= limit <= 1000:
        raise ValueError('cursor 或 limit 无效')
    task = session.task(task_id)
    rows = [(seq, line) for seq, line in task.logs if seq > cursor][:limit]
    return {'lines': [line for _, line in rows], 'next_cursor': rows[-1][0] if rows else cursor,
            'truncated': bool(task.logs and cursor < task.logs[0][0] - 1), 'status': task.status}


async def stop_training(task_id: str) -> dict:
    """终止训练进程树；已结束任务可重复调用。"""
    return await stop(session.task(task_id, 'training'))


def list_checkpoints(work_dir: str) -> dict:
    """扫描权重；指标仅在 last_checkpoint/元数据明确关联时返回，不推测分数。"""
    directory = Path(work_dir).expanduser().resolve()
    if not directory.is_dir():
        raise ValueError('工作目录不存在')
    rows = [{'checkpoint_path': str(p), 'size_bytes': p.stat().st_size,
             'modified_at': p.stat().st_mtime, 'metrics': None}
            for p in sorted(directory.rglob('*.pth'))]
    # 本次服务器会话内已评估的指标可以可靠关联到权重。
    for row in rows:
        for task in session.tasks.values():
            if task.kind == 'evaluation' and task.status == 'completed' and task.progress.get('checkpoint_path') == row['checkpoint_path']:
                row['metrics'] = task.result.get('metrics')
    return {'checkpoints': rows}
