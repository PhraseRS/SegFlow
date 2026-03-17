# -*- coding: utf-8 -*-
"""
模型选择组件 (Model Selection Widget)

提供框架选择、Backbone 选择、预训练权重管理。
包含两个子 Tab：公共预训练和自有遥感权重。

Training Roadmap Phase 3, Task 3.1
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QTabWidget, QCheckBox,
    QPushButton, QLineEdit, QFileDialog, QLabel,
    QSizePolicy
)
from PySide6.QtCore import Signal


# 预定义的 Backbone 和预训练模型
BACKBONE_CHOICES = {
    'ResNet-50': 'resnet50',
    'ResNet-101': 'resnet101',
    'HRNet-W48': 'hrnet_w48',
    'Swin-Tiny': 'swin_tiny',
    'Swin-Base': 'swin_base',
    'MiT-B0': 'mit_b0',
    'MiT-B2': 'mit_b2',
    'MiT-B5': 'mit_b5',
}

PRETRAINED_MODELS = {
    'ResNet-50': ['ImageNet-1K', 'COCO (DeepLabV3+)'],
    'ResNet-101': ['ImageNet-1K', 'COCO (DeepLabV3+)', 'Cityscapes'],
    'HRNet-W48': ['ImageNet-1K', 'Cityscapes'],
    'Swin-Tiny': ['ImageNet-1K', 'ADE20K'],
    'Swin-Base': ['ImageNet-22K', 'ADE20K'],
    'MiT-B0': ['ImageNet-1K'],
    'MiT-B2': ['ImageNet-1K', 'ADE20K'],
    'MiT-B5': ['ImageNet-1K', 'ADE20K'],
}


class ModelSelectionWidget(QWidget):
    """
    模型选择组件

    布局：
    - 顶部：框架选择 + Backbone 选择
    - 下方 QTabWidget：
        - Tab 1 "公共预训练": ImageNet/COCO 预训练复选框 + 模型下拉列表
        - Tab 2 "自有遥感权重": 文件选择器选择 .pth 文件

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
        layout.setSpacing(4)

        # ====== 框架与 Backbone 选择 ======
        top_form = QFormLayout()
        top_form.setSpacing(4)

        self.combo_framework = QComboBox()
        self.combo_framework.addItems(['MMSegmentation'])
        self.combo_framework.setToolTip("目前仅支持 MMSegmentation")
        top_form.addRow("框架:", self.combo_framework)

        self.combo_backbone = QComboBox()
        self.combo_backbone.addItems(list(BACKBONE_CHOICES.keys()))
        self.combo_backbone.setToolTip("选择模型的 Backbone 架构")
        top_form.addRow("Backbone:", self.combo_backbone)

        layout.addLayout(top_form)

        # (预训练权重相关配置已移至 weight_selection_widget)
        # layout.addLayout(top_form) 已经完成使命，不过原代码是 addLayout 到主 layout


    def _connect_signals(self):
        self.combo_backbone.currentTextChanged.connect(self._on_backbone_changed)
        self.combo_framework.currentTextChanged.connect(lambda: self.config_changed.emit())

    def _on_backbone_changed(self, backbone_name):
        self.config_changed.emit()

    def get_params(self) -> dict:
        """
        收集当前配置参数。

        Returns:
            dict: {
                'framework': str,
                'backbone': str,
                'backbone_key': str,
            }
        """
        backbone_name = self.combo_backbone.currentText()
        return {
            'framework': self.combo_framework.currentText(),
            'backbone': backbone_name,
            'backbone_key': BACKBONE_CHOICES.get(backbone_name, ''),
        }
