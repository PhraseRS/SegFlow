# -*- coding: utf-8 -*-
"""
可视化设置UI组件 (Visualization Settings Widget)
用于动态调整推理结果的可视化效果（透明度、调色板）
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QPushButton, QColorDialog, QGroupBox, QScrollArea
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from typing import List, Dict


class VisualizationSettingsWidget(QWidget):
    """
    可视化设置组件
    提供透明度调节和类别颜色自定义功能
    """

    # 信号定义
    palette_changed = Signal(dict)  # 调色板变化
    alpha_changed = Signal(float)   # 透明度变化
    apply_requested = Signal()      # 请求应用到预览

    def __init__(self, parent=None):
        super().__init__(parent)
        self.class_names = []
        self.current_palette = {}
        self.default_palette = {}
        self.color_buttons = {}
        self.init_ui()

    def init_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(10)

        # 透明度控制
        alpha_group = QGroupBox("透明度")
        alpha_layout = QHBoxLayout()

        self.alpha_slider = QSlider(Qt.Orientation.Horizontal)
        self.alpha_slider.setRange(0, 100)
        self.alpha_slider.setValue(50)
        self.alpha_slider.valueChanged.connect(self._on_alpha_changed)

        self.alpha_label = QLabel("50%")
        self.alpha_label.setMinimumWidth(40)
        self.alpha_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

        alpha_layout.addWidget(QLabel("叠加透明度:"))
        alpha_layout.addWidget(self.alpha_slider)
        alpha_layout.addWidget(self.alpha_label)
        alpha_group.setLayout(alpha_layout)
        layout.addWidget(alpha_group)

        # 类别颜色配置
        color_group = QGroupBox("类别颜色配置")
        color_layout = QVBoxLayout()

        # 创建滚动区域（类别多时）
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setMaximumHeight(300)

        # 颜色列表容器
        self.color_list_widget = QWidget()
        self.color_list_layout = QVBoxLayout(self.color_list_widget)
        self.color_list_layout.setContentsMargins(5, 5, 5, 5)
        self.color_list_layout.setSpacing(5)

        scroll.setWidget(self.color_list_widget)
        color_layout.addWidget(scroll)
        color_group.setLayout(color_layout)
        layout.addWidget(color_group)

        # 操作按钮
        btn_layout = QHBoxLayout()

        self.reset_btn = QPushButton("重置为默认")
        self.reset_btn.clicked.connect(self._reset_palette)

        self.apply_btn = QPushButton("应用到预览")
        self.apply_btn.clicked.connect(self.apply_requested.emit)
        self.apply_btn.setStyleSheet("font-weight: bold;")

        btn_layout.addWidget(self.reset_btn)
        btn_layout.addWidget(self.apply_btn)
        layout.addLayout(btn_layout)

        layout.addStretch()

    def set_classes_and_palette(self, class_names: List[str], palette: List[List[int]]):
        """
        设置类别名称和调色板

        Args:
            class_names: 类别名称列表
            palette: 调色板 [[R,G,B], ...]
        """
        self.class_names = class_names

        # 转换为字典格式
        self.current_palette = {i: color for i, color in enumerate(palette)}
        self.default_palette = self.current_palette.copy()

        # 重建颜色选择器列表
        self._rebuild_color_list()

    def _rebuild_color_list(self):
        """重建颜色选择器列表"""
        # 清空现有控件
        while self.color_list_layout.count():
            child = self.color_list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self.color_buttons.clear()

        # 为每个类别创建颜色选择器
        for class_id, class_name in enumerate(self.class_names):
            row = QHBoxLayout()
            row.setSpacing(10)

            # 颜色预览块
            color_preview = QPushButton()
            color_preview.setFixedSize(40, 30)
            color = self.current_palette.get(class_id, [128, 128, 128])
            color_preview.setStyleSheet(
                f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); "
                f"border: 1px solid #ccc; border-radius: 3px;"
            )
            color_preview.clicked.connect(lambda checked, cid=class_id: self._choose_color(cid))
            color_preview.setToolTip(f"点击选择 {class_name} 的颜色")

            # 类别名称
            label = QLabel(class_name)
            label.setMinimumWidth(100)

            row.addWidget(color_preview)
            row.addWidget(label)
            row.addStretch()

            self.color_list_layout.addLayout(row)
            self.color_buttons[class_id] = color_preview

        self.color_list_layout.addStretch()

    def _on_alpha_changed(self, value: int):
        """透明度滑块变化"""
        alpha = value / 100.0
        self.alpha_label.setText(f"{value}%")
        self.alpha_changed.emit(alpha)

    def _choose_color(self, class_id: int):
        """打开颜色选择对话框"""
        if class_id >= len(self.class_names):
            return

        current_color = self.current_palette.get(class_id, [128, 128, 128])
        qcolor = QColor(current_color[0], current_color[1], current_color[2])

        color = QColorDialog.getColor(
            qcolor,
            self,
            f"选择 {self.class_names[class_id]} 的颜色"
        )

        if color.isValid():
            # 更新调色板
            self.current_palette[class_id] = [color.red(), color.green(), color.blue()]

            # 更新按钮颜色
            self.color_buttons[class_id].setStyleSheet(
                f"background-color: rgb({color.red()}, {color.green()}, {color.blue()}); "
                f"border: 1px solid #ccc; border-radius: 3px;"
            )

            # 发射信号
            self.palette_changed.emit(self.current_palette)

    def _reset_palette(self):
        """重置为默认调色板"""
        if not self.default_palette:
            return

        self.current_palette = self.default_palette.copy()

        # 更新UI
        for class_id, color in self.default_palette.items():
            if class_id in self.color_buttons:
                self.color_buttons[class_id].setStyleSheet(
                    f"background-color: rgb({color[0]}, {color[1]}, {color[2]}); "
                    f"border: 1px solid #ccc; border-radius: 3px;"
                )

        self.palette_changed.emit(self.current_palette)

    def get_current_palette(self) -> Dict[int, List[int]]:
        """获取当前调色板"""
        return self.current_palette.copy()

    def get_current_alpha(self) -> float:
        """获取当前透明度"""
        return self.alpha_slider.value() / 100.0

    def set_alpha(self, alpha: float):
        """设置透明度"""
        value = int(alpha * 100)
        self.alpha_slider.setValue(value)
