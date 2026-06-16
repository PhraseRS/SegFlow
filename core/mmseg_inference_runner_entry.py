# -*- coding: utf-8 -*-
"""Subprocess entry for MMSeg inference with the selected training Python."""

from __future__ import annotations
# =================================================================
# [终极防暴毙补丁]：必须在 PyTorch 加载 CUDA DLL 之前，优先把 GDAL 锁死在内存里！
# =================================================================
try:
    from osgeo import gdal
except ImportError:
    pass
# =================================================================

import sys
import torch   # <-- 必须确保 GDAL 在 torch 之前被 import！
import argparse
import json
import os
import traceback
from typing import Any

import numpy as np

from core.inference_engine import InferenceEngine

INFERENCE_PROGRESS_PREFIX = "__RS_INFER_PROGRESS__"


def _emit_progress(current: int, total: int) -> None:
    total = max(int(total or 1), 1)
    value = int(10 + (int(current) / total) * 80)
    value = max(0, min(100, value))
    print(
        INFERENCE_PROGRESS_PREFIX + json.dumps(
            {"current": int(current), "total": total, "value": value},
            ensure_ascii=False,
        ),
        flush=True,
    )


def _save_arrays(value: Any, artifact_dir: str, prefix: str = "result") -> Any:
    if isinstance(value, np.ndarray):
        os.makedirs(artifact_dir, exist_ok=True)
        path = os.path.join(artifact_dir, f"{prefix}.npy")
        np.save(path, value)
        return {"__ndarray__": path}
    if isinstance(value, dict):
        return {key: _save_arrays(item, artifact_dir, f"{prefix}_{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_save_arrays(item, artifact_dir, f"{prefix}_{index}") for index, item in enumerate(value)]
    return value


def _run_request(payload: dict) -> dict:
    inference_model = payload["inference_model"]
    image_path = payload["image_path"]
    strategy = payload["strategy"]
    params = payload.get("inference_params", {})
    output_path = payload.get("output_path")
    artifact_dir = payload["artifact_dir"]

    engine = None
    try:
        engine = InferenceEngine(inference_model)
        engine.set_progress_callback(_emit_progress)
        if strategy == "large_image_block":
            if not output_path:
                raise ValueError("large_image_block inference requires output_path")
            result = engine.large_image_block_inference(
                image_path,
                output_path,
                crop_size=params["crop_size"],
                overlap_rate=params["overlap_rate"],
                enable_tta=params["enable_tta"],
            )
        elif strategy == "sliding_window":
            result = engine.sliding_window_inference(
                image_path,
                crop_size=params["crop_size"],
                stride=params["stride"],
                batch_size=params["batch_size"],
                enable_tta=params["enable_tta"],
            )
        elif strategy == "resize":
            result = engine.resize_inference(
                image_path,
                enable_tta=params["enable_tta"],
            )
        else:
            raise ValueError(f"Unknown inference strategy: {strategy}")
        return {"ok": True, "result": _save_arrays(result, artifact_dir)}
    except Exception as exc:
        return {"ok": False, "error": f"{exc}\n\n{traceback.format_exc()}"}
    finally:
        if engine and hasattr(engine, "close"):
            engine.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", required=True)
    parser.add_argument("--result-json", required=True)
    args = parser.parse_args()

    with open(args.request_json, "r", encoding="utf-8") as f:
        payload = json.load(f)

    result = _run_request(payload)

    with open(args.result_json, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False)

    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
