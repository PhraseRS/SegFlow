"""项目工具。"""
from pathlib import Path

from core.project_manager import ProjectManager
from core.project_state import ProjectState
from mcp_server.session import existing_file, session


def create_project(project_name: str, work_dir: str) -> dict:
    """创建项目，不覆盖已有文件。work_dir 应为绝对路径。"""
    if not project_name.strip() or any(c in project_name for c in '/\\:<>"|?*') or project_name in ('.', '..'):
        raise ValueError("项目名称必须是有效的文件名")
    directory = Path(work_dir).expanduser().resolve()
    path = directory / (project_name + '.rsgproj')
    if path.exists():
        raise ValueError(f"项目已存在: {path}")
    state = ProjectState()
    state.project.name = project_name
    state.model.work_dir = str(directory)
    ProjectManager().save_project(str(path), state)
    session.project = state
    return {"project_path": str(path)}


def open_project(project_path: str) -> dict:
    """加载 .rsgproj，包括 MCP 持久化的数据集清单。"""
    state = ProjectManager().load_project(existing_file(project_path))
    session.project = state
    return state.to_dict()


def get_project_status() -> dict:
    """返回当前项目与任务快照。任务状态仅在服务器进程内保留。"""
    return {"project": session.project.to_dict() if session.project else None,
            "tasks": [task.snapshot() for task in session.tasks.values()]}
