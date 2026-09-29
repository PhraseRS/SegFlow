"""会话与有界任务状态；不导入 Qt 或深度学习框架。"""
import asyncio
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path

from core.project_manager import ProjectManager
from core.project_state import ProjectState

ROOT = Path(__file__).resolve().parents[1]


def existing_file(value: str) -> str:
    path = Path(value).expanduser().resolve()
    if not value or not path.is_file():
        raise ValueError(f"文件不存在: {value}")
    return str(path)


@dataclass
class Task:
    kind: str
    work_dir: str
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: str = "queued"
    started: float = field(default_factory=time.monotonic)
    ended: float | None = None
    progress: dict = field(default_factory=dict)
    result: dict = field(default_factory=dict)
    error: str = ""
    logs: deque = field(default_factory=lambda: deque(maxlen=2000))
    sequence: int = 0
    process: object = None
    runner: object = None
    cancel_requested: bool = False
    events: asyncio.Queue = field(default_factory=lambda: asyncio.Queue(maxsize=100))

    def log(self, line):
        self.sequence += 1
        self.logs.append((self.sequence, line))

    def snapshot(self):
        return {"task_id": self.task_id, "kind": self.kind, "status": self.status,
                "work_dir": self.work_dir, "elapsed": (self.ended or time.monotonic()) - self.started,
                **self.progress, "result": self.result, "error": self.error}


class SessionState:
    def __init__(self):
        self.project = None
        self.tasks = {}
        self.lock = asyncio.Lock()

    def require_project(self) -> ProjectState:
        if self.project is None:
            raise ValueError("请先 create_project 或 open_project")
        return self.project

    def save(self):
        project = self.require_project()
        ProjectManager().save_project(project.project_path, project)

    def task(self, task_id, kind=None):
        task = self.tasks.get(task_id)
        if task is None or (kind and task.kind != kind):
            raise ValueError(f"任务不存在或类型不匹配: {task_id}")
        return task

    def add_task(self, kind, work_dir):
        if sum(t.status in ('queued', 'running') for t in self.tasks.values()) >= 8:
            raise ValueError("最多允许 8 个并发任务")
        if any(t.work_dir == work_dir and t.status in ('queued', 'running')
               for t in self.tasks.values()):
            raise ValueError("该工作目录已有运行中的任务")
        if len(self.tasks) >= 100:
            key = next((k for k, t in self.tasks.items()
                        if t.status not in ('queued', 'running')), None)
            if key:
                del self.tasks[key]
        task = Task(kind, work_dir)
        self.tasks[task.task_id] = task
        return task


session = SessionState()
