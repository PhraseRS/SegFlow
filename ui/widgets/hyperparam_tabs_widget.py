# -*- coding: utf-8 -*-
"""
训练超参数组件 (Hyperparameter Tabs Widget)

多 Tab 设计，覆盖常规参数、优化器、检查点、数据增强。
已集成推荐支持（💡/✅ 图标及蓝/橙颜色标注）。

Training Roadmap Phase 3, Task 3.3
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QTabWidget,
    QSpinBox, QDoubleSpinBox, QComboBox, QCheckBox,
    QLabel, QFrame, QHBoxLayout, QToolButton
)
from PySide6.QtCore import Signal, Qt


class HyperparamTabsWidget(QWidget):
    """
    训练超参数多 Tab 组件
    """

    config_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        
        # 推荐支持系统
        self._rec_btns = {}
        self._rec_widgets = {}
        self._rec_values = {}
        self._rec_reasons = {}
        self._rec_applied = {}
        
        self.COLOR_RECOMMENDED = "#1565C0"
        self.COLOR_OVERRIDDEN = "#E65100"
        self.COLOR_DEFAULT = ""
        
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

    def _add_rec_row(self, form, label_text: str, widget: QWidget, param_key: str):
        """为输入控件添加原生推荐按钮支持"""
        btn = QToolButton()
        btn.setFixedSize(22, 22)
        btn.setStyleSheet("QToolButton { border: none; background: transparent; font-size: 14px; }")
        btn.setVisible(False)
        btn.setCursor(Qt.PointingHandCursor)
        
        self._rec_btns[param_key] = btn
        self._rec_widgets[param_key] = widget
        self._rec_applied[param_key] = False
        
        btn.clicked.connect(lambda _, k=param_key: self._apply_single_recommendation(k))
        
        # 监听值改变以应用颜色
        if hasattr(widget, 'valueChanged'):
            widget.valueChanged.connect(lambda *args, k=param_key: self._on_widget_value_changed(k))
        elif hasattr(widget, 'currentTextChanged'):
            widget.currentTextChanged.connect(lambda *args, k=param_key: self._on_widget_value_changed(k))
        elif hasattr(widget, 'toggled'):
            widget.toggled.connect(lambda *args, k=param_key: self._on_widget_value_changed(k))
            
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(widget, 1)
        row.addWidget(btn)
        
        if label_text:
            form.addRow(label_text, row)
        else:
            form.addRow(row)

    def _create_tab_general(self):
        """Tab 1: 常规参数"""
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        self.spin_in_channels = QSpinBox()
        self.spin_in_channels.setRange(1, 256)
        self.spin_in_channels.setValue(3)
        self.spin_in_channels.setToolTip("输入影像通道数 (RGB图像通常为3)")
        self._add_rec_row(form, "输入通道数:", self.spin_in_channels, "in_channels")

        self.spin_crop_size = QSpinBox()
        self.spin_crop_size.setRange(16, 4096)
        self.spin_crop_size.setSingleStep(32)
        self.spin_crop_size.setValue(512)
        self.spin_crop_size.setToolTip("训练时的随机裁剪尺寸")
        self._add_rec_row(form, "裁剪尺寸:", self.spin_crop_size, "crop_size")

        self.spin_batch_size = QSpinBox()
        self.spin_batch_size.setRange(1, 64)
        self.spin_batch_size.setValue(2)
        self.spin_batch_size.setToolTip("每批训练样本数，受 GPU 显存限制")
        self._add_rec_row(form, "Batch Size:", self.spin_batch_size, "batch_size")

        self.spin_max_iters = QSpinBox()
        self.spin_max_iters.setRange(1000, 500000)
        self.spin_max_iters.setSingleStep(1000)
        self.spin_max_iters.setValue(40000)
        self.spin_max_iters.setToolTip("最大训练迭代次数")
        self._add_rec_row(form, "Max Iters:", self.spin_max_iters, "max_iters")

        self.spin_num_workers = QSpinBox()
        self.spin_num_workers.setRange(0, 16)
        self.spin_num_workers.setValue(4)
        self.spin_num_workers.setToolTip("数据加载并行线程数（0 = 主线程加载）")
        self._add_rec_row(form, "Num Workers:", self.spin_num_workers, "num_workers")

        self.spin_val_interval = QSpinBox()
        self.spin_val_interval.setRange(100, 50000)
        self.spin_val_interval.setSingleStep(500)
        self.spin_val_interval.setValue(4000)
        self.spin_val_interval.setToolTip("每 N 次迭代运行一次验证")
        self._add_rec_row(form, "验证间隔:", self.spin_val_interval, "val_interval")

        self.tabs.addTab(tab, "常规参数")

    def _create_tab_optimizer(self):
        """Tab 2: 优化器"""
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        self.combo_loss_type = QComboBox()
        self.combo_loss_type.addItems(['CrossEntropyLoss', 'FocalLoss', 'DiceLoss'])
        self.combo_loss_type.setToolTip("主干损失函数类型")
        self._add_rec_row(form, "损失函数:", self.combo_loss_type, "loss_type")

        self.chk_use_class_weight = QCheckBox("启用类别权重补偿")
        self.chk_use_class_weight.setToolTip("根据数据类别分布自动调整交叉熵权重，改善长尾问题")
        self._add_rec_row(form, "类别权重:", self.chk_use_class_weight, "class_weight")

        self.combo_optimizer = QComboBox()
        self.combo_optimizer.addItems(['AdamW', 'SGD', 'Adam', 'RAdam'])
        self.combo_optimizer.setToolTip("优化器类型")
        self._add_rec_row(form, "优化器:", self.combo_optimizer, "optimizer")

        self.dspin_lr = QDoubleSpinBox()
        self.dspin_lr.setRange(1e-7, 1.0)
        self.dspin_lr.setDecimals(6)
        self.dspin_lr.setSingleStep(0.0001)
        self.dspin_lr.setValue(0.0001)
        self.dspin_lr.setToolTip("初始学习率")
        self._add_rec_row(form, "学习率 (LR):", self.dspin_lr, "lr")

        self.dspin_weight_decay = QDoubleSpinBox()
        self.dspin_weight_decay.setRange(0.0, 1.0)
        self.dspin_weight_decay.setDecimals(5)
        self.dspin_weight_decay.setSingleStep(0.001)
        self.dspin_weight_decay.setValue(0.01)
        self.dspin_weight_decay.setToolTip("权重衰减（L2 正则化）")
        self._add_rec_row(form, "Weight Decay:", self.dspin_weight_decay, "weight_decay")

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form.addRow(line)

        self.combo_lr_schedule = QComboBox()
        self.combo_lr_schedule.addItems(['PolyLR', 'StepLR', 'CosineAnnealingLR'])
        self.combo_lr_schedule.setToolTip("学习率衰减策略")
        self._add_rec_row(form, "LR 衰减策略:", self.combo_lr_schedule, "lr_schedule")

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
        self._add_rec_row(form, "保存间隔:", self.spin_save_interval, "save_interval")

        self.spin_max_keep = QSpinBox()
        self.spin_max_keep.setRange(1, 50)
        self.spin_max_keep.setValue(3)
        self.spin_max_keep.setToolTip("保留最近的几个检查点文件")
        self._add_rec_row(form, "最大保留数:", self.spin_max_keep, "max_keep_ckpts")

        self.check_save_best = QCheckBox("保存最佳模型 (Best mIoU)")
        self.check_save_best.setChecked(True)
        self._add_rec_row(form, None, self.check_save_best, "save_best")

        self.tabs.addTab(tab, "检查点")

    def _create_tab_augmentation(self):
        """Tab 4: 数据增强"""
        tab = QWidget()
        form = QFormLayout(tab)
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        self.check_random_flip = QCheckBox("RandomFlip (水平翻转)")
        self.check_random_flip.setChecked(True)
        self._add_rec_row(form, None, self.check_random_flip, "aug_random_flip")

        self.check_photo_distortion = QCheckBox("PhotoMetricDistortion (光度扰动)")
        self.check_photo_distortion.setChecked(True)
        self._add_rec_row(form, None, self.check_photo_distortion, "aug_photo_distortion")

        self.check_random_rotate = QCheckBox("RandomRotate (随机旋转)")
        self.check_random_rotate.setChecked(False)
        self._add_rec_row(form, None, self.check_random_rotate, "aug_random_rotate")

        self.check_random_scale = QCheckBox("MultiScaleFlipAug (多尺度)")
        self.check_random_scale.setChecked(False)
        self._add_rec_row(form, None, self.check_random_scale, "aug_multi_scale")

        note = QLabel("💡 更多增强由 ConfigAdvisor 自动推荐")
        note.setStyleSheet("color: #888; font-size: 10px; font-style: italic;")
        note.setWordWrap(True)
        form.addRow(note)

        self.tabs.addTab(tab, "数据增强")

    def _connect_signals(self):
        """为了发送 config_changed，统一监听所有已经记录在 _rec_widgets 的组件"""
        for widget in self._rec_widgets.values():
            if hasattr(widget, 'valueChanged'):
                widget.valueChanged.connect(lambda: self.config_changed.emit())
            elif hasattr(widget, 'currentTextChanged'):
                widget.currentTextChanged.connect(lambda: self.config_changed.emit())
            elif hasattr(widget, 'toggled'):
                widget.toggled.connect(lambda: self.config_changed.emit())

    # ==================== 推荐系统 API ====================

    def set_recommendations(self, rec_dict: dict):
        """
        为匹配的控件设置推荐值与图标
        Args:
            rec_dict: dict like { 'batch_size': {'value': 4, 'reason': '...'}}
        """
        for key, rec_data in rec_dict.items():
            if key in self._rec_btns:
                val = rec_data.get('value')
                reason = rec_data.get('reason', '')
                
                self._rec_values[key] = val
                self._rec_reasons[key] = reason
                self._rec_applied[key] = False
                
                btn = self._rec_btns[key]
                btn.setText("💡")
                btn.setVisible(True)
                btn.setToolTip(f"推荐值: {val}\n{reason}\n\n🔹 点击应用此推荐")
                self._set_widget_color(self._rec_widgets[key], self.COLOR_DEFAULT)

    def apply_all_recommendations(self):
        """一键收集并应用所有推荐项"""
        for key, btn in self._rec_btns.items():
            if btn.isVisible():
                self._apply_single_recommendation(key)

    def clear_all_recommendations(self):
        """清空所有的推荐状态和显示"""
        self._rec_values.clear()
        self._rec_reasons.clear()
        for key, btn in self._rec_btns.items():
            btn.setVisible(False)
            self._rec_applied[key] = False
            self._set_widget_color(self._rec_widgets[key], self.COLOR_DEFAULT)

    # ==================== 内部状态更新 ====================

    def _apply_single_recommendation(self, key: str):
        if key not in self._rec_values:
            return
            
        val = self._rec_values[key]
        widget = self._rec_widgets[key]
        
        # 写入值
        if isinstance(widget, QSpinBox):
            widget.setValue(int(val))
        elif isinstance(widget, QDoubleSpinBox):
            widget.setValue(float(val))
        elif isinstance(widget, QComboBox):
            idx = widget.findText(str(val))
            if idx >= 0:
                widget.setCurrentIndex(idx)
        elif isinstance(widget, QCheckBox):
            widget.setChecked(bool(val))
            
        self._rec_applied[key] = True
        
        # 切换按钮
        btn = self._rec_btns[key]
        btn.setText("✅")
        btn.setToolTip(f"已应用推荐值: {val}\n{self._rec_reasons[key]}")
        
        # 切换颜色为来源确认
        self._set_widget_color(widget, self.COLOR_RECOMMENDED)

    def _on_widget_value_changed(self, key: str):
        if not self._rec_applied.get(key, False):
            return

        widget = self._rec_widgets[key]
        rec_val = self._rec_values[key]
        
        # 获取当前值并比对
        is_same = False
        if isinstance(widget, QSpinBox):
            is_same = (widget.value() == int(rec_val))
        elif isinstance(widget, QDoubleSpinBox):
            is_same = (abs(widget.value() - float(rec_val)) < 1e-9)
        elif isinstance(widget, QComboBox):
            is_same = (widget.currentText() == str(rec_val))
        elif isinstance(widget, QCheckBox):
            is_same = (widget.isChecked() == bool(rec_val))
            
        if is_same:
            self._set_widget_color(widget, self.COLOR_RECOMMENDED)
        else:
            self._set_widget_color(widget, self.COLOR_OVERRIDDEN)

    def _set_widget_color(self, widget: QWidget, color: str):
        style = f"color: {color}; font-weight: bold;" if color else ""
        if isinstance(widget, QComboBox):
            widget.setStyleSheet(f"QComboBox {{ color: {color}; font-weight: bold; }}" if color else "")
        elif isinstance(widget, QCheckBox):
            widget.setStyleSheet(f"QCheckBox {{ color: {color}; font-weight: bold; }}" if color else "")
        else:
            widget.setStyleSheet(style)

    # ==================== 获取参数 ====================

    def get_params(self) -> dict:
        return {
            'in_channels': self.spin_in_channels.value(),
            'crop_size': self.spin_crop_size.value(),
            'batch_size': self.spin_batch_size.value(),
            'max_iters': self.spin_max_iters.value(),
            'num_workers': self.spin_num_workers.value(),
            'val_interval': self.spin_val_interval.value(),
            'loss_type': self.combo_loss_type.currentText(),
            'class_weight': self.chk_use_class_weight.isChecked(),
            'optimizer': self.combo_optimizer.currentText(),
            'lr': self.dspin_lr.value(),
            'weight_decay': self.dspin_weight_decay.value(),
            'lr_schedule': self.combo_lr_schedule.currentText(),
            'save_interval': self.spin_save_interval.value(),
            'max_keep_ckpts': self.spin_max_keep.value(),
            'save_best': self.check_save_best.isChecked(),
            'aug_random_flip': self.check_random_flip.isChecked(),
            'aug_photo_distortion': self.check_photo_distortion.isChecked(),
            'aug_random_rotate': self.check_random_rotate.isChecked(),
            'aug_multi_scale': self.check_random_scale.isChecked(),
        }
