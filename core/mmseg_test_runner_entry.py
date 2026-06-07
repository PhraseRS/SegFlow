# -*- coding: utf-8 -*-
"""
Subprocess entry for project-local MMSeg Runner.test().
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from contextlib import contextmanager
from typing import Any, Iterable


RESULT_PREFIX = "__MMSEG_TEST_RESULT__"


@contextmanager
def temporary_sys_path(paths: str | Iterable[str] | None):
    if paths is None:
        normalized_paths = []
    elif isinstance(paths, str):
        normalized_paths = [paths]
    else:
        normalized_paths = list(paths)

    added_paths = []
    for path in normalized_paths:
        if not path:
            continue
        abs_path = os.path.abspath(path)
        if os.path.isdir(abs_path) and abs_path not in sys.path:
            sys.path.insert(0, abs_path)
            added_paths.append(abs_path)

    try:
        yield
    finally:
        for path in reversed(added_paths):
            try:
                sys.path.remove(path)
            except ValueError:
                pass


def main() -> int:
    args = _parse_args()
    cfg_options = json.loads(args.cfg_options_json) if args.cfg_options_json else None

    with temporary_sys_path(args.import_path):
        result = _run_test(
            test_config=args.test_config,
            checkpoint=args.checkpoint,
            work_dir=args.work_dir,
            show_dir=args.show_dir,
            out_dir=args.out_dir,
            cfg_options=cfg_options,
            tta=args.tta,
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
    parser.add_argument("--import-path", action="append", default=[])
    return parser.parse_args()


def _run_test(
    test_config: str,
    checkpoint: str,
    work_dir: str,
    show_dir: str = "",
    out_dir: str = "",
    cfg_options: dict | None = None,
    tta: bool = False,
) -> dict:
    from mmengine.config import Config
    from mmengine.runner import Runner

    cfg = Config.fromfile(test_config)
    cfg.launcher = "none"
    if cfg_options:
        cfg.merge_from_dict(cfg_options)

    cfg.work_dir = work_dir
    cfg.load_from = checkpoint

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
