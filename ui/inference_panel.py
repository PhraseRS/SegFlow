# -*- coding: utf-8 -*-
"""
Inference Visualization Panel (Inference Visualization Panel)
负责管理推理配置、Model Load、推理执行和结果Export
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QSpinBox, QDoubleSpinBox,
    QRadioButton, QCheckBox, QButtonGroup, QFrame, QScrollArea,
    QProgressBar, QFileDialog, QMessageBox, QApplication,
    QTableWidget, QTableWidgetItem, QHeaderView
)
from PySide6.QtCore import Qt, Signal, QTimer, QThread
import copy
import json
import os
import queue
import subprocess
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable
import numpy as np

from ui.widgets.visualization_settings_widget import VisualizationSettingsWidget
from ui.widgets.inference_visualization_widget import InferenceVisualizationWidget
from ui.widgets.wheel_guard import install_wheel_guard
from core.custom_module_import import normalize_import_paths
from core.env_state_manager import is_current_python, resolve_training_python
from core.mask_renderer import MaskRenderer
from core.project_module_resolver import load_custom_modules_from_files, validate_custom_module_files
from skills.skill_raster_io import sample_band_stats


RESULT_PREFIX = "__MMSEG_TEST_RESULT__"
INFERENCE_PROGRESS_PREFIX = "__RS_INFER_PROGRESS__"


@dataclass
class MMSegTestConfig:
    test_config: str
    checkpoint: str
    split: str
    work_dir: str
    show_dir: str
    out_dir: str
    custom_module_files: list[str]
    sample_count: int
    labelled_count: int
    samples: list[dict]
    format_only: bool


class MMSegTestConfigBuilder:
    """Create a temporary test config from the selected train_config.py."""

    def build(
        self,
        config_path: str,
        checkpoint_path: str,
        data_root: str,
        splits: dict[str, list[dict]],
        output_root: str | None = None,
        custom_module_files: list[str] | None = None,
    ) -> MMSegTestConfig:
        from mmengine.config import Config

        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"Config file not found: {config_path}")
        if not os.path.isfile(checkpoint_path):
            raise FileNotFoundError(f"Checkpoint file not found: {checkpoint_path}")
        if not data_root or not os.path.isdir(data_root):
            raise FileNotFoundError(f"Dataset root not found: {data_root}")

        resolved_custom_module_files = self._resolve_custom_module_files(config_path, custom_module_files)
        warnings = validate_custom_module_files(resolved_custom_module_files)
        if warnings:
            raise FileNotFoundError("; ".join(warnings))

        temp_config_path = None
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                content = f.read()

            modified = False
            if "custom_imports" in content:
                if "allow_failed_imports=False" in content:
                    content = content.replace("allow_failed_imports=False", "allow_failed_imports=True")
                    modified = True
                elif "allow_failed_imports" not in content:
                    lines = content.split("\n")
                    new_lines = []
                    for line in lines:
                        if "custom_imports" in line and "dict(" in line:
                            if line.strip().endswith(")"):
                                line = line.rstrip().rstrip(")") + ", allow_failed_imports=True)"
                                modified = True
                            elif line.strip().endswith(","):
                                line = line.rstrip().rstrip(",") + ", allow_failed_imports=True)"
                                modified = True
                        new_lines.append(line)
                    content = "\n".join(new_lines)

            if modified:
                temp_config_path = config_path + ".tmp.py"
                with open(temp_config_path, "w", encoding="utf-8") as f:
                    f.write(content)
                config_path = temp_config_path

            cfg = Config.fromfile(config_path)

            if hasattr(cfg, "custom_imports"):
                cfg.custom_imports["allow_failed_imports"] = False

        finally:
            if temp_config_path and os.path.isfile(temp_config_path):
                os.remove(temp_config_path)

        split = self._resolve_split(cfg, splits)
        samples = list((splits or {}).get(split, []))
        if not samples:
            raise ValueError(f"{split.upper()} split has no available samples")

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = output_root or os.path.join(data_root, "model_test_results", timestamp)
        work_dir = os.path.join(root, "work_dir")
        show_dir = os.path.join(root, "show")
        out_dir = os.path.join(root, "out")
        os.makedirs(work_dir, exist_ok=True)
        os.makedirs(show_dir, exist_ok=True)
        os.makedirs(out_dir, exist_ok=True)

        self._patch_test_dataloader(cfg, data_root, split)
        self._force_single_process_test_dataloader(cfg)
        self._ensure_full_iou_metrics(cfg)
        self._disable_test_visualization(cfg)
        format_only = self._is_format_only(cfg)

        test_config = os.path.join(root, "test_config.py")
        cfg.dump(test_config)

        return MMSegTestConfig(
            test_config=test_config,
            checkpoint=checkpoint_path,
            split=split,
            work_dir=work_dir,
            show_dir=show_dir,
            out_dir=out_dir,
            custom_module_files=resolved_custom_module_files,
            sample_count=len(samples),
            labelled_count=sum(1 for sample in samples if sample.get("label_path")),
            samples=samples,
            format_only=format_only,
        )

    @staticmethod
    def _resolve_custom_module_files(config_path: str, custom_module_files: list[str] | None) -> list[str]:
        paths = [path for path in (custom_module_files or []) if path]
        if config_path:
            config_dir = os.path.dirname(os.path.abspath(config_path))
            for filename in ("custom_rs_dataset.py", "custom_live_pred_hook.py"):
                candidate = os.path.join(config_dir, filename)
                if os.path.isfile(candidate):
                    paths.append(candidate)

        resolved_paths = []
        for path in paths:
            abs_path = os.path.abspath(path)
            if abs_path not in resolved_paths:
                resolved_paths.append(abs_path)
        return resolved_paths

    def _resolve_split(self, cfg: Any, splits: dict[str, list[dict]]) -> str:
        if hasattr(cfg, "val_dataloader") and (splits or {}).get("val"):
            return "val"
        dataloader_split = self._find_dataloader_split(getattr(cfg, "test_dataloader", None))
        if dataloader_split == "test" and (splits or {}).get("test"):
            return "test"
        if (splits or {}).get("val"):
            return "val"
        if (splits or {}).get("test"):
            return "test"
        return "val"

    def _patch_test_dataloader(self, cfg: Any, data_root: str, split: str) -> None:
        if split == "val" and hasattr(cfg, "val_dataloader"):
            cfg.test_dataloader = copy.deepcopy(cfg.val_dataloader)
            if hasattr(cfg, "val_evaluator"):
                cfg.test_evaluator = copy.deepcopy(cfg.val_evaluator)
        elif not hasattr(cfg, "test_dataloader"):
            if not hasattr(cfg, "val_dataloader"):
                raise AttributeError("Missing test_dataloader / val_dataloader in config")
            cfg.test_dataloader = copy.deepcopy(cfg.val_dataloader)
            if hasattr(cfg, "val_evaluator"):
                cfg.test_evaluator = copy.deepcopy(cfg.val_evaluator)

        self._patch_dataset_node(cfg.test_dataloader, data_root, split)
        if hasattr(cfg, "data_root"):
            cfg.data_root = data_root.replace("\\", "/")

    def _patch_dataset_node(self, node: Any, data_root: str, split: str) -> None:
        if isinstance(node, dict):
            if "dataset" in node:
                self._patch_dataset_node(node["dataset"], data_root, split)
            if "datasets" in node and isinstance(node["datasets"], list):
                for child in node["datasets"]:
                    self._patch_dataset_node(child, data_root, split)
            if any(key in node for key in ("ann_file", "data_prefix", "data_root")):
                node["data_root"] = data_root.replace("\\", "/")
                node["ann_file"] = f"ImageSets/Segmentation/{split}.txt"
                node["data_prefix"] = {
                    "img_path": "JPEGImages",
                    "seg_map_path": "SegmentationClass",
                }
                node["img_suffix"] = self._detect_suffix(os.path.join(data_root, "JPEGImages"), ".jpg")
                node["seg_map_suffix"] = self._detect_suffix(os.path.join(data_root, "SegmentationClass"), ".png")
        elif isinstance(node, list):
            for child in node:
                self._patch_dataset_node(child, data_root, split)

    def _force_single_process_test_dataloader(self, cfg: Any) -> None:
        """Avoid Windows spawn workers needing importable project custom modules."""
        dataloader = getattr(cfg, "test_dataloader", None)
        if isinstance(dataloader, dict):
            dataloader["num_workers"] = 0
            dataloader["persistent_workers"] = False

    def _find_dataloader_split(self, node: Any) -> str | None:
        if isinstance(node, dict):
            ann_file = str(node.get("ann_file", "")).replace("\\", "/").lower()
            ann_name = os.path.basename(ann_file)
            if ann_name == "val.txt":
                return "val"
            if ann_name == "test.txt":
                return "test"
            found = self._find_dataloader_split(node.get("dataset"))
            if found:
                return found
            datasets = node.get("datasets")
            if isinstance(datasets, list):
                for child in datasets:
                    found = self._find_dataloader_split(child)
                    if found:
                        return found
        elif isinstance(node, list):
            for child in node:
                found = self._find_dataloader_split(child)
                if found:
                    return found
        return None

    def _ensure_full_iou_metrics(self, cfg: Any) -> None:
        self._patch_evaluator_metrics(getattr(cfg, "test_evaluator", None))

    def _disable_test_visualization(self, cfg: Any) -> None:
        default_hooks = getattr(cfg, "default_hooks", None)
        if isinstance(default_hooks, dict) and "visualization" in default_hooks:
            default_hooks["visualization"]["draw"] = False
            default_hooks["visualization"]["show"] = False
        visualizer = getattr(cfg, "visualizer", None)
        if isinstance(visualizer, dict):
            visualizer.pop("save_dir", None)

    def _patch_evaluator_metrics(self, evaluator: Any) -> None:
        if isinstance(evaluator, dict):
            evaluator_type = str(evaluator.get("type", ""))
            if evaluator_type == "IoUMetric" or "iou_metrics" in evaluator:
                evaluator["iou_metrics"] = ["mIoU", "mDice", "mFscore"]
            for key in ("metrics", "evaluator", "evaluators"):
                child = evaluator.get(key)
                if child is not None:
                    self._patch_evaluator_metrics(child)
        elif isinstance(evaluator, list):
            for item in evaluator:
                self._patch_evaluator_metrics(item)

    def _detect_suffix(self, dir_path: str, default: str) -> str:
        if not os.path.isdir(dir_path):
            return default
        for name in os.listdir(dir_path):
            ext = os.path.splitext(name)[1].lower()
            if ext:
                return ext
        return default

    def _is_format_only(self, cfg: Any) -> bool:
        evaluator = getattr(cfg, "test_evaluator", None)
        text = repr(self._to_plain(evaluator)).replace(" ", "").lower()
        return "format_only':true" in text or '"format_only":true' in text

    def _to_plain(self, value: Any) -> Any:
        try:
            return value.to_dict()
        except Exception:
            return value


class MMSegTestRunner:
    """Run MMSeg official test flow in a project-local subprocess."""

    def __init__(self, log_callback: Callable[[str], None] | None = None):
        self._log_callback = log_callback
        self._process: subprocess.Popen | None = None
        self._cancel_requested = False

    def cancel(self) -> None:
        self._cancel_requested = True
        if self._process and self._process.poll() is None:
            self._terminate_process_tree(self._process)

    def run(
        self,
        test_config: str,
        checkpoint: str,
        work_dir: str,
        show_dir: str | None = None,
        out_dir: str | None = None,
        cfg_options: dict | None = None,
        tta: bool = False,
        custom_module_files: list[str] | None = None,
        python_path: str | None = None,
    ) -> dict:
        runtime_python = resolve_training_python(python_path)
        command = [
            runtime_python,
            "-B",
            "-m",
            "core.mmseg_test_runner_entry",
            "--test-config",
            test_config,
            "--checkpoint",
            checkpoint,
            "--work-dir",
            work_dir,
        ]
        if out_dir:
            command.extend(["--out-dir", out_dir])
        if tta:
            command.append("--tta")
        if cfg_options:
            command.extend(["--cfg-options-json", json.dumps(cfg_options, ensure_ascii=False)])
        if custom_module_files:
            command.extend([
                "--custom-module-files-json",
                json.dumps(custom_module_files, ensure_ascii=False),
            ])

        env = os.environ.copy()
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        python_paths = [project_root]
        existing_pythonpath = env.get("PYTHONPATH")
        if existing_pythonpath:
            python_paths.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        env.setdefault("PYTHONIOENCODING", "utf-8")

        self._log(f"Python: {runtime_python}")
        self._log(f"Config: {test_config}")
        self._log(f"Checkpoint: {checkpoint}")
        self._log(f"Work dir: {work_dir}")
        if show_dir:
            self._log(f"Show dir: {show_dir} (official visualization disabled)")
        if out_dir:
            self._log(f"Out dir: {out_dir}")
        for module_file in custom_module_files or []:
            self._log(f"Custom module: {module_file}")

        result = {}
        self._cancel_requested = False
        process = subprocess.Popen(
            command,
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )
        self._process = process

        try:
            assert process.stdout is not None
            stdout_queue: queue.Queue[str | None] = queue.Queue()
            reader = threading.Thread(
                target=self._read_stdout_lines,
                args=(process.stdout, stdout_queue),
                daemon=True,
            )
            reader.start()

            while True:
                if self._cancel_requested:
                    self._terminate_process_tree(process)
                    break
                try:
                    raw_line = stdout_queue.get(timeout=0.1)
                except queue.Empty:
                    if process.poll() is not None:
                        if not reader.is_alive() and stdout_queue.empty():
                            break
                    continue

                if raw_line is None:
                    if process.poll() is not None:
                        break
                    continue

                line = raw_line.rstrip()
                if line:
                    if line.startswith(RESULT_PREFIX):
                        result = self._parse_result_line(line)
                    else:
                        self._log(line)

            if self._cancel_requested:
                self._terminate_process_tree(process)
                raise RuntimeError("Model test cancelled")
            return_code = process.wait()
            if return_code != 0:
                raise RuntimeError(f"Model test subprocess exited with code {return_code}")
        finally:
            if self._cancel_requested and process.poll() is None:
                self._terminate_process_tree(process)
            self._process = None

        return {
            "metrics": self._normalize_metrics(result.get("metrics", {})),
            "work_dir": result.get("work_dir", work_dir),
            "show_dir": result.get("show_dir", ""),
            "out_dir": result.get("out_dir", out_dir or ""),
        }

    def _parse_result_line(self, line: str) -> dict:
        payload = line[len(RESULT_PREFIX):]
        try:
            return json.loads(payload)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Failed to parse model test result: {e}") from e

    def _normalize_metrics(self, metrics: Any) -> dict:
        if isinstance(metrics, dict):
            return metrics
        return {}

    def _read_stdout_lines(self, stdout, stdout_queue: queue.Queue) -> None:
        try:
            for line in stdout:
                stdout_queue.put(line)
        except Exception as e:
            stdout_queue.put(f"Failed to read model test output: {e}")
        finally:
            stdout_queue.put(None)

    def _terminate_process_tree(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except Exception:
            pass

        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception as e:
                self._log(f"Failed to taskkill model test process tree: {e}")
        else:
            try:
                process.kill()
            except Exception:
                pass
        try:
            process.wait(timeout=2)
        except Exception:
            pass

    def _log(self, message: str) -> None:
        if self._log_callback:
            self._log_callback(message)



# =============================================================================
# Worker Thread Class
# =============================================================================

class InferenceWorker(QThread):
    """
    后台推理工作线程
    用于在后台执行耗时的推理任务，避免阻塞主界面
    """
    # 信号定义
    finished = Signal(str, dict, dict)  # (image_path, result, params)
    error = Signal(str)                 # (error_msg)
    log = Signal(str)                   # (log_msg)
    progress = Signal(int)              # (progress_value: 0-100)
    cancelled = Signal()                # 取消完成信号

    def __init__(self, inference_model: dict, image_path: str, strategy: str, inference_params: dict, output_path: str = None):
        super().__init__()
        self.inference_model = inference_model
        self.image_path = image_path
        self.strategy = strategy
        self.inference_params = inference_params
        self.output_path = output_path

        # 推理引擎引用 (用于取消)
        self._engine = None
        self._process = None
        self._cancel_requested = False

    def request_cancel(self):
        """Request cancel inference"""
        self._cancel_requested = True
        if self._engine:
            self._engine.request_cancel()
        if self._process and self._process.poll() is None:
            self._terminate_process_tree(self._process)
        self.log.emit("🛑 Cancellation request sent...")

    def _on_engine_progress(self, current, total):
        """推理引擎进度回调"""
        # 将进度映射到10-90的范围
        progress_value = int(10 + (current / total) * 80)
        self.progress.emit(progress_value)

    def run(self):
        try:
            self.log.emit("🔄 Starting background inference...")
            self.log.emit(f"   Image Path: {self.image_path}")
            self.log.emit(f"   Strategy: {self.strategy}")

            # 导入推理引擎 (延迟导入避免循环依赖)
            runtime_python = resolve_training_python(self.inference_model.get("python_path", ""))
            self.log.emit(f"Python: {runtime_python}")
            if not is_current_python(runtime_python):
                self.log.emit(
                    "Starting inference subprocess using training env..."
                )
                result = self._run_subprocess_inference(runtime_python)
                self.progress.emit(90)
                if self._cancel_requested:
                    self.log.emit("推理Cancelled")
                    self.cancelled.emit()
                    return
                if result is None:
                    raise RuntimeError("Inference result is empty")
                self.finished.emit(self.image_path, result, self.inference_params)
                return

            from core.inference_engine import InferenceEngine

            # 创建推理引擎
            self.log.emit("🔧 Initializing inference engine...")
            self._engine = InferenceEngine(self.inference_model)

            # Settings进度回调
            self._engine.set_progress_callback(self._on_engine_progress)

            self.progress.emit(10)

            # 执行推理
            self.log.emit(f"⚙️  Running {self.strategy} Inference...")

            result = None
            if self.strategy == 'large_image_block':
                # 大图分块推理
                if not self.output_path:
                    raise ValueError("Tile inference requires output path")

                self.log.emit(f"📁 Output Path: {self.output_path}")

                result = self._engine.large_image_block_inference(
                    self.image_path,
                    self.output_path,
                    crop_size=self.inference_params['crop_size'],
                    overlap_rate=self.inference_params['overlap_rate'],
                    enable_tta=self.inference_params['enable_tta']
                )

            elif self.strategy == 'sliding_window':
                # Sliding Window
                result = self._engine.sliding_window_inference(
                    self.image_path,
                    crop_size=self.inference_params['crop_size'],
                    stride=self.inference_params['stride'],
                    batch_size=self.inference_params['batch_size'],
                    enable_tta=self.inference_params['enable_tta']
                )

            elif self.strategy == 'resize':
                # Full Image Scale推理
                result = self._engine.resize_inference(
                    self.image_path,
                    enable_tta=self.inference_params['enable_tta']
                )

            else:
                raise ValueError(f"Unknown inference strategy: {self.strategy}")

            self.progress.emit(90)

            # 检查是否被取消
            if self._cancel_requested:
                self.log.emit("🛑 推理Cancelled")
                self.cancelled.emit()
                return

            if result is None:
                raise RuntimeError("Inference result is empty")

            self.finished.emit(self.image_path, result, self.inference_params)

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self.log.emit(f"❌ Background inference error: {str(e)}")
            self.error.emit(f"{str(e)}\n\n{error_details}")
        finally:
            if self._engine and hasattr(self._engine, "close"):
                self._engine.close()
            self._process = None

    def _run_subprocess_inference(self, runtime_python: str) -> dict:
        project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        artifact_dir = tempfile.mkdtemp(prefix="rs_seg_infer_")
        request_json = os.path.join(artifact_dir, "request.json")
        result_json = os.path.join(artifact_dir, "result.json")

        payload = {
            "inference_model": self.inference_model,
            "image_path": self.image_path,
            "strategy": self.strategy,
            "inference_params": self.inference_params,
            "output_path": self.output_path,
            "artifact_dir": artifact_dir,
        }
        with open(request_json, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)

        command = [
            runtime_python,
            "-B",
            "-m",
            "core.mmseg_inference_runner_entry",
            "--request-json",
            request_json,
            "--result-json",
            result_json,
        ]

        env = os.environ.copy()
        python_paths = [project_root]
        existing_pythonpath = env.get("PYTHONPATH")
        if existing_pythonpath:
            python_paths.append(existing_pythonpath)
        env["PYTHONPATH"] = os.pathsep.join(python_paths)
        env.setdefault("PYTHONIOENCODING", "utf-8")

        self._process = subprocess.Popen(
            command,
            cwd=project_root,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == "win32" else 0,
        )

        stdout_queue: queue.Queue[str | None] = queue.Queue()
        assert self._process.stdout is not None
        reader = threading.Thread(
            target=self._read_stdout_lines,
            args=(self._process.stdout, stdout_queue),
            daemon=True,
        )
        reader.start()

        while True:
            if self._cancel_requested:
                self._terminate_process_tree(self._process)
                raise RuntimeError("Inference cancelled")
            try:
                raw_line = stdout_queue.get(timeout=0.1)
            except queue.Empty:
                if self._process.poll() is not None and not reader.is_alive() and stdout_queue.empty():
                    break
                continue
            if raw_line is None:
                if self._process.poll() is not None:
                    break
                continue
            line = raw_line.rstrip()
            if line:
                if line.startswith(INFERENCE_PROGRESS_PREFIX):
                    self._handle_subprocess_progress(line)
                else:
                    self.log.emit(line)

        return_code = self._process.wait()
        if return_code != 0:
            error_text = ""
            if os.path.isfile(result_json):
                with open(result_json, "r", encoding="utf-8") as f:
                    error_text = json.load(f).get("error", "")
            raise RuntimeError(error_text or f"Inference subprocess exited with code {return_code}")
        if not os.path.isfile(result_json):
            raise RuntimeError("Inference subprocess did not write result.json")

        with open(result_json, "r", encoding="utf-8") as f:
            payload = json.load(f)
        if not payload.get("ok"):
            raise RuntimeError(payload.get("error", "Inference subprocess failed"))
        return self._restore_subprocess_value(payload.get("result", {}))

    def _handle_subprocess_progress(self, line: str) -> None:
        payload = line[len(INFERENCE_PROGRESS_PREFIX):]
        try:
            data = json.loads(payload)
            value = int(data.get("value", 0))
        except Exception:
            return
        self.progress.emit(max(0, min(100, value)))

    def _restore_subprocess_value(self, value):
        if isinstance(value, dict) and "__ndarray__" in value:
            return np.load(value["__ndarray__"], allow_pickle=False)
        if isinstance(value, dict):
            return {key: self._restore_subprocess_value(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._restore_subprocess_value(item) for item in value]
        return value

    def _read_stdout_lines(self, stdout, stdout_queue: queue.Queue) -> None:
        try:
            for line in stdout:
                stdout_queue.put(line)
        except Exception as e:
            stdout_queue.put(f"Failed to read inference output: {e}")
        finally:
            stdout_queue.put(None)

    def _terminate_process_tree(self, process: subprocess.Popen) -> None:
        if process.poll() is not None:
            return
        try:
            process.terminate()
        except Exception:
            pass

        if sys.platform == "win32":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                )
            except Exception as e:
                self.log.emit(f"Failed to taskkill inference process tree: {e}")
        else:
            try:
                process.kill()
            except Exception:
                pass
        try:
            process.wait(timeout=2)
        except Exception:
            pass


class ModelTestWorker(QThread):
    """Run the project-local MMSeg Runner.test() flow in background."""

    finished = Signal(dict)
    error = Signal(str)
    log = Signal(str)
    progress = Signal(int)
    cancelled = Signal()

    def __init__(self, inference_model: dict, dataset_context: dict):
        super().__init__()
        self.inference_model = inference_model
        self.dataset_context = dataset_context
        self._cancel_requested = False
        self._runner = None

    def request_cancel(self):
        self._cancel_requested = True
        if self._runner:
            self._runner.cancel()
        self.log.emit("Cancellation requested, terminating...")

    def run(self):
        try:
            if self._cancel_requested:
                self.cancelled.emit()
                return

            self.progress.emit(5)
            builder = MMSegTestConfigBuilder()
            test_config = builder.build(
                config_path=self.inference_model.get("config", ""),
                checkpoint_path=self.inference_model.get("checkpoint", ""),
                data_root=self.dataset_context.get("data_root", ""),
                splits=self.dataset_context.get("splits", {}),
                custom_module_files=self.inference_model.get("custom_module_files", []),
            )

            self.progress.emit(25)
            self._runner = MMSegTestRunner(log_callback=self.log.emit)
            runner_result = self._runner.run(
                test_config=test_config.test_config,
                checkpoint=test_config.checkpoint,
                work_dir=test_config.work_dir,
                show_dir=test_config.show_dir,
                out_dir=test_config.out_dir,
                custom_module_files=test_config.custom_module_files,
                python_path=self.inference_model.get("python_path", ""),
            )

            if self._cancel_requested:
                self.cancelled.emit()
                return

            self.progress.emit(90)
            samples = self._build_sample_results(test_config.samples, test_config.show_dir)
            result = {
                "summary": {
                    "split": test_config.split,
                    "sample_count": test_config.sample_count,
                    "labelled_count": test_config.labelled_count,
                    "format_only": test_config.format_only,
                    "work_dir": runner_result.get("work_dir", ""),
                    "show_dir": runner_result.get("show_dir", ""),
                    "out_dir": runner_result.get("out_dir", ""),
                },
                "metrics": runner_result.get("metrics", {}),
                "samples": samples,
            }
            self.progress.emit(100)
            self.finished.emit(result)

        except Exception as e:
            if self._cancel_requested:
                self.cancelled.emit()
                return
            import traceback
            self.error.emit(f"{e}\n\n{traceback.format_exc()}")
        finally:
            self._runner = None

    def _build_sample_results(self, samples: list, show_dir: str) -> list:
        prediction_files = self._collect_prediction_files(show_dir)
        results = []
        for sample in samples:
            image_path = sample.get("image_path", "")
            label_path = sample.get("label_path", "")
            sample_id = sample.get("sample_id") or os.path.splitext(os.path.basename(image_path))[0]
            results.append({
                "sample_id": sample_id,
                "image_path": image_path,
                "label_path": label_path if label_path and os.path.exists(label_path) else "",
                "prediction_path": self._find_prediction_file(sample_id, image_path, prediction_files),
            })
        return results

    def _collect_prediction_files(self, show_dir: str) -> list:
        if not show_dir or not os.path.isdir(show_dir):
            return []
        files = []
        for root, _dirs, names in os.walk(show_dir):
            for name in names:
                if os.path.splitext(name)[1].lower() in {".png", ".jpg", ".jpeg", ".bmp"}:
                    files.append(os.path.join(root, name))
        return files

    def _find_prediction_file(self, sample_id: str, image_path: str, prediction_files: list) -> str:
        stems = {
            os.path.splitext(os.path.basename(image_path))[0].lower(),
            str(sample_id).lower(),
        }
        for file_path in prediction_files:
            pred_stem = os.path.splitext(os.path.basename(file_path))[0].lower()
            if any(stem and stem in pred_stem for stem in stems):
                return file_path
        return ""


class InferencePanel(QWidget):
    """Inference Visualization Panel"""

    # 信号定义
    model_loaded = Signal(dict)  # Model Load完成信号
    inference_started = Signal()  # 推理开始信号
    inference_finished = Signal(dict)  # Inference Complete信号
    inference_error = Signal(str)  # 推理错误信号
    log_message = Signal(str)  # 日志消息信号

    # 同步信号：当用户在推理面板选择输入路径时发出
    # 用于同步到左侧 GIS 图层控制
    input_path_selected = Signal(str)  # 参数: 选择的图像文件路径

    # 新增：Predict初始化信号 (用于通知左侧图层列表显示占位符)
    # 参数: (input_path, output_filename_with_extension)
    prediction_initializing = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.inference_model = None
        self.last_inference_result = None  # 保存最后一次推理结果
        self.last_visualization_metadata = None

        # 同步控制标志 - 防止信号循环
        # 当从外部调用 set_image_path 时设为 True，阻止再次发出 input_path_selected 信号
        self._suppress_sync = False

        # 推理状态追踪
        self._is_inferencing = False
        self._inference_engine = None  # 保存引用以便取消

        # 当前关联的数据集根目录（由 MainWindow 在 Tab1 加载数据集后注入）
        # 设计决策（W-07）: 历史模型列表仅在软件运行时保留，
        #   - 不写入 QSettings / 文件 / 数据库
        #   - 软件关闭后状态丢失，重启后由用户重新加载数据集触发扫描
        #   - 单一数据源原则: comboBox_modelRegistry 内容始终来自 work_dirs/ 即时扫描
        self._current_data_root = None
        self._dataset_context = None
        self._model_test_worker = None
        self._model_test_results = []
        self._model_test_summary = {}
        self._is_model_testing = False
        self._custom_module_dirs = []
        self._custom_module_files = []

        self._setup_ui()
        self._connect_signals()
        self._init_inference_config()
        self._refresh_model_test_state()

    def _setup_ui(self):
        """SettingsUI布局"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)  # 压缩边距
        layout.setSpacing(4)  # 压缩组件间距

        # Model Load区
        self._create_model_config_group(layout)
        self._create_model_test_group(layout)

        # 推理策略区
        self._create_inference_strategy_group(layout)

        # 执行与Export区
        self._create_action_export_group(layout)

        # 推理结果显示区
        self._create_inference_result_group(layout)

        # 添加弹性空间
        layout.addStretch()

        # UI-09：阻止鼠标悬停时滚轮误改 SpinBox / ComboBox 的值
        install_wheel_guard(self)

        # 显式触发一次策略模式变化，让参数显隐与默认 RadioButton（大图分块）对齐
        self._on_strategy_mode_changed()
    
    def _create_model_config_group(self, parent_layout):
        """创建Model Load区"""
        self.groupBox_modelConfig = QGroupBox("Model Configuration")
        form_layout = QFormLayout(self.groupBox_modelConfig)
        form_layout.setSpacing(3)  # 压缩行间距
        form_layout.setContentsMargins(6, 6, 6, 6)  # 压缩边距

        # === 新增：模型库选择区 ===
        self.label_modelRegistry = QLabel("Trained Model Repo:")
        registry_layout = QHBoxLayout()
        self.comboBox_modelRegistry = QComboBox()
        self.comboBox_modelRegistry.addItem("Please select trained model...", userData=None)

        self.pushButton_refreshRegistry = QPushButton("🔄 Refresh")
        self.pushButton_refreshRegistry.setMaximumWidth(60)
        self.pushButton_refreshRegistry.setToolTip("Need to load dataset in Tab1 to scan work_dirs")

        registry_layout.addWidget(self.comboBox_modelRegistry)
        registry_layout.addWidget(self.pushButton_refreshRegistry)
        form_layout.addRow(self.label_modelRegistry, registry_layout)

        # 分隔线
        line_reg = QFrame()
        line_reg.setFrameShape(QFrame.HLine)
        line_reg.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line_reg)

        # 配置文件
        self.label_configFile = QLabel("Config File:")
        config_layout = QHBoxLayout()
        self.lineEdit_configFile = QLineEdit()
        self.lineEdit_configFile.setPlaceholderText("Select MMSeg Config (.py)")
        self.pushButton_browseConfig = QPushButton("Browse...")
        config_layout.addWidget(self.lineEdit_configFile)
        config_layout.addWidget(self.pushButton_browseConfig)
        form_layout.addRow(self.label_configFile, config_layout)

        # 模型名称（自动解析）
        self.label_modelName = QLabel("Model Name:")
        self.label_modelNameValue = QLabel("Config Not Loaded")
        self.label_modelNameValue.setStyleSheet("color: #888; font-style: italic;")
        form_layout.addRow(self.label_modelName, self.label_modelNameValue)

        # 权重文件
        self.label_checkpointFile = QLabel("Weight File:")
        checkpoint_layout = QHBoxLayout()
        self.lineEdit_checkpointFile = QLineEdit()
        self.lineEdit_checkpointFile.setPlaceholderText("Select Model Weight File (.pth)")
        self.pushButton_browseCheckpoint = QPushButton("Browse...")
        checkpoint_layout.addWidget(self.lineEdit_checkpointFile)
        checkpoint_layout.addWidget(self.pushButton_browseCheckpoint)
        form_layout.addRow(self.label_checkpointFile, checkpoint_layout)

        # 计算设备
        self.label_device = QLabel("Device:")
        self.comboBox_device = QComboBox()
        self.comboBox_device.addItems(["Auto", "CUDA:0", "CPU"])
        form_layout.addRow(self.label_device, self.comboBox_device)

        # 加载按钮和状态
        load_layout = QHBoxLayout()
        self.pushButton_loadModel = QPushButton("Load Model")
        self.label_modelStatus = QLabel("Not Loaded")
        load_layout.addWidget(self.pushButton_loadModel)
        load_layout.addWidget(self.label_modelStatus)
        load_layout.addStretch()
        form_layout.addRow("", load_layout)

        # Class图例
        self.label_classesLegend = QLabel("Class图例:")
        self.scrollArea_classesLegend = QScrollArea()
        self.scrollArea_classesLegend.setWidgetResizable(True)
        self.scrollArea_classesLegend.setMaximumHeight(150)
        self.scrollArea_classesLegend.setVisible(False)

        self.scrollAreaWidgetContents_classes = QWidget()
        self.verticalLayout_classes = QVBoxLayout(self.scrollAreaWidgetContents_classes)
        self.verticalLayout_classes.setContentsMargins(5, 5, 5, 5)
        self.verticalLayout_classes.setSpacing(3)
        self.scrollArea_classesLegend.setWidget(self.scrollAreaWidgetContents_classes)
        form_layout.addRow(self.label_classesLegend, self.scrollArea_classesLegend)

        parent_layout.addWidget(self.groupBox_modelConfig)

    def _create_model_test_group(self, parent_layout):
        """Create model test/evaluation controls."""
        self.groupBox_modelTest = QGroupBox("Model Test / Evaluation")
        form_layout = QFormLayout(self.groupBox_modelTest)
        form_layout.setSpacing(3)
        form_layout.setContentsMargins(6, 6, 6, 6)

        self.label_testDataset = QLabel("Test Data:")
        self.label_testDatasetInfo = QLabel("Not Loaded")
        self.label_testDatasetInfo.setWordWrap(True)
        form_layout.addRow(self.label_testDataset, self.label_testDatasetInfo)

        button_layout = QHBoxLayout()
        self.pushButton_testModel = QPushButton("Test Model")
        self.pushButton_cancelModelTest = QPushButton("Cancel Test")
        self.pushButton_cancelModelTest.setEnabled(False)
        button_layout.addWidget(self.pushButton_testModel)
        button_layout.addWidget(self.pushButton_cancelModelTest)
        button_layout.addStretch()
        form_layout.addRow("", button_layout)

        self.label_testProgress = QLabel("测试Progress:")
        progress_layout = QHBoxLayout()
        self.progressBar_modelTest = QProgressBar()
        self.progressBar_modelTest.setValue(0)
        progress_layout.addWidget(self.progressBar_modelTest)
        form_layout.addRow(self.label_testProgress, progress_layout)

        self.label_testStatus = QLabel("Not Tested")
        form_layout.addRow("Test Status:", self.label_testStatus)

        self.comboBox_testSamples = QComboBox()
        self.comboBox_testSamples.addItem("No Samples", userData=None)
        self.comboBox_testSamples.setEnabled(False)
        form_layout.addRow("Sample Preview:", self.comboBox_testSamples)

        parent_layout.addWidget(self.groupBox_modelTest)

    def _create_inference_strategy_group(self, parent_layout):
        """创建推理策略区"""
        self.groupBox_inferenceStrategy = QGroupBox("Inference Strategy")
        form_layout = QFormLayout(self.groupBox_inferenceStrategy)
        form_layout.setSpacing(3)  # 压缩行间距
        form_layout.setContentsMargins(6, 6, 6, 6)  # 压缩边距

        # 推理模式选择（单图/批量）
        self.label_inferenceMode = QLabel("Inference Mode:")
        mode_layout = QHBoxLayout()
        self.radioButton_singleImage = QRadioButton("Single Inference")
        self.radioButton_singleImage.setChecked(True)
        self.radioButton_batchInference = QRadioButton("Batch Inference")
        self.radioButton_batchInference.setVisible(False)  # P0-3: 隐藏Batch Inference
        mode_layout.addWidget(self.radioButton_singleImage)
        mode_layout.addWidget(self.radioButton_batchInference)
        mode_layout.addStretch()
        self.buttonGroup_inferenceMode = QButtonGroup(self)
        self.buttonGroup_inferenceMode.addButton(self.radioButton_singleImage)
        self.buttonGroup_inferenceMode.addButton(self.radioButton_batchInference)
        form_layout.addRow(self.label_inferenceMode, mode_layout)

        # 输入影像选择（支持从 GIS 图层同步）
        self.label_inputPath = QLabel("Input Image:")
        input_layout = QHBoxLayout()
        self.lineEdit_inputPath = QLineEdit()
        self.lineEdit_inputPath.setPlaceholderText("Select image file or sync from GIS layer")
        self.lineEdit_inputPath.setReadOnly(True)  # 只读，防止手动输入
        self.pushButton_browseInput = QPushButton("Browse...")
        input_layout.addWidget(self.lineEdit_inputPath)
        input_layout.addWidget(self.pushButton_browseInput)
        form_layout.addRow(self.label_inputPath, input_layout)

        # 输出路径选择（自动保存预览PNG）
        self.label_outputPath = QLabel("Output Path (Preview PNG):")
        output_layout = QHBoxLayout()
        self.lineEdit_outputPath = QLineEdit()
        self.lineEdit_outputPath.setPlaceholderText("Inference Complete后自动保存预览PNG的路径（默认为输入图像所在目录）")
        self.lineEdit_outputPath.setReadOnly(True)  # 只读，防止手动输入
        self.lineEdit_outputPath.setToolTip("Inference Complete后会自动保存一个PNG格式的预览图到此路径")
        self.pushButton_browseOutputPath = QPushButton("Browse...")
        self.pushButton_browseOutputPath.setToolTip("Select folder for auto-saving preview PNG")
        output_layout.addWidget(self.lineEdit_outputPath)
        output_layout.addWidget(self.pushButton_browseOutputPath)
        form_layout.addRow(self.label_outputPath, output_layout)

        # 分隔线
        line1 = QFrame()
        line1.setFrameShape(QFrame.HLine)
        line1.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line1)
        
        # 推理策略模式选择（大图分块/滑窗/Full Image Scale）
        self.label_strategyMode = QLabel("Strategy:")
        strategy_layout = QHBoxLayout()
        # 注意：调整布局顺序，把"大图分块"放第一位并默认选中
        # 对象名保持原命名，避免破坏 _on_strategy_mode_changed() 等已有信号槽
        self.radioButton_largeImageBlock = QRadioButton("Large Image Tile (GDAL)")
        self.radioButton_largeImageBlock.setChecked(True)
        self.radioButton_slidingWindow = QRadioButton("Sliding Window")
        self.radioButton_resize = QRadioButton("Full Image Scale")
        strategy_layout.addWidget(self.radioButton_largeImageBlock)
        strategy_layout.addWidget(self.radioButton_slidingWindow)
        strategy_layout.addWidget(self.radioButton_resize)
        strategy_layout.addStretch()
        self.buttonGroup_strategyMode = QButtonGroup(self)
        self.buttonGroup_strategyMode.addButton(self.radioButton_largeImageBlock)
        self.buttonGroup_strategyMode.addButton(self.radioButton_slidingWindow)
        self.buttonGroup_strategyMode.addButton(self.radioButton_resize)
        form_layout.addRow(self.label_strategyMode, strategy_layout)

        # 策略说明（与 RadioButton 显示顺序一致）
        self.label_strategyNote = QLabel(
            "• 大图分块：图像 > 20000 像素超大影像（需 GDAL，推荐）\n"
            "• Sliding Window：图像 2000–20000 像素范围，标准推理\n"
            "• Full Image Scale：图像 ≤ 2000×2000 像素，快速预览"
        )
        self.label_strategyNote.setWordWrap(True)
        self.label_strategyNote.setStyleSheet("color: #666; font-size: 10px; font-style: italic;")
        form_layout.addRow("", self.label_strategyNote)

        # 滑窗参数 - 窗口大小
        self.label_cropSize = QLabel("Crop Size:")
        self.spinBox_cropSize = QSpinBox()
        self.spinBox_cropSize.setMinimum(256)
        self.spinBox_cropSize.setMaximum(2048)
        self.spinBox_cropSize.setSingleStep(64)
        self.spinBox_cropSize.setValue(1024)
        form_layout.addRow(self.label_cropSize, self.spinBox_cropSize)

        # 滑窗参数 - 步长 / 大图分块参数 - 重叠率
        self.label_stride = QLabel("Stride:")
        stride_layout = QHBoxLayout()
        self.spinBox_stride = QSpinBox()
        self.spinBox_stride.setMinimum(64)
        self.spinBox_stride.setMaximum(2048)
        self.spinBox_stride.setSingleStep(64)
        self.spinBox_stride.setValue(512)
        self.label_strideHint = QLabel("Recommended: 50%-75% of crop size")
        self.label_strideHint.setStyleSheet("color: #888; font-size: 10px;")
        stride_layout.addWidget(self.spinBox_stride)
        stride_layout.addWidget(self.label_strideHint)
        stride_layout.addStretch()
        form_layout.addRow(self.label_stride, stride_layout)

        # 大图分块 - 重叠率
        self.label_overlapRate = QLabel("Overlap Rate:")
        overlap_layout = QHBoxLayout()
        self.doubleSpinBox_overlapRate = QDoubleSpinBox()
        self.doubleSpinBox_overlapRate.setMinimum(0.0)
        self.doubleSpinBox_overlapRate.setMaximum(0.5)
        self.doubleSpinBox_overlapRate.setSingleStep(0.05)
        self.doubleSpinBox_overlapRate.setValue(0.2)
        self.doubleSpinBox_overlapRate.setVisible(False)
        self.label_overlapHint = QLabel("大图分块模式的重叠率")
        self.label_overlapHint.setStyleSheet("color: #888; font-size: 10px;")
        self.label_overlapHint.setVisible(False)
        overlap_layout.addWidget(self.doubleSpinBox_overlapRate)
        overlap_layout.addWidget(self.label_overlapHint)
        overlap_layout.addStretch()
        form_layout.addRow(self.label_overlapRate, overlap_layout)

        # 滑窗参数 - 批大小
        self.label_batchSize = QLabel("Batch Size:")
        batch_size_layout = QHBoxLayout()
        self.spinBox_batchSize = QSpinBox()
        self.spinBox_batchSize.setMinimum(1)
        self.spinBox_batchSize.setMaximum(32)
        self.spinBox_batchSize.setValue(1)
        self.label_batchSizeHint = QLabel("Adjust based on GPU VRAM")
        self.label_batchSizeHint.setStyleSheet("color: #888; font-size: 10px;")
        batch_size_layout.addWidget(self.spinBox_batchSize)
        batch_size_layout.addWidget(self.label_batchSizeHint)
        batch_size_layout.addStretch()
        form_layout.addRow(self.label_batchSize, batch_size_layout)

        # 分隔线
        line2 = QFrame()
        line2.setFrameShape(QFrame.HLine)
        line2.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line2)

        # TTA增强选项
        self.checkBox_enableTTA = QCheckBox("Enable TTA")
        form_layout.addRow("", self.checkBox_enableTTA)

        # 分隔线
        line3 = QFrame()
        line3.setFrameShape(QFrame.HLine)
        line3.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line3)

        # 置信度阈值
        self.label_confThreshold = QLabel("Confidence Threshold:")
        self.doubleSpinBox_confThreshold = QDoubleSpinBox()
        self.doubleSpinBox_confThreshold.setMinimum(0.0)
        self.doubleSpinBox_confThreshold.setMaximum(1.0)
        self.doubleSpinBox_confThreshold.setSingleStep(0.05)
        self.doubleSpinBox_confThreshold.setValue(0.5)
        self.doubleSpinBox_confThreshold.setToolTip("Confidence threshold, only valid for models supporting confidence output")
        form_layout.addRow(self.label_confThreshold, self.doubleSpinBox_confThreshold)

        parent_layout.addWidget(self.groupBox_inferenceStrategy)

    def _create_action_export_group(self, parent_layout):
        """创建执行与Export区"""
        self.groupBox_actionExport = QGroupBox("Action & Export")
        form_layout = QFormLayout(self.groupBox_actionExport)
        form_layout.setSpacing(3)  # 压缩行间距
        form_layout.setContentsMargins(6, 6, 6, 6)  # 压缩边距

        # 运行推理按钮
        self.pushButton_runInference = QPushButton("Run Inference")
        form_layout.addRow(self.pushButton_runInference)

        # Batch Inference按钮
        self.pushButton_batchInference = QPushButton("Batch Inference")
        self.pushButton_batchInference.setVisible(False)  # P0-3: 隐藏Batch Inference
        form_layout.addRow(self.pushButton_batchInference)

        # 进度条
        self.label_inferenceProgress = QLabel("Progress:")
        progress_layout = QHBoxLayout()
        self.progressBar_inference = QProgressBar()
        self.progressBar_inference.setValue(0)

        # 取消按钮
        self.pushButton_cancelInference = QPushButton("❌ Cancel")
        self.pushButton_cancelInference.setToolTip("取消当前正在进行的推理任务")
        self.pushButton_cancelInference.setEnabled(False)  # 初始Disable
        self.pushButton_cancelInference.setMaximumWidth(80)

        progress_layout.addWidget(self.progressBar_inference)
        progress_layout.addWidget(self.pushButton_cancelInference)
        form_layout.addRow(self.label_inferenceProgress, progress_layout)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        form_layout.addRow(line)

        # Export说明
        self.label_exportNote = QLabel(
            "💡 提示：Inference Complete后会自动保存预览PNG。\n"
            "   如需其他格式或正式存档，请使用下方的Export功能。"
        )
        self.label_exportNote.setWordWrap(True)
        self.label_exportNote.setStyleSheet("color: #0066cc; font-size: 10px; padding: 5px; background-color: #e6f2ff; border-radius: 3px;")
        form_layout.addRow("", self.label_exportNote)

        # Export格式（语义分割常用格式）
        self.label_exportFormat = QLabel("Export Format:")
        export_format_layout = QHBoxLayout()
        self.checkBox_exportTIF = QCheckBox("GeoTIFF (.tif)")
        self.checkBox_exportTIF.setChecked(True)
        self.checkBox_exportTIF.setToolTip("Export GeoTIFF, retain geo info (standard format)")
        self.checkBox_exportPNG = QCheckBox("PNG")
        self.checkBox_exportPNG.setToolTip("Export PNG format (no geo info)")
        self.checkBox_exportNumpy = QCheckBox("NumPy (.npy)")
        self.checkBox_exportNumpy.setToolTip("Export NumPy array format for further processing")
        export_format_layout.addWidget(self.checkBox_exportTIF)
        export_format_layout.addWidget(self.checkBox_exportPNG)
        export_format_layout.addWidget(self.checkBox_exportNumpy)
        export_format_layout.addStretch()
        form_layout.addRow(self.label_exportFormat, export_format_layout)

        # Export目录
        self.label_exportDir = QLabel("Export Directory:")
        export_dir_layout = QHBoxLayout()
        self.lineEdit_exportDir = QLineEdit()
        self.lineEdit_exportDir.setPlaceholderText("Select export directory (optional, default: output path)")
        self.lineEdit_exportDir.setToolTip("手动Export时使用的目录，用于正式存档")
        self.pushButton_browseExportDir = QPushButton("Browse...")
        self.pushButton_browseExportDir.setToolTip("Select Export Directory")
        export_dir_layout.addWidget(self.lineEdit_exportDir)
        export_dir_layout.addWidget(self.pushButton_browseExportDir)
        form_layout.addRow(self.label_exportDir, export_dir_layout)

        # Export结果按钮
        self.pushButton_exportResults = QPushButton("📤 Export Results")
        self.pushButton_exportResults.setToolTip("Export inference results to selected formats (PNG/NumPy/JSON)")
        form_layout.addRow(self.pushButton_exportResults)

        parent_layout.addWidget(self.groupBox_actionExport)

    def _create_inference_result_group(self, parent_layout):
        """创建推理结果显示区"""
        self.groupBox_inferenceResult = QGroupBox("Inference Result")
        layout = QVBoxLayout(self.groupBox_inferenceResult)
        layout.setSpacing(3)  # 压缩行间距
        layout.setContentsMargins(6, 6, 6, 6)  # 压缩边距

        self.label_inferenceResult = QLabel("No inference results\n\nPlease load model and run inference.")
        self.label_inferenceResult.setWordWrap(True)
        self.label_inferenceResult.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.label_inferenceResult.setMinimumHeight(100)
        layout.addWidget(self.label_inferenceResult)

        self.table_modelTestMetrics = QTableWidget(0, 3)
        self.table_modelTestMetrics.setHorizontalHeaderLabels(["Metrics", "数值", "Source"])
        self.table_modelTestMetrics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_modelTestMetrics.verticalHeader().setVisible(False)
        self.table_modelTestMetrics.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_modelTestMetrics.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table_modelTestMetrics.setVisible(False)
        layout.addWidget(self.table_modelTestMetrics)

        self.table_modelTestClassMetrics = QTableWidget(0, 4)
        self.table_modelTestClassMetrics.setHorizontalHeaderLabels(["Class", "IoU", "Acc", "Dice"])
        self.table_modelTestClassMetrics.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table_modelTestClassMetrics.verticalHeader().setVisible(False)
        self.table_modelTestClassMetrics.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table_modelTestClassMetrics.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table_modelTestClassMetrics.setVisible(False)
        layout.addWidget(self.table_modelTestClassMetrics)

        # Class颜色配置组件（Inference Complete后显示）
        self.visualization_settings = VisualizationSettingsWidget()
        self.visualization_settings.setVisible(False)
        layout.addWidget(self.visualization_settings)

        # 可视化渲染预览组件（已废弃，永久隐藏）
        self.visualization_widget = InferenceVisualizationWidget()
        self.visualization_widget.setVisible(False)
        layout.addWidget(self.visualization_widget)

        parent_layout.addWidget(self.groupBox_inferenceResult)

    def _connect_signals(self):
        """连接信号"""
        # 模型库区
        self.comboBox_modelRegistry.currentIndexChanged.connect(self._on_model_registry_changed)
        self.pushButton_refreshRegistry.clicked.connect(self._manual_refresh_registry)

        # Model Load区
        self.pushButton_browseConfig.clicked.connect(self._browse_config_file)
        self.pushButton_browseCheckpoint.clicked.connect(self._browse_checkpoint_file)
        self.lineEdit_configFile.textChanged.connect(self._on_config_file_changed)
        self.pushButton_loadModel.clicked.connect(self._load_inference_model)
        self.pushButton_testModel.clicked.connect(self._run_model_test)
        self.pushButton_cancelModelTest.clicked.connect(self._cancel_model_test)
        self.comboBox_testSamples.currentIndexChanged.connect(self._on_test_sample_changed)

        # 推理模式切换
        self.radioButton_batchInference.toggled.connect(self._on_inference_mode_changed)

        # 策略模式切换
        self.radioButton_slidingWindow.toggled.connect(self._on_strategy_mode_changed)
        self.radioButton_resize.toggled.connect(self._on_strategy_mode_changed)
        self.radioButton_largeImageBlock.toggled.connect(self._on_strategy_mode_changed)

        # 输入影像浏览
        self.pushButton_browseInput.clicked.connect(self._browse_input_image)

        # 输出路径浏览
        self.pushButton_browseOutputPath.clicked.connect(self._browse_output_path)

        # Export目录浏览
        self.pushButton_browseExportDir.clicked.connect(self._browse_export_dir)

        # 推理执行
        self.pushButton_runInference.clicked.connect(self._run_inference)
        self.pushButton_batchInference.clicked.connect(self._run_batch_inference)
        self.pushButton_cancelInference.clicked.connect(self._cancel_inference)

        # Export结果
        self.pushButton_exportResults.clicked.connect(self._export_results)

        # 可视化Settings信号（由 MainWindow 外部连接到 GIS 画布，此处不再内部连接预览渲染）

    def set_data_root(self, data_root: str):
        """由 MainWindow 在 Tab1 加载数据集后调用（BUG-INFER-02 修复）。

        同步 data_root 属性，并在下拉框尚处于初始占位状态时立即触发一次模型库扫描，
        让用户切到 Tab3 时下拉框已经填好候选项。

        触发条件 ``count() <= 1`` 同时满足：
        - 初次切到 Tab3：下拉框只有占位项 → 立即扫描，解决"无可选项"
        - 用户已选中模型后再切回 Tab1 重新加载：下拉框已含训练记录 → 不静默改写
        """
        if not data_root:
            return
        self._current_data_root = data_root
        # 仅当下拉框尚处于初始占位状态时自动扫一次，避免覆盖用户已选的项
        if self.comboBox_modelRegistry.count() <= 1:
            self.scan_trained_models(data_root)
        self._refresh_model_test_state()

    def set_dataset_context(self, dataset_context: dict):
        """Inject the dataset context loaded in Data Insight."""
        self._dataset_context = dataset_context or None
        if dataset_context and dataset_context.get("data_root"):
            self._current_data_root = dataset_context.get("data_root")
        self._refresh_model_test_state()

    def set_custom_module_dirs(self, module_dirs: list[str] | None):
        self._custom_module_dirs = normalize_import_paths(module_dirs)

    def get_custom_module_dirs(self) -> list[str]:
        return list(self._custom_module_dirs)

    def set_custom_module_files(self, module_files: list[str] | None):
        resolved = []
        for path in module_files or []:
            if not path:
                continue
            abs_path = os.path.abspath(path)
            if abs_path not in resolved:
                resolved.append(abs_path)
        self._custom_module_files = resolved

    def get_custom_module_files(self) -> list[str]:
        return list(self._custom_module_files)

    def _resolve_custom_module_dirs(self, config_path: str = "") -> list[str]:
        paths = list(self._custom_module_dirs)
        if config_path:
            paths.append(os.path.dirname(os.path.abspath(config_path)))
        return normalize_import_paths(paths)

    def _resolve_custom_module_files(self, config_path: str = "") -> list[str]:
        paths = list(self._custom_module_files)
        if not paths and self._custom_module_dirs:
            for module_dir in normalize_import_paths(self._custom_module_dirs):
                for filename in ("custom_rs_dataset.py", "custom_live_pred_hook.py"):
                    candidate = os.path.join(module_dir, filename)
                    if os.path.isfile(candidate):
                        paths.append(candidate)
        if config_path:
            config_dir = os.path.dirname(os.path.abspath(config_path))
            for filename in ("custom_rs_dataset.py", "custom_live_pred_hook.py"):
                candidate = os.path.join(config_dir, filename)
                if os.path.isfile(candidate):
                    paths.append(candidate)

        resolved = []
        for path in paths:
            abs_path = os.path.abspath(path)
            if abs_path not in resolved:
                resolved.append(abs_path)
        return resolved

    def _refresh_model_test_state(self):
        if not hasattr(self, "label_testDatasetInfo"):
            return

        context = self._dataset_context or {}
        data_root = context.get("data_root") or self._current_data_root
        splits = context.get("splits", {})
        if not data_root:
            self.label_testDatasetInfo.setText("Not Loaded")
            self.pushButton_testModel.setEnabled(False)
            return

        split = self._resolve_model_test_split(self.lineEdit_configFile.text().strip(), splits)
        samples = list(splits.get(split, []))
        labelled_count = sum(1 for sample in samples if sample.get("label_path"))
        self.label_testDatasetInfo.setText(
            f"Split: {split.upper()} | Sample: {len(samples)} | Label: {labelled_count}"
        )
        self.pushButton_testModel.setEnabled(bool(samples) and bool(self.inference_model) and not self._is_model_testing)

    def scan_trained_models(self, data_root=None):
        """扫描已训练模型库"""
        if data_root:
            self._current_data_root = data_root
        elif not self._current_data_root:
            return

        work_dirs_path = os.path.join(self._current_data_root, 'work_dirs')
        if not os.path.exists(work_dirs_path):
            self._emit_log(
                f"ℹ️ No work_dirs/ found at: {self._current_data_root}"
            )
            return

        current_data = self.comboBox_modelRegistry.currentData()

        self.comboBox_modelRegistry.blockSignals(True)
        self.comboBox_modelRegistry.clear()
        self.comboBox_modelRegistry.addItem("Select history trained model or specify file below...", userData=None)

        try:
            dirs = [d for d in os.listdir(work_dirs_path) if os.path.isdir(os.path.join(work_dirs_path, d))]
            dirs.sort(key=lambda d: os.path.getmtime(os.path.join(work_dirs_path, d)), reverse=True)

            for d in dirs:
                dir_path = os.path.join(work_dirs_path, d)
                config_file = os.path.join(dir_path, 'train_config.py')

                if not os.path.exists(config_file):
                    continue

                pth_files = [f for f in os.listdir(dir_path) if f.endswith('.pth')]
                if not pth_files:
                    continue

                self.comboBox_modelRegistry.addItem(f"📦 {d}", userData=dir_path)

        except Exception as e:
            self._emit_log(f"⚠️  Scan model repo failed: {e}")

        self.comboBox_modelRegistry.blockSignals(False)

        # P1-1: 扫描结束后若只有默认项，更新提示文字
        if self.comboBox_modelRegistry.count() == 1:
            self.comboBox_modelRegistry.setItemText(0, "(No training records found, please load dataset in 'Data Profile' or specify config below)")

        if current_data:
            index = self.comboBox_modelRegistry.findData(current_data)
            if index >= 0:
                self.comboBox_modelRegistry.setCurrentIndex(index)

    def _manual_refresh_registry(self):
        """手动刷新模型库（BUG-INFER-02 修复）。

        优先使用 Tab1 同步过来的 data_root；缺失时回退到项目根目录扫描，
        覆盖"未经过 Tab1 直接进入 Tab3"的独立推理工作流。
        """
        candidate = self._current_data_root
        if not candidate:
            # 回退：使用项目当前工作目录（main.py 启动目录，通常含 work_dirs/）
            candidate = os.getcwd()
            self._emit_log(
                f"ℹ️ Dataset not linked, fallback to project root scan: {candidate}"
            )
        self.scan_trained_models(candidate)
        self._emit_log("🔄 Refreshed trained model repo")
            
    def _on_model_registry_changed(self, index):
        """模型下拉框选择改变时触发"""
        if index <= 0:
            return

        dir_path = self.comboBox_modelRegistry.currentData()
        if not dir_path or not os.path.exists(dir_path):
            return

        config_file = os.path.join(dir_path, 'train_config.py')

        pth_files = [f for f in os.listdir(dir_path) if f.endswith('.pth')]
        best_pth = None

        for pth in pth_files:
            if 'best' in pth.lower():
                best_pth = pth
                break

        if not best_pth and pth_files:
            best_pth = max(pth_files, key=lambda f: os.path.getmtime(os.path.join(dir_path, f)))

        if os.path.exists(config_file):
            self.lineEdit_configFile.setText(config_file)

        if best_pth:
            self.lineEdit_checkpointFile.setText(os.path.join(dir_path, best_pth))

        self._emit_log(f"✅ Auto-filled model config from repo: {os.path.basename(dir_path)}")

    def select_model_by_dir(self, work_dir):
        """外部调用：强制下拉框选中指定的目录"""
        if not work_dir:
            return False

        normalized_dir = os.path.normpath(work_dir)
        for i in range(self.comboBox_modelRegistry.count()):
            item_data = self.comboBox_modelRegistry.itemData(i)
            if item_data and os.path.normpath(item_data) == normalized_dir:
                self.comboBox_modelRegistry.setCurrentIndex(i)
                return True
        return False

    def _init_inference_config(self):
        """初始化推理配置"""
        cuda_available = self._check_cuda_available()

        if cuda_available:
            self.comboBox_device.setCurrentIndex(0)  # Auto
            self._emit_log("🎮 [Inference] CUDA available, default device: Auto")
        else:
            self.comboBox_device.setCurrentIndex(2)  # CPU
            # Disable CUDA:0 选项
            model = self.comboBox_device.model()
            item = model.item(1)
            if item:
                item.setEnabled(False)
                item.setToolTip("CUDA Not Available")
            self._emit_log("⚠️  [推理配置] CUDA Not Available，默认设备: CPU")

    def _check_cuda_available(self) -> bool:
        """检测 CUDA 是否可用"""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False
        except Exception:
            return False

    def _emit_log(self, message: str):
        """发送日志消息"""
        self.log_message.emit(message)
        try:
            sys.__stdout__.write(f"{message}\n")
            sys.__stdout__.flush()
        except Exception:
            pass

    def _browse_config_file(self):
        """Browse and select MMSeg config"""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select MMSegmentation Config",
            "",
            "Python Files (*.py);;All Files (*.*)"
        )

        if not file_path:
            return

        self.lineEdit_configFile.setText(file_path)

        if not self._validate_config_file(file_path):
            return

        # 尝试解析模型名称
        try:
            config_info = self._parse_config_file(file_path)
            model_name = config_info.get('model_name', 'Unknown Model')

            self.label_modelNameValue.setText(model_name)
            self.label_modelNameValue.setStyleSheet("color: #000; font-style: normal; font-weight: bold;")

            self._emit_log(f"✅ [推理配置] 已加载Config File: {os.path.basename(file_path)}")
            self._emit_log(f"   📝 Model Name: {model_name}")

            # 智能推荐权重文件
            self._suggest_checkpoint_file(file_path, model_name)

        except Exception as e:
            self.label_modelNameValue.setText("Parse Failed")
            self.label_modelNameValue.setStyleSheet("color: #f00; font-style: italic;")
            self._emit_log(f"❌ [推理配置] 配置文件Parse Failed: {e}")

    def _validate_config_file(self, file_path: str) -> bool:
        """Validate config format"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            required_keywords = ['model', 'dict']
            has_keywords = any(keyword in content for keyword in required_keywords)

            if not has_keywords:
                QMessageBox.warning(
                    self,
                    "Config Format Error",
                    "所选文件可能不是有效的 MMSegmentation 配置文件。\n\n"
                    "有效的配置文件应包含 'model' 定义。"
                )
                return False

            return True

        except Exception as e:
            QMessageBox.critical(
                self,
                "File Read Error",
                f"Cannot read config file.\n\nError msg: {e}"
            )
            return False

    def _parse_config_file(self, file_path: str) -> dict:
        """解析配置文件获取模型信息 - 使用增强解析器"""
        try:
            # 使用增强的配置解析器
            from core.config_parser import ConfigParser
            parser = ConfigParser()

            # 解析配置文件
            classes, palette = parser.parse_config_file(file_path)
            model_name = parser.extract_model_name(file_path)
            model_type = parser.extract_model_type(file_path)

            # 构建配置信息
            config_info = {
                'model_name': model_name or os.path.splitext(os.path.basename(file_path))[0],
                'model_type': model_type,
                'classes': classes,
                'palette': palette
            }

            return config_info

        except Exception as e:
            # 优雅降级 - 不影响Model Load
            self._emit_log(f"⚠️  Config parse warning: {e}")
            return {
                'model_name': os.path.splitext(os.path.basename(file_path))[0],
                'model_type': None,
                'classes': None,
                'palette': None
            }

    def _suggest_checkpoint_file(self, config_path: str, model_name: str):
        """智能推荐权重文件"""
        config_dir = os.path.dirname(config_path)

        search_dirs = [
            config_dir,
            os.path.join(config_dir, 'checkpoints'),
            os.path.join(config_dir, '..', 'checkpoints'),
            os.path.join(config_dir, 'work_dirs'),
        ]

        found_checkpoints = []
        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue

            try:
                for file in os.listdir(search_dir):
                    if file.endswith(('.pth', '.pt')):
                        file_lower = file.lower()
                        model_lower = model_name.lower().replace('-', '').replace(' ', '')

                        if model_lower in file_lower.replace('-', '').replace('_', ''):
                            found_checkpoints.append(os.path.join(search_dir, file))
            except:
                continue

        if found_checkpoints:
            latest_checkpoint = max(found_checkpoints, key=os.path.getmtime)

            reply = QMessageBox.question(
                self,
                "Found matched weight file",
                f"Found with model '{model_name}' matching weight files:\n\n"
                f"{os.path.basename(latest_checkpoint)}\n\n"
                f"是否使用此权重文件？",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )

            if reply == QMessageBox.StandardButton.Yes:
                self.lineEdit_checkpointFile.setText(latest_checkpoint)
                self._emit_log(f"💡 [推理配置] 自动选择Weight File: {os.path.basename(latest_checkpoint)}")

    def _browse_checkpoint_file(self):
        """浏览并Select Model Weight File"""
        start_dir = ""
        config_path = self.lineEdit_configFile.text()
        if config_path and os.path.exists(config_path):
            start_dir = os.path.dirname(config_path)

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Model Weight File",
            start_dir,
            "PyTorch Checkpoint (*.pth *.pt);;All Files (*.*)"
        )

        if file_path:
            self.lineEdit_checkpointFile.setText(file_path)

            file_size = os.path.getsize(file_path)
            size_mb = file_size / (1024 * 1024)

            self._emit_log(f"✅ [推理配置] 已选择Weight File: {os.path.basename(file_path)}")
            self._emit_log(f"   📦 File Size: {size_mb:.2f} MB")

    def _on_config_file_changed(self, text):
        """配置文件路径变化时触发"""
        if not text:
            self.label_modelNameValue.setText("Config Not Loaded")
            self.label_modelNameValue.setStyleSheet("color: #888; font-style: italic;")

        self._refresh_model_test_state()

    def _on_inference_mode_changed(self, checked):
        """推理模式切换"""
        # 批量模式时，输入影像框应该支持选择目录，但我们统一使用程序化控制
        # 因此此处不再Disable/Enable控件
        pass

    def _on_strategy_mode_changed(self):
        """策略模式切换"""
        is_sliding_window = self.radioButton_slidingWindow.isChecked()
        is_large_image = self.radioButton_largeImageBlock.isChecked()

        # 滑窗模式：显示步长，隐藏重叠率
        self.spinBox_stride.setVisible(is_sliding_window)
        self.label_strideHint.setVisible(is_sliding_window)

        # 大图分块模式：显示重叠率，隐藏步长
        self.doubleSpinBox_overlapRate.setVisible(is_large_image)
        self.label_overlapHint.setVisible(is_large_image)

        # 更新标签文本
        if is_large_image:
            self.label_stride.setVisible(False)
            self.label_overlapRate.setVisible(True)
        else:
            self.label_stride.setVisible(is_sliding_window)
            self.label_overlapRate.setVisible(False)

        # 窗口大小和批大小对Full Image Scale模式不可用
        is_resize = self.radioButton_resize.isChecked()
        self.spinBox_cropSize.setEnabled(not is_resize)
        self.spinBox_batchSize.setEnabled(is_sliding_window)

    def _browse_input_image(self):
        """Browse input image"""
        if self.is_single_image_mode():
            # 单图模式：选择文件
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Select image to infer",
                "",
                "Image Files (*.png *.jpg *.jpeg *.tif *.tiff *.bmp);;All Files (*.*)"
            )
            if file_path:
                self.lineEdit_inputPath.setText(file_path)
                # P1-2: 选图后自动推荐推理策略
                try:
                    from PIL import Image as _PIL_Image
                    with _PIL_Image.open(file_path) as _img:
                        _w, _h = _img.size
                    self._auto_recommend_strategy(_w, _h)
                except Exception:
                    pass  # 读取失败时静默跳过
                # 发出同步信号
                if not self._suppress_sync:
                    self.input_path_selected.emit(file_path)
        else:
            # 批量模式：选择目录
            dir_path = QFileDialog.getExistingDirectory(
                self,
                "Select Batch Inference Image Directory",
                "",
                QFileDialog.Option.ShowDirsOnly
            )
            if dir_path:
                self.lineEdit_inputPath.setText(dir_path)

    def _auto_recommend_strategy(self, w: int, h: int):
        """根据图像尺寸自动推荐推理策略并更新说明文字"""
        if w * h <= 2000 * 2000:
            self.radioButton_resize.setChecked(True)
            tag = ("[Recommended]", "", "")
        elif w * h <= 20000 * 20000:
            self.radioButton_slidingWindow.setChecked(True)
            tag = ("", "[Recommended]", "")
        else:
            self.radioButton_largeImageBlock.setChecked(True)
            tag = ("", "", "[Recommended]")

        self.label_strategyNote.setText(
            f"• Full Image Scale {tag[0]}：图像 ≤ 2000×2000 像素，快速预览\n"
            f"• Sliding Window {tag[1]}：图像 2000–20000 像素范围，标准推理\n"
            f"• 大图分块 {tag[2]}: image > 20000 pixels (requires GDAL)"
        )
        self._emit_log(f"💡 Auto-selected strategy based on image size ({w}×{h})")

    def _browse_output_path(self):
        """Browse output path (auto-save preview PNG)"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select folder for auto-saving preview PNG",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        if dir_path:
            self.lineEdit_outputPath.setText(dir_path)
            self._emit_log(f"✅ [Inference] Preview PNG output path set: {dir_path}")

    def _generate_output_filename(self, input_path: str) -> str:
        """
        生成输出文件名（自动命名规则）

        规则：input.jpg -> input_pred_v1
        注意：不含扩展名，扩展名由具体保存逻辑决定

        Args:
            input_path: 输入图像路径

        Returns:
            输出文件名（不含扩展名）
        """
        base_name = os.path.splitext(os.path.basename(input_path))[0]
        # 用户需求：input.tif -> input_pred_v1.png
        output_filename = f"{base_name}_pred_v1"
        return output_filename

    def _browse_export_dir(self):
        """Browse Export Directory"""
        dir_path = QFileDialog.getExistingDirectory(
            self,
            "Select Export Directory",
            "",
            QFileDialog.Option.ShowDirsOnly
        )
        if dir_path:
            self.lineEdit_exportDir.setText(dir_path)

    def _load_inference_model(self):
        """加载推理模型"""
        config_path = self.lineEdit_configFile.text().strip()
        checkpoint_path = self.lineEdit_checkpointFile.text().strip()

        if not config_path:
            self._emit_log("⚠️  Please select config file first")
            QMessageBox.warning(self, "Missing Config File", "请先Select MMSegmentation Config。")
            return

        if not checkpoint_path:
            self._emit_log("⚠️  Please select weight file first")
            QMessageBox.warning(self, "Missing Weight File", "请先Select Model Weight File。")
            return

        if not os.path.exists(config_path):
            self._emit_log(f"❌ 配置File Not Found: {config_path}")
            QMessageBox.critical(self, "配置File Not Found", f"Config file does not exist:\n{config_path}")
            return

        if not os.path.exists(checkpoint_path):
            self._emit_log(f"❌ 权重File Not Found: {checkpoint_path}")
            QMessageBox.critical(self, "权重File Not Found", f"权重File Not Found:\n{checkpoint_path}")
            return

        device_text = self.comboBox_device.currentText()
        device_map = {"Auto": "cuda:0", "CUDA:0": "cuda:0", "CPU": "cpu"}
        device = device_map.get(device_text, "cpu")

        if device_text == "Auto" and not self._check_cuda_available():
            device = "cpu"

        self.pushButton_loadModel.setEnabled(False)
        self._emit_log("🔄 Loading model...")

        QApplication.processEvents()
        QTimer.singleShot(100, lambda: self._do_load_inference_model(config_path, checkpoint_path, device))

    def _do_load_inference_model(self, config_path: str, checkpoint_path: str, device: str):
        """实际执行Model Load - 增强版本"""
        try:
            # 解析配置文件 - 使用健壮解析器
            config_info = self._parse_config_file_robust(config_path)

            # 即使配置Parse Failed，也继续Model Load
            if config_info.get('classes') is None:
                self._emit_log("⚠️  未找到Class信息，将使用默认Settings")

            # 保存模型信息（实际项目中应使用 MMSegmentation API 加载真实模型）
            runtime_python = resolve_training_python()
            custom_module_files = self._resolve_custom_module_files(config_path)
            self.inference_model = {
                'config': config_path,
                'checkpoint': checkpoint_path,
                'device': device,
                'classes': config_info.get('classes'),
                'palette': config_info.get('palette'),
                'model_name': config_info.get('model_name', 'Unknown Model'),
                'custom_module_files': custom_module_files,
                'python_path': runtime_python,
            }

            self.pushButton_loadModel.setEnabled(True)
            self.label_modelStatus.setText("Model Ready")
            self.label_modelStatus.setStyleSheet("color: #28a745; font-weight: bold;")

            # 显示Class图例 - 安全版本
            try:
                self._display_classes_legend_safe(config_info.get('classes'), config_info.get('palette'))
            except Exception as legend_error:
                self._emit_log(f"⚠️  Class legend warning: {legend_error}")

            self._emit_log("✅ Model Ready (Model Ready)")
            self._emit_log(f"Python: {runtime_python}")
            for module_file in custom_module_files:
                self._emit_log(f"Custom module: {module_file}")
            self.model_loaded.emit(self.inference_model)
            self._refresh_model_test_state()

        except Exception as e:
            self._handle_model_loading_error(e)

    def _parse_config_file_robust(self, file_path: str) -> dict:
        """健壮的配置文件解析"""
        try:
            from core.config_parser import ConfigParser
            parser = ConfigParser()
            classes, palette = parser.parse_config_file(file_path)
            model_name = parser.extract_model_name(file_path)
            model_type = parser.extract_model_type(file_path)

            return {
                'classes': classes,
                'palette': palette,
                'model_name': model_name,
                'model_type': model_type
            }
        except Exception as e:
            # 记录警告但不抛出异常
            self._emit_log(f"⚠️  Config parse failed: {e}")
            return {
                'classes': None,
                'palette': None,
                'model_name': os.path.splitext(os.path.basename(file_path))[0],
                'model_type': None
            }

    def _display_classes_legend_safe(self, classes, palette):
        """安全的Class图例显示"""
        try:
            self._display_classes_legend(classes, palette)
        except Exception as e:
            self._emit_log(f"⚠️  Class图例显示失败: {e}")
            # 隐藏图例区域但不影响其他功能
            try:
                self.scrollArea_classesLegend.setVisible(False)
            except:
                pass

    def _handle_model_loading_error(self, error: Exception):
        """处理Model Load错误"""
        self.pushButton_loadModel.setEnabled(True)
        self.label_modelStatus.setText("Load Failed")
        self.label_modelStatus.setStyleSheet("color: #dc3545; font-weight: bold;")

        import traceback
        error_details = traceback.format_exc()
        self._emit_log(f"❌ Model load failed: {error}")
        self._emit_log(f"Detailed error:\n{error_details}")

        QMessageBox.critical(self, "Model Load Failed", f"Error occurred during model load.\n\nError msg:\n{str(error)}")

    def _display_classes_legend(self, classes, palette):
        """显示Class图例"""
        try:
            layout = self.verticalLayout_classes
            while layout.count():
                child = layout.takeAt(0)
                if child.widget():
                    child.widget().deleteLater()

            if classes is None:
                classes = []
            if palette is None:
                palette = []

            if not classes or not palette:
                self.scrollArea_classesLegend.setVisible(False)
                self._emit_log("⚠️  CLASSES or PALETTE not found in config")
                return

            self.scrollArea_classesLegend.setVisible(True)

            for idx, class_name in enumerate(classes):
                try:
                    if idx < len(palette):
                        color = palette[idx]
                        if isinstance(color, (list, tuple)) and len(color) >= 3:
                            r, g, b = int(color[0]), int(color[1]), int(color[2])
                        else:
                            r, g, b = 128, 128, 128
                    else:
                        r, g, b = 128, 128, 128

                    class_label = QLabel(self.scrollAreaWidgetContents_classes)
                    class_label.setObjectName(f"label_class_{idx}")
                    class_label.setText(f"  {str(class_name)}")
                    class_label.setStyleSheet(
                        f"background-color: rgb({r}, {g}, {b}); "
                        f"color: {'white' if (r + g + b) < 384 else 'black'}; "
                        f"padding: 3px 8px; "
                        f"border-radius: 3px; "
                        f"font-size: 11px;"
                    )

                    layout.addWidget(class_label)
                except Exception as label_error:
                    self._emit_log(f"⚠️  创建Class标签 {idx} Failed: {label_error}")
                    continue

            layout.addStretch()

            if classes:
                self._emit_log(f"📊 Loaded {len(classes)} 个Class")

        except Exception as e:
            self._emit_log(f"⚠️  Class图例显示失败: {e}")
            try:
                self.scrollArea_classesLegend.setVisible(False)
            except:
                pass

    def _resolve_model_test_split(self, config_path: str, splits: dict) -> str:
        if config_path and os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_text = f.read().lower()
                if "test_dataloader" in config_text and "test" in config_text and splits.get("test"):
                    return "test"
            except Exception:
                pass
        if splits.get("val"):
            return "val"
        if splits.get("test"):
            return "test"
        return "val"

    def _run_model_test(self):
        if not self.inference_model:
            QMessageBox.warning(self, "Model Not Loaded", "Please load model first.")
            return
        module_warnings = validate_custom_module_files(
            self.inference_model.get("custom_module_files", [])
        )
        if module_warnings:
            message = "\n".join(module_warnings)
            self._emit_log(f"Custom module path invalid: {message}")
            QMessageBox.critical(self, "自定义模块路径失效", message)
            return
        if not self._dataset_context or not self._dataset_context.get("data_root"):
            QMessageBox.warning(self, "Dataset not loaded", "Please load dataset in Data Profile first.")
            return
        if self._is_model_testing:
            return

        self._set_model_test_running(True)
        self._clear_model_test_tables()
        self._emit_log("Model Test Started")
        self.progressBar_modelTest.setValue(0)
        self._clear_test_sample_selector()

        self._model_test_worker = ModelTestWorker(self.inference_model, self._dataset_context)
        self._model_test_worker.log.connect(self._emit_log)
        self._model_test_worker.progress.connect(self.progressBar_modelTest.setValue)
        self._model_test_worker.finished.connect(self._on_model_test_finished)
        self._model_test_worker.error.connect(self._on_model_test_error)
        self._model_test_worker.cancelled.connect(self._on_model_test_cancelled)
        self._model_test_worker.finished.connect(self._cleanup_model_test_worker)
        self._model_test_worker.error.connect(self._cleanup_model_test_worker)
        self._model_test_worker.cancelled.connect(self._cleanup_model_test_worker)
        self._model_test_worker.start()

    def _cancel_model_test(self):
        if self._model_test_worker:
            self._model_test_worker.request_cancel()
            self.pushButton_cancelModelTest.setEnabled(False)
            self.label_testStatus.setText("Cancelling")

    def _on_model_test_finished(self, result: dict):
        self._model_test_summary = result.get("summary", {})
        self._model_test_results = result.get("samples", [])
        self.label_testStatus.setText("Test Complete")
        self._clear_model_test_tables()
        self._clear_test_sample_selector()
        self._log_model_test_result(self._model_test_summary, result.get("metrics", {}))

    def _on_model_test_error(self, error_msg: str):
        self.progressBar_modelTest.setValue(0)
        self.label_testStatus.setText("Test Failed")
        self._emit_log(f"Model test failed: {error_msg}")

    def _on_model_test_cancelled(self):
        self.progressBar_modelTest.setValue(0)
        self.label_testStatus.setText("Cancelled")
        self._emit_log("模型测试Cancelled")

    def _cleanup_model_test_worker(self):
        self._set_model_test_running(False)
        if self._model_test_worker:
            self._model_test_worker.deleteLater()
            self._model_test_worker = None

    def _set_model_test_running(self, is_running: bool):
        self._is_model_testing = is_running
        self.pushButton_testModel.setEnabled(not is_running)
        self.pushButton_cancelModelTest.setEnabled(is_running)
        if is_running:
            self.label_testStatus.setText("Testing")
        else:
            self._refresh_model_test_state()

    def _format_model_test_summary(self, summary: dict) -> str:
        return (
            f"模型Test Complete\n"
            f"Split: {str(summary.get('split', '')).upper()}\n"
            f"样本: {summary.get('sample_count', 0)}\n"
            f"Label: {summary.get('labelled_count', 0)}\n"
            f"输出: {summary.get('work_dir', '')}"
        )

    def _clear_model_test_tables(self):
        self.table_modelTestMetrics.setRowCount(0)
        self.table_modelTestMetrics.setVisible(False)
        self.table_modelTestClassMetrics.setRowCount(0)
        self.table_modelTestClassMetrics.setVisible(False)

    def _clear_test_sample_selector(self):
        self.comboBox_testSamples.blockSignals(True)
        self.comboBox_testSamples.clear()
        self.comboBox_testSamples.addItem("No Samples", userData=None)
        self.comboBox_testSamples.setEnabled(False)
        self.comboBox_testSamples.blockSignals(False)

    def _log_model_test_result(self, summary: dict, metrics: dict):
        self._emit_log("模型Test Complete")
        self._emit_log(f"Split: {str(summary.get('split', '')).upper()}")
        self._emit_log(f"样本: {summary.get('sample_count', 0)}")
        self._emit_log(f"Label: {summary.get('labelled_count', 0)}")
        self._emit_log(f"Test logs and evaluation records saved to {summary.get('work_dir', '')}")
        show_dir = summary.get("show_dir", "")
        out_dir = summary.get("out_dir", "")
        if show_dir:
            self._emit_log(f"Official visualization output saved to {show_dir}")
        if out_dir:
            self._emit_log(f"Raw prediction output saved to {out_dir}")

    def _update_model_test_tables(self, metrics: dict):
        metric_items = []
        class_items = []
        for key, value in (metrics or {}).items():
            if isinstance(value, (list, tuple)) and key.lower() in {"classes", "class_metrics"}:
                class_items = list(value)
            elif isinstance(value, (int, float, str, np.integer, np.floating)):
                metric_items.append((str(key), value))

        self.table_modelTestMetrics.setRowCount(len(metric_items))
        for row, (name, value) in enumerate(metric_items):
            self.table_modelTestMetrics.setItem(row, 0, QTableWidgetItem(name))
            self.table_modelTestMetrics.setItem(row, 1, QTableWidgetItem(self._format_metric_value(value)))
            self.table_modelTestMetrics.setItem(row, 2, QTableWidgetItem("Runner.test()"))
        self.table_modelTestMetrics.setVisible(bool(metric_items))

        self.table_modelTestClassMetrics.setRowCount(len(class_items))
        for row, item in enumerate(class_items):
            if isinstance(item, dict):
                values = [
                    item.get("class") or item.get("name") or str(row),
                    item.get("IoU", item.get("iou", "")),
                    item.get("Acc", item.get("acc", "")),
                    item.get("Dice", item.get("dice", "")),
                ]
            else:
                values = [str(item), "", "", ""]
            for col, value in enumerate(values):
                self.table_modelTestClassMetrics.setItem(row, col, QTableWidgetItem(self._format_metric_value(value)))
        self.table_modelTestClassMetrics.setVisible(bool(class_items))

    def _format_metric_value(self, value) -> str:
        if isinstance(value, (np.integer, int)):
            return str(int(value))
        if isinstance(value, (np.floating, float)):
            return f"{float(value):.4f}"
        return str(value)

    def _populate_test_sample_selector(self, samples: list):
        self.comboBox_testSamples.blockSignals(True)
        self.comboBox_testSamples.clear()
        if not samples:
            self.comboBox_testSamples.addItem("No Samples", userData=None)
            self.comboBox_testSamples.setEnabled(False)
        else:
            for sample in samples:
                label_state = "Has Label" if sample.get("label_path") else "No Label"
                self.comboBox_testSamples.addItem(f"{sample.get('sample_id', '')} ({label_state})", userData=sample)
            self.comboBox_testSamples.setEnabled(True)
            self.comboBox_testSamples.setCurrentIndex(0)
        self.comboBox_testSamples.blockSignals(False)

    def _on_test_sample_changed(self, index: int):
        sample = self.comboBox_testSamples.itemData(index)
        if sample:
            self._display_test_sample(sample)

    def _display_test_sample(self, sample: dict):
        try:
            image = self._read_preview_image(sample.get("image_path", ""), as_mask=False)
            label = None
            if sample.get("label_path"):
                label = self._read_preview_image(sample.get("label_path", ""), as_mask=True)
            prediction_path = sample.get("prediction_path", "")
            if not prediction_path:
                self.visualization_widget.clear()
                self.visualization_widget.setVisible(True)
                self.visualization_widget.image_label.setText("Prediction result not found")
                return
            prediction = self._read_preview_image(prediction_path, as_mask=False)
            self.visualization_settings.setVisible(False)
            self.visualization_widget.setVisible(True)
            self.visualization_widget.render_test_images(image=image, prediction=prediction, label=label)
        except Exception as e:
            self.visualization_widget.setVisible(True)
            self.visualization_widget.image_label.setText(f"Sample preview failed: {e}")

    def _read_preview_image(self, path: str, as_mask: bool = False):
        if not path or not os.path.exists(path):
            raise FileNotFoundError(path)
        from PIL import Image

        image = Image.open(path)
        if as_mask:
            return np.array(image)
        return np.array(image.convert("RGB"))

    def _run_inference(self):
        """Run Single Inference"""
        # 1. 检查模型是否已加载
        if not self.inference_model:
            self._emit_log("⚠️  Model not loaded, cannot infer")
            QMessageBox.warning(self, "Model Not Loaded", "Please load inference model first.")
            return

        module_warnings = validate_custom_module_files(
            self.inference_model.get("custom_module_files", [])
        )
        if module_warnings:
            message = "\n".join(module_warnings)
            self._emit_log(f"Custom module path invalid: {message}")
            QMessageBox.critical(self, "自定义模块路径失效", message)
            return

        # 2. 使用已选择的输入影像路径
        image_path = self.lineEdit_inputPath.text().strip()

        if not image_path:
            self._emit_log("⚠️  No image selected文件")
            QMessageBox.warning(
                self,
                "No image selected",
                "请先在'输入影像'中Select image to infer，\n或从 GIS 图层中同步图像。"
            )
            return

        # 3. 读取选择的图片（验证）
        if not os.path.exists(image_path):
            self._emit_log(f"❌ 图像File Not Found: {image_path}")
            QMessageBox.critical(self, "File Not Found", f"图像File Not Found:\n{image_path}")
            return

        try:
            from PIL import Image

            # 针对大尺寸遥感影像，提高PIL的像素限制
            # 默认限制约为178MB像素，这里提高到10GB像素
            Image.MAX_IMAGE_PIXELS = 10000000000

            img = Image.open(image_path)
            img_width, img_height = img.size
            img_size_mb = os.path.getsize(image_path) / (1024 * 1024)

            self._emit_log(f"📷 Loaded Image: {os.path.basename(image_path)}")
            self._emit_log(f"   Size: {img_width} x {img_height} ({img_width * img_height / 1000000:.1f}M pixels)")
            self._emit_log(f"   File Size: {img_size_mb:.2f} MB")

            # 对于超大图像给出警告和建议
            if img_width * img_height > 100000000:  # 超过1亿像素
                self._emit_log(f"⚠️  Detected large image, recommend Tile (GDAL) mode")

                # 如果当前选择的是Full Image Scale或Sliding Window，强烈建议切换
                if self.radioButton_resize.isChecked():
                    reply = QMessageBox.question(
                        self,
                        "Large Image Warning",
                        f"Detected large image ({img_width} x {img_height})。\n\n"
                        f"当前选择的是'Full Image Scale'模式，可能导致内存不足。\n"
                        f"建议切换到'Large Image Tile (GDAL)'模式。\n\n"
                        f"是否继续使用Full Image Scale模式？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )

                    if reply == QMessageBox.StandardButton.No:
                        self._emit_log("⚠️  User cancelled inference")
                        return

                elif self.radioButton_slidingWindow.isChecked():
                    reply = QMessageBox.warning(
                        self,
                        "Large Image Warning",
                        f"Detected large image ({img_width} x {img_height} = {img_width*img_height/1000000:.1f}M像素)。\n\n"
                        f"⚠️ 重要提示：\n"
                        f"'Sliding Window'模式需要在内存中创建完整的结果掩码，\n"
                        f"对于如此大的图像会导致内存溢出！\n\n"
                        f"系统将跳过实际推理以保护内存。\n\n"
                        f"✅ 强烈建议：\n"
                        f"请切换到'Large Image Tile (GDAL)'模式进行真正的推理！\n\n"
                        f"是否继续（将不会进行实际推理）？",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No
                    )

                    if reply == QMessageBox.StandardButton.No:
                        self._emit_log("⚠️  User cancelled inference，建议切换到大图分块模式")
                        return

        except Exception as e:
            self._emit_log(f"❌ Image read failed: {e}")
            QMessageBox.critical(self, "Image Read Failed", f"Cannot read image file.\n\nError msg:\n{str(e)}")
            return

        # 发送推理开始信号
        self.inference_started.emit()
        self._emit_log("🚀 Start single inference...")

        # 发送同步信号到左侧 GIS 图层控制（如果未被抑制）
        if not self._suppress_sync:
            self.input_path_selected.emit(image_path)

        # Disable推理按钮，防止重复点击
        self.pushButton_runInference.setEnabled(False)
        self.progressBar_inference.setValue(0)

        # 获取推理配置
        if self.radioButton_largeImageBlock.isChecked():
            strategy = 'large_image_block'
        elif self.radioButton_resize.isChecked():
            strategy = 'resize'
        else:
            strategy = 'sliding_window'

        inference_params = {
            'crop_size': self.spinBox_cropSize.value(),
            'stride': self.spinBox_stride.value(),
            'overlap_rate': self.doubleSpinBox_overlapRate.value(),
            'batch_size': self.spinBox_batchSize.value(),
            'enable_tta': self.checkBox_enableTTA.isChecked(),
            'conf_threshold': self.doubleSpinBox_confThreshold.value()
        }

        self._emit_log(f"   Strategy: {strategy}")
        if strategy == 'sliding_window':
            self._emit_log(f"   Window Size: {inference_params['crop_size']}")
            self._emit_log(f"   Stride: {inference_params['stride']}")
            self._emit_log(f"   Batch Size: {inference_params['batch_size']}")
        elif strategy == 'large_image_block':
            self._emit_log(f"   Window Size: {inference_params['crop_size']}")
            self._emit_log(f"   Overlap Rate: {inference_params['overlap_rate']}")
        self._emit_log(f"   TTA: {'Enable' if inference_params['enable_tta'] else 'Disable'}")

        # ========== 新增：通知图层列表添加占位符 ==========
        # 1. 确定输出文件名和扩展名
        base_output_name = self._generate_output_filename(image_path)
        if strategy == 'large_image_block':
            ext = ".tif"
        else:
            ext = ".png" # 默认保存为PNG

        expected_output_filename = f"{base_output_name}{ext}"

        # 2. 发送信号
        self.prediction_initializing.emit(image_path, expected_output_filename)
        self._emit_log(f"⏳ Reserved layer position: {expected_output_filename}")
        # ===============================================

        # 使用 QThread 异步执行推理
        self._start_worker(image_path, strategy, inference_params)

    def _start_worker(self, image_path: str, strategy: str, inference_params: dict):
        """启动后台工作线程"""
        # 准备大图模式需要的 output_path
        output_path = None
        if strategy == 'large_image_block':
            # 获取输出目录
            output_dir = self.lineEdit_outputPath.text().strip()
            if not output_dir:
                output_dir = os.path.dirname(image_path)
                self._emit_log(f"⚠️  Output path not set, using default: {output_dir}")

            # 生成文件名
            output_filename = self._generate_output_filename(image_path)
            output_path = os.path.join(output_dir, f"{output_filename}.tif") # 注意这里是大图模式特有的后缀

        # 创建并启动 Worker
        self._inference_worker = InferenceWorker(
            self.inference_model,
            image_path,
            strategy,
            inference_params,
            output_path
        )

        # 连接信号
        self._inference_worker.log.connect(self._emit_log)
        self._inference_worker.progress.connect(self.progressBar_inference.setValue)
        self._inference_worker.finished.connect(self._on_worker_finished)
        self._inference_worker.error.connect(self._on_worker_error)
        self._inference_worker.cancelled.connect(self._on_worker_cancelled)  # 取消信号
        self._inference_worker.finished.connect(self._cleanup_worker)
        self._inference_worker.error.connect(self._cleanup_worker)
        self._inference_worker.cancelled.connect(self._cleanup_worker)

        # Enable取消按钮
        self._is_inferencing = True
        self.pushButton_cancelInference.setEnabled(True)

        # 启动
        self._inference_worker.start()

    def _on_worker_finished(self, image_path: str, result: dict, inference_params: dict):
        """后台Inference Complete处理"""
        self.progressBar_inference.setValue(100)

        success = result.get('success', False)
        self._emit_log(f"📊 Inference Result Status: {'Success' if success else '失败'}")

        if success:
            self._handle_inference_success(image_path, result, inference_params)
        else:
            error_msg = result.get('error', 'Unknown error')
            self._handle_inference_error(error_msg)

    def _on_worker_error(self, error_msg: str):
        """后台推理错误处理"""
        self._handle_inference_error(error_msg)

    def _cleanup_worker(self):
        """清理 Worker 资源"""
        self.pushButton_runInference.setEnabled(True)
        self.pushButton_cancelInference.setEnabled(False)  # Disable取消按钮
        self._is_inferencing = False
        if hasattr(self, '_inference_worker'):
            self._inference_worker.deleteLater()
            self._inference_worker = None

    def _cancel_inference(self):
        """取消当前推理任务"""
        if not self._is_inferencing:
            self._emit_log("⚠️  No ongoing inference task")
            return

        if hasattr(self, '_inference_worker') and self._inference_worker:
            self._emit_log("🛑 Cancelling inference...")
            self._inference_worker.request_cancel()
            self.pushButton_cancelInference.setEnabled(False)
            self.pushButton_cancelInference.setText("Cancelling...")
        else:
            self._emit_log("⚠️  Cannot cancel: Worker not found")

    def _on_worker_cancelled(self):
        """推理被取消时的处理"""
        self._emit_log("✅ 推理已Success取消")
        self.progressBar_inference.setValue(0)
        self.pushButton_cancelInference.setText("❌ Cancel")
        self.label_inferenceResult.setText("推理Cancelled\\n\\n可以重新配置参数后再次运行推理。")

    def _handle_inference_success(self, image_path: str, result: dict, inference_params: dict):
        """处理推理Success的结果"""
        try:
            # 提取结果信息
            mask = result.get('mask')
            image_shape = result.get('image_shape', (0, 0))
            strategy = result.get('strategy', 'unknown')
            params = result.get('params', {})

            # 构建结果显示文本
            use_real_model = result.get('use_real_model', False)

            result_text = f"✅ Inference Complete！\n\n"

            # 显示推理模式
            if use_real_model:
                result_text += f"🚀 Inference with Real Model (MMSegmentation)\n\n"
            else:
                result_text += f"⚠️  Note: Currently using mock inference (MMSegmentation not integrated)\n\n"

            result_text += f"📷 Image: {os.path.basename(image_path)}\n"
            result_text += f"📐 Size: {image_shape[1]} x {image_shape[0]}\n"
            result_text += f"🎯 Strategy: {strategy}\n\n"

            if strategy == 'sliding_window':
                result_text += f"Window Params:\n"
                result_text += f"  • Window Size: {params.get('crop_size', 'N/A')}\n"
                result_text += f"  • Stride: {params.get('stride', 'N/A')}\n"
                result_text += f"  • Batch Size: {params.get('batch_size', 'N/A')}\n"
                result_text += f"  • Total Windows: {params.get('total_windows', 'N/A')}\n"

            result_text += f"\nInference Config:\n"
            result_text += f"  • TTA: {'Enable' if params.get('enable_tta', False) else 'Disable'}\n"
            result_text += f"  • Confidence Threshold: {inference_params.get('conf_threshold', 0.5)}\n"

            # 大图分块推理的特殊处理
            if strategy == 'large_image_block':
                output_path = result.get('output_path', '')
                temp_dir = result.get('temp_dir', '')

                result_text += f"\nTile Inference Result:\n"
                result_text += f"  • Output File: {os.path.basename(output_path)}\n"
                result_text += f"  • Tile Temp Dir: {os.path.basename(temp_dir)}\n"
                result_text += f"  • Tiles: {params.get('x_num', 0)} x {params.get('y_num', 0)} = {params.get('total_blocks', 0)}\n"

                # 更新结果显示
                self.label_inferenceResult.setText(result_text)

                # 保存推理结果
                self.last_inference_result = {
                    'image_path': image_path,
                    'output_path': output_path,
                    'result': result,
                    'params': inference_params
                }

                # 初始化可视化Settings（允许使用回退 classes/palette）
                self._ensure_visualization_controls(mask=mask, result=result)

                # 发送Inference Complete信号
                self.inference_finished.emit(result)

                self._emit_log("✅ 大图分块Inference Complete")
                self._emit_log(f"   Output File: {output_path}")

                # 提示用户
                QMessageBox.information(
                    self,
                    "Inference Complete",
                    f"大图分块推理已Success完成！\n\n"
                    f"图像: {os.path.basename(image_path)}\n"
                    f"输出: {output_path}\n"
                    f"分块数: {params.get('total_blocks', 0)}\n\n"
                    f"结果已保存为GeoTIFF格式。"
                )
                return

            # 统计Class分布（非大图分块模式）
            unique_classes = []  # 初始化变量
            total_pixels = image_shape[0] * image_shape[1]

            if mask is not None:
                unique_classes = np.unique(mask)
                result_text += f"\n检测到的Class: {len(unique_classes)} items\n"

                classes = result.get('classes', [])
                if classes:
                    result_text += f"\nClass分布:\n"
                    for cls_id in unique_classes[:10]:  # 最多显示10个Class
                        if cls_id < len(classes):
                            cls_name = classes[cls_id]
                            pixel_count = np.sum(mask == cls_id)
                            percentage = (pixel_count / mask.size) * 100
                            result_text += f"  • {cls_name}: {percentage:.2f}%\n"
            else:
                # 超大图像，未生成完整掩码
                result_text += f"\n💡 Large Image Mode:\n"
                result_text += f"  • Total pixels: {total_pixels:,} ({total_pixels/1000000:.1f}M)\n"
                result_text += f"  • To save memory, full mask not generated\n"
                result_text += f"  • 推理流程已验证Success\n"
                result_text += f"  • Real results will be generated after MMSegmentation integration\n"

            # 更新结果显示
            self.label_inferenceResult.setText(result_text)

            # 读取原始图像数据（用于后续可视化调整）
            image_array = None
            try:
                from PIL import Image
                img = Image.open(image_path).convert('RGB')
                image_array = np.array(img)
            except Exception as e:
                self._emit_log(f"⚠️  Read original image failed: {e}")

            # 保存推理结果供Export使用
            self.last_inference_result = {
                'image_path': image_path,
                'image': image_array,  # 保存图像数组用于可视化调整
                'mask': mask,
                'result': result,
                'params': inference_params
            }

            # 自动保存预览PNG（如果有掩码数据）
            saved_path = None
            if mask is not None:
                try:
                    # 获取输出路径
                    output_dir = self.lineEdit_outputPath.text().strip()
                    if not output_dir:
                        output_dir = os.path.dirname(image_path)
                        self._emit_log(f"⚠️  Output path not set, preview PNG will be saved to: {output_dir}")

                    # 生成输出文件名（自动命名规则：input.jpg -> input_pred_v1.png）
                    base_output_name = self._generate_output_filename(image_path)
                    output_filename = f"{base_output_name}.png"
                    saved_path = os.path.join(output_dir, output_filename)

                    # 保存为PNG格式（预览用）
                    from PIL import Image
                    result_image = Image.fromarray(mask.astype(np.uint8))
                    result_image.save(saved_path)

                    self._emit_log(f"✅ Preview PNG auto-saved: {saved_path}")

                    # 更新last_inference_result，添加保存路径
                    self.last_inference_result['saved_path'] = saved_path

                except Exception as save_error:
                    self._emit_log(f"⚠️  Preview PNG auto-save failed: {save_error}")

            self._emit_log("✅ Inference Complete")
            if mask is not None:
                self._emit_log(f"   Detected {len(unique_classes)} 个Class")
            else:
                self._emit_log(f"   Large Image Mode: full mask not generated (normal)")

            # 先准备可视化元数据，再通知外部使用当前 palette 注入主画布。
            self._ensure_visualization_controls(mask=mask, result=result)

            # 发送Inference Complete信号
            self.inference_finished.emit(result)

            # P1-3: 改为非侵入式日志提示（去掉弹窗）
            self._emit_log(f"✅ Inference Complete：{os.path.basename(image_path)}, Strategy: {strategy}")
            if saved_path:
                self._emit_log(f"   Preview saved to:{saved_path}")

        except Exception as e:
            self._emit_log(f"⚠️  Result process warning: {e}")
            self.label_inferenceResult.setText(f"Inference Complete，但结果处理出现问题:\n{str(e)}")

    def _handle_inference_error(self, error_msg: str):
        """处理推理错误"""
        self.progressBar_inference.setValue(0)

        error_text = f"❌ Inference failed\n\nError msg:\n{error_msg}"
        self.label_inferenceResult.setText(error_text)

        self._emit_log(f"❌ Inference Failed: {error_msg}")

        # 发送错误信号
        self.inference_error.emit(error_msg)

        QMessageBox.critical(
            self,
            "Inference Failed",
            f"Error occurred during inference.\n\nError msg:\n{error_msg}"
        )

    def _run_batch_inference(self):
        """Run Batch Inference"""
        if not self.inference_model:
            QMessageBox.warning(self, "Model Not Loaded", "Please load inference model first.")
            return

        batch_dir = self.lineEdit_inputPath.text().strip()
        if not batch_dir or not os.path.isdir(batch_dir):
            QMessageBox.warning(self, "Invalid Input Directory", "Please select valid batch inference image directory.")
            return

        self.inference_started.emit()
        self._emit_log(f"🚀 Start batch inference: {batch_dir}")

        # TODO: 实现实际的Batch Inference逻辑
        self.label_inferenceResult.setText("Batch inference to be implemented...\n\nPlease integrate MMSegmentation API in actual project.")

    def _export_results(self):
        """Export Inference Results"""
        # 1. 检查是否有推理结果
        if not self.last_inference_result:
            self._emit_log("⚠️  No inference results to export")
            QMessageBox.warning(
                self,
                "No Inference Results",
                "Please run inference first before exporting."
            )
            return

        # 2. 检查Export目录
        export_dir = self.lineEdit_exportDir.text().strip()
        if not export_dir:
            # 如果没有SettingsExport目录，使用输出路径
            export_dir = self.lineEdit_outputPath.text().strip()
            if not export_dir:
                # 如果输出路径也没有，使用输入图像所在目录
                input_path = self.last_inference_result.get('image_path', '')
                if input_path:
                    export_dir = os.path.dirname(input_path)
                else:
                    QMessageBox.warning(
                        self,
                        "Export Directory Not Set",
                        "请先Select Export Directory。"
                    )
                    return

            self.lineEdit_exportDir.setText(export_dir)

        # 确保Export目录存在
        if not os.path.exists(export_dir):
            try:
                os.makedirs(export_dir)
                self._emit_log(f"📁 Create export dir: {export_dir}")
            except Exception as e:
                QMessageBox.critical(
                    self,
                    "Create Directory Failed",
                    f"Cannot create export directory.\n\nError msg:\n{e}"
                )
                return

        # 3. 获取Export格式
        export_tif = self.checkBox_exportTIF.isChecked()
        export_png = self.checkBox_exportPNG.isChecked()
        export_numpy = self.checkBox_exportNumpy.isChecked()

        if not (export_tif or export_png or export_numpy):
            QMessageBox.warning(
                self,
                "Export Format Not Selected",
                "Please select at least one export format (GeoTIFF, PNG, or NumPy)."
            )
            return

        # 4. 执行Export
        self._emit_log(f"📤 Start exporting results to: {export_dir}")

        try:
            image_path = self.last_inference_result.get('image_path', '')
            base_name = os.path.splitext(os.path.basename(image_path))[0] if image_path else 'result'
            mask = self.last_inference_result.get('mask')

            exported_files = []

            # Export GeoTIFF 格式（语义分割标准格式）
            if export_tif and mask is not None:
                tif_path = os.path.join(export_dir, f"{base_name}_pred.tif")
                try:
                    import rasterio
                    from rasterio.transform import from_bounds
                    # 尝试从原始图像复制地理信息
                    src_path = self.last_inference_result.get('image_path', '')
                    h, w = mask.shape[:2]
                    profile = {
                        'driver': 'GTiff',
                        'dtype': 'uint8',
                        'width': w,
                        'height': h,
                        'count': 1,
                        'compress': 'lzw',
                    }
                    if src_path and os.path.exists(src_path):
                        try:
                            with rasterio.open(src_path) as src:
                                profile['crs'] = src.crs
                                profile['transform'] = src.transform
                        except Exception:
                            pass
                    with rasterio.open(tif_path, 'w', **profile) as dst:
                        dst.write(mask.astype(np.uint8), 1)
                    exported_files.append(tif_path)
                    self._emit_log(f"✅ GeoTIFF exported: {os.path.basename(tif_path)}")
                except ImportError:
                    # rasterio 不可用时回退到 PIL
                    from PIL import Image
                    result_image = Image.fromarray(mask.astype(np.uint8))
                    tif_path = os.path.join(export_dir, f"{base_name}_pred.tif")
                    result_image.save(tif_path)
                    exported_files.append(tif_path)
                    self._emit_log(f"✅ TIFF exported (no geo info): {os.path.basename(tif_path)}")

            # Export PNG 格式
            if export_png and mask is not None:
                png_path = os.path.join(export_dir, f"{base_name}_pred.png")
                from PIL import Image
                result_image = Image.fromarray(mask.astype(np.uint8))
                result_image.save(png_path)
                exported_files.append(png_path)
                self._emit_log(f"✅ PNG exported: {os.path.basename(png_path)}")

            # Export NumPy 格式
            if export_numpy and mask is not None:
                npy_path = os.path.join(export_dir, f"{base_name}_pred.npy")
                np.save(npy_path, mask)
                exported_files.append(npy_path)
                self._emit_log(f"✅ NumPy exported: {os.path.basename(npy_path)}")

            # 5. 显示ExportSuccess消息
            if exported_files:
                files_list = '\n'.join([f"  • {os.path.basename(f)}" for f in exported_files])
                QMessageBox.information(
                    self,
                    "ExportSuccess",
                    f"推理结果已SuccessExport！\n\nExport目录:\n{export_dir}\n\nExported files:\n{files_list}"
                )
                self._emit_log(f"✅ Export complete, total {len(exported_files)} files")
            else:
                QMessageBox.warning(
                    self,
                    "Export失败",
                    "No data to export.\n\nNote: Tile mode doesn't generate full mask, cannot export PNG/NumPy."
                )

        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            self._emit_log(f"❌ Export failed: {e}")
            self._emit_log(f"Detailed error:\n{error_details}")
            QMessageBox.critical(
                self,
                "Export失败",
                f"Error occurred during export.\n\nError msg:\n{e}"
            )

    def get_inference_config(self) -> dict:
        """获取当前推理配置"""
        return {
            'config_file': self.lineEdit_configFile.text(),
            'checkpoint_file': self.lineEdit_checkpointFile.text(),
            'device': self.comboBox_device.currentText(),
            'inference_mode': 'batch' if self.radioButton_batchInference.isChecked() else 'single',
            'input_path': self.lineEdit_inputPath.text(),
            'strategy_mode': (
                'large_image_block' if self.radioButton_largeImageBlock.isChecked()
                else 'resize' if self.radioButton_resize.isChecked()
                else 'sliding_window'
            ),
            'crop_size': self.spinBox_cropSize.value(),
            'stride': self.spinBox_stride.value(),
            'overlap_rate': self.doubleSpinBox_overlapRate.value(),
            'batch_size': self.spinBox_batchSize.value(),
            'enable_tta': self.checkBox_enableTTA.isChecked(),
            'conf_threshold': self.doubleSpinBox_confThreshold.value(),
            'export_formats': {
                'tif': self.checkBox_exportTIF.isChecked(),
                'png': self.checkBox_exportPNG.isChecked(),
                'numpy': self.checkBox_exportNumpy.isChecked()
            },
            'export_dir': self.lineEdit_exportDir.text()
        }

    def is_model_loaded(self) -> bool:
        """检查模型是否已加载"""
        return self.inference_model is not None

    # ==================== 双向同步方法 ====================

    def is_single_image_mode(self) -> bool:
        """
        检查当前是否为Single Inference模式

        Returns:
            bool: True 表示Single Inference模式，False 表示Batch Inference模式
        """
        return self.radioButton_singleImage.isChecked()

    def set_image_path(self, path: str) -> None:
        """
        Settings推理输入图像路径（由外部调用，用于接收同步）

        用于从左侧 GIS 图层控制同步过来的路径。
        会抑制信号发送，防止循环同步。

        Args:
            path: 图像文件路径
        """
        if not path or not os.path.exists(path):
            self._emit_log(f"⚠️ Sync path invalid or not found: {path}")
            return

        # Settings标志位，防止信号循环
        self._suppress_sync = True

        try:
            # 直接Settings到输入影像框
            self.lineEdit_inputPath.setText(path)
            self._emit_log(f"📥 Synced input path from GIS layer: {os.path.basename(path)}")
        finally:
            self._suppress_sync = False

    def set_batch_dir(self, dir_path: str) -> None:
        """
        SettingsBatch Inference目录（由外部调用，用于接收同步）

        Args:
            dir_path: 目录路径
        """
        if not dir_path or not os.path.isdir(dir_path):
            return

        self._suppress_sync = True
        try:
            self.lineEdit_inputPath.setText(dir_path)
        finally:
            self._suppress_sync = False

    def get_current_input_path(self) -> str:
        """
        获取当前的输入路径

        Returns:
            str: 当前配置的输入路径（输入影像框中的路径）
        """
        return self.lineEdit_inputPath.text().strip()

    def _build_visualization_metadata(self, mask=None, result=None):
        """Normalize classes/palette so rendering still works with partial config metadata."""
        result = result or {}
        model_info = self.inference_model or {}

        classes = model_info.get('classes') or result.get('classes') or []
        palette = model_info.get('palette') or result.get('palette') or []

        normalized_classes = []
        for idx, name in enumerate(classes or []):
            normalized_classes.append(str(name) if name is not None else f"Class {idx}")

        mask_class_count = 0
        if mask is not None:
            mask_array = np.asarray(mask)
            if mask_array.size > 0:
                mask_class_count = int(mask_array.max()) + 1
        elif isinstance(result, dict):
            output_path = result.get('output_path', '')
            if output_path and os.path.exists(output_path):
                try:
                    stats = sample_band_stats(output_path, band=1, sample_size=512)
                    mask_class_count = int(stats.get('class_count') or 0)
                except Exception:
                    pass

        class_count = max(len(normalized_classes), len(palette or []), mask_class_count)
        if class_count <= 0:
            self.last_visualization_metadata = {'classes': [], 'palette': []}
            return [], []

        if not normalized_classes:
            normalized_classes = [f"Class {idx}" for idx in range(class_count)]
        elif len(normalized_classes) < class_count:
            normalized_classes.extend(
                f"Class {idx}" for idx in range(len(normalized_classes), class_count)
            )

        fallback_palette = MaskRenderer(num_classes=class_count).get_palette()
        normalized_palette = []
        for idx in range(class_count):
            if idx < len(palette or []) and isinstance(palette[idx], (list, tuple)) and len(palette[idx]) >= 3:
                normalized_palette.append(
                    [int(palette[idx][0]), int(palette[idx][1]), int(palette[idx][2])]
                )
            else:
                normalized_palette.append(list(fallback_palette[idx]))

        self.last_visualization_metadata = {
            'classes': normalized_classes,
            'palette': normalized_palette,
        }
        return normalized_classes, normalized_palette

    def _ensure_visualization_controls(self, mask=None, result=None):
        classes, palette = self._build_visualization_metadata(mask=mask, result=result)
        self.visualization_settings.set_classes_and_palette(classes, palette)
        return classes, palette

    def _get_active_visualization_metadata(self, mask=None, result=None):
        classes, palette = self._build_visualization_metadata(mask=mask, result=result)
        current_palette = self.visualization_settings.get_current_palette()
        if current_palette:
            palette = [
                list(current_palette.get(idx, palette[idx]))
                for idx in range(len(classes))
            ]
        return classes, palette

    # ==================== 可视化Settings回调方法 ====================

    def _on_palette_changed(self, palette: dict):
        """调色板变化回调"""
        self._emit_log(f"调色板已更新")
        # 实时重新渲染
        self._render_inference_result()

    def _on_alpha_changed(self, alpha: float):
        """透明度变化回调"""
        self._emit_log(f"Alpha adjusted: {int(alpha * 100)}%")
        # 实时重新渲染
        self._render_inference_result()

    def _render_inference_result(self):
        """渲染推理结果的可视化"""
        if not self.last_inference_result:
            return

        try:
            # 显示可视化组件
            self.visualization_settings.setVisible(True)
            self.visualization_widget.setVisible(True)

            result = self.last_inference_result.get('result', {})
            strategy = result.get('strategy', '')
            mask = self.last_inference_result.get('mask')
            classes, palette_list = self._get_active_visualization_metadata(mask=mask, result=result)
            current_alpha = self.visualization_settings.get_current_alpha()

            # 大图推理结果
            if strategy == 'large_image_block':
                output_path = result.get('output_path', '')
                image_path = self.last_inference_result.get('image_path', '')

                if output_path and os.path.exists(output_path):
                    self.visualization_widget.render_large_image(
                        image_path=image_path,
                        mask_path=output_path,
                        classes=classes,
                        palette=palette_list,
                        alpha=current_alpha
                    )

            # 小图推理结果
            else:
                image_path = self.last_inference_result.get('image_path', '')

                # 如果 last_inference_result 中有 image，直接使用；否则从文件读取
                image_array = self.last_inference_result.get('image')
                if image_array is None and image_path and os.path.exists(image_path):
                    try:
                        from PIL import Image
                        img = Image.open(image_path).convert('RGB')
                        image_array = np.array(img)
                    except Exception as e:
                        self._emit_log(f"⚠️  Read original image failed: {e}")

                if mask is not None and image_array is not None:
                    self.visualization_widget.render(
                        image=image_array,
                        mask=mask,
                        classes=classes,
                        palette=palette_list,
                        alpha=current_alpha
                    )
                else:
                    if mask is None:
                        self._emit_log("⚠️  Predict mask empty, cannot render")
                    if image_array is None:
                        self._emit_log("⚠️  Original image empty, cannot render")

        except Exception as e:
            self._emit_log(f"Visualization render failed: {e}")

    def _apply_visualization_settings(self):
        """应用可视化Settings到预览"""
        if not self.last_inference_result:
            QMessageBox.warning(
                self,
                "Cannot Apply",
                "No inference results available.\n\nPlease run inference before adjusting visualization settings."
            )
            return

        try:
            self._emit_log("Applying new visualization settings...")

            result = self.last_inference_result.get('result', {})
            strategy = result.get('strategy', '')
            mask = self.last_inference_result.get('mask')
            classes, palette_list = self._get_active_visualization_metadata(mask=mask, result=result)
            current_alpha = self.visualization_settings.get_current_alpha()

            # 大图推理结果
            if strategy == 'large_image_block':
                output_path = result.get('output_path', '')
                image_path = self.last_inference_result.get('image_path', '')

                if not output_path or not os.path.exists(output_path):
                    raise Exception("Cannot find large image tile result file")

                self._emit_log("Re-rendering large image...")
                self.visualization_widget.render_large_image(
                    image_path=image_path,
                    mask_path=output_path,
                    classes=classes,
                    palette=palette_list,
                    alpha=current_alpha
                )
                self._emit_log("Large image rendering complete")

            # 小图推理结果
            else:
                image_path = self.last_inference_result.get('image_path', '')

                # 如果 last_inference_result 中有 image，直接使用；否则从文件读取
                image_array = self.last_inference_result.get('image')
                if image_array is None and image_path and os.path.exists(image_path):
                    try:
                        from PIL import Image
                        img = Image.open(image_path).convert('RGB')
                        image_array = np.array(img)
                    except Exception as e:
                        self._emit_log(f"⚠️  Read original image failed: {e}")

                if mask is None or image_array is None:
                    if mask is None:
                        raise Exception("Inference mask incomplete")
                    if image_array is None:
                        raise Exception("Cannot read original image")

                self._emit_log("Re-rendering thumbnail...")
                self.visualization_widget.render(
                    image=image_array,
                    mask=mask,
                    classes=classes,
                    palette=palette_list,
                    alpha=current_alpha
                )
                self._emit_log("Small image rendering complete")

        except Exception as e:
            self._emit_log(f"Apply visualization settings failed: {e}")
            QMessageBox.critical(
                self,
                "Apply Failed",
                f"Error applying visualization settings.\n\nError msg:\n{e}"
            )

