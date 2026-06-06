# -*- coding: utf-8 -*-
"""
模型选择组件 (Model Selection Widget)

提供框架选择、Backbone 选择、预训练权重管理。
框架列表从 FrameworkRegistry 动态读取，无需硬编码。

Training Roadmap Phase 3, Task 3.1
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QFormLayout,
    QGroupBox, QComboBox,
    QSizePolicy
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, Qt
from PySide6.QtGui import QColor

from core.framework_registry import (
    get_all_display_names,
    get_required_packages,
    get_key_by_display_name,
)
from ui.widgets.wheel_guard import install_wheel_guard


# 算法家族分组（决定下拉框的呈现顺序与分隔符位置）
# 注意：每组内算法按首字母排序，组与组之间用分隔标题项隔开
METHOD_GROUPS = [
    ('Transformer', ['Mask2Former', 'SegFormer', 'Swin-Transformer', 'UperNet']),
    ('CNN', ['DeepLabV3+', 'FCN', 'HRNet+OCR', 'PSPNet', 'UNet', 'UNet++']),
]

# 算法-Backbone映射关系（每组内 backbone 也按首字母升序）
METHOD_BACKBONE_MAP = {
    'PSPNet': ['ResNet-50', 'ResNet-101'],
    'DeepLabV3+': ['MobileNetV2', 'MobileNetV3', 'ResNet-50', 'ResNet-101'],
    'SegFormer': ['MiT-B0', 'MiT-B1', 'MiT-B2', 'MiT-B3', 'MiT-B4', 'MiT-B5'],
    'UperNet': ['ConvNeXt-Tiny', 'ResNet-50', 'Swin-Base', 'Swin-Tiny'],
    'FCN': ['ResNet-18', 'ResNet-50', 'ResNet-101'],
    'UNet': ['ResNet-50'],
    'UNet++': ['ResNet-50', 'ResNet-101'],
    'Mask2Former': ['ResNet-50', 'Swin-Base', 'Swin-Large', 'Swin-Tiny'],
    'HRNet+OCR': ['HRNet-W32', 'HRNet-W48'],
    'Swin-Transformer': ['Swin-Base', 'Swin-Large', 'Swin-Small', 'Swin-Tiny'],
}

# Backbone内部标识映射
BACKBONE_CHOICES = {
    'ResNet-18': 'resnet18',
    'ResNet-50': 'resnet50',
    'ResNet-101': 'resnet101',
    'MobileNetV2': 'mobilenet_v2',
    'MobileNetV3': 'mobilenet_v3_large',
    'HRNet-W32': 'hrnet_w32',
    'HRNet-W48': 'hrnet_w48',
    'Swin-Tiny': 'swin_tiny',
    'Swin-Small': 'swin_small',
    'Swin-Base': 'swin_base',
    'Swin-Large': 'swin_large',
    'ConvNeXt-Tiny': 'convnext_tiny',
    'MiT-B0': 'mit_b0',
    'MiT-B1': 'mit_b1',
    'MiT-B2': 'mit_b2',
    'MiT-B3': 'mit_b3',
    'MiT-B4': 'mit_b4',
    'MiT-B5': 'mit_b5',
}

PRETRAINED_MODELS = {
    'ResNet-50': ['ImageNet-1K', 'COCO (DeepLabV3+)'],
    'ResNet-101': ['ImageNet-1K', 'COCO (DeepLabV3+)', 'Cityscapes'],
    'MobileNetV2': ['ImageNet-1K'],
    'HRNet-W48': ['ImageNet-1K', 'Cityscapes'],
    'Swin-Tiny': ['ImageNet-1K', 'ADE20K'],
    'Swin-Small': ['ImageNet-1K', 'ADE20K'],
    'Swin-Base': ['ImageNet-22K', 'ADE20K'],
    'Swin-Large': ['ImageNet-22K', 'ADE20K'],
    'MiT-B0': ['ImageNet-1K'],
    'MiT-B1': ['ImageNet-1K'],
    'MiT-B2': ['ImageNet-1K', 'ADE20K'],
    'MiT-B5': ['ImageNet-1K', 'ADE20K'],
}


class ModelSelectionWidget(QWidget):
    """
    模型选择组件

    布局：
    - 顶部：框架选择 + Backbone 选择（框架列表从 FrameworkRegistry 动态读取）

    Signals:
        config_changed():               任何配置项变更时触发
        framework_changed(str, list):   框架切换时触发，携带 (display_name, required_packages)
    """

    config_changed = Signal()
    framework_changed = Signal(str, list)   # (display_name, required_packages)

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
        # 从注册表动态读取框架列表
        framework_names = get_all_display_names()
        self.combo_framework.addItems(framework_names)
        self.combo_framework.setToolTip("选择底层训练框架")
        top_form.addRow("框架:", self.combo_framework)

        self.combo_method = QComboBox()
        # 按分组结构填充算法下拉框，用分隔标题项区分组别
        for group_name, methods in METHOD_GROUPS:
            # 添加分隔标题项（不可选）
            separator_item = f"── {group_name} ──"
            self.combo_method.addItem(separator_item)
            idx = self.combo_method.count() - 1
            # 设置分隔项的样式：灰色、居中、不可选
            self.combo_method.model().item(idx).setEnabled(False)
            self.combo_method.model().item(idx).setForeground(QColor(128, 128, 128))
            self.combo_method.model().item(idx).setTextAlignment(Qt.AlignCenter)
            # 添加该组内的算法项
            for method in methods:
                self.combo_method.addItem(method)
        self.combo_method.setToolTip("选择分割算法/架构")
        # 默认选中第一个 Transformer 算法（跳过分隔项）
        self.combo_method.setCurrentText('Mask2Former')
        top_form.addRow("算法:", self.combo_method)

        self.combo_backbone = QComboBox()
        self.combo_backbone.setEnabled(False)
        self.combo_backbone.setToolTip("选择模型的 Backbone 架构")
        top_form.addRow("Backbone:", self.combo_backbone)

        layout.addLayout(top_form)

        # 初始化第一个算法的 Backbone 列表
        self._update_backbone_list(self.combo_method.currentText())

        # UI-09：阻止鼠标悬停时滚轮误改 ComboBox 的选项
        install_wheel_guard(self)

    def _connect_signals(self):
        self.combo_method.currentTextChanged.connect(self._on_method_changed)
        self.combo_backbone.currentTextChanged.connect(self._on_backbone_changed)
        self.combo_framework.currentTextChanged.connect(self._on_framework_changed)

    def _update_backbone_list(self, method_name: str):
        """根据选中的算法更新Backbone列表"""
        self.combo_backbone.clear()
        backbones = METHOD_BACKBONE_MAP.get(method_name, [])
        if backbones:
            self.combo_backbone.addItems(backbones)
            self.combo_backbone.setEnabled(True)
            self.combo_backbone.setCurrentIndex(0)
        else:
            self.combo_backbone.setEnabled(False)

    def _on_framework_changed(self, display_name: str):
        """框架切换：广播 framework_changed 信号，携带所需包列表。"""
        packages = get_required_packages(display_name)
        self.framework_changed.emit(display_name, packages)
        self.config_changed.emit()

    def _on_method_changed(self, method_name: str):
        """算法改变时更新Backbone列表"""
        # 防御：分隔标题项被误触发时直接忽略
        if method_name.startswith('──'):
            return
        self._update_backbone_list(method_name)
        self.config_changed.emit()

    def _on_backbone_changed(self, backbone_name):
        self.config_changed.emit()

    def get_params(self) -> dict:
        """
        收集当前配置参数。

        Returns:
            dict: {
                'framework': str,        # 显示名称
                'framework_key': str,    # 注册表 key
                'method': str,
                'backbone': str,
                'backbone_key': str,
            }
        """
        backbone_name = self.combo_backbone.currentText()
        method_name = self.combo_method.currentText()
        display_name = self.combo_framework.currentText()
        return {
            'framework': display_name,
            'framework_key': get_key_by_display_name(display_name) or '',
            'method': method_name,
            'backbone': backbone_name,
            'backbone_key': BACKBONE_CHOICES.get(backbone_name, ''),
        }

