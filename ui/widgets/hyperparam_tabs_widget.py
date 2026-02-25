# -*- coding: utf-8 -*-
"""
训练超参数组件 (Hyperparameter Tabs Widget)

多 Tab 设计，覆盖常规参数、优化器、检查点、数据增强。

Training Roadmap Phase 3, Task 3.3
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QTabWidget,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QLabel, QFrame
)
from PySide6.QtCore import Signal


class HyperparamTabsWidget(QWidget):
    """
    训练超参数多 Tab 组件

    Tab 1 "常规参数": Batch Size, Max Iters, Num Workers
    Tab 2 "优化器": Optimizer, LR, Weight Decay, LR Schedule
    Tab 3 "检查点": Save Interval, Max Keep Checkpoints
    Tab 4 "数据增强": RandomFlip, PhotoMetricDistortion 等开关

    Signals:
        config_changed(): 任何配置项变更时触发
    """

    config_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        self._create_tab_general()
        self._create_tab_optimizer()
        self._create_tab_checkpoint()
        self._create_tab_augmentation()

    def _create_tab_general(self):
        """Tab 1: 常规参数"""
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        self.spin_batch_size = QSpinBox()
        self.spin_batch_size.setRange(1, 64)
        self.spin_batch_size.setValue(2)
        self.spin_batch_size.setToolTip("每批训练样本数，受 GPU 显存限制")
        form.addRow("Batch Size:", self.spin_batch_size)

        self.spin_max_iters = QSpinBox()
        self.spin_max_iters.setRange(1000, 500000)
        self.spin_max_iters.setSingleStep(1000)
        self.spin_max_iters.setValue(40000)
        self.spin_max_iters.setToolTip("最大训练迭代次数")
        form.addRow("Max Iters:", self.spin_max_iters)

        self.spin_num_workers = QSpinBox()
        self.spin_num_workers.setRange(0, 16)
        self.spin_num_workers.setValue(4)
        self.spin_num_workers.setToolTip("数据加载并行线程数（0 = 主线程加载）")
        form.addRow("Num Workers:", self.spin_num_workers)

        self.spin_val_interval = QSpinBox()
        self.spin_val_interval.setRange(100, 50000)
        self.spin_val_interval.setSingleStep(500)
        self.spin_val_interval.setValue(4000)
        self.spin_val_interval.setToolTip("每 N 次迭代运行一次验证")
        form.addRow("验证间隔:", self.spin_val_interval)

        self.tabs.addTab(tab, "常规参数")

    def _create_tab_optimizer(self):
        """Tab 2: 优化器"""
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        self.combo_optimizer = QComboBox()
        self.combo_optimizer.addItems(['AdamW', 'SGD', 'Adam', 'RAdam'])
        self.combo_optimizer.setToolTip("优化器类型")
        form.addRow("优化器:", self.combo_optimizer)

        self.dspin_lr = QDoubleSpinBox()
        self.dspin_lr.setRange(1e-7, 1.0)
        self.dspin_lr.setDecimals(6)
        self.dspin_lr.setSingleStep(0.0001)
        self.dspin_lr.setValue(0.0001)
        self.dspin_lr.setToolTip("初始学习率")
        form.addRow("学习率 (LR):", self.dspin_lr)

        self.dspin_weight_decay = QDoubleSpinBox()
        self.dspin_weight_decay.setRange(0.0, 1.0)
        self.dspin_weight_decay.setDecimals(5)
        self.dspin_weight_decay.setSingleStep(0.001)
        self.dspin_weight_decay.setValue(0.01)
        self.dspin_weight_decay.setToolTip("权重衰减（L2 正则化）")
        form.addRow("Weight Decay:", self.dspin_weight_decay)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form.addRow(line)

        self.combo_lr_schedule = QComboBox()
        self.combo_lr_schedule.addItems(['PolyLR', 'StepLR', 'CosineAnnealingLR'])
        self.combo_lr_schedule.setToolTip("学习率衰减策略")
        form.addRow("LR 衰减策略:", self.combo_lr_schedule)

        self.tabs.addTab(tab, "优化器")

    def _create_tab_checkpoint(self):
        """Tab 3: 检查点"""
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        self.spin_save_interval = QSpinBox()
        self.spin_save_interval.setRange(100, 50000)
        self.spin_save_interval.setSingleStep(500)
        self.spin_save_interval.setValue(4000)
        self.spin_save_interval.setToolTip("每 N 次迭代保存一次检查点")
        form.addRow("保存间隔:", self.spin_save_interval)

        self.spin_max_keep = QSpinBox()
        self.spin_max_keep.setRange(1, 50)
        self.spin_max_keep.setValue(3)
        self.spin_max_keep.setToolTip("保留最近的几个检查点文件")
        form.addRow("最大保留数:", self.spin_max_keep)

        self.check_save_best = QCheckBox("保存最佳模型 (Best mIoU)")
        self.check_save_best.setChecked(True)
        form.addRow(self.check_save_best)

        self.tabs.addTab(tab, "检查点")

    def _create_tab_augmentation(self):
        """Tab 4: 数据增强"""
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        self.check_random_flip = QCheckBox("RandomFlip (水平翻转)")
        self.check_random_flip.setChecked(True)
        form.addRow(self.check_random_flip)

        self.check_photo_distortion = QCheckBox("PhotoMetricDistortion (光度扰动)")
        self.check_photo_distortion.setChecked(True)
        form.addRow(self.check_photo_distortion)

        self.check_random_rotate = QCheckBox("RandomRotate (随机旋转)")
        self.check_random_rotate.setChecked(False)
        form.addRow(self.check_random_rotate)

        self.check_random_scale = QCheckBox("MultiScaleFlipAug (多尺度)")
        self.check_random_scale.setChecked(False)
        form.addRow(self.check_random_scale)

        note = QLabel("💡 更多增强由 ConfigAdvisor 根据数据特征自动推荐")
        note.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        note.setWordWrap(True)
        form.addRow(note)

        self.tabs.addTab(tab, "数据增强")

    def _connect_signals(self):
        """连接所有控件变更信号"""
        # 常规
        self.spin_batch_size.valueChanged.connect(lambda: self.config_changed.emit())
        self.spin_max_iters.valueChanged.connect(lambda: self.config_changed.emit())
        self.spin_num_workers.valueChanged.connect(lambda: self.config_changed.emit())
        self.spin_val_interval.valueChanged.connect(lambda: self.config_changed.emit())
        # 优化器
        self.combo_optimizer.currentTextChanged.connect(lambda: self.config_changed.emit())
        self.dspin_lr.valueChanged.connect(lambda: self.config_changed.emit())
        self.dspin_weight_decay.valueChanged.connect(lambda: self.config_changed.emit())
        self.combo_lr_schedule.currentTextChanged.connect(lambda: self.config_changed.emit())
        # 检查点
        self.spin_save_interval.valueChanged.connect(lambda: self.config_changed.emit())
        self.spin_max_keep.valueChanged.connect(lambda: self.config_changed.emit())
        self.check_save_best.toggled.connect(lambda: self.config_changed.emit())

    def get_params(self) -> dict:
        """
        收集所有超参数。

        Returns:
            dict: 包含全部超参数的字典
        """
        return {
            # 常规
            'batch_size': self.spin_batch_size.value(),
            'max_iters': self.spin_max_iters.value(),
            'num_workers': self.spin_num_workers.value(),
            'val_interval': self.spin_val_interval.value(),
            # 优化器
            'optimizer': self.combo_optimizer.currentText(),
            'lr': self.dspin_lr.value(),
            'weight_decay': self.dspin_weight_decay.value(),
            'lr_schedule': self.combo_lr_schedule.currentText(),
            # 检查点
            'save_interval': self.spin_save_interval.value(),
            'max_keep_ckpts': self.spin_max_keep.value(),
            'save_best': self.check_save_best.isChecked(),
            # 数据增强
            'aug_random_flip': self.check_random_flip.isChecked(),
            'aug_photo_distortion': self.check_photo_distortion.isChecked(),
            'aug_random_rotate': self.check_random_rotate.isChecked(),
            'aug_multi_scale': self.check_random_scale.isChecked(),
        }
