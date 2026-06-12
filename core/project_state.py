"""Project file state models for the desktop application."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


PROJECT_FILE_VERSION = "1.0"


def _as_str(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


@dataclass
class ProjectInfo:
    name: str = ""
    version: str = PROJECT_FILE_VERSION

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectInfo":
        return cls(
            name=_as_str(data.get("name")),
            version=_as_str(data.get("version")) or PROJECT_FILE_VERSION,
        )


@dataclass
class InputState:
    dataset_root: str = ""
    sample_library: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "InputState":
        return cls(
            dataset_root=_as_str(data.get("dataset_root")),
            sample_library=_as_str(data.get("sample_library")),
        )


@dataclass
class ModelState:
    config: str = ""
    checkpoint: str = ""
    work_dir: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ModelState":
        return cls(
            config=_as_str(data.get("config")),
            checkpoint=_as_str(data.get("checkpoint")),
            work_dir=_as_str(data.get("work_dir")),
        )


@dataclass
class CustomModuleState:
    custom_rs_dataset: str = ""
    custom_live_pred_hook: str = ""
    module_dirs: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "CustomModuleState":
        return cls(
            custom_rs_dataset=_as_str(data.get("custom_rs_dataset")),
            custom_live_pred_hook=_as_str(data.get("custom_live_pred_hook")),
            module_dirs=_as_str_list(data.get("module_dirs")),
        )


@dataclass
class ProjectState:
    project_path: str = ""
    project: ProjectInfo = field(default_factory=ProjectInfo)
    inputs: InputState = field(default_factory=InputState)
    model: ModelState = field(default_factory=ModelState)
    custom_modules: CustomModuleState = field(default_factory=CustomModuleState)
    inference: dict[str, Any] = field(default_factory=dict)
    task_config: dict[str, Any] = field(default_factory=dict)
    test: dict[str, Any] = field(default_factory=dict)
    ui: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ProjectState":
        return cls(
            project_path=_as_str(data.get("project_path")),
            project=ProjectInfo.from_dict(_as_dict(data.get("project"))),
            inputs=InputState.from_dict(_as_dict(data.get("inputs"))),
            model=ModelState.from_dict(_as_dict(data.get("model"))),
            custom_modules=CustomModuleState.from_dict(_as_dict(data.get("custom_modules"))),
            inference=_as_dict(data.get("inference")),
            task_config=_as_dict(data.get("task_config")),
            test=_as_dict(data.get("test")),
            ui=_as_dict(data.get("ui")),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
