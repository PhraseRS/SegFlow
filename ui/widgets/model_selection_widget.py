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

        # ====== 预训练权重 Tab ======
        self.tab_pretrained = QTabWidget()
        self.tab_pretrained.setMaximumHeight(140)

        # --- Tab 1: 公共预训练 ---
        tab_public = QWidget()
        tab_public_layout = QVBoxLayout(tab_public)
        tab_public_layout.setContentsMargins(6, 6, 6, 6)
        tab_public_layout.setSpacing(4)

        self.check_use_pretrained = QCheckBox("使用预训练权重")
        self.check_use_pretrained.setChecked(True)
        tab_public_layout.addWidget(self.check_use_pretrained)

        pretrained_row = QHBoxLayout()
        pretrained_row.addWidget(QLabel("预训练模型:"))
        self.combo_pretrained_model = QComboBox()
        self.combo_pretrained_model.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        pretrained_row.addWidget(self.combo_pretrained_model)
        tab_public_layout.addLayout(pretrained_row)

        self.tab_pretrained.addTab(tab_public, "公共预训练")

        # --- Tab 2: 自有遥感权重 ---
        tab_custom = QWidget()
        tab_custom_layout = QVBoxLayout(tab_custom)
        tab_custom_layout.setContentsMargins(6, 6, 6, 6)
        tab_custom_layout.setSpacing(4)

        self.check_use_custom_weight = QCheckBox("使用自有权重 (.pth)")
        tab_custom_layout.addWidget(self.check_use_custom_weight)

        weight_row = QHBoxLayout()
        self.line_custom_weight = QLineEdit()
        self.line_custom_weight.setPlaceholderText("选择 .pth 权重文件...")
        self.line_custom_weight.setReadOnly(True)
        self.btn_browse_weight = QPushButton("浏览...")
        weight_row.addWidget(self.line_custom_weight)
        weight_row.addWidget(self.btn_browse_weight)
        tab_custom_layout.addLayout(weight_row)

        self.tab_pretrained.addTab(tab_custom, "自有遥感权重")

        layout.addWidget(self.tab_pretrained)

    def _connect_signals(self):
        self.combo_backbone.currentTextChanged.connect(self._on_backbone_changed)
        self.check_use_pretrained.toggled.connect(self._on_pretrained_toggled)
        self.btn_browse_weight.clicked.connect(self._on_browse_weight)
        self.combo_framework.currentTextChanged.connect(lambda: self.config_changed.emit())
        self.combo_pretrained_model.currentTextChanged.connect(lambda: self.config_changed.emit())
        self.check_use_custom_weight.toggled.connect(lambda: self.config_changed.emit())

        # 初始化预训练模型列表
        self._on_backbone_changed(self.combo_backbone.currentText())

    def _on_backbone_changed(self, backbone_name):
        """Backbone 变更时更新预训练模型列表"""
        self.combo_pretrained_model.clear()
        models = PRETRAINED_MODELS.get(backbone_name, [])
        self.combo_pretrained_model.addItems(models)
        self.config_changed.emit()

    def _on_pretrained_toggled(self, checked):
        """启用/禁用预训练模型选择"""
        self.combo_pretrained_model.setEnabled(checked)
        self.config_changed.emit()

    def _on_browse_weight(self):
        """浏览选择自有权重文件"""
        path, _ = QFileDialog.getOpenFileName(
            self, "选择权重文件", "",
            "PyTorch 权重 (*.pth);;所有文件 (*)"
        )
        if path:
            self.line_custom_weight.setText(path)
            self.check_use_custom_weight.setChecked(True)
            self.config_changed.emit()

    def get_params(self) -> dict:
        """
        收集当前配置参数。

        Returns:
            dict: {
                'framework': str,
                'backbone': str,
                'backbone_key': str,
                'use_pretrained': bool,
                'pretrained_model': str,
                'use_custom_weight': bool,
                'custom_weight_path': str,
            }
        """
        backbone_name = self.combo_backbone.currentText()
        return {
            'framework': self.combo_framework.currentText(),
            'backbone': backbone_name,
            'backbone_key': BACKBONE_CHOICES.get(backbone_name, ''),
            'use_pretrained': self.check_use_pretrained.isChecked(),
            'pretrained_model': self.combo_pretrained_model.currentText(),
            'use_custom_weight': self.check_use_custom_weight.isChecked(),
            'custom_weight_path': self.line_custom_weight.text(),
        }
