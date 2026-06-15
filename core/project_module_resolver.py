"""Load generated MMSeg custom modules from project-file paths."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any


CUSTOM_MODULE_KEYS = ("custom_rs_dataset", "custom_live_pred_hook")


def resolve_custom_module_files(state_or_dict: Any) -> list[str]:
    """Return existing custom module file paths from a ProjectState or dict."""
    custom_modules = _extract_custom_modules(state_or_dict)
    paths: list[str] = []
    for key in CUSTOM_MODULE_KEYS:
        path = _read_value(custom_modules, key)
        if path and os.path.isfile(path):
            abs_path = os.path.abspath(path)
            if abs_path not in paths:
                paths.append(abs_path)
    return paths


def validate_custom_module_files(paths: list[str] | tuple[str, ...] | None) -> list[str]:
    """Return human-readable warnings for invalid custom module file paths."""
    warnings: list[str] = []
    for raw_path in paths or []:
        if not raw_path:
            continue
        path = os.path.abspath(str(raw_path))
        if not os.path.isfile(path):
            warnings.append(f"Custom module file not found: {path}")
            continue
        if Path(path).suffix.lower() != ".py":
            warnings.append(f"Custom module is not a Python file: {path}")
    return warnings


def load_custom_modules_from_files(paths: list[str] | tuple[str, ...] | None) -> list[dict]:
    """Import custom modules from file paths and register them in sys.modules."""
    results: list[dict] = []
    for raw_path in paths or []:
        if not raw_path:
            continue
        path = os.path.abspath(str(raw_path))
        module_name = Path(path).stem
        if not os.path.isfile(path):
            results.append({
                "path": path,
                "module": module_name,
                "loaded": False,
                "error": f"Custom module file not found: {path}",
            })
            continue
        existing_module = sys.modules.get(module_name)
        if existing_module is not None:
            results.append({
                "path": path,
                "module": module_name,
                "loaded": True,
                "error": "",
            })
            continue
        try:
            spec = importlib.util.spec_from_file_location(module_name, path)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot create import spec for {path}")
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = module
            spec.loader.exec_module(module)
            results.append({
                "path": path,
                "module": module_name,
                "loaded": True,
                "error": "",
            })
        except Exception as exc:
            sys.modules.pop(module_name, None)
            results.append({
                "path": path,
                "module": module_name,
                "loaded": False,
                "error": str(exc),
            })
    return results


def _extract_custom_modules(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("custom_modules", value)
    return getattr(value, "custom_modules", value)


def _read_value(value: Any, key: str) -> str:
    if isinstance(value, dict):
        item = value.get(key, "")
    else:
        item = getattr(value, key, "")
    return item if isinstance(item, str) else ""
