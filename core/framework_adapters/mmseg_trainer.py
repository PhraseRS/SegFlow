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
import json

from core.framework_adapters.base_trainer import BaseTrainer

HOOK_CODE = """
import os
import cv2
import random
import numpy as np
import json
from mmengine.registry import HOOKS
from mmengine.hooks import Hook

@HOOKS.register_module()
class LivePredictionHook(Hook):
    def __init__(self, num_val_samples=25):
        # 验证集样本总量的估算值，用于随机索引
        self.num_val_samples = num_val_samples
        self._target_idx = 0

    def before_val_epoch(self, runner):
        # 每次验证开始时随机挑一个样本的 batch_idx
        self._target_idx = random.randint(0, max(0, self.num_val_samples - 1))

    def after_val_iter(self, runner, batch_idx, data_batch=None, outputs=None):
        # 只处理本次随机抽到的那个 batch
        if batch_idx != self._target_idx:
            return
        
        try:
            if not outputs:
                return
                
            sample = outputs[0]
            img_path = getattr(sample, 'img_path', '')
            
            if not img_path:
                return

            iter_num = getattr(runner, 'iter', 0)
            pred_tensor = sample.pred_sem_seg.data[0].cpu().numpy()
            
            out_dir = os.path.join(runner.work_dir, 'live_predictions')
            os.makedirs(out_dir, exist_ok=True)
            
            safe_name = os.path.basename(img_path).rsplit('.', 1)[0]
            pred_path = os.path.join(out_dir, f"iter_{iter_num}_{safe_name}_pred.png")
            gt_path = os.path.join(out_dir, f"iter_{iter_num}_{safe_name}_gt.png")
            
            # Save raw prediction and gt masks
            cv2.imencode('.png', pred_tensor.astype(np.uint8))[1].tofile(pred_path)
            
            if hasattr(sample, 'gt_sem_seg'):
                gt_tensor = sample.gt_sem_seg.data[0].cpu().numpy()
                cv2.imencode('.png', gt_tensor.astype(np.uint8))[1].tofile(gt_path)
            
            # Use a strict JSON format for robust logging parsing
            msg = {
                "type": "live_prediction",
                "iter": iter_num,
                "img": img_path,
                "gt": gt_path,
                "pred": pred_path
            }
            print(f"[LIVE_PRED] {json.dumps(msg)}", flush=True)
        except Exception:
            pass
"""


