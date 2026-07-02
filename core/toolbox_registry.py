from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ToolboxParameter:
    name: str
    label: str
    type: str = "string"
    flag: str = ""
    required: bool = False
    default: Any = None
    choices: tuple[str, ...] = ()
    direction: str = "option"
    advanced: bool = False
    visible_when: dict[str, object] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolboxParameter":
        visible_when = data.get("visible_when", {})
        if not isinstance(visible_when, dict):
            visible_when = {}
        return cls(
            name=str(data.get("name", "")),
            label=str(data.get("label") or data.get("name", "")),
            type=str(data.get("type", "string")),
            flag=str(data.get("flag", "")),
            required=bool(data.get("required", False)),
            default=data.get("default"),
            choices=tuple(str(item) for item in data.get("choices", [])),
            direction=str(data.get("direction", "option")),
            advanced=bool(data.get("advanced", False)),
            visible_when={str(key): value for key, value in visible_when.items()},
        )


@dataclass(frozen=True)
class ToolboxOutput:
    name: str
    label: str
    type: str = "report"
    source: str = ""
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolboxOutput":
        return cls(
            name=str(data.get("name", "")),
            label=str(data.get("label") or data.get("name", "")),
            type=str(data.get("type", "report")),
            source=str(data.get("source", "")),
            description=str(data.get("description", "")),
        )


@dataclass(frozen=True)
class ToolboxTool:
    id: str
    name: str
    category: str
    description: str
    command: list[str]
    runnable: bool = True
    parameters: tuple[ToolboxParameter, ...] = field(default_factory=tuple)
    outputs: tuple[ToolboxOutput, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ToolboxTool":
        return cls(
            id=str(data.get("id", "")),
            name=str(data.get("name", "")),
            category=str(data.get("category", "General")),
            description=str(data.get("description", "")),
            command=[str(item) for item in data.get("command", [])],
            runnable=bool(data.get("runnable", True)),
            parameters=tuple(ToolboxParameter.from_dict(item) for item in data.get("parameters", [])),
            outputs=tuple(ToolboxOutput.from_dict(item) for item in data.get("outputs", [])),
        )


@dataclass(frozen=True)
class Toolbox:
    id: str
    name: str
    version: str
    entrypoint: str
    root: Path
    description: str = ""
    tools: tuple[ToolboxTool, ...] = field(default_factory=tuple)

    @classmethod
    def from_manifest(cls, manifest_path: Path) -> "Toolbox":
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        required = ("id", "name", "version", "entrypoint")
        missing = [key for key in required if not data.get(key)]
        if missing:
            raise ValueError(f"{manifest_path} missing required fields: {', '.join(missing)}")
        return cls(
            id=str(data["id"]),
            name=str(data["name"]),
            version=str(data["version"]),
            entrypoint=str(data["entrypoint"]),
            root=manifest_path.parent,
            description=str(data.get("description", "")),
            tools=tuple(ToolboxTool.from_dict(item) for item in data.get("tools", [])),
        )


class ToolboxRegistry:
    """Scans SegFlow managed toolbox directories."""

    def __init__(self, root: str | Path | None = None):
        if root is None:
            root = Path(__file__).resolve().parents[1] / "toolboxes"
        self.root = Path(root)
        self._toolboxes: dict[str, Toolbox] = {}
        self._errors: list[str] = []

    @property
    def toolboxes(self) -> tuple[Toolbox, ...]:
        return tuple(self._toolboxes.values())

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(self._errors)

    def scan(self) -> tuple[Toolbox, ...]:
        self._toolboxes.clear()
        self._errors.clear()
        if not self.root.is_dir():
            return self.toolboxes

        for manifest_path in sorted(self.root.glob("*/toolbox.json")):
            try:
                toolbox = Toolbox.from_manifest(manifest_path)
            except Exception as exc:
                self._errors.append(str(exc))
                continue
            if toolbox.id in self._toolboxes:
                self._errors.append(f"Duplicate toolbox id: {toolbox.id}")
                continue
            self._toolboxes[toolbox.id] = toolbox
        return self.toolboxes

    def get(self, toolbox_id: str) -> Toolbox | None:
        return self._toolboxes.get(toolbox_id)
