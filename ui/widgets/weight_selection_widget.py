# -*- coding: utf-8 -*-
"""
权重选择组件 (Weight Selection Widget)

提供预训练权重的管理机制：
1. 公共预训练 (如 ImageNet、COCO 等对应 Backbone 的默认权重)
2. 自有遥感权重 (.pth)

这是从原 ModelSelectionWidget 中拆分出来的独立组件。
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QComboBox, QTabWidget, QCheckBox,
    QPushButton, QLineEdit, QFileDialog, QLabel,
    QSizePolicy
)
from PySide6.QtCore import Signal
from ui.widgets.model_selection_widget import PRETRAINED_MODELS


class WeightSelectionWidget(QWidget):
    """
    权重选择组件

    布局：
    - QTabWidget：
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
        
        # 初始时先清空列表，等上层 ModelSelection 通知
        self.combo_pretrained_model.clear()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        # ====== 预训练权重 Tab ======
        self.tab_pretrained = QTabWidget()
        self.tab_pretrained.setMaximumHeight(140)

        # --- Tab 1: 公共预训练 ---
        tab_public = QWidget()
        tab_public_layout = QVBoxLayout(tab_public)
        tab_public_layout.setContentsMargins(6, 6, 6, 6)
        tab_public_layout.setSpacing(4)

        self.check_use_pretrained = QCheckBox("使用预训练权重 (Use Pretrained)")
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

        self.tab_pretrained.addTab(tab_public, "公共预训练 (Public)")

        # --- Tab 2: 自有遥感权重 ---
        tab_custom = QWidget()
        tab_custom_layout = QVBoxLayout(tab_custom)
        tab_custom_layout.setContentsMargins(6, 6, 6, 6)
        tab_custom_layout.setSpacing(4)

        self.check_use_custom_weight = QCheckBox("使用自有权重 (Custom .pth)")
        tab_custom_layout.addWidget(self.check_use_custom_weight)

        weight_row = QHBoxLayout()
        self.line_custom_weight = QLineEdit()
        self.line_custom_weight.setPlaceholderText("选择 .pth 权重文件...")
        self.line_custom_weight.setReadOnly(True)
        self.btn_browse_weight = QPushButton("浏览...")
        weight_row.addWidget(self.line_custom_weight)
        weight_row.addWidget(self.btn_browse_weight)
        tab_custom_layout.addLayout(weight_row)

        self.tab_pretrained.addTab(tab_custom, "自有业务权重 (Custom)")

        layout.addWidget(self.tab_pretrained)

    def _connect_signals(self):
        self.check_use_pretrained.toggled.connect(self._on_pretrained_toggled)
        self.btn_browse_weight.clicked.connect(self._on_browse_weight)
        self.combo_pretrained_model.currentTextChanged.connect(lambda: self.config_changed.emit())
        self.check_use_custom_weight.toggled.connect(lambda: self.config_changed.emit())

    def update_backbone(self, backbone_name: str):
        """外部调用：当 Backbone 改变时，更新可用的预训练模型列表"""
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
        from PySide6.QtWidgets import QFileDialog
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
                'use_pretrained': bool,
                'pretrained_model': str,
                'use_custom_weight': bool,
                'custom_weight_path': str,
            }
        """
        return {
            'use_pretrained': self.check_use_pretrained.isChecked(),
            'pretrained_model': self.combo_pretrained_model.currentText(),
            'use_custom_weight': self.check_use_custom_weight.isChecked(),
            'custom_weight_path': self.line_custom_weight.text(),
        }
