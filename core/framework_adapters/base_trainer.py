# -*- coding: utf-8 -*-
"""
训练器基础抽象类 (Base Trainer)

定义深度学习框架适配器的统一接口。
所有框架特定的训练器（如 MMSegTrainer）必须继承此类并实现全部抽象方法。

Phase 1.1 of Training Roadmap
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional


class BaseTrainer(ABC):
    """
    训练器抽象基类

    职责：
    - 统一不同深度学习框架的配置生成与训练启停接口
    - 定义日志解析协议，供 TrainingDispatcher 消费

    子类实现：
    - MMSegTrainer (MMSegmentation)
    - 未来可扩展: DeepLabTrainer, SegFormerTrainer 等
    """

    @abstractmethod
    def generate_config(
        self,
        ui_params: dict,
        advisor_params: dict,
        save_path: str
    ) -> str:
        """
        根据 UI 参数和 Advisor 推荐参数生成训练配置文件。

        Args:
            ui_params: 从 UI 收集的训练超参数，结构示例：
                {
                    'base_config': str,       # 基础配置文件路径
                    'max_iters': int,         # 最大迭代次数
                    'batch_size': int,        # 批大小
                    'lr': float,              # 学习率
                    'optimizer': str,         # 优化器类型 ('AdamW', 'SGD')
                    'weight_decay': float,    # 权重衰减
                    'lr_schedule': str,       # 学习率策略 ('PolyLR', 'StepLR')
                    'save_interval': int,     # 检查点保存间隔
                    'max_keep_ckpts': int,    # 最大保留检查点数
                    'pretrained': str | None, # 预训练权重路径
                }
            advisor_params: 从 ConfigAdvisor 获取的推荐参数，结构示例：
                {
                    'in_channels': int,       # 输入通道数
                    'crop_size': (int, int),   # 推荐裁剪大小
                    'class_weight': list,     # 类别权重列表
                    'loss_config': dict,      # 推荐损失函数配置
                    'augmentation': dict,     # 推荐数据增强配置
                }
            save_path: 生成的配置文件保存路径

        Returns:
            str: 实际保存的配置文件绝对路径

        Raises:
            FileNotFoundError: base_config 不存在时
            ValueError: 参数验证失败时
        """
        ...

    @abstractmethod
    def start_training(
        self,
        config_path: str,
        work_dir: str,
        python_path: Optional[str] = None,
    ) -> None:
        """
        启动训练子进程。

        此方法应为非阻塞调用，训练在子进程中执行。
        调用后可通过 is_running / get_process 与子进程交互。

        Args:
            config_path:  训练配置文件路径（由 generate_config 生成）
            work_dir:     训练工作目录（存放日志、检查点等）
            python_path:  指定 Python 解释器路径（conda 环境）。
                          为 None 时回退到 sys.executable（向后兼容）。

        Raises:
            FileNotFoundError: config_path 不存在时
            RuntimeError: 已有训练进程在运行时
        """
        ...

    @abstractmethod
    def stop_training(self) -> None:
        """
        安全停止当前训练进程。

        实现要求：
        1. 优先尝试优雅终止（SIGTERM）
        2. 等待超时后强制杀死（SIGKILL）
        3. 清理子进程资源
        """
        ...

    @abstractmethod
    def parse_log_line(self, line: str) -> Optional[Dict]:
        """
        解析训练日志的单行输出。

        将框架特定的日志格式解析为统一的字典结构，
        供 TrainingDispatcher 发送给 UI 图表和控制台。

        Args:
            line: 训练进程标准输出的一行文本

        Returns:
            解析成功时返回字典，无法解析时返回 None。
            字典结构（字段按需出现）：
            {
                'type': str,        # 'train_loss' | 'val_metric' | 'info'
                'iter': int,        # 当前迭代次数
                'max_iter': int,    # 最大迭代次数
                'loss': float,      # 训练损失
                'lr': float,        # 当前学习率
                'mIoU': float,      # 验证 mIoU
                'mAcc': float,      # 验证 mAcc
                'eta': str,         # 预计剩余时间
            }
        """
        ...

    @abstractmethod
    def is_running(self) -> bool:
        """
        检查训练进程是否正在运行。

        Returns:
            bool: True 表示训练进程正在运行
        """
        ...

    @abstractmethod
    def get_process(self):
        """
        获取底层训练子进程对象。

        Returns:
            subprocess.Popen 或 None
        """
        ...
