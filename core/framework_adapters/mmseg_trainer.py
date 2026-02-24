# -*- coding: utf-8 -*-
"""
MMSegmentation 训练适配器 (MMSeg Trainer)

实现 BaseTrainer 接口，封装 MMSegmentation 框架的配置生成与训练执行。

Phase 1.2 of Training Roadmap
"""

import os
import re
import signal
import subprocess
import sys
import time
from typing import Dict, Optional

from core.framework_adapters.base_trainer import BaseTrainer


class MMSegTrainer(BaseTrainer):
    """
    MMSegmentation 框架训练适配器

    职责：
    - 使用 mmengine.Config 生成/修改训练配置
    - 通过 subprocess.Popen 管理训练子进程
    - 解析 MMSeg 标准日志输出
    """

    # 日志解析正则（匹配 MMSeg 2.x / MMEngine 格式）
    # 示例: "2024/01/01 12:00:00 - mmengine - INFO - Iter(train) [100/40000]  lr: 1.0000e-02  loss: 0.1234"
    _RE_TRAIN_LOG = re.compile(
        r'Iter\(train\)\s*\[(\d+)/(\d+)\]'     # iter / max_iter
        r'.*?lr:\s*([\d.eE+-]+)'                # learning rate
        r'.*?loss:\s*([\d.]+)'                   # loss
    )

    # 验证指标日志
    # 示例: "2024/01/01 12:00:00 - mmengine - INFO - Iter(val) [100/40000]  mIoU: 0.5678  mAcc: 0.7890"
    _RE_VAL_LOG = re.compile(
        r'mIoU:\s*([\d.]+)'
    )
    _RE_VAL_ACC = re.compile(
        r'mAcc:\s*([\d.]+)'
    )

    # ETA 日志
    # 示例: "eta: 1:23:45"
    _RE_ETA = re.compile(
        r'eta:\s*([\d:]+)'
    )

    def __init__(self):
        self._process: Optional[subprocess.Popen] = None
        self._config_path: Optional[str] = None
        self._work_dir: Optional[str] = None

    def generate_config(
        self,
        ui_params: dict,
        advisor_params: dict,
        save_path: str
    ) -> str:
        """
        使用 mmengine.Config 加载 base_config，
        根据 ui_params 和 advisor_params 覆盖字段后保存。
        """
        try:
            from mmengine.config import Config
        except ImportError:
            raise ImportError(
                "mmengine 未安装。请运行: pip install mmengine"
            )

        base_config = ui_params.get('base_config', '')
        if not base_config or not os.path.isfile(base_config):
            raise FileNotFoundError(
                f"基础配置文件不存在: {base_config}"
            )

        cfg = Config.fromfile(base_config)

        # ====== 训练策略 ======
        max_iters = ui_params.get('max_iters')
        if max_iters is not None:
            # MMSeg 2.x 使用 train_cfg
            if hasattr(cfg, 'train_cfg'):
                cfg.train_cfg.max_iters = int(max_iters)
                cfg.train_cfg.type = 'IterBasedTrainLoop'

        # ====== 优化器 ======
        optimizer_type = ui_params.get('optimizer', 'AdamW')
        lr = ui_params.get('lr', 0.0001)
        weight_decay = ui_params.get('weight_decay', 0.01)

        if hasattr(cfg, 'optim_wrapper'):
            cfg.optim_wrapper.optimizer = dict(
                type=optimizer_type,
                lr=float(lr),
                weight_decay=float(weight_decay),
            )
            # SGD 需要 momentum
            if optimizer_type == 'SGD':
                cfg.optim_wrapper.optimizer['momentum'] = 0.9

        # ====== 学习率策略 ======
        lr_schedule = ui_params.get('lr_schedule', 'PolyLR')
        if hasattr(cfg, 'param_scheduler'):
            if lr_schedule == 'PolyLR':
                cfg.param_scheduler = [
                    dict(type='PolyLR', power=0.9, begin=0,
                         end=int(max_iters or 40000), by_epoch=False)
                ]
            elif lr_schedule == 'StepLR':
                cfg.param_scheduler = [
                    dict(type='StepLR', step_size=int((max_iters or 40000) // 3),
                         gamma=0.1, by_epoch=False)
                ]

        # ====== 数据加载器 ======
        batch_size = ui_params.get('batch_size', 2)
        num_workers = ui_params.get('num_workers', 4)
        if hasattr(cfg, 'train_dataloader'):
            cfg.train_dataloader.batch_size = int(batch_size)
            cfg.train_dataloader.num_workers = int(num_workers)

        # ====== 检查点 ======
        save_interval = ui_params.get('save_interval', 4000)
        max_keep_ckpts = ui_params.get('max_keep_ckpts', 3)
        if hasattr(cfg, 'default_hooks') and hasattr(cfg.default_hooks, 'checkpoint'):
            cfg.default_hooks.checkpoint.interval = int(save_interval)
            cfg.default_hooks.checkpoint.max_keep_ckpts = int(max_keep_ckpts)

        # ====== 预训练权重 ======
        pretrained = ui_params.get('pretrained')
        if pretrained and os.path.isfile(pretrained):
            if hasattr(cfg, 'model'):
                cfg.model.backbone.init_cfg = dict(
                    type='Pretrained', checkpoint=pretrained
                )

        # ====== Advisor 推荐参数 ======
        if advisor_params:
            # 输入通道数
            in_channels = advisor_params.get('in_channels')
            if in_channels and in_channels != 3 and hasattr(cfg, 'model'):
                cfg.model.backbone.in_channels = int(in_channels)

            # 裁剪大小
            crop_size = advisor_params.get('crop_size')
            if crop_size:
                cfg.crop_size = tuple(crop_size)
                # 更新 pipeline 中的 RandomCrop
                if hasattr(cfg, 'train_pipeline'):
                    for transform in cfg.train_pipeline:
                        if isinstance(transform, dict) and transform.get('type') == 'RandomCrop':
                            transform['crop_size'] = tuple(crop_size)

            # 损失函数
            loss_config = advisor_params.get('loss_config')
            if loss_config and hasattr(cfg, 'model'):
                # 去除内部标记字段
                clean_loss = {k: v for k, v in loss_config.items()
                              if not k.startswith('_')}
                if hasattr(cfg.model, 'decode_head'):
                    cfg.model.decode_head.loss_decode = clean_loss

        # ====== 保存 ======
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        cfg.dump(save_path)

        self._config_path = save_path
        return os.path.abspath(save_path)

    def start_training(self, config_path: str, work_dir: str) -> None:
        """
        使用 subprocess.Popen 启动 MMSeg 训练。
        """
        if self.is_running():
            raise RuntimeError("训练进程已在运行，请先停止当前训练")

        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        os.makedirs(work_dir, exist_ok=True)
        self._config_path = config_path
        self._work_dir = work_dir

        # 构建命令: python -m mmseg.tools.train <config> --work-dir <dir>
        # 同时兼容 tools/train.py 方式
        cmd = [
            sys.executable, '-m', 'mmseg.tools.train',
            config_path,
            '--work-dir', work_dir,
        ]

        self._process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
            text=True,
            bufsize=1,  # 行缓冲
            encoding='utf-8',
            errors='replace',
            creationflags=(
                subprocess.CREATE_NEW_PROCESS_GROUP
                if sys.platform == 'win32' else 0
            ),
        )

    def stop_training(self) -> None:
        """
        安全停止训练进程：先 SIGTERM，超时 5s 后 SIGKILL。
        """
        if self._process is None:
            return

        if self._process.poll() is not None:
            # 进程已经结束
            self._process = None
            return

        try:
            if sys.platform == 'win32':
                # Windows: 发送 CTRL_BREAK_EVENT
                self._process.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                self._process.terminate()  # SIGTERM

            # 等待优雅退出
            try:
                self._process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._process.kill()  # SIGKILL
                self._process.wait(timeout=3)
        except (OSError, ProcessLookupError):
            pass  # 进程已退出
        finally:
            self._process = None

    def parse_log_line(self, line: str) -> Optional[Dict]:
        """
        解析 MMSeg / mmengine 格式日志行。
        """
        if not line or not line.strip():
            return None

        line = line.strip()

        # 尝试匹配训练日志
        train_match = self._RE_TRAIN_LOG.search(line)
        if train_match:
            result = {
                'type': 'train_loss',
                'iter': int(train_match.group(1)),
                'max_iter': int(train_match.group(2)),
                'lr': float(train_match.group(3)),
                'loss': float(train_match.group(4)),
            }
            # 尝试提取 ETA
            eta_match = self._RE_ETA.search(line)
            if eta_match:
                result['eta'] = eta_match.group(1)
            return result

        # 尝试匹配验证日志
        val_match = self._RE_VAL_LOG.search(line)
        if val_match:
            result = {
                'type': 'val_metric',
                'mIoU': float(val_match.group(1)),
            }
            acc_match = self._RE_VAL_ACC.search(line)
            if acc_match:
                result['mAcc'] = float(acc_match.group(1))
            return result

        return None

    def is_running(self) -> bool:
        """检查训练子进程是否正在运行。"""
        if self._process is None:
            return False
        return self._process.poll() is None

    def get_process(self) -> Optional[subprocess.Popen]:
        """获取底层训练子进程对象。"""
        return self._process
