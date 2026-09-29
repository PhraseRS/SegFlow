"""子进程请求文件与项目自定义模块解析。"""
import json
import uuid
from pathlib import Path

from core.project_manager import ProjectManager
from mcp_server.adapters.async_training import interpreter, launch
from mcp_server.session import session


def custom_modules(config_path):
    inferred = ProjectManager().infer_custom_modules(config_path)
    state = session.project.custom_modules if session.project else inferred
    files = [state.custom_rs_dataset or inferred.custom_rs_dataset,
             state.custom_live_pred_hook or inferred.custom_live_pred_hook]
    return [f for f in files if f]


def submit(kind, payload, work_dir, python_env_path=''):
    python = interpreter(python_env_path)
    directory = Path(work_dir).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    request = directory / f'.mcp-{kind}-{uuid.uuid4().hex}.json'
    request.write_text(json.dumps(payload, ensure_ascii=False), encoding='utf-8')
    return launch(kind, str(directory), [python, '-u', '-m',
                  'mcp_server.adapters.worker', kind, str(request)],
                  [str(Path(f).parent) for f in payload.get('custom_module_files', [])])
