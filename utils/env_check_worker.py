# -*- coding: utf-8 -*-
"""
EnvCheckWorker - 异步环境检测 Worker

将阻塞的 subprocess 探针调用移入 QThread，
避免在主线程执行时卡住 UI。

用法：
    worker = EnvCheckWorker(python_path, required_packages)
    worker.check_finished.connect(self._on_check_done)
    worker.start()
"""

import json
import os
import subprocess
from typing import List

from PySide6.QtCore import QThread, Signal


class EnvCheckWorker(QThread):
    """
    后台线程：探测指定 Python 解释器是否满足所需包依赖。

    Signals:
        check_started():            探测开始
        check_finished(dict):       探测完成，携带结构化结果
            结果格式:
            {
                "status":  "ready" | "incomplete" | "error",
                "details": {"python": "3.x", "torch": "2.x", ...},
                "msg":     str   # 仅 incomplete/error 时存在
            }
        check_failed(str):          探测过程中发生意外异常
    """

    check_started = Signal()
    check_finished = Signal(dict)
    check_failed = Signal(str)

    def __init__(
        self,
        python_path: str,
        required_packages: List[str],
        parent=None,
    ):
        super().__init__(parent)
        self._python_path = python_path
        self._required_packages = required_packages  # e.g. ["torch", "mmcv", "mmseg"]

    # ------------------------------------------------------------------
    # QThread 入口
    # ------------------------------------------------------------------

    def run(self):
        self.check_started.emit()
        try:
            result = self._probe(self._python_path, self._required_packages)
            self.check_finished.emit(result)
        except Exception as exc:
            self.check_failed.emit(str(exc))

    # ------------------------------------------------------------------
    # 内部探针逻辑
    # ------------------------------------------------------------------

    def _probe(self, python_path: str, packages: List[str]) -> dict:
        """在目标解释器中动态探测包版本与 CUDA 状态。"""
        if not python_path or not os.path.exists(python_path):
            return {
                "status": "error",
                "msg": f"Python 路径不存在: {python_path}",
            }

        probe_lines = [
            "import json, sys",
            "res = {'status': 'ready', 'details': {'python': sys.version.split()[0]}}",
        ]

        # 动态生成每个包的探测代码块
        for pkg in packages:
            probe_lines += [
                "try:",
                f"    import {pkg}",
                f"    res['details']['{pkg}'] = getattr({pkg}, '__version__', 'unknown')",
                "except Exception as _e:",
                "    res['status'] = 'incomplete'",
                "    res.setdefault('msg', '')",
                f"    res['msg'] += f'; {pkg} import failed: {{_e}}'",
            ]

        # torch 特殊处理：检测 CUDA
        if "torch" in packages:
            probe_lines += [
                "try:",
                "    import torch",
                "    res['details']['cuda'] = torch.cuda.is_available()",
                "except Exception:",
                "    res['details']['cuda'] = False",
            ]

        probe_lines.append("print(json.dumps(res, ensure_ascii=False))")
        probe_code = "\n".join(probe_lines)

        try:
            output = subprocess.check_output(
                [python_path, "-c", probe_code],
                text=True,
                timeout=15,
                stderr=subprocess.PIPE,  # 分离 stderr，避免 warning 污染 JSON
            )
            # 取最后一行非空内容作为 JSON（防止前面有 print/warning 输出）
            lines = [l for l in output.strip().splitlines() if l.strip()]
            if not lines:
                return {"status": "error", "msg": "探针无输出"}
            json_line = lines[-1]
            return json.loads(json_line)
        except subprocess.TimeoutExpired:
            return {"status": "error", "msg": "探针超时（>15s），解释器响应过慢"}
        except subprocess.CalledProcessError as exc:
            stderr_text = ""
            if exc.stderr:
                stderr_text = exc.stderr.strip()[:200]
            return {"status": "error", "msg": f"解释器执行失败: {stderr_text or exc.output or exc}"}
        except json.JSONDecodeError as exc:
            return {"status": "error", "msg": f"探针输出解析失败: {exc}. 原始输出: {output.strip()[:200]}"}
        except Exception as exc:
            return {"status": "error", "msg": f"探针异常: {exc}"}
