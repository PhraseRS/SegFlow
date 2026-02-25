# -*- coding: utf-8 -*-
"""
数据智能推荐配置组件 (Advisor Config Widget)

以只读/半锁定状态显示 ConfigAdvisor 传来的推荐参数。
用户可通过复选框决定是否采纳各项推荐。

Training Roadmap Phase 3, Task 3.2
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout, QGroupBox,
    QLabel, QCheckBox, QSpinBox, QDoubleSpinBox,
    QFrame
)
from PySide6.QtCore import Signal


class AdvisorConfigWidget(QWidget):
    """
    数据智能推荐组件

    显示 ConfigAdvisor.recommend_rs_params() 的结果，
    允许用户逐项启用/禁用推荐。

    Signals:
        config_changed(): 任何配置项变更时触发
    """

    config_changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._advisor_params = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # 状态标签
        self.label_status = QLabel("⏳ 等待数据分析完成...")
        self.label_status.setStyleSheet(
            "color: #666; font-style: italic; padding: 4px;"
        )
        layout.addWidget(self.label_status)

        # 推荐参数表单
        self.group_recommend = QGroupBox("💡 数据驱动推荐")
        self.group_recommend.setVisible(False)
        form = QFormLayout(self.group_recommend)
        form.setSpacing(4)
        form.setContentsMargins(6, 6, 6, 6)

        # 输入通道数
        self.check_in_channels = QCheckBox("应用推荐通道数")
        self.check_in_channels.setChecked(True)
        self.spin_in_channels = QSpinBox()
        self.spin_in_channels.setRange(1, 64)
        self.spin_in_channels.setValue(3)
        self.spin_in_channels.setReadOnly(True)
        self.spin_in_channels.setToolTip("由数据集影像通道数决定")
        form.addRow(self.check_in_channels, self.spin_in_channels)

        # 推荐 Crop Size
        self.check_crop_size = QCheckBox("应用推荐裁剪大小")
        self.check_crop_size.setChecked(True)
        self.spin_crop_size = QSpinBox()
        self.spin_crop_size.setRange(256, 2048)
        self.spin_crop_size.setSingleStep(32)
        self.spin_crop_size.setValue(512)
        self.spin_crop_size.setReadOnly(True)
        self.spin_crop_size.setToolTip("基于数据集最小影像尺寸 × 0.8，对齐到 32 倍数")
        form.addRow(self.check_crop_size, self.spin_crop_size)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form.addRow(line)

        # 类别权重补偿
        self.check_class_weight = QCheckBox("启用 Loss 类别权重补偿")
        self.check_class_weight.setChecked(True)
        self.check_class_weight.setToolTip(
            "基于中值频率平衡法计算的 class_weight，\n"
            "用于解决遥感背景像素占比过大的问题"
        )
        form.addRow(self.check_class_weight)

        # 推荐损失函数
        self.label_loss_type = QLabel("—")
        self.label_loss_type.setToolTip("推荐的损失函数类型")
        form.addRow("推荐损失函数:", self.label_loss_type)

        # 推荐理由
        self.label_reason = QLabel("")
        self.label_reason.setWordWrap(True)
        self.label_reason.setStyleSheet(
            "color: #1565C0; font-size: 11px; padding: 2px;"
        )
        form.addRow(self.label_reason)

        layout.addWidget(self.group_recommend)

        # 信号
        self.check_in_channels.toggled.connect(lambda: self.config_changed.emit())
        self.check_crop_size.toggled.connect(lambda: self.config_changed.emit())
        self.check_class_weight.toggled.connect(lambda: self.config_changed.emit())

    def set_advisor_params(self, params: dict):
        """
        填充推荐参数（由 ConfigAdvisor.recommend_rs_params() 提供）。

        Args:
            params: {
                'in_channels': int,
                'crop_size': tuple,
                'class_weight': list,
                'loss_config': dict,
                'augmentation': dict,
            }
        """
        self._advisor_params = params

        self.spin_in_channels.setValue(params.get('in_channels', 3))
        crop = params.get('crop_size', (512, 512))
        self.spin_crop_size.setValue(crop[0] if isinstance(crop, (tuple, list)) else crop)

        loss_cfg = params.get('loss_config', {})
        self.label_loss_type.setText(loss_cfg.get('type', '—'))
        self.label_reason.setText(loss_cfg.get('_reason', ''))

        class_weight = params.get('class_weight', [])
        if class_weight:
            self.check_class_weight.setToolTip(
                f"class_weight = {[round(w, 2) for w in class_weight[:8]]}"
                + ("..." if len(class_weight) > 8 else "")
            )

        self.label_status.setVisible(False)
        self.group_recommend.setVisible(True)
        self.config_changed.emit()

    def clear(self):
        """清空推荐参数，恢复等待状态"""
        self._advisor_params = {}
        self.label_status.setVisible(True)
        self.group_recommend.setVisible(False)

    def get_params(self) -> dict:
        """
        收集当前配置参数（仅返回用户启用的推荐项）。

        Returns:
            dict: {
                'in_channels': int | None,
                'crop_size': tuple | None,
                'use_class_weight': bool,
                'loss_config': dict | None,
                'augmentation': dict | None,
            }
        """
        params = self._advisor_params
        return {
            'in_channels': (
                self.spin_in_channels.value()
                if self.check_in_channels.isChecked() else None
            ),
            'crop_size': (
                (self.spin_crop_size.value(), self.spin_crop_size.value())
                if self.check_crop_size.isChecked() else None
            ),
            'use_class_weight': self.check_class_weight.isChecked(),
            'loss_config': (
                params.get('loss_config')
                if self.check_class_weight.isChecked() else None
            ),
            'augmentation': params.get('augmentation'),
        }
