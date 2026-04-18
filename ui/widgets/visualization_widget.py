# -*- coding: utf-8 -*-
"""
可视化设置组件 (Visualization Widget)
提供语义分割结果的颜色和透明度配置界面
"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QPushButton, QColorDialog, QGroupBox,
    QScrollArea, QFrame
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QColor
from typing import Dict, List, Optional


class VisualizationWidget(QWidget):
    """
    可视化设置组件
    允许用户自定义语义分割结果的颜色和透明度
    """

    # 信号定义
    palette_changed = Signal(dict)  # 调色板变化: {class_id: [R, G, B], ...}
    alpha_changed = Signal(float)   # 透明度变化: 0.0-1.0
    apply_requested = Signal()      # 请求应用到预览
    reset_requested = Signal()      # 请求重置为默认

    def __init__(self, class_names: List[str], default_palette: Dict[int, list],
                 default_alpha: float = 0.5, parent=None):
        """
        初始化可视化设置组件

        Args:
            class_names: 类别名称列表 ['背景', '建筑', '道路', ...]
            default_palette: 默认调色板 {0: [0,0,0], 1: [255,0,0], ...}
            default_alpha: 默认透明度 0.0-1.0
            parent: 父组件
        """
        super().__init__(parent)
        self.class_names = class_names
        self.default_palette = default_palette.copy()
        self.current_palette = default_palette.copy()
        self.default_alpha = default_alpha

        self.color_buttons = {}  # 存储颜色按钮引用

        self.init_ui()

    def init_ui(self):
        """初始化UI布局"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)

        # === 透明度控制区域 ===
        alpha_group = self._create_alpha_control()
        main_layout.addWidget(alpha_group)

        # === 类别颜色配置区域 ===
        color_group = self._create_color_control()
        main_layout.addWidget(color_group)

        # === 操作按钮区域 ===
        button_layout = self._create_button_layout()
        main_layout.addLayout(button_layout)

        # 添加弹性空间
        main_layout.addStretch()

    def _create_alpha_control(self) -> QGroupBox:
        """创建透明度控制组件"""
        alpha_group = QGroupBox("透明度")
        alpha_layout = QHBoxLayout()

        # 透明度滑块
        self.alpha_slider = QSlider(Qt.Horizontal)
        self.alpha_slider.setRange(0, 100)
        self.alpha_slider.setValue(int(self.default_alpha * 100))
        self.alpha_slider.setTickPosition(QSlider.TicksBelow)
        self.alpha_slider.setTickInterval(10)
        self.alpha_slider.valueChanged.connect(self._on_alpha_changed)

        # 透明度标签
        self.alpha_label = QLabel(f"{int(self.default_alpha * 100)}%")
        self.alpha_label.setMinimumWidth(40)
        self.alpha_label.setAlignment(Qt.AlignCenter)

        alpha_layout.addWidget(self.alpha_slider, stretch=1)
        alpha_layout.addWidget(self.alpha_label)

        alpha_group.setLayout(alpha_layout)
        return alpha_group

    def _create_color_control(self) -> QScrollArea:
        """创建类别颜色配置组件"""
        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(300)
        scroll.setFrameShape(QFrame.StyledPanel)

        # 内容容器
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(5, 5, 5, 5)
        content_layout.setSpacing(8)

        # 标题
        title_label = QLabel("类别颜色配置")
        title_label.setStyleSheet("font-weight: bold; font-size: 11pt;")
        content_layout.addWidget(title_label)

        # 为每个类别创建颜色选择行
        for class_id, class_name in enumerate(self.class_names):
            row_widget = self._create_color_row(class_id, class_name)
            content_layout.addWidget(row_widget)

        content_layout.addStretch()
        scroll.setWidget(content_widget)

        return scroll

    def _create_color_row(self, class_id: int, class_name: str) -> QWidget:
        """
        创建单个类别的颜色选择行

        Args:
            class_id: 类别ID
            class_name: 类别名称

        Returns:
            颜色选择行组件
        """
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.setSpacing(10)

        # 颜色预览按钮
        color_button = QPushButton()
        color_button.setFixedSize(40, 30)
        color_button.setToolTip(f"点击修改 {class_name} 的颜色")

        # 设置初始颜色
        color = self.current_palette.get(class_id, [128, 128, 128])
        self._update_button_color(color_button, color)

        # 连接点击事件
        color_button.clicked.connect(lambda: self._choose_color(class_id))

        # 类别名称标签
        name_label = QLabel(class_name)
        name_label.setMinimumWidth(80)

        # 颜色值标签 (显示RGB)
        self.color_value_label = QLabel(f"RGB({color[0]}, {color[1]}, {color[2]})")
        self.color_value_label.setStyleSheet("color: gray; font-size: 9pt;")

        row_layout.addWidget(color_button)
        row_layout.addWidget(name_label)
        row_layout.addWidget(self.color_value_label)
        row_layout.addStretch()

        # 保存按钮引用
        self.color_buttons[class_id] = {
            'button': color_button,
            'label': self.color_value_label
        }

        return row_widget

    def _update_button_color(self, button: QPushButton, color: list):
        """
        更新按钮的背景颜色

        Args:
            button: 按钮组件
            color: RGB颜色 [R, G, B]
        """
        button.setStyleSheet(
            f"QPushButton {{ background-color: rgb({color[0]}, {color[1]}, {color[2]}); "
            f"border: 2px solid #888; border-radius: 4px; }}"
            f"QPushButton:hover {{ border: 2px solid #555; }}"
        )

    def _create_button_layout(self) -> QHBoxLayout:
        """创建操作按钮布局"""
        button_layout = QHBoxLayout()
        button_layout.setSpacing(10)

        # 重置按钮
        reset_btn = QPushButton("重置为默认")
        reset_btn.setToolTip("恢复默认的颜色和透明度设置")
        reset_btn.clicked.connect(self._on_reset_clicked)

        # 应用按钮
        apply_btn = QPushButton("应用到预览")
        apply_btn.setToolTip("将当前设置应用到推理结果预览")
        apply_btn.setStyleSheet("QPushButton { font-weight: bold; }")
        apply_btn.clicked.connect(self.apply_requested.emit)

        button_layout.addWidget(reset_btn)
        button_layout.addWidget(apply_btn)

        return button_layout

    def _on_alpha_changed(self, value: int):
        """
        透明度滑块变化回调

        Args:
            value: 滑块值 0-100
        """
        alpha = value / 100.0
        self.alpha_label.setText(f"{value}%")
        self.alpha_changed.emit(alpha)

    def _choose_color(self, class_id: int):
        """
        打开颜色选择对话框

        Args:
            class_id: 类别ID
        """
        # 获取当前颜色
        current_color = self.current_palette.get(class_id, [128, 128, 128])
        qcolor = QColor(current_color[0], current_color[1], current_color[2])

        # 打开颜色选择对话框
        color = QColorDialog.getColor(
            qcolor,
            self,
            f"选择 {self.class_names[class_id]} 的颜色"
        )

        if color.isValid():
            # 更新调色板
            new_color = [color.red(), color.green(), color.blue()]
            self.current_palette[class_id] = new_color

            # 更新UI
            button_info = self.color_buttons[class_id]
            self._update_button_color(button_info['button'], new_color)
            button_info['label'].setText(f"RGB({new_color[0]}, {new_color[1]}, {new_color[2]})")

            # 发射信号
            self.palette_changed.emit(self.current_palette.copy())

    def _on_reset_clicked(self):
        """重置按钮点击回调"""
        # 重置调色板
        self.current_palette = self.default_palette.copy()

        # 更新所有颜色按钮
        for class_id, color in self.default_palette.items():
            if class_id in self.color_buttons:
                button_info = self.color_buttons[class_id]
                self._update_button_color(button_info['button'], color)
                button_info['label'].setText(f"RGB({color[0]}, {color[1]}, {color[2]})")

        # 重置透明度
        self.alpha_slider.setValue(int(self.default_alpha * 100))

        # 发射信号
        self.palette_changed.emit(self.current_palette.copy())
        self.alpha_changed.emit(self.default_alpha)
        self.reset_requested.emit()

    # === 公共接口 ===

    def get_current_palette(self) -> Dict[int, list]:
        """
        获取当前调色板

        Returns:
            调色板字典 {class_id: [R, G, B], ...}
        """
        return self.current_palette.copy()

    def get_current_alpha(self) -> float:
        """
        获取当前透明度

        Returns:
            透明度值 0.0-1.0
        """
        return self.alpha_slider.value() / 100.0

    def set_palette(self, palette: Dict[int, list]):
        """
        设置调色板

        Args:
            palette: 新的调色板字典
        """
        self.current_palette = palette.copy()

        # 更新UI
        for class_id, color in palette.items():
            if class_id in self.color_buttons:
                button_info = self.color_buttons[class_id]
                self._update_button_color(button_info['button'], color)
                button_info['label'].setText(f"RGB({color[0]}, {color[1]}, {color[2]})")

    def set_alpha(self, alpha: float):
        """
        设置透明度

        Args:
            alpha: 透明度值 0.0-1.0
        """
        value = int(alpha * 100)
        self.alpha_slider.setValue(value)
