"""Read, write, and validate RS segmentation project files."""

from __future__ import annotations

import json
import os
from pathlib import Path

from core.project_state import CustomModuleState, ProjectState


class ProjectManager:
    """Manage dependency-free ``.rsgproj`` project files.

    The first implementation stores JSON content under the ``.rsgproj`` suffix.
    It records custom module locations but does not modify ``sys.path``.
    """

    FILE_SUFFIX = ".rsgproj"

    def load_project(self, path: str) -> ProjectState:
        project_path = Path(path).expanduser().resolve()
        with project_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        state = ProjectState.from_dict(data)
        state.project_path = str(project_path)
        if not state.project.name:
            state.project.name = project_path.stem
        return state

    def save_project(self, path: str, state: ProjectState) -> None:
        project_path = Path(path).expanduser().resolve()
        if project_path.suffix.lower() != self.FILE_SUFFIX:
            project_path = project_path.with_suffix(self.FILE_SUFFIX)
        project_path.parent.mkdir(parents=True, exist_ok=True)

        state.project_path = str(project_path)
        if not state.project.name:
            state.project.name = project_path.stem

        with project_path.open("w", encoding="utf-8") as f:
            json.dump(state.to_dict(), f, ensure_ascii=False, indent=2)

    def validate_state(self, state: ProjectState) -> list[str]:
        warnings: list[str] = []
        self._validate_dir(state.inputs.dataset_root, "数据集根目录", warnings)
        self._validate_file(state.model.config, "模型配置文件", warnings)
        self._validate_file(state.model.checkpoint, "模型权重文件", warnings)
        self._validate_file(state.custom_modules.custom_rs_dataset, "custom_rs_dataset.py", warnings, optional=True)
        self._validate_file(
            state.custom_modules.custom_live_pred_hook,
            "custom_live_pred_hook.py",
            warnings,
            optional=True,
        )

        valid_module_dirs = []
        for module_dir in state.custom_modules.module_dirs:
            if os.path.isdir(module_dir):
                valid_module_dirs.append(module_dir)
            else:
                warnings.append(f"自定义模块目录不存在: {module_dir}")
        state.custom_modules.module_dirs = valid_module_dirs
        return warnings

    def infer_custom_modules(self, config_path: str, work_dir: str = "") -> CustomModuleState:
        base_dir = work_dir or os.path.dirname(config_path)
        if not base_dir:
            return CustomModuleState()

        custom_rs_dataset = os.path.join(base_dir, "custom_rs_dataset.py")
        custom_live_pred_hook = os.path.join(base_dir, "custom_live_pred_hook.py")
        module_dirs = [base_dir] if os.path.isdir(base_dir) else []
        return CustomModuleState(
            custom_rs_dataset=custom_rs_dataset if os.path.isfile(custom_rs_dataset) else "",
            custom_live_pred_hook=custom_live_pred_hook if os.path.isfile(custom_live_pred_hook) else "",
            module_dirs=module_dirs,
        )

    @staticmethod
    def _validate_file(path: str, label: str, warnings: list[str], optional: bool = False) -> None:
        if not path:
            if not optional:
                warnings.append(f"{label}未设置")
            return
        if not os.path.isfile(path):
            warnings.append(f"{label}不存在: {path}")

    @staticmethod
    def _validate_dir(path: str, label: str, warnings: list[str]) -> None:
        if not path:
            warnings.append(f"{label}未设置")
            return
        if not os.path.isdir(path):
            warnings.append(f"{label}不存在: {path}")
