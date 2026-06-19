# -*- coding: utf-8 -*-
"""
可折叠面板组件 (Collapsible Panel Widget)
支持独立展开/折叠的卡片式布局

关键约束：禁止使用 CSS/QSS (setStyleSheet)
必须通过 Qt 原生组件属性或 qtawesome 来实现样式控制
"""

from typing import Optional, Callable, List
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QToolButton,
    QFrame, QSizePolicy, QLabel
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont, QPalette

from ui.widgets.ui_utils import create_header_action_button


class CollapsiblePanel(QWidget):
    """
    可折叠面板组件
    
    Header 结构：
    +----------------------------------------------------------+
    | [▼] Title                              [Action1] [Action2]|
    +----------------------------------------------------------+
    
    - 左侧：折叠箭头 + 标题（点击可折叠）
    - 右侧：操作按钮区域（通过 add_header_action 添加）
    """
    
    # 信号：展开/折叠状态改变
    toggled = Signal(bool)
    
    def __init__(
        self, 
        title: str = "Panel", 
        parent: Optional[QWidget] = None, 
        expanded: bool = True
    ):
        super().__init__(parent)
        self._is_expanded = expanded
        self._title = title
        self._header_actions: List[QToolButton] = []
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """初始化UI"""
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
        
        # 设置尺寸策略：宽度扩展，高度由内容决定
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        # === Header 区域 ===
        self.header_frame = QFrame(self)
        self.header_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.header_frame.setFrameShadow(QFrame.Shadow.Raised)
        self.header_frame.setAutoFillBackground(True)
        
        # 设置 Header 背景色（使用 palette）
        palette = self.header_frame.palette()
        palette.setColor(QPalette.ColorRole.Window, palette.color(QPalette.ColorRole.Button))
        self.header_frame.setPalette(palette)
        
        self.header_layout = QHBoxLayout(self.header_frame)
        self.header_layout.setContentsMargins(4, 4, 4, 4)
        self.header_layout.setSpacing(4)
        
        # --- 左侧：折叠按钮 + 标题 ---
        self.left_container = QWidget()
        self.left_layout = QHBoxLayout(self.left_container)
        self.left_layout.setContentsMargins(0, 0, 0, 0)
        self.left_layout.setSpacing(4)
        
        # 折叠箭头按钮
        self.toggle_button = QToolButton()
        self.toggle_button.setAutoRaise(True)
        self.toggle_button.setCheckable(True)
        self.toggle_button.setChecked(self._is_expanded)
        self.toggle_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if self._is_expanded else Qt.ArrowType.RightArrow
        )
        self.toggle_button.clicked.connect(self._on_toggle_clicked)
        self.left_layout.addWidget(self.toggle_button)
        
        # 标题标签
        self.title_label = QLabel(self._title)
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        self.title_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title_label.mousePressEvent = self._on_title_clicked
        self.left_layout.addWidget(self.title_label)
        
        self.left_layout.addStretch()
        self.header_layout.addWidget(self.left_container, 1)
        
        # --- 右侧：操作按钮区域 ---
        self.actions_container = QWidget()
        self.actions_layout = QHBoxLayout(self.actions_container)
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(4)
        self.header_layout.addWidget(self.actions_container)
        
        self.main_layout.addWidget(self.header_frame)
        
        # === Content 区域 ===
        self.content_frame = QFrame(self)
        self.content_frame.setFrameShape(QFrame.Shape.StyledPanel)
        self.content_frame.setFrameShadow(QFrame.Shadow.Plain)
        self.content_frame.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.content_layout = QVBoxLayout(self.content_frame)
        self.content_layout.setContentsMargins(8, 8, 8, 8)
        self.content_layout.setSpacing(4)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        
        self.main_layout.addWidget(self.content_frame)
        
        # 应用初始展开状态
        self.content_frame.setVisible(self._is_expanded)
    
    def _on_toggle_clicked(self, checked: bool) -> None:
        """折叠按钮点击"""
        self._is_expanded = checked
        self._update_ui()
        self.toggled.emit(checked)
    
    def _on_title_clicked(self, event) -> None:
        """标题点击（触发折叠）"""
        self._is_expanded = not self._is_expanded
        self.toggle_button.setChecked(self._is_expanded)
        self._update_ui()
        self.toggled.emit(self._is_expanded)
    
    def _update_ui(self) -> None:
        """更新UI状态"""
        # 更新箭头方向
        self.toggle_button.setArrowType(
            Qt.ArrowType.DownArrow if self._is_expanded else Qt.ArrowType.RightArrow
        )
        # 更新内容可见性
        self.content_frame.setVisible(self._is_expanded)
    
    def add_header_action(
        self,
        text: str = "",
        icon_name: Optional[str] = None,
        icon_color: str = 'default',
        tooltip: str = "",
        on_clicked: Optional[Callable] = None
    ) -> QToolButton:
        """
        向 Header 右侧添加操作按钮
        
        Args:
            text: 按钮文字
            icon_name: qtawesome 图标名称，如 'fa5s.sync-alt'
            icon_color: 图标Color（预设名或十六进制）
            tooltip: 工具Tip
            on_clicked: 点击回调函数
        
        Returns:
            QToolButton: 创建的按钮（可用于后续操作，如禁用）
        """
        btn = create_header_action_button(
            text=text,
            icon_name=icon_name,
            icon_color=icon_color,
            tooltip=tooltip,
            parent=self.actions_container,
            on_clicked=on_clicked
        )
        
        self.actions_layout.addWidget(btn)
        self._header_actions.append(btn)
        
        return btn
    
    def add_header_widget(self, widget: QWidget) -> None:
        """
        向 Header 右侧添加任意控件
        
        Args:
            widget: 要添加的控件（如 QLabel、QToolButton 等）
        """
        widget.setParent(self.actions_container)
        self.actions_layout.addWidget(widget)
    
    def set_expanded(self, expanded: bool) -> None:
        """设置展开/折叠状态"""
        self._is_expanded = expanded
        self.toggle_button.setChecked(expanded)
        self._update_ui()
    
    def is_expanded(self) -> bool:
        """获取展开状态"""
        return self._is_expanded
    
    def set_title(self, title: str) -> None:
        """设置标题"""
        self._title = title
        self.title_label.setText(title)
    
    def get_content_layout(self) -> QVBoxLayout:
        """获取内容区域布局，用于添加子控件"""
        return self.content_layout
    
    def add_widget(self, widget: QWidget) -> None:
        """向内容区域添加控件"""
        self.content_layout.addWidget(widget)
    
    def add_layout(self, layout) -> None:
        """向内容区域添加布局"""
        self.content_layout.addLayout(layout)


