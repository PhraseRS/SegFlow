# -*- coding: utf-8 -*-
"""
EnvConfigWidget - 环境配置与检测组件

所有阻塞的 subprocess 调用均通过 EnvCheckWorker(QThread) 异步执行，
结果通过 Signal/Slot 回到主线程更新 UI，不会卡住界面。
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from utils.mmseg_env_manager import MMSegEnvManager
from utils.env_check_worker import EnvCheckWorker
from ui.widgets.wheel_guard import install_wheel_guard


# 默认 mmseg 所需包列表，可由外部通过 set_framework() 覆盖
_MMSEG_PACKAGES = ["torch", "mmcv", "mmseg"]


class EnvConfigWidget(QWidget):
    """
    环境配置与检测组件。

    Signals:
        env_ready(str):      环境验证通过，携带 python_path
        env_not_ready(str):  环境验证失败，携带Error消息
    """

    env_ready = Signal(str)       # python_path
    env_not_ready = Signal(str)   # error message

    def __init__(self, parent=None):
        super().__init__(parent)
        self.env_manager = MMSegEnvManager()
        self._envs: list = []
        self._current_framework: str = ""
        self._required_packages: list = list(_MMSEG_PACKAGES)
        self._version_constraints: dict = {}
        self._last_validated_path: str = ""
        self._last_validation_result = None
        self._check_worker = None   # type: Optional[EnvCheckWorker]
        self._refresh_worker = None  # type: Optional[EnvCheckWorker]
        self._debounce_timer = None  # type: Optional[QTimer]
        self._init_ui()
        # 延迟刷新，避免构造时阻塞
        self._schedule_refresh()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        select_label = QLabel(self.tr("Conda environments"))
        select_label.setStyleSheet("font-weight: bold; color: #495057;")
        layout.addWidget(select_label)

        select_row = QHBoxLayout()
        select_row.setSpacing(8)

        self.env_select = QComboBox()
        self.env_select.setMinimumWidth(220)
        self.env_select.currentIndexChanged.connect(self._on_env_changed)
        select_row.addWidget(self.env_select, stretch=1)

        self.refresh_button = QPushButton(self.tr("Refresh"))
        self.refresh_button.clicked.connect(self.refresh_envs)
        select_row.addWidget(self.refresh_button)

        layout.addLayout(select_row)

        # Python executable 行：标签 + Re-check 按钮
        path_row = QHBoxLayout()
        path_row.setSpacing(8)
        path_label = QLabel(self.tr("Python executable"))
        path_label.setStyleSheet("font-weight: bold; color: #495057;")
        path_row.addWidget(path_label)
        path_row.addStretch()

        self.validate_button = QPushButton(self.tr("Re-check"))
        self.validate_button.setToolTip(self.tr("手动重新验证当前环境（安装新包后使用）"))
        self.validate_button.clicked.connect(self.validate_env)
        path_row.addWidget(self.validate_button)
        layout.addLayout(path_row)

        self.custom_path = QLineEdit()
        self.custom_path.setPlaceholderText(self.tr("e.g. D:\\anaconda3\\envs\\mmseg\\python.exe"))
        self.custom_path.textEdited.connect(self._on_custom_path_edited)
        layout.addWidget(self.custom_path)

        self.framework_hint_label = QLabel(self.tr(""))
        self.framework_hint_label.setWordWrap(True)
        self.framework_hint_label.setStyleSheet(
            "background-color: #EEF4FF; border: 1px solid #CFE0FF; "
            "border-radius: 6px; padding: 8px; color: #315E9E;"
        )
        self.framework_hint_label.setVisible(False)
        layout.addWidget(self.framework_hint_label)

        self.status_label = QLabel(self.tr("Please select Python environment"))
        self.status_label.setWordWrap(True)
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.status_label.setStyleSheet(
            "background-color: #F8F9FA; border: 1px solid #DEE2E6; "
            "border-radius: 6px; padding: 8px; color: #495057;"
        )
        layout.addWidget(self.status_label)

        # 防抖定时器（切换环境/编辑路径后延迟自动验证）
        self._debounce_timer = QTimer(self)
        self._debounce_timer.setSingleShot(True)
        self._debounce_timer.timeout.connect(self._auto_validate)

        # UI-09：阻止鼠标悬停时滚轮误改 env_select ComboBox 的选项
        install_wheel_guard(self)

    def _schedule_refresh(self):
        """延迟一个事件循环周期后再刷新，避免构造时阻塞父组件初始化。"""
        QTimer.singleShot(0, self.refresh_envs)

    # ------------------------------------------------------------------
    # 防抖自动验证
    # ------------------------------------------------------------------

    def _schedule_auto_validate(self, delay_ms: int = 800):
        """启动防抖定时器，延迟后自动触发验证。"""
        self._debounce_timer.stop()
        self._debounce_timer.setInterval(delay_ms)
        self._debounce_timer.start()

    def _auto_validate(self):
        """防抖定时器到期，自动触发验证。"""
        python_path = self.get_selected_python_path()
        if not python_path:
            return
        # 如果路径没变且已有缓存结果，跳过
        if (self._last_validated_path == python_path
                and self._last_validation_result is not None):
            return
        self.validate_env()

    # ------------------------------------------------------------------
    # 环境列表刷新（异步）
    # ------------------------------------------------------------------

    def refresh_envs(self):
        """异步刷新 conda 环境列表，不阻塞主线程。"""
        self.refresh_button.setEnabled(False)
        self._set_status_loading("Scanning conda environments, please wait...")

        from PySide6.QtCore import QThread

        class _RefreshWorker(QThread):
            """仅用于 conda env list 的轻量 Worker。"""
            from PySide6.QtCore import Signal as _Signal
            finished = _Signal(list)   # list of env dicts

            def __init__(self, manager, parent=None):
                super().__init__(parent)
                self._manager = manager

            def run(self):
                envs = self._manager.list_all_envs()
                self.finished.emit(envs)

        worker = _RefreshWorker(self.env_manager, self)
        worker.finished.connect(self._on_refresh_done)
        worker.finished.connect(worker.deleteLater)
        self._refresh_worker = worker
        worker.start()

    def _on_refresh_done(self, envs: list):
        """conda 环境列表扫描完成，回到主线程更新 UI。"""
        self._envs = envs
        self.refresh_button.setEnabled(True)

        self.env_select.blockSignals(True)
        self.env_select.clear()

        for env in self._envs:
            self.env_select.addItem(env["display_name"], env["path"])

        if not self._envs:
            self.env_select.addItem("No conda environments detected", "")
            self.env_select.setEnabled(False)
        else:
            self.env_select.setEnabled(True)

        self.env_select.blockSignals(False)
        self._invalidate_validation_cache()
        self._fill_selected_env_path()

    def _fill_selected_env_path(self):
        """将当前下拉选中的环境路径填入输入框（强制覆盖）。"""
        path = self._selected_env_path()
        if path:
            self.custom_path.setText(path)
            self._invalidate_validation_cache()
            # 切换环境后自动触发验证（防抖 800ms）
            self._schedule_auto_validate(800)
        elif not self.custom_path.text().strip():
            self.custom_path.clear()

    def _selected_env_path(self) -> str:
        return (self.env_select.currentData() or "").strip()

    def _on_env_changed(self, _index: int):
        """下拉切换环境时，自动同步路径到输入框并触发验证。"""
        self._fill_selected_env_path()

    def _on_custom_path_edited(self, _text: str):
        """用户手动编辑路径时，防抖 1200ms 后自动验证。"""
        self._invalidate_validation_cache()
        self._schedule_auto_validate(1200)

    def set_framework(self, framework_name: str, required_packages=None):
        """
        设置当前框架，更新Tip文字和探针包列表。

        Args:
            framework_name:     框架显示名称，如 "MMSegmentation"
            required_packages:  该框架需要探测的包列表；
                                为 None 时从 FrameworkRegistry 自动查找，
                                找不到则保持当前列表不变。
        """
        self._current_framework = (framework_name or "").strip()

        # 更新探针包列表
        if required_packages is not None:
            self._required_packages = list(required_packages)
        else:
            from core.framework_registry import get_required_packages
            pkgs = get_required_packages(self._current_framework)
            if pkgs:
                self._required_packages = pkgs

        # 更新版本约束
        from core.framework_registry import get_version_constraints
        self._version_constraints = get_version_constraints(self._current_framework)

        # 切换框架后缓存失效
        self._invalidate_validation_cache()

        requires_env = self.requires_environment_check()
        if requires_env:
            pkg_str = ", ".join(self._required_packages)
            self.framework_hint_label.setText(
                f"{self._current_framework} 在训练时使用所选 Python 环境。\n"
                f"所需包：{pkg_str}\n"
                "建议在配置模型时提前验证解释器就绪状态。"
            )
            self.framework_hint_label.setVisible(True)
        else:
            self.framework_hint_label.setVisible(False)

    def requires_environment_check(self) -> bool:
        """
        判断当前框架是否需要独立的 conda 环境检测。
        只要有已注册的所需包列表，就认为需要检测。
        """
        return bool(self._required_packages)

    def _invalidate_validation_cache(self):
        self._last_validated_path = ""
        self._last_validation_result = None

    def get_selected_python_path(self) -> str:
        return self.custom_path.text().strip() or self._selected_env_path()

    def validate_env(self):
        """异步触发环境验证，不阻塞主线程。"""
        python_path = self.get_selected_python_path()
        if not python_path:
            self._set_status(
                False,
                "No Python interpreter selected. Choose a detected environment or enter a path manually.",
            )
            return

        # 如果已有 worker 在跑，先Cancel
        if self._check_worker is not None:
            try:
                if self._check_worker.isRunning():
                    self._check_worker.quit()
                    self._check_worker.wait(500)
            except RuntimeError:
                pass  # C++ 对象已销毁，忽略
            self._check_worker = None

        self._invalidate_validation_cache()
        self.validate_button.setEnabled(False)
        self._set_status_loading(f"🔍 Detecting: {python_path}")

        self._check_worker = EnvCheckWorker(
            python_path=python_path,
            required_packages=self._required_packages,
            version_constraints=self._version_constraints,
            parent=self,
        )
        self._check_worker.check_finished.connect(self._on_check_finished)
        self._check_worker.check_failed.connect(self._on_check_failed)
        self._check_worker.finished.connect(self._on_check_worker_done)
        self._check_worker.start()

    def _on_check_worker_done(self):
        """Worker 线程结束后清理引用，防止访问已删除对象。"""
        if self._check_worker is not None:
            self._check_worker.deleteLater()
            self._check_worker = None

    def _on_check_finished(self, result: dict):
        """EnvCheckWorker 完成后回到主线程处理结果。"""
        self.validate_button.setEnabled(True)
        python_path = self.get_selected_python_path()
        is_valid, message = self._parse_check_result(result)
        self._last_validated_path = python_path
        self._last_validation_result = (is_valid, message)
        self._set_status(is_valid, message)

        # 更新全局环境状态管理器
        from core.env_state_manager import EnvStateManager
        from core.framework_registry import get_key_by_display_name
        framework_key = get_key_by_display_name(self._current_framework) or self._current_framework
        EnvStateManager.instance().update(python_path, framework_key, result)

        if is_valid:
            self.env_ready.emit(python_path)
        else:
            self.env_not_ready.emit(message)

    def _on_check_failed(self, error: str):
        """EnvCheckWorker 发生意外异常时的处理。"""
        self.validate_button.setEnabled(True)
        self._set_status(False, f"Detection exception: {error}")
        # 同步更新状态管理器为 error 状态
        from core.env_state_manager import EnvStateManager
        EnvStateManager.instance().update(
            self.get_selected_python_path(),
            self._current_framework,
            {"status": "error", "msg": error},
        )
        self.env_not_ready.emit(error)

    def _parse_check_result(self, result: dict):
        """将 EnvCheckWorker 返回的 dict 转换为 (is_valid, message) 元组。"""
        details = result.get("details", {})
        status = result.get("status", "error")

        if status == "ready":
            parts = [f"Python {details.get('python', '?')}"]
            for pkg in self._required_packages:
                ver = details.get(pkg)
                if ver:
                    parts.append(f"{pkg.upper()} {ver}")
            if "cuda" in details:
                parts.append("CUDA " + ("Available" if details["cuda"] else "Not Available"))
            return True, "✅ Ready: " + " | ".join(parts)

        if status == "version_mismatch":
            msg = result.get("msg", "")
            # 构建安装Tip
            install_parts = []
            for pkg, constraint in self._version_constraints.items():
                install_parts.append(f"{pkg}{constraint}")
            install_cmd = "pip install " + " ".join(install_parts)
            return False, (
                f"❌ Version incompatible: {msg}\n"
                f"此 GUI 需要 MMSeg 1.x 配置格式，与 0.x 不兼容。\n"
                f"请运行: {install_cmd}"
            )

        if status == "incomplete":
            parts = [f"Python {details.get('python', '?')}"]
            for pkg in self._required_packages:
                ver = details.get(pkg)
                if ver:
                    parts.append(f"{pkg.upper()} {ver}")
            msg = result.get("msg", "Missing packages").lstrip("; ")
            return False, f"⚠️ Incomplete: {' | '.join(parts)} — {msg}"

        return False, f"❌ Error: {result.get('msg', 'Unknown error')}"

    def validate_selected_environment(self, force_refresh: bool = False):
        """
        同步接口（向后兼容）：仅读取缓存结果。
        如需强制刷新，请调用 validate_env()（异步）。
        """
        python_path = self.get_selected_python_path()
        if not python_path:
            return (
                False,
                "No Python interpreter selected. Choose a detected environment or enter a path manually.",
            )

        if (
            not force_refresh
            and self._last_validation_result is not None
            and python_path == self._last_validated_path
        ):
            return self._last_validation_result

        # force_refresh=True 时回退到同步探针（仅用于训练前最终检查）
        is_valid, message = self.env_manager.validate_environment(
            python_path, version_constraints=self._version_constraints
        )
        self._last_validated_path = python_path
        self._last_validation_result = (is_valid, message)
        return is_valid, message

    def ensure_ready_for_training(self):
        """
        训练前检查环境就绪状态。

        优先使用缓存结果；无缓存时自动执行一次同步验证
        （用户已点"运行"，此时阻塞 1-2 秒可接受）。
        """
        if not self.requires_environment_check():
            return True, ""

        python_path = self.get_selected_python_path()
        if not python_path:
            msg = "No Python environment selected. Please select or input path in environment panel."
            self._set_status(False, msg)
            return False, msg

        # 优先使用缓存结果
        if (self._last_validation_result is not None
                and self._last_validated_path == python_path):
            is_valid, message = self._last_validation_result
            self._set_status(is_valid, message)
            return is_valid, message

        # 无缓存：自动执行同步验证（兜底，正常流程中自动验证已覆盖）
        is_valid, message = self.env_manager.validate_environment(
            python_path, version_constraints=self._version_constraints
        )
        self._last_validated_path = python_path
        self._last_validation_result = (is_valid, message)
        self._set_status(is_valid, message)
        return is_valid, message

    def _set_status_loading(self, message: str):
        """显示加载中状态。"""
        self.status_label.setStyleSheet(
            "background-color: #E3F2FD; border: 1px solid #90CAF9; "
            "border-radius: 6px; padding: 8px; color: #1565C0;"
        )
        self.status_label.setText(message)

    def _set_status(self, is_valid: bool, message: str):
        if is_valid:
            style = (
                "background-color: #E8F5E9; border: 1px solid #A5D6A7; "
                "border-radius: 6px; padding: 8px; color: #2E7D32;"
            )
        else:
            style = (
                "background-color: #FFEBEE; border: 1px solid #EF9A9A; "
                "border-radius: 6px; padding: 8px; color: #C62828;"
            )
        self.status_label.setStyleSheet(style)
        self.status_label.setText(message)
