# -*- coding: utf-8 -*-
"""
Subprocess entry for project-local MMSeg Runner.test().
"""

from __future__ import annotations

import argparse
import json
import os
from typing import Any

from core.project_module_resolver import load_custom_modules_from_files, validate_custom_module_files


RESULT_PREFIX = "__MMSEG_TEST_RESULT__"


def main() -> int:
    args = _parse_args()
    cfg_options = json.loads(args.cfg_options_json) if args.cfg_options_json else None
    custom_module_files = json.loads(args.custom_module_files_json) if args.custom_module_files_json else []

    result = _run_test(
        test_config=args.test_config,
        checkpoint=args.checkpoint,
        work_dir=args.work_dir,
        show_dir=args.show_dir,
        out_dir=args.out_dir,
        cfg_options=cfg_options,
        tta=args.tta,
        custom_module_files=custom_module_files,
    )

    print(RESULT_PREFIX + json.dumps(result, ensure_ascii=False))
    return 0


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run MMSeg Runner.test() for rs-seg-gui")
    parser.add_argument("--test-config", required=True)
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--work-dir", required=True)
    parser.add_argument("--show-dir", default="")
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--cfg-options-json", default="")
    parser.add_argument("--tta", action="store_true")
    parser.add_argument("--custom-module-files-json", default="")
    return parser.parse_args()


def _run_test(
    test_config: str,
    checkpoint: str,
    work_dir: str,
    show_dir: str = "",
    out_dir: str = "",
    cfg_options: dict | None = None,
    tta: bool = False,
    custom_module_files: list[str] | None = None,
) -> dict:
    from mmengine.config import Config
    from mmengine.runner import Runner

    warnings = validate_custom_module_files(custom_module_files)
    if warnings:
        raise FileNotFoundError("; ".join(warnings))
    load_results = load_custom_modules_from_files(custom_module_files)
    failed = [item for item in load_results if not item.get("loaded")]
    if failed:
        message = "; ".join(f"{item.get('module')}: {item.get('error')}" for item in failed)
        raise ImportError(f"Failed to load custom modules: {message}")

    cfg = Config.fromfile(test_config)
    cfg.launcher = "none"
    if cfg_options:
        cfg.merge_from_dict(cfg_options)

    cfg.work_dir = work_dir
    cfg.load_from = checkpoint
    _force_single_process_test_dataloader(cfg)
    _disable_visualization(cfg)

    if show_dir:
        _enable_visualization(cfg, show_dir)
    if out_dir and hasattr(cfg, "test_evaluator"):
        cfg.test_evaluator["output_dir"] = out_dir
        cfg.test_evaluator["keep_results"] = True
    if tta:
        cfg.test_dataloader.dataset.pipeline = cfg.tta_pipeline
        cfg.tta_model.module = cfg.model
        cfg.model = cfg.tta_model

    runner = Runner.from_cfg(cfg)
    metrics = runner.test() or {}

    return {
        "metrics": _to_jsonable(metrics),
        "work_dir": work_dir,
        "show_dir": show_dir,
        "out_dir": out_dir,
    }


def _force_single_process_test_dataloader(cfg: Any) -> None:
    dataloader = getattr(cfg, "test_dataloader", None)
    if isinstance(dataloader, dict):
        dataloader["num_workers"] = 0
        dataloader["persistent_workers"] = False


def _enable_visualization(cfg: Any, show_dir: str) -> None:
    default_hooks = getattr(cfg, "default_hooks", None)
    if default_hooks is not None and "visualization" in default_hooks:
        default_hooks["visualization"]["draw"] = True
        visualizer = getattr(cfg, "visualizer", None)
        if visualizer is not None:
            visualizer["save_dir"] = show_dir
    else:
        print("VisualizationHook not found; show_dir output may be unavailable.")
    os.makedirs(show_dir, exist_ok=True)


def _disable_visualization(cfg: Any) -> None:
    default_hooks = getattr(cfg, "default_hooks", None)
    if default_hooks is not None and "visualization" in default_hooks:
        default_hooks["visualization"]["draw"] = False
        default_hooks["visualization"]["show"] = False
    visualizer = getattr(cfg, "visualizer", None)
    if visualizer is not None:
        visualizer.pop("save_dir", None)


def _to_jsonable(value: Any) -> Any:
    try:
        import numpy as np

        if isinstance(value, np.generic):
            return value.item()
        if isinstance(value, np.ndarray):
            return value.tolist()
    except Exception:
        pass

    if isinstance(value, dict):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


if __name__ == "__main__":
    raise SystemExit(main())