def _detect_suffix(dir_path: str, default: str = '.jpg') -> str:
    """扫描目录下第一个文件的扩展名，无文件时返回 default。"""
    if not os.path.isdir(dir_path):
        return default
    for f in os.listdir(dir_path):
        _, ext = os.path.splitext(f)
        if ext:
            return ext.lower()
    return default


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
                
                # 优先读取用户在 UI 中设置的 val_interval，无设置时用保底公式
                val_interval = int(ui_params.get('val_interval') or 0) or max(50, int(max_iters) // 10)
                cfg.train_cfg.val_interval = val_interval

        # ====== 优化器 ======
        optimizer_type = ui_params.get('optimizer', 'AdamW')
        lr = ui_params.get('lr', 0.0001)
        weight_decay = ui_params.get('weight_decay', 0.01)
        momentum = ui_params.get('momentum', 0.9)

        if hasattr(cfg, 'optim_wrapper'):
            cfg.optim_wrapper.optimizer = dict(
                type=optimizer_type,
                lr=float(lr),
                weight_decay=float(weight_decay),
            )
            # 条件注入 momentum：仅 SGD/RMSprop
            if optimizer_type in ['SGD', 'RMSprop']:
                cfg.optim_wrapper.optimizer['momentum'] = float(momentum)

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
            elif lr_schedule == 'CosineAnnealingLR':
                cfg.param_scheduler = [
                    dict(type='CosineAnnealingLR', T_max=int(max_iters or 40000),
                         eta_min=0.0, begin=0, end=int(max_iters or 40000),
                         by_epoch=False)
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
                            # 使用自定义 Dataset 类而非 PascalVOCDataset，
                            # 避免 BaseSegDataset.get_label_map() 的 subset 校验冲突
                            obj['type'] = 'RSFreeVOCDataset'
                            # 统一背景 0 的减除行为，防止与 ADE20K 自带 pipeline 里的设定相斥
                            obj['reduce_zero_label'] = False
                            # 覆写文件后缀，防止遥感 .tif 数据被默认 .jpg 找不到
                            obj['img_suffix'] = ui_params.get('img_suffix') or _detect_suffix(
                                os.path.join(data_root, 'JPEGImages'))
                            obj['seg_map_suffix'] = ui_params.get('seg_map_suffix') or _detect_suffix(
                                os.path.join(data_root, 'SegmentationClass'), default='.png')
                            # 清除基底 config 可能残留的 metainfo 字段，
                            # 类别定义已写入 RSFreeVOCDataset.METAINFO，无需再传参数
                            obj.pop('metainfo', None)
                        
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

        # ====== num_classes 注入 ======
        num_classes = ui_params.get('num_classes')
        if num_classes:
            num_classes = int(num_classes)
            if hasattr(cfg, 'model'):
                if hasattr(cfg.model, 'decode_head'):
                    cfg.model.decode_head.num_classes = num_classes
                if hasattr(cfg.model, 'auxiliary_head'):
                    cfg.model.auxiliary_head.num_classes = num_classes

        # ====== 检查点 ======
        save_interval = ui_params.get('save_interval', 4000)
        max_keep_ckpts = ui_params.get('max_keep_ckpts', 3)
        if hasattr(cfg, 'default_hooks') and hasattr(cfg.default_hooks, 'checkpoint'):
            cfg.default_hooks.checkpoint.interval = int(save_interval)
            cfg.default_hooks.checkpoint.max_keep_ckpts = int(max_keep_ckpts)
            # save_best 注入
            if ui_params.get('save_best', True):
                cfg.default_hooks.checkpoint.save_best = 'mIoU'
                cfg.default_hooks.checkpoint.rule = 'greater'

        # ====== 预训练权重 ======
        pretrained = ui_params.get('pretrained')
        if pretrained and os.path.isfile(pretrained):
            if hasattr(cfg, 'model'):
                cfg.model.backbone.init_cfg = dict(
                    type='Pretrained', checkpoint=pretrained
                )

        # ====== 评价指标配置 ======
        # 统一注入核心评价指标（mIoU / mDice / mFscore）
        # mPrecision / mRecall / aAcc / mAcc 会在结果字典中自动附带
        # 参考: docs/3 3 配置文件的基础参数设置（与模型无关的参数）.md
        eval_metrics = dict(
            type='IoUMetric',
            iou_metrics=['mIoU', 'mDice', 'mFscore'],
        )
        cfg.val_evaluator = eval_metrics
        cfg.test_evaluator = eval_metrics

        # ====== resume ======
        # 从 work_dir 中最新 checkpoint 续训
        cfg.resume = bool(ui_params.get('resume', False))

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

        # ====== Live Prediction Custom Hook + RSFreeVOCDataset ======
        work_dir = os.path.dirname(save_path)
        os.makedirs(work_dir, exist_ok=True)
        hook_file = os.path.join(work_dir, 'custom_live_pred_hook.py')
        custom_imports_list = []
        try:
            with open(hook_file, 'w', encoding='utf-8') as f:
                f.write(HOOK_CODE)
            custom_imports_list.append('custom_live_pred_hook')
        except Exception as e:
            print(f"Warning: Failed to write live prediction hook: {e}")

        # 生成自定义 Dataset 文件（支持任意类别，读取 VOC 文件树）
        class_names = ui_params.get('class_names') or []
        palette = ui_params.get('palette') or []
        if not class_names:
            num_cls = int(ui_params.get('num_classes') or 2)
            class_names = [f'class_{i}' for i in range(num_cls)]
        if len(palette) != len(class_names):
            _default_pal = [
                (0,0,0),(128,0,0),(0,128,0),(128,128,0),(0,0,128),
                (128,0,128),(0,128,128),(128,128,128),(64,0,0),(192,0,0),
            ]
            palette = [_default_pal[i % len(_default_pal)] for i in range(len(class_names))]
        try:
            self._write_custom_dataset_file(work_dir, class_names, palette)
            custom_imports_list.append('custom_rs_dataset')
        except Exception as e:
            print(f"Warning: Failed to write custom dataset file: {e}")

        if custom_imports_list:
            cfg.custom_imports = dict(imports=custom_imports_list, allow_failed_imports=False)

        # 追加 LivePredictionHook（仅当 hook 文件写入成功时）
        if 'custom_live_pred_hook' in custom_imports_list:
            new_hook = dict(type='LivePredictionHook', num_val_samples=25)
            if hasattr(cfg, 'custom_hooks'):
                if isinstance(cfg.custom_hooks, list):
                    cfg.custom_hooks.append(new_hook)
                else:
                    cfg.custom_hooks = [cfg.custom_hooks, new_hook]
            else:
                cfg.custom_hooks = [new_hook]

        # ====== 保存 ======
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

    def start_training(
        self,
        config_path: str,
        work_dir: str,
        python_path: Optional[str] = None,
    ) -> None:
        """
        使用 subprocess.Popen 启动 MMSeg 训练。

        Args:
            config_path:  训练配置文件路径
            work_dir:     训练工作目录
            python_path:  指定 Python 解释器（conda 环境）。
                          为 None 时回退到 sys.executable。
        """
        if self.is_running():
            raise RuntimeError("训练进程已在运行，请先停止当前训练")

        if not os.path.isfile(config_path):
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        os.makedirs(work_dir, exist_ok=True)
        self._config_path = config_path
        self._work_dir = work_dir

        # 确定使用的 Python 解释器
        interpreter = python_path if (python_path and os.path.isfile(python_path)) else sys.executable
        if python_path and not os.path.isfile(python_path):
            print(f"[Warning] 指定的 python_path 不存在: {python_path}，回退到 sys.executable")

        # 动态寻找 mmsegmentation 的 train.py 文件
        # 使用目标解释器探测 mmseg 安装位置，而非当前进程的 mmseg
        train_script = self._find_train_script(interpreter)

        cmd = [
            interpreter, '-u', train_script,
            config_path,
            '--work-dir', work_dir,
        ]

        env = os.environ.copy()
        current_pythonpath = env.get('PYTHONPATH', '')
        env['PYTHONPATH'] = (
            f"{os.path.abspath(work_dir)}{os.pathsep}{current_pythonpath}"
            if current_pythonpath
            else os.path.abspath(work_dir)
        )

        self._process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # 合并 stderr 到 stdout
            text=True,
            bufsize=1,  # 行缓冲
            encoding='utf-8',
            errors='replace',
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0,
        )

    def _write_custom_dataset_file(self, work_dir: str, class_names: list, palette: list) -> None:
        """
        在 work_dir 下生成 custom_rs_dataset.py。
        定义 RSFreeVOCDataset：继承 BaseSegDataset（非 PascalVOCDataset），
        类级 METAINFO 写入用户类别，彻底绕开 get_label_map() 的 subset 校验。
        支持 VOC 文件树（JPEGImages/ + SegmentationClass/ + ImageSets/）。
        """
        classes_repr = repr(tuple(class_names))
        palette_repr = repr([list(c) for c in palette])
        code = (
            "# 自动生成 — 由 RS-Seg-GUI 生成，请勿手动修改\n"
            "from mmseg.datasets.basesegdataset import BaseSegDataset\n"
            "from mmseg.registry import DATASETS\n\n"
            "@DATASETS.register_module()\n"
            "class RSFreeVOCDataset(BaseSegDataset):\n"
            f"    METAINFO = dict(classes={classes_repr}, palette={palette_repr})\n\n"
            "    def __init__(self, img_suffix='.jpg', seg_map_suffix='.png',\n"
            "                 reduce_zero_label=False, **kwargs):\n"
            "        super().__init__(img_suffix=img_suffix,\n"
            "                         seg_map_suffix=seg_map_suffix,\n"
            "                         reduce_zero_label=reduce_zero_label,\n"
            "                         **kwargs)\n"
        )
        out_path = os.path.join(work_dir, 'custom_rs_dataset.py')
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(code)

    def _find_train_script(self, interpreter: str) -> str:
        """
        在目标解释器的环境中查找 mmseg train.py。

        优先顺序：
        1. 通过目标解释器探测 mmseg 安装路径（支持 conda 环境）
        2. 当前进程的 mmseg 安装路径（回退）
        """
        # 方式1：用目标解释器探测（适用于 conda 环境与当前进程不同的情况）
        try:
            probe = subprocess.check_output(
                [interpreter, '-c',
                 'import mmseg, os; print(os.path.dirname(mmseg.__file__))'],
                text=True, timeout=10, stderr=subprocess.DEVNULL,
            ).strip()
            if probe:
                # mim 安装方式
                candidate = os.path.join(probe, '.mim', 'tools', 'train.py')
                if os.path.isfile(candidate):
                    return candidate
                # 源码安装方式
                candidate = os.path.join(os.path.dirname(probe), 'tools', 'train.py')
                if os.path.isfile(candidate):
                    return candidate
        except Exception:
            pass

        # 方式2：当前进程的 mmseg（回退）
        try:
            import mmseg
            mmseg_dir = os.path.dirname(mmseg.__file__)
            candidate = os.path.join(mmseg_dir, '.mim', 'tools', 'train.py')
            if os.path.isfile(candidate):
                return candidate
            candidate = os.path.join(os.path.dirname(mmseg_dir), 'tools', 'train.py')
            if os.path.isfile(candidate):
                return candidate
        except ImportError:
            pass

        raise FileNotFoundError(
            "找不到 MMSeg 训练脚本(train.py)。"
            "请确保已在目标 conda 环境中正确安装 mmsegmentation。"
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
        
        if "[LIVE_PRED]" in line:
            try:
                json_str = line.split("[LIVE_PRED]", 1)[1].strip()
                return json.loads(json_str)
            except Exception:
                pass

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