class CollapsibleContainer(QWidget):
    """可折叠面板容器（不带滚动条，由外层控制滚动）"""
    
    def __init__(self, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._panels: List[CollapsiblePanel] = []
        
        self._setup_ui()
    
    def _setup_ui(self) -> None:
        """初始化UI"""
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        
        self.container_layout = QVBoxLayout(self)
        self.container_layout.setContentsMargins(0, 0, 0, 0)
        self.container_layout.setSpacing(8)
        self.container_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    
    def add_panel(self, title: str, expanded: bool = True) -> CollapsiblePanel:
        """
        添加一个可折叠面板
        
        Args:
            title: 面板标题
            expanded: 初始是否展开
        
        Returns:
            CollapsiblePanel: 创建的面板对象
        """
        panel = CollapsiblePanel(title, self, expanded)
        
        self.container_layout.addWidget(panel)
        self._panels.append(panel)
        
        return panel
    
    def get_panel(self, index: int) -> Optional[CollapsiblePanel]:
        """获取指定索引的面板"""
        if 0 <= index < len(self._panels):
            return self._panels[index]
        return None
    
    def get_panels(self) -> List[CollapsiblePanel]:
        """获取所有面板"""
        return self._panels
    
    def expand_all(self) -> None:
        """展开所有面板"""
        for panel in self._panels:
            panel.set_expanded(True)
    
    def collapse_all(self) -> None:
        """折叠所有面板"""
        for panel in self._panels:
            panel.set_expanded(False)
