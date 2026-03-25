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
        r'Iter\(train\)\s*\[\s*(\d+)/(\d+)\]'     # iter / max_iter (added \s* for MMEngine formatting)
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
                
                # 智能计算验证间隔: 保证整个训练周期内至少采点 10 次，形成动态平滑验证曲线
                val_interval = max(50, int(max_iters) // 10)
                cfg.train_cfg.val_interval = val_interval

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
        
        # 必须同时修改验证集和测试集的线程数，否则在进入 val_loop 时会瞬间启动多个废弃子进程把系统内存撑爆
        if hasattr(cfg, 'val_dataloader'):
            cfg.val_dataloader.num_workers = int(num_workers)
            # 验证集通常不应该开多 batch 容易 OOM，可以固定为 1 或者随之修改
            cfg.val_dataloader.batch_size = max(1, int(batch_size) // 2)
            
        if hasattr(cfg, 'test_dataloader'):
            cfg.test_dataloader.num_workers = int(num_workers)

        # ====== 数据集路径 ======
        data_root = ui_params.get('data_root')
        if data_root:
            data_root = data_root.replace('\\', '/')
            if hasattr(cfg, 'data_root'):
                cfg.data_root = data_root
            
            def process_segmentation_split(obj, default_ann):
                if isinstance(obj, dict):
                    if 'data_root' in obj:
                        obj['data_root'] = data_root
                    
                    # === 强制修正 VOC 格式的子目录，防止基底配置 (如 ADE20k) 的自带路径引发 FolderNotFound ===
                    if 'data_prefix' in obj:
                        obj['data_prefix'] = dict(
                            img_path='JPEGImages',
                            seg_map_path='SegmentationClass'
                        )
                        # 核心修复：把源配置如 `ADE20KDataset` 强行变成 VOC 格式读取器，免得它看不懂 train.txt
                        if 'type' in obj:
                            obj['type'] = 'PascalVOCDataset'
                            # 统一背景 0 的减除行为，防止与 ADE20K 自带 pipeline 里的设定相斥
                            obj['reduce_zero_label'] = False
                        
                        # 兼容强转 Dataset 类型后带来的必填项缺失问题
                        if 'ann_file' not in obj or not obj['ann_file']:
                            obj['ann_file'] = default_ann
                            
                    # 同步清洗 Pipeline 里的毒瘤参数 (尤其是 ADE20K 喜欢自带的 reduce_zero_label=True)
                    if obj.get('type') == 'LoadAnnotations':
                        obj['reduce_zero_label'] = False
                            
                    # 兼容可能存在的 aug.txt 级联数据
                    if 'ann_file' in obj and 'aug.txt' in obj['ann_file']:
                        obj['ann_file'] = 'ImageSets/Segmentation/train.txt'

                    for k, v in obj.items():
                        process_segmentation_split(v, default_ann)
                elif isinstance(obj, list):
                    for item in obj:
                        process_segmentation_split(item, default_ann)
                            
            # 分别对 train, val, test 树进行独立的深度递归注射，赋予正确的 ann_file
            if hasattr(cfg, 'train_dataloader'):
                process_segmentation_split(cfg.train_dataloader, 'ImageSets/Segmentation/train.txt')
            if hasattr(cfg, 'val_dataloader'):
                process_segmentation_split(cfg.val_dataloader, 'ImageSets/Segmentation/val.txt')
            if hasattr(cfg, 'test_dataloader'):
                process_segmentation_split(cfg.test_dataloader, 'ImageSets/Segmentation/test.txt')

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
        
        # --- 硬核补丁：绕过 MMEngine 底层 AST 锁死机制，直接对落盘文件进行文本替换 ---
        data_root = ui_params.get('data_root')
        if data_root:
            data_root = data_root.replace('\\', '/')
            try:
                with open(save_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                # 替换 MMEngine 顽固保留的 './data' 为真实的绝对路径
                content = content.replace("'./data'", f"'{data_root}'")
                content = content.replace('"./data"', f"'{data_root}'")
                with open(save_path, 'w', encoding='utf-8') as f:
                    f.write(content)
            except Exception as e:
                print(f"[Warning] Post-processing config dump failed: {e}")

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

        # 动态寻找 mmsegmentation 的 train.py 文件
        import mmseg
        mmseg_dir = os.path.dirname(mmseg.__file__)
        
        # 常见安装方式: 通过 mim 安装会在 .mim/tools 下
        train_script = os.path.join(mmseg_dir, '.mim', 'tools', 'train.py')
        
        if not os.path.isfile(train_script):
            # 常见安装方式: 源码安装 (pip install -e .)
            train_script = os.path.join(os.path.dirname(mmseg_dir), 'tools', 'train.py')
            
        if not os.path.isfile(train_script):
            raise FileNotFoundError(f"找不到 MMSeg 训练脚本(train.py)。请确保已正确安装 mmsegmentation。尝试的位置: {train_script}")

        cmd = [
            sys.executable, '-u', train_script,
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
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
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
