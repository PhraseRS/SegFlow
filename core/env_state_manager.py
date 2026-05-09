# -*- coding: utf-8 -*-
"""
EnvStateManager - 环境状态管理器

集中持有并广播"当前选中的 Python 环境"状态，
避免各组件直接互相引用，实现响应式解耦。

设计原则：
- 纯 QObject，无 UI 依赖
- 通过 Signal 广播状态变化，订阅者无需轮询
- 单例模式：整个应用共享同一个实例

用法：
    from core.env_state_manager import EnvStateManager
    mgr = EnvStateManager.instance()
    mgr.state_changed.connect(self._on_env_state_changed)
    mgr.update(python_path, framework_key, check_result)
"""

from __future__ import annotations
from typing import Optional

from PySide6.QtCore import QObject, Signal


class EnvStateManager(QObject):
    """
    环境状态管理器（应用级单例）。

    Signals:
        state_changed(dict): 状态变化时广播，携带完整状态快照：
            {
                "python_path":   str,
                "framework_key": str,
                "is_ready":      bool,
                "status":        "ready" | "incomplete" | "error" | "unknown",
                "details":       dict,   # 包版本等详情
                "message":       str,    # 人类可读的状态描述
            }
    """

    state_changed = Signal(dict)

    _instance: Optional["EnvStateManager"] = None

    def __init__(self, parent=None):
        super().__init__(parent)
        self._python_path: str = ""
        self._framework_key: str = ""
        self._is_ready: bool = False
        self._status: str = "unknown"
        self._details: dict = {}
        self._message: str = ""

    # ------------------------------------------------------------------
    # 单例访问
    # ------------------------------------------------------------------

    @classmethod
    def instance(cls) -> "EnvStateManager":
        """获取全局单例。"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls):
        """测试用：重置单例（生产代码不应调用）。"""
        cls._instance = None

    # ------------------------------------------------------------------
    # 状态更新
    # ------------------------------------------------------------------

    def update(
        self,
        python_path: str,
        framework_key: str,
        check_result: dict,
    ) -> None:
        """
        更新环境状态并广播 state_changed 信号。

        Args:
            python_path:   Python 解释器路径
            framework_key: 框架注册表 key，如 "mmseg"
            check_result:  EnvCheckWorker 返回的探针结果 dict
        """
        self._python_path = python_path or ""
        self._framework_key = framework_key or ""
        self._status = check_result.get("status", "unknown")
        self._details = check_result.get("details", {})
        self._message = check_result.get("msg", "")
        self._is_ready = (self._status == "ready")

        self.state_changed.emit(self.snapshot())

    def clear(self) -> None:
        """清空状态（如用户切换环境时）。"""
        self._python_path = ""
        self._framework_key = ""
        self._is_ready = False
        self._status = "unknown"
        self._details = {}
        self._message = ""
        self.state_changed.emit(self.snapshot())

    # ------------------------------------------------------------------
    # 只读属性
    # ------------------------------------------------------------------

    @property
    def is_ready(self) -> bool:
        return self._is_ready

    @property
    def python_path(self) -> str:
        return self._python_path

    @property
    def framework_key(self) -> str:
        return self._framework_key

    @property
    def status(self) -> str:
        return self._status

    def snapshot(self) -> dict:
        """返回当前状态的完整快照（用于 Signal 广播）。"""
        return {
            "python_path":   self._python_path,
            "framework_key": self._framework_key,
            "is_ready":      self._is_ready,
            "status":        self._status,
            "details":       dict(self._details),
            "message":       self._message,
        }
